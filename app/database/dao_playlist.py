from __future__ import annotations

from typing import Any

from app.database.connection import Database


class PlaylistDao:
    def __init__(self, db: Database) -> None:
        self._db = db

    def list_folders(self) -> list[dict[str, Any]]:
        """Liste tous les dossiers de playlist."""
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, sort_order, created_at
                FROM playlist_folder
                ORDER BY sort_order, id
                """,
            ).fetchall()
            return [dict(r) for r in rows]

    def create_folder(self, name: str) -> int:
        """Crée un nouveau dossier et retourne son ID."""
        with self._db.connect() as conn:
            max_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) FROM playlist_folder",
            ).fetchone()[0]
            cursor = conn.execute(
                """
                INSERT INTO playlist_folder (name, sort_order)
                VALUES (?, ?)
                """,
                (name, max_order + 1),
            )
            return cursor.lastrowid or 0

    def rename_folder(self, folder_id: int, new_name: str) -> bool:
        """Renomme un dossier."""
        with self._db.connect() as conn:
            cursor = conn.execute(
                "UPDATE playlist_folder SET name = ? WHERE id = ?",
                (new_name, folder_id),
            )
            return cursor.rowcount > 0

    def delete_folder(self, folder_id: int) -> bool:
        """Supprime un dossier."""
        with self._db.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM playlist_folder WHERE id = ?",
                (folder_id,),
            )
            return cursor.rowcount > 0

    def get_folder(self, folder_id: int) -> dict[str, Any] | None:
        """Récupère un dossier par son ID."""
        with self._db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, name, sort_order, created_at
                FROM playlist_folder
                WHERE id = ?
                """,
                (folder_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_items(self, folder_id: int | None = None) -> list[dict[str, Any]]:
        """Liste les slides d'un dossier ou à la racine (folder_id=None)."""
        with self._db.connect() as conn:
            if folder_id is None:
                rows = conn.execute(
                    """
                    SELECT id, folder_id, source, reference, text, sort_order,
                           COALESCE(background, '') as background
                    FROM playlist_item
                    WHERE folder_id IS NULL
                    ORDER BY sort_order, id
                    """,
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, folder_id, source, reference, text, sort_order,
                           COALESCE(background, '') as background
                    FROM playlist_item
                    WHERE folder_id = ?
                    ORDER BY sort_order, id
                    """,
                    (folder_id,),
                ).fetchall()
            return [dict(r) for r in rows]

    def list_all_items(self) -> list[dict[str, Any]]:
        """Liste tous les slides de la playlist."""
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, folder_id, source, reference, text, sort_order,
                       COALESCE(background, '') as background
                FROM playlist_item
                ORDER BY folder_id NULLS FIRST, sort_order, id
                """,
            ).fetchall()
            return [dict(r) for r in rows]

    def add_item(
        self,
        source: str,
        reference: str,
        text: str,
        folder_id: int | None = None,
        background: str = "",
    ) -> int:
        """Ajoute un slide à la playlist et retourne son ID."""
        with self._db.connect() as conn:
            if folder_id is None:
                max_order = conn.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) FROM playlist_item WHERE folder_id IS NULL",
                ).fetchone()[0]
            else:
                max_order = conn.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) FROM playlist_item WHERE folder_id = ?",
                    (folder_id,),
                ).fetchone()[0]
            cursor = conn.execute(
                """
                INSERT INTO playlist_item (folder_id, source, reference, text, sort_order, background)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (folder_id, source, reference, text, max_order + 1, background or ""),
            )
            return cursor.lastrowid or 0

    def move_item(self, item_id: int, delta: int, folder_id: int | None) -> bool:
        """Move against a fresh ordering under one write transaction."""
        with self._db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT id FROM playlist_item WHERE folder_id IS ? ORDER BY sort_order, id",
                (folder_id,),
            ).fetchall()
            ids = [row[0] for row in rows]
            if item_id not in ids:
                return False
            index = ids.index(item_id)
            target = index + int(delta)
            if target < 0 or target >= len(ids):
                return False
            ids[index], ids[target] = ids[target], ids[index]
            # Normalize ties as well, so imported older orderings stay movable.
            conn.executemany(
                "UPDATE playlist_item SET sort_order = ? WHERE id = ?",
                [(rank, ident) for rank, ident in enumerate(ids, 1)],
            )
            return True

    def import_folder(self, name: str, items: list[dict]) -> int:
        """Insert a transferred folder and its media references atomically."""
        with self._db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            order = conn.execute("SELECT COALESCE(MAX(sort_order), 0)+1 FROM playlist_folder").fetchone()[0]
            folder_id = conn.execute(
                "INSERT INTO playlist_folder(name, sort_order) VALUES (?, ?)", (name, order)
            ).lastrowid
            conn.executemany(
                "INSERT INTO playlist_item(folder_id, source, reference, text, background, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                [(folder_id, it.get("source", "custom"), it.get("reference", ""),
                  it.get("text", ""), it.get("background", ""), rank)
                 for rank, it in enumerate(items, 1)],
            )
            return int(folder_id)

    def update_item_background(self, item_id: int, background: str) -> bool:
        """Met à jour l'image de fond d'un slide."""
        with self._db.connect() as conn:
            cursor = conn.execute(
                "UPDATE playlist_item SET background = ? WHERE id = ?",
                (background or "", item_id),
            )
            return cursor.rowcount > 0

    def add_items(
        self, items: list[tuple[str, str, str]], folder_id: int | None = None
    ) -> list[int]:
        """Add several playlist slides in one transaction and return their IDs."""
        if not items:
            return []

        with self._db.connect() as conn:
            if folder_id is None:
                max_order = conn.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) FROM playlist_item WHERE folder_id IS NULL",
                ).fetchone()[0]
            else:
                max_order = conn.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) FROM playlist_item WHERE folder_id = ?",
                    (folder_id,),
                ).fetchone()[0]

            inserted_ids: list[int] = []
            for offset, (source, reference, text) in enumerate(items, start=1):
                cursor = conn.execute(
                    """
                    INSERT INTO playlist_item (folder_id, source, reference, text, sort_order)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (folder_id, source, reference, text, max_order + offset),
                )
                inserted_ids.append(cursor.lastrowid or 0)
            return inserted_ids

    def delete_item(self, item_id: int) -> bool:
        """Supprime un slide de la playlist."""
        with self._db.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM playlist_item WHERE id = ?",
                (item_id,),
            )
            return cursor.rowcount > 0

    def update_item_sort_order(
        self, item_id: int, sort_order: int, folder_id: int | None = None
    ) -> bool:
        """Met à jour l'ordre de tri et le dossier d'un item."""
        with self._db.connect() as conn:
            cursor = conn.execute(
                "UPDATE playlist_item SET sort_order = ?, folder_id = ? WHERE id = ?",
                (sort_order, folder_id, item_id),
            )
            return cursor.rowcount > 0

    def update_item(self, item_id: int, reference: str, text: str) -> bool:
        """Met à jour la référence et le texte d'un slide existant."""
        with self._db.connect() as conn:
            cursor = conn.execute(
                "UPDATE playlist_item SET reference = ?, text = ? WHERE id = ?",
                (reference, text, item_id),
            )
            return cursor.rowcount > 0
