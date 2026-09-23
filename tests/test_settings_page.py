"""Unified settings page: one page, sections instead of dialogs, and every
change applied immediately (no Apply / Cancel)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from app.database.connection import Database, DatabaseConfig
from app.utils.app_paths import settings_path

SECTIONS = ("projection", "themes", "hdmi", "obs", "obs_output", "appearance")


@pytest.fixture
def window(tmp_path: Path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    from app.ui.main_window import MainWindow

    monkeypatch.setattr(MainWindow, "_start_obs_output", lambda self: None)
    monkeypatch.setattr(MainWindow, "_poll_obs_status", lambda self: None)
    db = Database(DatabaseConfig(db_path=tmp_path / "main.db"))
    db.initialize()
    win = MainWindow(db=db)
    win.show()
    app.processEvents()
    yield win
    win.close()
    win.deleteLater()


def _page(win):
    return win.library_panel.settings_page


@pytest.mark.parametrize("key", SECTIONS)
def test_each_section_opens_inside_the_page(window, key) -> None:
    window._show_settings_section(key)
    page = _page(window)
    assert window.rail.currentIndex() == window._SETTINGS_TAB
    assert page.current_key() == key
    section = page.current_widget()
    assert section is not None and section.isVisible()
    assert not section.isWindow()  # hosted, not a separate window
    labels = {b.text() for b in section.findChildren(QPushButton) if b.isVisible()}
    assert not labels & {"Annuler", "Enregistrer", "Appliquer"}  # immediate apply


def test_projection_change_is_applied_and_saved_without_a_button(window) -> None:
    window._show_settings_section("projection")
    dlg = _page(window).current_widget()
    changed = dlg.read_settings()
    changed.text_size = changed.text_size + 7

    dlg.settingsChanged.emit(changed)

    assert window._settings.projection.text_size == changed.text_size
    presentation_cfg = json.loads((window._presentation_dir / "config.json").read_text(encoding="utf-8"))
    assert "themes" in presentation_cfg  # full config, theme registry included
    window._flush_settings_save()
    saved = json.loads(settings_path().read_text(encoding="utf-8"))
    assert saved["projection"]["text_size"] == changed.text_size


def test_escape_and_enter_never_hide_a_section(window) -> None:
    window._show_settings_section("projection")
    section = _page(window).current_widget()
    for key in (Qt.Key.Key_Escape, Qt.Key.Key_Return):
        QTest.keyClick(section, key)
    assert section.isVisible()


def test_obs_port_applies_once_typing_pauses(window, monkeypatch) -> None:
    applied = []
    monkeypatch.setattr(window._obs, "update_settings", lambda s: applied.append(s.web_port))
    window._show_settings_section("obs")
    dlg = _page(window).current_widget()

    dlg._port_spin.setValue(8095)
    assert applied == []  # nothing restarts mid-typing
    dlg._change_watch.timeout.emit()

    assert applied == [8095]
    assert window._settings.obs.web_port == 8095


def test_appearance_change_is_saved_and_explained(window) -> None:
    window._show_settings_section("appearance")
    dlg = _page(window).current_widget()
    target = "light" if window._settings.appearance.theme == "dark" else "dark"

    dlg._select_theme(target)

    assert window._settings.appearance.theme == target
    assert _page(window).info_bar.isVisible()  # restart notice, non-blocking


def test_output_chip_opens_the_matching_section(window) -> None:
    window.command_bar.outputClicked.emit("hdmi")
    assert _page(window).current_key() == "hdmi"


# ── OBS lower-third screen (single Fluent column) ─────────────────────────


@pytest.fixture
def obs_screen():
    QApplication.instance() or QApplication([])
    from app.ui.obs_output_settings_dialog import ObsOutputSettingsDialog
    from app.utils.settings import ObsSettings

    screen = ObsOutputSettingsDialog(ObsSettings(), embedded=True)
    yield screen
    screen.deleteLater()


def test_obs_checkboxes_become_wrapping_setting_cards(obs_screen) -> None:
    from PySide6.QtWidgets import QCheckBox

    from app.ui.obs_output_settings_dialog import SettingRow

    boxes = obs_screen.findChildren(QCheckBox)
    assert boxes and all(not b.text() for b in boxes)  # labels moved to cards
    assert all(b.accessibleName() for b in boxes)  # still named for screen readers

    card = next(r for r in obs_screen.findChildren(SettingRow) if r._toggle is obs_screen._show_ref)
    before = obs_screen._show_ref.isChecked()
    QTest.mouseClick(card, Qt.MouseButton.LeftButton)
    assert obs_screen._show_ref.isChecked() is not before


def test_obs_pages_are_sized_to_the_visible_tab(obs_screen) -> None:
    heights = set()
    for index in range(4):
        obs_screen._on_nav_clicked(index)
        heights.add(obs_screen._stack.minimumSizeHint().height())
    assert len(heights) > 1  # a short tab leaves no blank space


def test_obs_preset_still_applies(obs_screen) -> None:
    emitted = []
    obs_screen.obsSettingsChanged.connect(emitted.append)
    obs_screen._apply_preset({"layout_mode": "fullscreen", "text_size": 61})
    obs_screen._change_timer.timeout.emit()
    assert emitted and emitted[-1].output.layout_mode == "fullscreen"


# ── Projection screen ─────────────────────────────────────────────────────


def test_projection_screen_modes() -> None:
    QApplication.instance() or QApplication([])
    from PySide6.QtWidgets import QComboBox, QScrollArea

    from app.ui.settings_dialog import ProjectionSettingsDialog
    from app.utils.settings import ProjectionSettings

    page = ProjectionSettingsDialog(ProjectionSettings(), embedded=True)
    # In the settings page: no nested scroll area, no Cancel / Save footer.
    assert not page.findChildren(QScrollArea)
    visible = {b.text() for b in page.findChildren(QPushButton) if b.isVisibleTo(page)}
    assert "Réinitialiser" in visible and not visible & {"Annuler", "Enregistrer"}
    combo = page._display_screen
    assert combo.toolTip() == combo.currentText()  # clipped choice stays readable

    # Standalone (theme style editor): scrolls and keeps Cancel / Save.
    dialog = ProjectionSettingsDialog(ProjectionSettings())
    assert dialog.findChildren(QScrollArea)
    visible = {b.text() for b in dialog.findChildren(QPushButton) if b.isVisibleTo(dialog)}
    assert {"Annuler", "Enregistrer"} <= visible
    for w in (page, dialog):
        w.deleteLater()


# ── Themes screen ─────────────────────────────────────────────────────────


def test_themes_screen_is_one_visible_column() -> None:
    QApplication.instance() or QApplication([])
    from app.ui.theme_dialog import ThemeDialog
    from app.utils.settings import AppSettings

    screen = ThemeDialog(AppSettings(), embedded=True)
    screen.resize(460, 900)
    screen.show()
    try:
        # Selected-theme card and assignments are in the single column.
        assert screen._btn_edit_style.isVisible()
        assert all(c.isVisible() for c in screen._assign_combos.values())
        assert screen._active_badge.isVisible()  # the default theme is active
        # The list is sized to its themes, not stretched over the page.
        assert screen._theme_list.height() < 200

        emitted = []
        screen.themesLiveChanged.connect(lambda *args: emitted.append(args))
        combo = next(iter(screen._assign_combos.values()))
        combo.setCurrentIndex(combo.count() - 1)
        assert emitted  # every change is broadcast for immediate apply
    finally:
        screen.close()
        screen.deleteLater()
