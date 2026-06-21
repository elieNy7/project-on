"""Importe les cantiques au format Word (.docx) du dossier CANTIQUE D'ADORATION.

Complement de `import_cantique_adoration_folder.py` (qui gere .pptx/.ppt/.ewsx) :
un .docx peut contenir un ou plusieurs cantiques. On decoupe sur les lignes
vides multiples (>=1 paragraphe vide separe les blocs) et, a l'interieur d'un
cantique, chaque paragraphe non vide devient une strophe ; si le cantique est
ecrit ligne par ligne (un paragraphe = une ligne), on regroupe par quatrains.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import docx  # python-docx

from app.database.connection import Database, DatabaseConfig
from app.database.dao_hymns import HymnsDao
from app.utils.text_utils import clean_text

DEFAULT_FOLDER = ROOT / "CANTIQUE D'ADORATION"
DEFAULT_DB = ROOT / "data" / "project_on.db"


def normalize_key(value: object) -> str:
    text = clean_text(value).replace("’", "'").replace("`", "'")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text.casefold())
    return re.sub(r"\s+", " ", text).strip()


def read_paragraphs(path: Path) -> list[str]:
    document = docx.Document(str(path))
    out: list[str] = []
    for para in document.paragraphs:
        # A single paragraph may itself hold several lines (embedded newlines).
        out.extend(line.rstrip() for line in para.text.split("\n"))
    return out


def split_songs(lines: list[str]) -> list[list[str]]:
    """Split a flat list of lines into song blocks on blank-line gaps."""
    blocks: list[list[str]] = []
    current: list[str] = []
    blank_run = 0
    for line in lines:
        if line.strip():
            if blank_run >= 2 and current:
                blocks.append(current)
                current = []
            blank_run = 0
            current.append(line.strip())
        else:
            blank_run += 1
    if current:
        blocks.append(current)
    return [b for b in blocks if b]


def block_to_hymn(block: list[str]) -> dict[str, Any] | None:
    if not block:
        return None
    title = clean_text(block[0])
    body = block[1:]
    if not title or not body:
        return None

    # Lines that look like full stanzas already (sung lines kept together).
    # Heuristic: if there are few lines, treat the whole block as one stanza;
    # otherwise group into quatrains for readable projection.
    cleaned = [clean_text(b) for b in body if clean_text(b)]
    if not cleaned:
        return None

    stanzas: list[str] = []
    chunk: list[str] = []
    for line in cleaned:
        chunk.append(line)
        starts_refrain = re.match(r"^(refrain|chorus|ch[oœ]ur)\b", line, re.I)
        if len(chunk) >= 4 or starts_refrain and len(chunk) > 1:
            stanzas.append("\n".join(chunk))
            chunk = []
    if chunk:
        stanzas.append("\n".join(chunk))

    return {"title": title, "stanzas": stanzas}


def parse_docx(path: Path) -> list[dict[str, Any]]:
    lines = read_paragraphs(path)
    hymns: list[dict[str, Any]] = []
    for block in split_songs(lines):
        hymn = block_to_hymn(block)
        if hymn:
            hymn["source_path"] = str(path)
            hymns.append(hymn)
    return hymns


def next_ad_sort_number(db: Database) -> int:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT sort_key FROM hymn WHERE sort_key LIKE 'AD-FOLDER-%' "
            "ORDER BY sort_key DESC LIMIT 1"
        ).fetchone()
    if row is None or not row["sort_key"]:
        return 1
    match = re.search(r"AD-FOLDER-(\d+)", str(row["sort_key"]))
    return int(match.group(1)) + 1 if match else 1


def load_existing_keys(db: Database) -> set[str]:
    with db.connect() as conn:
        rows = conn.execute("SELECT title FROM hymn").fetchall()
    return {normalize_key(r["title"]) for r in rows if r["title"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, default=DEFAULT_FOLDER)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--language", default="en")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    folder = args.folder.resolve()
    db = Database(DatabaseConfig(db_path=args.db.resolve()))
    dao = HymnsDao(db)
    existing = load_existing_keys(db)
    sort_no = next_ad_sort_number(db)

    imported = skipped = failed = 0
    for path in sorted(folder.glob("*.docx")):
        if path.name.startswith("~$"):
            continue
        hymns = parse_docx(path)
        if not hymns:
            failed += 1
            print(f"ECHEC  {path.name}")
            continue
        for hymn in hymns:
            key = normalize_key(hymn["title"])
            if key in existing:
                skipped += 1
                print(f"EXISTE {hymn['title']}")
                continue
            print(f"{'DRY' if args.dry_run else 'OK':<6} {hymn['title']} "
                  f"({len(hymn['stanzas'])} strophe(s))  <- {path.name}")
            if not args.dry_run:
                hid = dao.import_hymn(
                    hymn["title"],
                    hymn["stanzas"],
                    number=f"AD-FOLDER-{sort_no:04d}",
                    language=args.language,
                )
                with db.connect() as conn:
                    conn.execute(
                        "UPDATE hymn SET sort_key = ? WHERE id = ?",
                        (f"AD-FOLDER-{sort_no:04d}", hid),
                    )
                sort_no += 1
            existing.add(key)
            imported += 1

    print(f"\n{'Simulation' if args.dry_run else 'Import'} termine.")
    print(f"  Cantiques importes: {imported}")
    print(f"  Ignored deja en BD: {skipped}")
    print(f"  Fichiers illisibles: {failed}")


if __name__ == "__main__":
    main()
