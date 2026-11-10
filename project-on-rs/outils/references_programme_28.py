"""Les références du programme de la 2.8 (phase 3, comparées par `po-parite programme`).

Le vrai code de la 2.8 prépare des programmes entiers à partir d'une COPIE de la base : sermons,
cantiques, chapitres de la Bible et chapitres des ouvrages (Exposé, biographies, brochures). Pour
chacun, il note les entrées (référence, texte), puis, pour plusieurs réglages de découpage, les
slides, le premier slide de chaque entrée et le slide tel que les écrans le montrent.

Les fonctions de la 2.8 sont appelées telles quelles, sans fenêtre ni objet Qt : un simple espace
de noms leur tient lieu de `self` (elles ne lisent que les réglages de découpage).

    py -3.14 outils/references_programme_28.py <copie de project_on.db> <dossier de sortie>
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from app.database.connection import Database, DatabaseConfig  # noqa: E402
from app.database.dao_bible import BibleDao  # noqa: E402
from app.database.dao_hymns import HymnsDao  # noqa: E402
from app.database.dao_sermons import SermonsDao  # noqa: E402
from app.utils.library_controller import LibraryController as LC  # noqa: E402
from app.utils.project_on_controller import ProjectOnController as POC  # noqa: E402
from app.utils.settings import SplitSettings  # noqa: E402


def user_split() -> dict:
    """Les réglages de découpage de l'utilisateur, lus sans rien écrire."""
    path = Path(os.environ.get("APPDATA", "")) / "Project-On" / "data" / "settings.json"
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")).get("split") or {})
    except (OSError, ValueError):
        return {}


VARIANTS = {
    "utilisateur": user_split(),
    "defaut": {},
    "sans_decoupage": {"text_enabled": False, "hymn_enabled": False},
    "court_sans_compteur": {
        "max_chars": 150, "keep_line_breaks": False, "hymn_max_lines": 4, "hymn_keep_couplets": False,
        "hymn_repeat_chorus": False, "show_part_counter": False,
    },
}


def controller(split: SplitSettings) -> SimpleNamespace:
    me = SimpleNamespace(_split=split, _MIN_CHARS=POC._MIN_CHARS)
    me._clean_text = POC._clean_text
    me._clean_chunk = POC._clean_chunk
    me._split_text = lambda text: POC._split_text(me, text)
    me._split_entry = lambda source, text: POC._split_entry(me, source, text)
    return me


def program(split: SplitSettings, source: str, entries: list[tuple[str, str]]) -> dict:
    slides, starts = POC.build_slides(controller(split), source, entries, True)
    shown = [POC.presentation_slide(s) for s in slides]
    return {
        "slides": [[s.reference, s.text] for s in slides],
        "starts": starts,
        "ecran": [[s.reference, s.text] for s in shown],
    }


LIB = SimpleNamespace(
    _clean_text=LC._clean_text,
    _format_sermon_reference=LC._format_sermon_reference,
    _format_hymn_reference=LC._format_hymn_reference,
)


def programs(source: str, entries_for) -> dict:
    """Les programmes d'une même source pour chaque réglage (les entrées peuvent en dépendre)."""
    out = {}
    for name, payload in VARIANTS.items():
        split = SplitSettings.from_payload(payload)
        entries = entries_for(split)
        out[name] = {"entrees": [list(e) for e in entries], **program(split, source, entries)}
    return out


