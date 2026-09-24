"""Importe les livres et brochures du dossier ``Livres/`` dans ``project_on.db``.

L'onglet « Livres » presente chaque ouvrage comme l'Expose des Sept Ages :
des chapitres, des pages, et des paragraphes numerotes ``page-n`` (``45-3`` =
3e paragraphe commencant a la page 45). Chaque chapitre est une ligne de la
table ``sermon`` (tradition VGR, date ``BK-<CODE>-CHnn`` pour un livre,
``TR-<CODE>`` pour une brochure) ; ``library_book`` decrit les ouvrages.

Trois sources :

* livres au texte reel (``FRNBK-*``) : chapitres reperes par leurs titres
  (grande police), numero de page imprime lu dans l'en-tete courant ;
  l'album photo, la table des matieres, les legendes, notes et temoignages
  sont ecartes ;
* brochures au texte reel : une brochure = un chapitre de « Brochures » ;
* brochures scannees : texte lu par l'OCR de Windows (fr-FR), puis nettoye.

Un paragraphe commence a chaque retrait de premiere ligne (ou apres un
intertitre) ; un paragraphe coupe par un saut de page reste entier.

Par defaut le script analyse seulement et ecrit un rapport ; ``--apply``
remplace les ouvrages importes par ce script (dates ``BK-SENT``, ``BK-PVSA``,
``TR-*``) sans toucher aux deux Exposes, aux sermons ni au reste de la base.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import fitz

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "Livres"
DEFAULT_DB = ROOT / "data" / "project_on.db"
DEFAULT_REPORT = ROOT / "verification" / "books_import_report.json"
OCR_SCRIPT = Path(__file__).resolve().parent / "windows_ocr.ps1"
TRADITION = "VGR"
BROCHURES_KEY = "brochures"
BROCHURES_PREFIX = "TR-"

ROMAN_RE = re.compile(r"^(?=[ivxlc]+$)c{0,3}(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})$", re.I)


class ImportError_(RuntimeError):
    """Structure inattendue : l'import serait hasardeux."""


# ── Descriptions des ouvrages ─────────────────────────────────────────────


@dataclass(frozen=True)
class TextBook:
    """Livre au texte reel, decoupe en chapitres."""

    key: str
    code: str
    title: str
    pdf: str
    front_title: str  # "Introduction" / "Préface"
    front_pages: tuple[int, int]  # pages PDF (1-based, incluses)
    body_pages: tuple[int, int]
    chapter_title_size: float  # taille mini d'un titre de chapitre
    body_size: tuple[float, float] = (9.5, 10.5)
    header_max_y: float = 45.0


@dataclass(frozen=True)
class Brochure:
    code: str
    title: str
    pdf: str
    pages: tuple[int, int]  # pages PDF du texte (1-based, incluses)
    mode: str  # "text", "ocr" ou "magazine"


BOOKS: tuple[TextBook, ...] = (
    TextBook(
        key="sent",
        code="SENT",
        title="William Branham, un homme envoyé de Dieu",
        pdf="FRNBK-SENT William Branham A Man Sent From God VGR.pdf",
        front_title="Introduction",
        front_pages=(19, 24),
        body_pages=(25, 186),
        chapter_title_size=16.0,
    ),
    TextBook(
        key="pvsa",
        code="PVSA",
        title="William Branham, un prophète visite l’Afrique du Sud",
        pdf="FRNBK-PVSA William Branham A Prophet Visits South Africa VGR.pdf",
        front_title="Préface",
        front_pages=(3, 5),
        # Les témoignages (chapitre 6, page PDF 159) ne sont pas importés.
        body_pages=(9, 158),
        chapter_title_size=21.0,
    ),
)

