//! Le déroulé du culte (`app/database/dao_service_plan.py`) : l'heure de début d'une playlist et ses
//! sections (nom, durée, premier élément).

use rusqlite::{OptionalExtension, TransactionBehavior, params};
use serde::Serialize;

use crate::{Database, Result};

/// Une section du déroulé.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Section {
    pub id: i64,
    pub folder_id: i64,
    pub name: String,
    pub duration_min: i64,
    /// Le premier élément de la playlist qui appartient à la section.
    pub item_id: Option<i64>,
    pub sort_order: Option<i64>,
}

impl Database {
    pub fn start_time(&self, folder_id: i64) -> Result<String> {
        Ok(self
            .conn
            .query_row("SELECT COALESCE(start_time, '') FROM playlist_folder WHERE id = ?", [folder_id], |r| r.get(0))
            .optional()?
            .unwrap_or_default())
    }

    pub fn set_start_time(&self, folder_id: i64, start_time: &str) -> Result<()> {
        self.conn.execute("UPDATE playlist_folder SET start_time = ? WHERE id = ?", params![start_time, folder_id])?;
        Ok(())
    }

    pub fn list_sections(&self, folder_id: i64) -> Result<Vec<Section>> {
        let mut stmt = self.conn.prepare_cached(
            "SELECT id, folder_id, name, duration_min, item_id, sort_order
             FROM service_section WHERE folder_id = ? ORDER BY sort_order, id",
        )?;
        let rows = stmt.query_map([folder_id], |r| {
            Ok(Section {
                id: r.get(0)?,
                folder_id: r.get(1)?,
                name: r.get(2)?,
                duration_min: r.get(3)?,
                item_id: r.get(4)?,
                sort_order: r.get(5)?,
            })
        })?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    /// Ajoute une section à la fin ; une durée négative compte pour zéro.
    pub fn add_section(&mut self, folder_id: i64, name: &str, duration_min: i64, item_id: Option<i64>) -> Result<i64> {
        let tx = self.conn.transaction()?;
        let last: i64 = tx.query_row(
            "SELECT COALESCE(MAX(sort_order), 0) FROM service_section WHERE folder_id = ?",
            [folder_id],
            |r| r.get(0),
        )?;
        tx.execute(
            "INSERT INTO service_section (folder_id, name, duration_min, item_id, sort_order) VALUES (?, ?, ?, ?, ?)",
            params![folder_id, name, duration_min.max(0), item_id, last + 1],
        )?;
        let id = tx.last_insert_rowid();
        tx.commit()?;
        Ok(id)
    }

    pub fn update_section(&self, section_id: i64, name: &str, duration_min: i64, item_id: Option<i64>) -> Result<()> {
        self.conn.execute(
            "UPDATE service_section SET name = ?, duration_min = ?, item_id = ? WHERE id = ?",
            params![name, duration_min.max(0), item_id, section_id],
        )?;
        Ok(())
    }

    pub fn delete_section(&self, section_id: i64) -> Result<()> {
        self.conn.execute("DELETE FROM service_section WHERE id = ?", [section_id])?;
        Ok(())
    }

    /// Monte ou descend une section de `delta` places.
    pub fn move_section(&mut self, section_id: i64, delta: i64) -> Result<bool> {
        let tx = self.conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let Some(folder_id) = tx
            .query_row("SELECT folder_id FROM service_section WHERE id = ?", [section_id], |r| r.get::<_, i64>(0))
            .optional()?
        else {
            return Ok(false);
        };
        let mut ids: Vec<i64> = {
            let mut stmt = tx.prepare("SELECT id FROM service_section WHERE folder_id = ? ORDER BY sort_order, id")?;
            stmt.query_map([folder_id], |r| r.get(0))?.collect::<rusqlite::Result<_>>()?
        };
        let Some(index) = ids.iter().position(|&id| id == section_id) else { return Ok(false) };
        let target = index as i64 + delta;
        if target < 0 || target >= ids.len() as i64 {
            return Ok(false);
        }
        let moved = ids.remove(index);
        ids.insert(target as usize, moved);
        for (order, id) in ids.iter().enumerate() {
            tx.execute("UPDATE service_section SET sort_order = ? WHERE id = ?", params![order as i64 + 1, id])?;
        }
        tx.commit()?;
        Ok(true)
    }
}

#[cfg(test)]
mod tests {
    use crate::testing;

    #[test]
    fn sections_follow_their_playlist() {
        let mut db = testing::empty();
        let folder = db.create_folder("Culte").unwrap();
        db.set_start_time(folder, "09:30").unwrap();
        assert_eq!(db.start_time(folder).unwrap(), "09:30");
        assert_eq!(db.start_time(999).unwrap(), "");
        let a = db.add_section(folder, "Louange", 20, None).unwrap();
        let b = db.add_section(folder, "Prédication", -5, None).unwrap();
        assert_eq!(db.list_sections(folder).unwrap()[1].duration_min, 0);
        assert!(db.move_section(b, -1).unwrap());
        assert_eq!(db.list_sections(folder).unwrap().iter().map(|s| s.id).collect::<Vec<_>>(), [b, a]);
        assert!(!db.move_section(b, -1).unwrap());
        db.update_section(a, "Louange et adoration", 25, Some(3)).unwrap();
        db.delete_section(b).unwrap();
        let sections = db.list_sections(folder).unwrap();
        assert_eq!((sections.len(), sections[0].item_id), (1, Some(3)));
        db.delete_folder(folder).unwrap();
        assert!(db.list_sections(folder).unwrap().is_empty());
    }
}
