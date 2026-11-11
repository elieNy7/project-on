//! Les cantiques (`app/database/dao_hymns.py`).

use po_text::py;
use rusqlite::types::Value as SqlValue;
use rusqlite::{Connection, OptionalExtension, Row, params, params_from_iter};
use serde::Serialize;
use unicode_normalization::UnicodeNormalization;

use crate::schema::{HYMN_FTS_DDL, HYMN_FTS_FILL};
use crate::{Database, DbError, Result, table_exists};

/// Un cantique.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Hymn {
    pub id: i64,
    pub original_title: String,
    /// Le titre affiché : le titre commun s'il existe.
    pub title: String,
    pub number: Option<String>,
    pub language: Option<String>,
    pub sort_key: Option<String>,
    pub title_search: Option<String>,
}

/// Une strophe.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Stanza {
    pub stanza_no: i64,
    /// « Strophe 2 », « Refrain ».
    pub label: String,
    pub is_chorus: bool,
    pub text: String,
}

/// Une strophe trouvée par la recherche.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct HymnHit {
    pub id: i64,
    pub hymn_id: i64,
    pub stanza_no: i64,
    pub text: String,
    pub hymn_title: String,
    pub original_title: String,
    pub hymn_number: Option<String>,
    pub label: String,
    /// Tel qu'en base (`NULL` possible sur une très ancienne base).
    pub is_chorus: Option<i64>,
}

const HYMN_COLUMNS: &str = "id, title AS original_title, COALESCE(NULLIF(canonical_title, ''), title) AS title,
                            number, language, sort_key, title_search";

fn hymn_from_row(r: &Row<'_>) -> rusqlite::Result<Hymn> {
    Ok(Hymn {
        id: r.get(0)?,
        original_title: r.get(1)?,
        title: r.get(2)?,
        number: r.get(3)?,
        language: r.get(4)?,
        sort_key: r.get(5)?,
        title_search: r.get(6)?,
    })
}

const HIT_COLUMNS: &str = "hs.id, hs.hymn_id, hs.stanza_no, hs.text,
                           COALESCE(NULLIF(h.canonical_title, ''), h.title) AS hymn_title,
                           h.title AS original_title,
                           h.number AS hymn_number,
                           COALESCE(NULLIF(hs.label, ''), 'Strophe ' || hs.stanza_no) AS label,
                           hs.is_chorus AS is_chorus";

fn hit_from_row(r: &Row<'_>) -> rusqlite::Result<HymnHit> {
    Ok(HymnHit {
        id: r.get(0)?,
        hymn_id: r.get(1)?,
        stanza_no: r.get(2)?,
        text: r.get(3)?,
        hymn_title: r.get(4)?,
        original_title: r.get(5)?,
        hymn_number: r.get(6)?,
        label: r.get(7)?,
        is_chorus: r.get(8)?,
    })
}

/// L'identité d'un titre ou d'une strophe : NFC, espaces regroupées, sans casse (`casefold`).
fn identity_text(value: &str) -> String {
    let normalized: String = value.nfc().collect();
    py::casefold(&py::split(&normalized).collect::<Vec<_>>().join(" "))
}

fn title_search(canonical: &str, title: &str, number: Option<&str>, language: &str) -> String {
    po_text::search_key(&[canonical, title, number.unwrap_or(""), language].join(" "))
}

/// Recrée l'index de recherche des cantiques : un index sans contenu refuse DELETE, et des lignes
/// périmées gêneraient les identifiants réutilisés.
fn rebuild_fts(conn: &Connection) -> rusqlite::Result<()> {
    if !table_exists(conn, "hymn_stanza_fts")? {
        return Ok(());
    }
    conn.execute_batch("DROP TABLE hymn_stanza_fts")?;
    conn.execute_batch(HYMN_FTS_DDL)?;
    conn.execute_batch(HYMN_FTS_FILL)
}

