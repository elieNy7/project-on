from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF = ROOT / "cantiques" / "cantique-swahili.pdf"
DEFAULT_DB = ROOT / "data" / "project_on.db"
DEFAULT_BACKUP = ROOT / "data" / "project_on.before_swahili_import.db"
FIRST_HYMN_PAGE = 8
LAST_HYMN_PAGE = 418
EXPECTED_HYMNS = 335

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.connection import Database, DatabaseConfig
from app.database.dao_hymns import HymnsDao
from app.utils.text_utils import clean_text


@dataclass
class Line:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class ParsedHymn:
    number: int
    title: str
    start_page: int
    end_page: int
    stanzas: list[str]


SKIP_PHRASES = (
    "Page de titre",
    "Table alphabetique",
    "Table alphabétique",
    "Table numerique",
    "Table numérique",
)
VERSE_RE = re.compile(r"^(\d{1,2})\.\s*(.*)")
SOURCE_LINE_RE = re.compile(
    r"\b(Sgt|Evgt|R\.S\.|R\.H\.|M\.A\.|Mel\.|S\.Sgt)\b", re.IGNORECASE
)
YEAR_RE = re.compile(r"\b(1[6-9]\d{2}|20\d{2})(?:-\d{4})?\b")


def fix_pdf_text(text: str) -> str:
    text = clean_text(text)
    return text.replace("Ť", "«").replace("ť", "»")


def page_lines(doc: fitz.Document, page_index: int) -> list[Line]:
    fragments: list[Line] = []
    page = doc[page_index]
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = fix_pdf_text("".join(span["text"] for span in line["spans"]))
            if not text:
                continue
            x0, y0, x1, y1 = line["bbox"]
            fragments.append(Line(text=text, x0=x0, y0=y0, x1=x1, y1=y1))

    fragments.sort(key=lambda item: (item.y0, item.x0))
    merged: list[Line] = []
    for item in fragments:
        if (
            merged
            and abs(item.y0 - merged[-1].y0) < 2.5
            and item.x0 >= merged[-1].x0
        ):
            prev = merged[-1]
            prev.text = f"{prev.text} {item.text}".strip()
            prev.x1 = max(prev.x1, item.x1)
            prev.y1 = max(prev.y1, item.y1)
        else:
            merged.append(item)
    return merged


def should_skip_line(text: str) -> bool:
    if not text:
        return True
    return any(phrase in text for phrase in SKIP_PHRASES) or text.startswith(
        "Suite, page suivante"
    )


def title_from_start_page(lines: list[Line], expected_number: int) -> tuple[bool, str]:
    found = False
    title_parts: list[str] = []
    for line in lines:
        text = line.text
        if should_skip_line(text):
            continue
        if not (80 <= line.y0 <= 180 and 40 <= line.x0 <= 580):
            continue

        if re.fullmatch(str(expected_number), text):
            found = True
            continue

        leading_number = re.match(rf"^{expected_number}\s+(.+?)\s*$", text)
        if leading_number:
            title_parts.append(leading_number.group(1).strip())
            found = True
            continue

        trailing_number = re.match(rf"(.+?)\s+{expected_number}\s*$", text)
        if trailing_number:
            title_parts.append(trailing_number.group(1).strip())
            found = True
            continue

        if SOURCE_LINE_RE.search(text):
            continue
        title_parts.append(text)

    return found, " ".join(title_parts).strip()


def find_hymn_starts(doc: fitz.Document) -> list[tuple[int, int, str]]:
    starts: list[tuple[int, int, str]] = []
    expected = 1
    for page_index in range(FIRST_HYMN_PAGE - 1, LAST_HYMN_PAGE):
        found, title = title_from_start_page(page_lines(doc, page_index), expected)
        if found:
            starts.append((expected, page_index, title))
            expected += 1
            if expected > EXPECTED_HYMNS:
                break
    return starts


def strip_credit_suffix(text: str) -> str:
    text = text.strip()
    if re.match(r"^v\.\s*\d", text, re.IGNORECASE):
        return ""
    text = re.sub(
        r"\s+[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ.'-]+(?:\s+[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ.'-]+){0,6},\s*"
        r"(?:1[6-9]\d{2}|20\d{2})(?:-\d{4})?\s*$",
        "",
        text,
    ).strip()
    return text


def looks_like_credit_line(line: Line) -> bool:
    text = line.text.strip()
    if len(text) > 85 or VERSE_RE.match(text):
        return False
    if YEAR_RE.search(text):
        return True
    if line.y0 < 540 or line.x0 < 170:
        return False
    if any(ch in text for ch in "!?«»:;"):
        return False
    if re.search(r"\b(arr|Mrs|Mr|Fr|Missionnary)\b", text, re.IGNORECASE):
        return True
    tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ.'-]*", text)
    if len(tokens) < 2 or len(tokens) > 8:
        return False
    capitalized = sum(1 for token in tokens if token[:1].isupper())
    return capitalized >= max(1, len(tokens) - 1)


