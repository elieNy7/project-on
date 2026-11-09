//! La base de données de Project-On : le même fichier SQLite que la 2.x, sans conversion.
//!
//! Phase 0 : la lecture des sermons et la recherche dans leurs paragraphes, assez pour mesurer la
//! pile. Les requêtes reprennent celles de `app.database.dao_sermons` (2.8).

use std::path::Path;
use std::time::Duration;

use rusqlite::functions::{Context, FunctionFlags};
use rusqlite::types::ValueRef;
use rusqlite::{Connection, OpenFlags, params_from_iter};

/// Les erreurs de la base, présentées en français à l'utilisateur par l'application.
#[derive(Debug, thiserror::Error)]
pub enum DbError {
    #[error("la base de données « {path} » est introuvable")]
    Missing { path: String },
    #[error("erreur SQLite : {0}")]
    Sqlite(#[from] rusqlite::Error),
}

pub type Result<T> = std::result::Result<T, DbError>;

/// Comment ouvrir la base.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    /// Lecture seule : rien ne peut être écrit, même par erreur (mesures, aperçus).
    ReadOnly,
    ReadWrite,
}

/// Un sermon de la liste (onglet Prédications).
#[derive(Debug, Clone, PartialEq)]
pub struct Sermon {
    pub id: i64,
    /// Code de date (« 63-0317M ») ; les livres et brochures commencent par BK- ou TR-.
    pub date: String,
    /// Titre affiché (titre canonique s'il existe).
    pub title: String,
    /// Le traducteur (VGR, SHP, BSS).
    pub translator: String,
    pub language: String,
    pub location: String,
}

/// Un paragraphe trouvé par la recherche.
#[derive(Debug, Clone, PartialEq)]
pub struct ParagraphHit {
    pub sermon_id: i64,
    pub paragraph_no: i64,
    pub marker: String,
    /// « 63-0317M - Titre - ¶12 », comme la 2.x.
    pub reference: String,
    pub text: String,
}

/// Les filtres de la liste des sermons.
#[derive(Debug, Clone, Default)]
pub struct SermonFilter<'a> {
    pub translator: Option<&'a str>,
    pub language: Option<&'a str>,
    pub title: Option<&'a str>,
    pub limit: Option<usize>,
}

/// La connexion à la base.
pub struct Database {
    conn: Connection,
}

/// Les sermons seulement : les chapitres de livres (BK-) et les brochures (TR-) ont leur onglet.
const NOT_A_BOOK: &str = "COALESCE(date, '') NOT LIKE 'BK-%' AND COALESCE(date, '') NOT LIKE 'TR-%'";

impl Database {
    pub fn open(path: &Path, mode: Mode) -> Result<Self> {
        if !path.is_file() {
            return Err(DbError::Missing { path: path.display().to_string() });
        }
        let flags = match mode {
            Mode::ReadOnly => OpenFlags::SQLITE_OPEN_READ_ONLY,
            Mode::ReadWrite => OpenFlags::SQLITE_OPEN_READ_WRITE,
        } | OpenFlags::SQLITE_OPEN_NO_MUTEX
            | OpenFlags::SQLITE_OPEN_URI;
        let conn = Connection::open_with_flags(path, flags)?;
        conn.busy_timeout(Duration::from_secs(30))?;
        // Mêmes réglages de lecture que la 2.x (connection.py).
        conn.execute_batch("PRAGMA temp_store = MEMORY; PRAGMA cache_size = -64000; PRAGMA mmap_size = 268435456;")?;
        register_unaccent(&conn)?;
        Ok(Database { conn })
    }

    /// Le numéro de version du schéma (`PRAGMA user_version`).
    pub fn schema_version(&self) -> Result<i64> {
        Ok(self.conn.query_row("PRAGMA user_version", [], |r| r.get(0))?)
    }

