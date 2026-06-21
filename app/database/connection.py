from __future__ import annotations

import contextlib
import html
import json
import re
import sqlite3
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.utils.app_paths import app_db_path, bible_json_dir, resource_root


@dataclass(frozen=True)
class DatabaseConfig:
    db_path: Path


class Database:
    _HTML_TAG_RE = re.compile(r"<[^>]+>")
    _STARTUP_MAINTENANCE_KEY = "startup_maintenance_version"
    _STARTUP_MAINTENANCE_VERSION = "8"
    _VACUUM_KEY = "vacuum_version"
    _VACUUM_VERSION = "2"

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config

    @property
    def db_path(self) -> Path:
        return self._config.db_path

    @staticmethod
    def project_root() -> Path:
        return resource_root()

    @classmethod
    def default(cls) -> Database:
        return cls(DatabaseConfig(db_path=app_db_path()))

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with self.connect() as conn:
            self._ensure_app_meta_table(conn)
            current_version = self._get_user_version(conn)
            if current_version == 0:
                self._apply_migration_v1(conn)
                self._set_user_version(conn, 1)
                current_version = 1
            if current_version < 2:
                self._apply_migration_v2(conn)
                self._set_user_version(conn, 2)
                current_version = 2
            if current_version < 3:
                self._apply_migration_v3(conn)
                self._set_user_version(conn, 3)
                current_version = 3
            if current_version < 4:
                self._apply_migration_v4(conn)
                self._set_user_version(conn, 4)
                current_version = 4
            if current_version < 5:
                self._apply_migration_v5(conn)
                self._set_user_version(conn, 5)
                current_version = 5
            if current_version < 6:
                self._apply_migration_v6(conn)
                self._set_user_version(conn, 6)
                current_version = 6
            if current_version < 7:
                self._apply_migration_v7(conn)
                self._set_user_version(conn, 7)
                current_version = 7
            self._ensure_playlist_tables(conn)
            # Cheap and idempotent: drop dead weight indexes on every launch.
            indexes_dropped = self._drop_obsolete_indexes(conn)
            maintenance_ran = False
            if self._startup_maintenance_needed(conn):
                self._ensure_sermon_search_metadata(conn)
                self._ensure_hymn_search_metadata(conn)
                self._seed_demo_data_if_empty(conn)
                self._import_bible_json_translations(conn)
                self._set_app_meta(
                    conn,
                    self._STARTUP_MAINTENANCE_KEY,
                    self._STARTUP_MAINTENANCE_VERSION,
                )
                maintenance_ran = True
            vacuum_needed = (
                (maintenance_ran or indexes_dropped)
                and self._get_app_meta(conn, self._VACUUM_KEY) != self._VACUUM_VERSION
            )

        # VACUUM must run outside the transaction above; it reclaims the large
        # amount of free space freed when the heavy FTS index is rebuilt.
        if vacuum_needed:
            self._reclaim_space()
            with self.connect() as conn:
                self._set_app_meta(conn, self._VACUUM_KEY, self._VACUUM_VERSION)

    # Plain B-tree indexes over full text columns. They cannot serve the only
    # text queries the app issues (`unaccent(text) LIKE '%q%'`, handled by FTS),
    # so they just duplicate the text on disk. Dropping them reclaims ~600 MB.
    _OBSOLETE_INDEXES = (
        "idx_sermon_paragraph_text",
        "idx_bible_translation_verse_text",
        "idx_bible_verse_text",
        "idx_hymn_stanza_text",
    )

    def _drop_obsolete_indexes(self, conn: sqlite3.Connection) -> bool:
        """Drop the dead text indexes if present. Returns True if any existed."""
        dropped = False
        for name in self._OBSOLETE_INDEXES:
            try:
                exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
                    (name,),
                ).fetchone()
                if exists:
                    conn.execute(f"DROP INDEX IF EXISTS {name}")
                    dropped = True
            except sqlite3.Error:
                pass
        return dropped

    def _reclaim_space(self) -> None:
        """Checkpoint the WAL and compact the database file on disk."""
        conn = sqlite3.connect(self.db_path, timeout=60.0, isolation_level=None)
        try:
            conn.execute("PRAGMA busy_timeout = 60000;")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            conn.execute("VACUUM;")
        except sqlite3.Error:
            pass
        finally:
            conn.close()

    @contextlib.contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        from app.utils.text_utils import unaccent

        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.row_factory = sqlite3.Row
            conn.create_function("unaccent", 1, unaccent)
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA busy_timeout = 30000;")
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA temp_store = MEMORY;")
            conn.execute("PRAGMA cache_size = -64000;")
            conn.execute("PRAGMA mmap_size = 268435456;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _get_user_version(conn: sqlite3.Connection) -> int:
        row = conn.execute("PRAGMA user_version;").fetchone()
        return int(row[0]) if row is not None else 0

    @staticmethod
    def _set_user_version(conn: sqlite3.Connection, version: int) -> None:
        conn.execute(f"PRAGMA user_version = {int(version)};")

    @staticmethod
    def _ensure_app_meta_table(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

    @staticmethod
    def _get_app_meta(conn: sqlite3.Connection, key: str) -> str | None:
        try:
            row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
        except sqlite3.Error:
            return None
        return str(row[0]) if row is not None else None

    @staticmethod
    def _set_app_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
        conn.execute(
            """
            INSERT INTO app_meta (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )

    def _startup_maintenance_needed(self, conn: sqlite3.Connection) -> bool:
        current = self._get_app_meta(conn, self._STARTUP_MAINTENANCE_KEY)
        if current == self._STARTUP_MAINTENANCE_VERSION:
            return False

        if self._startup_data_already_ready(conn):
            self._set_app_meta(
                conn,
                self._STARTUP_MAINTENANCE_KEY,
                self._STARTUP_MAINTENANCE_VERSION,
            )
            return False

        return True

    def _startup_data_already_ready(self, conn: sqlite3.Connection) -> bool:
        try:
            sermon_count = int(
                conn.execute("SELECT COUNT(*) FROM sermon_paragraph").fetchone()[0] or 0
            )
            sermon_fts_count = int(
                conn.execute("SELECT COUNT(*) FROM sermon_paragraph_fts").fetchone()[0]
                or 0
            )
            hymn_count = int(
                conn.execute("SELECT COUNT(*) FROM hymn_stanza").fetchone()[0] or 0
            )
            hymn_fts_count = int(
                conn.execute("SELECT COUNT(*) FROM hymn_stanza_fts").fetchone()[0] or 0
            )
            bible_translation_count = int(
                conn.execute("SELECT COUNT(*) FROM bible_translation_verse").fetchone()[0]
                or 0
            )
            missing_sermon_meta = conn.execute(
                """
                SELECT 1
                FROM sermon
                WHERE canonical_title IS NULL
                   OR canonical_title = ''
                   OR title_search IS NULL
                   OR title_search = ''
                LIMIT 1
                """
            ).fetchone()
            missing_hymn_meta = conn.execute(
                """
                SELECT 1
                FROM hymn
                WHERE canonical_title IS NULL
                   OR canonical_title = ''
                   OR title_search IS NULL
                   OR title_search = ''
                LIMIT 1
                """
            ).fetchone()
            missing_markers = conn.execute(
                """
                SELECT 1
                FROM sermon_paragraph
                WHERE marker IS NULL OR marker = ''
                LIMIT 1
                """
            ).fetchone()
            missing_labels = conn.execute(
                """
                SELECT 1
                FROM hymn_stanza
                WHERE label IS NULL OR label = ''
                LIMIT 1
                """
            ).fetchone()
        except sqlite3.Error:
            return False

        return (
            sermon_count > 0
            and sermon_count == sermon_fts_count
            and hymn_count > 0
            and hymn_count == hymn_fts_count
            and bible_translation_count > 0
            and missing_sermon_meta is None
            and missing_hymn_meta is None
            and missing_markers is None
            and missing_labels is None
        )

    def _apply_migration_v1(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bible_book (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                abbreviation TEXT,
                testament TEXT,
                sort_order INTEGER
            );

            CREATE TABLE IF NOT EXISTS bible_verse (
                id INTEGER PRIMARY KEY,
                book_id INTEGER NOT NULL,
                chapter INTEGER NOT NULL,
                verse INTEGER NOT NULL,
                text TEXT NOT NULL,
                FOREIGN KEY (book_id) REFERENCES bible_book (id) ON DELETE CASCADE,
                UNIQUE (book_id, chapter, verse)
            );

            CREATE INDEX IF NOT EXISTS idx_bible_verse_book_chapter
                ON bible_verse (book_id, chapter);


            CREATE TABLE IF NOT EXISTS sermon (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                date TEXT,
                tradition TEXT NOT NULL,
                language TEXT,
                source_path TEXT,
                sort_key TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_sermon_tradition
                ON sermon (tradition);

            CREATE INDEX IF NOT EXISTS idx_sermon_sort
                ON sermon (sort_key, date);


            CREATE TABLE IF NOT EXISTS sermon_paragraph (
                id INTEGER PRIMARY KEY,
                sermon_id INTEGER NOT NULL,
                paragraph_no INTEGER NOT NULL,
                ref TEXT,
                text TEXT NOT NULL,
                FOREIGN KEY (sermon_id) REFERENCES sermon (id) ON DELETE CASCADE,
                UNIQUE (sermon_id, paragraph_no)
            );

            CREATE INDEX IF NOT EXISTS idx_sermon_paragraph_sermon
                ON sermon_paragraph (sermon_id, paragraph_no);


            CREATE TABLE IF NOT EXISTS hymn (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                number TEXT,
                language TEXT,
                sort_key TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_hymn_sort
                ON hymn (sort_key, number);


            CREATE TABLE IF NOT EXISTS hymn_stanza (
                id INTEGER PRIMARY KEY,
                hymn_id INTEGER NOT NULL,
                stanza_no INTEGER NOT NULL,
                text TEXT NOT NULL,
                FOREIGN KEY (hymn_id) REFERENCES hymn (id) ON DELETE CASCADE,
                UNIQUE (hymn_id, stanza_no)
            );

            CREATE INDEX IF NOT EXISTS idx_hymn_stanza_hymn
                ON hymn_stanza (hymn_id, stanza_no);
            """,
        )

    @classmethod
    def _clean_text(cls, value: Any) -> str:
        s = str(value or "")
        s = html.unescape(s)
        s = s.replace("\ufeff", "").replace("\u200b", "")
        s = s.replace("\ufffd", "")
        s = s.replace("\u00a0", " ").replace("\u202f", " ")
        s = s.replace("Â ", " ").replace("Â\u00a0", " ")
        s = s.replace("\r", "")
        s = s.replace("<br/>", "\n").replace("<br />", "\n").replace("<br>", "\n")
        s = s.replace("&nbsp;", " ")
        s = cls._HTML_TAG_RE.sub("", s)
        s = re.sub(r"(^|\n)\s*¶\s*", r"\1", s)
        s = s.replace("¶", "")
        s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", s)
        s = re.sub(r"[\t ]+", " ", s)
        s = s.strip()
        return s

    @staticmethod
    def _sqlite_tables(conn: sqlite3.Connection) -> list[str]:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """,
        ).fetchall()
        return [str(r[0]) for r in rows]

    @staticmethod
    def _sqlite_text_columns(
        conn: sqlite3.Connection, table: str
    ) -> tuple[str | None, list[str]]:
        cols = conn.execute(
            f"PRAGMA table_info({Database._quote_ident(table)})"
        ).fetchall()
        pk_col: str | None = None
        text_cols: list[str] = []
        for c in cols:
            name = str(c[1])
            col_type = str(c[2] or "").upper()
            is_pk = int(c[5] or 0) > 0
            if is_pk and pk_col is None:
                pk_col = name
            if "TEXT" in col_type or "CHAR" in col_type or "CLOB" in col_type:
                text_cols.append(name)
        return pk_col, text_cols

    def sanitize_project_db_texts(self, dry_run: bool = True) -> dict[str, int]:
        summary: dict[str, int] = {}
        with self.connect() as conn:
            tables = self._sqlite_tables(conn)
            for t in tables:
                pk_col, text_cols = self._sqlite_text_columns(conn, t)
                if pk_col is None or not text_cols:
                    continue

                pk_q = self._quote_ident(pk_col)
                cols_q = ", ".join(self._quote_ident(c) for c in text_cols)
                rows = conn.execute(
                    f"SELECT {pk_q}, {cols_q} FROM {self._quote_ident(t)}"
                ).fetchall()
                if not rows:
                    continue

                changed = 0
                for r in rows:
                    pk = r[0]
                    new_vals: list[str] = []
                    is_changed = False
                    for i, col in enumerate(text_cols, start=1):
                        original = r[i]
                        cleaned = self._clean_text(original)
                        if (original is None and cleaned != "") or (
                            original is not None and str(original) != cleaned
                        ):
                            is_changed = True
                        new_vals.append(cleaned)

                    if not is_changed:
                        continue
                    changed += 1
                    if not dry_run:
                        set_sql = ", ".join(
                            f"{self._quote_ident(c)} = ?" for c in text_cols
                        )
                        conn.execute(
                            f"UPDATE {self._quote_ident(t)} SET {set_sql} WHERE {pk_q} = ?",
                            tuple(new_vals + [pk]),
                        )
                if changed:
                    summary[t] = changed
        return summary

    def _apply_migration_v2(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bible_translation (
                id INTEGER PRIMARY KEY,
                module TEXT NOT NULL UNIQUE,
                name TEXT,
                shortname TEXT,
                lang TEXT
            );

            CREATE TABLE IF NOT EXISTS bible_translation_verse (
                id INTEGER PRIMARY KEY,
                translation_id INTEGER NOT NULL,
                book INTEGER NOT NULL,
                book_name TEXT,
                chapter INTEGER NOT NULL,
                verse INTEGER NOT NULL,
                text TEXT NOT NULL,
                FOREIGN KEY (translation_id) REFERENCES bible_translation (id) ON DELETE CASCADE,
                UNIQUE (translation_id, book, chapter, verse)
            );

            CREATE INDEX IF NOT EXISTS idx_bible_translation_verse_ref
                ON bible_translation_verse (translation_id, book, chapter);
            """,
        )

    def _apply_migration_v4(self, conn: sqlite3.Connection) -> None:
        """Ajoute la colonne location a la table sermon (si absente)."""
        cols = [r[1] for r in conn.execute("PRAGMA table_info(sermon)").fetchall()]
        if "location" not in cols:
            conn.execute("ALTER TABLE sermon ADD COLUMN location TEXT DEFAULT ''")
        if "sort_key" not in cols:
            conn.execute("ALTER TABLE sermon ADD COLUMN sort_key TEXT DEFAULT ''")

    def _apply_migration_v5(self, conn: sqlite3.Connection) -> None:
        """Ajoute les metadonnees de recherche/titres sans modifier les originaux."""
        sermon_cols = [r[1] for r in conn.execute("PRAGMA table_info(sermon)").fetchall()]
        if "canonical_title" not in sermon_cols:
            conn.execute("ALTER TABLE sermon ADD COLUMN canonical_title TEXT DEFAULT ''")
        if "title_search" not in sermon_cols:
            conn.execute("ALTER TABLE sermon ADD COLUMN title_search TEXT DEFAULT ''")

        para_cols = [
            r[1] for r in conn.execute("PRAGMA table_info(sermon_paragraph)").fetchall()
        ]
        if "marker" not in para_cols:
            conn.execute("ALTER TABLE sermon_paragraph ADD COLUMN marker TEXT DEFAULT ''")

        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_sermon_lang_trad_date
                ON sermon (language, tradition, date);
            CREATE INDEX IF NOT EXISTS idx_sermon_date_lang
                ON sermon (date, language);
            CREATE INDEX IF NOT EXISTS idx_sermon_canonical_title
                ON sermon (canonical_title);
            CREATE INDEX IF NOT EXISTS idx_sermon_title_search
                ON sermon (title_search);
            CREATE INDEX IF NOT EXISTS idx_sermon_paragraph_marker
                ON sermon_paragraph (sermon_id, marker);
            """
        )

    def _ensure_sermon_search_metadata(self, conn: sqlite3.Connection) -> None:
        """Maintient les titres canoniques, marqueurs et index de recherche."""
        self._ensure_sermon_title_metadata(conn)
        self._ensure_sermon_paragraph_markers(conn)
        self._ensure_sermon_fts(conn)

    @classmethod
    def _search_key(cls, value: Any) -> str:
        text = cls._clean_text(value).lower()
        normalized = unicodedata.normalize("NFD", text)
        text = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def _clean_sermon_title_for_canonical(cls, title: Any) -> str:
        text = cls._clean_text(title)
        text = re.sub(r"\s*-\s*[A-Z][A-Z' .-]+(?:\s+[A-Z]{2})?\s+USA\s*$", "", text)
        text = re.sub(r"\s*-\s*[A-Z][A-Z' .-]+\s+[A-Z]{2,}\s*$", "", text)
        text = re.sub(r"\s+", " ", text).strip(" -")
        if text.isupper():
            small_words = {
                "a",
                "au",
                "aux",
                "avec",
                "ce",
                "ces",
                "de",
                "des",
                "du",
                "en",
                "et",
                "la",
                "le",
                "les",
                "pour",
                "que",
                "qui",
                "sur",
                "un",
                "une",
            }
            parts = []
            for i, word in enumerate(text.lower().split()):
                parts.append(word if i > 0 and word in small_words else word.capitalize())
            text = " ".join(parts)
        return text

    @classmethod
    def _choose_canonical_title(cls, rows: list[sqlite3.Row]) -> str:
        def score(row: sqlite3.Row) -> tuple[int, int, int]:
            title = cls._clean_sermon_title_for_canonical(row["title"])
            trad = str(row["tradition"] or "").upper()
            generic = 1 if re.match(r"^(SERMON|MESSAGE)\s+\d+", title, re.I) else 0
            priority = {"VGR": 0, "BSS": 1, "SHP": 2}.get(trad, 3)
            return (generic, priority, len(title))

        best = sorted(rows, key=score)[0]
        return cls._clean_sermon_title_for_canonical(best["title"])

    def _ensure_sermon_title_metadata(self, conn: sqlite3.Connection) -> None:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(sermon)").fetchall()]
        if "canonical_title" not in cols or "title_search" not in cols:
            return

        grouped: dict[tuple[str, str], list[sqlite3.Row]] = {}
        rows = conn.execute(
            """
            SELECT id, date, title, tradition, language, canonical_title, title_search
            FROM sermon
            """
        ).fetchall()
        for row in rows:
            date = str(row["date"] or "").strip()
            language = str(row["language"] or "").strip().lower()
            key = (date, language) if date else (f"id:{row['id']}", language)
            grouped.setdefault(key, []).append(row)

        updates: list[tuple[str, str, int]] = []
        for items in grouped.values():
            canonical = self._choose_canonical_title(items)
            for row in items:
                search_parts = [
                    canonical,
                    row["title"],
                    row["date"],
                    row["tradition"],
                    row["language"],
                ]
                title_search = self._search_key(" ".join(str(p or "") for p in search_parts))
                if (
                    str(row["canonical_title"] or "") != canonical
                    or str(row["title_search"] or "") != title_search
                ):
                    updates.append((canonical, title_search, int(row["id"])))

        if updates:
            conn.executemany(
                "UPDATE sermon SET canonical_title = ?, title_search = ? WHERE id = ?",
                updates,
            )

    @staticmethod
    def _marker_from_ref(ref: Any, paragraph_no: int) -> str:
        value = str(ref or "").replace("Â¶", "¶").replace("Â§", "§").strip()
        match = re.search(r"([A-Z]-[A-Z0-9]+)\s*$", value)
        if match:
            return match.group(1).replace("O", "0")
        match = re.search(r"([¶§]\s*\d+)\s*$", value)
        if match:
            return re.sub(r"\s+", "", match.group(1))
        match = re.search(r"(\d+)-(\d+)\s*$", value)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
        return f"¶{int(paragraph_no)}"

    def _ensure_sermon_paragraph_markers(self, conn: sqlite3.Connection) -> None:
        cols = [
            r[1] for r in conn.execute("PRAGMA table_info(sermon_paragraph)").fetchall()
        ]
        if "marker" not in cols:
            return

        rows = conn.execute(
            """
            SELECT id, paragraph_no, ref, marker
            FROM sermon_paragraph
            WHERE marker IS NULL OR marker = '' OR marker LIKE '%Â%' OR marker LIKE '%Ã%'
            """
        ).fetchall()
        updates = [
            (self._marker_from_ref(r["ref"], int(r["paragraph_no"])), int(r["id"]))
            for r in rows
        ]
        if updates:
            conn.executemany(
                "UPDATE sermon_paragraph SET marker = ? WHERE id = ?", updates
            )

    # Contentless (content='') + detail=none keeps the FTS index tiny: it stores
    # no copy of the text and no token positions. Search only needs MATCH + rowid
    # and bm25() ranking, all of which work in this mode. This shrinks the sermon
    # index from ~920 MB to ~45 MB.
    _SERMON_FTS_DDL = (
        "CREATE VIRTUAL TABLE sermon_paragraph_fts USING fts5("
        "text, ref, sermon_title, canonical_title, "
        "content='', detail=none, "
        "tokenize='unicode61 remove_diacritics 2')"
    )

    def _ensure_sermon_fts(self, conn: sqlite3.Connection) -> None:
        try:
            existing = conn.execute(
                """
                SELECT sql FROM sqlite_master
                WHERE type = 'table' AND name = 'sermon_paragraph_fts'
                """
            ).fetchone()
            existing_sql = str(existing[0] or "").lower() if existing else ""
            # Rebuild whenever the on-disk schema is not the compact one.
            if existing and "detail=none" not in existing_sql:
                conn.execute("DROP TABLE sermon_paragraph_fts")
                existing = None
            if existing is None:
                conn.execute(self._SERMON_FTS_DDL)
        except sqlite3.Error:
            return

        fts_count = conn.execute(
            "SELECT COUNT(*) FROM sermon_paragraph_fts"
        ).fetchone()[0]
        para_count = conn.execute("SELECT COUNT(*) FROM sermon_paragraph").fetchone()[0]
        if int(fts_count or 0) == int(para_count or 0) and int(para_count or 0) > 0:
            return

        # Contentless FTS5 forbids plain DELETE, so re-create to clear stale rows.
        conn.execute("DROP TABLE IF EXISTS sermon_paragraph_fts")
        conn.execute(self._SERMON_FTS_DDL)
        conn.execute(
            """
            INSERT INTO sermon_paragraph_fts
                (rowid, text, ref, sermon_title, canonical_title)
            SELECT
                p.id,
                p.text,
                COALESCE(p.ref, ''),
                s.title,
                COALESCE(NULLIF(s.canonical_title, ''), s.title)
            FROM sermon_paragraph p
            JOIN sermon s ON s.id = p.sermon_id
            """
        )

    def _apply_migration_v6(self, conn: sqlite3.Connection) -> None:
        """Ajoute les metadonnees de recherche des cantiques sans modifier les originaux."""
        hymn_cols = [r[1] for r in conn.execute("PRAGMA table_info(hymn)").fetchall()]
        if "canonical_title" not in hymn_cols:
            conn.execute("ALTER TABLE hymn ADD COLUMN canonical_title TEXT DEFAULT ''")
        if "title_search" not in hymn_cols:
            conn.execute("ALTER TABLE hymn ADD COLUMN title_search TEXT DEFAULT ''")

        stanza_cols = [
            r[1] for r in conn.execute("PRAGMA table_info(hymn_stanza)").fetchall()
        ]
        if "label" not in stanza_cols:
            conn.execute("ALTER TABLE hymn_stanza ADD COLUMN label TEXT DEFAULT ''")
        if "is_chorus" not in stanza_cols:
            conn.execute("ALTER TABLE hymn_stanza ADD COLUMN is_chorus INTEGER DEFAULT 0")

        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_hymn_language_sort
                ON hymn (language, sort_key, number);
            CREATE INDEX IF NOT EXISTS idx_hymn_title_search
                ON hymn (title_search);
            CREATE INDEX IF NOT EXISTS idx_hymn_canonical_title
                ON hymn (canonical_title);
            CREATE INDEX IF NOT EXISTS idx_hymn_stanza_label
                ON hymn_stanza (hymn_id, label);
            """
        )

    def _ensure_hymn_search_metadata(self, conn: sqlite3.Connection) -> None:
        self._ensure_hymn_title_metadata(conn)
        self._ensure_hymn_stanza_labels(conn)
        self._ensure_hymn_fts(conn)

    @classmethod
    def _clean_hymn_title_for_canonical(cls, title: Any) -> str:
        text = cls._clean_text(title)
        text = re.sub(r"\s+", " ", text).strip(" -")
        if text.isupper():
            small_words = {
                "a",
                "au",
                "aux",
                "avec",
                "ce",
                "ces",
                "de",
                "des",
                "du",
                "en",
                "et",
                "la",
                "le",
                "les",
                "pour",
                "que",
                "qui",
                "sur",
                "un",
                "une",
            }
            parts = []
            for i, word in enumerate(text.lower().split()):
                parts.append(word if i > 0 and word in small_words else word.capitalize())
            text = " ".join(parts)
        return text

    def _ensure_hymn_title_metadata(self, conn: sqlite3.Connection) -> None:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(hymn)").fetchall()]
        if "canonical_title" not in cols or "title_search" not in cols:
            return

        rows = conn.execute(
            """
            SELECT id, title, number, language, canonical_title, title_search
            FROM hymn
            """
        ).fetchall()
        updates: list[tuple[str, str, int]] = []
        for row in rows:
            canonical = self._clean_hymn_title_for_canonical(row["title"])
            search_parts = [
                canonical,
                row["title"],
                row["number"],
                row["language"],
            ]
            title_search = self._search_key(" ".join(str(p or "") for p in search_parts))
            if (
                str(row["canonical_title"] or "") != canonical
                or str(row["title_search"] or "") != title_search
            ):
                updates.append((canonical, title_search, int(row["id"])))

        if updates:
            conn.executemany(
                "UPDATE hymn SET canonical_title = ?, title_search = ? WHERE id = ?",
                updates,
            )

    @staticmethod
    def _detect_hymn_chorus(text: Any) -> bool:
        stripped = str(text or "").strip()
        return bool(
            re.match(
                r"^(?:Dernier\s+)?(Chœur|Choeur|Refrain|Chorus)\s*[:.\-–—]?",
                stripped,
                re.IGNORECASE,
            )
        )

    def _ensure_hymn_stanza_labels(self, conn: sqlite3.Connection) -> None:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(hymn_stanza)").fetchall()]
        if "label" not in cols or "is_chorus" not in cols:
            return

        rows = conn.execute(
            """
            SELECT id, hymn_id, stanza_no, text, label, is_chorus
            FROM hymn_stanza
            ORDER BY hymn_id, stanza_no
            """
        ).fetchall()
        updates: list[tuple[str, int, int]] = []
        current_hymn: int | None = None
        verse_no = 0
        chorus_no = 0
        for row in rows:
            hymn_id = int(row["hymn_id"])
            if hymn_id != current_hymn:
                current_hymn = hymn_id
                verse_no = 0
                chorus_no = 0
            is_chorus = self._detect_hymn_chorus(row["text"])
            if is_chorus:
                chorus_no += 1
                label = "Refrain" if chorus_no == 1 else f"Refrain {chorus_no}"
            else:
                verse_no += 1
                label = f"Strophe {verse_no}"
            chorus_value = 1 if is_chorus else 0
            if str(row["label"] or "") != label or int(row["is_chorus"] or 0) != chorus_value:
                updates.append((label, chorus_value, int(row["id"])))

        if updates:
            conn.executemany(
                "UPDATE hymn_stanza SET label = ?, is_chorus = ? WHERE id = ?",
                updates,
            )

    _HYMN_FTS_DDL = (
        "CREATE VIRTUAL TABLE hymn_stanza_fts USING fts5("
        "text, hymn_title, hymn_number, label, "
        "content='', detail=none, "
        "tokenize='unicode61 remove_diacritics 2')"
    )

    def _ensure_hymn_fts(self, conn: sqlite3.Connection) -> None:
        try:
            existing = conn.execute(
                """
                SELECT sql FROM sqlite_master
                WHERE type = 'table' AND name = 'hymn_stanza_fts'
                """
            ).fetchone()
            existing_sql = str(existing[0] or "").lower() if existing else ""
            if existing and "detail=none" not in existing_sql:
                conn.execute("DROP TABLE hymn_stanza_fts")
                existing = None
            if existing is None:
                conn.execute(self._HYMN_FTS_DDL)
        except sqlite3.Error:
            return

        fts_count = conn.execute("SELECT COUNT(*) FROM hymn_stanza_fts").fetchone()[0]
        stanza_count = conn.execute("SELECT COUNT(*) FROM hymn_stanza").fetchone()[0]
        if int(fts_count or 0) == int(stanza_count or 0) and int(stanza_count or 0) > 0:
            return

        # Contentless FTS5 forbids plain DELETE, so re-create to clear stale rows.
        conn.execute("DROP TABLE IF EXISTS hymn_stanza_fts")
        conn.execute(self._HYMN_FTS_DDL)
        conn.execute(
            """
            INSERT INTO hymn_stanza_fts
                (rowid, text, hymn_title, hymn_number, label)
            SELECT
                hs.id,
                hs.text,
                COALESCE(NULLIF(h.canonical_title, ''), h.title),
                COALESCE(h.number, ''),
                COALESCE(NULLIF(hs.label, ''), 'Strophe ' || hs.stanza_no)
            FROM hymn_stanza hs
            JOIN hymn h ON h.id = hs.hymn_id
            """
        )

    def _apply_migration_v3(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS playlist_folder (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_playlist_folder_sort
                ON playlist_folder (sort_order);

            CREATE TABLE IF NOT EXISTS playlist_item (
                id INTEGER PRIMARY KEY,
                folder_id INTEGER,
                source TEXT NOT NULL,
                reference TEXT NOT NULL,
                text TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (folder_id) REFERENCES playlist_folder (id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_playlist_item_folder
                ON playlist_item (folder_id, sort_order);
            """,
        )

    def _apply_migration_v7(self, conn: sqlite3.Connection) -> None:
        """Add background column to playlist_item for per-slide background images."""
        cols = [r[1] for r in conn.execute("PRAGMA table_info(playlist_item)").fetchall()]
        if "background" not in cols:
            conn.execute("ALTER TABLE playlist_item ADD COLUMN background TEXT DEFAULT ''")

    def _ensure_playlist_tables(self, conn: sqlite3.Connection) -> None:
        """S'assure que les tables playlist existent (pour les bases existantes)."""
        self._apply_migration_v3(conn)

    def _import_bible_json_translations(self, conn: sqlite3.Connection) -> None:
        json_dir = bible_json_dir()
        if not json_dir.exists() or not json_dir.is_dir():
            return

        for json_path in sorted(json_dir.glob("*.json")):
            try:
                with json_path.open("r", encoding="utf-8") as f:
                    payload = json.load(f)
            except Exception:
                continue

            metadata = payload.get("metadata") if isinstance(payload, dict) else None
            if not isinstance(metadata, dict):
                continue

            module = metadata.get("module")
            if not module:
                module = json_path.stem

            name = optional_str(metadata.get("name"))
            shortname = optional_str(metadata.get("shortname"))
            lang = optional_str(metadata.get("lang_short") or metadata.get("lang"))

            conn.execute(
                "INSERT OR IGNORE INTO bible_translation (module, name, shortname, lang) VALUES (?, ?, ?, ?)",
                (str(module), name, shortname, lang),
            )
            row = conn.execute(
                "SELECT id FROM bible_translation WHERE module = ?",
                (str(module),),
            ).fetchone()
            if row is None:
                continue
            translation_id = int(row[0])

            verses = payload.get("verses") if isinstance(payload, dict) else None
            if not isinstance(verses, list) or not verses:
                continue

            batch: list[tuple[int, int, str | None, int, int, str]] = []
            for v in verses:
                if not isinstance(v, dict):
                    continue
                try:
                    book = int(v.get("book"))
                    chapter = int(v.get("chapter"))
                    verse_no = int(v.get("verse"))
                    text = self._clean_text(str(v.get("text") or ""))
                except Exception:
                    continue
                if not text:
                    continue

                book_name = optional_str(v.get("book_name"))
                batch.append((translation_id, book, book_name, chapter, verse_no, text))

                if len(batch) >= 2000:
                    conn.executemany(
                        """
                        INSERT OR IGNORE INTO bible_translation_verse
                            (translation_id, book, book_name, chapter, verse, text)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        batch,
                    )
                    batch.clear()

            if batch:
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO bible_translation_verse
                        (translation_id, book, book_name, chapter, verse, text)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    batch,
                )

    @staticmethod
    def _quote_ident(name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    def _seed_demo_data_if_empty(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT COUNT(1) FROM bible_book;").fetchone()
        has_bible = int(row[0]) > 0 if row is not None else False

        row = conn.execute("SELECT COUNT(1) FROM hymn;").fetchone()
        has_hymns = int(row[0]) > 0 if row is not None else False

        row = conn.execute("SELECT COUNT(1) FROM sermon;").fetchone()
        has_sermons = int(row[0]) > 0 if row is not None else False

        if not has_bible:
            conn.executemany(
                "INSERT INTO bible_book (id, name, abbreviation, testament, sort_order) VALUES (?, ?, ?, ?, ?)",
                [
                    (1, "Genèse", "Gn", "OT", 1),
                    (2, "Exode", "Ex", "OT", 2),
                    (3, "Jean", "Jn", "NT", 43),
                ],
            )

            conn.executemany(
                "INSERT INTO bible_verse (book_id, chapter, verse, text) VALUES (?, ?, ?, ?)",
                [
                    (1, 1, 1, "Au commencement, Dieu créa les cieux et la terre."),
                    (
                        1,
                        1,
                        2,
                        "La terre était informe et vide: il y avait des ténèbres à la surface de l'abîme, et l'Esprit de Dieu se mouvait au-dessus des eaux.",
                    ),
                    (1, 1, 3, "Dieu dit: Que la lumière soit! Et la lumière fut."),
                    (
                        2,
                        3,
                        14,
                        "Dieu dit à Moïse: Je suis celui qui suis. Et il ajouta: C'est ainsi que tu répondras aux enfants d'Israël: Celui qui s'appelle “je suis” m'a envoyé vers vous.",
                    ),
                    (
                        3,
                        3,
                        16,
                        "Car Dieu a tant aimé le monde qu'il a donné son Fils unique, afin que quiconque croit en lui ne périsse point, mais qu'il ait la vie éternelle.",
                    ),
                ],
            )

        if not has_hymns:
            conn.execute(
                "INSERT INTO hymn (id, title, number, language, sort_key) VALUES (?, ?, ?, ?, ?)",
                (1, "Je veux chanter", "1", "fr", "0001"),
            )
            conn.executemany(
                "INSERT INTO hymn_stanza (hymn_id, stanza_no, text) VALUES (?, ?, ?)",
                [
                    (
                        1,
                        1,
                        "Je veux chanter, louer mon Roi,\nCar Il est bon et fidèle.",
                    ),
                    (1, 2, "Sa grâce m'a relevé,\nSon amour m'a délivré."),
                ],
            )

        if not has_sermons:
            conn.execute(
                "INSERT INTO sermon (id, title, date, tradition, language, source_path, sort_key) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (1, "La Foi", "1953-09-12", "VGR", "fr", "", "0001"),
            )
            conn.executemany(
                "INSERT INTO sermon_paragraph (sermon_id, paragraph_no, ref, text) VALUES (?, ?, ?, ?)",
                [
                    (
                        1,
                        1,
                        "La Foi ¶1",
                        "La foi est une substance des choses qu'on espère, une démonstration de celles qu'on ne voit pas.",
                    ),
                    (
                        1,
                        2,
                        "La Foi ¶2",
                        "Elle prend Dieu au mot et marche comme si la promesse était déjà accomplie.",
                    ),
                ],
            )


def optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
