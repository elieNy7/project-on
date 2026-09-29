"""Bibles libres de droits : catalogue, téléchargement, import et gestion.

Les traductions sont stockées dans les tables ``bible_translation`` /
``bible_translation_verse`` (celles de l'onglet Bible). Trois sources :

- **Bibles fournies** avec l'application (``bibles/*.json.gz``), installées
  au démarrage si elles manquent — aucune connexion requise ;
- **Catalogue en ligne** : Bibles du domaine public publiées par le projet
  scrollmapper/bible_databases (GitHub), téléchargées à la demande ;
- **Fichier local** : Bible au format Zefania XML, « Beblia » XML,
  scrollmapper JSON ou JSON Project-On — pour une version dont l'église
  détient les droits (lingala, swahili, tshiluba…).

Format commun (identique à ``bible_json/*.json``)::

    {"metadata": {"module", "name", "shortname", "lang", "license", "source"},
     "verses": [{"book", "book_name", "chapter", "verse", "text"}, …]}
"""

from __future__ import annotations

import gzip
import json
import re
import sqlite3
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.utils.text_utils import clean_text

SCROLLMAPPER_URL = (
    "https://raw.githubusercontent.com/scrollmapper/bible_databases/master/"
    "formats/json/{code}.json"
)


@dataclass(frozen=True)
class BibleEntry:
    code: str  # nom du fichier scrollmapper
    shortname: str
    name: str
    lang: str
    license: str = "Domaine public"
    bundled: bool = False  # fournie avec l'installeur
    note: str = ""

    @property
    def module(self) -> str:
        return f"sm_{self.code.lower()}"


# Uniquement des textes du domaine public (ou sous licence libre explicite).
CATALOG: tuple[BibleEntry, ...] = (
    # ── Français ──
    BibleEntry("FreBDM1744", "Martin 1744", "Bible David Martin (1744)", "fr", bundled=True),
    BibleEntry(
        "FreCrampon", "Crampon 1923", "Bible Augustin Crampon (1923)", "fr",
        bundled=True, note="Livres deutérocanoniques non repris",
    ),
    BibleEntry("FrePGR", "Perret-Gentil", "Bible Perret-Gentil et Rilliet (1866)", "fr", bundled=True),
    BibleEntry("FreBBB", "Bovet-Bonnet", "Bible Bovet-Bonnet (1900)", "fr", bundled=True),
    BibleEntry("FreJND", "Darby (JND)", "Bible J.N. Darby (1885)", "fr"),
    BibleEntry("FreSynodale1921", "Synodale 1921", "Version Synodale 1921 (NT et Psaumes)", "fr"),
    BibleEntry("FreOltramare1874", "Oltramare 1874", "Nouveau Testament Oltramare (1874)", "fr"),
    BibleEntry("FreStapfer1889", "Stapfer 1889", "Nouveau Testament Stapfer (1889)", "fr"),
    # ── English ──
    BibleEntry("KJV", "KJV", "King James Version (1769)", "en", bundled=True),
    BibleEntry("BSB", "BSB", "Berean Standard Bible", "en", bundled=True),
    BibleEntry("ASV", "ASV", "American Standard Version (1901)", "en"),
    BibleEntry("Darby", "Darby EN", "Darby Bible (1889)", "en"),
    BibleEntry("DRC", "Douay-Rheims", "Douay-Rheims, Challoner Revision", "en"),
    # ── Autres langues ──
    BibleEntry("SpaRV", "Reina-Valera 1909", "La Santa Biblia Reina-Valera (1909)", "es", bundled=True),
    BibleEntry("PorBLivre", "Bíblia Livre", "Bíblia Livre", "pt", license="CC BY 3.0 BR"),
    BibleEntry("Haitian", "Kreyòl", "Bib la an Kreyòl ayisyen", "ht"),
    BibleEntry("Mg1865", "Malagasy 1865", "Baiboly Malagasy (1865)", "mg"),
    BibleEntry("GerElb1905", "Elberfelder 1905", "Elberfelder Bibel (1905)", "de"),
    BibleEntry("RusSynodal", "Synodale russe", "Синодальный перевод", "ru"),
    BibleEntry("Viet", "Việt 1934", "Kinh Thánh Tiếng Việt (1934)", "vi"),
)

