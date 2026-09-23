"""Preview ("Aperçu") / live ("Direct") workflow.

Single click prepares a programme in the preview, never live; F2 (or the
button) sends exactly the prepared programme live; double-click / Enter
still projects immediately.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from app.database.connection import Database, DatabaseConfig
from app.utils.project_on_controller import ProgramCue, ProjectOnController

# ── Controller level ──────────────────────────────────────────────────────


def test_cue_slide_is_the_first_part_of_a_split_entry(tmp_path: Path, db: Database) -> None:
    project = ProjectOnController(db, tmp_path)
    long_text = " ".join(["Parole"] * 200)
    cue = ProgramCue("sermon", "Sermon", (("A", "court"), ("B", long_text)), focus_entry=1)

    slide = project.cue_slide(cue)

    assert slide is not None and slide.reference.startswith("B (1/")
    assert project.program_count == 0  # building a preview projects nothing


def test_take_projects_the_focused_entry(tmp_path: Path, db: Database) -> None:
    project = ProjectOnController(db, tmp_path)
    cue = ProgramCue("bible", "Jean 3", (("Jean 3:1", "un"), ("Jean 3:2", "deux")), focus_entry=1)

    row = project.take(cue)

    assert row == 1
    assert project.current_slide().reference == "Jean 3:2"
    assert project.program_title == "Jean 3"


# ── Real window ───────────────────────────────────────────────────────────


@pytest.fixture
def window(tmp_path: Path, monkeypatch):
    QApplication.instance() or QApplication([])
    from app.ui.main_window import MainWindow

    db = Database(DatabaseConfig(db_path=tmp_path / "main.db"))
    db.initialize()  # imports the bundled Bible translations
    monkeypatch.setattr(MainWindow, "_start_obs_output", lambda self: None)
    monkeypatch.setattr(MainWindow, "_poll_obs_status", lambda self: None)
    win = MainWindow(db=db)
    yield win
    win.close()
    win.deleteLater()


def _verse_item(win, verse: int):
    lst = win.library_panel.bible_tab.verses_list
    for row in range(lst.count()):
        if lst.item(row).data(258) == verse:
            return lst.item(row)
    raise AssertionError(f"verse {verse} not listed")


def _open_chapter(win, chapter: int) -> None:
    win.library_panel.bible_tab.select_book(43)
    win._library_controller.on_bible_chapter_selected(chapter)


def test_single_click_prepares_without_going_live(window) -> None:
    _open_chapter(window, 3)
    project = window._project_controller
    live_before = project.current_slide()

    window.library_panel.bible_tab.verses_list.itemClicked.emit(_verse_item(window, 16))

    cue = window.cue_monitor.cue()
    assert cue is not None and cue.entries[cue.focus_entry][0].endswith("3:16")
    assert project.current_slide() == live_before  # nothing reached the outputs
    assert window.cue_monitor._take_button.isEnabled()


def test_f2_sends_exactly_what_was_prepared(window) -> None:
    _open_chapter(window, 3)
    window.library_panel.bible_tab.verses_list.itemClicked.emit(_verse_item(window, 16))

    # The operator browses elsewhere before sending: the preview must not follow.
    _open_chapter(window, 4)
    window._take_cue()

    project = window._project_controller
    assert project.current_slide().reference.endswith("3:16")
    assert project.program_title.endswith(" 3")  # chapter 3 was prepared, not 4


def test_double_click_still_projects_immediately(window) -> None:
    _open_chapter(window, 3)
    bible = window.library_panel.bible_tab
    bible.verses_list.itemActivated.emit(_verse_item(window, 5))

    assert window._project_controller.current_slide().reference.endswith("3:5")
    assert window.cue_monitor.cue() is None  # activation does not touch the preview


def test_take_with_an_empty_preview_does_nothing(window) -> None:
    before = window._project_controller.current_slide()
    window._take_cue()
    assert window._project_controller.current_slide() == before
