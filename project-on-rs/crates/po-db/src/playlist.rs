//! Les playlists (`app/database/dao_playlist.py`) : dossiers, éléments, réorganisation, copie,
//! déplacement, et l'instantané qui permet d'annuler (Ctrl+Z) à l'identique.

use rusqlite::{Connection, OptionalExtension, Row, TransactionBehavior, params};
use serde::Serialize;

use crate::{Database, Result};

/// Une playlist.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Folder {
    pub id: i64,
    pub name: String,
    pub sort_order: Option<i64>,
    pub created_at: Option<String>,
}

/// Un élément d'une playlist.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct PlaylistItem {
    pub id: i64,
    pub folder_id: Option<i64>,
    /// bible, hymn, sermon, custom, media…
    pub source: String,
    pub reference: String,
    pub text: String,
    pub sort_order: Option<i64>,
    pub background: String,
}

/// Un élément tel qu'il est en base, pour l'annulation exacte (identifiants et dates compris).
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct ItemSnapshot {
    pub id: i64,
    pub folder_id: Option<i64>,
    pub source: String,
    pub reference: String,
    pub text: String,
    pub sort_order: Option<i64>,
    pub background: Option<String>,
    pub created_at: Option<String>,
}

/// Un élément à ajouter (import d'une playlist transférée).
#[derive(Debug, Clone, PartialEq)]
pub struct NewItem {
    pub source: String,
    pub reference: String,
    pub text: String,
    pub background: String,
}

/// Un dossier et ses copies : (original, copie).
type FolderCopies = (Option<i64>, Vec<(i64, i64)>);

const ITEM_COLUMNS: &str = "id, folder_id, source, reference, text, sort_order, COALESCE(background, '') AS background";
const SNAPSHOT_COLUMNS: &str = "id, folder_id, source, reference, text, sort_order, background, created_at";

fn folder_from_row(r: &Row<'_>) -> rusqlite::Result<Folder> {
    Ok(Folder { id: r.get(0)?, name: r.get(1)?, sort_order: r.get(2)?, created_at: r.get(3)? })
}

fn item_from_row(r: &Row<'_>) -> rusqlite::Result<PlaylistItem> {
    Ok(PlaylistItem {
        id: r.get(0)?,
        folder_id: r.get(1)?,
        source: r.get(2)?,
        reference: r.get(3)?,
        text: r.get(4)?,
        sort_order: r.get(5)?,
        background: r.get(6)?,
    })
}

fn snapshot_from_row(r: &Row<'_>) -> rusqlite::Result<ItemSnapshot> {
    Ok(ItemSnapshot {
        id: r.get(0)?,
        folder_id: r.get(1)?,
        source: r.get(2)?,
        reference: r.get(3)?,
        text: r.get(4)?,
        sort_order: r.get(5)?,
        background: r.get(6)?,
        created_at: r.get(7)?,
    })
}

/// Le plus grand rang d'un dossier (ou de la racine, `None`).
fn max_order(conn: &Connection, folder_id: Option<i64>) -> rusqlite::Result<i64> {
    conn.query_row("SELECT COALESCE(MAX(sort_order), 0) FROM playlist_item WHERE folder_id IS ?", [folder_id], |r| {
        r.get(0)
    })
}

fn ordered_ids(conn: &Connection, folder_id: Option<i64>) -> rusqlite::Result<Vec<i64>> {
    let mut stmt = conn.prepare("SELECT id FROM playlist_item WHERE folder_id IS ? ORDER BY sort_order, id")?;
    let rows = stmt.query_map([folder_id], |r| r.get(0))?;
    rows.collect()
}

/// Les rangs 1, 2, 3… dans l'ordre donné (les égalités d'anciens imports disparaissent).
fn renumber(conn: &Connection, ids: &[i64]) -> rusqlite::Result<()> {
    let mut stmt = conn.prepare("UPDATE playlist_item SET sort_order = ? WHERE id = ?")?;
    for (rank, id) in ids.iter().enumerate() {
        stmt.execute(params![rank as i64 + 1, id])?;
    }
    Ok(())
}