LANG_LABELS = {
    "fr": "Français", "en": "English", "es": "Español", "pt": "Português",
    "ht": "Kreyòl", "mg": "Malagasy", "de": "Deutsch", "ru": "Русский",
    "vi": "Tiếng Việt", "ln": "Lingala", "sw": "Kiswahili", "lua": "Tshiluba",
    "kg": "Kikongo",
}

FRENCH_BOOKS = (
    "Genèse", "Exode", "Lévitique", "Nombres", "Deutéronome", "Josué", "Juges",
    "Ruth", "1 Samuel", "2 Samuel", "1 Rois", "2 Rois", "1 Chroniques",
    "2 Chroniques", "Esdras", "Néhémie", "Esther", "Job", "Psaumes", "Proverbes",
    "Ecclésiaste", "Cantique des cantiques", "Ésaïe", "Jérémie", "Lamentations",
    "Ézéchiel", "Daniel", "Osée", "Joël", "Amos", "Abdias", "Jonas", "Michée",
    "Nahum", "Habacuc", "Sophonie", "Aggée", "Zacharie", "Malachie", "Matthieu",
    "Marc", "Luc", "Jean", "Actes", "Romains", "1 Corinthiens", "2 Corinthiens",
    "Galates", "Éphésiens", "Philippiens", "Colossiens", "1 Thessaloniciens",
    "2 Thessaloniciens", "1 Timothée", "2 Timothée", "Tite", "Philémon",
    "Hébreux", "Jacques", "1 Pierre", "2 Pierre", "1 Jean", "2 Jean", "3 Jean",
    "Jude", "Apocalypse",
)

ENGLISH_BOOKS = (
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy", "Joshua",
    "Judges", "Ruth", "1 Samuel", "2 Samuel", "1 Kings", "2 Kings",
    "1 Chronicles", "2 Chronicles", "Ezra", "Nehemiah", "Esther", "Job",
    "Psalms", "Proverbs", "Ecclesiastes", "Song of Solomon", "Isaiah",
    "Jeremiah", "Lamentations", "Ezekiel", "Daniel", "Hosea", "Joel", "Amos",
    "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah", "Haggai",
    "Zechariah", "Malachi", "Matthew", "Mark", "Luke", "John", "Acts",
    "Romans", "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians",
    "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians",
    "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews", "James",
    "1 Peter", "2 Peter", "1 John", "2 John", "3 John", "Jude", "Revelation",
)

SPANISH_BOOKS = (
    "Génesis", "Éxodo", "Levítico", "Números", "Deuteronomio", "Josué",
    "Jueces", "Rut", "1 Samuel", "2 Samuel", "1 Reyes", "2 Reyes",
    "1 Crónicas", "2 Crónicas", "Esdras", "Nehemías", "Ester", "Job",
    "Salmos", "Proverbios", "Eclesiastés", "Cantares", "Isaías", "Jeremías",
    "Lamentaciones", "Ezequiel", "Daniel", "Oseas", "Joel", "Amós", "Abdías",
    "Jonás", "Miqueas", "Nahúm", "Habacuc", "Sofonías", "Hageo", "Zacarías",
    "Malaquías", "Mateo", "Marcos", "Lucas", "Juan", "Hechos", "Romanos",
    "1 Corintios", "2 Corintios", "Gálatas", "Efesios", "Filipenses",
    "Colosenses", "1 Tesalonicenses", "2 Tesalonicenses", "1 Timoteo",
    "2 Timoteo", "Tito", "Filemón", "Hebreos", "Santiago", "1 Pedro",
    "2 Pedro", "1 Juan", "2 Juan", "3 Juan", "Judas", "Apocalipsis",
)


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(c for c in value if not unicodedata.combining(c)).lower()
    value = re.sub(r"\biii\b", "3", value)
    value = re.sub(r"\bii\b", "2", value)
    value = re.sub(r"\bi\b", "1", value)
    return re.sub(r"[^a-z0-9]+", "", value)


