"""Capture real screenshots of the Project-On UI (offscreen) for the website.

Boots the actual Qt widgets — main window, settings dialogs and the fullscreen
projection — with the bundled database, then grabs each to PNG.

Run:  py -3 tools/capture_screenshots.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication

OUT = ROOT / "screenshots"
OUT.mkdir(exist_ok=True)


def _pump(app, n=8):
    for _ in range(n):
        app.processEvents()


def _grab(widget, name, size=None):
    if size is not None:
        widget.resize(*size)
    widget.show()
    QApplication.instance().processEvents()
    QApplication.instance().processEvents()
    pix = widget.grab()
    path = OUT / name
    pix.save(str(path), "PNG")
    print(f"  saved {name}  ({pix.width()}x{pix.height()})")
    return path


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        __import__("PyQt6.QtCore", fromlist=["Qt"]).Qt
        .HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication([])

    from app.ui.theme import build_app_stylesheet, set_theme
    from app.utils.translations import set_language
    from app.utils.font_loader import load_fonts
    from app.utils.app_paths import (
        data_dir,
        ensure_data_initialized,
        seed_default_backgrounds,
        settings_path,
        backgrounds_dir,
    )
    from app.utils.settings import AppSettings, ProjectionSettings, ObsOutputSettings

    set_theme("dark")
    set_language("fr")
    load_fonts()
    app.setStyleSheet(build_app_stylesheet())
    data_dir().mkdir(parents=True, exist_ok=True)
    ensure_data_initialized()
    seed_default_backgrounds()

    from app.database.connection import Database

    db = Database.default()
    db.initialize()

    # 1) Main window with a populated preview
    from app.ui.main_window import MainWindow

    win = MainWindow(db=db)
    win.resize(1720, 1040)
    _pump(app, 12)
    try:
        win.preview_panel.set_slide(
            "Jean 3.16 — Louis Segond",
            "Car Dieu a tant aimé le monde qu'il a donné son Fils unique, "
            "afin que quiconque croit en lui ne périsse point, mais qu'il ait "
            "la vie éternelle.",
        )
    except Exception as exc:  # pragma: no cover - best effort
        print("preview fill skipped:", exc)
    _pump(app, 12)
    _grab(win, "01-app-main.png")

    # 2) Projection settings dialog (shows the new Transitions & Effects section)
    from app.ui.settings_dialog import ProjectionSettingsDialog

    dlg = ProjectionSettingsDialog(ProjectionSettings())
    dlg.resize(900, 760)
    _pump(app, 6)
    _grab(dlg, "02-projection-settings.png")
    # scroll to the Transitions section for a second shot
    try:
        from PyQt6.QtWidgets import QScrollArea

        area = dlg.findChild(QScrollArea)
        if area is not None:
            bar = area.verticalScrollBar()
            bar.setValue(bar.maximum())
            _pump(app, 4)
            _grab(dlg, "02b-transitions.png")
    except Exception as exc:
        print("scroll skipped:", exc)
    dlg.close()

    # 3) OBS lower-third settings dialog
    from app.ui.obs_output_settings_dialog import ObsOutputSettingsDialog

    obs_dlg = ObsOutputSettingsDialog(ObsOutputSettings())
    obs_dlg.resize(960, 720)
    _pump(app, 6)
    _grab(obs_dlg, "03-obs-settings.png")
    obs_dlg.close()

    # 4) Fullscreen projection — Bible verse over a Christian background
    from app.ui.projection_window import ProjectionWindow

    bg_dir = backgrounds_dir()

    def _bg(name: str) -> str:
        p = bg_dir / name
        return str(p) if p.is_file() else ""

    shots = [
        (
            "04-projection-bible.png",
            {"source": "bible", "bg": "bg-symbole-croix_16x9.png"},
            {
                "text": "L'Éternel est mon berger : je ne manquerai de rien.",
                "reference": "Psaume 23.1",
                "source": "bible",
            },
        ),
        (
            "05-projection-hymn.png",
            {"source": "hymn", "bg": "bg-symbole-aigle_16x9.png"},
            {
                "text": "Quel ami fidèle et tendre\nNous avons en Jésus-Christ",
                "reference": "Cantique 142",
                "source": "hymn",
            },
        ),
    ]
    for fname, meta, slide in shots:
        pw = ProjectionWindow(ROOT / "presentation")
        cfg = ProjectionSettings(
            bg_mode="image" if _bg(meta["bg"]) else "color",
            bg_image=_bg(meta["bg"]),
            position="center",
        ).to_presentation_config()
        pw._apply_config(cfg)
        pw._current_slide = {}
        pw._render_slide_content(slide)
        _pump(app, 8)
        _grab(pw, fname, size=(1600, 900))
        pw.close()

    print(f"\nScreenshots written to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
