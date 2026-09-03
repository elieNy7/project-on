from __future__ import annotations

from typing import Any

from app.database.connection import Database


class MediaDao:
    """Bibliothèque de médias (images et vidéos) projetables."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def list_media(self) -> list[dict[str, Any]]:
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, path, kind, sort_order, created_at,
                       COALESCE(loop, 0) AS loop
                FROM media_item
                ORDER BY sort_order, id
                """,
            ).fetchall()
            return [dict(r) for r in rows]

    def get_media(self, media_id: int) -> dict[str, Any] | None:
        with self._db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, name, path, kind, COALESCE(loop, 0) AS loop
                FROM media_item WHERE id = ?
                """,
                (int(media_id),),
            ).fetchone()
            return dict(row) if row else None

    def set_loop(self, media_id: int, loop: bool) -> bool:
        """Active/désactive la boucle vidéo d'un média."""
        with self._db.connect() as conn:
            cursor = conn.execute(
                "UPDATE media_item SET loop = ? WHERE id = ?",
                (1 if loop else 0, int(media_id)),
            )
            return cursor.rowcount > 0

    def add_media(self, name: str, path: str, kind: str) -> int:
        """Ajoute un média et retourne son ID (path UNIQUE → idempotent)."""
        with self._db.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM media_item WHERE path = ?", (str(path),)
            ).fetchone()
            if existing:
                return int(existing["id"])
            max_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) FROM media_item"
            ).fetchone()[0]
            cursor = conn.execute(
                "INSERT INTO media_item (name, path, kind, sort_order) VALUES (?, ?, ?, ?)",
                (str(name), str(path), str(kind), max_order + 1),
            )
            return cursor.lastrowid or 0

    def rename_media(self, media_id: int, new_name: str) -> bool:
        with self._db.connect() as conn:
            cursor = conn.execute(
                "UPDATE media_item SET name = ? WHERE id = ?",
                (str(new_name), int(media_id)),
            )
            return cursor.rowcount > 0

    def delete_media(self, media_id: int) -> bool:
        with self._db.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM media_item WHERE id = ?", (int(media_id),)
            )
            return cursor.rowcount > 0
