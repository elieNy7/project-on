from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.import_cantique_adoration_folder import (
    DEFAULT_CACHE,
    DEFAULT_DB,
    DEFAULT_FOLDER,
    iter_folder_files,
    parse_cantique_file,
)
from app.utils.pptx_parser import _post_process_stanzas


@dataclass
class RepairStats:
    db_hymns: int = 0
    source_hymns: int = 0
    matched: int = 0
    changed: int = 0
    unchanged: int = 0
    missing_source: int = 0
    failed_source: int = 0


def normalize_key(value: object) -> str:
    text = str(value or "").replace("\u2019", "'").replace("`", "'")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_text(value: object) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u202f", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        is not None
    )


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def detect_chorus(text: str) -> bool:
    return bool(
        re.match(
            r"^(?:Dernier\s+)?(Ch\u0153ur|Choeur|Refrain|Chorus)\s*[:.\-–—]?",
            str(text or "").strip(),
            re.IGNORECASE,
        )
    )


def stanza_label(text: str, verse_no: int, chorus_no: int) -> tuple[str, bool]:
    if detect_chorus(text):
        label = "Refrain" if chorus_no <= 1 else f"Refrain {chorus_no}"
        return label, True
    return f"Strophe {verse_no}", False


def load_source_hymns(
    folder: Path,
    cache_dir: Path,
    recursive: bool,
    wanted_keys: set[str],
) -> tuple[dict[str, dict[str, Any]], int]:
    parsed: dict[str, dict[str, Any]] = {}
    failed = 0
    for path in iter_folder_files(folder, recursive=recursive):
        if normalize_key(path.stem) not in wanted_keys:
            continue
        hymn = parse_cantique_file(path, cache_dir)
        if hymn is None:
            failed += 1
            continue
        title = clean_text(hymn.get("title") or path.stem)
        stanzas = [clean_text(s) for s in hymn.get("stanzas", []) if clean_text(s)]
        if not title or not stanzas:
            failed += 1
            continue
        parsed.setdefault(
            normalize_key(title),
            {"title": title, "stanzas": stanzas, "path": str(path)},
        )
    return parsed, failed