    /// La liste des sermons, triée par date puis par titre (`SermonDAO.list_sermons`).
    pub fn list_sermons(&self, filter: &SermonFilter<'_>) -> Result<Vec<Sermon>> {
        let mut sql = format!(
            "SELECT id, COALESCE(date, ''), COALESCE(NULLIF(canonical_title, ''), title),
                    COALESCE(tradition, ''), COALESCE(language, ''), COALESCE(location, '')
             FROM sermon WHERE {NOT_A_BOOK}"
        );
        let mut params: Vec<String> = Vec::new();
        if let Some(translator) = filter.translator {
            sql.push_str(" AND tradition = ?");
            params.push(translator.to_uppercase());
        }
        if let Some(title) = filter.title.map(po_text::plain_query).filter(|t| !t.is_empty()) {
            sql.push_str(" AND (title_search LIKE ? OR unaccent(title) LIKE unaccent(?))");
            params.push(format!("%{}%", po_text::search_key(&title)));
            params.push(format!("%{title}%"));
        }
        if let Some(language) = filter.language {
            sql.push_str(" AND language = ?");
            params.push(language.chars().take(2).collect::<String>().to_lowercase());
        }
        sql.push_str(" ORDER BY date, title COLLATE NOCASE");
        if let Some(limit) = filter.limit {
            sql.push_str(&format!(" LIMIT {limit}"));
        }
        let mut stmt = self.conn.prepare_cached(&sql)?;
        let rows = stmt.query_map(params_from_iter(params.iter()), |r| {
            Ok(Sermon {
                id: r.get(0)?,
                date: r.get(1)?,
                title: r.get(2)?,
                translator: r.get(3)?,
                language: r.get(4)?,
                location: r.get(5)?,
            })
        })?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    /// Recherche dans les paragraphes des sermons (`SermonDAO.search_paragraphs`) : l'index FTS5
    /// d'abord (mots en préfixe, classement bm25), puis, s'il ne trouve rien et si
    /// `substring_fallback` le permet, une recherche par sous-chaîne sans accents.
    pub fn search_paragraphs(
        &self,
        query: &str,
        language: Option<&str>,
        translator: Option<&str>,
        limit: usize,
        substring_fallback: bool,
    ) -> Result<Vec<ParagraphHit>> {
        let query = query.trim();
        if query.is_empty() {
            return Ok(Vec::new());
        }
        let fts = po_text::fts_query(query);
        let mut hits = Vec::new();
        let mut fts_ok = false;
        if !fts.is_empty() {
            let base = format!(
                "{SELECT_HIT}
                 FROM sermon_paragraph_fts
                 JOIN sermon_paragraph p ON p.id = sermon_paragraph_fts.rowid
                 JOIN sermon s ON s.id = p.sermon_id
                 WHERE sermon_paragraph_fts MATCH ?
                   AND s.date NOT LIKE 'BK-%' AND s.date NOT LIKE 'TR-%'"
            );
            let order = "ORDER BY bm25(sermon_paragraph_fts), s.date, p.paragraph_no";
            match self.hits(&base, fts, language, translator, order, limit) {
                Ok(found) => {
                    hits = found;
                    fts_ok = true;
                }
                // Une requête que FTS5 refuse : on se rabat sur la sous-chaîne, comme la 2.x.
                Err(DbError::Sqlite(_)) => {}
                Err(other) => return Err(other),
            }
        }
        if hits.is_empty() && (!fts_ok || substring_fallback) {
            let base = format!(
                "{SELECT_HIT}
                 FROM sermon_paragraph p
                 JOIN sermon s ON s.id = p.sermon_id
                 WHERE unaccent(p.text) LIKE unaccent(?)
                   AND s.date NOT LIKE 'BK-%' AND s.date NOT LIKE 'TR-%'"
            );
            let needle = format!("%{}%", po_text::plain_query(query));
            hits = self.hits(&base, needle, language, translator, "ORDER BY s.date, p.paragraph_no", limit)?;
        }
        Ok(hits)
    }

    fn hits(
        &self,
        base: &str,
        first: String,
        language: Option<&str>,
        translator: Option<&str>,
        order: &str,
        limit: usize,
    ) -> Result<Vec<ParagraphHit>> {
        let mut sql = base.to_string();
        let mut params = vec![first];
        if let Some(translator) = translator {
            sql.push_str(" AND s.tradition = ?");
            params.push(translator.to_uppercase());
        }
        if let Some(language) = language {
            sql.push_str(" AND s.language = ?");
            params.push(language.chars().take(2).collect::<String>().to_lowercase());
        }
        sql.push_str(&format!(" {order} LIMIT {limit}"));
        let mut stmt = self.conn.prepare_cached(&sql)?;
        let rows = stmt.query_map(params_from_iter(params.iter()), |r| {
            let sermon_id: i64 = r.get(0)?;
            let paragraph_no: i64 = r.get(1)?;
            let marker: String = r.get(2)?;
            let marker = if marker.trim().is_empty() { format!("¶{paragraph_no}") } else { marker.trim().to_string() };
            let date: String = r.get(4)?;
            let title: String = r.get(5)?;
            let reference = [date.trim(), title.trim(), marker.as_str()]
                .iter()
                .filter(|p| !p.is_empty())
                .copied()
                .collect::<Vec<_>>();
            Ok(ParagraphHit { sermon_id, paragraph_no, reference: reference.join(" - "), marker, text: r.get(3)? })
        })?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    /// Les paragraphes d'un sermon, dans l'ordre.
    pub fn paragraphs(&self, sermon_id: i64) -> Result<Vec<(i64, String)>> {
        let mut stmt = self.conn.prepare_cached(
            "SELECT paragraph_no, text FROM sermon_paragraph WHERE sermon_id = ? ORDER BY paragraph_no",
        )?;
        let rows = stmt.query_map([sermon_id], |r| Ok((r.get(0)?, r.get(1)?)))?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }
}

const SELECT_HIT: &str = "SELECT p.sermon_id, p.paragraph_no, COALESCE(NULLIF(p.marker, ''), p.ref, ''), p.text,
        COALESCE(s.date, ''), COALESCE(NULLIF(s.canonical_title, ''), s.title)";

/// `unaccent()` dans SQLite, lue sur place (pas de passage par Python) : mêmes règles que
/// l'extension de la 2.8. NULL, 0 et "" donnent "" ; un nombre est d'abord converti en texte.
fn register_unaccent(conn: &Connection) -> rusqlite::Result<()> {
    conn.create_scalar_function(
        "unaccent",
        1,
        FunctionFlags::SQLITE_UTF8 | FunctionFlags::SQLITE_DETERMINISTIC | FunctionFlags::SQLITE_INNOCUOUS,
        |ctx: &Context<'_>| {
            Ok(match ctx.get_raw(0) {
                ValueRef::Null | ValueRef::Integer(0) | ValueRef::Real(0.0) | ValueRef::Blob([]) => String::new(),
                ValueRef::Text(bytes) | ValueRef::Blob(bytes) => po_text::fold(&String::from_utf8_lossy(bytes)),
                ValueRef::Integer(i) => i.to_string(),
                ValueRef::Real(f) => po_text::fold(&f.to_string()),
            })
        },
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Une petite base au schéma de la 2.x, en mémoire.
    fn sample() -> Database {
        let conn = Connection::open_in_memory().unwrap();
        register_unaccent(&conn).unwrap();
        conn.execute_batch(
            "CREATE TABLE sermon (id INTEGER PRIMARY KEY, title TEXT NOT NULL, date TEXT, tradition TEXT NOT NULL,
                 language TEXT, source_path TEXT, sort_key TEXT, location TEXT DEFAULT '',
                 canonical_title TEXT DEFAULT '', title_search TEXT DEFAULT '');
             CREATE TABLE sermon_paragraph (id INTEGER PRIMARY KEY, sermon_id INTEGER NOT NULL,
                 paragraph_no INTEGER NOT NULL, ref TEXT, text TEXT NOT NULL, marker TEXT DEFAULT '');
             CREATE VIRTUAL TABLE sermon_paragraph_fts USING fts5(text, ref, sermon_title, canonical_title,
                 content='', detail=full, tokenize='unicode61 remove_diacritics 2');
             INSERT INTO sermon VALUES (1, 'LA FOI EST UNE FERME ASSURANCE', '47-0412', 'VGR', 'fr', '', '47-0412',
                 '', 'La Foi Est une Ferme Assurance', 'la foi est une ferme assurance');
             INSERT INTO sermon VALUES (2, 'Chapitre 1', 'BK-AGES-CH1', 'VGR', 'fr', '', '', '', '', 'chapitre 1');
             INSERT INTO sermon_paragraph VALUES (10, 1, 1, '', 'Ô Éternel, la foi est une ferme assurance.', '¶1');
             INSERT INTO sermon_paragraph VALUES (11, 1, 2, '', 'Il était là, déjà.', '');
             INSERT INTO sermon_paragraph VALUES (20, 2, 1, '', 'La foi dans le livre.', '');
             INSERT INTO sermon_paragraph_fts (rowid, text) VALUES (10, 'Ô Éternel, la foi est une ferme assurance.');
             INSERT INTO sermon_paragraph_fts (rowid, text) VALUES (11, 'Il était là, déjà.');
             INSERT INTO sermon_paragraph_fts (rowid, text) VALUES (20, 'La foi dans le livre.');",
        )
        .unwrap();
        Database { conn }
    }

    #[test]
    fn lists_sermons_but_not_books() {
        let db = sample();
        let sermons = db.list_sermons(&SermonFilter::default()).unwrap();
        assert_eq!(sermons.len(), 1);
        assert_eq!(sermons[0].title, "La Foi Est une Ferme Assurance");
        let found = db.list_sermons(&SermonFilter { title: Some("fermé"), ..Default::default() }).unwrap();
        assert_eq!(found.len(), 1);
    }

    #[test]
    fn full_text_search_ignores_accents() {
        let db = sample();
        let hits = db.search_paragraphs("eternel", Some("fr"), None, 100, true).unwrap();
        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].reference, "47-0412 - La Foi Est une Ferme Assurance - ¶1");
    }

    #[test]
    fn substring_fallback_and_marker() {
        let db = sample();
        // « ait là, d » n'est pas un début de mot : seule la sous-chaîne le trouve.
        let hits = db.search_paragraphs("ait la, d", None, Some("vgr"), 100, true).unwrap();
        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].marker, "¶2");
        assert!(db.search_paragraphs("ait la, d", None, None, 100, false).unwrap().is_empty());
    }
}
