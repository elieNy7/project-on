from __future__ import annotations

import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


def extract_slides_from_pptx(pptx_path: Path) -> list[str]:
    """Extract text content from each slide in a PPTX file.
    Returns a list of strings, one per slide.
    """
    slides: list[str] = []

    if not pptx_path.exists():
        return slides

    try:
        with zipfile.ZipFile(pptx_path, "r") as zf:
            slide_files = sorted(
                [n for n in zf.namelist() if re.match(r"ppt/slides/slide\d+\.xml", n)],
                key=lambda x: int(re.search(r"slide(\d+)", x).group(1)),  # type: ignore
            )

            for slide_file in slide_files:
                with zf.open(slide_file) as f:
                    tree = ET.parse(f)
                    root = tree.getroot()

                    texts: list[str] = []
                    for p in root.iter():
                        if p.tag.endswith("}p"):
                            p_text = "".join(
                                [
                                    t.text
                                    for t in p.iter()
                                    if t.tag.endswith("}t") and t.text
                                ]
                            )
                            if p_text.strip():
                                texts.append(p_text.strip())

                    slide_text = "\n".join(texts).strip()
                    if slide_text:
                        slides.append(slide_text)

    except (zipfile.BadZipFile, ET.ParseError, KeyError):
        pass

    return slides


def _clean_stanza_text(text: str, title: str) -> str:
    """Remove the hymn title from the stanza ONLY if it appears as a distinct header.
    Does NOT remove the title if it is part of the lyrics/sentence.
    """
    cleaned = text.strip()
    title_lower = title.lower().strip()

    if not title_lower:
        return cleaned

    # 1. Check if the text matches the title exactly (case-insensitive)
    if cleaned.lower() == title_lower:
        return ""

    # 2. Check if the text starts with the title followed by a distinct separator
    #    or if the title is repeated (e.g. "Title Title! Lyrics")
    if cleaned.lower().startswith(title_lower):
        remaining = cleaned[len(title) :]  # No strip yet to check separator

        # Valid separators indicating a header:
        # - Newline (if we had them, but inputs are usually stripped of newlines by extract_slides)
        # - " - ", " : ", " | "
        # - Repetition of title (Title... Title...)

        # Check for repetition first (most common case for "Title\nTitle! Lyrics")
        # "Amazing Grace Amazing Grace!..."
        if remaining.strip().lower().startswith(title_lower):
            # Remove the first occurrence (the header)
            return remaining.strip()

        # Case: "Title\nLyrics". This is common in PowerPoint slides where
        # the title box is exported before the lyrics box.
        if remaining.startswith(("\n", "\r")):
            return remaining.strip()

        # Check for clear separators
        # We look at the immediate next chars

        # If remaining starts with space/punctuation that is a separator
        stripped_remaining = remaining.strip()

        # If ' - ', ' : ', ' | ', ' – ', ' — '
        separators = ["-", "–", "—", ":", "|", "."]
        # Note: "." might be "St. John", so be careful. But "Title." is usually header.

        if not stripped_remaining:
            # Case: "Title " -> Empty.
            return ""

        remaining[0] if remaining else ""

        # If it starts with non-word separator char (except typical punctuation found in lyrics like '!', '?', ',')
        # Typical lyric punctuation: '!', '?', ',', ';', '’', '\''

        should_remove = False

        # Case: "Title - Subtitle"
        for sep in separators:
            if stripped_remaining.startswith(sep):
                should_remove = True
                remaining = stripped_remaining[len(sep) :]  # Advance past sep
                break

        if should_remove:
            return remaining.strip()

    # We do NOT remove title if it's just a prefix of a sentence (e.g. "Amazing Grace! how sweet...")
    # We also REMOVED the "search inside string" logic which was causing false positives.

    return cleaned.strip()


def _is_chorus_slide(text: str) -> bool:
    """Check if a slide is a chorus.
    Matches:
    - Starts with Chœur, Choeur, Chorus, Refrain (case-insensitve)
    - Maybe preceded by a number/bullet: "1. Refrain", "- Refrain"
    - Maybe followed by colon: "Refrain:"
    """
    text_lower = text.strip().lower()
    # Regex to match start of string, optional numbering/bullets, then chorus keyword
    # ^(?:[\d\.\-\)\s]*)\b(ch[oeœ]ur|chorus|refrain)\b
    return bool(
        re.match(r"(?i)^(?:[\d\.\-\)\s]*)\b(ch[oeœ]ur|chorus|refrain)\b", text_lower)
    )


def _extract_chorus_text(text: str) -> str:
    """Extract chorus text, removing the label."""
    # Remove the label found by _is_chorus_slide
    # We want to keep the text AFTER the label.
    # Regex: replace the match with empty string.
    pattern = r"(?i)^(?:[\d\.\-\)\s]*)\b(ch[oeœ]ur|chorus|refrain)\b[\s:：\-–—]*"
    cleaned = re.sub(pattern, "", text.strip())
    return cleaned.strip()


