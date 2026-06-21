"""Clean every hymn from the database and re-import the cantiques PDFs.

Scope (per request):
  * Wipe the `hymn`, `hymn_stanza` (and `hymn_stanza_fts`) tables entirely.
  * Parse the three PDFs in ``cantiques/`` — EXCLUDING ``cantique-swahili.pdf``:
      - Cantique Pene Na Yo.pdf      (Lingala hymnal, two columns + single
                                       "Choeur" markers -> needs column-break
                                       handling)
      - Cantiques Crois seulement.pdf (French)
      - Cantiques-Ins.pdf            (French)
  * Re-import them (titles + stanzas faithful to the PDF) through ``HymnsDao``
    so canonical titles, search keys, stanza labels and the FTS index are all
    populated.

The PDF parsing helpers live in ``import_cantiques_from_pdfs`` and are reused
here.

Usage:
    py -3 tools/import_cantiques.py            # dry-run (parse + report only)
    py -3 tools/import_cantiques.py --apply    # wipe + import into the DB
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import import_cantiques_from_pdfs as parser  # noqa: E402  (reused PDF parser)

from app.database.connection import Database  # noqa: E402
from app.database.dao_hymns import HymnsDao  # noqa: E402

CANTIQUES_DIR = ROOT / "cantiques"

# (source code, filename, page ranges [(start, end)], language, column_break)
# `column_break` forces a stanza break at two-column boundaries — required by
# the Pene Na Yo hymnal where a chorus can end at the bottom of the left column
# and the next verse start at the top of the right column with no vertical gap.
SPECS: list[tuple[str, str, list[tuple[int, int | None]], str, bool]] = [
    ("PNY", "Cantique Pene Na Yo.pdf", [(0, 47)], "ln", True),
    ("CS", "Cantiques Crois seulement.pdf", [(0, 70), (76, None)], "fr", False),
    ("CI", "Cantiques-Ins.pdf", [(4, 154)], "fr", False),
]


def parse_all() -> list[tuple[parser.Hymn, str]]:
    out: list[tuple[parser.Hymn, str]] = []
    for source, name, ranges, lang, column_break in SPECS:
        pdf_path = CANTIQUES_DIR / name
        if not pdf_path.exists():
            raise FileNotFoundError(pdf_path)
        hymns = parser.parse_pdf_ranges(
            pdf_path, source, ranges, column_break=column_break
        )
        out.extend((hymn, lang) for hymn in hymns)
    return out


def print_report(hymns: list[tuple[parser.Hymn, str]]) -> None:
    by_source: dict[str, list[parser.Hymn]] = {}
    for hymn, _lang in hymns:
        by_source.setdefault(hymn.source, []).append(hymn)

    print("Cantiques analysés:")
    for source, items in by_source.items():
        stanzas = sum(len(h.stanzas) for h in items)
        print(f"  {source}: {len(items)} cantiques, {stanzas} strophes/refrains")
        for sample in items[:2]:
            preview = sample.stanzas[0].replace("\n", " ")[:80]
            print(f"    {sample.number} | {sample.title} | {len(sample.stanzas)} | {preview}")
    print(f"  TOTAL: {len(hymns)} cantiques")


def clean_all_hymns(db: Database) -> int:
    with db.connect() as conn:
        before = conn.execute("SELECT COUNT(*) FROM hymn").fetchone()[0]
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='hymn_stanza_fts'"
        ).fetchone():
            conn.execute("DELETE FROM hymn_stanza_fts")
        conn.execute("DELETE FROM hymn_stanza")
        conn.execute("DELETE FROM hymn")
    return int(before)


def import_all(db: Database, hymns: list[tuple[parser.Hymn, str]]) -> int:
    dao = HymnsDao(db)
    sort_updates: list[tuple[str, int]] = []
    for order, (hymn, lang) in enumerate(hymns, start=1):
        hymn_id = dao.import_hymn(
            hymn.title, hymn.stanzas, number=hymn.number, language=lang
        )
        # Preserve PDF order (PNY, then CS, then CI) rather than alphabetical.
        sort_updates.append((f"{order:05d}", int(hymn_id)))

    with db.connect() as conn:
        conn.executemany("UPDATE hymn SET sort_key = ? WHERE id = ?", sort_updates)
    return len(sort_updates)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Effectue le nettoyage complet + import (sinon: dry-run).",
    )
    args = ap.parse_args()

    hymns = parse_all()
    print_report(hymns)

    if not args.apply:
        print("\nDry-run: la base n'a pas été modifiée. Utilisez --apply pour importer.")
        return

    db = Database.default()
    print(f"\nBase: {db.db_path}")
    removed = clean_all_hymns(db)
    imported = import_all(db, hymns)
    with db.connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM hymn").fetchone()[0]
        stanzas = conn.execute("SELECT COUNT(*) FROM hymn_stanza").fetchone()[0]
    print(
        f"Nettoyage: {removed} cantiques supprimés.\n"
        f"Import: {imported} cantiques ({stanzas} strophes).\n"
        f"Total en base: {total} cantiques."
    )


if __name__ == "__main__":
    main()
