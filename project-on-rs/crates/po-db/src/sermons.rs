//! Les prédications, les livres (onglet « Livres ») et l'Exposé des Sept Âges
//! (`app/database/dao_sermons.py`).

use po_text::py;
use rusqlite::types::Value as SqlValue;
use rusqlite::{OptionalExtension, Row, params, params_from_iter};
use serde::Serialize;

use crate::{Database, DbError, Result, language_code, table_exists};

/// Les sermons seulement : les chapitres de livres (BK-) et les brochures (TR-) ont leur onglet.
const NOT_A_BOOK: &str = "COALESCE(date, '') NOT LIKE 'BK-%' AND COALESCE(date, '') NOT LIKE 'TR-%'";
const TITLE: &str = "COALESCE(NULLIF(canonical_title, ''), title)";
const S_TITLE: &str = "COALESCE(NULLIF(s.canonical_title, ''), s.title)";
const MARKER: &str = "COALESCE(NULLIF(p.marker, ''), p.ref, '')";

/// Une prédication (une traduction d'un sermon).
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Sermon {
    pub id: i64,
    /// Le code de date (« 63-0317M »).
    pub date: Option<String>,
    /// Le titre affiché : le titre commun s'il existe.
    pub title: String,
    /// Le titre de la source.
    pub original_title: String,
    /// Le traducteur (VGR, SHP, BSS).
    pub tradition: String,
    pub language: Option<String>,
    pub location: String,
    /// La date telle qu'imprimée (sermons SHP).
    pub printed_date: String,
}

/// Le tri de la liste des sermons.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub enum SermonSort {
    #[default]
    Date,
    Title,
    Location,
}

/// Les filtres de la liste des sermons (`list_sermons`).
#[derive(Debug, Clone, Default)]
pub struct SermonFilter<'a> {
    /// Le traducteur (VGR, SHP, BSS), quelle que soit la casse.
    pub translator: Option<&'a str>,
    pub language: Option<&'a str>,
    pub title: Option<&'a str>,
    /// Une date « 1965-12-31 » ou un code « 65-1231 » ; `__NODATE__` pour les sermons sans date.
    pub date_from: Option<&'a str>,
    pub date_to: Option<&'a str>,
    pub location: Option<&'a str>,
    pub sort: SermonSort,
    pub limit: Option<usize>,
}

/// Un paragraphe d'une prédication ou d'un chapitre.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Paragraph {
    pub paragraph_no: i64,
    /// « ¶12 », « E-76 », « 112-3 ».
    pub marker: String,
    /// La référence de la source, telle quelle.
    #[serde(rename = "ref")]
    pub raw_ref: Option<String>,
    pub text: String,
}

/// Un paragraphe trouvé par la recherche dans les prédications.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct ParagraphHit {
    pub sermon_id: i64,
    pub paragraph_no: i64,
    pub marker: String,
    /// « 63-0317M - Titre - ¶12 ».
    pub reference: String,
    pub raw_ref: Option<String>,
    pub text: String,
    pub sermon_title: String,
    pub original_title: String,
    pub sermon_date: Option<String>,
    pub sermon_tradition: String,
}

/// La recherche dans les paragraphes des prédications.
#[derive(Debug, Clone)]
pub struct ParagraphSearch<'a> {
    pub query: &'a str,
    pub language: Option<&'a str>,
    pub translator: Option<&'a str>,
    pub limit: usize,
    /// Si l'index ne trouve rien, chercher la sous-chaîne (lent : 2 à 3 s sur toute la base).
    pub substring_fallback: bool,
}

/// Un ouvrage de l'onglet « Livres ».
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Book {
    pub key: String,
    pub title: String,
    pub date_prefix: String,
    pub tradition: String,
}

/// Un chapitre d'un ouvrage (ou de l'Exposé).
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct BookChapter {
    pub id: i64,
    pub title: String,
    pub original_title: String,
    /// 0 pour l'introduction ; pour une brochure, sa place dans la collection.
    pub chapter_num: i64,
    pub date_code: Option<String>,
}

