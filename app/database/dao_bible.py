from __future__ import annotations

from typing import Any

from app.database.connection import Database


class BibleDao:
    def __init__(self, db: Database) -> None:
        self._db = db

    def list_translations(self) -> list[dict[str, Any]]:
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, module, name, shortname, lang
                FROM bible_translation
                ORDER BY COALESCE(shortname, name, module)
                """,
            ).fetchall()
            return [dict(r) for r in rows]

    def list_translation_books(self, translation_id: int) -> list[dict[str, Any]]:
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT book AS id, MIN(COALESCE(book_name, '')) AS name
                FROM bible_translation_verse
                WHERE translation_id = ?
                GROUP BY book
                ORDER BY book
                """,
                (int(translation_id),),
            ).fetchall()

            prepared: list[dict[str, Any]] = []
            for r in rows:
                book_id = int(r["id"])
                name = (r["name"] or "").strip()
                if not name:
                    name = str(book_id)
                prepared.append({"id": book_id, "name": name})
            return prepared

    def list_translation_chapters(self, translation_id: int, book: int) -> list[int]:
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT chapter
                FROM bible_translation_verse
                WHERE translation_id = ? AND book = ?
                ORDER BY chapter
                """,
                (int(translation_id), int(book)),
            ).fetchall()
            return [int(r[0]) for r in rows]

    def list_translation_verses(
        self, translation_id: int, book: int, chapter: int
    ) -> list[dict[str, Any]]:
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT verse, text
                FROM bible_translation_verse
                WHERE translation_id = ? AND book = ? AND chapter = ?
                ORDER BY verse
                """,
                (int(translation_id), int(book), int(chapter)),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_books(self) -> list[dict[str, Any]]:
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, abbreviation, testament, sort_order
                FROM bible_book
                ORDER BY COALESCE(sort_order, 999999), name
                """,
            ).fetchall()
            return [dict(r) for r in rows]

    def list_chapters(self, book_id: int) -> list[int]:
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT chapter
                FROM bible_verse
                WHERE book_id = ?
                ORDER BY chapter
                """,
                (book_id,),
            ).fetchall()
            return [int(r[0]) for r in rows]

    def list_verses(self, book_id: int, chapter: int) -> list[dict[str, Any]]:
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT verse, text
                FROM bible_verse
                WHERE book_id = ? AND chapter = ?
                ORDER BY verse
                """,
                (book_id, chapter),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_verse(
        self, book_id: int, chapter: int, verse: int
    ) -> dict[str, Any] | None:
        with self._db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, book_id, chapter, verse, text
                FROM bible_verse
                WHERE book_id = ? AND chapter = ? AND verse = ?
                """,
                (book_id, chapter, verse),
            ).fetchone()
            return dict(row) if row is not None else None

    def search_verses(self, query: str, limit: int = 100) -> list[dict[str, Any]]:
        q = f"%{query.strip()}%"
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT v.id, v.book_id, v.chapter, v.verse, v.text, b.name AS book_name
                FROM bible_verse v
                JOIN bible_book b ON b.id = v.book_id
                WHERE unaccent(v.text) LIKE unaccent(?)
                ORDER BY b.sort_order, v.chapter, v.verse
                LIMIT ?
                """,
                (q, int(limit)),
            ).fetchall()
            return [dict(r) for r in rows]
