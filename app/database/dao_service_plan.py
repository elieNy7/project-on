"""Déroulé du culte : sections d'une playlist (nom, durée, slide de départ)."""

from __future__ import annotations

from typing import Any

from app.database.connection import Database


class ServicePlanDao:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get_start_time(self, folder_id: int) -> str:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(start_time, '') FROM playlist_folder WHERE id = ?",
                (int(folder_id),),
            ).fetchone()
            return str(row[0]) if row else ""

    def set_start_time(self, folder_id: int, start_time: str) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE playlist_folder SET start_time = ? WHERE id = ?",
                (str(start_time or ""), int(folder_id)),
            )
            conn.commit()

    def list_sections(self, folder_id: int) -> list[dict[str, Any]]:
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, folder_id, name, duration_min, item_id, sort_order
                FROM service_section
                WHERE folder_id = ?
                ORDER BY sort_order, id
                """,
                (int(folder_id),),
            ).fetchall()
            return [dict(r) for r in rows]

    def add_section(
        self, folder_id: int, name: str, duration_min: int, item_id: int | None = None
    ) -> int:
        with self._db.connect() as conn:
            order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) FROM service_section WHERE folder_id = ?",
                (int(folder_id),),
            ).fetchone()[0]
            cursor = conn.execute(
                """
                INSERT INTO service_section (folder_id, name, duration_min, item_id, sort_order)
                VALUES (?, ?, ?, ?, ?)
                """,
                (int(folder_id), name, max(0, int(duration_min)), item_id, order + 1),
            )
            conn.commit()
            return int(cursor.lastrowid or 0)

    def update_section(
        self, section_id: int, name: str, duration_min: int, item_id: int | None
    ) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE service_section SET name = ?, duration_min = ?, item_id = ? WHERE id = ?",
                (name, max(0, int(duration_min)), item_id, int(section_id)),
            )
            conn.commit()

    def delete_section(self, section_id: int) -> None:
        with self._db.connect() as conn:
            conn.execute("DELETE FROM service_section WHERE id = ?", (int(section_id),))
            conn.commit()

    def move_section(self, section_id: int, delta: int) -> bool:
        with self._db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT folder_id FROM service_section WHERE id = ?", (int(section_id),)
            ).fetchone()
            if row is None:
                conn.rollback()
                return False
            ids = [
                r[0]
                for r in conn.execute(
                    "SELECT id FROM service_section WHERE folder_id = ? ORDER BY sort_order, id",
                    (row[0],),
                ).fetchall()
            ]
            index = ids.index(int(section_id))
            target = index + int(delta)
            if not 0 <= target < len(ids):
                conn.rollback()
                return False
            ids.insert(target, ids.pop(index))
            conn.executemany(
                "UPDATE service_section SET sort_order = ? WHERE id = ?",
                [(order, sid) for order, sid in enumerate(ids, start=1)],
            )
            conn.commit()
            return True
