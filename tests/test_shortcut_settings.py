"""Raccourcis configurables (télécommande, Stream Deck)."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.utils.settings import AppSettings
from app.utils.shortcuts import ACTIONS, ShortcutSettings


def test_defaults_and_overrides(tmp_path: Path) -> None:
    settings = ShortcutSettings()
    assert settings.key_for("take") == "F2"
    assert settings.key_for("next_slide") == "PgDown"
    assert settings.conflicts() == {}

    custom = ShortcutSettings(keys={"take": "Ctrl+Alt+F1", "hide": "", "inconnu": "X"}).sanitized()
    assert custom.keys == {"take": "Ctrl+Alt+F1", "hide": ""}
    assert custom.key_for("hide") == ""  # désactivé

    path = tmp_path / "settings.json"
    app = AppSettings()
    app.shortcuts = custom
    app.save(path)
    assert AppSettings.load(path).shortcuts.keys == custom.keys


def test_conflicts_detect_duplicates_and_reserved() -> None:
    settings = ShortcutSettings(keys={"hide": "F2", "search": "Ctrl+1"})
    conflicts = settings.conflicts()
    assert sorted(conflicts["f2"]) == ["hide", "take"]
    assert conflicts["ctrl+1"] == ["search"]


def test_dialog_reads_back_and_resets() -> None:
    from PySide6.QtGui import QKeySequence
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from app.ui.shortcut_settings_dialog import ShortcutSettingsDialog

    dialog = ShortcutSettingsDialog(ShortcutSettings(keys={"take": "F9"}))
    emitted = []
    dialog.shortcutsChanged.connect(emitted.append)
    try:
        assert dialog.read_settings().key_for("take") == "F9"
        dialog._edits["hide"].setKeySequence(QKeySequence("F9"))
        dialog._on_change()
        assert "F9" in dialog._warning.text() or "f9" in dialog._warning.text().lower()
        dialog._reset_defaults()
        assert emitted[-1].keys == {}
        assert len(dialog._edits) == len(ACTIONS)
    finally:
        dialog.close()


def test_help_dialog_shows_configured_keys() -> None:
    from PySide6.QtWidgets import QApplication, QLabel

    QApplication.instance() or QApplication([])
    from app.ui.shortcuts_dialog import ShortcutsDialog

    keys = ShortcutSettings(keys={"take": "F9"}).effective()
    dialog = ShortcutsDialog(None, keys=keys)
    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert "F9" in texts and "PgDown" in texts
    dialog.close()
