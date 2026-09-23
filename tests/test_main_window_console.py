"""Régie complète : console réduite, fonctionnalités retirées, diaporama câblé.

Ces vérifications portent sur l'assemblage réel de :class:`MainWindow` — la
partie que les tests unitaires ne couvrent pas, et où une suppression mal
découpée laisse un signal branché sur une méthode disparue.

Une seule régie est construite par exécution (le process garde une seule
QApplication vivante) : les quatre contrôles partagent donc le même test.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QShortcut  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from app.database.connection import Database, DatabaseConfig  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.utils.settings import AppSettings  # noqa: E402


def test_main_window_console_and_slideshow_wiring(tmp_path: Path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])  # noqa: F841 - app vivante

    db = Database(DatabaseConfig(db_path=tmp_path / "main.db"))
    db.initialize()
    # Le serveur OBS et sa surveillance ne doivent pas s'inviter dans un test.
    monkeypatch.setattr(MainWindow, "_start_obs_output", lambda self: None)
    monkeypatch.setattr(MainWindow, "_poll_obs_status", lambda self: None)
    window = MainWindow(db=db)
    try:
        # ── 1. Console réduite à l'essentiel ────────────────────────────
        boutons = window.preview_panel.console_frame.findChildren(QPushButton)
        libelles = [b.text() or b.toolTip() for b in boutons]
        assert any(l.startswith("Projeter") for l in libelles)
        assert any(l.startswith("Masquer") for l in libelles)
        assert any(l.startswith("Modifier") for l in libelles)
        # Trois commandes d'essai + la position de la référence + les trois
        # commandes vidéo (masquées tant qu'aucune vidéo n'est projetée).
        assert len(boutons) == 7, libelles
        assert window.preview_panel._video_play_button.isHidden()
        assert window.preview_panel._video_loop_button.isHidden()
        assert window.preview_panel._video_stop_button.isHidden()
        for disparu in ("Scène", "Message", "Annonces"):
            assert not any(disparu in l for l in libelles), libelles

        # ── 2. Fonctionnalités retirées ─────────────────────────────────
        for attribut in ("_stage_window", "_announcements", "_ticker"):
            assert not hasattr(window, attribut), attribut
        for methode in (
            "_update_stage",
            "_toggle_stage",
            "_send_stage_message",
            "_toggle_announcements",
            "_open_ticker_settings",
        ):
            assert not hasattr(window, methode), methode
        for attribut_panneau in (
            "_stage_button",
            "_stage_message_button",
            "_announce_button",
        ):
            assert not hasattr(window.preview_panel, attribut_panneau)

        reglages = AppSettings()
        assert not hasattr(reglages, "stage")
        assert not hasattr(reglages, "ticker")
        assert not hasattr(reglages.hdmi, "show_ticker")

        # ── 3. Le diaporama reste câblé de bout en bout ─────────────────
        photo = tmp_path / "photo.png"
        Image.new("RGB", (16, 12), (200, 40, 40)).save(photo)
        window._start_slideshow([{"name": "Photo", "path": str(photo)}])
        assert window._slideshow.is_active
        assert window._project_controller.current_slide().image_path == str(photo)
        window._slideshow.stop()
        assert not window._slideshow.is_active

        # ── 4. Une activation manuelle prend le live ────────────────────
        window._start_slideshow([{"name": "Photo", "path": str(photo)}])
        assert window._slideshow.is_active
        window._project_controller.load_program(
            "custom", "Culte", [("Jean 3:16", "Car Dieu…")]
        )
        assert not window._slideshow.is_active
        assert window._project_controller.program_title == "Culte"

        # ── 5. Sortie HDMI : fermée au démarrage, quittée par Échap ─────
        assert window._mixer_window is None, "la sortie HDMI s'ouvre au démarrage"
        window._settings.hdmi.enabled = True
        app.processEvents()
        assert window._mixer_window is None, "la sortie HDMI s'ouvre au démarrage"

        window._open_mixer_window()
        mixer = window._mixer_window
        assert mixer is not None
        touches = [
            shortcut.key().toString() for shortcut in mixer.findChildren(QShortcut)
        ]
        assert "Esc" in touches, touches
        for shortcut in mixer.findChildren(QShortcut):
            if shortcut.key() == Qt.Key.Key_Escape:
                shortcut.activated.emit()  # l'opérateur quitte le mode HDMI
        app.processEvents()
        assert window._mixer_window is None, "la fenêtre HDMI reste ouverte"
        assert window._settings.hdmi.enabled is False, "le réglage HDMI reste actif"
    finally:
        window.close()