# Noms de livres (anglais scrollmapper, français, espagnol) → numéro 1..66.
_BOOK_NUMBERS: dict[str, int] = {}
for _names in (ENGLISH_BOOKS, FRENCH_BOOKS, SPANISH_BOOKS):
    for _index, _name in enumerate(_names, start=1):
        _BOOK_NUMBERS.setdefault(_norm(_name), _index)
for _alias, _index in {
    "revelationofjohn": 66, "songofsongs": 22, "canticles": 22, "psalm": 19,
    "cantiquedescantiques": 22, "cantique": 22, "isaie": 23, "apocalypsis": 66,
}.items():
    _BOOK_NUMBERS.setdefault(_alias, _index)


def book_number(name: str) -> int | None:
    """Numéro canonique (1..66) d'un livre, ou None (deutérocanonique…)."""
    return _BOOK_NUMBERS.get(_norm(name))


def book_display_name(book: int, lang: str) -> str:
    names = {"en": ENGLISH_BOOKS, "es": SPANISH_BOOKS}.get(lang, FRENCH_BOOKS)
    return names[book - 1] if 1 <= book <= 66 else str(book)


def entry_by_code(code: str) -> BibleEntry | None:
    return next((e for e in CATALOG if e.code == code), None)


# ── Conversion ────────────────────────────────────────────────────────────


def _payload(module: str, shortname: str, name: str, lang: str,
             license_: str, source: str, verses: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "metadata": {
            "module": module,
            "shortname": shortname,
            "name": name,
            "lang": lang,
            "license": license_,
            "source": source,
        },
        "verses": verses,
    }


def from_scrollmapper(data: dict[str, Any], entry: BibleEntry) -> dict[str, Any]:
    """Convertit le JSON scrollmapper (livres → chapitres → versets)."""
    verses: list[dict[str, Any]] = []
    for book in data.get("books") or []:
        number = book_number(str(book.get("name") or ""))
        if number is None:
            continue  # livres deutérocanoniques : hors du canon de l'app
        display = book_display_name(number, entry.lang)
        for chapter in book.get("chapters") or []:
            ch = int(chapter.get("chapter") or 0)
            for verse in chapter.get("verses") or []:
                text = clean_text(verse.get("text") or "")
                if ch and text:
                    verses.append({
                        "book": number, "book_name": display, "chapter": ch,
                        "verse": int(verse.get("verse") or 0), "text": text,
                    })
    return _payload(entry.module, entry.shortname, entry.name, entry.lang,
                    entry.license, "scrollmapper/bible_databases", verses)


def from_xml_file(path: Path, *, shortname: str = "", lang: str = "fr") -> dict[str, Any]:
    """Bible XML : Zefania (``BIBLEBOOK/CHAPTER/VERS``) ou Beblia
    (``book/chapter/verse``). Le livre est lu par son numéro, sinon son nom."""
    root = ET.parse(str(path)).getroot()
    title = (
        root.get("biblename") or root.get("translation")
        or (root.findtext(".//INFORMATION/title") or "").strip()
        or path.stem
    )
    verses: list[dict[str, Any]] = []
    books = [el for el in root.iter() if el.tag.lower() in ("biblebook", "book")]
    for book in books:
        raw_number = book.get("bnumber") or book.get("number") or ""
        number = int(raw_number) if str(raw_number).isdigit() else None
        if number is None:
            number = book_number(book.get("bname") or book.get("name") or "")
        if number is None or not 1 <= number <= 66:
            continue
        display = book_display_name(number, lang)
        for chapter in book:
            if chapter.tag.lower() not in ("chapter",):
                continue
            ch = int(chapter.get("cnumber") or chapter.get("number") or 0)
            for verse in chapter:
                if verse.tag.lower() not in ("vers", "verse"):
                    continue
                text = clean_text("".join(verse.itertext()))
                vno = int(verse.get("vnumber") or verse.get("number") or 0)
                if ch and vno and text:
                    verses.append({
                        "book": number, "book_name": display, "chapter": ch,
                        "verse": vno, "text": text,
                    })
    module = "file_" + re.sub(r"[^a-z0-9]+", "_", _norm(path.stem) or "bible")
    return _payload(module, shortname or title[:40], title, lang,
                    "Fichier importé", path.name, verses)