BROCHURES: tuple[Brochure, ...] = (
    Brochure("ASCE", "Étant monté en haut, Il a fait des dons aux hommes",
             "FRNTR-ASCE He Ascended Up On High And Gave Gifts Unto Men VGR.pdf", (2, 18), "ocr"),
    Brochure("BEYO", "Au-delà du rideau du temps",
             "FRNTR-BEYO Beyond The Curtain Of Time VGR.pdf", (3, 18), "text"),
    Brochure("DOCT", "La doctrine des Nicolaïtes",
             "FRNTR-DOCT The Doctrine Of The Nicolaitanes VGR.pdf", (2, 17), "ocr"),
    Brochure("ENTI", "Les esprits séducteurs contre la Parole de Dieu",
             "FRNTR-ENTI Enticing Spirits Versing The Word of God VGR.pdf", (1, 6), "ocr"),
    Brochure("JCIG", "Jésus-Christ est Dieu",
             "FRNTR-JCIG Jesus Christ Is God VGR.pdf", (1, 6), "ocr"),
    Brochure("JCTS", "Jésus-Christ, le même hier, aujourd’hui et pour toujours",
             "FRNTR-JCTS Jesus Christ The Same Yesterday Today And Forever VGR.pdf", (2, 26), "ocr"),
    Brochure("JEZE", "La femme Jézabel",
             "FRNTR-JEZE That Woman Jezebel VGR.pdf", (3, 26), "text"),
    Brochure("MESS", "Le Messager",
             "FRNTR-MESS The Messenger VGR.pdf", (1, 12), "ocr"),
    Brochure("PUYP", "Prends ta plume et écris",
             "FRNTR-PUYP Pick Up Your Pen And Write VGR.pdf", (1, 8), "ocr"),
    Brochure("WT-2", "Le mystère de Dieu",
             "FRNTR-WT-2 The Mystery Of God VGR.pdf", (3, 20), "magazine"),
)


# ── Résultat d'extraction ─────────────────────────────────────────────────


@dataclass
class Paragraph:
    page: int
    text: str
    heading: bool = False


@dataclass
class Chapter:
    date_code: str
    title: str
    number: int  # 0 = introduction / préface
    source_path: str
    paragraphs: list[Paragraph] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def numbered(self) -> list[tuple[str, Paragraph]]:
        """Paragraphes avec leur marqueur ``page-n``."""
        counts: dict[int, int] = {}
        out = []
        for paragraph in self.paragraphs:
            counts[paragraph.page] = counts.get(paragraph.page, 0) + 1
            out.append((f"{paragraph.page}-{counts[paragraph.page]}", paragraph))
        return out


@dataclass
class Work:
    key: str
    title: str
    date_prefix: str
    sort_order: int
    source: str
    chapters: list[Chapter]


# ── Texte ─────────────────────────────────────────────────────────────────


def clean_text(value: str) -> str:
    text = unicodedata.normalize("NFC", value or "")
    text = text.replace(" ", " ").replace(" ", " ").replace("\t", " ")
    text = text.replace("­", "").replace("﻿", "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Polices VGR : « ^ » et « _ » impriment le tiret d'hesitation
    # (« je—j’avais »), « ` » est un ornement de titre.
    text = text.replace("^", "—").replace("_", "—").replace("`", "")
    return re.sub(r" {2,}", " ", text).strip()


def join_lines(lines: list[str]) -> str:
    """Joint les lignes d'un paragraphe ; « au- / dessus » → « au-dessus »."""
    out = ""
    for line in lines:
        verse_break = line.startswith("\n")
        line = clean_text(line)
        if not line:
            continue
        if not out:
            out = line
        elif verse_break:
            out += "\n" + line  # vers d'un poème : un vers par ligne
        elif out.endswith("-") and not out.endswith(" -"):
            out += line
        else:
            out += " " + line
    return out


def roman_value(token: str) -> int | None:
    token = token.strip().lower()
    if not token or not ROMAN_RE.match(token):
        return None
    values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}
    total = 0
    for index, char in enumerate(token):
        value = values[char]
        if index + 1 < len(token) and values[token[index + 1]] > value:
            total -= value
        else:
            total += value
    return total


def _spaced_line_text(line: dict[str, Any]) -> str:
    """Texte d'une ligne dont les espaces manquent (« LESRÉUNIONS »).

    Les titres espaces a la main n'ont pas de caractere espace : un blanc
    plus large qu'un tiers de la taille de police marque une coupure de mot.
    """
    out: list[str] = []
    previous_x1: float | None = None
    for span in line.get("spans", []):
        size = float(span.get("size", 10.0))
        for char in span.get("chars", []):
            c = char.get("c", "")
            x0, _y0, x1, _y1 = char.get("bbox", (0, 0, 0, 0))
            if previous_x1 is not None and x0 - previous_x1 > size * 0.3 and c != " ":
                if out and out[-1] != " ":
                    out.append(" ")
            out.append(c)
            previous_x1 = x1
    return clean_text("".join(out))


@dataclass
class _Line:
    text: str
    size: float
    x0: float
    y0: float
    y1: float
    italic: bool
    raw: dict[str, Any]


