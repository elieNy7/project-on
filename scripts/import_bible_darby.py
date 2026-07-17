"""Importe la Bible J.N. Darby (1872) depuis bible_json/Bible-Darby.pdf.

Le PDF est une edition texte-seul, sans notes ni titres de section :
- la premiere ligne de chaque page est l'en-tete (nom du livre) ;
- les chapitres sont marques par une ligne ``Chapitre N`` ;
- les versets 1-9 sont une ligne ne contenant que le numero ;
- les versets >= 10 sont ``N␣␣texte`` (numero + 2 espaces + texte) ;
- le pied de page ``Page N sur 1437`` est ignore.

Le script produit ``bible_json/darby.json`` (meme schema que segond_1910.json,
donc importe automatiquement sur toute nouvelle installation) puis insere la
traduction dans la base existante (data/project_on.db) de maniere idempotente.

Usage :
    py -3 scripts/import_bible_darby.py            # parse + JSON + import DB
    py -3 scripts/import_bible_darby.py --no-db     # parse + JSON seulement
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = ROOT / "bible_json" / "Bible-Darby.pdf"
JSON_PATH = ROOT / "bible_json" / "darby.json"
DB_PATH = ROOT / "data" / "project_on.db"

# Numero canonique (aligne sur Segond 1910) -> nom francais propre.
CANONICAL_NAMES = {
    1: "Genèse", 2: "Exode", 3: "Lévitique", 4: "Nombres", 5: "Deutéronome",
    6: "Josué", 7: "Juges", 8: "Ruth", 9: "1 Samuel", 10: "2 Samuel",
    11: "1 Rois", 12: "2 Rois", 13: "1 Chroniques", 14: "2 Chroniques",
    15: "Esdras", 16: "Néhémie", 17: "Esther", 18: "Job", 19: "Psaumes",
    20: "Proverbes", 21: "Ecclésiaste", 22: "Cantique des cantiques",
    23: "Ésaïe", 24: "Jérémie", 25: "Lamentations", 26: "Ézéchiel",
    27: "Daniel", 28: "Osée", 29: "Joël", 30: "Amos", 31: "Abdias",
    32: "Jonas", 33: "Michée", 34: "Nahum", 35: "Habacuc", 36: "Sophonie",
    37: "Aggée", 38: "Zacharie", 39: "Malachie", 40: "Matthieu", 41: "Marc",
    42: "Luc", 43: "Jean", 44: "Actes", 45: "Romains", 46: "1 Corinthiens",
    47: "2 Corinthiens", 48: "Galates", 49: "Éphésiens", 50: "Philippiens",
    51: "Colossiens", 52: "1 Thessaloniciens", 53: "2 Thessaloniciens",
    54: "1 Timothée", 55: "2 Timothée", 56: "Tite", 57: "Philémon",
    58: "Hébreux", 59: "Jacques", 60: "1 Pierre", 61: "2 Pierre",
    62: "1 Jean", 63: "2 Jean", 64: "3 Jean", 65: "Jude", 66: "Apocalypse",
}


def _norm(s: str) -> str:
    """minuscule, sans accents, espaces normalises."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()


# En-tete de page (PDF) normalise -> numero de livre canonique.
HEADER_TO_BOOK = {
    "genese": 1, "exode": 2, "levitique": 3, "nombres": 4, "deuteronome": 5,
    "josue": 6, "juges": 7, "ruth": 8, "samuel": 9, "2 samuel": 10,
    "1 rois": 11, "2 rois": 12, "1 chroniques": 13, "2 chroniques": 14,
    "esdras": 15, "nehemie": 16, "esther": 17, "job": 18, "psaumes": 19,
    "proverbes": 20, "ecclesiaste": 21, "cantique": 22, "esaie": 23,
    "jeremie": 24, "lamentations": 25, "ezechiel": 26, "daniel": 27,
    "osee": 28, "joel": 29, "amos": 30, "abdias": 31, "jonas": 32,
    "michee": 33, "nahum": 34, "habacuc": 35, "sophonie": 36, "aggee": 37,
    "zacharie": 38, "malachie": 39, "matthieu": 40, "marc": 41, "luc": 42,
    "jean": 43, "actes": 44, "romains": 45, "1 corinthiens": 46,
    "2 corinthiens": 47, "galates": 48, "ephesiens": 49, "philippiens": 50,
    "colossiens": 51, "1 thessalonicien": 52, "2 thessalonicien": 53,
    "1 timothee": 54, "2 timothee": 55, "tite": 56, "philemon": 57,
    "hebreux": 58, "jacques": 59, "1 pierre": 60, "2 pierre": 61,
    "1 jean": 62, "2 jean": 63, "3 jean": 64, "jude": 65, "revelation": 66,
}