def load_bible_file(path: Path, *, shortname: str = "", lang: str = "fr") -> dict[str, Any]:
    """Lit un fichier de Bible (XML, JSON scrollmapper, JSON Project-On, .gz)."""
    path = Path(path)
    if path.suffix.lower() == ".xml":
        return from_xml_file(path, shortname=shortname, lang=lang)
    raw = path.read_bytes()
    if path.suffix.lower() == ".gz":
        raw = gzip.decompress(raw)
    data = json.loads(raw.decode("utf-8-sig"))
    if isinstance(data, dict) and isinstance(data.get("verses"), list):
        return data  # déjà au format Project-On
    if isinstance(data, dict) and isinstance(data.get("books"), list):
        title = str(data.get("translation") or path.stem)
        entry = BibleEntry(
            code=re.sub(r"[^A-Za-z0-9]+", "", path.stem) or "Bible",
            shortname=shortname or title.split(":")[0][:40],
            name=title, lang=lang, license="Fichier importé",
        )
        payload = from_scrollmapper(data, entry)
        payload["metadata"]["source"] = path.name
        return payload
    raise ValueError("Format de Bible non reconnu (XML Zefania/Beblia ou JSON attendu).")


# ── Téléchargement ────────────────────────────────────────────────────────


def download(entry: BibleEntry, progress: Callable[[int, int], None] | None = None,
             timeout: float = 60.0) -> dict[str, Any]:
    """Télécharge une Bible du catalogue et la convertit (sans l'installer)."""
    url = SCROLLMAPPER_URL.format(code=entry.code)
    request = urllib.request.Request(url, headers={"User-Agent": "Project-On"})
    chunks: list[bytes] = []
    with urllib.request.urlopen(request, timeout=timeout) as response:
        total = int(response.headers.get("Content-Length") or 0)
        received = 0
        while True:
            block = response.read(256 * 1024)
            if not block:
                break
            chunks.append(block)
            received += len(block)
            if progress is not None:
                progress(received, total)
    data = json.loads(b"".join(chunks).decode("utf-8-sig"))
    payload = from_scrollmapper(data, entry)
    if len(payload["verses"]) < 1000:
        raise ValueError(f"Bible incomplète ({len(payload['verses'])} versets).")
    return payload


def save_payload(payload: dict[str, Any], folder: Path) -> Path:
    """Enregistre une Bible convertie (JSON compressé) — sauvegarde locale."""
    folder.mkdir(parents=True, exist_ok=True)
    module = str(payload["metadata"]["module"])
    path = folder / f"{module}.json.gz"
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(gzip.compress(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        compresslevel=9,
    ))
    tmp.replace(path)
    return path


# ── Installation dans la base ─────────────────────────────────────────────


