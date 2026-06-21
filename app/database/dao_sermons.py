from __future__ import annotations

import re
import sqlite3
from typing import Any

from app.database.connection import Database


class SermonsDao:
    def __init__(self, db: Database) -> None:
        self._db = db

    def _date_to_year(self, date_code: str) -> int | None:
        if not date_code or len(date_code) < 2:
            return None
        yy = date_code[:2]
        if yy.isdigit():
            year = int(yy)
            return 1900 + year if year >= 47 else 2000 + year
        return None

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
            return "COALESCE(NULLIF(s.canonical_title, ''), s.title)"
        return "s.title"

    @staticmethod
    def _sermon_title_expr(has_canonical_title: bool) -> str:
        if has_canonical_title:
            return "COALESCE(NULLIF(canonical_title, ''), title)"
        return "title"

    @staticmethod
    def _format_reference(date_code: Any, title: Any, marker: Any) -> str:
        parts = [
            str(date_code or "").strip(),
            str(title or "").strip(),
            str(marker or "").strip(),
        ]
        return " - ".join(p for p in parts if p)

    @staticmethod
    def _expose_ref_parts(value: Any) -> tuple[int, int] | None:
        match = re.search(r"(\d+)-(\d+)\s*$", str(value or "").strip())
        if not match:
            return None
        return int(match.group(1)), int(match.group(2))

    @staticmethod
    def _clean_expose_title(value: Any) -> str:
        title = str(value or "").strip()
        title = re.sub(r"\s+", " ", title)
        title = re.sub(r"^CHAPITRE\s+\d+\s+", "", title, flags=re.IGNORECASE)
        return title.strip()

    @staticmethod
    def _expose_chapter_num(date_code: Any, title: Any, translator: str) -> int:
        match = re.search(r"CH(\d+)", str(date_code or ""))
        raw_num = int(match.group(1)) if match else 0
        if translator.upper() == "SHP":
            clean_title = SermonsDao._clean_expose_title(title).upper()
            if clean_title.startswith("INTRODUCTION"):
                return 0
            if raw_num > 0:
                return raw_num - 1
        return raw_num

    @staticmethod
    def _fts_query(value: str) -> str:
        key = Database._search_key(value)
        if not key:
            return ""
        return " ".join(f"{token}*" for token in key.split())

    def list_sermon_years(
        self,
        tradition: str | None = None,
        language: str | None = None,
        title_query: str | None = None,
        translator: str | None = None,
    ) -> list[int]:
        years_set: set[int] = set()
        with self._db.connect() as conn:
            has_title_search = self._has_column(conn, "sermon", "title_search")
            sql = "SELECT DISTINCT date FROM sermon WHERE 1=1"
            params: list[Any] = []

            trad = translator or tradition
            if trad:
                sql += " AND tradition = ?"
                params.append(trad.upper())
            if language:
                sql += " AND language = ?"
                params.append(language[:2].lower())
            if title_query:
                query = title_query.strip()
                if has_title_search:
                    sql += " AND (title_search LIKE ? OR unaccent(title) LIKE unaccent(?))"
                    params.extend((f"%{Database._search_key(query)}%", f"%{query}%"))
                else:
                    sql += " AND unaccent(title) LIKE unaccent(?)"
                    params.append(f"%{query}%")

            for r in conn.execute(sql, tuple(params)).fetchall():
                d = r["date"]
                if d and len(d) >= 2:
                    yy = d[:2]
                    if len(d) >= 10 and d[4] == "-" and d[7] == "-":
                        years_set.add(int(d[:4]))
                    elif yy.isdigit():
                        y = int(yy)
                        years_set.add(1900 + y if y >= 47 else 2000 + y)
        return sorted(years_set)

    def list_branham_translators(self, language: str = "fr") -> list[str]:
        lang_code = language[:2].lower()
        translators = set()
        with self._db.connect() as conn:
            sql = "SELECT DISTINCT tradition FROM sermon WHERE language = ? AND tradition IS NOT NULL AND tradition != ''"
            for r in conn.execute(sql, (lang_code,)).fetchall():
                if r[0]:
                    translators.add(str(r[0]).upper())
        return sorted(list(translators))

    def _normalize_filter_date(self, value: str | None) -> str | None:
        if value is None:
            return None
        v = str(value).strip()
        if not v:
            return None
        if v == "__NODATE__":
            return v
        if len(v) == 10 and v[4] == "-" and v[7] == "-":
            return f"{v[2:4]}-{v[5:7]}{v[8:10]}"
        return v

    def list_sermon_locations(
        self,
        tradition: str | None = None,
        language: str | None = None,
    ) -> list[str]:
        locs: set[str] = set()
        with self._db.connect() as conn:
            sql = "SELECT DISTINCT location FROM sermon WHERE location IS NOT NULL AND location != '' AND location != 'Lieu inconnu'"
            params: list[Any] = []
            trad = tradition
            if trad:
                sql += " AND tradition = ?"
                params.append(trad.upper())
            if language:
                sql += " AND language = ?"
                params.append(language[:2].lower())
            for r in conn.execute(sql, tuple(params)).fetchall():
                raw = str(r[0] or "").strip()
                city = raw.split()[0] if raw else ""
                if city:
                    locs.add(city)
        return sorted(locs)

    def list_sermons(
        self,
        tradition: str | None = None,
        language: str | None = None,
        title_query: str | None = None,
        translator: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        location_query: str | None = None,
        sort_by: str = "date",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        df = self._normalize_filter_date(date_from)
        dt = self._normalize_filter_date(date_to)
        out: list[dict[str, Any]] = []

        with self._db.connect() as conn:
            has_location = self._has_column(conn, "sermon", "location")
            has_canonical_title = self._has_column(conn, "sermon", "canonical_title")
            has_title_search = self._has_column(conn, "sermon", "title_search")
            title_expr = self._sermon_title_expr(has_canonical_title)
            select_loc = ", location" if has_location else ""

            sql = f"""
                SELECT id, date, title AS original_title, {title_expr} AS title,
                       tradition, language, source_path{select_loc}
                FROM sermon
                WHERE 1=1
            """
            params: list[Any] = []

            trad = translator or tradition
            if trad:
                sql += " AND tradition = ?"
                params.append(trad.upper())
            if title_query:
                query = title_query.strip()
                if has_title_search:
                    sql += " AND (title_search LIKE ? OR unaccent(title) LIKE unaccent(?))"
                    params.extend((f"%{Database._search_key(query)}%", f"%{query}%"))
                else:
                    sql += " AND unaccent(title) LIKE unaccent(?)"
                    params.append(f"%{query}%")
            if location_query and has_location:
                sql += " AND unaccent(location) LIKE unaccent(?)"
                params.append(f"%{location_query.strip()}%")

            if df == "__NODATE__" or dt == "__NODATE__":
                sql += " AND (date IS NULL OR date = '' OR date NOT GLOB '[0-9]*')"
            else:
                if df:
                    sql += " AND date >= ?"
                    params.append(df)
                if dt:
                    sql += " AND date <= ?"
                    params.append(dt)

            if language:
                sql += " AND language = ?"
                params.append(language[:2].lower())

            order = "date, title COLLATE NOCASE"
            if sort_by == "title":
                order = "title COLLATE NOCASE, date"
            elif sort_by == "location" and has_location:
                order = "location COLLATE NOCASE, date, title COLLATE NOCASE"
            sql += f" ORDER BY {order}"

            if limit:
                sql += " LIMIT ?"
                params.append(limit)

            rows = conn.execute(sql, tuple(params)).fetchall()
            for r in rows:
                loc = str(r["location"]) if has_location and r["location"] else ""
                out.append(
                    {
                        "id": f"int_{r['id']}",
                        "title": r["title"],
                        "original_title": r["original_title"],
                        "date": r["date"],
                        "date_code": r["date"],
                        "tradition": r["tradition"],
                        "language": r["language"],
                        "translator": r["tradition"],
                        "sort_key": r["date"],
                        "location": loc,
                    }
                )
        return out

    def get_sermon(self, sermon_id: Any, language: str = "en") -> dict[str, Any] | None:
        int_id = int(str(sermon_id).replace("int_", ""))
        with self._db.connect() as conn:
            has_canonical_title = self._has_column(conn, "sermon", "canonical_title")
            has_location = self._has_column(conn, "sermon", "location")
            title_expr = self._sermon_title_expr(has_canonical_title)
            select_loc = ", location" if has_location else ""
            row = conn.execute(
                f"""
                SELECT id, date, title AS original_title, {title_expr} AS title,
                       tradition, language, source_path{select_loc}
                FROM sermon
                WHERE id = ?
                """,
                (int_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "id": f"int_{row['id']}",
                "title": row["title"],
                "original_title": row["original_title"],
                "date": row["date"],
                "date_code": row["date"],
                "tradition": row["tradition"],
                "language": row["language"],
                "translator": row["tradition"],
                "sort_key": row["date"],
                "location": str(row["location"] or "") if has_location else "",
            }

    def _get_marker(self, ref: str | None, no: int) -> str:
        value = (
            str(ref or "")
            .replace("Ã‚Â¶", "¶")
            .replace("Ã‚Â§", "§")
            .replace("Â¶", "¶")
            .replace("Â§", "§")
            .strip()
        )
        if not value:
            return f"¶{no}"

        bss_match = re.search(r"([A-Z]-[A-Z0-9]+)\s*$", value)
        if bss_match:
            return bss_match.group(1).replace("O", "0")

        marker_match = re.search(r"([¶§]\s*\d+)\s*$", value)
        if marker_match:
            return re.sub(r"\s+", "", marker_match.group(1))

        page_match = re.search(r"(\d+)-(\d+)\s*$", value)
        if page_match:
            return f"{page_match.group(1)}-{page_match.group(2)}"

        return f"¶{no}"

    def list_paragraphs(
        self, sermon_id: Any, language: str = "en"
    ) -> list[dict[str, Any]]:
        int_id = int(str(sermon_id).replace("int_", ""))
        with self._db.connect() as conn:
            has_marker = self._has_column(conn, "sermon_paragraph", "marker")
            marker_select = ", marker" if has_marker else ""
            rows = conn.execute(
                f"""
                SELECT paragraph_no, ref, text{marker_select}
                FROM sermon_paragraph
                WHERE sermon_id = ?
                ORDER BY paragraph_no
                """,
                (int_id,),
            ).fetchall()

            out = []
            for r in rows:
                marker = (
                    str(r["marker"] or "").strip()
                    if has_marker and r["marker"]
                    else self._get_marker(r["ref"], r["paragraph_no"])
                )
                out.append(
                    {
                        "paragraph_no": r["paragraph_no"],
                        "para_id": marker,
                        "marker": marker,
                        "ref": r["ref"],
                        "text": r["text"],
                    }
                )
            return out

    def get_paragraph(
        self, sermon_id: Any, paragraph_no: int, language: str = "en"
    ) -> dict[str, Any] | None:
        int_id = int(str(sermon_id).replace("int_", ""))
        with self._db.connect() as conn:
            has_marker = self._has_column(conn, "sermon_paragraph", "marker")
            marker_select = ", marker" if has_marker else ""
            row = conn.execute(
                f"""
                SELECT paragraph_no, ref, text{marker_select}
                FROM sermon_paragraph
                WHERE sermon_id = ? AND paragraph_no = ?
                """,
                (int_id, paragraph_no),
            ).fetchone()
            if not row:
                return None
            marker = (
                str(row["marker"] or "").strip()
                if has_marker and row["marker"]
                else self._get_marker(row["ref"], row["paragraph_no"])
            )
            return {
                "id": f"int_p_{int_id}_{paragraph_no}",
                "sermon_id": f"int_{int_id}",
                "paragraph_no": row["paragraph_no"],
                "para_id": marker,
                "marker": marker,
                "ref": row["ref"],
                "text": row["text"],
            }

    def search_paragraphs(
        self,
        query: str,
        language: str = "en",
        translator: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        q = query.strip()
        if not q:
            return out

        with self._db.connect() as conn:
            has_marker = self._has_column(conn, "sermon_paragraph", "marker")
            has_canonical_title = self._has_column(conn, "sermon", "canonical_title")
            title_expr = self._title_expr(has_canonical_title)
            marker_expr = "COALESCE(NULLIF(p.marker, ''), p.ref, '')" if has_marker else "p.ref"
            rows: list[sqlite3.Row] = []

            if self._table_exists(conn, "sermon_paragraph_fts"):
                fts_q = self._fts_query(q)
                if fts_q:
                    try:
                        sql = f"""
                            SELECT p.sermon_id, p.paragraph_no, p.ref, p.text,
                                   {marker_expr} AS marker,
                                   s.title AS original_title,
                                   {title_expr} AS title,
                                   s.date, s.tradition
                            FROM sermon_paragraph_fts
                            JOIN sermon_paragraph p ON p.id = sermon_paragraph_fts.rowid
                            JOIN sermon s ON s.id = p.sermon_id
                            WHERE sermon_paragraph_fts MATCH ?
                        """
                        params: list[Any] = [fts_q]
                        if translator:
                            sql += " AND s.tradition = ?"
                            params.append(translator.upper())
                        if language:
                            sql += " AND s.language = ?"
                            params.append(language[:2].lower())
                        sql += " ORDER BY bm25(sermon_paragraph_fts), s.date, p.paragraph_no LIMIT ?"
                        params.append(limit)
                        rows = conn.execute(sql, tuple(params)).fetchall()
                    except sqlite3.Error:
                        rows = []

            if not rows:
                sql = f"""
                    SELECT p.sermon_id, p.paragraph_no, p.ref, p.text,
                           {marker_expr} AS marker,
                           s.title AS original_title,
                           {title_expr} AS title,
                           s.date, s.tradition
                    FROM sermon_paragraph p
                    JOIN sermon s ON s.id = p.sermon_id
                    WHERE unaccent(p.text) LIKE unaccent(?)
                """
                params = [f"%{q}%"]
                if translator:
                    sql += " AND s.tradition = ?"
                    params.append(translator.upper())
                if language:
                    sql += " AND s.language = ?"
                    params.append(language[:2].lower())
                sql += " ORDER BY s.date, p.paragraph_no LIMIT ?"
                params.append(limit)
                rows = conn.execute(sql, tuple(params)).fetchall()

            for r in rows:
                marker = str(r["marker"] or "").strip() or self._get_marker(
                    r["ref"], r["paragraph_no"]
                )
                ref = self._format_reference(r["date"], r["title"], marker)
                out.append(
                    {
                        "id": f"int_p_{r['sermon_id']}_{r['paragraph_no']}",
                        "sermon_id": f"int_{r['sermon_id']}",
                        "paragraph_no": r["paragraph_no"],
                        "para_id": marker,
                        "marker": marker,
                        "ref": ref,
                        "reference": ref,
                        "raw_ref": r["ref"],
                        "text": r["text"],
                        "sermon_title": r["title"],
                        "original_title": r["original_title"],
                        "sermon_date": r["date"],
                        "sermon_tradition": r["tradition"],
                    }
                )
        return out

    def list_expose_chapters(self, translator: str = "VGR") -> list[dict[str, Any]]:
        prefix = "BK-AGES" if translator.upper() == "VGR" else "BK-AGES-SHP"
        translator = translator.upper()
        with self._db.connect() as conn:
            has_canonical_title = self._has_column(conn, "sermon", "canonical_title")
            title_expr = self._sermon_title_expr(has_canonical_title)
            sql = f"""
                SELECT id, date, title AS original_title, {title_expr} AS title
                FROM sermon
                WHERE date LIKE ? AND tradition = ?
                ORDER BY date
            """
            rows = conn.execute(sql, (f"{prefix}-%", translator)).fetchall()
            out = []
            for r in rows:
                date_code = r["date"] or ""
                title = self._clean_expose_title(r["title"] or "")
                original_title = self._clean_expose_title(r["original_title"] or "")
                ch_num = self._expose_chapter_num(date_code, title, translator)
                out.append(
                    {
                        "id": f"int_{r['id']}",
                        "title": title,
                        "original_title": original_title,
                        "chapter_num": ch_num,
                        "date_code": date_code,
                    }
                )
            return out

    def list_expose_pages(self, chapter_id: Any) -> list[int]:
        int_id = int(str(chapter_id).replace("int_", ""))
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT ref FROM sermon_paragraph WHERE sermon_id = ? ORDER BY paragraph_no",
                (int_id,),
            ).fetchall()
            if not rows:
                return []

            pages = set()
            has_pages = False
            for r in rows:
                ref_parts = self._expose_ref_parts(r["ref"])
                if ref_parts is not None:
                    pages.add(ref_parts[0])
                    has_pages = True
            if has_pages:
                return sorted(list(pages))

            count = len(rows)
            import math

            return list(range(1, math.ceil(count / 50) + 1))

    def list_expose_page_paragraphs(
        self, chapter_id: Any, page_num: int
    ) -> list[dict[str, Any]]:
        int_id = int(str(chapter_id).replace("int_", ""))

        with self._db.connect() as conn:
            has_marker = self._has_column(conn, "sermon_paragraph", "marker")
            marker_select = ", marker" if has_marker else ""
            rows = conn.execute(
                f"""
                SELECT paragraph_no, ref, text{marker_select}
                FROM sermon_paragraph
                WHERE sermon_id = ?
                ORDER BY paragraph_no
                """,
                (int_id,),
            ).fetchall()

            if not rows:
                return []

            has_pages = any(self._expose_ref_parts(r["ref"]) is not None for r in rows)

            out = []
            if has_pages:
                for r in rows:
                    ref_parts = self._expose_ref_parts(r["ref"])
                    if ref_parts is None:
                        continue
                    p_val, para_val = ref_parts
                    if p_val == page_num:
                        marker = (
                            str(r["marker"] or "").strip()
                            if has_marker and r["marker"]
                            else f"{p_val}-{para_val}"
                        )
                        out.append(
                            {
                                "paragraph_no": r["paragraph_no"],
                                "para_id": marker,
                                "marker": marker,
                                "ref": r["ref"],
                                "text": r["text"],
                            }
                        )
            else:
                offset = (page_num - 1) * 50
                rows_in_page = rows[offset : offset + 50]
                for r in rows_in_page:
                    marker = (
                        str(r["marker"] or "").strip()
                        if has_marker and r["marker"]
                        else f"§{r['paragraph_no']}"
                    )
                    out.append(
                        {
                            "paragraph_no": r["paragraph_no"],
                            "para_id": marker,
                            "marker": marker,
                            "ref": r["ref"],
                            "text": r["text"],
                        }
                    )

            return out

    def search_expose(
        self, query: str, translator: str = "VGR", limit: int = 100
    ) -> list[dict[str, Any]]:
        prefix = "BK-AGES" if translator.upper() == "VGR" else "BK-AGES-SHP"
        out = []
        with self._db.connect() as conn:
            has_marker = self._has_column(conn, "sermon_paragraph", "marker")
            has_canonical_title = self._has_column(conn, "sermon", "canonical_title")
            title_expr = self._title_expr(has_canonical_title)
            marker_expr = "COALESCE(NULLIF(p.marker, ''), p.ref, '')" if has_marker else "p.ref"
            sql = f"""
                SELECT p.sermon_id, p.paragraph_no, p.ref, p.text,
                       {marker_expr} AS marker,
                       {title_expr} AS title,
                       s.date
                FROM sermon_paragraph p
                JOIN sermon s ON s.id = p.sermon_id
                WHERE s.date LIKE ? AND s.tradition = ? AND unaccent(p.text) LIKE unaccent(?)
                ORDER BY s.date, p.paragraph_no
                LIMIT ?
            """
            rows = conn.execute(
                sql, (f"{prefix}-%", translator.upper(), f"%{query.strip()}%", limit)
            ).fetchall()
            for r in rows:
                marker = str(r["marker"] or "").strip() or self._get_marker(
                    r["ref"], r["paragraph_no"]
                )
                ref = self._format_reference(r["date"], r["title"], marker)
                out.append(
                    {
                        "id": f"int_p_{r['sermon_id']}_{r['paragraph_no']}",
                        "sermon_id": f"int_{r['sermon_id']}",
                        "paragraph_no": r["paragraph_no"],
                        "para_id": marker,
                        "marker": marker,
                        "ref": ref,
                        "reference": ref,
                        "raw_ref": r["ref"],
                        "text": r["text"],
                        "title": r["title"],
                    }
                )
            return out
