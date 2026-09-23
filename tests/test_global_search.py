"""Global search: data layer, suggestion flyout and revealing a hit."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

from app.database.connection import Database, DatabaseConfig
from app.database.dao_bible import BibleDao
from app.database.dao_media import MediaDao
from app.database.dao_playlist import PlaylistDao
from app.database.dao_sermons import SermonsDao
from app.utils import global_search
from app.utils.global_search import SearchContext, SearchDeps, run_global_search

VERSES = [
    (43, "Jean", 3, 16, "Car Dieu a tant aimé le monde qu'il a donné son Fils unique"),
    (43, "Jean", 8, 12, "Je suis la lumière du monde"),
    (40, "Matthieu", 5, 14, "Vous êtes la lumière du monde"),
]


def _seed(db: Database) -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO bible_translation (id, module, name, shortname, lang)"
            " VALUES (7, 'LSG', 'Louis Segond', 'LSG', 'fr')"
        )
        conn.executemany(
            "INSERT INTO bible_translation_verse"
            " (translation_id, book, book_name, chapter, verse, text) VALUES (7, ?, ?, ?, ?, ?)",
            VERSES,
        )
        conn.execute("INSERT INTO playlist_folder (name, sort_order) VALUES ('Culte du dimanche', 1)")
        conn.commit()


@pytest.fixture
def deps(db: Database) -> SearchDeps:
    _seed(db)
    global_search._verse_index.clear()
    return SearchDeps(db, BibleDao(db), SermonsDao(db), MediaDao(db), PlaylistDao(db))


CTX = SearchContext(bible_translation_id=7)


def test_reference_query_opens_the_verse(deps) -> None:
    hits = run_global_search(deps, "jean 3:16", CTX)
    assert hits[0]["kind"] == "bible"
    assert hits[0]["title"] == "Jean 3:16"
    assert (hits[0]["book_id"], hits[0]["chapter"], hits[0]["verse"]) == (43, 3, 16)
    assert "tant aimé" in hits[0]["subtitle"]


def test_text_search_ignores_accents(deps) -> None:
    hits = [h for h in run_global_search(deps, "lumiere du monde", CTX) if h["kind"] == "bible"]
    assert [h["title"] for h in hits] == ["Matthieu 5:14", "Jean 8:12"]


def test_other_libraries_are_searched(deps) -> None:
    hits = run_global_search(deps, "dimanche", CTX)
    assert [(h["kind"], h["title"]) for h in hits] == [("playlist", "Culte du dimanche")]


def test_hymns_are_not_searched() -> None:
    assert "hymn" not in global_search.KINDS


def test_short_query_returns_nothing(deps) -> None:
    assert run_global_search(deps, "j", CTX) == []


def test_failing_source_does_not_hide_the_others(deps, monkeypatch) -> None:
    def boom(*_a, **_k):
        raise RuntimeError("source down")

    monkeypatch.setattr(deps.sermons_dao, "list_sermons", boom)
    hits = run_global_search(deps, "lumiere du monde", CTX)
    assert any(h["kind"] == "bible" for h in hits)


# ── Flyout ────────────────────────────────────────────────────────────────


@pytest.fixture
def popup():
    QApplication.instance() or QApplication([])
    from app.ui.global_search_popup import GlobalSearchPopup

    host = QWidget()
    host.resize(900, 600)
    field = QLineEdit(host)
    widget = GlobalSearchPopup(host)
    widget.attach(field)
    host.show()
    yield widget, field
    host.deleteLater()


def test_groups_follow_library_order_whatever_the_arrival(popup) -> None:
    widget, _field = popup
    widget.begin()
    widget.add_group("playlist", [{"kind": "playlist", "title": "P"}])
    widget.add_group("bible", [{"kind": "bible", "title": "B"}])
    rows = [widget._list.item(i) for i in range(widget._list.count())]
    labels = [r.data(Qt.ItemDataRole.UserRole + 1) or r.data(Qt.ItemDataRole.UserRole)["title"] for r in rows]
    assert labels == ["Bible", "B", "Playlists", "P"]
    assert widget.current_hit()["title"] == "B"  # first hit, never a header


def test_arrows_skip_headers_and_enter_activates(popup) -> None:
    widget, field = popup
    widget.begin()
    widget.add_group("bible", [{"kind": "bible", "title": "B1"}])
    widget.add_group("sermon", [{"kind": "sermon", "title": "H1"}])
    opened = []
    widget.hitActivated.connect(opened.append)

    down = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    assert widget.eventFilter(field, down) is True
    assert widget.current_hit()["title"] == "H1"

    enter = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    widget.eventFilter(field, enter)
    assert [h["title"] for h in opened] == ["H1"]
    assert not widget.isVisible()


def test_escape_in_the_field_never_reaches_live_shortcuts(popup) -> None:
    widget, field = popup
    override = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    override.ignore()
    widget.eventFilter(field, override)
    assert override.isAccepted()


def test_late_groups_do_not_reopen_a_dismissed_flyout(popup) -> None:
    widget, _field = popup
    widget.begin()
    widget.add_group("bible", [{"kind": "bible", "title": "B1"}])
    widget._activate_current()  # the operator opened a hit
    widget.add_group("expose", [{"kind": "expose", "title": "late"}])
    assert not widget.isVisible()


def test_empty_result_message(popup) -> None:
    widget, _field = popup
    widget.begin()
    for kind in global_search.KINDS:
        widget.add_group(kind, [])
    assert widget._status.text() == "Aucun résultat"


# ── Reveal in the real window ─────────────────────────────────────────────


def test_bible_hit_is_revealed_without_projecting(tmp_path: Path, monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    from app.ui.main_window import MainWindow

    db = Database(DatabaseConfig(db_path=tmp_path / "main.db"))
    db.initialize()
    _seed(db)
    monkeypatch.setattr(MainWindow, "_start_obs_output", lambda self: None)
    monkeypatch.setattr(MainWindow, "_poll_obs_status", lambda self: None)
    window = MainWindow(db=db)
    try:
        projected = []
        window._project_controller.programChanged.connect(projected.append)
        window.rail.setCurrentIndex(4)

        window._open_search_hit(
            {"kind": "bible", "title": "Jean 8:12", "book_id": 43, "chapter": 8, "verse": 12}
        )

        assert window.rail.currentIndex() == 0
        bible = window.library_panel.bible_tab
        assert bible.books_list.currentItem().data(256) == 43
        assert bible.verses_list.currentItem().data(258) == 12
        assert projected == []  # revealing never goes live
    finally:
        window.close()
        window.deleteLater()
