"""Sermons : « Ajouter à la playlist » prend le paragraphe entier (alinéas)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.database.connection import Database, DatabaseConfig
from app.database.dao_playlist import PlaylistDao
from app.ui.sermons_tab import SermonsTab

PARAGRAPHS = [
    {"reference": "65-0725M - §41", "text": "Premier paragraphe.", "marker": "E-41"},
    {"reference": "65-0725M - §42", "text": "Alinéa A du 42.", "marker": "E-42"},
    {"reference": "65-0725M - §42", "text": "Alinéa B du 42.", "marker": "E-42"},
    {"reference": "65-0725M - §42", "text": "Alinéa C du 42.", "marker": "E-42"},
    {"reference": "65-0725M - §43", "text": "Paragraphe 43.", "marker": "E-43"},
]


def _tab() -> SermonsTab:
    QApplication.instance() or QApplication([])
    tab = SermonsTab()
    tab.set_paragraphs(PARAGRAPHS)
    return tab


def test_paragraph_rows_cover_every_alinea_of_the_paragraph() -> None:
    tab = _tab()
    assert tab._paragraph_rows(0) == [0]
    assert tab._paragraph_rows(1) == [1, 2, 3]
    assert tab._paragraph_rows(3) == [1, 2, 3]  # depuis le dernier alinéa
    assert tab._paragraph_rows(4) == [4]
    assert tab._paragraph_entry([1, 2, 3]) == (
        "65-0725M - §42", "Alinéa A du 42.\nAlinéa B du 42.\nAlinéa C du 42."
    )


def test_range_adds_each_touched_paragraph_once_and_whole(monkeypatch) -> None:
    from app.ui import range_dialog

    class _Range:
        def __init__(self, *_a, **_k):
            pass

        def exec(self):
            from PySide6.QtWidgets import QDialog

            return QDialog.DialogCode.Accepted

        def values(self):
            return 3, 5  # commence au milieu du §42

    monkeypatch.setattr(range_dialog, "RangeDialog", _Range)
    payload = _tab()._paragraphs_range_payload()
    assert [ref for ref, _text in payload] == ["65-0725M - §42", "65-0725M - §43"]
    assert payload[0][1].count("\n") == 2


def test_added_items_keep_their_source_type(tmp_path: Path) -> None:
    from app.utils.library_controller import LibraryController

    QApplication.instance() or QApplication([])
    db = Database(DatabaseConfig(db_path=tmp_path / "t.db"))
    db.initialize()
    dao = PlaylistDao(db=db)
    folder = dao.create_folder("Culte")

    controller = LibraryController.__new__(LibraryController)
    controller._playlist_dao = dao
    controller._current_playlist_folder_id = None
    controller._playlist_tab = None
    controller.refresh_playlists = lambda **_k: None
    controller._commit_to_playlist(folder, "", [("Jean 3:16", "Car Dieu…")], "bible")
    controller._commit_to_playlist(folder, "", [("Note", "Libre")])
    assert [it["source"] for it in dao.list_items(folder)] == ["bible", "custom"]
