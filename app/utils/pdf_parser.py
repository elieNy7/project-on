"""Generic PDF parser for hymn import.
Supports multiple formats used in the project:
- Cantiques-Inspir: Number + Title in uppercase, Chœur marker
- Chant des victoire: Number + Title, numbered verses (1., 2.), Refrain
- Pene Na Yo: N. TITLE, Choeur marker
- Adorations: TITLE IN UPPERCASE, numbered verses (1-, 2-), Réfrain
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import fitz  # PyMuPDF

    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

try:
    import io

    import pytesseract
    from PIL import Image

    HAS_OCR = True
except ImportError:
    HAS_OCR = False


def read_pdf(pdf_path: Path) -> str:
    """Read all text from PDF using column-aware block extraction.

    Detects two-column layouts. If a page has no extractable text,
    it attempts OCR using pytesseract.
    """
    if not HAS_FITZ:
        raise ImportError(
            "PyMuPDF (fitz) is required for PDF import. Install with: pip install pymupdf"
        )

    doc = fitz.open(pdf_path)
    full_text = ""
    for page in doc:
        page_text = _extract_page_text_columns(page)

        # If no text found, try OCR
        if not page_text.strip() and HAS_OCR:
            try:
                # Render page to image
                pix = page.get_pixmap(
                    matrix=fitz.Matrix(2, 2)
                )  # 2x scale for better OCR
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))

                # Run OCR (French and English by default)
                # Note: tesseract must be installed on the system
                config = "--psm 3"  # Fully automatic page segmentation, but no OSD.
                page_text = pytesseract.image_to_string(
                    img, lang="fra+eng", config=config
                )
            except Exception as e:
                print(f"OCR Error on page {page.number}: {e}")

        full_text += page_text + "\n"

    doc.close()
    # Normalize typographic quotes to ASCII
    full_text = full_text.replace("\u2019", "'")  # right single quotation mark
    full_text = full_text.replace("\u2018", "'")  # left single quotation mark
    full_text = full_text.replace("\u201c", '"')  # left double quotation mark
    full_text = full_text.replace("\u201d", '"')  # right double quotation mark
    return full_text


def _extract_page_text_columns(page) -> str:
    """Extract text from a page with line-level precision and column-aware ordering.

    Uses dict-based extraction so every PDF line is handled individually.
    Detects two-column layouts by analysing line centre positions relative to the
    page centre.  Left column is read top-to-bottom first, then right column.
    Headers / footers are filtered out.
    """
    try:
        page_dict = page.get_text("dict")
    except Exception:
        return page.get_text("text")

    if not page_dict or "blocks" not in page_dict:
        return ""

    page_width = page.rect.width
    page_height = page.rect.height

    # ── Collect every individual line ──────────────────────────────────────
    all_lines: list[dict] = []
    for block in page_dict["blocks"]:
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            bbox = line["bbox"]
            parts = [span.get("text", "") for span in line.get("spans", [])]
            text = "".join(parts).strip()
            if not text:
                continue
            all_lines.append(
                {
                    "x0": bbox[0],
                    "y0": bbox[1],
                    "x1": bbox[2],
                    "y1": bbox[3],
                    "text": text,
                }
            )

    if not all_lines:
        return ""

    # ── Filter obvious header / footer lines ───────────────────────────────
    margin_top = page_height * 0.06
    margin_bottom = page_height * 0.94

    content_lines: list[dict] = []
    for ln in all_lines:
        # Always skip lines that match known header/footer text
        if _is_header_footer(ln["text"]):
            continue
        # Also skip bare page numbers that sit in the margin zone
        mid_y = (ln["y0"] + ln["y1"]) / 2
        if (mid_y < margin_top or mid_y > margin_bottom) and re.match(
            r"^\d{1,4}$", ln["text"].strip()
        ):
            continue
        content_lines.append(ln)

    if not content_lines:
        return ""

    # ── Detect two-column layout ───────────────────────────────────────────
    mid_x = page_width / 2
    gap_zone = page_width * 0.04

    left_lines = [
        ln for ln in content_lines if (ln["x0"] + ln["x1"]) / 2 < mid_x - gap_zone
    ]
    right_lines = [
        ln for ln in content_lines if (ln["x0"] + ln["x1"]) / 2 > mid_x + gap_zone
    ]
    center_lines = [
        ln
        for ln in content_lines
        if mid_x - gap_zone <= (ln["x0"] + ln["x1"]) / 2 <= mid_x + gap_zone
    ]

    is_two_column = len(left_lines) >= 3 and len(right_lines) >= 3

    if is_two_column:
        for ln in center_lines:
            (left_lines if (ln["x0"] + ln["x1"]) / 2 < mid_x else right_lines).append(
                ln
            )
        left_lines.sort(key=lambda l: l["y0"])
        right_lines.sort(key=lambda l: l["y0"])
        return _lines_to_text(left_lines) + "\n" + _lines_to_text(right_lines)

    content_lines.sort(key=lambda l: (l["y0"], l["x0"]))
    return _lines_to_text(content_lines)


def _lines_to_text(lines: list[dict]) -> str:
    """Join line dicts into text, inserting blank lines for paragraph-level gaps."""
    if not lines:
        return ""
    # Compute median inter-line gap to decide paragraph breaks
    gaps = []
    for i in range(1, len(lines)):
        g = lines[i]["y0"] - lines[i - 1]["y1"]
        if g > 0:
            gaps.append(g)
    if gaps:
        gaps_sorted = sorted(gaps)
        median_gap = gaps_sorted[len(gaps_sorted) // 2]
        para_threshold = max(median_gap * 1.8, 6)
    else:
        para_threshold = 6

    parts = [lines[0]["text"]]
    for i in range(1, len(lines)):
        g = lines[i]["y0"] - lines[i - 1]["y1"]
        if g > para_threshold:
            parts.append("")  # blank line → paragraph break
        parts.append(lines[i]["text"])
    return "\n".join(parts)


def _is_header_footer(text: str) -> bool:
    """Check if text matches a known header or footer pattern.

    These patterns are filtered regardless of where they appear on the page
    because they are never hymn content.
    """
    if not text:
        return True
    text = text.strip()
    # NOTE: standalone page numbers are NOT checked here because this
    # function is called for ALL lines (not just margin lines).  Hymn
    # numbers ("55", "131") look identical to page numbers and must not
    # be filtered.  Page numbers are handled separately in
    # _extract_page_text_columns via the margin-zone check.
    #
    # Common header/footer patterns (fragments are enough to match)
    patterns = [
        r"Petit Troupeau Tabernacle",
        r"branhammessage",
        r"Un Evangile Eternel",
        r"revienne sur terre",
        r"Evangile Eternel pour un peuple",
        r"crois seulement",
        r"chant des victoires",
        r"pene na yo",
        r"cantique d\'adoration",
        r"TABLE DES MATIERES",
        r"TABLE ANALYTIQUE",
        r"INDEX DES TITRES",
        r"MATIERE",
    ]
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False


def _is_uppercase_title_line(line: str) -> bool:
    """Check if a line looks like part of an uppercase title.

    Accepts lines where >= 70% of alphabetic characters are uppercase.
    More flexible than 75% to accommodate OCR errors.
    """
    stripped = line.strip()
    if not stripped or len(stripped) < 2:
        return False

    # Common OCR noise at the start of a title
    stripped = re.sub(r"^[\.\|\:\_\-\s]+", "", stripped)

    # Must start with an uppercase letter, digit, or common French accented caps
    if not re.match(r"^[A-ZÀÂÄÉÈÊËÏÎÔÙÛÜÇŒ0-9]", stripped):
        return False

    # Count alpha chars
    alpha_chars = [c for c in stripped if c.isalpha()]
    if not alpha_chars:
        # Might be just numbers (e.g. "123") - not a title line on its own
        return False

    upper_count = sum(1 for c in alpha_chars if c.isupper())
    return upper_count / len(alpha_chars) >= 0.70


def _format_title(title: str) -> str:
    """Format an uppercase title to Title Case with French-aware rules."""
    if not title:
        return title
    # Use Python's title() then fix common French small words
    result = title.title()
    # Fix apostrophe-based contractions: L'Amour → L'amour → keep L'Amour
    result = re.sub(
        r"([DLNSJCM]')([A-ZÀ-Ü])", lambda m: m.group(1) + m.group(2), result
    )
    return result


def clean_ocr_text(text: str) -> str:
    """Clean common OCR-specific errors and noise."""
    # Fix common character confusions
    # 0 -> O in words
    text = re.sub(r"([A-Z])0([A-Z])", r"\1O\2", text)
    # 1 -> I or l in words
    text = re.sub(r"([a-zA-Z])1([a-zA-Z])", r"\1l\2", text)
    # Removing vertical bars often seen in OCR of columns
    text = re.sub(r"^\s*\|\s*", "", text, flags=re.MULTILINE)
    # Removing weird punctuation clusters
    text = re.sub(r"[\_\-\=\~]{3,}", "", text)
    return text


def clean_latex_commands(text: str) -> str:
    """Remove LaTeX-style musical notation commands.

    Preserves newline structure so multi-line verses stay multi-line.
    """
    text = clean_ocr_text(text)
    text = re.sub(r"\\[lr]rep\s*", "", text)
    text = re.sub(r"\\rep\{\d+\}\s*", "", text)
    text = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", "", text)
    text = re.sub(r"\\[a-zA-Z]+\s*", "", text)
    # Collapse horizontal whitespace only (preserve newlines)
    text = re.sub(r"[^\S\n]+", " ", text)
    # Collapse runs of blank lines into a single blank line
    text = re.sub(r"\n[ \t]*\n+", "\n\n", text)
    # Strip leading/trailing whitespace on each line
    text = "\n".join(line.strip() for line in text.split("\n"))
    return text.strip()


def parse_hymns_from_pdf(pdf_path: Path, prefix: str = "PDF") -> list[dict[str, Any]]:
    """Parse hymns from a PDF file.
    Tries multiple formats to extract hymns.

    Args:
        pdf_path: Path to the PDF file
        prefix: Prefix for hymn titles (e.g., "CI", "CV", "PN", "AD")

    Returns:
        List of hymn dicts with 'number', 'title', and 'stanzas' keys

    """
    text = read_pdf(pdf_path)

    # Try different parsing strategies in order of specificity
    # Format 1: "N\nTITLE IN UPPERCASE" (Cantiques-Inspir style)
    hymns = _parse_format_number_newline_title(text, prefix)

    # Format 2: "N. TITLE IN UPPERCASE" (Pene Na Yo style)
    if not hymns:
        hymns = _parse_format_numbered_dot_title(text, prefix)

    # Format 3: "N Title" on same line (Chant des victoire style)
    if not hymns:
        hymns = _parse_format_number_space_title(text, prefix)

    # Format 4: "TITLE IN UPPERCASE" alone (Adorations style)
    if not hymns:
        hymns = _parse_format_uppercase_title(text, prefix)

    # Format 5: Simple fallback
    if not hymns:
        hymns = _parse_format_simple(text, prefix)

    return hymns


def _parse_format_number_newline_title(text: str, prefix: str) -> list[dict[str, Any]]:
    """Parse format: Number alone on line, then TITLE IN UPPERCASE on next line(s).
    Supports multi-line titles (e.g., "ALLELUIA, NOUS\\nRESSUSCITERONS").
    Also handles mixed formats: "N." or "N.TITLE" on a line.
    Used by: Cantiques-Inspir.pdf
    """
    lines = text.split("\n")

    # Phase 1: Find all hymn positions (number + multi-line title)
    hymn_positions = []  # (number, title, num_line_idx, body_line_idx)

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        number = None
        num_line = i
        title_parts = []

        # Case A: standalone number (e.g., "55") or with letter suffix (e.g., "131 a", "167a.")
        num_match = re.match(r"^(\d+)\s*[a-z]?\.?$", stripped)
        if num_match:
            number = int(num_match.group(1))

        # Case B: "N." alone or "N. " (e.g., "165.")
        if number is None:
            dot_match = re.match(r"^(\d+)\.\s*$", stripped)
            if dot_match:
                number = int(dot_match.group(1))

        # Case C: "N. TITLE" or "N.TITLE" on same line.
        # Keep chord suffixes such as Ab/Bb/G out of the title test.
        if number is None:
            inline_match = re.match(r"^(\d+)\.?\s+(.{3,})$", stripped)
            if inline_match:
                number = int(inline_match.group(1))
                inline_title = inline_match.group(2).strip()
                inline_title = re.sub(
                    r"\s+[A-G](?:[#b])?\s*$", "", inline_title
                ).strip()
                if _is_uppercase_title_line(inline_title):
                    title_parts.append(inline_title)
                else:
                    number = None

        if number is not None:
            # Collect consecutive uppercase lines as title (from next line onward).
            # Allow up to 1 blank line inside a multi-line title so that
            # titles wrapped across two lines with a blank gap are captured.
            j = i + 1
            blank_gap = 0
            while j < len(lines):
                next_stripped = lines[j].strip()
                if not next_stripped:
                    if not title_parts:
                        j += 1  # skip blanks between number and title
                        continue
                    blank_gap += 1
                    if blank_gap > 1:
                        break  # more than 1 consecutive blank → end of title
                    j += 1
                    continue
                if _is_uppercase_title_line(next_stripped):
                    title_parts.append(next_stripped)
                    blank_gap = 0  # reset after finding a title line
                    j += 1
                else:
                    break

            if title_parts:
                title = " ".join(title_parts)
                title = re.sub(r"\s+[A-G](?:[#b])?\s*$", "", title).strip()
                if len(title) > 2 and "TABLE DES" not in title:
                    hymn_positions.append((number, title, num_line, j))
            i = max(i + 1, j)
        else:
            i += 1

    if len(hymn_positions) < 5:
        return []

    # Phase 2: Build hymns with body text
    hymns = []
    seen_numbers = set()

    for idx, (number, title, num_line, body_start) in enumerate(hymn_positions):
        if number in seen_numbers:
            continue
        seen_numbers.add(number)

        # Body extends to the number line of the next hymn
        if idx + 1 < len(hymn_positions):
            body_end = hymn_positions[idx + 1][2]
        else:
            body_end = len(lines)

        body = "\n".join(lines[body_start:body_end]).strip()
        stanzas = _parse_stanzas_with_chorus(body)

        if stanzas:
            hymns.append(
                {
                    "number": number,
                    "title": f"{prefix}-{number}. {_format_title(title)}",
                    "stanzas": stanzas,
                }
            )

    hymns.sort(key=lambda h: h["number"])
    return hymns


def _parse_format_numbered_dot_title(text: str, prefix: str) -> list[dict[str, Any]]:
    """Parse format: N. TITLE IN UPPERCASE
    Used by: Pene Na Yo.pdf
    Example: "1. NZAMBE AZALI BOLINGO"
    """
    # Matches N. Title or N Title
    # Title can start with a letter, quote, or bracket
    hymn_pattern = re.compile(
        r'^(\d{1,3})[\.\s]+([A-ZÀÂÄÉÈÊËÏÎÔÙÛÜÇ\'"’\[][^\n]{3,})\n',
        re.MULTILINE,
    )

    matches = list(hymn_pattern.finditer(text))
    if len(matches) < 3:
        # Fallback to a even more loose pattern
        hymn_pattern = re.compile(
            r"^(\d{1,3})\.?\s+([A-ZÀÂÄÉÈÊËÏÎÔÙÛÜÇ][^\n]{3,})\n", re.MULTILINE
        )
        matches = list(hymn_pattern.finditer(text))

    if len(matches) < 3:
        return []

    hymns = []
    seen_numbers = set()

    for i, match in enumerate(matches):
        hymn_number = int(match.group(1))
        hymn_title = match.group(2).strip()

        if hymn_number in seen_numbers:
            continue
        seen_numbers.add(hymn_number)

        start_pos = match.end()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        hymn_text = text[start_pos:end_pos].strip()
        if prefix == "PN":
            stanzas = _parse_stanzas_lingala(hymn_text)
        else:
            stanzas = _parse_stanzas_with_chorus(hymn_text)

        if stanzas:
            hymns.append(
                {
                    "number": hymn_number,
                    "title": f"{prefix}-{hymn_number}. {_format_title(hymn_title)}",
                    "stanzas": stanzas,
                }
            )

    hymns.sort(key=lambda h: h["number"])
    return hymns


def _parse_format_number_space_title(text: str, prefix: str) -> list[dict[str, Any]]:
    """Parse format: N Title (number and title on same line)
    Used by: Chant des victoire.pdf
    Example: "5 Jésus ! Jésus !"
    """
    hymn_pattern = re.compile(
        r"^(\d+)\s+([A-ZÀ-ÜÉÈÊËÎÏÔÛÙÇŒœa-zà-ü][^\n]+?)\s*\n",
        re.MULTILINE,
    )

    matches = list(hymn_pattern.finditer(text))
    if len(matches) < 5:
        return []

    hymns = []
    seen_numbers = set()

    for i, match in enumerate(matches):
        hymn_number = int(match.group(1))
        hymn_title = match.group(2).strip()

        if hymn_number in seen_numbers:
            continue
        if len(hymn_title) < 3:
            continue
        if "TABLE" in hymn_title.upper() or "SOMMAIRE" in hymn_title.upper():
            continue

        seen_numbers.add(hymn_number)

        start_pos = match.end()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        hymn_text = text[start_pos:end_pos].strip()
        stanzas = _parse_stanzas_numbered(hymn_text)

        if stanzas:
            hymns.append(
                {
                    "number": hymn_number,
                    "title": f"{prefix}-{hymn_number}. {_format_title(hymn_title)}",
                    "stanzas": stanzas,
                }
            )

    hymns.sort(key=lambda h: h["number"])
    return hymns


def _parse_format_uppercase_title(text: str, prefix: str) -> list[dict[str, Any]]:
    """Parse format: TITLE IN UPPERCASE followed by numbered verses.
    Used by: adorations.pdf
    """
    hymn_pattern = re.compile(
        r"^([A-ZÀÂÄÉÈÊËÏÎÔÙÛÜÇ][A-ZÀÂÄÉÈÊËÏÎÔÙÛÜÇ\s\',\-!?\']+)\s*\n",
        re.MULTILINE,
    )

    matches = list(hymn_pattern.finditer(text))
    hymns = []
    seen_titles = set()
    hymn_number = 1

    for i, match in enumerate(matches):
        hymn_title = match.group(1).strip()

        if len(hymn_title) < 5 or hymn_title.upper() in ("RÉFRAIN", "REFRAIN"):
            continue

        title_key = hymn_title.upper()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        start_pos = match.end()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        hymn_text = text[start_pos:end_pos].strip()
        stanzas = _parse_stanzas_with_refrain(hymn_text)

        if stanzas:
            hymns.append(
                {
                    "number": hymn_number,
                    "title": f"{prefix}-{hymn_number}. {_format_title(hymn_title)}",
                    "stanzas": stanzas,
                }
            )
            hymn_number += 1

    return hymns


def _parse_format_simple(text: str, prefix: str) -> list[dict[str, Any]]:
    """Parse simple format: split by triple newlines.
    Fallback parser.
    """
    blocks = re.split(r"\n\s*\n\s*\n", text)

    hymns = []
    hymn_number = 1

    for block in blocks:
        block = block.strip()
        if not block or len(block) < 20:
            continue

        lines = block.split("\n")
        if not lines:
            continue

        title = lines[0].strip()
        if len(title) < 3:
            continue

        content = "\n".join(lines[1:]).strip()
        if not content:
            continue

        stanzas = _parse_stanzas_with_refrain(content)
        if not stanzas:
            stanzas = [content]

        hymns.append(
            {
                "number": hymn_number,
                "title": f"{prefix}-{hymn_number}. {_format_title(title)}",
                "stanzas": stanzas,
            }
        )
        hymn_number += 1

    return hymns


def _clean_body_text(text: str) -> str:
    """Clean hymn body text for reliable stanza parsing.

    - Removes embedded page numbers (standalone 1-4 digit lines),
      replacing them with blank lines so paragraph breaks survive.
    - Removes known header/footer fragments
    - Joins only *short* continuation fragments (< 15 chars starting
      with lowercase) back to their predecessor.  Longer lowercase
      lines are legitimate hymn lines in narrow-column PDFs and must
      be kept as-is.
    """
    lines = text.split("\n")

    # Pass 1 – remove junk lines
    #   Page numbers are replaced with a blank line ONLY when the
    #   preceding content line ends with punctuation (natural verse
    #   break).  Otherwise the page number is simply dropped so that
    #   verses spanning a page break stay connected.
    filtered: list[str] = []
    for line in lines:
        # Explicit removal of line decorators like ¶, *, and "
        line = line.replace("¶", "").replace("*", "").replace('"', "")
        stripped = line.strip()
        # Standalone page numbers
        if stripped and re.match(r"^\d{1,4}$", stripped):
            prev_content = ""
            for p in reversed(filtered):
                if p.strip():
                    prev_content = p.strip()
                    break
            if re.search(r"[.!?;:]\s*$", prev_content):
                filtered.append("")  # natural break → keep blank line
            # else: mid-verse page break → just drop it
            continue
        # Known header / footer text
        if stripped and _is_header_footer(stripped):
            continue
        filtered.append(stripped)

    # Pass 2 – join only SHORT continuation fragments
    #   In narrow-column PDFs a long line wraps, leaving a short tail
    #   on the next line (e.g. "pour\nvaincre").  Only join when:
    #     • the fragment starts with a lowercase letter
    #     • the fragment is SHORT (< 15 chars) — true broken wrap
    #     • it's not a chorus/refrain marker
    #     • the previous line doesn't end with sentence punctuation
    SHORT_FRAG = 15
    joined: list[str] = []
    for line in filtered:
        if not line:
            joined.append("")
            continue
        prev = joined[-1] if joined else ""
        is_short_fragment = (
            prev
            and line[0].islower()
            and len(line) < SHORT_FRAG
            and not re.match(
                r"^(chœur|choeur|refrain|chorus|réf\.?|ref\.?|ch\.?|r\.?)\b",
                line,
                re.IGNORECASE,
            )
            and not re.search(r"[.!?;:,]\s*$", prev)
        )
        if is_short_fragment:
            joined[-1] += " " + line
        else:
            joined.append(line)

    return "\n".join(joined)


def _parse_stanzas_with_chorus(text: str) -> list[str]:
    """Parse stanzas with Chœur / Choeur / Refrain / Chorus marker.

    Works line-by-line so that it handles:
    - Markers alone on a line ("Chœur:", "Refrain")
    - Markers with inline text ("Chœur: Gloire à Dieu")
    - Multiple markers (first chorus text is kept as canonical)
    - Verse-number boundaries ("1.", "2.") that end a chorus section
    - Two-column extractions where blank-line separators are missing
    """
    text = _clean_body_text(text)
    lines = text.split("\n")

    # Matches marker alone on line
    marker_solo_re = re.compile(
        r"^(?:Dernier\s+)?(Chœur|Choeur|Refrain|Chorus|Réf\.?|Ref\.?|Ch\.?|R\.?|Couplet|Strophe|Verset)\s*[:.]?\s*$",
        re.IGNORECASE,
    )
    # Matches marker with inline text: "Chœur: Gloire à Dieu"
    marker_inline_re = re.compile(
        r"^(?:Dernier\s+)?(Chœur|Choeur|Refrain|Chorus|Réf\.?|Ref\.?|Ch\.?|R\.?|Couplet|Strophe|Verset)\s*[:.-]\s+(.+)$",
        re.IGNORECASE,
    )
    # Verse-number start: "1.", "2. ", "1- ", "1) ", "1 ", "[1]", "(1)"
    # Also handle verses starting with common markers like " ' " or quotes
    verse_num_re = re.compile(r"^(\[|\()?\d+(\]|\))?\s*[.\-\)]?\s+|^\'")

    # ── Phase 1: locate all chorus sections ───────────────────────────
    chorus_text: str | None = None
    chorus_ranges: list[tuple[int, int]] = []  # (start, end) line indices

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        # Check for inline marker first (e.g. "Chœur: Gloire à Dieu")
        inline_m = marker_inline_re.match(stripped)
        if inline_m:
            sec_start = i
            chorus_lines: list[str] = [inline_m.group(2).strip()]
            # Collect continuation lines
            j = i + 1
            while j < len(lines):
                sl = lines[j].strip()
                if not sl:
                    break
                if marker_solo_re.match(sl) or marker_inline_re.match(sl):
                    break
                if verse_num_re.match(sl):
                    break
                chorus_lines.append(sl)
                j += 1
            if chorus_text is None and chorus_lines:
                chorus_text = "\n".join(chorus_lines)
            chorus_ranges.append((sec_start, j))
            i = j
            continue

        # Check for solo marker (e.g. "Chœur:" or "Refrain")
        if marker_solo_re.match(stripped):
            sec_start = i
            j = i + 1
            chorus_lines = []
            while j < len(lines):
                sl = lines[j].strip()
                # Empty line ends chorus only if we already collected text
                if not sl:
                    if chorus_lines:
                        break
                    j += 1
                    continue
                if marker_solo_re.match(sl) or marker_inline_re.match(sl):
                    break
                # A numbered verse marker ends the chorus section
                if verse_num_re.match(sl):
                    break
                chorus_lines.append(sl)
                j += 1
            if chorus_text is None and chorus_lines:
                chorus_text = "\n".join(chorus_lines)
            chorus_ranges.append((sec_start, j))
            i = j
        else:
            i += 1

    # ── Phase 2: build the verse-only body (strip all chorus sections) ──
    skip_set: set[int] = set()
    for start, end in chorus_ranges:
        for k in range(start, end):
            skip_set.add(k)

    verse_lines: list[str] = []
    for idx, line in enumerate(lines):
        if idx not in skip_set:
            verse_lines.append(line)

    verse_body = "\n".join(verse_lines)
    verses = _split_into_verses(verse_body)

    if not chorus_text:
        # Try implicit refrain detection before giving up on chorus
        result = _extract_implicit_refrain(verses)
        return result or (verses or _split_into_verses(text))

    # ── Phase 2b: trim oversized chorus that absorbed a verse ────────
    #   When the PDF has no blank line between chorus end and the next
    #   verse, the collector grabs both.  Detect this by comparing
    #   chorus line count to verse sizes and split the excess back out.
    if verses and chorus_text:
        cho_lines = chorus_text.split("\n")
        cho_lc = len(cho_lines)
        v_lcs = sorted(v.count("\n") + 1 for v in verses)
        med_v = v_lcs[len(v_lcs) // 2]

        if med_v >= 2 and cho_lc >= med_v * 1.6 and cho_lc >= med_v + 2:
            # Chorus likely absorbed a verse.  Keep first ~med_v lines
            # as chorus, extract the rest as a recovered verse.
            split_at = med_v
            chorus_text = "\n".join(cho_lines[:split_at])
            recovered = "\n".join(cho_lines[split_at:]).strip()
            if recovered:
                recovered_parts = _split_at_natural_break(recovered, med_v)
                for offset, part in enumerate(recovered_parts):
                    verses.insert(1 + offset, part)  # verse(s) absorbed by chorus

    # ── Phase 3: interleave verses with chorus ────────────────────────
    # Determine the canonical chorus label
    chorus_label = "Chœur:"
    for start, _ in chorus_ranges:
        sl = lines[start].strip()
        m = re.match(
            r"^(?:Dernier\s+)?(Chœur|Choeur|Refrain|Chorus|Réf\.?|Ref\.?|Ch\.?|R\.?)",
            sl,
            re.IGNORECASE,
        )
        if m:
            word = m.group(1).lower()
            if word.startswith("ref") or word.startswith("réf") or word == "r":
                chorus_label = "Refrain:"
            elif word.startswith("ch") or word == "c":
                chorus_label = "Chœur:"
            break

    result: list[str] = []
    for v in verses:
        v = v.strip()
        if v:
            result.append(v)
            result.append(f"{chorus_label}\n{chorus_text}")
    return result or _split_into_verses(text)


def _extract_implicit_refrain(verses: list[str]) -> list[str] | None:
    """Detect and extract an implicit refrain from verse endings.

    Many hymns repeat the same 1-3 lines at the end of each verse
    without an explicit "Chœur" or "Refrain" marker.  When ≥60% of
    verses share common ending lines, those lines are extracted as a
    separate refrain stanza and interleaved after each verse.

    Returns None if no implicit refrain is detected.
    """
    if len(verses) < 3:
        return None

    # Try matching 1, 2, or 3 ending lines (prefer longest match)
    best_refrain: str | None = None
    best_n = 0

    for n_lines in (3, 2, 1):
        endings: dict[str, int] = {}
        valid_count = 0

        for v in verses:
            lines = v.strip().split("\n")
            if len(lines) <= n_lines:
                continue  # verse too short to have an n_lines ending
            valid_count += 1
            ending = "\n".join(line.strip() for line in lines[-n_lines:])
            endings[ending] = endings.get(ending, 0) + 1

        if not endings or valid_count < 3:
            continue

        most_common = max(endings, key=endings.get)
        count = endings[most_common]

        # Require ≥60% of valid verses to share this ending
        if count >= 3 and count >= valid_count * 0.6:
            best_refrain = most_common
            best_n = n_lines
            break  # longest match wins

    if not best_refrain or best_n == 0:
        return None

    # Build result: strip refrain lines from each verse, interleave
    result: list[str] = []
    best_refrain.split("\n")

    for v in verses:
        lines = v.strip().split("\n")
        # Only strip if this verse actually ends with the refrain
        v_ending = "\n".join(line.strip() for line in lines[-best_n:])
        if v_ending == best_refrain and len(lines) > best_n:
            trimmed = "\n".join(lines[:-best_n]).strip()
            if trimmed:
                result.append(trimmed)
            else:
                result.append(v)
        else:
            result.append(v)
        result.append(f"Refrain:\n{best_refrain}")

    return result


def _parse_stanzas_numbered(text: str) -> list[str]:
    """Parse stanzas with numbered verses (1., 2., etc.) and Refrain.
    Used by Chant des victoire.

    Handles three chorus styles:
    - Explicit Refrain/Chœur markers embedded in verse text
    - "etc." pattern: verse 1 contains full chorus, subsequent verses
      end with "etc." referencing it
    - No chorus at all (just numbered verses)
    """
    text = _clean_body_text(text)
    verse_pattern = re.compile(r"(?:^|\n)\s*(\d+)\.\s+", re.MULTILINE)
    matches = list(verse_pattern.finditer(text))

    if not matches:
        cleaned = clean_latex_commands(text)
        return [cleaned] if cleaned else []

    marker_re = re.compile(
        r"^(?:Dernier\s+)?(Chœur|Choeur|Refrain|Chorus)\s*[:.]?\s*",
        re.IGNORECASE,
    )

    # ── Phase 1: extract raw verse blocks ─────────────────────────────
    raw_verses: list[dict] = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        block = clean_latex_commands(block)

        verse_lines: list[str] = []
        refrain_lines: list[str] = []
        in_refrain = False
        etc_hint = ""

        for line in block.split("\n"):
            sl = line.strip()
            if not sl:
                if in_refrain and refrain_lines:
                    break
                continue

            # Explicit refrain marker
            m = marker_re.match(sl)
            if m:
                in_refrain = True
                rest = sl[m.end() :].strip()
                if rest:
                    refrain_lines.append(rest)
                continue

            # "etc." at end of line → chorus reference
            etc_m = re.search(r",?\s*etc\.?\s*$", sl, re.IGNORECASE)
            if etc_m:
                before = sl[: etc_m.start()].strip()
                if before:
                    etc_hint = before
                # Don't add this line to verse_lines
                continue

            if in_refrain:
                refrain_lines.append(sl)
            else:
                verse_lines.append(sl)

        raw_verses.append(
            {
                "lines": verse_lines,
                "refrain": refrain_lines,
                "etc_hint": etc_hint,
            }
        )

    # ── Phase 2: detect chorus ────────────────────────────────────────
    chorus_text = ""
    chorus_label = "Refrain:"

    # Strategy A: explicit refrain markers
    for rv in raw_verses:
        if rv["refrain"] and not chorus_text:
            chorus_text = "\n".join(rv["refrain"])
            break

    # Strategy B: "etc." pattern — extract chorus from verse 1
    if not chorus_text and len(raw_verses) >= 2:
        etc_hint = ""
        for rv in raw_verses[1:]:
            if rv["etc_hint"]:
                etc_hint = rv["etc_hint"]
                break

        v1_lines = raw_verses[0]["lines"]
        if etc_hint and v1_lines:
            # Find where the etc_hint text starts in verse 1
            hint_prefix = etc_hint[: min(25, len(etc_hint))]
            for idx, vl in enumerate(v1_lines):
                if vl.strip().startswith(hint_prefix):
                    chorus_text = "\n".join(v1_lines[idx:])
                    raw_verses[0]["lines"] = v1_lines[:idx]
                    break

            # Fallback: use line count of subsequent verses as reference
            if not chorus_text:
                ref_count = None
                for rv in raw_verses[1:]:
                    if rv["etc_hint"]:
                        ref_count = len(rv["lines"])
                        break
                if ref_count and ref_count < len(v1_lines):
                    chorus_text = "\n".join(v1_lines[ref_count:])
                    raw_verses[0]["lines"] = v1_lines[:ref_count]

    # ── Phase 3: build final stanzas ──────────────────────────────────
    verses: list[str] = []
    for rv in raw_verses:
        vt = "\n".join(rv["lines"]).strip()
        if vt:
            verses.append(vt)

    if chorus_text and verses:
        final: list[str] = []
        for v in verses:
            final.append(v)
            final.append(f"{chorus_label}\n{chorus_text}")
        return final

    return verses or []


def _parse_stanzas_lingala(text: str) -> list[str]:
    """Parse stanzas for Lingala hymns (Pene Na Yo style).
    Handles Choeur marker (solo and inline).
    """
    text = _clean_body_text(text)
    lines = text.strip().split("\n")

    marker_re = re.compile(
        r"^(Chœur|Choeur|Refrain|Chorus)\s*[:.]?\s*$",
        re.IGNORECASE,
    )
    marker_inline_re = re.compile(
        r"^(Chœur|Choeur|Refrain|Chorus)\s*[:.]\s+(.+)$",
        re.IGNORECASE,
    )

    stanzas: list[str] = []
    chorus_text = ""
    current_verse: list[str] = []
    in_chorus = False

    for line in lines:
        line = line.strip()
        if not line:
            # Blank line ends chorus if we have content
            if in_chorus and chorus_text:
                in_chorus = False
            continue

        # Inline marker: "Choeur: text"
        inline_m = marker_inline_re.match(line)
        if inline_m:
            if current_verse:
                stanzas.append(" ".join(current_verse))
                current_verse = []
            in_chorus = True
            if not chorus_text:
                chorus_text = inline_m.group(2).strip()
            continue

        # Solo marker: "Choeur" alone
        if marker_re.match(line):
            if current_verse:
                stanzas.append(" ".join(current_verse))
                current_verse = []
            in_chorus = True
            continue

        # Standalone verse number (e.g. "2.")
        if re.match(r"^\d+\.\s*$", line):
            if in_chorus:
                in_chorus = False
            continue

        # Numbered verse start (e.g. "2. text")
        if re.match(r"^\d+\.\s", line):
            if in_chorus:
                in_chorus = False
            # Fall through to add to current_verse

        if in_chorus:
            if not chorus_text:
                chorus_text = line
            else:
                chorus_text += " " + line
            continue

        current_verse.append(line)

    if current_verse:
        stanzas.append(" ".join(current_verse))

    if chorus_text and stanzas:
        final_stanzas: list[str] = []
        for verse in stanzas:
            final_stanzas.append(verse)
            final_stanzas.append(f"Chœur:\n{chorus_text}")
        return final_stanzas

    return stanzas or ([text] if text else [])


def _parse_stanzas_with_refrain(text: str) -> list[str]:
    """Parse stanzas with Réfrain/Refrain marker (Adorations style).
    Handles numbered verses (1-, 2-) and refrain.
    Also handles inline refrain text: "Refrain: text here".
    """
    text = _clean_body_text(text)
    lines = text.strip().split("\n")

    marker_re = re.compile(
        r"^(?:Dernier\s+)?(Réfrain|Refrain|Choeur|Chœur|Chorus)\s*[:.]?\s*$",
        re.IGNORECASE,
    )
    marker_inline_re = re.compile(
        r"^(?:Dernier\s+)?(Réfrain|Refrain|Choeur|Chœur|Chorus)\s*[:.]\s+(.+)$",
        re.IGNORECASE,
    )

    stanzas: list[str] = []
    chorus_text = ""
    current_verse: list[str] = []
    in_chorus = False

    for line in lines:
        line = line.strip()
        if not line:
            # Blank line: if we're in a chorus and have content, end it
            if in_chorus and current_verse:
                if not chorus_text:
                    chorus_text = "\n".join(current_verse)
                current_verse = []
                in_chorus = False
            continue

        # Check inline marker (e.g. "Refrain: Gloire à Dieu")
        inline_m = marker_inline_re.match(line)
        if inline_m:
            if current_verse and not in_chorus:
                stanzas.append("\n".join(current_verse))
                current_verse = []
            elif current_verse and in_chorus:
                if not chorus_text:
                    chorus_text = "\n".join(current_verse)
                current_verse = []
            in_chorus = True
            current_verse.append(inline_m.group(2).strip())
            continue

        # Check solo marker (e.g. "Refrain" alone)
        if marker_re.match(line):
            if current_verse:
                if not in_chorus:
                    stanzas.append("\n".join(current_verse))
                elif not chorus_text:
                    chorus_text = "\n".join(current_verse)
                current_verse = []
            in_chorus = True
            continue

        # Check numbered verse start (e.g. "2- text" or "2. text")
        verse_match = re.match(r"^(\d+)[\-\.\)]\s*(.*)$", line)
        if verse_match:
            if current_verse:
                if in_chorus:
                    if not chorus_text:
                        chorus_text = "\n".join(current_verse)
                else:
                    stanzas.append("\n".join(current_verse))
                current_verse = []
            in_chorus = False
            rest = verse_match.group(2).strip()
            if rest:
                current_verse.append(rest)
            continue

        current_verse.append(line)

    # Flush remaining
    if current_verse:
        if in_chorus:
            if not chorus_text:
                chorus_text = "\n".join(current_verse)
        else:
            stanzas.append("\n".join(current_verse))

    if chorus_text and stanzas:
        final_stanzas: list[str] = []
        for verse in stanzas:
            final_stanzas.append(verse)
            final_stanzas.append(f"Refrain:\n{chorus_text}")
        return final_stanzas

    return stanzas or []


def _split_into_verses(body: str) -> list[str]:
    """Split hymn body into verses based on numbered markers or blank lines."""
    if not body.strip():
        return []

    # Primary: split on blank lines
    parts = re.split(r"\n\s*\n+", body.strip())

    # If only one part, try splitting on lines starting with ' (typical for Crois Seulement)
    if len(parts) == 1:
        parts = re.split(r"\n(?=\')", body.strip())

    verses = [p.strip() for p in parts if p.strip()]

    # If blank-line splitting produced multiple results, check if any
    # single part still contains numbered verses that need sub-splitting
    if len(verses) > 1:
        expanded: list[str] = []
        for v in verses:
            subs = _try_split_numbered(v)
            expanded.extend(subs)
        verses = expanded
    elif len(verses) == 1:
        # Fallback: try splitting on numbered markers
        subs = _try_split_numbered(verses[0])
        if len(subs) > 1:
            verses = subs

    # Post-process: split oversized verse blocks
    verses = _post_split_large_verses(verses)

    # Strip leading verse numbers from each verse (e.g. "1. text" → "text")
    cleaned: list[str] = []
    for v in verses:
        v = re.sub(r"^\d+[.\-\)]\s*", "", v.strip())
        if v:
            cleaned.append(v)
    return cleaned


def _post_split_large_verses(verses: list[str]) -> list[str]:
    """Detect and split verse blocks that are much larger than others.

    When some verses are ~5 lines and one is ~9 lines, the large one
    very likely contains two merged couplets.  Tries to split at a
    *natural* boundary (sentence-ending punctuation followed by an
    uppercase-starting line) near the expected verse length.
    """
    if len(verses) < 2:
        if verses and verses[0].count("\n") >= 7:
            return _split_single_block(verses[0])
        return verses

    # Compute line counts — use the smallest verse as reference
    line_counts = sorted(v.count("\n") + 1 for v in verses)
    ref_lc = line_counts[max(0, len(line_counts) // 4)]

    if ref_lc < 2:
        return verses

    # A verse is "oversized" if it has > 1.5× the reference
    threshold = int(ref_lc * 1.5)

    result: list[str] = []
    for v in verses:
        lc = v.count("\n") + 1
        if lc > threshold and lc >= int(ref_lc * 1.6):
            parts = _split_at_natural_break(v, ref_lc)
            result.extend(parts)
        else:
            result.append(v)
    return result


def _split_at_natural_break(text: str, target_lc: int) -> list[str]:
    """Split an oversized verse block at natural boundaries.

    A natural boundary is a line ending with sentence punctuation (.!?)
    followed by a line starting with an uppercase letter.  The split
    closest to *target_lc* lines from the start wins.
    """
    lines = text.split("\n")
    n = len(lines)

    # Find candidate split points
    candidates: list[int] = []
    for i in range(1, n):
        prev = lines[i - 1].strip()
        curr = lines[i].strip()
        if prev and curr and re.search(r"[.!?]\s*$", prev) and curr[0].isupper():
            candidates.append(i)

    if candidates:
        # Pick the candidate closest to target_lc
        best = min(candidates, key=lambda c: abs(c - target_lc))
        part1 = "\n".join(lines[:best]).strip()
        part2 = "\n".join(lines[best:]).strip()
        # Recursively split part2 if it's also oversized
        if part2.count("\n") + 1 > int(target_lc * 1.6):
            parts2 = _split_at_natural_break(part2, target_lc)
            return [part1] + parts2 if part1 else parts2
        return [p for p in (part1, part2) if p]

    # No natural break found — fall back to even splitting
    n_chunks = round(n / target_lc)
    n_chunks = max(n_chunks, 2)
    actual_size = n // n_chunks
    remainder = n % n_chunks
    result: list[str] = []
    pos = 0
    for ci in range(n_chunks):
        sz = actual_size + (1 if ci < remainder else 0)
        chunk = "\n".join(lines[pos : pos + sz]).strip()
        if chunk:
            result.append(chunk)
        pos += sz
    return result


def _split_single_block(text: str) -> list[str]:
    """Split a single large block of text into verses by line-count heuristic.

    Tries common hymn verse lengths (4, 6, 8 lines) and picks the best fit.
    """
    lines = text.strip().split("\n")
    n = len(lines)
    if n <= 6:
        return [text]

    # Try common verse lengths, prefer 4 then 6 then 8
    for vlen in [4, 6, 8, 3, 5]:
        if n % vlen == 0:
            n_verses = n // vlen
            if 2 <= n_verses <= 10:
                return ["\n".join(lines[i : i + vlen]) for i in range(0, n, vlen)]

    # Try the best approximate fit
    for vlen in [6, 4, 8]:
        n_verses = round(n / vlen)
        if n_verses >= 2:
            actual_size = n // n_verses
            remainder = n % n_verses
            result: list[str] = []
            pos = 0
            for ci in range(n_verses):
                sz = actual_size + (1 if ci < remainder else 0)
                chunk = "\n".join(lines[pos : pos + sz]).strip()
                if chunk:
                    result.append(chunk)
                pos += sz
            if len(result) >= 2:
                return result

    return [text]


def _try_split_numbered(block: str) -> list[str]:
    """Try to split a text block on numbered verse markers.

    Recognises: "1. ", "2. ", "1- ", "2- ", "1) ", "1 " etc.
    Returns the original block as single-element list if no markers found.
    """
    # Match numbered markers at line start: "1. ", "2- ", "1) ", "(1) ", "[1] "
    parts = re.split(r"(?:^|\n)\s*(?:[\[\(]?\d+[\]\)]?)\s*[.\-\)]?\s+", block)
    # re.split with a capture group interleaves numbers and text:
    # ['preamble', '1', 'verse1...', '2', 'verse2...', ...]
    if len(parts) < 3:
        return [block.strip()] if block.strip() else []

    result: list[str] = []
    # Skip preamble (parts[0]) if empty, otherwise include it
    preamble = parts[0].strip()
    if preamble:
        result.append(preamble)
    # Walk pairs: (number, text)
    for idx in range(1, len(parts) - 1, 2):
        verse_text = parts[idx + 1].strip() if idx + 1 < len(parts) else ""
        if verse_text:
            result.append(verse_text)
    return result or [block.strip()]