def page_lines(page: Any, rawdict: bool = False) -> list[_Line]:
    """Lignes de la page, morceaux d'une meme ligne de base fusionnes."""
    mode = "rawdict" if rawdict else "dict"
    lines: list[_Line] = []
    for block in page.get_text(mode, sort=True).get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if rawdict:
                text = "".join(ch.get("c", "") for s in spans for ch in s.get("chars", []))
            else:
                text = "".join(str(s.get("text", "")) for s in spans)
            if not text.strip():
                continue
            size = max(float(s.get("size", 0.0)) for s in spans)
            italic = all("Ital" in str(s.get("font", "")) or "Obl" in str(s.get("font", ""))
                         for s in spans if str(s.get("text", s.get("chars", ""))).strip())
            x0, y0, _x1, y1 = (float(v) for v in line["bbox"])
            if lines and abs(lines[-1].y1 - y1) < 2.5 and abs(lines[-1].size - size) < 0.6:
                last = lines[-1]
                last.text = f"{last.text} {text}"
                last.x0 = min(last.x0, x0)
                continue
            lines.append(_Line(text, size, x0, y0, y1, italic, line))
    return lines


def _body_margin(lines: list[_Line]) -> float | None:
    xs = sorted(round(line.x0) for line in lines)
    if not xs:
        return None
    # La marge est la position la plus frequente parmi les plus a gauche.
    counts: dict[int, int] = {}
    for x in xs:
        counts[x] = counts.get(x, 0) + 1
    left = [x for x in counts if x <= xs[0] + 3]
    return float(max(left, key=lambda x: counts[x]))


# ── Livres au texte reel ──────────────────────────────────────────────────


def _is_header(line: "_Line", header_max_y: float) -> bool:
    """En-tete courant : petite ligne en haut de page (titre, numero)."""
    return line.y0 < header_max_y and line.size <= 10.5


def _is_page_number(text: str) -> bool:
    token = clean_text(text)
    return token.isdigit() and len(token) <= 3 or roman_value(token) is not None


def _printed_page(lines: list[_Line], header_max_y: float) -> int | None:
    for line in lines:
        if not _is_header(line, header_max_y):
            continue
        for token in re.split(r"\s+", clean_text(line.text)):
            if token.isdigit():
                return int(token)
            value = roman_value(token)
            if value is not None:
                return value
    return None


def extract_text_book(book: TextBook, source: Path) -> Work:
    pdf_path = source / book.pdf
    document = fitz.open(pdf_path)
    relative = pdf_path.name
    chapters: list[Chapter] = []

    def new_chapter(number: int, title: str) -> Chapter:
        code = f"BK-{book.code}-CH{number:02d}"
        chapter = Chapter(code, title, number, relative)
        chapters.append(chapter)
        return chapter

    try:
        front = new_chapter(0, book.front_title)
        _extract_pages(document, book, book.front_pages, lambda: front, None)

        state: dict[str, Any] = {"chapter": None, "number": 0}

        def current() -> Chapter:
            if state["chapter"] is None:
                raise ImportError_(f"{book.code}: texte avant le premier chapitre")
            return state["chapter"]

        def on_title(title: str) -> None:
            state["number"] += 1
            state["chapter"] = new_chapter(state["number"], title)

        _extract_pages(document, book, book.body_pages, current, on_title)
    finally:
        document.close()
    return Work(book.key, book.title, f"BK-{book.code}-", 10 + BOOKS.index(book), relative, chapters)


_TERMINAL = (".", "?", "!", "»", "”", "…", ")", '"')
_OPENING = ("“", "«", '"', "—", "–")


def _standard_indent(document, book: TextBook, pages: tuple[int, int]) -> float:
    """Retrait de premiere ligne le plus courant du livre (≈ 18 pt)."""
    low, high = book.body_size
    counts: dict[int, int] = {}
    for page_index in range(pages[0] - 1, pages[1]):
        body = [ln for ln in page_lines(document[page_index])
                if not _is_header(ln, book.header_max_y) and low <= ln.size <= high]
        margin = _body_margin(body)
        for line in body:
            offset = round(line.x0 - margin) if margin is not None else 0
            if offset >= 6:
                counts[offset] = counts.get(offset, 0) + 1
    return float(max(counts, key=counts.get)) if counts else 18.0


def _printed_pages(document, book: TextBook, pages: tuple[int, int]) -> dict[int, int]:
    """Numero imprime de chaque page ; les pages sans en-tete (debut de
    chapitre) prennent celui de la page suivante moins un."""
    found = {}
    for page_index in range(pages[0] - 1, pages[1]):
        value = _printed_page(page_lines(document[page_index]), book.header_max_y)
        if value is not None:
            found[page_index] = value
    out = {}
    for page_index in range(pages[0] - 1, pages[1]):
        if page_index in found:
            out[page_index] = found[page_index]
        elif page_index + 1 in found:
            out[page_index] = found[page_index + 1] - 1
        elif page_index - 1 in out:
            out[page_index] = out[page_index - 1] + 1
        else:
            out[page_index] = page_index + 1
    return out


