"""Les références de la 2.8 pour les tests dorés de la phase 1 (comparées par `po-parite`).

Le vrai code de la 2.8 (Python + son module natif) tourne sur une COPIE de la base et écrit ce qu'il
rend. `po-parite` refait ensuite les mêmes appels avec le code Rust et compare tout, cas par cas.

    python outils/references_28.py <copie de project_on.db> <dossier de sortie> [module natif]

- La copie n'est que lue (les fonctions de la 2.8 l'ouvrent en écriture, sans rien y changer).
- Les bases de travail (maintenance, base neuve, opérations) sont créées dans le dossier de sortie.
- Le dossier de sortie contient des textes de la base : il reste sur ce poste (target/ n'est pas
  versionné).
"""

from __future__ import annotations

import html
import json
import shutil
import sqlite3
import sys
import time
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if len(sys.argv) > 3:
    sys.path.insert(0, sys.argv[3])
sys.path.insert(0, str(REPO))

from app.database.connection import Database, DatabaseConfig  # noqa: E402
from app.database.dao_bible import BibleDao  # noqa: E402
from app.database.dao_hymns import HymnsDao  # noqa: E402
from app.database.dao_media import MediaDao  # noqa: E402
from app.database.dao_playlist import PlaylistDao  # noqa: E402
from app.database.dao_sermons import SermonsDao  # noqa: E402
from app.database.dao_service_plan import ServicePlanDao  # noqa: E402
from app.utils import text_utils  # noqa: E402
from app.utils.bible_reference import parse_reference  # noqa: E402
from app.utils.settings import AppSettings  # noqa: E402

# Des cas limites écrits à la main, en plus des textes de la base.
EDGE_CASES = [
    "",
    "   ",
    "\u00a0\u202f\ufeff\u200b",
    "a\x1cb\x1dc\x1ed\x1fe",
    "ligne\u2028séparée\u2029ici",
    "&eacute;&amp;&#233;&#xE9;&#X41;&notit; &amp &ampx &zzz; &#; &#150;&#0;&#xD800;&#1114112;&#11;",
    "<b>Gras</b><br/>nouvelle<br />ligne<br>encore &nbsp;fin",
    "¶ 12 Amen\n  ¶3 Gloire ¶",
    "Â¶ 5",
    "Ã‚Â§ 6",
    "L’ANGE DE DIEU",
    "QU’IL VIENNE AUJOURD’HUI",
    "EST-CE LE SCEAU II ?",
    "A-T-IL DIT : « AMEN » ?",
    "LA FOI - JEFFERSONVILLE IN USA",
    "ECOUTEZ-LE - DURBAN AFRIQUE",
    "PHOENIX AZ USA",
    "AFRIQUE DU SUD",
    "TORONTO ON CANADA",
    "SERMON 12",
    "Message 3 : la foi",
    "ΟΔΟΣ Σ",
    "Straße ﬁn ǆ İstanbul",
    "M. Branham et Mme Dupont sont à St. Louis. Le Dr. Lee est venu. Voir v. 12 et ch. 3. J.-C. est Seigneur.",
    "3. le premier point. 4. Le second point... et la suite! Vraiment? Oui… «Amen.» (Fin.)",
    "https://www.exemple.org/un/très/long/chemin/qui/ne/finit/jamais/et/dépasse/la/limite/de/caractères/autorisée/pour/une/partie/de/texte/ainsi/de/suite/encore/et/encore/jusqu/a/la/fin",
    "Refrain :\nGloire à Dieu",
    "[Chœur] Gloire",
    "2. Refrain - Refrain\nAmen",
    "Refrains d'été",
    "DERNIER REFRAIN\nAlléluia",
    "Chorus",
    "  - Refrain ; Il vient",
    "BK 112-3",
    "47-1123 Les enfants E-7O",
    "CHAPITRE 3  L'âge   d'Éphèse",
    "INTRODUCTION",
    "1965-12-31",
    "__NODATE__",
    '"colonne de feu"',
    "« Grâce infinie » foi",
    'a"b c"d',
    '"ouvert sans fin',
]


