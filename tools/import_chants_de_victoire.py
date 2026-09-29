"""Import du recueil « Chants de Victoire » (paroles seules, 311 cantiques).

Source : PDF « paroles seules » composé en LaTeX (cantiques.yapper.fr,
fichier CV_paroles.pdf), rangé dans ``cantiques/``. Le texte des cantiques est
celui de l'édition de 1926 (domaine public). La mise en page est régulière,
d'où une analyse par position plutôt que par heuristiques :

* numéro en gras 17 pt, titre en oblique 14 pt (parfois sur deux lignes) ;
* deux colonnes ; dans chaque colonne, le retrait de la ligne dit son rôle :
  0 = début de strophe (« 1. … »), +6 = refrain, +11 = suite de strophe,
  +24 et plus = fin d'une ligne trop longue, renvoyée à la ligne ;
* « … etc. » au retrait des strophes = rappel du refrain ;
* ``\\lrep … \\rrep \\rep{n}`` = passage à répéter n fois.

L'import est ADDITIF : les autres cantiques de la base ne sont pas touchés.

    py -3 tools/import_chants_de_victoire.py            # analyse seule
    py -3 tools/import_chants_de_victoire.py --apply    # sauvegarde puis import
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.connection import Database, DatabaseConfig  # noqa: E402
from app.utils.hymn_pdf_parser import HymnSection  # noqa: E402

CV_PDF = ROOT / "cantiques" / "Chants de Victoire (paroles).pdf"
SOURCE = "CV"
EXPECTED_HYMNS = 324  # 311 numéros, dont 13 en deux variantes « a »/« b »
FIRST_HYMN_PAGE = 4  # pages 1-4 : index alphabétique

_NUMBER_FONT = "LMSans10-Bold"
_TITLE_FONT = "LMSans12-Oblique"
_BODY_FONT = "LMRoman10-Regular"
_STANZA_START = re.compile(r"^(\d+)\.\s+(.*)$")
_REPEAT = re.compile(r"\\rep\{(\d+)\}")
_REPEAT_WORDS = {2: "(bis)", 3: "(ter)"}


@dataclass
class CvHymn:
    number: str
    title: str
    sections: list[HymnSection] = field(default_factory=list)


def _clean(text: str) -> str:
    """Retire les marqueurs LaTeX de répétition, en gardant l'indication."""
    text = text.replace("\\lrep", "").replace("\\rrep", "")
    text = _REPEAT.sub(
        lambda m: _REPEAT_WORDS.get(int(m.group(1)), f"({m.group(1)} fois)"), text
    )
    return re.sub(r"\s+", " ", text).strip()


def _page_lines(page) -> list[tuple[int, float, float, str, str]]:
    """(colonne, y, retrait, police, texte) — colonne gauche puis droite."""
    middle = page.rect.width / 2
    raw = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            # Les espaces sont des fragments à part : on les garde tous.
            spans = line["spans"]
            if not any(s["text"].strip() for s in spans):
                continue
            x, y = line["bbox"][0], line["bbox"][1]
            column = 0 if x < middle else 1
            raw.append((column, y, x, spans))
    # Origine de chaque colonne : le début de strophe le plus à gauche.
    origins = {}
    for column, _y, x, spans in raw:
        first = next(s for s in spans if s["text"].strip())
        if first["font"] == _BODY_FONT:
            origins[column] = min(origins.get(column, x), x)
    lines = []
    for column, y, x, spans in raw:
        indent = x - origins.get(column, x)
        for font in {s["font"] for s in spans if s["text"].strip()}:
            text = "".join(s["text"] for s in spans if s["font"] == font).strip()
            if text:
                lines.append((column, y, indent, font, text))
    lines.sort(key=lambda item: (item[0], item[1], item[3] != _NUMBER_FONT))
    return lines


class _Builder:
    def __init__(self) -> None:
        self.hymns: list[CvHymn] = []
        self.kind = ""  # "stanza" | "chorus"
        self.lines: list[str] = []
        self.stanza_no = 0
        self.chorus = ""

    @property
    def current(self) -> CvHymn | None:
        return self.hymns[-1] if self.hymns else None

    def flush(self) -> None:
        hymn = self.current
        text = "\n".join(_clean(line) for line in self.lines if _clean(line))
        if hymn is not None and text:
            if self.kind == "chorus":
                self.chorus = text
                hymn.sections.append(HymnSection("Choeur:\n" + text, "Refrain", True))
            else:
                # Chant d'une seule strophe : pas de « 1. » dans le recueil.
                self.stanza_no = self.stanza_no or 1
                hymn.sections.append(HymnSection(text, f"Strophe {self.stanza_no}", False))
        self.lines = []
        self.kind = ""

    def start_hymn(self, number: str) -> None:
        self.flush()
        match = re.fullmatch(r"(\d+)([a-z]?)", number.strip())
        if match is None:
            raise ValueError(f"Numéro illisible : {number!r}")
        self.hymns.append(CvHymn(f"{SOURCE}-{int(match.group(1)):03d}{match.group(2).upper()}", ""))
        self.stanza_no = 0
        self.chorus = ""

    def add_title(self, text: str) -> None:
        hymn = self.current
        hymn.title = f"{hymn.title} {text}".strip() if hymn.title else text

    def add_body(self, indent: float, text: str) -> None:
        if self.current is None:
            return
        if indent >= 20 and self.lines:
            # Fin d'une ligne trop longue, renvoyée à la ligne.
            self.lines[-1] = f"{self.lines[-1]} {text}"
            return
        start = _STANZA_START.match(text) if indent < 3 else None
        if start:
            self.flush()
            self.kind = "stanza"
            self.stanza_no = int(start.group(1))
            self.lines = [start.group(2)]
            return
        if 3 <= indent < 9:
            if self.kind != "chorus":
                self.flush()
                self.kind = "chorus"
            self.lines.append(text)
            return
        if text.rstrip(" .»\"").endswith("etc") and self.chorus:
            # Rappel du refrain : on le répète en entier, comme à l'écran.
            self.flush()
            self.current.sections.append(
                HymnSection("Choeur:\n" + self.chorus, "Refrain", True)
            )
            return
        if self.kind == "chorus":
            # Un refrain ne se poursuit pas au retrait des strophes.
            self.flush()
            self.kind = "stanza"
        if not self.kind:
            self.kind = "stanza"
        self.lines.append(text)


