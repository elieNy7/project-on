"""Shared text utilities used across controllers and DAOs."""

from __future__ import annotations

import html
import re
import unicodedata

from app.utils import constants
from app.utils.constants import MAX_CHARS_PER_SLIDE, MIN_CHARS_PER_SLIDE  # noqa: F401

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
# Valeurs centralisées dans app.utils.constants.
MAX_CHARS_PER_SLIDE = constants.MAX_CHARS_PER_SLIDE
MIN_CHARS_PER_SLIDE = constants.MIN_CHARS_PER_SLIDE


# Force des coupures (plus la valeur est haute, plus la coupure est naturelle).
_BREAK_PARAGRAPH = 4
_BREAK_LINE = 3
_BREAK_SENTENCE = 2
_BREAK_CLAUSE = 1
_BREAK_WORD = 0

# Pénalité de coupure selon sa force : on coupe entre deux paragraphes ou
# deux lignes avant de couper une phrase, et une phrase avant un mot.
_BREAK_PENALTY = {
    _BREAK_PARAGRAPH: 0.0,
    _BREAK_LINE: 0.05,
    _BREAK_SENTENCE: 0.15,
    _BREAK_CLAUSE: 0.6,
    _BREAK_WORD: 2.0,
}

# Abréviations suivies d'un point qui ne terminent pas la phrase.
_ABBREVIATIONS = {
    "m", "mm", "mme", "mlle", "dr", "st", "ste", "fr", "sr", "jr", "mr", "mrs",
    "rév", "rev", "frère", "soeur", "p", "pp", "v", "vv", "ch", "chap", "cf",
    "etc", "no", "n°", "env", "vol", "av", "apr", "j.-c", "c-à-d", "ex",
}

_SENTENCE_END_RE = re.compile(r"[.!?…]+[»\"”’')\]]*$")
_CLAUSE_END_RE = re.compile(r"[,;:—–]$")


def _is_sentence_end(token: str, next_token: str) -> bool:
    """Vrai si ``token`` termine une phrase (et pas une abréviation)."""
    if not _SENTENCE_END_RE.search(token):
        return False
    word = token.rstrip(".!?…»\"”’')]").lower().lstrip("«\"“‘(")
    if token.rstrip("»\"”’')]").endswith(".") and not token.endswith(".."):
        if word in _ABBREVIATIONS or (len(word) == 1 and word.isalpha()):
            return False
        # « 3. » suivi d'une minuscule : numérotation, pas une fin de phrase.
        if word.isdigit() and next_token[:1].islower():
            return False
    return True


def _units_of_line(line: str, limit: int) -> list[tuple[str, int]]:
    """Découpe une ligne en unités (phrase, proposition ou mot).

    Chaque unité porte la force de la coupure qui la SUIT dans la ligne.
    Une phrase qui tient dans ``limit`` reste entière ; sinon elle est
    découpée à ses virgules/points-virgules, puis entre les mots.
    """
    tokens = line.split()
    if not tokens:
        return []
    sentences: list[list[str]] = [[]]
    for index, token in enumerate(tokens):
        sentences[-1].append(token)
        following = tokens[index + 1] if index + 1 < len(tokens) else ""
        if following and _is_sentence_end(token, following):
            sentences.append([])
    sentences = [words for words in sentences if words]

    units: list[tuple[str, int]] = []
    for words in sentences:
        sentence = " ".join(words)
        if len(sentence) <= limit:
            units.append((sentence, _BREAK_SENTENCE))
            continue
        clauses: list[list[str]] = [[]]
        for index, word in enumerate(words):
            clauses[-1].append(word)
            if index + 1 < len(words) and _CLAUSE_END_RE.search(word):
                clauses.append([])
        for clause_words in clauses:
            clause = " ".join(clause_words)
            if len(clause) <= limit:
                units.append((clause, _BREAK_CLAUSE))
                continue
            for word in clause_words:
                if len(word) > limit:  # URL, mot démesuré : coupe brute
                    for pos in range(0, len(word), limit):
                        units.append((word[pos : pos + limit], _BREAK_WORD))
                else:
                    units.append((word, _BREAK_WORD))
            units[-1] = (units[-1][0], _BREAK_CLAUSE)
        units[-1] = (units[-1][0], _BREAK_SENTENCE)
    return units