def sermons(dao: SermonsDao) -> list[dict]:
    cases = []
    listed = dao.list_sermons(language="fr")
    for s in listed[::23]:
        title = str(s.get("title", ""))
        date = str(s.get("date_code", "") or "") or str(s.get("date", "") or "")
        paragraphs = dao.list_paragraphs(s["id"], "fr")
        prepared = LC._prepare_sermon_entries(LIB, paragraphs, title, date)
        entries = LC._group_alineas([(p["reference"], p["text"]) for p in prepared])
        clicked = prepared[len(prepared) // 2]["reference"] if prepared else ""
        cases.append({
            "genre": "sermon", "id": s["id"], "date": date, "titre": title,
            "titre_programme": LC._format_sermon_reference(date, title, "").strip(" -"),
            "clic": clicked, "focus": LC._find_entry_index(entries, clicked),
            "programmes": programs("sermon", lambda _split, e=entries: e),
        })
    return cases


def hymns(dao: HymnsDao) -> list[dict]:
    cases = []
    for h in dao.list_hymns()[::7]:
        hymn = dao.get_hymn(h["id"]) or {}
        number, title = hymn.get("number", "") or "", hymn.get("title", "") or ""
        prepared = LC._prepare_hymn_stanzas(LIB, dao.list_stanzas(h["id"]), number, title)

        def entries_for(split, prepared=prepared):
            me = SimpleNamespace(_project=SimpleNamespace(split_settings=split), _clean_text=LC._clean_text)
            return LC._hymn_program_entries(me, prepared)

        cases.append({
            "genre": "hymn", "id": h["id"], "numero": number, "titre": title,
            "titre_programme": LC._format_hymn_reference(number, title, "").strip(" -"),
            "programmes": programs("hymn", entries_for),
        })
    return cases


def bible(dao: BibleDao) -> list[dict]:
    cases = []
    for t in dao.list_translations():
        books = dao.list_translation_books(t["id"])
        for book in books[::9]:
            chapters = dao.list_translation_chapters(t["id"], book["id"])
            for chapter in chapters[::6]:
                verses = dao.list_translation_verses(t["id"], book["id"], chapter)
                name = str(book.get("name", ""))
                entries = [(f"{name} {chapter}:{int(v['verse'])}".strip(), LC._clean_text(v["text"])) for v in verses]
                cases.append({
                    "genre": "bible", "traduction": t["id"], "livre": book["id"], "nom": name, "chapitre": chapter,
                    "programmes": programs("bible", lambda _split, e=entries: e),
                })
    return cases


def books(dao: SermonsDao) -> list[dict]:
    cases = []
    lib = SimpleNamespace(_sermons_dao=dao, _BOOK_REFERENCE_TITLES=LC._BOOK_REFERENCE_TITLES)
    lib._expose_book_prefix = lambda ch: LC._expose_book_prefix(lib, ch)
    for key in ("ages-vgr", "ages-shp", "sent", "pvsa", "brochures"):
        chapters = dao.list_book_chapters(key)
        for ch in chapters[::3]:
            full = LC._expose_full_reference(lib, ch["id"], str(ch.get("title", "")))
            rows = []
            for page in dao.list_expose_pages(ch["id"]):
                rows.extend(dao.list_expose_page_paragraphs(ch["id"], page) or [])
            entries = []
            for p in rows:
                reference = full
                m = re.search(r"(\d+)-(\d+)", str(p.get("ref", "")))
                if m:
                    reference = f"{full} · Page {m.group(1)} §{m.group(2)}"
                entries.append((reference, LC._clean_text(p.get("text", ""))))
            cases.append({
                "genre": "livre", "cle": key, "chapitre": ch["id"], "titre": str(ch.get("title", "")),
                "reference": full, "programmes": programs("sermon", lambda _split, e=entries: e),
            })
    return cases


def main() -> None:
    source, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    db = Database(DatabaseConfig(db_path=source))
    data = {
        "reglages": VARIANTS,
        "cas": sermons(SermonsDao(db)) + hymns(HymnsDao(db)) + bible(BibleDao(db)) + books(SermonsDao(db)),
    }
    (out / "programme.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    kinds = {}
    for case in data["cas"]:
        kinds[case["genre"]] = kinds.get(case["genre"], 0) + 1
    print(f"{len(data['cas'])} programmes {kinds} en {time.perf_counter() - started:.0f} s")


if __name__ == "__main__":
    main()
