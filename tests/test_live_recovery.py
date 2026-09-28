"""Reprise après coupure de courant."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.database.connection import Database, DatabaseConfig
from app.utils import live_recovery
from app.utils.project_on_controller import ProjectOnController


def _controller(tmp_path: Path) -> ProjectOnController:
    db = Database(DatabaseConfig(db_path=tmp_path / "r.db"))
    db.initialize()
    return ProjectOnController(db=db, presentation_dir=tmp_path / "pres")


def test_snapshot_save_load_restore(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    assert live_recovery.snapshot(controller) is None  # rien en direct

    controller.load_program(
        "bible", "Jean 3", [("Jean 3:16", "Car Dieu a tant aimé"), ("Jean 3:17", "Dieu n'a pas envoyé")],
        focus_entry=1,
    )
    data = live_recovery.snapshot(controller, hidden=True)
    path = tmp_path / "data" / "live-recovery.json"
    live_recovery.save(path, data)
    assert path.exists()

    loaded = live_recovery.load(path)
    assert loaded["title"] == "Jean 3" and loaded["hidden"] is True
    assert loaded["slides"][1].reference == "Jean 3:17"

    fresh = _controller(tmp_path / "second")
    assert live_recovery.restore(fresh, loaded) == 1
    assert fresh.program_title == "Jean 3"
    assert fresh.current_slide().reference == "Jean 3:17"
    written = json.loads((tmp_path / "second" / "pres" / "slide.json").read_text("utf-8"))
    assert written["reference"] == "Jean 3:17"

    live_recovery.clear(path)
    assert live_recovery.load(path) is None


def test_old_or_broken_files_are_ignored(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    controller.load_program("custom", "Annonce", [("Annonce", "Bienvenue")])
    path = tmp_path / "live-recovery.json"
    live_recovery.save(path, live_recovery.snapshot(controller))
    later = datetime.now() + timedelta(hours=13)
    assert live_recovery.load(path, now=later) is None  # culte d'hier : pas de reprise
    path.write_text("{ tronqué", encoding="utf-8")
    assert live_recovery.load(path) is None


def test_main_window_offers_and_restores(tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QApplication, QMessageBox

    QApplication.instance() or QApplication([])
    from app.ui.main_window import MainWindow
    from app.utils.app_paths import data_dir

    previous = _controller(tmp_path / "before")
    previous.load_program("hymn", "Cantique 12", [("12 - Strophe 1", "À toi la gloire\nÔ Ressuscité")])
    live_recovery.save(data_dir() / "live-recovery.json", live_recovery.snapshot(previous))

    monkeypatch.setattr(MainWindow, "_start_obs_output", lambda self: None)
    monkeypatch.setattr(MainWindow, "_poll_obs_status", lambda self: None)
    asked = []
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **k: (asked.append(a[2]), QMessageBox.StandardButton.Yes)[1],
    )
    db = Database(DatabaseConfig(db_path=tmp_path / "main.db"))
    db.initialize()
    window = MainWindow(db=db)
    try:
        assert window._pending_recovery is not None
        window._offer_recovery()
        assert asked and "Cantique 12" in asked[0]
        assert window._project_controller.program_title == "Cantique 12"
        window._save_recovery()
        assert (data_dir() / "live-recovery.json").exists()
    finally:
        window.close()
    assert not (data_dir() / "live-recovery.json").exists()  # fermeture normale
