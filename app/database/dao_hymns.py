from __future__ import annotations

import re
import sqlite3
from typing import Any

from app.database.connection import Database


class HymnsDao:
    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
        return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})"))

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _title_expr(has_canonical_title: bool) -> str:
        if has_canonical_title:
            return "COALESCE(NULLIF(canonical_title, ''), title)"
        return "title"

    @staticmethod
    def _fts_query(value: str) -> str:
        key = Database._search_key(value)
        if not key:
            return ""
        return " ".join(f"{token}*" for token in key.split())

    @staticmethod
    def _detect_chorus(text: str) -> bool:
        return bool(
            re.match(
                r"^(?:Dernier\s+)?(Chœur|Choeur|Refrain|Chorus)\s*[:.\-–—]?",
                str(text or "").strip(),
                re.IGNORECASE,
            )
        )

    @staticmethod
    def _stanza_label(text: str, verse_no: int, chorus_no: int) -> tuple[str, bool]:
        if HymnsDao._detect_chorus(text):
            label = "Refrain" if chorus_no <= 1 else f"Refrain {chorus_no}"
            return label, True
        return f"Strophe {verse_no}", False

    def list_hymns(
        self,
        language: str | None = None,
        limit: int | None = None,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._db.connect() as conn:
            has_canonical_title = self._has_column(conn, "hymn", "canonical_title")
            has_title_search = self._has_column(conn, "hymn", "title_search")
            title_expr = self._title_expr(has_canonical_title)
            title_search_select = ", title_search" if has_title_search else ""

            sql = f"""
                SELECT id, title AS original_title, {title_expr} AS title,
                       number, language, sort_key{title_search_select}
                FROM hymn
                WHERE (? IS NULL OR language = ?)
            """
            params: list[Any] = [language, language]
            if query:
                q = query.strip()
                if has_title_search:
                    sql += " AND (title_search LIKE ? OR unaccent(title) LIKE unaccent(?))"
                    params.extend((f"%{Database._search_key(q)}%", f"%{q}%"))
                else:
                    sql += " AND unaccent(title) LIKE unaccent(?)"
                    params.append(f"%{q}%")

            sql += " ORDER BY COALESCE(sort_key, ''), number, title COLLATE NOCASE"
            if limit is not None:
                sql += " LIMIT ?"
                params.append(int(limit))

            rows = conn.execute(sql, tuple(params)).fetchall()
            return [dict(r) for r in rows]

    def get_hymn(self, hymn_id: int) -> dict[str, Any] | None:
        with self._db.connect() as conn:
            has_canonical_title = self._has_column(conn, "hymn", "canonical_title")
            has_title_search = self._has_column(conn, "hymn", "title_search")
            title_expr = self._title_expr(has_canonical_title)
            title_search_select = ", title_search" if has_title_search else ""
            row = conn.execute(
                f"""
                SELECT id, title AS original_title, {title_expr} AS title,
                       number, language, sort_key{title_search_select}
                FROM hymn
                WHERE id = ?
                """,
                (hymn_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def list_stanzas(self, hymn_id: int) -> list[dict[str, Any]]:
        with self._db.connect() as conn:
            has_label = self._has_column(conn, "hymn_stanza", "label")
            has_chorus = self._has_column(conn, "hymn_stanza", "is_chorus")
            label_select = ", label" if has_label else ""
            chorus_select = ", is_chorus" if has_chorus else ""
            rows = conn.execute(
                f"""
                SELECT stanza_no, text{label_select}{chorus_select}
                FROM hymn_stanza
                WHERE hymn_id = ?
                ORDER BY stanza_no
                """,
                (hymn_id,),
            ).fetchall()

            out: list[dict[str, Any]] = []
            verse_no = 0
            chorus_no = 0
            for row in rows:
                text = str(row["text"] or "")
                if self._detect_chorus(text):
                    chorus_no += 1
                    inferred_label, inferred_chorus = self._stanza_label(
                        text, verse_no, chorus_no
                    )
                else:
                    verse_no += 1
                    inferred_label, inferred_chorus = self._stanza_label(
                        text, verse_no, chorus_no
                    )
                label = (
                    str(row["label"] or "").strip()
                    if has_label and row["label"]
                    else inferred_label
                )
                is_chorus = (
                    bool(int(row["is_chorus"] or 0))
                    if has_chorus
                    else inferred_chorus
                )
                out.append(
                    {
                        "stanza_no": row["stanza_no"],
                        "label": label,
                        "is_chorus": is_chorus,
                        "text": text,
                    }
                )
            return out

    def search_stanzas(self, query: str, limit: int = 100) -> list[dict[str, Any]]:
        q = query.strip()
        if not q:
            return []

        with self._db.connect() as conn:
            has_canonical_title = self._has_column(conn, "hymn", "canonical_title")
            has_label = self._has_column(conn, "hymn_stanza", "label")
            has_chorus = self._has_column(conn, "hymn_stanza", "is_chorus")
            title_expr = (
                "COALESCE(NULLIF(h.canonical_title, ''), h.title)"
                if has_canonical_title
                else "h.title"
            )
            label_expr = (
                "COALESCE(NULLIF(hs.label, ''), 'Strophe ' || hs.stanza_no)"
                if has_label
                else "'Strophe ' || hs.stanza_no"
            )
            chorus_expr = "hs.is_chorus" if has_chorus else "0"
            rows: list[sqlite3.Row] = []

            if self._table_exists(conn, "hymn_stanza_fts"):
                fts_q = self._fts_query(q)
                if fts_q:
                    try:
                        rows = conn.execute(
                            f"""
                            SELECT hs.id, hs.hymn_id, hs.stanza_no, hs.text,
                                   {title_expr} AS hymn_title,
                                   h.title AS original_title,
                                   h.number AS hymn_number,
                                   {label_expr} AS label,
                                   {chorus_expr} AS is_chorus
                            FROM hymn_stanza_fts
                            JOIN hymn_stanza hs ON hs.id = hymn_stanza_fts.rowid
                            JOIN hymn h ON h.id = hs.hymn_id
                            WHERE hymn_stanza_fts MATCH ?
                            ORDER BY bm25(hymn_stanza_fts), COALESCE(h.sort_key, ''), h.number, hs.stanza_no
                            LIMIT ?
                            """,
                            (fts_q, int(limit)),
                        ).fetchall()
                    except sqlite3.Error:
                        rows = []

            if not rows:
                rows = conn.execute(
                    f"""
                    SELECT hs.id, hs.hymn_id, hs.stanza_no, hs.text,
                           {title_expr} AS hymn_title,
                           h.title AS original_title,
                           h.number AS hymn_number,
                           {label_expr} AS label,
                           {chorus_expr} AS is_chorus
                    FROM hymn_stanza hs
                    JOIN hymn h ON h.id = hs.hymn_id
                    WHERE unaccent(hs.text) LIKE unaccent(?)
                    ORDER BY COALESCE(h.sort_key, ''), h.number, hs.stanza_no
                    LIMIT ?
                    """,
                    (f"%{q}%", int(limit)),
                ).fetchall()
            return [dict(r) for r in rows]

    def import_hymn(
        self,
        title: str,
        stanzas: list[str],
        number: str | None = None,
        language: str = "fr",
    ) -> int:
        """Import a hymn with its stanzas into the database. Returns the new hymn ID."""
        with self._db.connect() as conn:
            hymn_cols = [r[1] for r in conn.execute("PRAGMA table_info(hymn)").fetchall()]
            has_canonical_title = "canonical_title" in hymn_cols
            has_title_search = "title_search" in hymn_cols
            canonical_title = Database._clean_hymn_title_for_canonical(title)
            title_search = Database._search_key(
                " ".join(str(p or "") for p in (canonical_title, title, number, language))
            )

            columns = ["title", "number", "language", "sort_key"]
            values: list[Any] = [title, number, language, title.lower()]
            if has_canonical_title:
                columns.append("canonical_title")
                values.append(canonical_title)
            if has_title_search:
                columns.append("title_search")
                values.append(title_search)

            placeholders = ", ".join("?" for _ in columns)
            cursor = conn.execute(
                f"""
                INSERT INTO hymn ({", ".join(columns)})
                VALUES ({placeholders})
                """,
                tuple(values),
            )
            hymn_id = cursor.lastrowid

            stanza_cols = [
                r[1] for r in conn.execute("PRAGMA table_info(hymn_stanza)").fetchall()
            ]
            has_label = "label" in stanza_cols
            has_chorus = "is_chorus" in stanza_cols
            verse_no = 0
            chorus_no = 0
            for idx, text in enumerate(stanzas, start=1):
                if self._detect_chorus(text):
                    chorus_no += 1
                    label, is_chorus = self._stanza_label(text, verse_no, chorus_no)
                else:
                    verse_no += 1
                    label, is_chorus = self._stanza_label(text, verse_no, chorus_no)

                columns = ["hymn_id", "stanza_no", "text"]
                values = [hymn_id, idx, text]
                if has_label:
                    columns.append("label")
                    values.append(label)
                if has_chorus:
                    columns.append("is_chorus")
                    values.append(1 if is_chorus else 0)
                placeholders = ", ".join("?" for _ in columns)
                stanza_cursor = conn.execute(
                    f"""
                    INSERT INTO hymn_stanza ({", ".join(columns)})
                    VALUES ({placeholders})
                    """,
                    tuple(values),
                )
                if self._table_exists(conn, "hymn_stanza_fts"):
                    conn.execute(
                        """
                        INSERT INTO hymn_stanza_fts
                            (rowid, text, hymn_title, hymn_number, label)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            stanza_cursor.lastrowid,
                            text,
                            canonical_title,
                            number or "",
                            label,
                        ),
                    )

            return hymn_id  # type: ignore

    def hymn_exists(self, title: str) -> bool:
        with self._db.connect() as conn:
            has_title_search = self._has_column(conn, "hymn", "title_search")
            if has_title_search:
                key = Database._search_key(title)
                row = conn.execute(
                    """
                    SELECT 1
                    FROM hymn
                    WHERE title = ? OR title_search LIKE ?
                    LIMIT 1
                    """,
                    (title, f"%{key}%"),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT 1 FROM hymn WHERE title = ? LIMIT 1",
                    (title,),
                ).fetchone()
            return row is not None

    def delete_hymn(self, hymn_id: int) -> None:
        with self._db.connect() as conn:
            conn.execute("DELETE FROM hymn_stanza WHERE hymn_id = ?", (hymn_id,))
            conn.execute("DELETE FROM hymn WHERE id = ?", (hymn_id,))

    def delete_all_hymns(self) -> int:
        with self._db.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM hymn").fetchone()[0]
            conn.execute("DELETE FROM hymn_stanza")
            conn.execute("DELETE FROM hymn")
            return count
