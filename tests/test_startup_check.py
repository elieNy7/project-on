"""Contrôle avant culte automatique au démarrage."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.utils.settings import AppSettings
from app.utils.system_health import HealthCheck, HealthReport


def _window(tmp_path: Path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from app.database.connection import Database, DatabaseConfig
    from app.ui.main_window import MainWindow

    monkeypatch.setattr(MainWindow, "_start_obs_output", lambda self: None)
    monkeypatch.setattr(MainWindow, "_poll_obs_status", lambda self: None)
    db = Database(DatabaseConfig(db_path=tmp_path / "m.db"))
    db.initialize()
    return MainWindow(db=db)


def test_setting_default_and_round_trip(tmp_path: Path) -> None:
    assert AppSettings().appearance.startup_check is True
    path = tmp_path / "s.json"
    settings = AppSettings()
    settings.appearance.startup_check = False
    settings.save(path)
    assert AppSettings.load(path).appearance.startup_check is False


def test_only_problems_are_reported(tmp_path: Path, monkeypatch) -> None:
    window = _window(tmp_path, monkeypatch)
    try:
        ok = HealthReport((HealthCheck("db", "Base", "success", "OK"),), datetime.now())
        window._on_startup_check_done(ok)
        assert getattr(window, "_startup_check_box", None) is None

        bad = HealthReport(
            (HealthCheck("screens", "Écrans détectés", "warning", "Un seul écran"),),
            datetime.now(),
        )
        window._on_startup_check_done(bad)
        box = window._startup_check_box
        assert "Un seul écran" in box.text() and not box.isModal()
        box.close()
        assert window._preflight_kwargs()["screen_count"] >= 0
    finally:
        window.close()