class Segmenter:
    """Decoupe une suite de lignes en paragraphes.

    Un retrait de premiere ligne ouvre un paragraphe, sauf pour les vers et
    les citations en retrait : une ligne en retrait qui suit une ligne en
    retrait sans ponctuation finale poursuit la strophe (un vrai paragraphe
    n'a qu'une premiere ligne en retrait). Les vers gardent leur retour a la
    ligne.
    """

    def __init__(self) -> None:
        self.lines: list[str] | None = None
        self.indented = False
        self.page = 0
        self.chapter: Chapter | None = None

    def flush(self) -> None:
        if self.lines and self.chapter is not None:
            text = join_lines(self.lines)
            if text:
                self.chapter.paragraphs.append(Paragraph(self.page, text))
        self.lines = None

    def heading(self, chapter: Chapter, page: int, text: str) -> None:
        self.flush()
        last = chapter.paragraphs[-1] if chapter.paragraphs else None
        if last is not None and last.heading and last.page == page:
            last.text += " " + text
        else:
            chapter.paragraphs.append(Paragraph(page, text, heading=True))

    def line(self, chapter: Chapter, page: int, raw: str, indent: bool) -> None:
        text = clean_text(raw)
        if not text:
            return
        if re.fullmatch(r"[*\s]+", text):
            self.flush()  # séparateur « * * * »
            return
        previous = clean_text(self.lines[-1]) if self.lines else ""
        continues = (
            indent and self.indented and bool(self.lines)
            and not text.startswith(_OPENING)
            and not previous.endswith(_TERMINAL)
            and not (previous.isupper() and len(previous) > 3)
        )
        if continues:
            chapter.warnings.append(f"strophe p.{page}: …{previous[-40:]} / {text[:40]}…")
        if self.lines is None or (indent and not continues) or self.chapter is not chapter:
            self.flush()
            self.lines = []
            self.page = page
            self.chapter = chapter
        # Un vers commence par une majuscule ; une citation en retrait se
        # poursuit en minuscule sur la ligne suivante.
        self.lines.append(("\n" if continues and text[:1].isupper() else "") + text)
        # Signature « — Cooper » : elle clot la citation.
        self.indented = indent and not (text.startswith(("—", "–")) and len(text) < 40)


def _extract_pages(document, book: TextBook, pages: tuple[int, int], chapter_of, on_title) -> None:
    low, high = book.body_size
    printed_of = _printed_pages(document, book, pages)
    segmenter = Segmenter()
    flush = segmenter.flush

    for page_index in range(pages[0] - 1, pages[1]):
        page = document[page_index]
        lines = page_lines(page)
        printed = printed_of[page_index]
        body = [ln for ln in lines if not _is_header(ln, book.header_max_y)
                and low <= ln.size <= high and not _is_page_number(ln.text)]
        margin = _body_margin(body)
        title_parts: list[str] = []
        for line in lines:
            if _is_header(line, book.header_max_y) or _is_page_number(line.text):
                continue
            if line.size >= book.chapter_title_size and on_title is not None:
                title_parts.append(clean_text(line.text))
                continue
            if title_parts:
                flush()
                on_title(join_lines(title_parts))
                title_parts = []
            if line.size > high + 1.0:
                # Intertitre (« Chapitre 3 » est deja porte par le titre).
                text = _spaced_line_text(page.get_text("rawdict", clip=fitz.Rect(
                    line.raw["bbox"]))["blocks"][0]["lines"][0]) if " " not in line.text.strip() or re.search(r"[A-ZÉÈ]{12,}", line.text) else clean_text(line.text)
                if re.fullmatch(r"(?i)chapitre\s+\d+", text) or re.fullmatch(r"[*\s]+", text):
                    continue
                chapter = chapter_of()
                if not chapter.paragraphs and text.casefold() == chapter.title.casefold():
                    continue  # titre du chapitre, deja porte par le chapitre
                segmenter.heading(chapter, printed, text)
                continue
            if not (low <= line.size <= high):
                continue  # légendes, notes, lettres reproduites
            indent = margin is not None and line.x0 - margin >= 6.0
            segmenter.line(chapter_of(), printed, line.text, indent)
        if title_parts:
            flush()
            on_title(join_lines(title_parts))
    flush()


# ── Brochures ─────────────────────────────────────────────────────────────