def _normalize_for_match(value: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _strip_source_header(text: str, title: str = "") -> str:
    """Remove leading source headers such as '282. TITLE ( Eb ) *' from a slide."""
    cleaned = re.sub(r"[ \t]+", " ", str(text or "").strip())
    if not cleaned:
        return ""

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if len(lines) >= 2:
        if re.match(r"^\d{3,4}[a-z]?\.?\s*\S+", lines[0], re.IGNORECASE):
            cleaned = "\n".join(lines[1:]).strip()
            lines = lines[1:]

    if len(lines) >= 2:
        first_key = _normalize_for_match(lines[0])
        title_key = _normalize_for_match(title)
        next_starts_content = bool(
            re.match(
                r"^(?:\d{1,2}\s*[.\-)]\s*|[*•\-]\s*|ch[oeœ]ur\b|refrain\b)",
                lines[1],
                re.IGNORECASE,
            )
        )
        first_letters = [ch for ch in lines[0] if ch.isalpha()]
        first_is_title_like = bool(first_letters) and (
            sum(1 for ch in first_letters if ch.isupper()) / len(first_letters) >= 0.65
        )
        if next_starts_content and (
            (title_key and (first_key.startswith(title_key) or title_key.startswith(first_key)))
            or first_is_title_like
        ):
            cleaned = "\n".join(lines[1:]).strip()

    # Most AD slides start with a catalogue number, an uppercase title, and
    # often a chord marker before the actual lyric.
    chord_header = re.match(
        r"^\s*\d{1,4}[a-z]?\.?\s*.+?\(\s*[A-G](?:[#b])?m?\s*\)\s*[*.:\-–—]*\s*(.+)$",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if chord_header:
        return chord_header.group(1).lstrip("*.:-–—• ").strip()

    # Same pattern without parentheses, e.g. "29. J'AI RESOLU Bb".
    bare_chord_header = re.match(
        r"^\s*\d{1,4}[a-z]?\.?\s*.+?\s+[A-G](?:[#b])?m?\s*[*.:\-–—]+\s*(.+)$",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if bare_chord_header:
        return bare_chord_header.group(1).lstrip("*.:-–—• ").strip()

    uppercase_title_header = re.match(
        r"^\s*\d{1,4}[a-z]?\.?\s*([A-ZÀ-Ý0-9'’ ,!?;:\-]{3,}?)\s+((?:[A-ZÀ-Ý]\s+)?[A-ZÀ-Ýa-zà-ÿ][a-zà-ÿ].*)$",
        cleaned,
        flags=re.DOTALL,
    )
    if uppercase_title_header:
        return uppercase_title_header.group(2).lstrip("*.:-–—• ").strip()

    numbered = re.match(
        r"^\s*\d{1,4}[a-z]?\.?\s*([A-ZÀ-Ý0-9'’ ,!?;:\-]+?)\s+(.+)$",
        cleaned,
        flags=re.DOTALL,
    )
    if not numbered:
        return cleaned.lstrip("*•- ").strip()

    header = numbered.group(1).strip(" .:-–—")
    body = numbered.group(2).strip()
    if len(_normalize_for_match(header)) < 3:
        return cleaned

    body_key = _normalize_for_match(body)
    header_key = _normalize_for_match(header)
    title_key = _normalize_for_match(title)
    if body_key.startswith(header_key) or (
        title_key and header_key.startswith(title_key)
    ):
        return body.lstrip("*.:-–— ").strip()
    return cleaned.lstrip("*•- ").strip()


def _split_numbered_compound_stanza(text: str) -> list[str]:
    """Split one slide that contains multiple numbered couplets."""
    cleaned = str(text or "").strip()
    if not cleaned:
        return []

    marker_re = re.compile(r"(?:^|\n)\s*(\d{1,2})\.\s*")
    matches = list(marker_re.finditer(cleaned))
    if len(matches) < 2:
        return [cleaned]

    prefix = cleaned[: matches[0].start()].strip()
    parts: list[str] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(cleaned)
        body = cleaned[start:end].strip()
        if not body:
            continue
        if idx == 0 and prefix:
            prefix_key = _normalize_for_match(prefix)
            body_key = _normalize_for_match(body)
            if prefix_key and not body_key.startswith(prefix_key):
                body = f"{prefix}\n{body}"
        parts.append(body.lstrip("*•- ").strip())

    return parts or [cleaned]


def _strip_leading_verse_marker(text: str) -> str:
    return re.sub(r"^\s*\d{1,2}\s*[.\-)]\s*", "", str(text or "").strip()).strip()


def _post_process_stanzas(stanzas: list[str], title: str) -> list[str]:
    result: list[str] = []
    for stanza in stanzas:
        cleaned = _strip_source_header(stanza, title)
        if _is_chorus_slide(cleaned):
            if cleaned.strip():
                result.append(cleaned.strip())
            continue
        result.extend(
            _strip_leading_verse_marker(part)
            for part in _split_numbered_compound_stanza(cleaned)
        )
    return [s.strip() for s in result if s and s.strip()]


def parse_slides_as_hymn(slides: list[str], title: str) -> dict[str, Any] | None:
    """Core logic to parse a list of slide texts into a hymn structure."""
    if not slides:
        return None

    # First pass: clean slides, identify chorus, and track slide order
    cleaned_slides: list[dict[str, Any]] = []  # {"text": ..., "is_chorus": bool}
    chorus_text: str = ""
    chorus_label: str = "Chœur:"

    for slide_text in slides:
        # Check for chorus BEFORE cleaning (cleaning might remove labels if title matches label, unlikely but safe)
        is_chorus_label = _is_chorus_slide(slide_text)

        cleaned = _clean_stanza_text(slide_text, title)
        if not cleaned or cleaned.lower() == title.lower():
            continue

        if is_chorus_label:
            extracted = _extract_chorus_text(slide_text)
            extracted = _clean_stanza_text(extracted, title)
            if not chorus_text and extracted:
                chorus_text = extracted
                # Detect label from original text for display preference
                if "refrain" in slide_text.lower():
                    chorus_label = "Refrain:"
            cleaned_slides.append({"text": extracted, "is_chorus": True})
        else:
            cleaned_slides.append({"text": cleaned, "is_chorus": False})

    if not cleaned_slides:
        return None

    # Implicit chorus detection
    if not chorus_text:
        texts = [s["text"] for s in cleaned_slides]
        counts = Counter(texts)
        total_slides = len(texts)

        # Heuristics for implicit chorus:
        # 1. Repeats >= 2 times AND (is > 25% of total OR total slides <= 5)
        # 2. appears at even positions? (Too complex)

        found_implicit = False
        for txt, cnt in counts.most_common():
            if cnt < 2:
                break

            # If it's the most common and appears significantly
            if cnt >= 2:
                # Strengthening the heuristic:
                # If total slides is small (e.g., 4 slides: V1, C, V2, C), 30% is 1.2. So 2 counts is enough.
                # If total slides is large (e.g. 20), 2 counts might be accidental repetition.
                # Let's say if it repeats >= 3 times, it's definitely chorus.
                # If it repeats 2 times, we check percentage or if it's the ONLY repeated slide.

                is_valid = False
                if cnt >= 3 or (
                    cnt == 2 and (total_slides <= 8 or cnt >= total_slides * 0.2)
                ):
                    is_valid = True

                if is_valid:
                    chorus_text = txt
                    chorus_label = "Chœur:"  # Default
                    found_implicit = True
                    break

        if found_implicit:
            for s in cleaned_slides:
                if s["text"] == chorus_text:
                    s["is_chorus"] = True

    # Collect unique verses (skip chorus slides)
    verses: list[str] = []
    for s in cleaned_slides:
        if not s["is_chorus"] and s["text"]:
            verses.append(s["text"])

    if not verses:
        return None

    # Build final stanzas: verse, chorus, verse, chorus, ...
    stanzas: list[str] = []
    for i, verse in enumerate(verses):
        stanzas.append(verse)
        if chorus_text:
            stanzas.append(f"{chorus_label}\n{chorus_text}")

    stanzas = _post_process_stanzas(stanzas, title)
    if not stanzas:
        return None

    return {
        "title": title,
        "stanzas": stanzas,
    }


def parse_pptx_as_hymn(pptx_path: Path) -> dict[str, Any] | None:
    """Parse a PPTX file as a hymn.
    - Title: filename without extension
    - Stanzas: each slide becomes a stanza (title is removed from stanza text)
    - If a chorus is detected, it is repeated after each verse
    Returns None if no slides found.
    """
    path = Path(pptx_path)
    title = path.stem

    slides = extract_slides_from_pptx(path)
    return parse_slides_as_hymn(slides, title)


def parse_pptx_folder(folder_path: Path) -> list[dict[str, Any]]:
    """Parse all PPTX files in a folder as hymns.
    Returns a list of hymn dicts.
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        return []

    hymns: list[dict[str, Any]] = []
    for pptx_file in sorted(folder.glob("*.pptx")):
        hymn = parse_pptx_as_hymn(pptx_file)
        if hymn:
            hymns.append(hymn)

    for pptx_file in sorted(folder.glob("*.ppsx")):
        hymn = parse_pptx_as_hymn(pptx_file)
        if hymn:
            hymns.append(hymn)

    return hymns
