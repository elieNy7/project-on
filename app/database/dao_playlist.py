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

    # ── Organisation : plusieurs éléments à la fois ───────────────────────

    _ITEM_COLUMNS = "id, folder_id, source, reference, text, sort_order, background, created_at"

    @staticmethod
    def _ordered_ids(conn, folder_id: int) -> list[int]:
        return [r[0] for r in conn.execute(
            "SELECT id FROM playlist_item WHERE folder_id IS ? ORDER BY sort_order, id",
            (folder_id,),
        ).fetchall()]

    @staticmethod
    def _renumber(conn, ids: list[int]) -> None:
        conn.executemany(
            "UPDATE playlist_item SET sort_order = ? WHERE id = ?",
            [(rank, ident) for rank, ident in enumerate(ids, 1)],
        )

    def reorder_items(self, folder_id: int, ordered_ids: list[int]) -> bool:
        """Applique l'ordre donné (glisser-déposer). Refuse un ordre qui ne
        contient pas exactement les éléments du dossier."""
        with self._db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = self._ordered_ids(conn, folder_id)
            ordered = [int(i) for i in ordered_ids]
            if sorted(current) != sorted(ordered):
                return False
            self._renumber(conn, ordered)
            return True

    def delete_items(self, item_ids: list[int]) -> int:
        """Supprime plusieurs éléments ; renvoie le nombre supprimé."""
        with self._db.connect() as conn:
            cursor = conn.executemany(
                "DELETE FROM playlist_item WHERE id = ?", [(int(i),) for i in item_ids]
            )
            return cursor.rowcount

    def duplicate_items(self, item_ids: list[int]) -> list[int]:
        """Copie chaque élément juste après l'original ; renvoie les copies."""
        wanted = {int(i) for i in item_ids}
        with self._db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                f"SELECT {self._ITEM_COLUMNS} FROM playlist_item WHERE id IN "
                f"({','.join('?' * len(wanted))})",
                tuple(wanted),
            ).fetchall() if wanted else []
            copies: list[int] = []
            by_folder: dict[Any, dict[int, int]] = {}
            for row in rows:
                new_id = conn.execute(
                    "INSERT INTO playlist_item (folder_id, source, reference, text, sort_order,"
                    " background) VALUES (?, ?, ?, ?, ?, ?)",
                    (row["folder_id"], row["source"], row["reference"], row["text"],
                     row["sort_order"], row["background"] or ""),
                ).lastrowid
                copies.append(int(new_id))
                by_folder.setdefault(row["folder_id"], {})[int(row["id"])] = int(new_id)
            for folder_id, pairs in by_folder.items():
                order = [i for i in self._ordered_ids(conn, folder_id)
                         if i not in pairs.values()]
                placed: list[int] = []
                for ident in order:
                    placed.append(ident)
                    if ident in pairs:
                        placed.append(pairs[ident])
                self._renumber(conn, placed)
            return copies

    def copy_items(self, item_ids: list[int], folder_id: int) -> list[int]:
        """Copie les éléments (dans leur ordre) à la fin d'une autre playlist."""
        with self._db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = self._rows_in_order(conn, item_ids)
            start = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) FROM playlist_item WHERE folder_id = ?",
                (folder_id,),
            ).fetchone()[0]
            return [int(conn.execute(
                "INSERT INTO playlist_item (folder_id, source, reference, text, sort_order,"
                " background) VALUES (?, ?, ?, ?, ?, ?)",
                (folder_id, row["source"], row["reference"], row["text"], start + rank,
                 row["background"] or ""),
            ).lastrowid) for rank, row in enumerate(rows, 1)]

    def move_items_to_folder(self, item_ids: list[int], folder_id: int) -> int:
        """Déplace les éléments (dans leur ordre) à la fin d'une autre playlist."""
        with self._db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = self._rows_in_order(conn, item_ids)
            start = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) FROM playlist_item WHERE folder_id = ?",
                (folder_id,),
            ).fetchone()[0]
            conn.executemany(
                "UPDATE playlist_item SET folder_id = ?, sort_order = ? WHERE id = ?",
                [(folder_id, start + rank, row["id"]) for rank, row in enumerate(rows, 1)],
            )
            return len(rows)

    def _rows_in_order(self, conn, item_ids: list[int]) -> list[Any]:
        wanted = [int(i) for i in item_ids]
        if not wanted:
            return []
        rows = conn.execute(
            f"SELECT {self._ITEM_COLUMNS} FROM playlist_item WHERE id IN "
            f"({','.join('?' * len(wanted))}) ORDER BY folder_id, sort_order, id",
            tuple(wanted),
        ).fetchall()
        return list(rows)

    # ── Annuler : instantané puis restauration exacte ─────────────────────

    def snapshot_folders(self, folder_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
        """Contenu complet (identifiants compris) des playlists données."""
        out: dict[int, list[dict[str, Any]]] = {}
        with self._db.connect() as conn:
            for folder_id in folder_ids:
                out[int(folder_id)] = [dict(r) for r in conn.execute(
                    f"SELECT {self._ITEM_COLUMNS} FROM playlist_item WHERE folder_id = ?"
                    " ORDER BY sort_order, id",
                    (int(folder_id),),
                ).fetchall()]
        return out

    def restore_folders(self, snapshot: dict[int, list[dict[str, Any]]]) -> bool:
        """Remet les playlists exactement dans l'état de l'instantané, avec
        les mêmes identifiants (le déroulé du culte s'y réfère). Refuse si
        une des playlists a été supprimée entre-temps."""
        with self._db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for folder_id in snapshot:
                if conn.execute(
                    "SELECT 1 FROM playlist_folder WHERE id = ?", (int(folder_id),)
                ).fetchone() is None:
                    conn.rollback()
                    return False
            for folder_id, rows in snapshot.items():
                conn.execute("DELETE FROM playlist_item WHERE folder_id = ?", (int(folder_id),))
                conn.executemany(
                    "INSERT OR REPLACE INTO playlist_item (id, folder_id, source, reference,"
                    " text, sort_order, background, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [(r["id"], int(folder_id), r["source"], r["reference"], r["text"],
                      r["sort_order"], r["background"] or "", r["created_at"]) for r in rows],
                )
            return True