def _text_units(raw: str, limit: int) -> list[tuple[str, int]]:
    """Unités du texte : (morceau, force de la coupure qui le suit)."""
    units: list[tuple[str, int]] = []
    paragraphs = [p for p in re.split(r"\n\s*\n+", raw) if p.strip()]
    for p_index, para in enumerate(paragraphs):
        lines = [line.strip() for line in para.split("\n") if line.strip()]
        for l_index, line in enumerate(lines):
            line_units = _units_of_line(line, limit)
            if not line_units:
                continue
            last_line = l_index == len(lines) - 1
            strength = _BREAK_PARAGRAPH if last_line else _BREAK_LINE
            line_units[-1] = (line_units[-1][0], strength)
            units.extend(line_units)
    if units:
        units[-1] = (units[-1][0], _BREAK_PARAGRAPH)
    return units


def _join_units(units: list[tuple[str, int]], keep_line_breaks: bool) -> str:
    parts: list[str] = []
    for index, (chunk, _strength) in enumerate(units):
        parts.append(chunk)
        if index < len(units) - 1:
            strength = units[index][1]
            parts.append("\n" if keep_line_breaks and strength >= _BREAK_LINE else " ")
    return "".join(parts)


def _unit_span_length(lengths: list[int], i: int, j: int) -> int:
    """Longueur des unités [i, j) jointes (un séparateur entre chacune)."""
    return lengths[j] - lengths[i] + (j - i - 1)


def _partition_units(
    units: list[tuple[str, int]], limit: int, min_chars: int
) -> list[tuple[int, int]]:
    """Découpage optimal des unités en parties équilibrées.

    Programmation dynamique : le moins de parties possible (chacune tient
    dans ``limit``), et parmi ces découpages, celui dont les parties sont
    les plus égales et les coupures les plus naturelles (paragraphe > ligne
    > phrase > proposition > mot). Aucune partie « orpheline » trop courte
    tant qu'un autre découpage l'évite.
    """
    n = len(units)
    prefix = [0]
    for chunk, _strength in units:
        prefix.append(prefix[-1] + len(chunk))

    # Nombre minimal de parties (glouton : optimal pour ce critère).
    k_min = 0
    i = 0
    while i < n:
        j = i + 1
        while j < n and _unit_span_length(prefix, i, j + 1) <= limit:
            j += 1
        k_min += 1
        i = j

    total = _unit_span_length(prefix, 0, n)
    target = total / max(1, k_min)
    inf = float("inf")
    # best[k][j] : coût minimal des j premières unités en k parties.
    best = [[inf] * (n + 1) for _ in range(k_min + 1)]
    back = [[-1] * (n + 1) for _ in range(k_min + 1)]
    best[0][0] = 0.0
    for k in range(1, k_min + 1):
        for j in range(1, n + 1):
            for i in range(j - 1, -1, -1):
                length = _unit_span_length(prefix, i, j)
                if length > limit and j - i > 1:
                    break
                previous = best[k - 1][i]
                if previous == inf:
                    continue
                cost = ((length - target) / max(1.0, target)) ** 2
                if length < min_chars and k_min > 1:
                    cost += 4.0
                if j < n:
                    cost += _BREAK_PENALTY[units[j - 1][1]]
                if previous + cost < best[k][j]:
                    best[k][j] = previous + cost
                    back[k][j] = i
    if best[k_min][n] == inf:  # sécurité : ne devrait pas arriver
        return [(0, n)]
    spans: list[tuple[int, int]] = []
    j = n
    for k in range(k_min, 0, -1):
        i = back[k][j]
        spans.append((i, j))
        j = i
    spans.reverse()
    return spans