/// Les éléments donnés, dans leur ordre d'affichage.
fn rows_in_order(conn: &Connection, ids: &[i64]) -> rusqlite::Result<Vec<ItemSnapshot>> {
    if ids.is_empty() {
        return Ok(Vec::new());
    }
    let marks = vec!["?"; ids.len()].join(",");
    let mut stmt = conn.prepare(&format!(
        "SELECT {SNAPSHOT_COLUMNS} FROM playlist_item WHERE id IN ({marks}) ORDER BY folder_id, sort_order, id"
    ))?;
    let rows = stmt.query_map(rusqlite::params_from_iter(ids), snapshot_from_row)?;
    rows.collect()
}

impl Database {
    pub fn list_folders(&self) -> Result<Vec<Folder>> {
        let mut stmt = self
            .conn
            .prepare("SELECT id, name, sort_order, created_at FROM playlist_folder ORDER BY sort_order, id")?;
        let rows = stmt.query_map([], folder_from_row)?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    pub fn folder(&self, folder_id: i64) -> Result<Option<Folder>> {
        Ok(self
            .conn
            .query_row(
                "SELECT id, name, sort_order, created_at FROM playlist_folder WHERE id = ?",
                [folder_id],
                folder_from_row,
            )
            .optional()?)
    }

    /// Crée une playlist à la fin ; rend son identifiant.
    pub fn create_folder(&mut self, name: &str) -> Result<i64> {
        let tx = self.conn.transaction()?;
        let last: i64 = tx.query_row("SELECT COALESCE(MAX(sort_order), 0) FROM playlist_folder", [], |r| r.get(0))?;
        tx.execute("INSERT INTO playlist_folder (name, sort_order) VALUES (?, ?)", params![name, last + 1])?;
        let id = tx.last_insert_rowid();
        tx.commit()?;
        Ok(id)
    }

    pub fn rename_folder(&self, folder_id: i64, name: &str) -> Result<bool> {
        Ok(self.conn.execute("UPDATE playlist_folder SET name = ? WHERE id = ?", params![name, folder_id])? > 0)
    }

    /// Supprime une playlist (ses éléments et ses sections partent avec elle).
    pub fn delete_folder(&self, folder_id: i64) -> Result<bool> {
        Ok(self.conn.execute("DELETE FROM playlist_folder WHERE id = ?", [folder_id])? > 0)
    }

    /// Les éléments d'une playlist, ou ceux de la racine (`None`).
    pub fn list_items(&self, folder_id: Option<i64>) -> Result<Vec<PlaylistItem>> {
        let mut stmt = self.conn.prepare_cached(&format!(
            "SELECT {ITEM_COLUMNS} FROM playlist_item WHERE folder_id IS ? ORDER BY sort_order, id"
        ))?;
        let rows = stmt.query_map([folder_id], item_from_row)?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    pub fn list_all_items(&self) -> Result<Vec<PlaylistItem>> {
        let mut stmt = self.conn.prepare(&format!(
            "SELECT {ITEM_COLUMNS} FROM playlist_item ORDER BY folder_id NULLS FIRST, sort_order, id"
        ))?;
        let rows = stmt.query_map([], item_from_row)?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    /// Ajoute un élément à la fin d'une playlist ; rend son identifiant.
    pub fn add_item(
        &mut self,
        source: &str,
        reference: &str,
        text: &str,
        folder_id: Option<i64>,
        background: &str,
    ) -> Result<i64> {
        let tx = self.conn.transaction()?;
        let last = max_order(&tx, folder_id)?;
        tx.execute(
            "INSERT INTO playlist_item (folder_id, source, reference, text, sort_order, background) VALUES (?, ?, ?, ?, ?, ?)",
            params![folder_id, source, reference, text, last + 1, background],
        )?;
        let id = tx.last_insert_rowid();
        tx.commit()?;
        Ok(id)
    }

    /// Ajoute plusieurs éléments (source, référence, texte) en une fois ; rend leurs identifiants.
    pub fn add_items(&mut self, items: &[(String, String, String)], folder_id: Option<i64>) -> Result<Vec<i64>> {
        if items.is_empty() {
            return Ok(Vec::new());
        }
        let tx = self.conn.transaction()?;
        let last = max_order(&tx, folder_id)?;
        let mut ids = Vec::with_capacity(items.len());
        for (offset, (source, reference, text)) in items.iter().enumerate() {
            tx.execute(
                "INSERT INTO playlist_item (folder_id, source, reference, text, sort_order) VALUES (?, ?, ?, ?, ?)",
                params![folder_id, source, reference, text, last + offset as i64 + 1],
            )?;
            ids.push(tx.last_insert_rowid());
        }
        tx.commit()?;
        Ok(ids)
    }

    /// Monte ou descend un élément de `delta` places ; renumérote le dossier.
    pub fn move_item(&mut self, item_id: i64, delta: i64, folder_id: Option<i64>) -> Result<bool> {
        let tx = self.conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let mut ids = ordered_ids(&tx, folder_id)?;
        let Some(index) = ids.iter().position(|&id| id == item_id) else { return Ok(false) };
        let target = index as i64 + delta;
        if target < 0 || target >= ids.len() as i64 {
            return Ok(false);
        }
        ids.swap(index, target as usize);
        renumber(&tx, &ids)?;
        tx.commit()?;
        Ok(true)
    }

    /// Importe une playlist transférée (dossier et éléments) d'un seul coup.
    pub fn import_folder(&mut self, name: &str, items: &[NewItem]) -> Result<i64> {
        let tx = self.conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let order: i64 =
            tx.query_row("SELECT COALESCE(MAX(sort_order), 0)+1 FROM playlist_folder", [], |r| r.get(0))?;
        tx.execute("INSERT INTO playlist_folder(name, sort_order) VALUES (?, ?)", params![name, order])?;
        let folder_id = tx.last_insert_rowid();
        for (rank, item) in items.iter().enumerate() {
            tx.execute(
                "INSERT INTO playlist_item(folder_id, source, reference, text, background, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                params![folder_id, item.source, item.reference, item.text, item.background, rank as i64 + 1],
            )?;
        }
        tx.commit()?;
        Ok(folder_id)
    }

    pub fn update_item_background(&self, item_id: i64, background: &str) -> Result<bool> {
        Ok(self.conn.execute("UPDATE playlist_item SET background = ? WHERE id = ?", params![background, item_id])? > 0)
    }

    pub fn delete_item(&self, item_id: i64) -> Result<bool> {
        Ok(self.conn.execute("DELETE FROM playlist_item WHERE id = ?", [item_id])? > 0)
    }

    pub fn update_item_sort_order(&self, item_id: i64, sort_order: i64, folder_id: Option<i64>) -> Result<bool> {
        Ok(self.conn.execute(
            "UPDATE playlist_item SET sort_order = ?, folder_id = ? WHERE id = ?",
            params![sort_order, folder_id, item_id],
        )? > 0)
    }

    pub fn update_item(&self, item_id: i64, reference: &str, text: &str) -> Result<bool> {
        Ok(self.conn.execute(
            "UPDATE playlist_item SET reference = ?, text = ? WHERE id = ?",
            params![reference, text, item_id],
        )? > 0)
    }

    /// Applique l'ordre donné (glisser-déposer). Refuse un ordre qui ne contient pas exactement les
    /// éléments du dossier.
    pub fn reorder_items(&mut self, folder_id: i64, ordered: &[i64]) -> Result<bool> {
        let tx = self.conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let mut current = ordered_ids(&tx, Some(folder_id))?;
        let mut wanted = ordered.to_vec();
        current.sort_unstable();
        wanted.sort_unstable();
        if current != wanted {
            return Ok(false);
        }
        renumber(&tx, ordered)?;
        tx.commit()?;
        Ok(true)
    }

    /// Supprime plusieurs éléments ; rend le nombre supprimé.
    pub fn delete_items(&mut self, item_ids: &[i64]) -> Result<usize> {
        let tx = self.conn.transaction()?;
        let mut deleted = 0;
        for id in item_ids {
            deleted += tx.execute("DELETE FROM playlist_item WHERE id = ?", [id])?;
        }
        tx.commit()?;
        Ok(deleted)
    }

    /// Copie chaque élément juste après l'original ; rend les copies.
    pub fn duplicate_items(&mut self, item_ids: &[i64]) -> Result<Vec<i64>> {
        let mut wanted = item_ids.to_vec();
        wanted.sort_unstable();
        wanted.dedup();
        let tx = self.conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let rows = if wanted.is_empty() {
            Vec::new()
        } else {
            let marks = vec!["?"; wanted.len()].join(",");
            let mut stmt =
                tx.prepare(&format!("SELECT {SNAPSHOT_COLUMNS} FROM playlist_item WHERE id IN ({marks}) ORDER BY id"))?;
            let rows = stmt.query_map(rusqlite::params_from_iter(&wanted), snapshot_from_row)?;
            rows.collect::<rusqlite::Result<Vec<_>>>()?
        };
        let mut copies = Vec::new();
        // (dossier, [(original, copie)]) dans l'ordre où les dossiers apparaissent.
        let mut by_folder: Vec<FolderCopies> = Vec::new();
        for row in &rows {
            tx.execute(
                "INSERT INTO playlist_item (folder_id, source, reference, text, sort_order, background) VALUES (?, ?, ?, ?, ?, ?)",
                params![row.folder_id, row.source, row.reference, row.text, row.sort_order, row.background.as_deref().unwrap_or("")],
            )?;
            let copy = tx.last_insert_rowid();
            copies.push(copy);
            match by_folder.iter_mut().find(|(f, _)| *f == row.folder_id) {
                Some((_, pairs)) => pairs.push((row.id, copy)),
                None => by_folder.push((row.folder_id, vec![(row.id, copy)])),
            }
        }
        for (folder_id, pairs) in &by_folder {
            let is_copy = |id: i64| pairs.iter().any(|(_, c)| *c == id);
            let mut placed = Vec::new();
            for id in ordered_ids(&tx, *folder_id)?.into_iter().filter(|&id| !is_copy(id)) {
                placed.push(id);
                if let Some((_, copy)) = pairs.iter().find(|(original, _)| *original == id) {
                    placed.push(*copy);
                }
            }
            renumber(&tx, &placed)?;
        }
        tx.commit()?;
        Ok(copies)
    }

    /// Copie les éléments (dans leur ordre) à la fin d'une autre playlist ; rend les copies.
    pub fn copy_items(&mut self, item_ids: &[i64], folder_id: i64) -> Result<Vec<i64>> {
        let tx = self.conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let rows = rows_in_order(&tx, item_ids)?;
        let start = max_order(&tx, Some(folder_id))?;
        let mut copies = Vec::with_capacity(rows.len());
        for (rank, row) in rows.iter().enumerate() {
            tx.execute(
                "INSERT INTO playlist_item (folder_id, source, reference, text, sort_order, background) VALUES (?, ?, ?, ?, ?, ?)",
                params![folder_id, row.source, row.reference, row.text, start + rank as i64 + 1, row.background.as_deref().unwrap_or("")],
            )?;
            copies.push(tx.last_insert_rowid());
        }
        tx.commit()?;
        Ok(copies)
    }

    /// Déplace les éléments (dans leur ordre) à la fin d'une autre playlist ; rend leur nombre.
    pub fn move_items_to_folder(&mut self, item_ids: &[i64], folder_id: i64) -> Result<usize> {
        let tx = self.conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let rows = rows_in_order(&tx, item_ids)?;
        let start = max_order(&tx, Some(folder_id))?;
        for (rank, row) in rows.iter().enumerate() {
            tx.execute(
                "UPDATE playlist_item SET folder_id = ?, sort_order = ? WHERE id = ?",
                params![folder_id, start + rank as i64 + 1, row.id],
            )?;
        }
        tx.commit()?;
        Ok(rows.len())
    }

    /// Le contenu complet (identifiants compris) des playlists données, pour pouvoir annuler.
    pub fn snapshot_folders(&self, folder_ids: &[i64]) -> Result<Vec<(i64, Vec<ItemSnapshot>)>> {
        let mut stmt = self.conn.prepare(&format!(
            "SELECT {SNAPSHOT_COLUMNS} FROM playlist_item WHERE folder_id = ? ORDER BY sort_order, id"
        ))?;
        let mut out = Vec::with_capacity(folder_ids.len());
        for &folder_id in folder_ids {
            let rows = stmt.query_map([folder_id], snapshot_from_row)?.collect::<rusqlite::Result<Vec<_>>>()?;
            out.push((folder_id, rows));
        }
        Ok(out)
    }

    /// Remet les playlists exactement dans l'état de l'instantané, avec les mêmes identifiants (le
    /// déroulé du culte s'y réfère). Refuse si une des playlists a été supprimée entre-temps.
    pub fn restore_folders(&mut self, snapshot: &[(i64, Vec<ItemSnapshot>)]) -> Result<bool> {
        let tx = self.conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
        for (folder_id, _) in snapshot {
            let exists =
                tx.query_row("SELECT 1 FROM playlist_folder WHERE id = ?", [folder_id], |_| Ok(())).optional()?;
            if exists.is_none() {
                return Ok(false); // la transaction est annulée en sortant
            }
        }
        for (folder_id, rows) in snapshot {
            tx.execute("DELETE FROM playlist_item WHERE folder_id = ?", [folder_id])?;
            for r in rows {
                tx.execute(
                    "INSERT OR REPLACE INTO playlist_item (id, folder_id, source, reference, text, sort_order, background, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    params![
                        r.id,
                        folder_id,
                        r.source,
                        r.reference,
                        r.text,
                        r.sort_order,
                        r.background.as_deref().unwrap_or(""),
                        r.created_at
                    ],
                )?;
            }
        }
        tx.commit()?;
        Ok(true)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::testing;

    fn texts(db: &Database, folder: i64) -> Vec<String> {
        db.list_items(Some(folder)).unwrap().into_iter().map(|i| i.text).collect()
    }

    #[test]
    fn organize_copy_move_and_undo() {
        let mut db = testing::empty();
        let a = db.create_folder("Culte").unwrap();
        let b = db.create_folder("Soirée").unwrap();
        let items: Vec<(String, String, String)> =
            ["1", "2", "3"].iter().map(|t| ("custom".into(), format!("R{t}"), t.to_string())).collect();
        let ids = db.add_items(&items, Some(a)).unwrap();
        assert!(db.move_item(ids[0], 1, Some(a)).unwrap());
        assert_eq!(texts(&db, a), ["2", "1", "3"]);
        assert!(!db.move_item(ids[0], 5, Some(a)).unwrap());

        let before = db.snapshot_folders(&[a]).unwrap();
        let copies = db.duplicate_items(&[ids[2], ids[1]]).unwrap();
        assert_eq!(copies.len(), 2);
        assert_eq!(texts(&db, a), ["2", "2", "1", "3", "3"]);
        assert!(db.restore_folders(&before).unwrap());
        assert_eq!(texts(&db, a), ["2", "1", "3"]);
        assert_eq!(db.list_items(Some(a)).unwrap()[0].id, ids[1]);

        assert!(!db.reorder_items(a, &[ids[0]]).unwrap());
        assert!(db.reorder_items(a, &[ids[2], ids[1], ids[0]]).unwrap());
        assert_eq!(texts(&db, a), ["3", "2", "1"]);
        assert_eq!(db.copy_items(&[ids[0], ids[2]], b).unwrap().len(), 2);
        assert_eq!(texts(&db, b), ["3", "1"]);
        assert_eq!(db.move_items_to_folder(&[ids[1]], b).unwrap(), 1);
        assert_eq!(texts(&db, b), ["3", "1", "2"]);
        assert_eq!(db.delete_items(&[ids[0], ids[2], 999]).unwrap(), 2);
        assert!(db.delete_folder(b).unwrap());
        assert!(db.list_items(Some(b)).unwrap().is_empty());
        assert!(!db.restore_folders(&[(b, Vec::new())]).unwrap());
    }

    #[test]
    fn root_items_and_import() {
        let mut db = testing::empty();
        db.add_item("bible", "Jean 3:16", "Car Dieu…", None, "").unwrap();
        assert_eq!(db.list_items(None).unwrap().len(), 1);
        let item =
            NewItem { source: "custom".into(), reference: "R".into(), text: "T".into(), background: "fond.png".into() };
        let folder = db.import_folder("Transférée", &[item.clone(), item]).unwrap();
        let imported = db.list_items(Some(folder)).unwrap();
        assert_eq!(imported.iter().map(|i| i.sort_order).collect::<Vec<_>>(), [Some(1), Some(2)]);
        assert_eq!(db.list_all_items().unwrap()[0].folder_id, None);
    }
}