/// Un paragraphe trouvé dans un ouvrage ou dans l'Exposé.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct BookHit {
    pub sermon_id: i64,
    pub paragraph_no: i64,
    pub marker: String,
    pub reference: String,
    pub raw_ref: Option<String>,
    pub text: String,
    pub title: String,
}

fn opt_str(row: &Row<'_>, index: usize) -> rusqlite::Result<String> {
    Ok(row.get::<_, Option<String>>(index)?.unwrap_or_default())
}

fn sermon_from_row(r: &Row<'_>) -> rusqlite::Result<Sermon> {
    Ok(Sermon {
        id: r.get(0)?,
        date: r.get(1)?,
        original_title: r.get(2)?,
        title: r.get(3)?,
        tradition: r.get(4)?,
        language: r.get(5)?,
        location: opt_str(r, 6)?,
        printed_date: opt_str(r, 7)?,
    })
}

const SERMON_COLUMNS: &str = "id, date, title AS original_title, COALESCE(NULLIF(canonical_title, ''), title) AS title, tradition, language, location, printed_date";

/// Le repère d'un paragraphe : celui de la base, sinon celui de la 2.8 (`_get_marker`).
fn stored_or_derived_marker(stored: Option<String>, reference: Option<&str>, paragraph_no: i64) -> String {
    match stored {
        Some(m) if !m.is_empty() => py::strip(&m).to_string(),
        _ => po_text::paragraph_marker(reference.unwrap_or(""), paragraph_no),
    }
}

impl Database {
    /// Les années des sermons (pour le filtre par année).
    pub fn list_sermon_years(
        &self,
        translator: Option<&str>,
        language: Option<&str>,
        title: Option<&str>,
    ) -> Result<Vec<i32>> {
        let mut sql = format!("SELECT DISTINCT date FROM sermon WHERE {NOT_A_BOOK}");
        let mut params: Vec<String> = Vec::new();
        if let Some(t) = translator.filter(|t| !t.is_empty()) {
            sql.push_str(" AND tradition = ?");
            params.push(t.to_uppercase());
        }
        if let Some(l) = language.filter(|l| !l.is_empty()) {
            sql.push_str(" AND language = ?");
            params.push(language_code(l));
        }
        if let Some(q) = title.filter(|q| !q.is_empty()) {
            let q = py::strip(q);
            sql.push_str(" AND (title_search LIKE ? OR unaccent(title) LIKE unaccent(?))");
            params.push(format!("%{}%", po_text::search_key(q)));
            params.push(format!("%{q}%"));
        }
        let mut stmt = self.conn.prepare(&sql)?;
        let dates = stmt.query_map(params_from_iter(&params), |r| r.get::<_, Option<String>>(0))?;
        let mut years = std::collections::BTreeSet::new();
        for date in dates {
            if let Some(year) = date?.as_deref().and_then(po_text::sermon_year) {
                years.insert(year);
            }
        }
        Ok(years.into_iter().collect())
    }

    /// Les traducteurs des sermons d'une langue, en capitales.
    pub fn list_translators(&self, language: &str) -> Result<Vec<String>> {
        let mut stmt = self.conn.prepare(
            "SELECT DISTINCT tradition FROM sermon WHERE language = ? AND tradition IS NOT NULL AND tradition != ''",
        )?;
        let rows = stmt.query_map([language_code(language)], |r| r.get::<_, String>(0))?;
        let mut out: Vec<String> =
            rows.collect::<rusqlite::Result<Vec<_>>>()?.iter().map(|t| t.to_uppercase()).collect();
        out.sort();
        out.dedup();
        Ok(out)
    }

