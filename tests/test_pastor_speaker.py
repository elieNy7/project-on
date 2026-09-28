"""Pasteur (sur toutes les publications) et orateur du jour."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw

from app.utils.church_graphics import (
    ChurchProfile,
    has_guest_speaker,
    pastor_label,
    render_quote,
    render_socials,
    render_speaker,
    render_welcome,
    speaker_label,
)

PASTOR_BLUE = (20, 30, 200)
GUEST_GREEN = (20, 180, 60)


def _cutout(path: Path, color) -> Path:
    """Silhouette sur fond transparent (photo « sans arrière-plan »)."""
    image = Image.new("RGBA", (300, 400), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((100, 20, 200, 120), fill=(*color, 255))
    draw.rectangle((60, 130, 240, 400), fill=(*color, 255))
    image.save(path)
    return path


def _has_color(image, color, box=None) -> bool:
    region = image.crop(box) if box else image
    import numpy as np

    pixels = np.asarray(region.convert("RGB"))
    return bool((pixels == np.array(color, dtype=pixels.dtype)).all(axis=2).any())


def _profile(tmp_path: Path, **extra) -> ChurchProfile:
    return ChurchProfile(
        name="Église", pastor_title="Pasteur", pastor_name="Elie Nyembo",
        pastor_photo=str(_cutout(tmp_path / "pasteur.png", PASTOR_BLUE)), **extra,
    )


def test_pastor_face_is_on_every_publication(tmp_path: Path) -> None:
    profile = _profile(tmp_path, socials={"youtube": "@Eglise"})
    for image in (
        render_welcome(profile),
        render_socials(profile),
        render_quote(profile, "Dieu est amour", "1 Jean 4:8", "square"),
        render_quote(profile, "Dieu est amour", "1 Jean 4:8", "story"),
        render_speaker(profile),
    ):
        assert _has_color(image, PASTOR_BLUE), image.size


def test_speaker_defaults_to_the_pastor(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    assert not has_guest_speaker(profile)
    assert speaker_label(profile) == pastor_label(profile) == "Pasteur Elie Nyembo"


def test_guest_speaker_screen_keeps_the_pastor(tmp_path: Path) -> None:
    profile = _profile(
        tmp_path, speaker_title="Évangéliste", speaker_name="Jean Kabasele",
        speaker_photo=str(_cutout(tmp_path / "invite.png", GUEST_GREEN)),
        speaker_message="La foi",
    )
    assert has_guest_speaker(profile) and speaker_label(profile) == "Évangéliste Jean Kabasele"
    screen = render_speaker(profile)
    assert _has_color(screen, GUEST_GREEN, (0, 0, 960, 1080))  # invité en grand, à gauche
    assert _has_color(screen, PASTOR_BLUE, (1500, 600, 1920, 1080))  # pasteur en médaillon
    welcome = render_welcome(profile)
    plain = render_welcome(ChurchProfile(**{**profile.__dict__, "speaker_name": "",
                                            "speaker_message": ""}))
    assert welcome.tobytes() != plain.tobytes()  # « Orateur du jour : … »


def test_legacy_message_and_round_trip(tmp_path: Path) -> None:
    from app.utils.settings import AppSettings

    legacy = ChurchProfile.from_payload({"pastor_message": "La grâce"})
    assert legacy.speaker_message == "La grâce"
    path = tmp_path / "s.json"
    settings = AppSettings()
    settings.church = ChurchProfile(speaker_name="Jean", speaker_title="Frère")
    settings.save(path)
    loaded = AppSettings.load(path).church
    assert (loaded.speaker_name, loaded.speaker_title) == ("Jean", "Frère")


def test_dialog_imports_transparent_photos_only(tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

    QApplication.instance() or QApplication([])
    from app.ui.church_profile_dialog import ChurchProfileDialog, has_transparency

    cutout = _cutout(tmp_path / "cut.png", PASTOR_BLUE)
    opaque = tmp_path / "photo.jpg"
    Image.new("RGB", (200, 200), (200, 200, 200)).save(opaque)
    assert has_transparency(cutout) and not has_transparency(opaque)

    dialog = ChurchProfileDialog(ChurchProfile(name="Église"), logo_folder=tmp_path / "church")
    try:
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(cutout), ""))
        dialog._import_photo("pastor")
        stored = Path(dialog.read_profile().pastor_photo)
        assert stored.parent == tmp_path / "church" and stored.is_file()

        # Photo avec arrière-plan : refusée si l'opérateur ne confirme pas.
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(opaque), ""))
        monkeypatch.setattr(QMessageBox, "question",
                            lambda *a, **k: QMessageBox.StandardButton.No)
        dialog._import_photo("speaker")
        assert dialog.read_profile().speaker_photo == ""

        dialog.speaker_name.setText("Jean Kabasele")
        dialog.speaker_title.setCurrentText("Évangéliste")
        assert dialog.read_profile().speaker_name == "Jean Kabasele"
        dialog._pastor_preaches()
        assert dialog.read_profile().speaker_name == ""
    finally:
        dialog.close()


def test_main_window_projects_speaker_screen(tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from app.database.connection import Database, DatabaseConfig
    from app.ui.main_window import MainWindow

    monkeypatch.setattr(MainWindow, "_start_obs_output", lambda self: None)
    monkeypatch.setattr(MainWindow, "_poll_obs_status", lambda self: None)
    db = Database(DatabaseConfig(db_path=tmp_path / "m.db"))
    db.initialize()
    window = MainWindow(db=db)
    try:
        window._settings.church = _profile(tmp_path, speaker_name="Jean Kabasele")
        window._project_pastor_screen()
        slide = json.loads((window._presentation_dir / "slide.json").read_text("utf-8"))
        assert slide["image"].endswith("orateur-du-jour.png")
        assert window._project_controller.program_title == "Jean Kabasele"
    finally:
        window.close()
