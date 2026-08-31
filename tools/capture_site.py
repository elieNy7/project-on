"""Captures réelles de Project-On pour le site (rendu Qt exact, données réelles).

Usage :
    python tools/capture_site.py            # thème sombre (par défaut)
    python tools/capture_site.py --light    # thème clair

Génère/rafraîchit les fichiers référencés par docs/index.html dans
screenshots/. Les fichiers runtime (settings.json, slide.json, config.json)
sont sauvegardés puis restaurés.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Plateforme native (polices réelles) — les widgets restent cachés :
# grab() force le rendu sans montrer les fenêtres.

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LIGHT = "--light" in sys.argv

from PyQt6.QtWidgets import QApplication  # noqa: E402

from app.database.connection import Database  # noqa: E402
from app.utils.app_paths import settings_path  # noqa: E402
from app.utils.slide_writer import SlideWriter  # noqa: E402

SHOTS = ROOT / "screenshots"
SHOTS.mkdir(exist_ok=True)


def drain(seconds: float = 1.2) -> None:
    """Laisse les workers asynchrones se terminer (event loop manuelle)."""
    deadline = time.time() + seconds
    app = QApplication.instance()
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def grab(widget, name: str) -> None:
    pixmap = widget.grab()
    target = SHOTS / name
    pixmap.save(str(target))
    print(f"[OK] {name} ({pixmap.width()}x{pixmap.height()})")


def main() -> None:
    settings_file = settings_path()
    original_settings = settings_file.read_text(encoding="utf-8")
    original_slide = (ROOT / "presentation" / "slide.json").read_text(
        encoding="utf-8"
    )
    try:
        if LIGHT:
            payload = json.loads(original_settings)
            payload.setdefault("appearance", {})["theme"] = "light"
            settings_file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        app = QApplication.instance() or QApplication([])

        from app.ui.main_window import MainWindow

        win = MainWindow(db=Database.default())
        win.resize(1680, 1000)
        app.processEvents()

        # ── Onglets de la bibliothèque (vraies données de la base) ────────
        tabs = [
            (0, "01-app-main.png"),          # Bible
            (1, "06-app-hymns.png"),         # Cantiques
            (2, "07-app-sermons.png"),       # Prédications
            (3, "08-app-expose.png"),        # Exposés
            (4, "09-app-playlists.png"),     # Playlists
        ]
        if LIGHT:
            # Passe claire : une seule capture (sans écraser le thème sombre).
            win.library_panel.sidebar.setCurrentIndex(0)
            drain(1.6)
            grab(win, "app-light.png")
        else:
            # Playlists de démonstration (supprimées après la capture).
            from app.database.dao_playlist import PlaylistDao

            dao = PlaylistDao(win._project_controller.db)
            demo_ids: list[int] = []
            if not dao.list_folders():
                f1 = dao.create_folder("Culte du dimanche")
                dao.add_item(
                    "custom",
                    "Jean 3:16",
                    "Car Dieu a tant aimé le monde qu'il a donné son Fils "
                    "unique, afin que quiconque croit en lui ne périsse point.",
                    folder_id=f1,
                )
                dao.add_item(
                    "custom",
                    "Psaume 23:1",
                    "L'Éternel est mon berger : je ne manquerai de rien.",
                    folder_id=f1,
                )
                dao.add_item(
                    "custom",
                    "Chœur",
                    "Jésus, Roi des rois, nous t'adorons, remplis nos cœurs "
                    "de ta joie !",
                    folder_id=f1,
                )
                dao.add_item(
                    "custom",
                    "Annonce",
                    "Repas d'amour partagé après le culte — venez nombreux !",
                    folder_id=f1,
                )
                f2 = dao.create_folder("Louange")
                dao.add_item(
                    "custom",
                    "CV-12 - Grande est ta fidélité (V. 1)",
                    "Grande est ta fidélité, ô Dieu mon Père…",
                    folder_id=f2,
                )
                dao.add_item(
                    "custom",
                    "CV-12 - Grande est ta fidélité (C)",
                    "Grande est ta fidélité ! Matin par matin, nouvelles mercis…",
                    folder_id=f2,
                )
                demo_ids = [f1, f2]

            for index, name in tabs:
                win.library_panel.sidebar.setCurrentIndex(index)
                drain(2.2 if index in (1, 2, 3) else 1.2)
                if index == 4 and demo_ids:
                    win._library_controller.refresh_playlists()
                    drain(1.5)
                grab(win, name)

            # Retrait des playlists de démonstration.
            for fid in demo_ids:
                dao.delete_folder(fid)

        if LIGHT:
            win.close()
            app.processEvents()
            from PyQt6.QtCore import QThreadPool

            QThreadPool.globalInstance().waitForDone(5000)
            return

        # ── Dialogues de réglages ─────────────────────────────────────────
        from app.ui.obs_settings_dialog import ObsSettingsDialog
        from app.ui.settings_dialog import ProjectionSettingsDialog

        dlg = ProjectionSettingsDialog(win._settings.projection, parent=win)
        dlg.resize(dlg.size().expandedTo(win.size() * 0.62))
        drain(0.4)
        grab(dlg, "02-projection-settings.png")
        dlg.close()

        obs_dlg = ObsSettingsDialog(win._settings.obs, parent=win)
        obs_dlg.resize(obs_dlg.size().expandedTo(win.size() * 0.62))
        drain(0.4)
        grab(obs_dlg, "03-obs-settings.png")
        obs_dlg.close()

        # ── Fenêtre de projection (rendu réel, 1080p) ─────────────────────
        from app.ui.projection_window import ProjectionWindow

        presentation_dir = win._presentation_dir
        cfg = win._settings.projection.to_presentation_config()

        writer = SlideWriter(presentation_dir=presentation_dir)
        writer.write(
            type(
                "S",
                (),
                {
                    "source": "bible",
                    "reference": "Jean 3:16",
                    "text": (
                        "Car Dieu a tant aimé le monde qu'il a donné son Fils "
                        "unique, afin que quiconque croit en lui ne périsse "
                        "point, mais qu'il ait la vie éternelle."
                    ),
                    "background": "",
                    "image_path": "",
                },
            )()
        )

        proj = ProjectionWindow(presentation_dir)
        proj.resize(1920, 1080)
        proj._apply_config(cfg)
        proj._apply_slide(
            json.loads((presentation_dir / "slide.json").read_text(encoding="utf-8"))
        )
        drain(0.8)
        grab(proj, "projection-1080.png")

        # Variante bandeau bas (mode OBS lower third)
        cfg_lower = dict(cfg)
        cfg_lower["layout_mode"] = "lower_third"
        proj._apply_config(cfg_lower)
        drain(0.5)
        grab(proj, "obs-lower_third.png")

        proj.close()
        win.close()
        app.processEvents()

        from PyQt6.QtCore import QThreadPool

        QThreadPool.globalInstance().waitForDone(5000)
    finally:
        settings_file.write_text(original_settings, encoding="utf-8")
        (ROOT / "presentation" / "slide.json").write_text(
            original_slide, encoding="utf-8"
        )


if __name__ == "__main__":
    main()