    /// La liste des sermons (`list_sermons`).
    pub fn list_sermons(&self, filter: &SermonFilter<'_>) -> Result<Vec<Sermon>> {
        let date_from = filter.date_from.and_then(po_text::normalize_filter_date);
        let date_to = filter.date_to.and_then(po_text::normalize_filter_date);
        let mut sql = format!("SELECT {SERMON_COLUMNS} FROM sermon WHERE {NOT_A_BOOK}");
        let mut params: Vec<SqlValue> = Vec::new();
        if let Some(t) = filter.translator.filter(|t| !t.is_empty()) {
            sql.push_str(" AND tradition = ?");
            params.push(t.to_uppercase().into());
        }
        if let Some(q) = filter.title.filter(|q| !q.is_empty()) {
            let q = po_text::plain_query(q);
            sql.push_str(" AND (title_search LIKE ? OR unaccent(title) LIKE unaccent(?))");
            params.push(format!("%{}%", po_text::search_key(&q)).into());
            params.push(format!("%{q}%").into());
        }
        if let Some(place) = filter.location.filter(|l| !l.is_empty()) {
            sql.push_str(" AND unaccent(location) LIKE unaccent(?)");
            params.push(format!("%{}%", py::strip(place)).into());
        }
        if date_from.as_deref() == Some("__NODATE__") || date_to.as_deref() == Some("__NODATE__") {
            sql.push_str(" AND (date IS NULL OR date = '' OR date NOT GLOB '[0-9]*')");
        } else {
            if let Some(d) = date_from {
                sql.push_str(" AND date >= ?");
                params.push(d.into());
            }
            if let Some(d) = date_to {
                sql.push_str(" AND date <= ?");
                params.push(d.into());
            }
        }
        if let Some(l) = filter.language.filter(|l| !l.is_empty()) {
            sql.push_str(" AND language = ?");
            params.push(language_code(l).into());
        }
        sql.push_str(match filter.sort {
            SermonSort::Date => " ORDER BY date, title COLLATE NOCASE",
            SermonSort::Title => " ORDER BY title COLLATE NOCASE, date",
            SermonSort::Location => " ORDER BY location COLLATE NOCASE, date, title COLLATE NOCASE",
        });
        if let Some(limit) = filter.limit.filter(|&l| l > 0) {
            sql.push_str(" LIMIT ?");
            params.push(SqlValue::Integer(limit as i64));
        }
        let mut stmt = self.conn.prepare_cached(&sql)?;
        let rows = stmt.query_map(params_from_iter(params), sermon_from_row)?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    /// Une prédication.
    pub fn sermon(&self, id: i64) -> Result<Option<Sermon>> {
        let sql = format!("SELECT {SERMON_COLUMNS} FROM sermon WHERE id = ?");
        Ok(self.conn.query_row(&sql, [id], sermon_from_row).optional()?)
    }

    /// Les paragraphes d'une prédication ou d'un chapitre, dans l'ordre.
    pub fn paragraphs(&self, sermon_id: i64) -> Result<Vec<Paragraph>> {
        let mut stmt = self.conn.prepare_cached(
            "SELECT paragraph_no, ref, text, marker FROM sermon_paragraph WHERE sermon_id = ? ORDER BY paragraph_no",
        )?;
        let rows = stmt.query_map([sermon_id], |r| {
            let paragraph_no: i64 = r.get(0)?;
            let raw_ref: Option<String> = r.get(1)?;
            let marker = stored_or_derived_marker(r.get(3)?, raw_ref.as_deref(), paragraph_no);
            Ok(Paragraph { paragraph_no, marker, raw_ref, text: r.get(2)? })
        })?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    /// La recherche dans les prédications : l'index (mots en préfixe, « expression exacte »,
    /// classement bm25), puis, s'il échoue ou ne trouve rien et si on le permet, la sous-chaîne
    /// sans accents.
    pub fn search_paragraphs(&self, search: &ParagraphSearch<'_>) -> Result<Vec<ParagraphHit>> {
        let query = py::strip(search.query);
        if query.is_empty() {
            return Ok(Vec::new());
        }
        let select = format!(
            "SELECT p.sermon_id, p.paragraph_no, p.ref, p.text, {MARKER} AS marker, s.title AS original_title,
                    {S_TITLE} AS title, s.date, s.tradition"
        );
        let mut hits = Vec::new();
        let mut fts_succeeded = false;
        if table_exists(&self.conn, "sermon_paragraph_fts")? {
            let fts = po_text::fts_query(query);
            if !fts.is_empty() {
                let base = format!(
                    "{select}
                     FROM sermon_paragraph_fts
                     JOIN sermon_paragraph p ON p.id = sermon_paragraph_fts.rowid
                     JOIN sermon s ON s.id = p.sermon_id
                     WHERE sermon_paragraph_fts MATCH ?
                       AND s.date NOT LIKE 'BK-%' AND s.date NOT LIKE 'TR-%'"
                );
                let order = "ORDER BY bm25(sermon_paragraph_fts), s.date, p.paragraph_no";
                match self.hits(&base, fts, search, order) {
                    Ok(found) => {
                        hits = found;
                        fts_succeeded = true;
                    }
                    // Une requête que FTS5 refuse : la sous-chaîne prend le relais, comme en 2.8.
                    Err(DbError::Sqlite(_)) => {}
                    Err(other) => return Err(other),
                }
            }
        }
        if hits.is_empty() && (!fts_succeeded || search.substring_fallback) {
            let base = format!(
                "{select}
                 FROM sermon_paragraph p
                 JOIN sermon s ON s.id = p.sermon_id
                 WHERE unaccent(p.text) LIKE unaccent(?)
                   AND s.date NOT LIKE 'BK-%' AND s.date NOT LIKE 'TR-%'"
            );
            let needle = format!("%{}%", po_text::plain_query(query));
            hits = self.hits(&base, needle, search, "ORDER BY s.date, p.paragraph_no")?;
        }
        Ok(hits)
    }

    fn hits(&self, base: &str, first: String, search: &ParagraphSearch<'_>, order: &str) -> Result<Vec<ParagraphHit>> {
        let mut sql = base.to_string();
        let mut params: Vec<SqlValue> = vec![first.into()];
        if let Some(t) = search.translator.filter(|t| !t.is_empty()) {
            sql.push_str(" AND s.tradition = ?");
            params.push(t.to_uppercase().into());
        }
        if let Some(l) = search.language.filter(|l| !l.is_empty()) {
            sql.push_str(" AND s.language = ?");
            params.push(language_code(l).into());
        }
        sql.push_str(&format!(" {order} LIMIT ?"));
        params.push(SqlValue::Integer(search.limit as i64));
        let mut stmt = self.conn.prepare_cached(&sql)?;
        let rows = stmt.query_map(params_from_iter(params), |r| {
            let sermon_id: i64 = r.get(0)?;
            let paragraph_no: i64 = r.get(1)?;
            let raw_ref: Option<String> = r.get(2)?;
            let marker = py::strip(&opt_str(r, 4)?).to_string();
            let marker = if marker.is_empty() {
                po_text::paragraph_marker(raw_ref.as_deref().unwrap_or(""), paragraph_no)
            } else {
                marker
            };
            let title: String = r.get(6)?;
            let date: Option<String> = r.get(7)?;
            Ok(ParagraphHit {
                sermon_id,
                paragraph_no,
                reference: po_text::format_reference(date.as_deref().unwrap_or(""), &title, &marker),
                marker,
                raw_ref,
                text: r.get(3)?,
                sermon_title: title,
                original_title: r.get(5)?,
                sermon_date: date,
                sermon_tradition: r.get(8)?,
            })
        })?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    // ── Livres ──────────────────────────────────────────────────────────────────────────────

    /// Les ouvrages de l'onglet « Livres » qui ont au moins un chapitre.
    pub fn list_books(&self) -> Result<Vec<Book>> {
        if !table_exists(&self.conn, "library_book")? {
            return Ok(Vec::new());
        }
        let mut stmt = self.conn.prepare(
            "SELECT b.key, b.title, b.date_prefix, b.tradition
             FROM library_book b
             WHERE EXISTS (
                 SELECT 1 FROM sermon s
                 WHERE s.date LIKE b.date_prefix || '%' AND s.tradition = b.tradition
             )
             ORDER BY b.sort_order, b.title",
        )?;
        let rows = stmt.query_map([], book_from_row)?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    fn book(&self, key: &str) -> Result<Option<Book>> {
        if !table_exists(&self.conn, "library_book")? {
            return Ok(None);
        }
        Ok(self
            .conn
            .query_row(
                "SELECT key, title, date_prefix, tradition FROM library_book WHERE key = ?",
                [key],
                book_from_row,
            )
            .optional()?)
    }

    /// L'ouvrage d'un chapitre (pour la référence projetée).
    pub fn book_of_chapter(&self, chapter_id: i64) -> Result<Option<Book>> {
        if !table_exists(&self.conn, "library_book")? {
            return Ok(None);
        }
        Ok(self
            .conn
            .query_row(
                "SELECT b.key, b.title, b.date_prefix, b.tradition
                 FROM sermon s
                 JOIN library_book b
                   ON s.date LIKE b.date_prefix || '%' AND s.tradition = b.tradition
                 WHERE s.id = ?
                 ORDER BY length(b.date_prefix) DESC
                 LIMIT 1",
                [chapter_id],
                book_from_row,
            )
            .optional()?)
    }

    /// Les chapitres d'un ouvrage, dans l'ordre du livre.
    pub fn list_book_chapters(&self, key: &str) -> Result<Vec<BookChapter>> {
        if let Some(translator) = expose_translator(key) {
            return self.list_expose_chapters(translator);
        }
        let Some(book) = self.book(key)? else { return Ok(Vec::new()) };
        let mut stmt = self.conn.prepare(&format!(
            "SELECT id, date, title AS original_title, {TITLE} AS title
             FROM sermon
             WHERE date LIKE ? AND tradition = ?
             ORDER BY sort_key, date"
        ))?;
        let rows = stmt.query_map(params![format!("{}%", book.date_prefix), book.tradition], |r| {
            Ok((r.get::<_, i64>(0)?, r.get::<_, Option<String>>(1)?, r.get::<_, String>(2)?, r.get::<_, String>(3)?))
        })?;
        let mut out = Vec::new();
        for (position, row) in rows.enumerate() {
            let (id, date, original_title, title) = row?;
            let chapter = date.as_deref().and_then(chapter_suffix);
            out.push(BookChapter {
                id,
                title,
                original_title,
                chapter_num: chapter.unwrap_or(position as i64 + 1),
                date_code: date,
            });
        }
        Ok(out)
    }

    /// La recherche (par sous-chaîne) dans un ouvrage.
    pub fn search_book(&self, query: &str, key: &str, limit: usize) -> Result<Vec<BookHit>> {
        if let Some(translator) = expose_translator(key) {
            return self.search_expose(query, translator, limit);
        }
        let Some(book) = self.book(key)? else { return Ok(Vec::new()) };
        let mut stmt = self.conn.prepare(&format!(
            "SELECT p.sermon_id, p.paragraph_no, p.ref, p.text, {MARKER} AS marker, {S_TITLE} AS title, s.date
             FROM sermon_paragraph p
             JOIN sermon s ON s.id = p.sermon_id
             WHERE s.date LIKE ? AND s.tradition = ?
               AND unaccent(p.text) LIKE unaccent(?)
             ORDER BY s.sort_key, p.paragraph_no
             LIMIT ?"
        ))?;
        let needle = format!("%{}%", po_text::plain_query(query));
        let rows =
            stmt.query_map(params![format!("{}%", book.date_prefix), book.tradition, needle, limit as i64], |r| {
                let raw_ref: Option<String> = r.get(2)?;
                let marker = opt_str(r, 4)?;
                Ok(BookHit {
                    sermon_id: r.get(0)?,
                    paragraph_no: r.get(1)?,
                    reference: raw_ref.clone().filter(|s| !s.is_empty()).unwrap_or_else(|| marker.clone()),
                    marker,
                    raw_ref,
                    text: r.get(3)?,
                    title: r.get(5)?,
                })
            })?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    // ── Exposé des Sept Âges ────────────────────────────────────────────────────────────────

    /// Les chapitres de l'Exposé d'un traducteur (VGR ou SHP).
    pub fn list_expose_chapters(&self, translator: &str) -> Result<Vec<BookChapter>> {
        let translator = translator.to_uppercase();
        let prefix = if translator == "VGR" { "BK-AGES" } else { "BK-AGES-SHP" };
        let mut stmt = self.conn.prepare(&format!(
            "SELECT id, date, title AS original_title, {TITLE} AS title
             FROM sermon
             WHERE date LIKE ? AND tradition = ?
             ORDER BY date"
        ))?;
        let rows = stmt.query_map(params![format!("{prefix}-%"), translator], |r| {
            let date: Option<String> = r.get(1)?;
            let title = po_text::clean_expose_title(&r.get::<_, String>(3)?);
            let original_title = po_text::clean_expose_title(&r.get::<_, String>(2)?);
            let chapter_num = po_text::expose_chapter_num(date.as_deref().unwrap_or(""), &title, &translator);
            Ok(BookChapter {
                id: r.get(0)?,
                title,
                original_title,
                chapter_num: i64::from(chapter_num),
                date_code: date,
            })
        })?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    /// Les pages d'un chapitre de l'Exposé (celles des références « page-paragraphe », sinon des
    /// pages de 50 paragraphes).
    pub fn list_expose_pages(&self, chapter_id: i64) -> Result<Vec<u32>> {
        let refs = self.paragraph_refs(chapter_id)?;
        if refs.is_empty() {
            return Ok(Vec::new());
        }
        let pages: std::collections::BTreeSet<u32> = refs
            .iter()
            .filter_map(|r| po_text::expose_ref_parts(r.as_deref().unwrap_or("")).map(|(page, _)| page))
            .collect();
        if !pages.is_empty() {
            return Ok(pages.into_iter().collect());
        }
        Ok((1..=refs.len().div_ceil(50) as u32).collect())
    }

    fn paragraph_refs(&self, chapter_id: i64) -> Result<Vec<Option<String>>> {
        let mut stmt =
            self.conn.prepare("SELECT ref FROM sermon_paragraph WHERE sermon_id = ? ORDER BY paragraph_no")?;
        let rows = stmt.query_map([chapter_id], |r| r.get(0))?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    /// Les paragraphes d'une page d'un chapitre de l'Exposé.
    pub fn list_expose_page_paragraphs(&self, chapter_id: i64, page: u32) -> Result<Vec<Paragraph>> {
        let mut stmt = self.conn.prepare(
            "SELECT paragraph_no, ref, text, marker FROM sermon_paragraph WHERE sermon_id = ? ORDER BY paragraph_no",
        )?;
        type Row = (i64, Option<String>, String, Option<String>);
        let rows = stmt
            .query_map([chapter_id], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)))?
            .collect::<rusqlite::Result<Vec<Row>>>()?;
        let parts = |r: &Option<String>| po_text::expose_ref_parts(r.as_deref().unwrap_or(""));
        let has_pages = rows.iter().any(|(_, raw_ref, _, _)| parts(raw_ref).is_some());
        let stored = |m: Option<String>, fallback: String| match m {
            Some(m) if !m.is_empty() => py::strip(&m).to_string(),
            _ => fallback,
        };
        let mut out = Vec::new();
        if has_pages {
            for (paragraph_no, raw_ref, text, marker) in rows {
                let Some((p, para)) = parts(&raw_ref) else { continue };
                if p == page {
                    out.push(Paragraph { paragraph_no, marker: stored(marker, format!("{p}-{para}")), raw_ref, text });
                }
            }
        } else {
            let offset = (page.saturating_sub(1) as usize) * 50;
            for (paragraph_no, raw_ref, text, marker) in rows.into_iter().skip(offset).take(50) {
                out.push(Paragraph {
                    paragraph_no, marker: stored(marker, format!("§{paragraph_no}")), raw_ref, text
                });
            }
        }
        Ok(out)
    }

    /// La recherche (par sous-chaîne) dans l'Exposé d'un traducteur.
    pub fn search_expose(&self, query: &str, translator: &str, limit: usize) -> Result<Vec<BookHit>> {
        let translator = translator.to_uppercase();
        let prefix = if translator == "VGR" { "BK-AGES" } else { "BK-AGES-SHP" };
        let mut stmt = self.conn.prepare(&format!(
            "SELECT p.sermon_id, p.paragraph_no, p.ref, p.text, {MARKER} AS marker, {S_TITLE} AS title, s.date
             FROM sermon_paragraph p
             JOIN sermon s ON s.id = p.sermon_id
             WHERE s.date LIKE ? AND s.tradition = ? AND unaccent(p.text) LIKE unaccent(?)
             ORDER BY s.date, p.paragraph_no
             LIMIT ?"
        ))?;
        let needle = format!("%{}%", py::strip(query));
        let rows = stmt.query_map(params![format!("{prefix}-%"), translator, needle, limit as i64], |r| {
            let paragraph_no: i64 = r.get(1)?;
            let raw_ref: Option<String> = r.get(2)?;
            let marker = py::strip(&opt_str(r, 4)?).to_string();
            let marker = if marker.is_empty() {
                po_text::paragraph_marker(raw_ref.as_deref().unwrap_or(""), paragraph_no)
            } else {
                marker
            };
            let title: String = r.get(5)?;
            let date: Option<String> = r.get(6)?;
            Ok(BookHit {
                sermon_id: r.get(0)?,
                paragraph_no,
                reference: po_text::format_reference(date.as_deref().unwrap_or(""), &title, &marker),
                marker,
                raw_ref,
                text: r.get(3)?,
                title,
            })
        })?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }
}

fn book_from_row(r: &Row<'_>) -> rusqlite::Result<Book> {
    Ok(Book { key: r.get(0)?, title: r.get(1)?, date_prefix: r.get(2)?, tradition: r.get(3)? })
}

/// Les deux Exposés ont leur propre lecture (pages, numéros de chapitres).
fn expose_translator(key: &str) -> Option<&'static str> {
    match key {
        "ages-vgr" => Some("VGR"),
        "ages-shp" => Some("SHP"),
        _ => None,
    }
}

/// Le numéro de chapitre à la fin d'un code (« BK-SENT-CH12 » → 12).
fn chapter_suffix(date: &str) -> Option<i64> {
    let at = date.rfind("-CH")?;
    let digits = &date[at + 3..];
    py::ascii_int(digits).map(i64::from)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::testing;

    fn sample() -> Database {
        let db = testing::empty();
        db.conn
            .execute_batch(
                "INSERT INTO sermon (id, title, date, tradition, language, sort_key, canonical_title, title_search, location)
                 VALUES (1, 'LA FOI EST UNE FERME ASSURANCE', '47-0412', 'VGR', 'fr', '47-0412',
                         'La Foi Est une Ferme Assurance', 'la foi est une ferme assurance', 'OAKLAND CA'),
                        (2, 'Chapitre 1', 'BK-AGES-CH01', 'VGR', 'fr', '', '', 'chapitre 1', ''),
                        (3, 'CHAPITRE 2 L''âge d''Éphèse', 'BK-AGES-CH02', 'VGR', 'fr', '', '', '', '');
                 INSERT INTO sermon_paragraph (id, sermon_id, paragraph_no, ref, text, marker) VALUES
                        (10, 1, 1, '', 'Ô Éternel, la foi est une ferme assurance.', '¶1'),
                        (11, 1, 2, 'La Foi ¶2', 'Il était là, déjà.', ''),
                        (20, 2, 1, 'BK 12-1', 'La foi dans le livre.', ''),
                        (21, 2, 2, 'BK 13-1', 'Une autre page.', ''),
                        (30, 3, 1, 'BK 40-1', 'Éphèse.', '');
                 CREATE VIRTUAL TABLE sermon_paragraph_fts USING fts5(text, ref, sermon_title, canonical_title,
                     content='', detail=full, tokenize='unicode61 remove_diacritics 2');
                 INSERT INTO sermon_paragraph_fts (rowid, text) VALUES (10, 'Ô Éternel, la foi est une ferme assurance.'),
                        (11, 'Il était là, déjà.'), (20, 'La foi dans le livre.');",
            )
            .unwrap();
        db
    }

    fn search<'a>(query: &'a str, translator: Option<&'a str>, fallback: bool) -> ParagraphSearch<'a> {
        ParagraphSearch { query, language: Some("fr"), translator, limit: 100, substring_fallback: fallback }
    }

    #[test]
    fn lists_sermons_but_not_books() {
        let db = sample();
        let sermons = db.list_sermons(&SermonFilter::default()).unwrap();
        assert_eq!(sermons.len(), 1);
        assert_eq!(sermons[0].title, "La Foi Est une Ferme Assurance");
        assert_eq!(db.list_sermons(&SermonFilter { title: Some("fermé"), ..Default::default() }).unwrap().len(), 1);
        assert_eq!(
            db.list_sermons(&SermonFilter { location: Some("oakland"), ..Default::default() }).unwrap().len(),
            1
        );
        let from_1950 = SermonFilter { date_from: Some("1950-01-01"), ..Default::default() };
        assert!(db.list_sermons(&from_1950).unwrap().is_empty());
        assert_eq!(db.list_sermon_years(None, Some("fr"), None).unwrap(), [1947]);
        assert_eq!(db.list_translators("fr").unwrap(), ["VGR"]);
    }

    #[test]
    fn full_text_search_ignores_accents() {
        let db = sample();
        let hits = db.search_paragraphs(&search("eternel", None, true)).unwrap();
        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].reference, "47-0412 - La Foi Est une Ferme Assurance - ¶1");
    }

    #[test]
    fn substring_fallback_and_marker() {
        let db = sample();
        // « ait là, d » n'est pas un début de mot : seule la sous-chaîne le trouve. Le repère vient
        // alors de la référence brute, comme en 2.8.
        let hits = db.search_paragraphs(&search("ait la, d", Some("vgr"), true)).unwrap();
        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].marker, "La Foi ¶2");
        assert!(db.search_paragraphs(&search("ait la, d", None, false)).unwrap().is_empty());
    }

    #[test]
    fn expose_chapters_and_pages() {
        let db = sample();
        let chapters = db.list_book_chapters("ages-vgr").unwrap();
        assert_eq!(chapters.iter().map(|c| c.chapter_num).collect::<Vec<_>>(), [1, 2]);
        assert_eq!(chapters[1].title, "L'âge d'Éphèse");
        assert_eq!(db.list_expose_pages(2).unwrap(), [12, 13]);
        let page = db.list_expose_page_paragraphs(2, 13).unwrap();
        assert_eq!((page.len(), page[0].marker.as_str()), (1, "13-1"));
        // Sans repère en base, la 2.8 prend la référence brute (« BK 40-1 ») comme repère.
        assert_eq!(
            db.search_book("ephese", "ages-vgr", 10).unwrap()[0].reference,
            "BK-AGES-CH02 - CHAPITRE 2 L'âge d'Éphèse - BK 40-1"
        );
        assert_eq!(db.list_books().unwrap().len(), 1);
        assert_eq!(db.book_of_chapter(3).unwrap().unwrap().key, "ages-vgr");
        assert_eq!(db.paragraphs(1).unwrap()[1].marker, "¶2");
    }
}
