//! La bibliothèque des médias projetables (`app/database/dao_media.py`).

use rusqlite::{OptionalExtension, Row, params};
use serde::Serialize;

use crate::{Database, Result};

/// Un média (image, vidéo, diapositive).
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct MediaItem {
    pub id: i64,
    pub name: String,
    pub path: String,
    /// image, video…
    pub kind: String,
    pub sort_order: Option<i64>,
    pub created_at: Option<String>,
    /// Une vidéo qui tourne en boucle (0 ou 1).
    #[serde(rename = "loop")]
    pub looped: i64,
    /// La durée d'affichage en diaporama (0 = avance manuelle).
    pub duration_seconds: i64,
}

fn media_from_row(r: &Row<'_>) -> rusqlite::Result<MediaItem> {
    Ok(MediaItem {
        id: r.get(0)?,
        name: r.get(1)?,
        path: r.get(2)?,
        kind: r.get(3)?,
        sort_order: r.get(4)?,
        created_at: r.get(5)?,
        looped: r.get(6)?,
        duration_seconds: r.get(7)?,
    })
}

const COLUMNS: &str = "id, name, path, kind, sort_order, created_at, COALESCE(loop, 0) AS loop, COALESCE(duration_seconds, 0) AS duration_seconds";

impl Database {
    pub fn list_media(&self) -> Result<Vec<MediaItem>> {
        let mut stmt = self.conn.prepare(&format!("SELECT {COLUMNS} FROM media_item ORDER BY sort_order, id"))?;
        let rows = stmt.query_map([], media_from_row)?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    pub fn media(&self, media_id: i64) -> Result<Option<MediaItem>> {
        Ok(self
            .conn
            .query_row(&format!("SELECT {COLUMNS} FROM media_item WHERE id = ?"), [media_id], media_from_row)
            .optional()?)
    }

    pub fn set_media_loop(&self, media_id: i64, looped: bool) -> Result<bool> {
        Ok(self.conn.execute("UPDATE media_item SET loop = ? WHERE id = ?", params![i64::from(looped), media_id])? > 0)
    }

    /// La durée d'affichage en diaporama, bornée à 0..3600 s.
    pub fn set_media_duration(&self, media_id: i64, seconds: i64) -> Result<bool> {
        Ok(self.conn.execute(
            "UPDATE media_item SET duration_seconds = ? WHERE id = ?",
            params![seconds.clamp(0, 3600), media_id],
        )? > 0)
    }

    /// Ajoute un média à la fin ; un chemin déjà connu rend l'identifiant existant.
    pub fn add_media(&mut self, name: &str, path: &str, kind: &str) -> Result<i64> {
        let tx = self.conn.transaction()?;
        if let Some(id) = tx.query_row("SELECT id FROM media_item WHERE path = ?", [path], |r| r.get(0)).optional()? {
            return Ok(id);
        }
        let last: i64 = tx.query_row("SELECT COALESCE(MAX(sort_order), 0) FROM media_item", [], |r| r.get(0))?;
        tx.execute(
            "INSERT INTO media_item (name, path, kind, sort_order) VALUES (?, ?, ?, ?)",
            params![name, path, kind, last + 1],
        )?;
        let id = tx.last_insert_rowid();
        tx.commit()?;
        Ok(id)
    }

    pub fn rename_media(&self, media_id: i64, name: &str) -> Result<bool> {
        Ok(self.conn.execute("UPDATE media_item SET name = ? WHERE id = ?", params![name, media_id])? > 0)
    }

    pub fn delete_media(&self, media_id: i64) -> Result<bool> {
        Ok(self.conn.execute("DELETE FROM media_item WHERE id = ?", [media_id])? > 0)
    }

    /// Retire les anciennes pages web (plus projetables depuis la 2.x) ; rend leur nombre.
    pub fn purge_web_media(&self) -> Result<usize> {
        Ok(self.conn.execute("DELETE FROM media_item WHERE kind = 'web'", [])?)
    }
}

#[cfg(test)]
mod tests {
    use crate::testing;

    #[test]
    fn media_library() {
        let mut db = testing::empty();
        let id = db.add_media("Fond", r"C:\m\fond.png", "image").unwrap();
        assert_eq!(db.add_media("Autre nom", r"C:\m\fond.png", "image").unwrap(), id);
        db.add_media("Site", "https://exemple", "web").unwrap();
        assert!(db.set_media_loop(id, true).unwrap());
        assert!(db.set_media_duration(id, 99_999).unwrap());
        let media = db.media(id).unwrap().unwrap();
        assert_eq!((media.looped, media.duration_seconds), (1, 3600));
        assert_eq!(db.purge_web_media().unwrap(), 1);
        assert!(db.rename_media(id, "Fond bleu").unwrap());
        assert_eq!(db.list_media().unwrap()[0].name, "Fond bleu");
        assert!(db.delete_media(id).unwrap());
    }
}