def load_db_hymns(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, number, title
        FROM hymn
        WHERE number LIKE 'AD-FOLDER-%'
        ORDER BY sort_key, number, id
        """
    ).fetchall()


def load_db_stanzas(conn: sqlite3.Connection, hymn_id: int) -> list[str]:
    rows = conn.execute(
        """
        SELECT text
        FROM hymn_stanza
        WHERE hymn_id = ?
        ORDER BY stanza_no
        """,
        (hymn_id,),
    ).fetchall()
    return [clean_text(row["text"]) for row in rows]


def replace_stanzas(conn: sqlite3.Connection, hymn: sqlite3.Row, stanzas: list[str]) -> None:
    stanza_cols = table_columns(conn, "hymn_stanza")
    hymn_cols = table_columns(conn, "hymn")
    has_label = "label" in stanza_cols
    has_chorus = "is_chorus" in stanza_cols
    has_fts = table_exists(conn, "hymn_stanza_fts")
    canonical_title = (
        str(hymn["title"] or "")
        if "canonical_title" not in hymn_cols
        else str(
            conn.execute(
                "SELECT COALESCE(NULLIF(canonical_title, ''), title) FROM hymn WHERE id = ?",
                (hymn["id"],),
            ).fetchone()[0]
        )
    )

    if has_fts:
        rowids = [
            int(row[0])
            for row in conn.execute(
                "SELECT id FROM hymn_stanza WHERE hymn_id = ?", (hymn["id"],)
            )
        ]
        if rowids:
            placeholders = ",".join("?" for _ in rowids)
            conn.execute(f"DELETE FROM hymn_stanza_fts WHERE rowid IN ({placeholders})", rowids)

    conn.execute("DELETE FROM hymn_stanza WHERE hymn_id = ?", (hymn["id"],))

    verse_no = 0
    chorus_no = 0
    for stanza_no, stanza in enumerate(stanzas, start=1):
        if detect_chorus(stanza):
            chorus_no += 1
            label, is_chorus = stanza_label(stanza, verse_no, chorus_no)
        else:
            verse_no += 1
            label, is_chorus = stanza_label(stanza, verse_no, chorus_no)

        cols = ["hymn_id", "stanza_no", "text"]
        vals: list[Any] = [hymn["id"], stanza_no, stanza]
        if has_label:
            cols.append("label")
            vals.append(label)
        if has_chorus:
            cols.append("is_chorus")
            vals.append(1 if is_chorus else 0)

        placeholders = ", ".join("?" for _ in cols)
        cursor = conn.execute(
            f"INSERT INTO hymn_stanza ({', '.join(cols)}) VALUES ({placeholders})",
            tuple(vals),
        )
        if has_fts:
            conn.execute(
                """
                INSERT INTO hymn_stanza_fts
                    (rowid, text, hymn_title, hymn_number, label)
                VALUES (?, ?, ?, ?, ?)
                """,
                (cursor.lastrowid, stanza, canonical_title, hymn["number"] or "", label),
            )


def repair_database(
    db_path: Path,
    folder: Path,
    cache_dir: Path,
    recursive: bool,
    apply: bool,
    backup: bool,
) -> RepairStats:
    stats = RepairStats()

    if apply and backup:
        backup_path = db_path.with_suffix(".before_hymn_repair.db")
        shutil.copy2(db_path, backup_path)
        print(f"Sauvegarde creee: {backup_path}")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        db_hymns = load_db_hymns(conn)
        stats.db_hymns = len(db_hymns)
        wanted_keys = {normalize_key(row["title"]) for row in db_hymns}

    source_hymns, failed = load_source_hymns(folder, cache_dir, recursive, wanted_keys)
    stats.source_hymns = len(source_hymns)
    stats.failed_source = failed

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        db_hymns = load_db_hymns(conn)

        for hymn in db_hymns:
            source = source_hymns.get(normalize_key(hymn["title"]))
            if source is None:
                stats.missing_source += 1
                continue

            stats.matched += 1
            new_stanzas = source["stanzas"]
            old_stanzas = load_db_stanzas(conn, int(hymn["id"]))
            if old_stanzas == new_stanzas:
                stats.unchanged += 1
                continue

            stats.changed += 1
            print(
                f"CHANGE {hymn['number']} | {hymn['title']} | "
                f"{len(old_stanzas)} -> {len(new_stanzas)} strophe(s)"
            )
            if apply:
                replace_stanzas(conn, hymn, new_stanzas)

        if apply:
            conn.commit()
        else:
            conn.rollback()

    return stats


def repair_existing_database(db_path: Path, apply: bool, backup: bool) -> RepairStats:
    stats = RepairStats()
    if apply and backup:
        backup_path = db_path.with_suffix(".before_hymn_repair.db")
        shutil.copy2(db_path, backup_path)
        print(f"Sauvegarde creee: {backup_path}")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        db_hymns = load_db_hymns(conn)
        stats.db_hymns = len(db_hymns)

        for hymn in db_hymns:
            old_stanzas = load_db_stanzas(conn, int(hymn["id"]))
            new_stanzas: list[str] = []
            for stanza in old_stanzas:
                new_stanzas.extend(_post_process_stanzas([stanza], str(hymn["title"] or "")))

            if old_stanzas == new_stanzas:
                stats.unchanged += 1
                continue

            stats.changed += 1
            print(
                f"CHANGE {hymn['number']} | {hymn['title']} | "
                f"{len(old_stanzas)} -> {len(new_stanzas)} strophe(s)"
            )
            if apply:
                replace_stanzas(conn, hymn, new_stanzas)

        if apply:
            conn.commit()
        else:
            conn.rollback()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repare les strophes AD-FOLDER deja importees depuis CANTIQUE D'ADORATION."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--folder", type=Path, default=DEFAULT_FOLDER)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--apply", action="store_true", help="Ecrit les corrections en base.")
    parser.add_argument(
        "--from-source",
        action="store_true",
        help="Relit les PowerPoint sources au lieu de reparer les strophes deja en base.",
    )
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    db_path = args.db.resolve()
    folder = args.folder.resolve()
    cache_dir = args.cache_dir.resolve()
    if not db_path.exists():
        raise SystemExit(f"Base introuvable: {db_path}")
    if not folder.is_dir():
        raise SystemExit(f"Dossier introuvable: {folder}")

    if args.from_source:
        stats = repair_database(
            db_path=db_path,
            folder=folder,
            cache_dir=cache_dir,
            recursive=bool(args.recursive),
            apply=bool(args.apply),
            backup=not bool(args.no_backup),
        )
    else:
        stats = repair_existing_database(
            db_path=db_path,
            apply=bool(args.apply),
            backup=not bool(args.no_backup),
        )

    mode = "Reparation" if args.apply else "Simulation"
    print(f"\n{mode} terminee.")
    print(f"  Cantiques AD en base: {stats.db_hymns}")
    if args.from_source:
        print(f"  Sources lues: {stats.source_hymns}")
        print(f"  Sources illisibles: {stats.failed_source}")
        print(f"  Correspondances: {stats.matched}")
    print(f"  A corriger: {stats.changed}")
    print(f"  Deja propres: {stats.unchanged}")
    if args.from_source:
        print(f"  Sans source retrouvee: {stats.missing_source}")
    if not args.apply:
        print("  Aucune modification ecrite. Relancez avec --apply pour appliquer.")


if __name__ == "__main__":
    main()
