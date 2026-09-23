"""Escape closes the live projection, except while the operator is typing."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.database.connection import Database, DatabaseConfig


def test_escape_in_a_field_never_closes_the_projection(tmp_path: Path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    from app.ui.main_window import MainWindow

    closed: list[bool] = []
    monkeypatch.setattr(MainWindow, "_close_projection", lambda self: closed.append(True))
    monkeypatch.setattr(MainWindow, "_start_obs_output", lambda self: None)
    monkeypatch.setattr(MainWindow, "_poll_obs_status", lambda self: None)
    db = Database(DatabaseConfig(db_path=tmp_path / "main.db"))
    db.initialize()
    window = MainWindow(db=db)
    try:
        window.show()
        window.activateWindow()
        app.processEvents()
        bible = window.library_panel.bible_tab

        for field in (bible.search, window.command_bar.search_edit):
            field.setFocus()
            app.processEvents()
            QTest.keyClick(field, Qt.Key.Key_Escape)
            app.processEvents()
        assert closed == []

        # Outside a text field, Escape still closes the projection.
        bible.verses_list.setFocus()
        app.processEvents()
        QTest.keyClick(bible.verses_list, Qt.Key.Key_Escape)
        app.processEvents()
        assert closed == [True]
    finally:
        window.close()
        window.deleteLater()
