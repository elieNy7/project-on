"""Fond vidéo en boucle derrière le texte (projection locale)."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from app.utils.settings import AppSettings, ProjectionSettings


def test_settings_keep_video_background(tmp_path: Path) -> None:
    video = tmp_path / "nuages.mp4"
    video.write_bytes(b"x")
    path = tmp_path / "settings.json"
    settings = AppSettings()
    settings.projection = ProjectionSettings(bg_mode="video", bg_video=str(video))
    settings.save(path)
    loaded = AppSettings.load(path).projection
    assert loaded.bg_mode == "video" and loaded.bg_video == str(video)
    cfg = loaded.to_presentation_config()
    assert cfg["bg_mode"] == "video" and cfg["bg_video"] == str(video)

    # Vidéo disparue : repli sur la couleur (jamais d'écran noir).
    video.unlink()
    assert AppSettings.load(path).projection.bg_mode == "color"


def test_canvas_paints_video_frame_under_text() -> None:
    QApplication.instance() or QApplication([])
    from app.ui.slide_canvas import SlideCanvas

    requested = []

    class Canvas(SlideCanvas):
        def _on_background_video_changed(self, path: str) -> None:
            requested.append(path)

    canvas = Canvas()
    canvas.resize(320, 180)
    cfg = ProjectionSettings(bg_mode="video", bg_video="C:/fonds/nuages.mp4").to_presentation_config()
    cfg["background_dimmer"] = 0.0
    canvas.apply_config(cfg)
    canvas.set_slide({"text": "", "reference": "", "source": "bible"})
    assert requested == ["C:/fonds/nuages.mp4"]

    frame = QImage(64, 36, QImage.Format.Format_RGB32)
    frame.fill(QColor(200, 30, 30))
    canvas.set_background_frame(frame)
    pixel = canvas.grab().toImage().pixelColor(160, 90)
    assert pixel.red() > 150 and pixel.green() < 80

    # Un slide de playlist avec sa propre vidéo de fond l'emporte.
    canvas.set_slide({"text": "Gloire", "background": "D:/louange.mp4", "source": "custom"})
    assert requested[-1] == "D:/louange.mp4"

    # Un média projeté comme contenu coupe le fond vidéo.
    canvas.set_slide({"text": "", "image": "D:/photo.png", "source": "image"})
    assert requested[-1] == ""
    canvas.close()
