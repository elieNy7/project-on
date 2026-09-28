"""Orateur du jour (photo et nom) sur les slides de projection."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw
from PySide6.QtWidgets import QApplication

from app.utils.church_graphics import ChurchProfile, speaker_slide_badge
from app.utils.settings import ProjectionSettings

GREEN = (20, 180, 60)


def _cutout(path: Path) -> Path:
    image = Image.new("RGBA", (300, 400), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((100, 20, 200, 120), fill=(*GREEN, 255))
    draw.rectangle((60, 130, 240, 400), fill=(*GREEN, 255))
    image.save(path)
    return path


@pytest.fixture
def canvas():
    QApplication.instance() or QApplication([])
    from app.ui.slide_canvas import SlideCanvas

    widget = SlideCanvas()
    widget.resize(1920, 1080)
    yield widget
    widget.close()


def _configure(canvas, profile: ChurchProfile) -> None:
    cfg = ProjectionSettings().to_presentation_config()
    cfg["speaker_badge"] = speaker_slide_badge(profile)
    canvas.apply_config(cfg)


SLIDE = {"text": "Maintenant la foi est une ferme assurance", "reference": "Hébreux 11:1",
         "source": "bible"}


def test_badge_defaults_to_pastor_then_guest(tmp_path: Path) -> None:
    pastor = ChurchProfile(pastor_title="Pasteur", pastor_name="Elie",
                           pastor_photo=str(_cutout(tmp_path / "p.png")))
    assert speaker_slide_badge(pastor)["name"] == "Elie"
    guest = ChurchProfile(**{**pastor.__dict__, "speaker_name": "Jean",
                             "speaker_title": "Frère"})
    badge = speaker_slide_badge(guest)
    assert (badge["title"], badge["name"], badge["photo"]) == ("Frère", "Jean", "")
    assert badge["mode"] == "all" and badge["side"] == "right"


def test_photo_and_name_painted_and_text_moved_aside(canvas, tmp_path: Path) -> None:
    profile = ChurchProfile(speaker_name="Jean Kabasele", speaker_title="Évangéliste",
                            speaker_photo=str(_cutout(tmp_path / "o.png")))
    _configure(canvas, ChurchProfile(**{**profile.__dict__, "speaker_on_slides": "off"}))
    canvas.set_slide(dict(SLIDE))
    full_width = canvas._available_content_width

    _configure(canvas, profile)
    canvas.set_slide(dict(SLIDE))
    assert canvas._speaker_reserve_applied > 0
    assert canvas._available_content_width < full_width  # le texte laisse la place
    image = canvas.grab().toImage()
    assert image.pixelColor(1920 - 150, 1080 - 300).green() > 150  # photo, à droite

    # Média plein écran : pas d'orateur par-dessus l'image.
    canvas.set_slide({"text": "", "image": str(tmp_path / "o.png"), "source": "image"})
    assert canvas._speaker_reserve_applied == 0


def test_sermon_only_mode_and_left_side(canvas, tmp_path: Path) -> None:
    profile = ChurchProfile(speaker_name="Jean", speaker_on_slides="sermon",
                            speaker_slides_side="left",
                            speaker_photo=str(_cutout(tmp_path / "o.png")))
    _configure(canvas, profile)
    canvas.set_slide(dict(SLIDE))  # verset : pas d'orateur
    assert canvas._speaker_reserve_applied == 0
    canvas.set_slide({**SLIDE, "source": "sermon"})
    assert canvas._speaker_reserve_applied > 0
    margins = canvas._main_layout.contentsMargins()
    assert margins.left() > margins.right()
    image = canvas.grab().toImage()
    assert image.pixelColor(150, 1080 - 300).green() > 150  # photo, à gauche


def test_main_window_sends_badge_to_projection_and_preview(tmp_path: Path, monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    from app.database.connection import Database, DatabaseConfig
    from app.ui.main_window import MainWindow

    monkeypatch.setattr(MainWindow, "_start_obs_output", lambda self: None)
    monkeypatch.setattr(MainWindow, "_poll_obs_status", lambda self: None)
    db = Database(DatabaseConfig(db_path=tmp_path / "m.db"))
    db.initialize()
    window = MainWindow(db=db)
    try:
        window._settings.church = ChurchProfile(speaker_name="Jean Kabasele")
        window._apply_projection_config()
        cfg = json.loads((window._presentation_dir / "config.json").read_text("utf-8"))
        assert cfg["speaker_badge"]["name"] == "Jean Kabasele"
        assert window.preview_panel._canvas_style_config()["speaker_badge"]["name"] == "Jean Kabasele"
    finally:
        window.close()