CHAPITRE_RE = re.compile(r"^Chapitre\s*(\d+)$")
STANDALONE_VERSE_RE = re.compile(r"^(\d+)$")
INLINE_VERSE_RE = re.compile(r"^(\d+) {2,}(\S.*)$")
# Certains marqueurs inline n'ont qu'un seul espace (ex. Job 41:10) : on ne les
# accepte que si le numero suit la sequence attendue, pour eviter les faux
# positifs sur du texte commencant par un nombre.
INLINE_VERSE_1SP_RE = re.compile(r"^(\d+) (\S.*)$")
FOOTER_RE = re.compile(r"^Page \d+ sur \d+$")


def _normalize_text(s: str) -> str:
    """Apostrophes typographiques -> ', espaces propres."""
    s = s.replace("’", "'").replace("‘", "'")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def _append(buf: str, frag: str) -> str:
    """Joint un fragment de ligne en gerant la cesure (mot-coupe-)."""
    frag = frag.strip()
    if not frag:
        return buf
    if not buf:
        return frag
    # Mot coupe par un trait d'union en fin de ligne : recoller sans espace.
    if buf.endswith("-") and len(buf) >= 2 and buf[-2].isalpha():
        return buf + frag
    return buf + " " + frag


class Verse:
    __slots__ = ("book", "chapter", "verse", "buf")

    def __init__(self, book: int, chapter: int, verse: int, text: str = ""):
        self.book = book
        self.chapter = chapter
        self.verse = verse
        self.buf = text


def parse_pdf(pdf_path: Path) -> list[Verse]:
    doc = fitz.open(pdf_path)
    verses: list[Verse] = []
    current: Verse | None = None
    book: int | None = None
    chapter = 0

    def flush() -> None:
        nonlocal current
        if current is not None:
            text = _normalize_text(current.buf)
            if text:
                current.buf = text
                verses.append(current)
        current = None

    for page_index in range(doc.page_count):
        text = doc[page_index].get_text()
        if not text.strip():
            continue
        lines = text.split("\n")
        header = _norm(lines[0])
        # Page de titre / sommaire : en-tete inconnu et aucun "Chapitre".
        mapped = HEADER_TO_BOOK.get(header)
        if mapped is not None:
            book = mapped
        if book is None:
            continue  # avant le premier livre (titre + sommaire)

        for raw in lines[1:]:
            line = raw.strip()
            if not line or FOOTER_RE.match(line):
                continue
            m = CHAPITRE_RE.match(line)
            if m:
                flush()
                chapter = int(m.group(1))
                continue
            m = STANDALONE_VERSE_RE.match(line)
            if m:
                flush()
                current = Verse(book, chapter, int(m.group(1)))
                continue
            m = INLINE_VERSE_RE.match(line)
            if m:
                flush()
                current = Verse(book, chapter, int(m.group(1)), m.group(2))
                continue
            m = INLINE_VERSE_1SP_RE.match(line)
            if m and current is not None and int(m.group(1)) == current.verse + 1:
                flush()
                current = Verse(book, chapter, int(m.group(1)), m.group(2))
                continue
            # Ligne de continuation du verset courant.
            if current is not None:
                current.buf = _append(current.buf, line)

    flush()
    doc.close()
    return verses


def apply_corrections(verses: list[Verse]) -> None:
    """Repare les rares defauts de numerotation de la couche texte du PDF.

    Chaque correction est verifiee (assert) : si la couche texte change, le
    script echoue bruyamment au lieu d'alterer silencieusement l'Ecriture.
    Ne touche PAS aux omissions volontaires de Darby (Mt 23:14, Ac 8:37,
    Ac 15:34), fideles au texte critique.
    """

    def find(book: int, chapter: int, verse: int) -> list[Verse]:
        return [v for v in verses if v.book == book and v.chapter == chapter and v.verse == verse]

    # --- Psaume 4 : le marqueur du v2 est rendu inline "(4.2 ..." dans le v1.
    v1 = find(19, 4, 1)
    assert len(v1) == 1 and "(4.2" in v1[0].buf, "Ps 4: motif (4.2 introuvable"
    before, after = re.split(r"\s*\(4\.2\s+", v1[0].buf, maxsplit=1)
    v1[0].buf = before.strip()
    verses.append(Verse(19, 4, 2, after.strip()))

    # --- Psaume 5 : le titre et le corps sont tous deux numerotes "1".
    p5 = find(19, 5, 1)
    assert len(p5) == 2, "Ps 5: doublon du v1 attendu"
    body = next(v for v in p5 if not v.buf.startswith("Au chef de musique"))
    body.verse = 2

    # --- Psaume 9 : deux versets consecutifs numerotes "21" (le 1er est le 20).
    p9 = find(19, 9, 21)
    assert len(p9) == 2, "Ps 9: doublon du v21 attendu"
    p9[0].verse = 20  # ordre de lecture conserve

    # --- Psaume 19 : v2 et v3 fusionnes en un bloc numerote "3".
    p19 = find(19, 19, 3)
    assert len(p19) == 1 and "(" in p19[0].buf, "Ps 19: bloc fusionne introuvable"
    before, after = re.split(r"\s*\(\s*", p19[0].buf, maxsplit=1)
    p19[0].verse = 2
    p19[0].buf = before.strip()
    verses.append(Verse(19, 19, 3, after.rstrip().rstrip(")").strip()))

    verses.sort(key=lambda v: (v.book, v.chapter, v.verse))