def extract_text_brochure(brochure: Brochure, source: Path) -> Chapter:
    pdf_path = source / brochure.pdf
    document = fitz.open(pdf_path)
    chapter = Chapter(BROCHURES_PREFIX + brochure.code, brochure.title, 0, pdf_path.name)
    try:
        all_lines = [page_lines(document[i]) for i in range(brochure.pages[0] - 1, brochure.pages[1])]
        sizes = [round(ln.size, 1) for lines in all_lines for ln in lines]
        body_size = statistics.mode(sizes)
        segmenter = Segmenter()
        for offset, lines in enumerate(all_lines):
            page_no = brochure.pages[0] + offset
            body = [ln for ln in lines if abs(ln.size - body_size) <= 0.6
                    and not _is_page_number(ln.text)]
            margin = _body_margin(body)
            for line in body:
                segmenter.line(chapter, page_no, line.text,
                               margin is not None and line.x0 - margin >= 5.0)
        segmenter.flush()
    finally:
        document.close()
    return chapter


def extract_magazine(brochure: Brochure, source: Path) -> Chapter:
    """« Le mystère de Dieu » : doubles pages, texte courant 12 pt, encadrés 7-8 pt."""
    pdf_path = source / brochure.pdf
    document = fitz.open(pdf_path)
    chapter = Chapter(BROCHURES_PREFIX + brochure.code, brochure.title, 0, pdf_path.name)
    try:
        for page_index in range(brochure.pages[0] - 1, brochure.pages[1]):
            page = document[page_index]
            half = page.rect.width
            blocks = []
            for block in page.get_text("dict", sort=True).get("blocks", []):
                lines = [ln for ln in block.get("lines", [])
                         if "".join(s.get("text", "") for s in ln.get("spans", [])).strip()]
                if not lines:
                    continue
                sizes = [s["size"] for ln in lines for s in ln["spans"] if s["text"].strip()]
                size = statistics.median(sizes)
                x0, y0 = block["bbox"][0], block["bbox"][1]
                text = join_lines(["".join(s["text"] for s in ln["spans"]) for ln in lines])
                blocks.append((x0 >= half, y0, x0, size, text))
            for right, _y, _x, size, text in sorted(blocks):
                if not text or re.fullmatch(r"\d{1,3}", text):
                    continue
                if 11.0 <= size <= 13.0:
                    chapter.paragraphs.append(Paragraph(page_index + 1, text))
                elif 14.0 <= size <= 40.0 and len(text) < 120:
                    chapter.paragraphs.append(Paragraph(page_index + 1, text, heading=True))
    finally:
        document.close()
    return chapter


def _run_windows_ocr(images: list[Path]) -> list[dict[str, Any]]:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
        handle.write("\n".join(str(p) for p in images))
        list_file = handle.name
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(OCR_SCRIPT), "-ListFile", list_file],
        capture_output=True, check=False,
    )
    Path(list_file).unlink(missing_ok=True)
    out = completed.stdout.decode("utf-8", errors="replace")
    results = [json.loads(line) for line in out.splitlines() if line.strip().startswith("{")]
    if len(results) != len(images):
        raise ImportError_(
            "OCR Windows incomplet : " + completed.stderr.decode("utf-8", errors="replace")[:500]
        )
    return results


_OCR_FIXES = (
    (re.compile(r"(?<=\w)'(?=\w)"), "’"),  # apostrophe typographique
    (re.compile(r"(?<=[a-zà-ÿ])Q(?=[\"”»\s]|$)"), "?"),  # « pasQ » : « ? » lu « Q »
    (re.compile(r"(?<=[a-zà-ÿ])I(?=[a-zà-ÿ])"), "l"),  # « EvangiIe » : « l » lu « I »
    (re.compile(r"\s+([,.])"), r"\1"),
    (re.compile(r"«\s*"), "« "),
    (re.compile(r"\s*»"), " »"),
)


def clean_ocr_text(text: str) -> str:
    text = clean_text(text)
    for pattern, replacement in _OCR_FIXES:
        text = pattern.sub(replacement, text)
    return text


WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿŒœ]+")
# En-tête de collection imprimé en tête des brochures.
SERIES_LINES = {"la parole de dieu est venue au prophète", "william marrion branham",
                "rév. william marrion branham", "rev. william marrion branham"}


def vocabulary(works: list["Work"]) -> set[str]:
    """Mots des ouvrages au texte reel : reference pour juger l'OCR."""
    words: set[str] = set()
    for work in works:
        for chapter in work.chapters:
            for paragraph in chapter.paragraphs:
                words.update(w.lower() for w in WORD_RE.findall(paragraph.text))
    return words


