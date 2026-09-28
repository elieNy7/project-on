"""Déroulé du culte : sections, heures prévues, avance/retard."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.database.connection import Database, DatabaseConfig
from app.database.dao_playlist import PlaylistDao
from app.database.dao_service_plan import ServicePlanDao
from app.utils.service_plan import (
    PlanSection,
    ServiceTracker,
    describe_delay,
    parse_start_time,
)


def _t(h: int, m: int, s: int = 0) -> datetime:
    return datetime(2026, 9, 27, h, m, s)


def test_parse_start_time() -> None:
    assert parse_start_time("9:30") == (9, 30)
    assert parse_start_time("09h30") == (9, 30)
    assert parse_start_time("10") == (10, 0)
    assert parse_start_time("25:00") is None
    assert parse_start_time("") is None


def test_tracker_delay_and_overrun() -> None:
    tracker = ServiceTracker([
        PlanSection(1, "Louange", 30), PlanSection(2, "Annonces", 10, item_id=7),
        PlanSection(3, "Prédication", 45),
    ])
    start = _t(9, 30)
    tracker.start(_t(9, 32))
    status = tracker.status(_t(9, 40), start)
    assert status["name"] == "Louange"
    assert status["delay"] == 120  # commencé 2 min en retard

    # Louange déborde : le retard grandit en direct.
    status = tracker.status(_t(10, 5), start)
    assert status["delay"] == 120 + 3 * 60
    assert status["remaining"] < 0

    # Le slide lié aux annonces passe en direct : section suivante.
    assert tracker.enter_item(7, _t(10, 5)) is True
    assert tracker.enter_item(7, _t(10, 6)) is False  # déjà en cours
    status = tracker.status(_t(10, 6), start)
    assert status["name"] == "Annonces" and status["delay"] == 5 * 60
    assert status["expected_end"] == _t(11, 0)  # 10:55 prévu + 5 min

    assert tracker.next(_t(10, 5)) is True  # annonces écourtées
    status = tracker.status(_t(10, 5), start)
    assert status["name"] == "Prédication" and status["delay"] == -5 * 60
    assert describe_delay(status["delay"]) == "5:00 d'avance"
    assert tracker.next(_t(11, 0)) is False  # dernière section


def test_dao_sections_and_start_time(tmp_path: Path) -> None:
    db = Database(DatabaseConfig(db_path=tmp_path / "p.db"))
    db.initialize()
    folder = PlaylistDao(db).create_folder("Culte du dimanche")
    dao = ServicePlanDao(db)
    a = dao.add_section(folder, "Louange", 30)
    b = dao.add_section(folder, "Prédication", 45, item_id=12)
    dao.set_start_time(folder, "9:30")
    assert dao.get_start_time(folder) == "9:30"
    assert [s["name"] for s in dao.list_sections(folder)] == ["Louange", "Prédication"]
    assert dao.move_section(b, -1) is True
    assert [s["id"] for s in dao.list_sections(folder)] == [b, a]
    dao.update_section(a, "Adoration", 20, None)
    dao.delete_section(b)
    assert [(s["name"], s["duration_min"]) for s in dao.list_sections(folder)] == [("Adoration", 20)]
    # Supprimer la playlist supprime son déroulé.
    PlaylistDao(db).delete_folder(folder)
    with db.connect() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
    assert dao.get_start_time(folder) == ""


def test_panel_follows_live_items(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from app.ui.service_plan_panel import ServicePlanPanel

    db = Database(DatabaseConfig(db_path=tmp_path / "p.db"))
    db.initialize()
    folder = PlaylistDao(db).create_folder("Culte")
    item = PlaylistDao(db).add_item("bible", "Jean 3:16", "texte", folder)
    dao = ServicePlanDao(db)
    dao.add_section(folder, "Louange", 30)
    dao.add_section(folder, "Prédication", 45, item_id=item)
    dao.set_start_time(folder, "9:30")

    now = [_t(9, 30)]
    panel = ServicePlanPanel(dao, now=lambda: now[0])
    entered = []
    panel.sectionEntered.connect(entered.append)
    try:
        panel.set_folder(folder)
        assert panel.table.rowCount() == 2
        assert panel.table.item(1, 2).text() == "10:00"  # heure prévue
        now[0] = _t(10, 12)
        panel.on_item_live(item)  # le slide lié démarre la section
        assert entered == ["Prédication"]
        assert "12:00 de retard" in panel.status.text()
        assert panel.table.item(1, 3).text() == "10:12"
        panel.next_section()  # dernière section : rien ne change
        assert entered == ["Prédication"]
    finally:
        panel.close()
