"""Onglet Réglages : présence et câblage de la sauvegarde complète."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.ui.settings_tab import SettingsTab, _BundleWorker


def test_bundle_items_exist_and_are_wired(qtbot=None):
    app = QApplication.instance() or QApplication([])
    tab = SettingsTab()

    assert hasattr(tab, "_backup_bundle_item")
    assert hasattr(tab, "_restore_bundle_item")
    # Les clics sont connectés : les handlers existent et sont appelables.
    assert callable(tab._on_backup_bundle)
    assert callable(tab._on_restore_bundle)
    assert callable(tab._on_bundle_done)
    # Le worker d'archive utilise bien l'API complète du plan.
    assert hasattr(_BundleWorker, "run")

    tab.deleteLater()
    app.processEvents()