def parse_cv_pdf(path: Path = CV_PDF) -> list[CvHymn]:
    import fitz  # PyMuPDF

    builder = _Builder()
    with fitz.open(path) as doc:
        for page_no in range(FIRST_HYMN_PAGE, doc.page_count):
            for _column, _y, indent, font, text in _page_lines(doc[page_no]):
                if font == _NUMBER_FONT:
                    builder.start_hymn(text)
                elif font == _TITLE_FONT:
                    builder.add_title(text)
                elif font == _BODY_FONT:
                    builder.add_body(indent, text)
    builder.flush()
    return builder.hymns


def add_to_database(db: Database, hymns: list[CvHymn]) -> int:
    """Ajoute les cantiques CV absents, à la fin de l'ordre. Retourne le nombre ajouté."""
    with db.connect() as conn:
        present = {
            str(row[0])
            for row in conn.execute("SELECT number FROM hymn WHERE number LIKE ?", (f"{SOURCE}-%",))
        }
        new = [h for h in hymns if h.number not in present]
        if not new:
            return 0
        last = conn.execute("SELECT MAX(CAST(sort_key AS INTEGER)) FROM hymn").fetchone()[0] or 0
        conn.execute("DROP TABLE IF EXISTS hymn_stanza_fts")
        for offset, hymn in enumerate(new, start=1):
            canonical = Database._clean_hymn_title_for_canonical(hymn.title)
            title_search = Database._search_key(f"{canonical} {hymn.title} {hymn.number} fr")
            cursor = conn.execute(
                "INSERT INTO hymn (title, number, language, sort_key, canonical_title, title_search)"
                " VALUES (?, ?, 'fr', ?, ?, ?)",
                (hymn.title, hymn.number, f"{last + offset:05d}", canonical, title_search),
            )
            hymn_id = int(cursor.lastrowid)
            conn.executemany(
                "INSERT INTO hymn_stanza (hymn_id, stanza_no, text, label, is_chorus)"
                " VALUES (?, ?, ?, ?, ?)",
                [
                    (hymn_id, no, s.text, s.label, 1 if s.is_chorus else 0)
                    for no, s in enumerate(hymn.sections, start=1)
                ],
            )
        db._ensure_hymn_fts(conn)
    return len(new)


def main() -> None:
    from tools.import_cantiques import ImportHymn, backup_database, validate_corpus

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="sauvegarde puis importe")
    parser.add_argument("--db", type=Path, help="base SQLite cible")
    parser.add_argument("--show", help="affiche un cantique (ex. CV-011)")
    args = parser.parse_args()

    hymns = parse_cv_pdf()
    if len(hymns) != EXPECTED_HYMNS:
        raise SystemExit(f"{len(hymns)} cantiques lus, attendu {EXPECTED_HYMNS}.")
    validate_corpus(
        [ImportHymn(SOURCE, h.number, h.title, "fr", h.sections, CV_PDF.name) for h in hymns]
    )
    choruses = sum(s.is_chorus for h in hymns for s in h.sections)
    print(f"{SOURCE} : {len(hymns)} cantiques, {sum(len(h.sections) for h in hymns)} sections"
          f" dont {choruses} passages de refrain.")
    if args.show:
        hymn = next(h for h in hymns if h.number == args.show)
        print(f"\n{hymn.number} — {hymn.title}")
        for section in hymn.sections:
            print(f"[{section.label}]\n{section.text}\n")
    if not args.apply:
        print("Analyse seule ; aucune donnée modifiée. Ajoutez --apply pour importer.")
        return

    db = Database(DatabaseConfig(args.db.resolve())) if args.db else Database.default()
    db.initialize()
    backup = backup_database(db.db_path)
    added = add_to_database(db, hymns)
    with sqlite3.connect(db.db_path) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM hymn").fetchone()[0]
    if integrity != "ok":
        raise RuntimeError(f"Intégrité : {integrity} (sauvegarde : {backup})")
    print(f"Ajoutés : {added} ; total : {total} cantiques. Sauvegarde : {backup}")


if __name__ == "__main__":
    main()