def split_text_into_slides(
    text: str,
    max_chars: int = MAX_CHARS_PER_SLIDE,
    min_chars: int = MIN_CHARS_PER_SLIDE,
    *,
    keep_line_breaks: bool = True,
) -> list[str]:
    """Découpe un texte long en parties équilibrées et lisibles.

    Coupe d'abord entre paragraphes, puis entre lignes (alinéas, vers),
    puis en fin de phrase (sans couper après « M. », « St. », « v. »…),
    puis aux virgules, et seulement en dernier recours entre deux mots.
    Toutes les parties ont une longueur proche ; les retours à la ligne du
    texte d'origine sont conservés (``keep_line_breaks``).
    """
    raw = str(text or "").strip()
    if not raw:
        return []

    raw = raw.replace("\r", "")
    raw = re.sub(r"[\t ]+", " ", raw)
    raw = re.sub(r"\n[ \t]+", "\n", raw)
    raw = re.sub(r"[ \t]+\n", "\n", raw)
    max_chars = max(40, int(max_chars))
    min_chars = max(0, min(int(min_chars), max_chars // 2))

    if not keep_line_breaks:
        raw = re.sub(r"\s*\n\s*", " ", raw)
    if len(raw) <= max_chars:
        return [raw]

    units = _text_units(raw, max_chars)
    if not units:
        return [raw]
    if len(units) > 600:
        # Texte démesuré : regroupement glouton (évite un calcul trop long).
        spans: list[tuple[int, int]] = []
        start = 0
        length = 0
        for index, (chunk, _strength) in enumerate(units):
            extra = len(chunk) + (1 if index > start else 0)
            if index > start and length + extra > max_chars:
                spans.append((start, index))
                start, length = index, len(chunk)
            else:
                length += extra
        spans.append((start, len(units)))
    else:
        spans = _partition_units(units, max_chars, min_chars)
    return [
        _join_units(units[i:j], keep_line_breaks)
        for i, j in spans
        if units[i:j]
    ]


def split_hymn_stanza(
    text: str,
    max_lines: int = 4,
    max_chars: int = MAX_CHARS_PER_SLIDE,
    *,
    keep_couplets: bool = True,
) -> list[str]:
    """Découpe une strophe longue en parties de quelques vers.

    Les vers ne sont jamais coupés (sauf un vers plus long que
    ``max_chars``). Les parties sont équilibrées : 8 vers en 4 + 4, 6 vers
    en 4 + 2 avec les couplets (vers 1-2, 3-4, 5-6 restent ensemble) ou
    3 + 3 sans. Une strophe sans retours à la ligne (import à plat) est
    découpée comme un texte, phrase par phrase.
    """
    raw = str(text or "").replace("\r", "").strip()
    if not raw:
        return []
    lines = [re.sub(r"[\t ]+", " ", line).strip() for line in raw.split("\n")]
    lines = [line for line in lines if line]
    max_lines = max(1, int(max_lines))
    max_chars = max(40, int(max_chars))

    if len(lines) <= 1:
        return split_text_into_slides(raw, max_chars, 0)

    # Vers démesuré : on le découpe d'abord pour respecter la limite.
    verses: list[str] = []
    for line in lines:
        if len(line) > max_chars:
            verses.extend(
                part.replace("\n", " ")
                for part in split_text_into_slides(line, max_chars, 0)
            )
        else:
            verses.append(line)

    def span_len(group: list[str]) -> int:
        return sum(len(v) for v in group) + max(0, len(group) - 1)

    if len(verses) <= max_lines and span_len(verses) <= max_chars:
        return ["\n".join(verses)]

    # Blocs insécables : couplets (2 vers) ou vers seuls.
    block = 2 if keep_couplets and max_lines >= 2 else 1
    blocks = [verses[i : i + block] for i in range(0, len(verses), block)]
    parts_count = max(
        -(-len(verses) // max_lines),
        -(-span_len(verses) // max_chars),
        1,
    )
    while True:
        parts_count = min(parts_count, len(blocks))
        base, extra = divmod(len(blocks), parts_count)
        groups: list[list[str]] = []
        pos = 0
        for index in range(parts_count):
            size = base + (1 if index < extra else 0)
            group = [verse for blk in blocks[pos : pos + size] for verse in blk]
            groups.append(group)
            pos += size
        too_big = any(
            len(g) > max_lines or span_len(g) > max_chars for g in groups
        )
        if not too_big or parts_count >= len(blocks):
            if too_big and block == 2:
                # Couplets trop longs pour la limite : vers par vers.
                block = 1
                blocks = [[v] for v in verses]
                continue
            return ["\n".join(g) for g in groups if g]
        parts_count += 1