def verify(verses: list[Verse]) -> bool:
    ok = True
    books = sorted({v.book for v in verses})
    if books != list(range(1, 67)):
        print(f"  [ERREUR] livres manquants/inattendus: {set(range(1,67))-set(books)}")
        ok = False
    empties = [v for v in verses if not v.buf]
    if empties:
        print(f"  [ERREUR] {len(empties)} versets vides")
        ok = False
    # Continuite des versets par chapitre.
    from collections import defaultdict
    per_chap: dict[tuple[int, int], list[int]] = defaultdict(list)
    for v in verses:
        per_chap[(v.book, v.chapter)].append(v.verse)
    gaps = 0
    for (b, c), nums in per_chap.items():
        nums.sort()
        if nums[0] != 1 or nums != list(range(1, nums[-1] + 1)):
            gaps += 1
    if gaps:
        print(f"  [AVERTISSEMENT] {gaps} chapitres avec numerotation non continue")
    print(f"  Livres: {len(books)}/66  Versets: {len(verses)}")
    return ok


def write_json(verses: list[Verse], path: Path) -> None:
    payload = {
        "metadata": {
            "name": "Bible J.N. Darby",
            "shortname": "Darby",
            "module": "darby",
            "year": "1872",
            "publisher": None,
            "owner": None,
            "description": "Traduction J.N. Darby (1872). Texte du domaine public.",
            "lang": "",
            "lang_short": "fr",
            "copyright": 0,
            "copyright_statement": "Domaine public.",
            "url": None,
            "citation_limit": 0,
            "restrict": 0,
            "italics": 0,
            "strongs": 0,
            "red_letter": 0,
            "paragraph": 0,
            "official": 1,
            "research": 1,
            "module_version": "1.0",
        },
        "verses": [
            {
                "book_name": CANONICAL_NAMES[v.book],
                "book": v.book,
                "chapter": v.chapter,
                "verse": v.verse,
                "text": v.buf,
            }
            for v in verses
        ],
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def import_db(verses: list[Verse], db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            "INSERT OR IGNORE INTO bible_translation (module, name, shortname, lang) "
            "VALUES (?, ?, ?, ?)",
            ("darby", "Bible J.N. Darby", "Darby", "fr"),
        )
        row = conn.execute(
            "SELECT id FROM bible_translation WHERE module = ?", ("darby",)
        ).fetchone()
        translation_id = int(row[0])
        rows = [
            (translation_id, v.book, CANONICAL_NAMES[v.book], v.chapter, v.verse, v.buf)
            for v in verses
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO bible_translation_verse "
            "(translation_id, book, book_name, chapter, verse, text) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        n = conn.execute(
            "SELECT COUNT(*) FROM bible_translation_verse WHERE translation_id = ?",
            (translation_id,),
        ).fetchone()[0]
        print(f"  DB: traduction id={translation_id}, {n} versets en base.")
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-db", action="store_true", help="ne pas importer en base")
    args = ap.parse_args()

    if not PDF_PATH.exists():
        print(f"PDF introuvable: {PDF_PATH}")
        return 1

    print(f"Analyse de {PDF_PATH.name} ...")
    verses = parse_pdf(PDF_PATH)
    apply_corrections(verses)
    print("Verification:")
    ok = verify(verses)

    write_json(verses, JSON_PATH)
    print(f"JSON ecrit: {JSON_PATH}  ({JSON_PATH.stat().st_size/1e6:.1f} Mo)")

    if not args.no_db:
        print("Import en base:")
        import_db(verses, DB_PATH)

    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
