"""Position de la référence (haut/bas) et suivi du paragraphe d'Exposé projeté."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.utils.settings import AppSettings
from app.utils.project_on_controller import ProjectOnController


def _make_controller(tmp_path: Path) -> ProjectOnController:
    from app.database.connection import Database, DatabaseConfig

    db = Database(DatabaseConfig(db_path=tmp_path / "test.db"))
    db.initialize()
    return ProjectOnController(db=db, presentation_dir=tmp_path / "pres")


# ── entry_index_for_row ──────────────────────────────────────────────────────

def test_entry_index_maps_split_slides_back_to_entries(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    long_text = " ".join(f"phrase numéro {i} du texte long." for i in range(40))
    controller.load_program(
        "sermon",
        "Chapitre test",
        [("R1", "court"), ("R2", long_text), ("R3", "court aussi")],
        focus_entry=0,
    )

    # Slide 0 → entrée 0 ; les slides découpées du texte long → entrée 1 ;
    # la dernière slide → entrée 2.
    assert controller.entry_index_for_row(0) == 0
    assert controller.entry_index_for_row(1) == 1
    assert controller.entry_index_for_row(controller.program_count - 1) == 2
    assert controller.entry_index_for_row(-1) is None
    assert controller.entry_index_for_row(controller.program_count) is None


def test_entry_index_none_for_empty_program(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    assert controller.entry_index_for_row(0) is None


# ── PreviewPanel : position de la référence ──────────────────────────────────

def _make_preview_panel():
    from PyQt6.QtWidgets import QApplication

    from app.ui.preview_panel import PreviewPanel

    app = QApplication.instance() or QApplication([])
    panel = PreviewPanel(settings=AppSettings())
    panel.resize(800, 600)
    return app, panel


def test_preview_ref_label_moves_between_top_and_bottom() -> None:
    _app, panel = _make_preview_panel()

    panel.set_reference_position(False)
    lay = panel._slide_frame.layout()
    below_text = lay.indexOf(panel._ref_label) > lay.indexOf(panel.slide_view)
    assert below_text

    panel.set_reference_position(True)
    above_text = lay.indexOf(panel._ref_label) < lay.indexOf(panel.slide_view)
    assert above_text


def test_preview_ref_position_button_follows_settings() -> None:
    _app, panel = _make_preview_panel()
    assert panel._ref_pos_button.isChecked() is False  # défaut : en bas

    settings = AppSettings()
    settings.projection.reference_position = "top"
    panel.set_settings(settings)
    assert panel._ref_pos_button.isChecked() is True


def test_preview_ref_toggle_emits_signal() -> None:
    _app, panel = _make_preview_panel()
    received: list[bool] = []
    panel.referencePositionToggled.connect(received.append)
    panel._ref_pos_button.setChecked(True)
    panel._on_ref_pos_clicked(True)
    assert received == [True]


# ── ExposeTab : suivi du paragraphe projeté ──────────────────────────────────

def _make_expose_tab():
    from PyQt6.QtWidgets import QApplication

    from app.ui.expose_tab import ExposeTab

    app = QApplication.instance() or QApplication([])
    return app, ExposeTab()


def test_expose_highlight_live_entry_selects_row_without_preview_change() -> None:
    _app, tab = _make_expose_tab()
    rows = [
        {"ref": "10-1", "text": "Premier paragraphe"},
        {"ref": "10-2", "text": "Deuxième paragraphe"},
        {"ref": "11-1", "text": "Troisième paragraphe"},
    ]
    tab.set_paragraphs(rows)
    assert tab.paragraphs_list.currentRow() == 0

    tab.highlight_live_entry(2)
    assert tab.paragraphs_list.currentRow() == 2
    # Le suivi ne doit pas réécrire l'aperçu de l'opérateur.
    tab.highlight_live_entry(None)
    assert tab.paragraphs_list.currentRow() == 2
    tab.highlight_live_entry(99)
    assert tab.paragraphs_list.currentRow() == 2


def test_expose_solo_signal_payload() -> None:
    _app, tab = _make_expose_tab()
    received: list[tuple[str, str, str]] = []
    tab.paragraphSoloRequested.connect(lambda r, t, ti: received.append((r, t, ti)))
    tab._current_chapter_title = "L'Église de Philadelphie"
    item = None
    tab.set_paragraphs([{"ref": "40-2", "text": "Corps du paragraphe"}])
    item = tab.paragraphs_list.item(0)
    tab._emit_solo(item)
    assert received == [("40-2", "Corps du paragraphe", "L'Église de Philadelphie")]


def test_expose_highlight_updates_current_page(tmp_path: Path) -> None:
    _app, tab = _make_expose_tab()
    tab.set_paragraphs(
        [{"ref": "45-3", "text": "Paragraphe de la page 45"}]
    )
    tab.set_pages([40, 41, 45])
    tab.highlight_live_entry(0)
    assert tab._current_page == 45
