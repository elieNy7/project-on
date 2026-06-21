"""Column-aware, gap-based hymn PDF parser.

This is the parser developed and validated against the project's cantique
PDFs (Pene Na Yo, Crois seulement, Cantiques-Ins). It reconstructs the page
text line-by-line using the real vertical gaps between lines, so stanzas are
separated exactly where the PDF separates them. It also:

  * detects two-column layouts and reads left-then-right,
  * can force a stanza break at the column boundary (``column_break``) — a
    chorus ending at the bottom of the left column and the next verse starting
    at the top of the right column have no measurable vertical gap,
  * keeps a "Choeur"/"Refrain" label even when a blank line sits between the
    marker and its body,
  * repeats a single chorus after every verse (projection-friendly).

Both the in-app PDF import (``library_controller``) and the offline import
script (``tools/import_cantiques_from_pdfs``) use this module so the behaviour
stays identical.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import fitz  # PyMuPDF

    HAS_FITZ = True
except ImportError:  # pragma: no cover - optional dependency
    HAS_FITZ = False


HEADER_PATTERNS = (
    "Petit Troupeau Tabernacle",
    "Un Evangile Eternel",
    "branhammessage",
    "TABLE DE MATIERES",
    "CHANTS CONVENTION",
    "Index",
)

MUSIC_KEY_RE = re.compile(
    r"^(?:[A-G](?:b|#)?|[A-G](?:b|#)?m|Do|Re|Mi|Fa|Sol|La|Si)\.?$",
    re.IGNORECASE,
)

CHORUS_RE = re.compile(
    r"^(ch(?:oe|œ)ur|refrain|dernier refrain)\s*:?\s*(.*)$",
    re.IGNORECASE,
)


@dataclass
class Hymn:
    source: str
    source_order: int
    number: str
    title: str
    stanzas: list[str]


def normalize_text(value: str) -> str:
    value = value.replace("’", "'").replace("‘", "'")
    value = value.replace("“", '"').replace("”", '"')
    value = value.replace(" ", " ").replace(" ", " ")
    value = re.sub(r"[ 	]+", " ", value)
    return value.strip()


def is_header_footer(text: str) -> bool:
    text = normalize_text(text)
    return any(pattern.lower() in text.lower() for pattern in HEADER_PATTERNS)


def ordered_pdf_lines(
    pdf_path: Path,
    page_start: int = 0,
    page_end: int | None = None,
    column_break: bool = False,
) -> list[str]:
    doc = fitz.open(pdf_path)
    end = doc.page_count if page_end is None else min(page_end, doc.page_count)
    all_lines: list[str] = []

    for page_index in range(page_start, end):
        page = doc[page_index]
        page_dict = page.get_text("dict")
        page_width = page.rect.width
        page_height = page.rect.height

        raw_lines: list[dict[str, float | str]] = []
        for block in page_dict.get("blocks", []):
            if block.get("type", 0) != 0:
                continue
            for line in block.get("lines", []):
                text = normalize_text(
                    "".join(span.get("text", "") for span in line.get("spans", []))
                )
                if not text or is_header_footer(text):
                    continue

                bbox = line["bbox"]
                sizes = [
                    float(span.get("size", 0))
                    for span in line.get("spans", [])
                    if span.get("text", "").strip()
                ]
                size = max(sizes) if sizes else 0
                x0, y0, x1, y1 = map(float, bbox)

                # Skip visual page numbers, but keep hymn numbers.
                if re.fullmatch(r"\d{1,4}", text):
                    if y0 > page_height * 0.92 or size >= 18 or x0 > page_width * 0.85:
                        continue

                raw_lines.append(
                    {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": text}
                )

        mid_x = page_width / 2
        left = [ln for ln in raw_lines if (float(ln["x0"]) + float(ln["x1"])) / 2 < mid_x]
        right = [ln for ln in raw_lines if (float(ln["x0"]) + float(ln["x1"])) / 2 >= mid_x]
        is_two_column = len(left) >= 6 and len(right) >= 6

        if is_two_column:
            left_lines = lines_to_text_lines(left)
            right_lines = lines_to_text_lines(right)
            # A stanza ending at the bottom of the left column and the next one
            # starting at the top of the right column have no measurable vertical
            # gap, so force a stanza break at the column boundary when requested.
            if column_break and left_lines and right_lines:
                page_lines = left_lines + [""] + right_lines
            else:
                page_lines = left_lines + right_lines
        else:
            page_lines = lines_to_text_lines(raw_lines)

        all_lines.extend(page_lines)

    doc.close()
    return all_lines


def lines_to_text_lines(lines: list[dict[str, float | str]]) -> list[str]:
    if not lines:
        return []

    ordered = sorted(lines, key=lambda item: (float(item["y0"]), float(item["x0"])))
    # These PDFs use tight line spacing, but stanza breaks are visible as small
    # positive gaps between baselines. A low threshold is needed for songs that
    # have no explicit verse numbers.
    blank_gap = 2.0

    out: list[str] = []
    prev_y1: float | None = None
    for item in ordered:
        y0 = float(item["y0"])
        if prev_y1 is not None and y0 - prev_y1 > blank_gap and out and out[-1] != "":
            out.append("")
        out.append(str(item["text"]))
        prev_y1 = float(item["y1"])
    return out


def strip_music_key(title: str) -> str:
    title = normalize_text(title)
    title = re.sub(r"\s{2,}", " ", title)
    parts = title.split()
    if parts and MUSIC_KEY_RE.fullmatch(parts[-1]):
        title = " ".join(parts[:-1])
    return title.strip(" .")


def upper_ratio(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for ch in letters if ch.isupper()) / len(letters)


def looks_like_title_line(text: str) -> bool:
    text = strip_music_key(text)
    if len(text) < 3:
        return False
    if CHORUS_RE.match(text):
        return False
    if MUSIC_KEY_RE.fullmatch(text):
        return False

    leading = re.sub(r"^[\"'(\[]+", "", text)
    if not leading or not leading[0].isupper():
        return False

    first_part = re.split(r"\s*\(", text, maxsplit=1)[0].strip()
    if upper_ratio(first_part) >= 0.70:
        return True
    if upper_ratio(text) >= 0.62 and len(text) <= 80:
        return True
    return False


def should_continue_title(line: str, current_parts: list[str]) -> bool:
    clean = strip_music_key(line)
    if not clean:
        return False
    if MUSIC_KEY_RE.fullmatch(clean):
        return False
    if current_parts and current_parts[-1].rstrip().endswith("-"):
        return True
    previous = current_parts[-1] if current_parts else ""
    if re.search(r"\bEXO\b|Eclats|Éclats", clean, re.IGNORECASE):
        return len(clean) <= 55
    if re.search(r"\bEXO\b|Eclats|Éclats", previous, re.IGNORECASE):
        return bool(re.match(r"^(?:d'|d’)", clean, re.IGNORECASE))
    return looks_like_title_line(clean) and len(clean) <= 70


def parse_hymn_headers(lines: list[str]) -> list[tuple[int, int, str, int]]:
    headers: list[tuple[int, int, str, int]] = []
    i = 0

    while i < len(lines):
        line = normalize_text(lines[i])
        if not line:
            i += 1
            continue

        number: int | None = None
        title_parts: list[str] = []
        body_start = i + 1

        inline = re.match(r"^(\d{1,3})\.\s*(.+)$", line)
        compact_inline = re.match(r"^(\d{1,3})([A-ZÀ-ÖØ-Þ].+)$", line)
        spaced_inline = re.match(r"^(\d{1,3})\s+([A-ZÀ-ÖØ-Þ].+)$", line)
        standalone = re.match(r"^(\d{1,3})(?:\s*[a-z])?\.?$", line, re.IGNORECASE)

        if inline and looks_like_title_line(inline.group(2)):
            number = int(inline.group(1))
            title_parts.append(inline.group(2))
            body_start = i + 1
        elif compact_inline and looks_like_title_line(compact_inline.group(2)):
            number = int(compact_inline.group(1))
            title_parts.append(compact_inline.group(2))
            body_start = i + 1
        elif spaced_inline and looks_like_title_line(spaced_inline.group(2)):
            number = int(spaced_inline.group(1))
            title_parts.append(spaced_inline.group(2))
            body_start = i + 1
        elif standalone:
            j = i + 1
            while j < len(lines) and not normalize_text(lines[j]):
                j += 1
            if j < len(lines) and looks_like_title_line(lines[j]):
                number = int(standalone.group(1))
                title_parts.append(lines[j])
                body_start = j + 1

        if number is None:
            i += 1
            continue

        j = body_start
        while j < len(lines):
            candidate = normalize_text(lines[j])
            if not candidate:
                break
            if should_continue_title(candidate, title_parts):
                title_parts.append(candidate)
                j += 1
                body_start = j
                continue
            break

        title = clean_title(" ".join(title_parts))
        if title and len(title) >= 3:
            headers.append((i, number, title, body_start))
            i = max(body_start, i + 1)
        else:
            i += 1

    return headers


def clean_title(title: str) -> str:
    title = strip_music_key(title)
    title = re.sub(r"\s+", " ", title)
    title = title.replace(" .", ".").strip(" .")
    title = title.title()
    title = re.sub(r"\bD'", "D'", title)
    title = re.sub(r"\bL'", "L'", title)
    title = re.sub(r"\bJ'", "J'", title)
    title = re.sub(r"\bN'", "N'", title)
    title = re.sub(r"\bM'", "M'", title)
    title = re.sub(r"\bS'", "S'", title)
    title = re.sub(r"\bQu'", "Qu'", title)
    title = title.replace("Jesus", "Jesus")
    return title.strip()


def clean_body_line(line: str) -> str:
    line = normalize_text(line)
    if MUSIC_KEY_RE.fullmatch(line):
        return ""
    return line


def parse_stanzas(lines: list[str], repeat_single_chorus: bool = True) -> list[str]:
    parts: list[tuple[str, str]] = []
    current_label = "verse"
    current: list[str] = []
    pending_chorus_blank = False

    def flush() -> None:
        nonlocal current, pending_chorus_blank
        text = "\n".join(item for item in current if item).strip()
        if text:
            parts.append((current_label, text))
        current = []
        pending_chorus_blank = False

    for raw_line in lines:
        if raw_line == "":
            if current_label in ("chorus", "final_chorus") and not current:
                # Blank line between the "Choeur"/"Refrain" marker and its body
                # (common in single-marker hymnals) — keep the chorus label.
                continue
            if current_label == "chorus" and current:
                pending_chorus_blank = True
                continue
            flush()
            current_label = "verse"
            continue

        line = clean_body_line(raw_line)
        if not line:
            continue

        if pending_chorus_blank:
            if line.startswith("("):
                current.append(line)
                pending_chorus_blank = False
                continue
            flush()
            current_label = "verse"

        chorus_match = CHORUS_RE.match(line)
        if chorus_match:
            flush()
            label = chorus_match.group(1).lower()
            current_label = "final_chorus" if label.startswith("dernier") else "chorus"
            remainder = chorus_match.group(2).strip()
            if remainder:
                current.append(remainder)
            continue

        verse_match = re.match(r"^(\d{1,2})\.\s*(.*)$", line)
        if verse_match and not looks_like_title_line(verse_match.group(2)):
            flush()
            current_label = "verse"
            remainder = verse_match.group(2).strip()
            if remainder:
                current.append(remainder)
            continue

        current.append(line)

    flush()

    if not parts:
        return []

    if repeat_single_chorus:
        chorus_blocks = [text for label, text in parts if label == "chorus"]
        final_blocks = [text for label, text in parts if label == "final_chorus"]
        verse_blocks = [text for label, text in parts if label == "verse"]
        if len(chorus_blocks) == 1 and len(final_blocks) == 0 and len(verse_blocks) > 1:
            chorus = chorus_blocks[0]
            rebuilt: list[str] = []
            for verse in verse_blocks:
                rebuilt.append(verse)
                rebuilt.append("Choeur:\n" + chorus)
            return rebuilt

    stanzas: list[str] = []
    for label, text in parts:
        if label == "chorus":
            stanzas.append("Choeur:\n" + text)
        elif label == "final_chorus":
            stanzas.append("Dernier refrain:\n" + text)
        else:
            stanzas.append(text)
    return stanzas


def parse_hymns_from_lines(lines: list[str], source: str) -> list[Hymn]:
    headers = parse_hymn_headers(lines)
    hymns: list[Hymn] = []
    seen_number_counts: dict[int, int] = {}

    for index, (header_line, number, title, body_start) in enumerate(headers, start=1):
        next_header = headers[index][0] if index < len(headers) else len(lines)
        body_lines = lines[body_start:next_header]
        stanzas = parse_stanzas(body_lines)
        if not stanzas:
            continue

        seen_number_counts[number] = seen_number_counts.get(number, 0) + 1
        suffix = "" if seen_number_counts[number] == 1 else f"-{seen_number_counts[number]}"
        source_number = f"{source}-{number:03d}{suffix}"
        hymns.append(
            Hymn(
                source=source,
                source_order=index,
                number=source_number,
                title=title,
                stanzas=stanzas,
            )
        )

    return hymns


def parse_pdf(
    pdf_path: Path,
    source: str,
    page_start: int = 0,
    page_end: int | None = None,
    column_break: bool = False,
) -> list[Hymn]:
    lines = ordered_pdf_lines(
        pdf_path, page_start=page_start, page_end=page_end, column_break=column_break
    )
    return parse_hymns_from_lines(lines, source)


def parse_pdf_ranges(
    pdf_path: Path,
    source: str,
    ranges: list[tuple[int, int | None]],
    column_break: bool = False,
) -> list[Hymn]:
    lines: list[str] = []
    for page_start, page_end in ranges:
        lines.extend(
            ordered_pdf_lines(
                pdf_path,
                page_start=page_start,
                page_end=page_end,
                column_break=column_break,
            )
        )
    return parse_hymns_from_lines(lines, source)


def parse_hymns_for_import(
    pdf_path: Path, column_break: bool = True
) -> list[dict[str, Any]]:
    """Parse a hymnal PDF for the in-app import dialog.

    Returns a list of ``{"number": int, "title": str, "stanzas": list[str]}``
    dicts (the format expected by ``PdfImportDialog``). ``column_break`` defaults
    to True because hymnals break columns at stanza boundaries; it only affects
    detected two-column pages.
    """
    lines = ordered_pdf_lines(pdf_path, column_break=column_break)
    headers = parse_hymn_headers(lines)
    hymns: list[dict[str, Any]] = []

    for index, (_header_line, number, title, body_start) in enumerate(
        headers, start=1
    ):
        next_header = headers[index][0] if index < len(headers) else len(lines)
        stanzas = parse_stanzas(lines[body_start:next_header])
        if not stanzas:
            continue
        hymns.append({"number": number, "title": title, "stanzas": stanzas})

    return hymns