def write(out: Path, name: str, data) -> None:
    (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def every(items, step):
    return [x for i, x in enumerate(items) if i % step == 0]


def collect_texts(conn: sqlite3.Connection) -> dict[str, list[str]]:
    q = lambda sql: [r[0] or "" for r in conn.execute(sql).fetchall()]  # noqa: E731
    paragraphs = q("SELECT text FROM sermon_paragraph ORDER BY id")
    longest = sorted(paragraphs, key=len, reverse=True)[:60]
    return {
        "titres": q("SELECT title FROM sermon ORDER BY id") + q("SELECT title FROM hymn ORDER BY id"),
        "lieux": sorted(set(q("SELECT location FROM sermon") + q("SELECT printed_location FROM sermon"))),
        "references": every(q("SELECT ref FROM sermon_paragraph ORDER BY id"), 40),
        "paragraphes": every(paragraphs, 400) + longest,
        "strophes": q("SELECT text FROM hymn_stanza ORDER BY id"),
        "versets": every(q("SELECT text FROM bible_translation_verse ORDER BY id"), 500),
        "livres": sorted(set(q("SELECT book_name FROM bible_translation_verse GROUP BY translation_id, book"))),
        "cas": EDGE_CASES,
    }


def long_texts(conn: sqlite3.Connection) -> list[str]:
    """Des textes longs : plusieurs paragraphes d'une prédication (séparés par une ligne vide ou un
    retour), assez pour passer au regroupement glouton (plus de 600 unités)."""
    out = []
    ids = [r[0] for r in conn.execute("SELECT id FROM sermon ORDER BY id").fetchall()]
    for sermon_id in every(ids, 300):
        rows = [r[0] for r in conn.execute(
            "SELECT text FROM sermon_paragraph WHERE sermon_id = ? ORDER BY paragraph_no LIMIT 60", (sermon_id,))]
        out.append("\n\n".join(rows[:8]))
        out.append("\n".join(rows[:5]))
        out.append(" ".join(rows))
    return out


def text_references(conn: sqlite3.Connection) -> dict:
    t = collect_texts(conn)
    everything = sorted(set(sum(t.values(), [])))
    c = {}
    c["unaccent"] = {s: text_utils.unaccent(s) for s in everything}
    c["html_unescape"] = {s: html.unescape(s) for s in everything}
    c["clean_text"] = {s: text_utils.clean_text(s) for s in everything}
    c["search_key"] = {s: Database._search_key(s) for s in everything}
    short = sorted(set(t["titres"] + t["lieux"] + t["cas"] + t["livres"]))
    c["fts_query"] = {s: SermonsDao._fts_query(s) for s in short}
    c["hymn_fts_query"] = {s: HymnsDao._fts_query(s) for s in short}
    c["plain_query"] = {s: SermonsDao._plain_query(s) for s in short}
    c["title_case_words"] = {s: Database.title_case_words(s) for s in short}
    c["display_location"] = {s: Database.display_location(s) for s in short}
    c["title_case_french"] = {s: Database._title_case_french(s) for s in short}
    c["mostly_uppercase"] = {s: Database._mostly_uppercase(s) for s in short}
    c["clean_sermon_title"] = {s: Database._clean_sermon_title_for_canonical(s) for s in short}
    c["clean_hymn_title"] = {s: Database._clean_hymn_title_for_canonical(s) for s in short}
    c["clean_expose_title"] = {s: SermonsDao._clean_expose_title(s) for s in short}
    c["normalize_filter_date"] = {s: SermonsDao._normalize_filter_date(None, s) for s in short}
    refs = sorted(set(t["references"] + t["cas"]))
    c["marker_from_ref"] = {s: Database._marker_from_ref(s, 7) for s in refs}
    c["paragraph_marker"] = {s: SermonsDao._get_marker(None, s, 7) for s in refs}
    c["expose_ref_parts"] = {s: SermonsDao._expose_ref_parts(s) for s in refs}
    stanzas = sorted(set(t["strophes"] + t["cas"]))
    c["strip_hymn_label"] = {s: text_utils.strip_hymn_projection_label(s) for s in stanzas}
    c["is_chorus"] = {s: Database._detect_hymn_chorus(s) for s in stanzas}
    c["format_reference"] = [
        [a, b, m, SermonsDao._format_reference(a, b, m)]
        for a, b, m in [(" 47-0412", "La Foi", ""), ("", "", "¶1"), ("BK-AGES-CH01", " Titre ", " 3-1 ")]
    ]
    chapters = conn.execute(
        "SELECT date, title, tradition FROM sermon WHERE date LIKE 'BK-AGES%' ORDER BY id").fetchall()
    c["expose_chapter_num"] = [
        [d, ti, tr, SermonsDao._expose_chapter_num(d, ti, tr)] for d, ti, tr in chapters
    ] + [[d, ti, "shp", SermonsDao._expose_chapter_num(d, ti, "shp")] for d, ti, tr in chapters if tr == "VGR"]

    texts = sorted(set(t["paragraphes"] + t["versets"] + t["cas"] + long_texts(conn)))
    c["split_text"] = [
        [s, m, mn, k, text_utils.split_text_into_slides(s, m, mn, keep_line_breaks=k)]
        for s in texts for (m, mn, k) in [(280, 60, True), (120, 60, False), (500, 0, True), (40, 60, True)]
    ]
    c["split_stanza"] = [
        [s, ml, mc, kc, text_utils.split_hymn_stanza(s, ml, mc, keep_couplets=kc)]
        for s in stanzas for (ml, mc, kc) in [(2, 280, True), (4, 280, False), (1, 120, True), (3, 60, True)]
    ]
    return c


BIBLE_QUERIES = [
    "Jean 3:16", "1 co 13", "esaie 53.5", "Ps 23", "1jean 1 9", "J 3", "Jean 0", "Apocalypse 1", "Jean",
    "gen 1", "Gen. 1:1", "2 Rois 5 14", "3 jean 1", "Cantique 2", "  jn 3 16 ", "Jn3:16", "1Co13:4",
    "Romains 8,28", "Héb 11.1", "matt 5:3-10", "Psaumes 1000", "ps 23 1", "EX 3:14", "1 S 17", "",
]


def bible_references(db: Database) -> list:
    dao = BibleDao(db)
    out = []
    for translation in dao.list_translations():
        books = dao.list_translation_books(translation["id"])
        queries = list(BIBLE_QUERIES)
        for book in books:
            name = book["name"]
            short = text_utils.unaccent(name).replace(" ", "")[:3]
            queries += [f"{name} 3", f"{name} 3:16", f"{short} 1.1", f"{short[:2]} 2 3"]
        for query in queries:
            r = parse_reference(query, books)
            out.append([translation["id"], query,
                        None if r is None else [r.book_id, r.book_name, r.chapter, r.verse, r.label]])
    return out


def call(out: list, name: str, fn, *args, **kwargs) -> None:
    started = time.perf_counter()
    result = fn(*args, **kwargs)
    out.append({"fn": name, "args": list(args), "kwargs": kwargs, "out": result,
                "ms": round((time.perf_counter() - started) * 1000, 1)})


def query_references(db: Database) -> list:
    s, b, h = SermonsDao(db), BibleDao(db), HymnsDao(db)
    p, sp, m = PlaylistDao(db), ServicePlanDao(db), MediaDao(db)
    out: list = []
    for kwargs in [{}, {"translator": "vgr"}, {"translator": "SHP", "language": "fr"}, {"tradition": "BSS"},
                   {"title_query": "foi"}, {"title_query": "FERMÉ"}, {"title_query": '"colonne"'},
                   {"title_query": "assurance", "sort_by": "title"},
                   {"date_from": "1960-01-01", "date_to": "1963-12-31"}, {"date_from": "__NODATE__"},
                   {"location_query": "jeffersonville", "sort_by": "location"}, {"location_query": "Phoenix"},
                   {"language": "fr", "limit": 50}, {"language": "en"}]:
        call(out, "list_sermons", s.list_sermons, **kwargs)
    for kwargs in [{}, {"translator": "SHP"}, {"title_query": "foi"}, {"language": "fr"}]:
        call(out, "list_sermon_years", s.list_sermon_years, **kwargs)
    for lang in ["fr", "en", "FRA"]:
        call(out, "list_branham_translators", s.list_branham_translators, lang)
    ids = [r["id"] for r in s.list_sermons()]
    for sid in every(ids, 250) + ["int_999999"]:
        call(out, "get_sermon", s.get_sermon, sid)
    for sid in every(ids, 200):
        call(out, "list_paragraphs", s.list_paragraphs, sid)
    for query, kwargs in [
        ("grâce", {"language": "fr"}), ("ferme assurance", {"language": "fr"}), ('"colonne de feu"', {"language": "fr"}),
        ("« la foi »", {"language": "fr", "translator": "shp"}), ("Éternel Dieu", {"translator": "BSS"}),
        ("foi*", {"language": "fr"}), ("ange", {"language": "fr", "limit": 7}), ("Jésus-Christ", {}),
        ("zzqxw", {"language": "fr", "substring_fallback": False}), ("ernel Die", {"language": "fr"}),
        ("ait là, d", {"language": "fr", "translator": "VGR"}), ("   ", {}), ('"', {}), ("AND OR NOT", {"language": "fr"}),
    ]:
        call(out, "search_paragraphs", s.search_paragraphs, query, **kwargs)
    books = s.list_books()
    call(out, "list_books", s.list_books)
    for book in books + [{"key": "absent"}]:
        call(out, "list_book_chapters", s.list_book_chapters, book["key"])
        for query in ["Dieu", "ernel", "Éphèse"]:
            call(out, "search_book", s.search_book, query, book["key"], limit=40)
        for chapter in s.list_book_chapters(book["key"])[:2]:
            call(out, "book_of_chapter", s.book_of_chapter, chapter["id"])
    for translator in ["VGR", "SHP", "shp"]:
        chapters = s.list_expose_chapters(translator)
        call(out, "list_expose_chapters", s.list_expose_chapters, translator)
        for chapter in chapters[:3] + chapters[-1:]:
            call(out, "list_expose_pages", s.list_expose_pages, chapter["id"])
            pages = s.list_expose_pages(chapter["id"])
            for page in (pages[:1] + pages[len(pages) // 2: len(pages) // 2 + 1] + [9999]):
                call(out, "list_expose_page_paragraphs", s.list_expose_page_paragraphs, chapter["id"], page)
        call(out, "search_expose", s.search_expose, "Éphèse", translator)
        call(out, "search_expose", s.search_expose, "lumiere", translator, 25)

    translations = b.list_translations()
    call(out, "list_translations", b.list_translations)
    for t in translations:
        call(out, "list_translation_books", b.list_translation_books, t["id"])
        for book in [1, 19, 43, 66]:
            call(out, "list_translation_chapters", b.list_translation_chapters, t["id"], book)
        for book, chapter in [(43, 3), (19, 23), (1, 1), (66, 22)]:
            call(out, "list_translation_verses", b.list_translation_verses, t["id"], book, chapter)
    call(out, "list_books_legacy", b.list_books)
    for book in b.list_books():
        call(out, "list_chapters_legacy", b.list_chapters, book["id"])
        for chapter in b.list_chapters(book["id"]):
            call(out, "list_verses_legacy", b.list_verses, book["id"], chapter)

    for kwargs in [{}, {"language": "fr"}, {"limit": 20}, {"query": "grace"}, {"query": "Jésus"},
                   {"query": "123"}, {"language": "fr", "query": "  gloire  "}]:
        call(out, "list_hymns", h.list_hymns, **kwargs)
    hymn_ids = [r["id"] for r in h.list_hymns()]
    for hid in every(hymn_ids, 100) + [999999]:
        call(out, "get_hymn", h.get_hymn, hid)
    for hid in hymn_ids:
        call(out, "list_stanzas", h.list_stanzas, hid)
    for query in ["grâce", "Jésus revient", "refrain", "alléluia gloire", "ernel", "zzqxw", "   ", "o"]:
        call(out, "search_stanzas", h.search_stanzas, query)
        call(out, "search_stanzas", h.search_stanzas, query, limit=5)

    call(out, "list_folders", p.list_folders)
    call(out, "list_items", p.list_items, None)
    for folder in p.list_folders():
        call(out, "list_items", p.list_items, folder["id"])
        call(out, "list_sections", sp.list_sections, folder["id"])
        call(out, "get_start_time", sp.get_start_time, folder["id"])
    call(out, "list_all_items", p.list_all_items)
    call(out, "list_media", m.list_media)
    for media in m.list_media():
        call(out, "get_media", m.get_media, media["id"])
    return out


def prepare_maintenance(source: Path, target: Path) -> None:
    """Une copie dont les métadonnées sont à refaire : la maintenance de la 2.8 et celle de la 3.0
    les recalculent toutes, et les résultats sont comparés ligne à ligne."""
    for suffix in ("", "-wal", "-shm"):
        Path(str(target) + suffix).unlink(missing_ok=True)
    with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    conn = sqlite3.connect(target)
    conn.executescript(
        """
        DROP TABLE IF EXISTS sermon_paragraph_fts;
        DROP TABLE IF EXISTS hymn_stanza_fts;
        UPDATE sermon SET canonical_title = '', title_search = '';
        UPDATE sermon_paragraph SET marker = '', text = '';
        UPDATE hymn SET canonical_title = '', title_search = '';
        UPDATE hymn_stanza SET label = '', is_chorus = 0;
        DELETE FROM bible_translation_verse;
        DELETE FROM app_meta WHERE key IN ('startup_maintenance_version', 'vacuum_version');
        """
    )
    conn.commit()
    conn.execute("VACUUM")
    conn.close()


OPERATIONS = [
    ["create_folder", "Culte du dimanche"],
    ["create_folder", "Soirée de prière"],
    ["add_item", "bible", "Jean 3:16", "Car Dieu a tant aimé le monde", None, ""],
    ["add_item", "custom", "Annonce", "Bienvenue", 1, "C:/fonds/a.png"],
    ["add_items", [["hymn", "Cantique 12", "Gloire"], ["sermon", "47-0412", "La foi"], ["custom", "Note", "Prière"]], 1],
    ["add_items", [], 1],
    ["move_item", 3, 1, 1],
    ["move_item", 3, 9, 1],
    ["move_item", 99, 1, 1],
    ["snapshot_folders", [1]],
    ["duplicate_items", [5, 2]],
    ["list_items", 1],
    ["restore_folders"],
    ["list_items", 1],
    ["reorder_items", 1, [2]],
    ["reorder_items", 1, [5, 4, 3, 2]],
    ["copy_items", [2, 4], 2],
    ["move_items_to_folder", [3], 2],
    ["update_item", 2, "Annonce (modifiée)", "Bienvenue à tous"],
    ["update_item_background", 4, "C:/fonds/b.png"],
    ["update_item_sort_order", 5, 10, 2],
    ["delete_item", 1],
    ["delete_items", [4, 999]],
    ["import_folder", "Transférée", [{"source": "custom", "reference": "R1", "text": "T1", "background": ""},
                                     {"source": "media", "reference": "R2", "text": "T2", "background": "x.png"}]],
    ["rename_folder", 2, "Soirée"],
    ["set_start_time", 1, "09:30"],
    ["get_start_time", 1],
    ["add_section", 1, "Louange", 20, None],
    ["add_section", 1, "Prédication", -5, 2],
    ["move_section", 2, -1],
    ["move_section", 2, -1],
    ["update_section", 1, "Louange et adoration", 25, 3],
    ["list_sections", 1],
    ["delete_section", 2],
    ["delete_folder", 3],
    ["list_folders"],
    ["list_all_items"],
    ["add_media", "Fond", "C:/m/fond.png", "image"],
    ["add_media", "Autre nom", "C:/m/fond.png", "image"],
    ["add_media", "Site", "https://exemple", "web"],
    ["set_loop", 1, True],
    ["set_duration", 1, 99999],
    ["rename_media", 1, "Fond bleu"],
    ["purge_web_media"],
    ["list_media"],
    ["import_hymn", "GRÂCE INFINIE", ["Grâce infinie, ô Dieu", "Refrain\nAlléluia", "Il vient"], "12", "fr"],
    ["save_hymn", None, "  Il vient  ", [["Il vient bientôt", False], ["Gloire", True], ["  ", False]], None, "fr"],
    ["save_hymn", 3, "Il revient", [["Refrain : Il revient", False], ["Amen", True]], "7", "fr"],
    ["hymn_exists", "  grâce   INFINIE "],
    ["hymn_exists", "Grace infinie"],
    ["exact_duplicate_exists", "Grâce infinie", ["Grâce infinie, ô Dieu", "Refrain\nAlléluia", "Il vient"]],
    ["exact_duplicate_exists", "Grâce infinie", ["Grâce infinie, ô Dieu"]],
    ["search_stanzas", "alleluia"],
    ["list_stanzas", 3],
    ["delete_hymn", 1],
    ["list_hymns"],
]


def run_operations(db: Database) -> list:
    p, sp, m, h = PlaylistDao(db), ServicePlanDao(db), MediaDao(db), HymnsDao(db)
    snapshot = None
    results = []
    for op in OPERATIONS:
        name, args = op[0], op[1:]
        if name == "snapshot_folders":
            snapshot = p.snapshot_folders(*args)
            result = {str(k): v for k, v in snapshot.items()}
        elif name == "restore_folders":
            result = p.restore_folders(snapshot)
        elif name == "import_folder":
            result = p.import_folder(*args)
        elif name == "save_hymn":
            hid, title, stanzas, number, language = args
            result = h.save_hymn(hid, title, [tuple(s) for s in stanzas], number, language)
        elif hasattr(p, name):
            result = getattr(p, name)(*args)
        elif hasattr(sp, name):
            result = getattr(sp, name)(*args)
        elif hasattr(m, name):
            result = getattr(m, name)(*args)
        else:
            result = getattr(h, name)(*args)
        results.append(result)
    return results


def settings_references(out: Path) -> list:
    import os
    import tempfile

    cases = []
    for path in [REPO / "data" / "settings.json", Path(os.environ.get("APPDATA", "")) / "Project-On" / "data" / "settings.json"]:
        if path.is_file():
            cases.append(["fichier", str(path)])
    payloads = [
        {},
        {"projection": {"text_size": "4", "ref_size": -3, "line_height": 0.1, "panel_opacity": 7, "font_family": "  ",
                        "uppercase": "non", "bg_mode": "image", "bg_image": "Z:/absent.png",
                        "media_default_duration": 999, "auto_fit": True, "letter_spacing": "1_000",
                        "background_dimmer": "0.5", "max_lines": 3.9, "media_fit": "COVER", "media_backdrop": "rouge",
                        "media_backdrop_dim": "beaucoup", "text_color": 12, "align": ["a"], "shadow_blur": None}},
        {"appearance": {"theme": "LIGHT", "language": "de", "mica": None, "low_power": "oui", "rail_compact": 0}},
        {"split": {"max_chars": "5000", "hymn_max_lines": 2.9, "text_enabled": 0, "keep_line_breaks": [],
                   "show_part_counter": "false"}},
        {"hdmi": {"key_color": " Magenta ", "text_scale": 0, "offset_y": -900, "layout": "OBS", "screen": "  ",
                  "style": {"text_size": 30.5, "accent_mode": "AUTO", "line_height": "3", "bg_color_2": "",
                            "bg_color": " ", "letter_spacing": "x", "max_lines": 2.5, "edge_margin": 3.5,
                            "font_weight": "Light", "animation_type": "zoom", "show_kicker": "non"}}},
        {"hdmi": {"style": "pas un objet", "use_obs_style": 0}, "projection": "pas un objet"},
        {"projection": {"text_size": 70, "font_family": "Passion One", "uppercase": True, "bg_mode": "video",
                        "bg_video": str(REPO / "README.md")}, "church": {"name": "Tabernacle"}, "inconnu": [1, 2]},
    ]
    folder = Path(tempfile.mkdtemp(dir=out))
    for index, payload in enumerate(payloads):
        path = folder / f"reglages-{index}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        cases.append(["synthetique", str(path)])
    broken = folder / "illisible.json"
    broken.write_text("{ cassé", encoding="utf-8")
    cases.append(["illisible", str(broken)])
    results = []
    for kind, path in cases:
        s = AppSettings.load(Path(path))
        results.append({"cas": kind, "chemin": path, "warning": s.load_warning,
                        "projection": asdict(s.projection), "appearance": asdict(s.appearance),
                        "hdmi": asdict(s.hdmi), "split": asdict(s.split)})
    return results


def main() -> None:
    source, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    started = time.perf_counter()
    if text_utils._NATIVE_SQLITE_EXTENSION is None:
        print("ATTENTION : module natif absent, la 2.8 n'est pas dans ses conditions réelles.")

    ro = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    write(out, "textes.json", text_references(ro))
    print(f"textes : {time.perf_counter() - started:.0f} s")
    db = Database(DatabaseConfig(db_path=source))
    write(out, "references_bibliques.json", bible_references(db))
    write(out, "requetes.json", query_references(db))
    print(f"requêtes : {time.perf_counter() - started:.0f} s")
    ro.close()

    prepare_maintenance(source, out / "maintenance-28.db")
    shutil.copy2(out / "maintenance-28.db", out / "maintenance-30.db")
    Database(DatabaseConfig(db_path=out / "maintenance-28.db")).initialize()
    print(f"maintenance : {time.perf_counter() - started:.0f} s")

    Database(DatabaseConfig(db_path=out / "neuve-28.db")).initialize()
    for name in ("operations-28.db", "operations-30.db"):
        shutil.copy2(out / "neuve-28.db", out / name)
    write(out, "operations.json", {"operations": OPERATIONS,
                                   "resultats": run_operations(Database(DatabaseConfig(db_path=out / "operations-28.db")))})
    write(out, "reglages.json", settings_references(out))
    write(out, "manifeste.json", {
        "copie": str(source),
        "bible_json": str(REPO / "bible_json"),
        "natif": text_utils._NATIVE_SQLITE_EXTENSION is not None,
        "python": sys.version.split()[0],
        "sqlite": sqlite3.sqlite_version,
    })
    print(f"terminé en {time.perf_counter() - started:.0f} s : {out}")


if __name__ == "__main__":
    main()