# Mot deforme par l'OCR : majuscule ou chiffre au milieu, barre, parenthese.
WEIRD_TOKEN_RE = re.compile(
    r"[a-zà-ÿ][A-ZÀ-ÞŒ]|\d(?!(?:e|er|ème|re)\b)[A-Za-zÀ-ÿ]|[A-Za-zÀ-ÿ]\d|\w[/|()]\w|/$"
)
# Bloc d'adresse de la 4e de couverture.
CONTACT_RE = re.compile(
    r"C\.P\. ?156|Succursale|Sainte-Rose|\(Québec\)|www\.|^FRENCH$|H2L|H7R", re.I
)


def weird_tokens(text: str) -> list[str]:
    return [token for token in text.split() if WEIRD_TOKEN_RE.search(token.strip(".,;:!?«»“”\"—–"))]


def known_ratio(text: str, lexicon: set[str]) -> float:
    """Part des mots connus (les nombres et références sont neutres)."""
    known = total = 0
    for token in text.split():
        token = token.strip(".,;:!?«»“”\"()[]—–-…")
        if not token or re.fullmatch(r"[\d.,\-–]+", token):
            continue
        total += 1
        parts = [part for part in re.split(r"[’'\-]", token.lower()) if part]
        if parts and all(part in lexicon for part in parts):
            known += 1
    return known / total if total else 1.0


def is_ocr_garbage(text: str, lexicon: set[str]) -> bool:
    """Titre en écriture décorative mal lu : mots déformés, peu de mots connus."""
    return bool(weird_tokens(text)) and known_ratio(text, lexicon) < 0.5


def _same_title(text: str, title: str) -> bool:
    def key(value: str) -> str:
        value = unicodedata.normalize("NFD", value).casefold()
        return "".join(c for c in value if c.isalnum())
    return key(text) == key(title)


def extract_ocr_brochure(brochure: Brochure, source: Path, cache_dir: Path,
                         lexicon: set[str] | None = None) -> Chapter:
    pdf_path = source / brochure.pdf
    chapter = Chapter(BROCHURES_PREFIX + brochure.code, brochure.title, 0, pdf_path.name)
    document = fitz.open(pdf_path)
    images: list[Path] = []
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        for page_index in range(brochure.pages[0] - 1, brochure.pages[1]):
            image = cache_dir / f"{brochure.code}-{page_index + 1:03d}.png"
            if not image.exists():
                document[page_index].get_pixmap(dpi=300).save(image)
            images.append(image)
    finally:
        document.close()
    cache = cache_dir / f"{brochure.code}.ocr.json"
    if cache.exists():
        results = json.loads(cache.read_text(encoding="utf-8"))
    else:
        results = _run_windows_ocr(images)
        cache.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")

    segmenter = Segmenter()
    for offset, result in enumerate(results):
        page_no = brochure.pages[0] + offset
        raw = result.get("lines") or []
        if isinstance(raw, dict):
            raw = [raw]
        heights = [float(l["y1"]) - float(l["y0"]) for l in raw]
        typical = statistics.median(heights) if heights else 0.0
        body: list[_Line] = []
        for l in raw:
            text = clean_ocr_text(str(l.get("text", "")))
            if not text or re.fullmatch(r"[\d\s.\-–]{1,5}", text) or len(text) <= 3:
                continue  # numéro de page, bribe isolée
            if text.casefold() in SERIES_LINES or _same_title(text, brochure.title):
                continue  # en-tête de collection, titre déjà porté par le chapitre
            if CONTACT_RE.search(text):
                continue  # adresse de la 4e de couverture
            if lexicon and is_ocr_garbage(text, lexicon):
                # Titre en écriture décorative, illisible par l'OCR.
                chapter.warnings.append(f"ligne illisible écartée p.{page_no}: {text}")
                continue
            height = float(l["y1"]) - float(l["y0"])
            body.append(_Line(text, height, float(l["x0"]), float(l["y0"]), float(l["y1"]),
                              False, {"big": typical and height > typical * 1.35}))
        margin = _body_margin([b for b in body if not b.raw["big"]])
        # Retrait d'environ 10 pt : 40 px a 300 dpi.
        for line in body:
            if line.raw["big"]:
                segmenter.heading(chapter, page_no, line.text)
                continue
            segmenter.line(chapter, page_no, line.text,
                           margin is not None and line.x0 - margin >= 25.0)
    segmenter.flush()
    for marker, paragraph in chapter.numbered():
        doubtful = weird_tokens(paragraph.text)
        if doubtful:
            chapter.warnings.append(f"à relire {marker}: {', '.join(doubtful[:8])}")
    return chapter


