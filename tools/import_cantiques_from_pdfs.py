"""Legacy CLI: import the CS/CI cantique PDFs into data/project_on.db.

The PDF parsing logic now lives in ``app.utils.hymn_pdf_parser`` (shared with
the in-app importer). This module re-exports those primitives for backward
compatibility and keeps the older CS/CI replace-in-place CLI.

For a full clean re-import of all three PDFs, prefer ``tools/import_cantiques.py``.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Re-export the shared parser primitives (single source of truth).
from app.utils.hymn_pdf_parser import (  # noqa: E402,F401
    CHORUS_RE,
    HEADER_PATTERNS,
    MUSIC_KEY_RE,
    Hymn,
    clean_body_line,
    clean_title,
    is_header_footer,
    lines_to_text_lines,
    looks_like_title_line,
    normalize_text,
    ordered_pdf_lines,
    parse_hymn_headers,
    parse_hymns_from_lines,
    parse_pdf,
    parse_pdf_ranges,
    parse_stanzas,
    should_continue_title,
    strip_music_key,
    upper_ratio,
)

DB_PATH = ROOT / "data" / "project_on.db"
CANTIQUES_DIR = ROOT / "cantiques"


def parse_all_hymns() -> list[Hymn]:
    specs = [
        # Cantiques Crois seulement has an index on PDF pages 71-76.
        # Hymn content resumes after the index, so import two content ranges.
        ("CS", CANTIQUES_DIR / "Cantiques Crois seulement.pdf", [(0, 70), (76, None)]),
        # Cantiques-Ins pages 1-4 are front matter and pages 157+ are the index.
        ("CI", CANTIQUES_DIR / "Cantiques-Ins.pdf", [(4, 154)]),
    ]

    all_hymns: list[Hymn] = []
    for source, pdf_path, page_ranges in specs:
        if not pdf_path.exists():
            raise FileNotFoundError(pdf_path)
        all_hymns.extend(parse_pdf_ranges(pdf_path, source, page_ranges))
    return all_hymns


def replace_hymns(db_path: Path, hymns: list[Hymn]) -> tuple[int, int]:
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        old_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM hymn
            WHERE number LIKE 'CS-%' OR number LIKE 'CI-%'
            """
        ).fetchone()[0]

        existing_rows = conn.execute(
            """
            SELECT id, number
            FROM hymn
            WHERE number LIKE 'CS-%' OR number LIKE 'CI-%'
            ORDER BY id
            """
        ).fetchall()
        existing_by_number: dict[str, int] = {}
        duplicate_ids: list[int] = []
        for hymn_id, number in existing_rows:
            if number in existing_by_number:
                duplicate_ids.append(int(hymn_id))
            else:
                existing_by_number[str(number)] = int(hymn_id)

        new_numbers = {hymn.number for hymn in hymns}
        stale_ids = [
            hymn_id
            for number, hymn_id in existing_by_number.items()
            if number not in new_numbers
        ]
        delete_ids = stale_ids + duplicate_ids
        if delete_ids:
            placeholders = ",".join("?" for _ in delete_ids)
            conn.execute(f"DELETE FROM hymn_stanza WHERE hymn_id IN ({placeholders})", delete_ids)
            conn.execute(f"DELETE FROM hymn WHERE id IN ({placeholders})", delete_ids)

        for global_order, hymn in enumerate(hymns, start=1):
            sort_key = f"{global_order:05d}-{hymn.source}-{hymn.source_order:04d}"
            hymn_id = existing_by_number.get(hymn.number)
            if hymn_id is None:
                cursor = conn.execute(
                    "INSERT INTO hymn (title, number, language, sort_key) VALUES (?, ?, ?, ?)",
                    (hymn.title, hymn.number, "fr", sort_key),
                )
                hymn_id = int(cursor.lastrowid)
            else:
                conn.execute(
                    """
                    UPDATE hymn
                    SET title = ?, language = ?, sort_key = ?
                    WHERE id = ?
                    """,
                    (hymn.title, "fr", sort_key, hymn_id),
                )
                conn.execute("DELETE FROM hymn_stanza WHERE hymn_id = ?", (hymn_id,))

            for stanza_no, stanza in enumerate(hymn.stanzas, start=1):
                conn.execute(
                    "INSERT INTO hymn_stanza (hymn_id, stanza_no, text) VALUES (?, ?, ?)",
                    (hymn_id, stanza_no, stanza),
                )

        conn.commit()
    return old_count, len(hymns)


def print_report(hymns: list[Hymn]) -> None:
    by_source: dict[str, list[Hymn]] = {}
    for hymn in hymns:
        by_source.setdefault(hymn.source, []).append(hymn)

    print("Cantiques trouves:")
    for source, items in by_source.items():
        stanza_count = sum(len(item.stanzas) for item in items)
        print(f"  {source}: {len(items)} cantiques, {stanza_count} couplets/refrains")
        for sample in items[:3]:
            preview = sample.stanzas[0].replace("\n", " ")[:90]
            print(f"    {sample.number} | {sample.title} | {len(sample.stanzas)} | {preview}")
        if len(items) > 3:
            last = items[-1]
            print(f"    ... dernier: {last.number} | {last.title} | {len(last.stanzas)}")


def main() -> None:
    arg_parser = argparse.ArgumentParser(
        description="Importe les cantiques des deux PDF du dossier cantiques vers data/project_on.db."
    )
    arg_parser.add_argument("--db", type=Path, default=DB_PATH)
    arg_parser.add_argument("--dry-run", action="store_true")
    args = arg_parser.parse_args()

    db_path = args.db.resolve()
    expected_data_dir = (ROOT / "data").resolve()
    if db_path.parent != expected_data_dir:
        raise SystemExit(f"Refus: utilisez uniquement une base dans {expected_data_dir}")
    if not db_path.exists():
        raise SystemExit(f"Base introuvable: {db_path}")

    hymns = parse_all_hymns()
    print_report(hymns)

    if args.dry_run:
        print("Dry-run: aucune modification de la base.")
        return

    old_count, new_count = replace_hymns(db_path, hymns)
    print(
        f"Base mise a jour: {old_count} cantiques PDF remplaces/mis a jour, "
        f"{new_count} importes."
    )


if __name__ == "__main__":
    main()
