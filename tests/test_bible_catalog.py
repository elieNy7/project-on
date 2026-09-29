"""Bibles libres : conversion, fichiers, installation et gestion."""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.database.connection import Database, DatabaseConfig
from app.utils import bible_catalog as bc

ROOT = Path(__file__).resolve().parents[1]

SCROLLMAPPER = {
    "translation": "FreTest: Bible de test",
    "books": [
        {"name": "Genesis", "chapters": [{"chapter": 1, "verses": [
            {"verse": 1, "text": "Au commencement Dieu créa le ciel et la terre."},
            {"verse": 2, "text": "La terre était informe et vide."},
        ]}]},
        {"name": "Tobit", "chapters": [{"chapter": 1, "verses": [
            {"verse": 1, "text": "Livre deutérocanonique ignoré."},
        ]}]},
        {"name": "I John", "chapters": [{"chapter": 4, "verses": [
            {"verse": 8, "text": "Dieu est amour."},
        ]}]},
        {"name": "Revelation of John", "chapters": [{"chapter": 22, "verses": [
            {"verse": 21, "text": "Que la grâce soit avec tous !"},
        ]}]},
    ],
}


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(DatabaseConfig(db_path=tmp_path / "bible.db"))
    database.initialize()
    return database


def test_book_numbers_cover_all_naming_styles() -> None:
    assert bc.book_number("Genesis") == 1
    assert bc.book_number("Genèse") == 1
    assert bc.book_number("I Samuel") == 9
    assert bc.book_number("III John") == 64
    assert bc.book_number("Revelation of John") == 66
    assert bc.book_number("Apocalypse") == 66
    assert bc.book_number("Cantique des cantiques") == 22
    assert bc.book_number("Tobit") is None
    assert bc.book_display_name(43, "fr") == "Jean"
    assert bc.book_display_name(43, "en") == "John"
    assert bc.book_display_name(43, "es") == "Juan"


def test_scrollmapper_conversion_skips_deuterocanon_and_names_books() -> None:
    entry = bc.BibleEntry("FreTest", "Test", "Bible de test", "fr")
    payload = bc.from_scrollmapper(SCROLLMAPPER, entry)
    assert payload["metadata"]["module"] == "sm_fretest"
    books = {(v["book"], v["book_name"]) for v in payload["verses"]}
    assert books == {(1, "Genèse"), (62, "1 Jean"), (66, "Apocalypse")}
    assert len(payload["verses"]) == 4


def test_zefania_and_beblia_xml(tmp_path: Path) -> None:
    zefania = tmp_path / "lingala.xml"
    zefania.write_text(
        '<XMLBIBLE biblename="Biblia Test"><BIBLEBOOK bnumber="43" bname="Yoane">'
        '<CHAPTER cnumber="3"><VERS vnumber="16">Pamba te Nzambe alingaki mokili…</VERS>'
        "</CHAPTER></BIBLEBOOK></XMLBIBLE>",
        encoding="utf-8",
    )
    payload = bc.load_bible_file(zefania, lang="ln")
    assert payload["metadata"]["name"] == "Biblia Test"
    assert payload["verses"][0] == {
        "book": 43, "book_name": "Jean", "chapter": 3, "verse": 16,
        "text": "Pamba te Nzambe alingaki mokili…",
    }

    beblia = tmp_path / "sw.xml"
    beblia.write_text(
        '<bible translation="Swahili Test"><testament name="New"><book number="1">'
        '<chapter number="1"><verse number="1">Hapo mwanzo</verse></chapter>'
        "</book></testament></bible>",
        encoding="utf-8",
    )
    payload = bc.load_bible_file(beblia, lang="sw")
    assert payload["verses"][0]["book"] == 1 and payload["verses"][0]["text"] == "Hapo mwanzo"


def test_install_replace_and_remove(db: Database, tmp_path: Path) -> None:
    entry = bc.BibleEntry("FreTest", "Test", "Bible de test", "fr")
    payload = bc.from_scrollmapper(SCROLLMAPPER, entry)
    with db.connect() as conn:
        tid = bc.install_payload(conn, payload)
        conn.commit()
        assert bc.installed_translations(conn)["sm_fretest"]["verses"] == 4
        # Réinstallation : remplacée, pas dupliquée.
        assert bc.install_payload(conn, payload) == tid
        assert bc.installed_translations(conn)["sm_fretest"]["verses"] == 4

    from app.database.dao_bible import BibleDao

    dao = BibleDao(db)
    books = dao.list_translation_books(tid)
    assert books[0] == {"id": 1, "name": "Genèse"}
    assert dao.list_translation_verses(tid, 62, 4)[0]["text"] == "Dieu est amour."

    with db.connect() as conn:
        assert bc.remove_translation(conn, "sm_fretest") is True
        conn.commit()
        assert "sm_fretest" not in bc.installed_translations(conn)