def extract_brochures(source: Path, cache_dir: Path, codes: set[str] | None,
                      lexicon: set[str] | None = None) -> Work:
    chapters = []
    for brochure in BROCHURES:
        if codes and brochure.code not in codes:
            continue
        started = time.perf_counter()
        if brochure.mode == "text":
            chapter = extract_text_brochure(brochure, source)
        elif brochure.mode == "magazine":
            chapter = extract_magazine(brochure, source)
        else:
            chapter = extract_ocr_brochure(brochure, source, cache_dir, lexicon)
        print(f"[{brochure.code}] {len(chapter.paragraphs)} paragraphes "
              f"({time.perf_counter() - started:.1f}s, {brochure.mode})", flush=True)
        chapters.append(chapter)
    chapters.sort(key=lambda c: _sort_title(c.title))
    return Work(BROCHURES_KEY, "Brochures", BROCHURES_PREFIX, 30, "Livres/FRNTR-*.pdf", chapters)


def _sort_title(title: str) -> str:
    text = unicodedata.normalize("NFD", title).casefold()
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


# ── Validation, rapport ───────────────────────────────────────────────────


def validate(works: list[Work]) -> dict[str, Any]:
    summary: dict[str, Any] = {"works": []}
    for work in works:
        entries = []
        for chapter in work.chapters:
            if not chapter.paragraphs:
                raise ImportError_(f"{chapter.date_code}: chapitre vide ({chapter.title})")
            texts = [p.text for p in chapter.paragraphs]
            short = [t for t in texts if len(t) < 25 and not t.endswith((".", "?", "!", "»", "”"))]
            entries.append({
                "date_code": chapter.date_code,
                "title": chapter.title,
                "paragraphs": len(chapter.paragraphs),
                "headings": sum(1 for p in chapter.paragraphs if p.heading),
                "pages": sorted({p.page for p in chapter.paragraphs}),
                "suspicious_short": short[:15],
                "notes": chapter.warnings,
            })
        summary["works"].append({
            "key": work.key, "title": work.title, "chapters": entries,
            "paragraphs": sum(e["paragraphs"] for e in entries),
        })
    return summary


# ── Écriture en base ──────────────────────────────────────────────────────


LIBRARY_BOOK_DDL = """
    CREATE TABLE IF NOT EXISTS library_book (
        key TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        date_prefix TEXT NOT NULL,
        tradition TEXT NOT NULL,
        sort_order INTEGER DEFAULT 0,
        source TEXT DEFAULT ''
    )
"""


def apply_import(db_path: Path, works: list[Work], backup_dir: Path | None) -> dict[str, Any]:
    if not db_path.exists():
        raise ImportError_(f"Base introuvable : {db_path}")
    sys.path.insert(0, str(ROOT))
    from app.database.connection import Database, DatabaseConfig

    backup_path = None
    if backup_dir is not None:
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"project_on-before-books-{datetime.now():%Y%m%d-%H%M%S}.db"
        source = sqlite3.connect(db_path)
        target = sqlite3.connect(backup_path)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()

    connection = sqlite3.connect(db_path, timeout=120.0)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(LIBRARY_BOOK_DDL)
        connection.execute("BEGIN IMMEDIATE")

        def count(sql: str) -> int:
            return int(connection.execute(sql).fetchone()[0])

        protected_sql = (
            "SELECT COUNT(*) FROM sermon_paragraph p JOIN sermon s ON s.id = p.sermon_id "
            "WHERE s.date NOT LIKE 'BK-SENT-%' AND s.date NOT LIKE 'BK-PVSA-%' "
            "AND s.date NOT LIKE 'TR-%'"
        )
        protected_before = count(protected_sql)
        expose_before = count("SELECT COUNT(*) FROM sermon WHERE date LIKE 'BK-AGES-%'")

        for work in works:
            connection.execute(
                "DELETE FROM sermon_paragraph WHERE sermon_id IN "
                "(SELECT id FROM sermon WHERE date LIKE ? AND tradition = ?)",
                (work.date_prefix + "%", TRADITION),
            )
            connection.execute(
                "DELETE FROM sermon WHERE date LIKE ? AND tradition = ?",
                (work.date_prefix + "%", TRADITION),
            )
            connection.execute(
                "INSERT OR REPLACE INTO library_book "
                "(key, title, date_prefix, tradition, sort_order, source) VALUES (?, ?, ?, ?, ?, ?)",
                (work.key, work.title, work.date_prefix, TRADITION, work.sort_order, work.source),
            )
            for chapter in work.chapters:
                # Brochures : ordre alphabétique des titres ; livres : ordre des chapitres.
                sort_key = (f"{work.date_prefix}{work.chapters.index(chapter) + 1:03d}"
                            if work.key == BROCHURES_KEY else chapter.date_code)
                cursor = connection.execute(
                    "INSERT INTO sermon (title, date, tradition, language, source_path, sort_key, "
                    "location, canonical_title, title_search) VALUES (?, ?, ?, 'fr', ?, ?, '', ?, '')",
                    (chapter.title, chapter.date_code, TRADITION, chapter.source_path,
                     sort_key, chapter.title),
                )
                sermon_id = int(cursor.lastrowid)
                rows = []
                for marker, paragraph in chapter.numbered():
                    page, n = (int(v) for v in marker.split("-"))
                    rows.append((sermon_id, page * 1000 + n, marker, paragraph.text, marker))
                connection.executemany(
                    "INSERT INTO sermon_paragraph (sermon_id, paragraph_no, ref, text, marker) "
                    "VALUES (?, ?, ?, ?, ?)",
                    rows,
                )
        if count(protected_sql) != protected_before:
            raise ImportError_("Un contenu hors des livres importés a changé ; import annulé")
        if count("SELECT COUNT(*) FROM sermon WHERE date LIKE 'BK-AGES-%'") != expose_before:
            raise ImportError_("Les Exposés ont changé ; import annulé")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    database = Database(DatabaseConfig(db_path=db_path))
    with database.connect() as conn:
        # L'index plein texte suit le nouveau nombre de paragraphes.
        database._ensure_sermon_search_metadata(conn)
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        fts = int(conn.execute("SELECT COUNT(*) FROM sermon_paragraph_fts").fetchone()[0])
        total = int(conn.execute("SELECT COUNT(*) FROM sermon_paragraph").fetchone()[0])
    if integrity.lower() != "ok" or fts != total:
        raise ImportError_(f"Contrôle final en échec : integrity={integrity}, fts={fts}/{total}")
    return {
        "backup_path": str(backup_path) if backup_path else None,
        "integrity_check": integrity,
        "protected_paragraphs": protected_before,
        "imported_paragraphs": sum(len(c.paragraphs) for w in works for c in w.chapters),
    }