def installed_translations(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT t.id, t.module, t.name, t.shortname, t.lang,
               (SELECT COUNT(1) FROM bible_translation_verse v
                 WHERE v.translation_id = t.id) AS verses
        FROM bible_translation t
        """
    ).fetchall()
    return {str(r[1]): {
        "id": int(r[0]), "module": str(r[1]), "name": r[2], "shortname": r[3],
        "lang": r[4], "verses": int(r[5] or 0),
    } for r in rows}


def install_payload(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    """Installe (ou remplace) une traduction ; renvoie son identifiant.

    Tout se fait dans une transaction : une installation interrompue ne
    laisse pas de traduction à moitié remplie.
    """
    meta = payload.get("metadata") or {}
    module = str(meta.get("module") or "").strip()
    verses = payload.get("verses") or []
    if not module or not verses:
        raise ValueError("Bible vide ou sans identifiant.")
    conn.execute("SAVEPOINT bible_install")
    try:
        conn.execute(
            """
            INSERT INTO bible_translation (module, name, shortname, lang)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(module) DO UPDATE SET
                name = excluded.name, shortname = excluded.shortname,
                lang = excluded.lang
            """,
            (module, meta.get("name"), meta.get("shortname"), meta.get("lang")),
        )
        translation_id = int(conn.execute(
            "SELECT id FROM bible_translation WHERE module = ?", (module,)
        ).fetchone()[0])
        conn.execute(
            "DELETE FROM bible_translation_verse WHERE translation_id = ?",
            (translation_id,),
        )
        conn.executemany(
            """
            INSERT OR IGNORE INTO bible_translation_verse
                (translation_id, book, book_name, chapter, verse, text)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (translation_id, int(v["book"]), v.get("book_name"),
                 int(v["chapter"]), int(v["verse"]), str(v["text"]))
                for v in verses
            ),
        )
        conn.execute("RELEASE SAVEPOINT bible_install")
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT bible_install")
        conn.execute("RELEASE SAVEPOINT bible_install")
        raise
    return translation_id


def remove_translation(conn: sqlite3.Connection, module: str) -> bool:
    row = conn.execute(
        "SELECT id FROM bible_translation WHERE module = ?", (module,)
    ).fetchone()
    if row is None:
        return False
    conn.execute("DELETE FROM bible_translation_verse WHERE translation_id = ?", (int(row[0]),))
    conn.execute("DELETE FROM bible_translation WHERE id = ?", (int(row[0]),))
    return True


def bundled_bibles_dir() -> Path:
    from app.utils.app_paths import resource_root

    return resource_root() / "bibles"


def user_bibles_dir() -> Path:
    from app.utils.app_paths import data_dir

    return data_dir() / "bibles"


def install_bundled_bibles(db, folder: Path | None = None) -> list[str]:
    """Installe les Bibles fournies qui manquent encore (idempotent, rapide).

    Une Bible supprimée volontairement par l'opérateur n'est pas réinstallée
    (liste ``bible_removed`` dans ``app_meta``).
    """
    folder = folder or bundled_bibles_dir()
    if not folder.is_dir():
        return []
    installed: list[str] = []
    with db.connect() as conn:
        # EXISTS s'arrête au premier verset : compter les versets de chaque
        # traduction (installed_translations) coûtait ~0,5 s par démarrage.
        present = {
            str(module)
            for (module,) in conn.execute(
                "SELECT t.module FROM bible_translation t WHERE EXISTS ("
                "SELECT 1 FROM bible_translation_verse v WHERE v.translation_id = t.id)"
            )
        }
        removed = _removed_modules(conn)
        for path in sorted(folder.glob("*.json.gz")):
            module = path.name[: -len(".json.gz")]
            if module in removed:
                continue
            if module in present:
                continue
            try:
                install_payload(conn, load_bible_file(path))
                installed.append(module)
            except Exception:
                continue
        conn.commit()
    return installed


def _removed_modules(conn: sqlite3.Connection) -> set[str]:
    try:
        row = conn.execute(
            "SELECT value FROM app_meta WHERE key = 'bible_removed'"
        ).fetchone()
    except sqlite3.Error:
        return set()
    if not row or not row[0]:
        return set()
    return {m for m in str(row[0]).split(",") if m}


def mark_removed(conn: sqlite3.Connection, module: str, removed: bool = True) -> None:
    modules = _removed_modules(conn)
    if removed:
        modules.add(module)
    else:
        modules.discard(module)
    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES ('bible_removed', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (",".join(sorted(modules)),),
    )