def test_bundled_bibles_installed_once_and_removal_respected(db: Database, tmp_path: Path) -> None:
    folder = tmp_path / "bibles"
    entry = bc.BibleEntry("FreTest", "Test", "Bible de test", "fr")
    bc.save_payload(bc.from_scrollmapper(SCROLLMAPPER, entry), folder)
    assert (folder / "sm_fretest.json.gz").exists()

    assert bc.install_bundled_bibles(db, folder) == ["sm_fretest"]
    assert bc.install_bundled_bibles(db, folder) == []  # déjà là

    with db.connect() as conn:
        bc.remove_translation(conn, "sm_fretest")
        bc.mark_removed(conn, "sm_fretest")
        conn.commit()
    assert bc.install_bundled_bibles(db, folder) == []  # retirée volontairement


def test_shipped_bibles_are_complete_public_domain_payloads() -> None:
    folder = ROOT / "bibles"
    files = sorted(folder.glob("*.json.gz"))
    bundled = {e.module for e in bc.CATALOG if e.bundled}
    assert {p.name[: -len(".json.gz")] for p in files} == bundled
    for path in files:
        payload = json.loads(gzip.decompress(path.read_bytes()))
        assert len(payload["verses"]) > 30000, path.name
        assert {v["book"] for v in payload["verses"]} == set(range(1, 67)), path.name


def test_download_converts_the_catalog_file(monkeypatch) -> None:
    raw = json.dumps(
        {"translation": "X", "books": [
            {"name": "Genesis", "chapters": [{"chapter": 1, "verses": [
                {"verse": i, "text": f"verset {i}"} for i in range(1, 1201)
            ]}]}
        ]}
    ).encode("utf-8")

    class _Response:
        headers = {"Content-Length": str(len(raw))}

        def __init__(self):
            self._data = [raw, b""]

        def read(self, _n):
            return self._data.pop(0)

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    seen = []
    monkeypatch.setattr(bc.urllib.request, "urlopen", lambda req, timeout: (seen.append(req.full_url), _Response())[1])
    progress = []
    payload = bc.download(bc.entry_by_code("KJV"), lambda d, t: progress.append((d, t)))
    assert seen[0].endswith("/formats/json/KJV.json")
    assert payload["metadata"]["module"] == "sm_kjv" and len(payload["verses"]) == 1200
    assert progress[-1] == (len(raw), len(raw))


def test_bible_manager_dialog_lists_and_imports(db: Database, tmp_path: Path) -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from app.ui.bible_manager_dialog import BibleManagerDialog

    dialog = BibleManagerDialog(db)
    try:
        changed = []
        dialog.biblesChanged.connect(lambda: changed.append(True))
        path = tmp_path / "test.json"
        big = dict(SCROLLMAPPER)
        big["books"] = [{"name": "Genesis", "chapters": [{"chapter": 1, "verses": [
            {"verse": i, "text": f"v{i}"} for i in range(1, 30)]}]}]
        path.write_text(json.dumps(big), encoding="utf-8")
        assert dialog.import_path(path, lang="fr", shortname="Maison")
        assert changed
        with db.connect() as conn:
            installed = bc.installed_translations(conn)
        assert any(i["shortname"] == "Maison" for i in installed.values())
        assert dialog._buttons["KJV"].text() in ("Télécharger", "Installée")
    finally:
        dialog.close()


def test_translation_books_are_listed_with_their_names(db) -> None:
    from app.database.dao_bible import BibleDao

    with db.connect() as conn:
        conn.execute("INSERT INTO bible_translation (id, module, name, shortname, lang) "
                     "VALUES (90, 'TEST', 'Test', 'TST', 'fr')")
        conn.executemany(
            "INSERT INTO bible_translation_verse (translation_id, book, book_name, chapter, verse, text) "
            "VALUES (90, ?, ?, ?, ?, 'x')",
            [(1, "Genèse", 1, 1), (1, "Genèse", 1, 2), (2, "Exode", 1, 1), (40, None, 1, 1)],
        )
        conn.commit()
    assert BibleDao(db).list_translation_books(90) == [
        {"id": 1, "name": "Genèse"}, {"id": 2, "name": "Exode"}, {"id": 40, "name": "40"},
    ]
