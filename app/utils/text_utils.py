"""Shared text utilities used across controllers and DAOs."""

from __future__ import annotations

import html
import re
import unicodedata

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HYMN_SECTION_LABEL_RE = re.compile(
    r"""
    \A\s*
    (?:[\[(]\s*)?
    (?:\d{1,2}\s*[.)-]\s*|[-*•]\s*)?
    (?:
        dernier\s+refrain
        |dernier\s+ch(?:oe|\u0153)ur
        |ch(?:oe|\u0153)ur
        |refrain
        |chorus
    )
    (?:\s*[\])])?
    (?:\s*[:.;,\-–—]\s*|\s+|\s*\n+|\s*\Z)
    """,
    re.IGNORECASE | re.VERBOSE,
)


def clean_text(value: object) -> str:
    """Clean text: strip HTML, control chars, BOM, pilcrow markers, collapse whitespace."""
    s = str(value or "")
    s = html.unescape(s)
    s = s.replace("\ufeff", "").replace("\u200b", "")
    s = s.replace("\ufffd", "")
    s = s.replace("\u00a0", " ").replace("\u202f", " ")
    s = s.replace("\u00c2 ", " ").replace("\u00c2\u00a0", " ")  # "Â " artifact
    s = s.replace("\r", "")
    s = s.replace("<br/>", "\n").replace("<br />", "\n").replace("<br>", "\n")
    s = s.replace("&nbsp;", " ")
    s = _HTML_TAG_RE.sub("", s)
    s = re.sub(r"(^|\n)\s*\u00b6\s*", r"\1", s)  # pilcrow ¶
    s = s.replace("\u00b6", "")
    s = _CONTROL_CHARS_RE.sub("", s)
    s = re.sub(r"[\t ]+", " ", s)
    return s.strip()


def strip_hymn_projection_label(value: object) -> str:
    """Remove leading chorus/refrain labels from hymn text before projection."""
    text = clean_text(value)
    previous = None
    while text and text != previous:
        previous = text
        text = _HYMN_SECTION_LABEL_RE.sub("", text, count=1).strip()
    return text


def format_hymn_for_obs_lower_third(value: object) -> str:
    """Format hymn lyrics for OBS lower thirds, independent of local projection line breaks."""
    text = strip_hymn_projection_label(value)
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = strip_hymn_projection_label(raw_line)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)

    flattened = " ".join(lines)
    flattened = re.sub(r"\s+([,.;:!?])", r"\1", flattened)
    flattened = re.sub(r"\s+", " ", flattened)
    return flattened.strip()


def format_hymn_reference_for_obs(value: object) -> str:
    """Keep hymn OBS references in one broadcast-style line."""
    reference = clean_text(value)
    reference = re.sub(r"\s*\n+\s*", " - ", reference)
    reference = re.sub(r"\s+", " ", reference)
    return reference.strip(" -")


def unaccent(text: str) -> str:
    """Strip accents and lowercase for accent-insensitive comparison."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn").lower()


# ── Slide text splitting ────────────────────────────────────────────────────
MAX_CHARS_PER_SLIDE = 280
MIN_CHARS_PER_SLIDE = 60


def _force_split(text: str, limit: int) -> list[str]:
    """Force-split an oversized sentence at the best available break."""
    tokens = re.findall(r"\S+(?:\s+|$)", text)
    parts: list[str] = []
    current = ""
    break_chars = {".", ",", ";", ":", "!", "?"}
    for tok in tokens:
        if len(current) + len(tok) > limit and current:
            parts.append(current.strip())
            current = ""
        current += tok
        stripped = tok.strip()
        if stripped and stripped[-1] in break_chars and len(current) >= limit * 0.55:
            parts.append(current.strip())
            current = ""
    if current.strip():
        parts.append(current.strip())
    return parts or [text]


def _rebalance(slides: list[str], limit: int, min_chars: int) -> list[str]:
    """Rebalance slides so the last one isn't too short."""
    if len(slides) < 2:
        return slides
    while len(slides) >= 2 and len(slides[-1]) < min_chars:
        last = slides.pop()
        prev = slides.pop()
        combined = prev + " " + last
        if len(combined) <= limit:
            slides.append(combined)
        else:
            words = combined.split()
            mid = len(words) // 2
            part1 = " ".join(words[:mid])
            part2 = " ".join(words[mid:])
            if len(part1) <= limit and len(part2) <= limit:
                slides.append(part1)
                slides.append(part2)
            else:
                slides.append(prev)
                slides.append(last)
            break
    return slides


def split_text_into_slides(
    text: str,
    max_chars: int = MAX_CHARS_PER_SLIDE,
    min_chars: int = MIN_CHARS_PER_SLIDE,
) -> list[str]:
    """Split text into balanced, readable slides.

    Two-phase algorithm: break into sentences/segments at natural boundaries
    (paragraph breaks, sentence-ending punctuation), then greedily merge and
    rebalance so slides have roughly equal length without exceeding *max_chars*.
    """
    raw = str(text or "").strip()
    if not raw:
        return []

    raw = raw.replace("\r", "")
    raw = re.sub(r"[\t ]+", " ", raw)
    raw = re.sub(r"\n[ \t]+", "\n", raw)

    if len(raw) <= max_chars:
        return [raw]

    paragraphs = re.split(r"\n\s*\n+", raw)
    sentences: list[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        for part in re.split(r"(?<=[.!?;:])\s+", para):
            part = part.strip()
            if part:
                sentences.append(part)

    if not sentences:
        return [raw]

    slides: list[str] = []
    current = ""
    for s in sentences:
        candidate = (current + " " + s).strip() if current else s
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                slides.append(current)
            if len(s) > max_chars:
                forced = _force_split(s, max_chars)
                slides.extend(forced[:-1])
                current = forced[-1]
            else:
                current = s
    if current:
        slides.append(current)

    return _rebalance(slides, max_chars, min_chars)