def strip_author_tail(lines: list[Line]) -> list[Line]:
    out = list(lines)
    while out:
        last = out[-1]
        if (
            len(out) >= 2
            and YEAR_RE.search(out[-2].text)
            and re.fullmatch(
                r"[A-Z](?:\.)?|[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ.'-]{1,20}",
                last.text.strip(),
            )
        ):
            out.pop()
            continue
        stripped = strip_credit_suffix(last.text)
        if stripped != last.text:
            if stripped:
                had_year = bool(YEAR_RE.search(last.text))
                last.text = stripped
                if (
                    looks_like_credit_line(last)
                    or re.fullmatch(r"(?:[A-Z]\.){1,4}", stripped)
                    or (
                        had_year
                        and re.fullmatch(
                            r"[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ.'-]{1,25}",
                            stripped,
                        )
                    )
                ):
                    out.pop()
                    continue
                break
            out.pop()
            continue
        if looks_like_credit_line(last):
            out.pop()
            continue
        break
    return out


def extract_hymn_lines(
    doc: fitz.Document, start_page: int, end_page: int
) -> list[Line]:
    raw: list[Line] = []
    collecting = False
    for page_index in range(start_page, end_page + 1):
        for line in page_lines(doc, page_index):
            text = line.text
            if should_skip_line(text) or line.x0 > 530:
                continue
            if page_index == start_page and not collecting:
                if VERSE_RE.match(text):
                    collecting = True
                else:
                    continue
            elif line.y0 < 125:
                continue
            if collecting:
                raw.append(line)
    return strip_author_tail(raw)


def split_stanzas(lines: list[Line]) -> list[str]:
    stanzas: list[str] = []
    current: list[str] = []
    for line in lines:
        match = VERSE_RE.match(line.text)
        if match:
            if current:
                stanzas.append("\n".join(current).strip())
            rest = match.group(2).strip()
            current = [rest] if rest else []
        elif current:
            current.append(line.text)
    if current:
        stanzas.append("\n".join(current).strip())
    return [stanza for stanza in stanzas if stanza]


def parse_pdf(pdf_path: Path) -> list[ParsedHymn]:
    with fitz.open(pdf_path) as doc:
        starts = find_hymn_starts(doc)
        if len(starts) != EXPECTED_HYMNS:
            raise RuntimeError(
                f"Expected {EXPECTED_HYMNS} hymn starts, found {len(starts)}."
            )

        hymns: list[ParsedHymn] = []
        for idx, (number, start_page, title) in enumerate(starts):
            end_page = (
                starts[idx + 1][1] - 1 if idx + 1 < len(starts) else LAST_HYMN_PAGE - 1
            )
            stanzas = split_stanzas(extract_hymn_lines(doc, start_page, end_page))
            if not stanzas:
                raise RuntimeError(f"No stanzas parsed for hymn {number}.")
            hymns.append(
                ParsedHymn(
                    number=number,
                    title=title or f"Cantique Swahili {number}",
                    start_page=start_page + 1,
                    end_page=end_page + 1,
                    stanzas=stanzas,
                )
            )
        return hymns


def existing_numbers(db: Database, prefix: str) -> set[str]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT number FROM hymn WHERE number LIKE ?", (f"{prefix}-%",)
        ).fetchall()
    return {str(row["number"]) for row in rows if row["number"]}


def backup_database(db_path: Path, backup_path: Path) -> None:
    if backup_path.exists():
        return
    shutil.copy2(db_path, backup_path)


def import_hymns(
    hymns: list[ParsedHymn],
    db_path: Path,
    prefix: str,
    apply: bool,
    no_backup: bool,
) -> tuple[int, int]:
    db = Database(DatabaseConfig(db_path=db_path))
    db.initialize()
    dao = HymnsDao(db)
    existing = existing_numbers(db, prefix)

    imported = 0
    skipped = 0
    if apply and not no_backup:
        backup_database(db_path, DEFAULT_BACKUP)

    for hymn in hymns:
        number = f"{prefix}-{hymn.number:03d}"
        title = f"{number}. {hymn.title}"
        if number in existing:
            skipped += 1
            continue
        if apply:
            dao.import_hymn(title, hymn.stanzas, number=number, language="sw")
        imported += 1
    return imported, skipped


def print_report(hymns: list[ParsedHymn]) -> None:
    stanza_counts = [len(hymn.stanzas) for hymn in hymns]
    print(f"Cantiques detectes: {len(hymns)}")
    print(f"Strophes totales: {sum(stanza_counts)}")
    print(f"Pages: {hymns[0].start_page}-{hymns[-1].end_page}")
    print()
    for hymn in hymns[:5]:
        print(
            f"{hymn.number:03d}. {hymn.title} "
            f"({hymn.start_page}-{hymn.end_page}, {len(hymn.stanzas)} strophes)"
        )
        print("  " + hymn.stanzas[0].splitlines()[0][:120])
    print("...")
    for hymn in hymns[-3:]:
        print(
            f"{hymn.number:03d}. {hymn.title} "
            f"({hymn.start_page}-{hymn.end_page}, {len(hymn.stanzas)} strophes)"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import cantiques Swahili depuis cantique-swahili.pdf."
    )
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--prefix", default="SW")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    hymns = parse_pdf(args.pdf)
    print_report(hymns)
    imported, skipped = import_hymns(
        hymns=hymns,
        db_path=args.db,
        prefix=args.prefix,
        apply=args.apply,
        no_backup=args.no_backup,
    )
    if args.apply:
        print(f"\nImportes: {imported}")
        print(f"Ignores car deja presents: {skipped}")
        if not args.no_backup:
            print(f"Sauvegarde: {DEFAULT_BACKUP}")
    else:
        print(f"\nSimulation: {imported} seraient importes, {skipped} deja presents.")
        print("Relancez avec --apply pour importer.")


if __name__ == "__main__":
    main()