impl Database {
    /// Les cantiques, filtrés par langue et par titre.
    pub fn list_hymns(&self, language: Option<&str>, limit: Option<usize>, query: Option<&str>) -> Result<Vec<Hymn>> {
        let mut sql = format!("SELECT {HYMN_COLUMNS} FROM hymn WHERE (? IS NULL OR language = ?)");
        let mut params: Vec<SqlValue> = vec![language.map(str::to_string).into(), language.map(str::to_string).into()];
        if let Some(q) = query.filter(|q| !q.is_empty()) {
            let q = py::strip(q);
            sql.push_str(" AND (title_search LIKE ? OR unaccent(title) LIKE unaccent(?))");
            params.push(format!("%{}%", po_text::search_key(q)).into());
            params.push(format!("%{q}%").into());
        }
        sql.push_str(" ORDER BY COALESCE(sort_key, ''), number, title COLLATE NOCASE");
        if let Some(limit) = limit {
            sql.push_str(" LIMIT ?");
            params.push(SqlValue::Integer(limit as i64));
        }
        let mut stmt = self.conn.prepare_cached(&sql)?;
        let rows = stmt.query_map(params_from_iter(params), hymn_from_row)?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    pub fn hymn(&self, id: i64) -> Result<Option<Hymn>> {
        Ok(self
            .conn
            .query_row(&format!("SELECT {HYMN_COLUMNS} FROM hymn WHERE id = ?"), [id], hymn_from_row)
            .optional()?)
    }

    /// Les strophes d'un cantique, avec leur étiquette (celle de la base, sinon déduite du texte).
    pub fn stanzas(&self, hymn_id: i64) -> Result<Vec<Stanza>> {
        let mut stmt = self.conn.prepare_cached(
            "SELECT stanza_no, text, label, is_chorus FROM hymn_stanza WHERE hymn_id = ? ORDER BY stanza_no",
        )?;
        type Row = (i64, String, Option<String>, Option<i64>);
        let rows = stmt
            .query_map([hymn_id], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)))?
            .collect::<rusqlite::Result<Vec<Row>>>()?;
        let inferred = po_text::stanza_labels(rows.iter().map(|(_, text, _, _)| text.as_str()));
        Ok(rows
            .into_iter()
            .zip(inferred)
            .map(|((stanza_no, text, label, is_chorus), (inferred_label, _))| Stanza {
                stanza_no,
                label: match label {
                    Some(l) if !l.is_empty() => py::strip(&l).to_string(),
                    _ => inferred_label,
                },
                is_chorus: is_chorus.unwrap_or(0) != 0,
                text,
            })
            .collect())
    }

    /// La recherche dans les strophes : l'index (mots en préfixe), sinon la sous-chaîne.
    pub fn search_stanzas(&self, query: &str, limit: usize) -> Result<Vec<HymnHit>> {
        let q = py::strip(query);
        if q.is_empty() {
            return Ok(Vec::new());
        }
        let mut rows = Vec::new();
        if table_exists(&self.conn, "hymn_stanza_fts")? {
            let fts = po_text::hymn_fts_query(q);
            if !fts.is_empty() {
                let sql = format!(
                    "SELECT {HIT_COLUMNS}
                     FROM hymn_stanza_fts
                     JOIN hymn_stanza hs ON hs.id = hymn_stanza_fts.rowid
                     JOIN hymn h ON h.id = hs.hymn_id
                     WHERE hymn_stanza_fts MATCH ?
                     ORDER BY bm25(hymn_stanza_fts), COALESCE(h.sort_key, ''), h.number, hs.stanza_no
                     LIMIT ?"
                );
                let found = self.conn.prepare_cached(&sql).and_then(|mut stmt| {
                    stmt.query_map(params![fts, limit as i64], hit_from_row)?.collect::<rusqlite::Result<Vec<_>>>()
                });
                rows = found.unwrap_or_default();
            }
        }
        if rows.is_empty() {
            let sql = format!(
                "SELECT {HIT_COLUMNS}
                 FROM hymn_stanza hs
                 JOIN hymn h ON h.id = hs.hymn_id
                 WHERE unaccent(hs.text) LIKE unaccent(?)
                 ORDER BY COALESCE(h.sort_key, ''), h.number, hs.stanza_no
                 LIMIT ?"
            );
            let mut stmt = self.conn.prepare_cached(&sql)?;
            rows = stmt
                .query_map(params![format!("%{q}%"), limit as i64], hit_from_row)?
                .collect::<rusqlite::Result<_>>()?;
        }
        Ok(rows)
    }

    /// Ajoute un cantique importé ; le refrain est reconnu à son texte. Rend son identifiant.
    pub fn import_hymn(
        &mut self,
        title: &str,
        stanzas: &[String],
        number: Option<&str>,
        language: &str,
    ) -> Result<i64> {
        let tx = self.conn.transaction()?;
        let canonical = po_text::clean_hymn_title_for_canonical(title);
        tx.execute(
            "INSERT INTO hymn (title, number, language, sort_key, canonical_title, title_search) VALUES (?, ?, ?, ?, ?, ?)",
            params![title, number, language, title.to_lowercase(), canonical, title_search(&canonical, title, number, language)],
        )?;
        let hymn_id = tx.last_insert_rowid();
        let has_fts = table_exists(&tx, "hymn_stanza_fts")?;
        let labels = po_text::stanza_labels(stanzas.iter().map(String::as_str));
        for (index, (text, (label, chorus))) in stanzas.iter().zip(labels).enumerate() {
            tx.execute(
                "INSERT INTO hymn_stanza (hymn_id, stanza_no, text, label, is_chorus) VALUES (?, ?, ?, ?, ?)",
                params![hymn_id, index as i64 + 1, text, label, i64::from(chorus)],
            )?;
            if has_fts {
                tx.execute(
                    "INSERT INTO hymn_stanza_fts (rowid, text, hymn_title, hymn_number, label) VALUES (?, ?, ?, ?, ?)",
                    params![tx.last_insert_rowid(), text, canonical, number.unwrap_or(""), label],
                )?;
            }
        }
        tx.commit()?;
        Ok(hymn_id)
    }

    /// Les clés de tri des cantiques « PRÉFIXE-12. … » importés d'un recueil
    /// (`_update_sort_keys_for_prefix` de la 2.8) : une lettre par recueil connu, puis le numéro.
    pub fn update_prefix_sort_keys(&mut self, prefix: &str) -> Result<()> {
        let letter = match prefix {
            "CI" => 'A',
            "CV" => 'B',
            "PN" => 'C',
            "AD" => 'D',
            _ => 'I',
        };
        let tx = self.conn.transaction()?;
        let rows: Vec<(i64, String)> = {
            let mut stmt = tx.prepare("SELECT id, title FROM hymn WHERE title LIKE ?")?;
            stmt.query_map([format!("{prefix}-%")], |r| Ok((r.get(0)?, r.get(1)?)))?.collect::<rusqlite::Result<_>>()?
        };
        for (id, title) in rows {
            let rest = &title[prefix.len() + 1..];
            let digits: String = rest.chars().take_while(char::is_ascii_digit).collect();
            if !digits.is_empty()
                && rest[digits.len()..].starts_with('.')
                && let Ok(n) = digits.parse::<u32>()
            {
                tx.execute("UPDATE hymn SET sort_key = ? WHERE id = ?", params![format!("{letter}{n:04}"), id])?;
            }
        }
        tx.commit()?;
        Ok(())
    }

    /// Crée ou remplace un cantique (éditeur) : (texte, est un refrain) par strophe, le refrain étant
    /// marqué par l'opérateur. Tout se fait dans une transaction, index compris.
    pub fn save_hymn(
        &mut self,
        hymn_id: Option<i64>,
        title: &str,
        stanzas: &[(String, bool)],
        number: Option<&str>,
        language: &str,
    ) -> Result<i64> {
        let title = match py::strip(title) {
            "" => "Sans titre",
            t => t,
        };
        let stanzas: Vec<(&str, bool)> =
            stanzas.iter().map(|(t, c)| (py::strip(t), *c)).filter(|(t, _)| !t.is_empty()).collect();
        if stanzas.is_empty() {
            return Err(DbError::EmptyHymn);
        }
        let tx = self.conn.transaction()?;
        let canonical = po_text::clean_hymn_title_for_canonical(title);
        let search = title_search(&canonical, title, number, language);
        let hymn_id = match hymn_id {
            None => {
                tx.execute(
                    "INSERT INTO hymn (title, number, language, sort_key, canonical_title, title_search) VALUES (?, ?, ?, ?, ?, ?)",
                    params![title, number, language, title.to_lowercase(), canonical, search],
                )?;
                tx.last_insert_rowid()
            }
            Some(id) => {
                tx.execute(
                    "UPDATE hymn SET title = ?, number = ?, language = ?, sort_key = ?, canonical_title = ?, title_search = ? WHERE id = ?",
                    params![title, number, language, title.to_lowercase(), canonical, search, id],
                )?;
                tx.execute("DELETE FROM hymn_stanza WHERE hymn_id = ?", [id])?;
                id
            }
        };
        let (mut verse_no, mut chorus_no) = (0, 0);
        for (index, (text, is_chorus)) in stanzas.into_iter().enumerate() {
            // Même convention que les cantiques importés : un refrain commence par « Refrain »
            // (retiré à la projection), et la maintenance qui relit les textes le garde ainsi.
            let text = if is_chorus && !po_text::is_chorus(text) {
                format!("Refrain\n{text}")
            } else if !is_chorus && po_text::is_chorus(text) {
                match po_text::strip_hymn_projection_label(text) {
                    s if s.is_empty() => text.to_string(),
                    s => s,
                }
            } else {
                text.to_string()
            };
            let label = if is_chorus {
                chorus_no += 1;
                if chorus_no == 1 { "Refrain".to_string() } else { format!("Refrain {chorus_no}") }
            } else {
                verse_no += 1;
                format!("Strophe {verse_no}")
            };
            tx.execute(
                "INSERT INTO hymn_stanza (hymn_id, stanza_no, text, label, is_chorus) VALUES (?, ?, ?, ?, ?)",
                params![hymn_id, index as i64 + 1, text, label, i64::from(is_chorus)],
            )?;
        }
        rebuild_fts(&tx)?;
        tx.commit()?;
        Ok(hymn_id)
    }

    /// Un cantique de même titre existe-t-il ? La casse et les espaces répétées ne comptent pas ;
    /// les accents et la ponctuation, si (« Grâce » n'est pas « Grâce infinie »).
    pub fn hymn_exists(&self, title: &str) -> Result<bool> {
        let key = identity_text(title);
        if key.is_empty() {
            return Ok(false);
        }
        let mut stmt = self.conn.prepare("SELECT title FROM hymn")?;
        let titles = stmt.query_map([], |r| r.get::<_, String>(0))?;
        for t in titles {
            if identity_text(&t?) == key {
                return Ok(true);
            }
        }
        Ok(false)
    }

    /// Un cantique identique existe-t-il : même titre (comme [`Self::hymn_exists`]) et mêmes strophes,
    /// dans le même ordre ?
    pub fn exact_duplicate_exists(&self, title: &str, stanzas: &[String]) -> Result<bool> {
        let key = identity_text(title);
        if key.is_empty() {
            return Ok(false);
        }
        let wanted: Vec<String> = stanzas.iter().map(|s| identity_text(s)).collect();
        let mut stmt = self.conn.prepare("SELECT id, title FROM hymn")?;
        let candidates = stmt
            .query_map([], |r| Ok((r.get::<_, i64>(0)?, r.get::<_, String>(1)?)))?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        let mut texts = self.conn.prepare("SELECT text FROM hymn_stanza WHERE hymn_id = ? ORDER BY stanza_no")?;
        for (id, t) in candidates {
            if identity_text(&t) != key {
                continue;
            }
            let stored: Vec<String> = texts
                .query_map([id], |r| r.get::<_, String>(0))?
                .map(|t| t.map(|t| identity_text(&t)))
                .collect::<rusqlite::Result<_>>()?;
            if stored == wanted {
                return Ok(true);
            }
        }
        Ok(false)
    }

    pub fn delete_hymn(&mut self, hymn_id: i64) -> Result<()> {
        let tx = self.conn.transaction()?;
        tx.execute("DELETE FROM hymn_stanza WHERE hymn_id = ?", [hymn_id])?;
        tx.execute("DELETE FROM hymn WHERE id = ?", [hymn_id])?;
        rebuild_fts(&tx)?;
        tx.commit()?;
        Ok(())
    }

    /// Supprime tous les cantiques ; rend leur nombre.
    pub fn delete_all_hymns(&mut self) -> Result<i64> {
        let tx = self.conn.transaction()?;
        let count: i64 = tx.query_row("SELECT COUNT(*) FROM hymn", [], |r| r.get(0))?;
        tx.execute_batch("DELETE FROM hymn_stanza; DELETE FROM hymn;")?;
        rebuild_fts(&tx)?;
        tx.commit()?;
        Ok(count)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::testing;

    fn with_fts() -> Database {
        let db = testing::empty();
        db.conn.execute_batch(HYMN_FTS_DDL).unwrap();
        db
    }

    #[test]
    fn import_search_and_labels() {
        let mut db = with_fts();
        let stanzas = ["Grâce infinie, ô Dieu".to_string(), "Refrain\nAlléluia".to_string(), "Il vient".to_string()];
        let id = db.import_hymn("GRÂCE INFINIE", &stanzas, Some("12"), "fr").unwrap();
        let hymn = db.hymn(id).unwrap().unwrap();
        assert_eq!(hymn.title, "Grâce Infinie");
        assert_eq!(hymn.sort_key.as_deref(), Some("grâce infinie"));
        let labels: Vec<String> = db.stanzas(id).unwrap().into_iter().map(|s| s.label).collect();
        assert_eq!(labels, ["Strophe 1", "Refrain", "Strophe 2"]);
        assert_eq!(db.search_stanzas("alleluia", 10).unwrap()[0].stanza_no, 2);
        // « ia, ô » n'est pas un début de mot : la sous-chaîne prend le relais.
        assert_eq!(db.search_stanzas("ie, o", 10).unwrap()[0].stanza_no, 1);
        assert_eq!(db.list_hymns(Some("fr"), None, Some("grace")).unwrap().len(), 1);
        assert!(db.hymn_exists("  grâce   INFINIE ").unwrap());
        assert!(!db.hymn_exists("Grace infinie").unwrap());
        assert!(db.exact_duplicate_exists("Grâce infinie", &stanzas).unwrap());
    }

    #[test]
    fn editor_marks_choruses_and_rebuilds_the_index() {
        let mut db = with_fts();
        let id = db
            .save_hymn(
                None,
                "  ",
                &[("Il vient".into(), false), ("Gloire".into(), true), ("  ".into(), false)],
                None,
                "fr",
            )
            .unwrap();
        let stanzas = db.stanzas(id).unwrap();
        assert_eq!(stanzas.len(), 2);
        assert_eq!((stanzas[1].text.as_str(), stanzas[1].is_chorus), ("Refrain\nGloire", true));
        assert_eq!(db.hymn(id).unwrap().unwrap().title, "Sans titre");
        let id = db.save_hymn(Some(id), "Il vient", &[("Refrain : Il vient".into(), false)], None, "fr").unwrap();
        assert_eq!(db.stanzas(id).unwrap()[0].text, "Il vient");
        assert_eq!(db.search_stanzas("vient", 10).unwrap().len(), 1);
        assert!(matches!(db.save_hymn(None, "x", &[], None, "fr"), Err(DbError::EmptyHymn)));
        assert_eq!(db.delete_all_hymns().unwrap(), 1);
        assert!(db.search_stanzas("vient", 10).unwrap().is_empty());
    }
}