# ── CLI ───────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--only", nargs="*", help="Codes à analyser (SENT, PVSA, BEYO…)")
    parser.add_argument("--ocr-cache", type=Path, default=ROOT / "tmp" / "books-ocr")
    parser.add_argument("--dump", type=Path, help="Écrit le texte extrait (relecture)")
    parser.add_argument("--apply", action="store_true", help="Écrit dans la base")
    parser.add_argument("--no-backup", action="store_true")
    return parser


def extract_all(source: Path, cache: Path, only: set[str] | None) -> list[Work]:
    works = []
    for book in BOOKS:
        if only and book.code not in only:
            continue
        started = time.perf_counter()
        work = extract_text_book(book, source)
        print(f"[{book.code}] {len(work.chapters)} chapitres, "
              f"{sum(len(c.paragraphs) for c in work.chapters)} paragraphes "
              f"({time.perf_counter() - started:.1f}s)", flush=True)
        works.append(work)
    codes = {b.code for b in BROCHURES}
    wanted = (only & codes) if only else None
    if not only or wanted:
        # Vocabulaire de référence : livres et brochures au texte réel.
        reference = list(works) if not only else [
            extract_text_book(book, source) for book in BOOKS
        ]
        text_codes = {b.code for b in BROCHURES if b.mode != "ocr"}
        reference.append(extract_brochures(source, cache, text_codes))
        works.append(extract_brochures(source, cache, wanted, vocabulary(reference)))
    return works


def dump_text(works: list[Work], path: Path) -> None:
    lines = []
    for work in works:
        lines.append(f"##### {work.title}")
        for chapter in work.chapters:
            lines.append(f"\n=== {chapter.date_code} — {chapter.title}")
            for marker, paragraph in chapter.numbered():
                prefix = "## " if paragraph.heading else ""
                lines.append(f"[{marker}] {prefix}{paragraph.text}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    only = {code.upper() for code in args.only} if args.only else None
    if args.apply and only:
        raise ImportError_("--apply exige tous les ouvrages ; retirez --only")
    works = extract_all(args.source.resolve(), args.ocr_cache.resolve(), only)
    summary = validate(works)
    if args.dump:
        dump_text(works, args.dump)
    applied = None
    if args.apply:
        backup = None if args.no_backup else ROOT / "tmp" / "db-backups"
        applied = apply_import(args.db.resolve(), works, backup)
        print(json.dumps(applied, ensure_ascii=False, indent=2))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps({"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "summary": summary, "applied": applied}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for work in summary["works"]:
        print(f"{work['title']}: {len(work['chapters'])} chapitres, {work['paragraphs']} paragraphes")
    print(f"Rapport : {args.report}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ImportError_ as error:
        print(f"ERREUR : {error}", file=sys.stderr)
        raise SystemExit(2) from error
