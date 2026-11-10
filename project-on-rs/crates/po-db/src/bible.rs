//! Les Bibles (`app/database/dao_bible.py`) : les traductions installées et, pour les très
//! anciennes bases, la Bible de démonstration (`bible_book` / `bible_verse`).

use rusqlite::params;
use serde::Serialize;

use crate::{Database, Result};

/// Une traduction installée.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Translation {
    pub id: i64,
    pub module: String,
    pub name: Option<String>,
    pub shortname: Option<String>,
    pub lang: Option<String>,
}

/// Un livre d'une traduction (son nom vient de ses versets).
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct TranslationBook {
    pub id: i64,
    pub name: String,
}

/// Un verset.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Verse {
    pub verse: i64,
    pub text: String,
}

/// Un livre de la Bible de démonstration.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct LegacyBook {
    pub id: i64,
    pub name: String,
    pub abbreviation: Option<String>,
    pub testament: Option<String>,
    pub sort_order: Option<i64>,
}

impl Database {
    /// Les traductions, par nom court.
    pub fn list_translations(&self) -> Result<Vec<Translation>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, module, name, shortname, lang FROM bible_translation ORDER BY COALESCE(shortname, name, module)",
        )?;
        let rows = stmt.query_map([], |r| {
            Ok(Translation { id: r.get(0)?, module: r.get(1)?, name: r.get(2)?, shortname: r.get(3)?, lang: r.get(4)? })
        })?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    /// Les livres d'une traduction, dans l'ordre canonique. Un livre sans nom porte son numéro.
    pub fn list_translation_books(&self, translation_id: i64) -> Result<Vec<TranslationBook>> {
        // Un verset par livre (le nom est le même pour tout le livre).
        let mut stmt = self.conn.prepare_cached(
            "SELECT b.book AS id,
                    (SELECT COALESCE(v.book_name, '')
                       FROM bible_translation_verse v
                      WHERE v.translation_id = ? AND v.book = b.book
                      LIMIT 1) AS name
             FROM (SELECT DISTINCT book FROM bible_translation_verse
                   WHERE translation_id = ?) b
             ORDER BY b.book",
        )?;
        let rows = stmt.query_map(params![translation_id, translation_id], |r| {
            let id: i64 = r.get(0)?;
            let name = po_text::py::strip(&r.get::<_, Option<String>>(1)?.unwrap_or_default()).to_string();
            Ok(TranslationBook { id, name: if name.is_empty() { id.to_string() } else { name } })
        })?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    pub fn list_translation_chapters(&self, translation_id: i64, book: i64) -> Result<Vec<i64>> {
        let mut stmt = self.conn.prepare_cached(
            "SELECT DISTINCT chapter FROM bible_translation_verse WHERE translation_id = ? AND book = ? ORDER BY chapter",
        )?;
        let rows = stmt.query_map(params![translation_id, book], |r| r.get(0))?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    pub fn list_translation_verses(&self, translation_id: i64, book: i64, chapter: i64) -> Result<Vec<Verse>> {
        let mut stmt = self.conn.prepare_cached(
            "SELECT verse, text FROM bible_translation_verse
             WHERE translation_id = ? AND book = ? AND chapter = ? ORDER BY verse",
        )?;
        let rows = stmt
            .query_map(params![translation_id, book, chapter], |r| Ok(Verse { verse: r.get(0)?, text: r.get(1)? }))?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    /// Les livres de la Bible de démonstration.
    pub fn list_legacy_books(&self) -> Result<Vec<LegacyBook>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, name, abbreviation, testament, sort_order FROM bible_book ORDER BY COALESCE(sort_order, 999999), name",
        )?;
        let rows = stmt.query_map([], |r| {
            Ok(LegacyBook {
                id: r.get(0)?,
                name: r.get(1)?,
                abbreviation: r.get(2)?,
                testament: r.get(3)?,
                sort_order: r.get(4)?,
            })
        })?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    pub fn list_legacy_chapters(&self, book_id: i64) -> Result<Vec<i64>> {
        let mut stmt =
            self.conn.prepare("SELECT DISTINCT chapter FROM bible_verse WHERE book_id = ? ORDER BY chapter")?;
        let rows = stmt.query_map([book_id], |r| r.get(0))?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    pub fn list_legacy_verses(&self, book_id: i64, chapter: i64) -> Result<Vec<Verse>> {
        let mut stmt = self
            .conn
            .prepare("SELECT verse, text FROM bible_verse WHERE book_id = ? AND chapter = ? ORDER BY verse")?;
        let rows = stmt.query_map(params![book_id, chapter], |r| Ok(Verse { verse: r.get(0)?, text: r.get(1)? }))?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }
}

#[cfg(test)]
mod tests {
    use crate::testing;

    #[test]
    fn translations_books_and_verses() {
        let db = testing::empty();
        db.conn
            .execute_batch(
                "INSERT INTO bible_translation (id, module, name, shortname, lang) VALUES (1, 'lsg', 'Louis Segond', 'LSG', 'fr');
                 INSERT INTO bible_translation_verse (translation_id, book, book_name, chapter, verse, text) VALUES
                    (1, 43, ' Jean ', 3, 16, 'Car Dieu a tant aimé le monde'), (1, 43, 'Jean', 3, 17, 'Dieu, en effet'),
                    (1, 44, NULL, 1, 1, 'Théophile');",
            )
            .unwrap();
        assert_eq!(db.list_translations().unwrap()[0].shortname.as_deref(), Some("LSG"));
        let books = db.list_translation_books(1).unwrap();
        assert_eq!(books.iter().map(|b| b.name.as_str()).collect::<Vec<_>>(), ["Jean", "44"]);
        assert_eq!(db.list_translation_chapters(1, 43).unwrap(), [3]);
        assert_eq!(db.list_translation_verses(1, 43, 3).unwrap()[1].verse, 17);
        assert!(db.list_legacy_books().unwrap().is_empty());
    }
}
