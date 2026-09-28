"""Pasteur : photo sans arrière-plan, écran du prédicateur, affichages."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw

from app.utils import background_removal as br
from app.utils.church_graphics import (
    ChurchProfile,
    pastor_label,
    render_pastor,
    render_quote,
    render_welcome,
)


def _studio_photo() -> Image.Image:
    """Personne stylisée devant un mur uni, avec une tache isolée."""
    image = Image.new("RGB", (400, 500), (228, 230, 235))
    draw = ImageDraw.Draw(image)
    draw.ellipse((140, 60, 260, 180), fill=(120, 80, 60))  # tête
    draw.rectangle((110, 190, 290, 500), fill=(20, 30, 70))  # buste
    return image


def test_plain_background_is_removed_and_cropped() -> None:
    cut = br.remove_background(_studio_photo(), "plain", 40)
    assert cut.mode == "RGBA"
    assert cut.width < 300  # recadré sur la personne
    assert cut.getpixel((2, 2))[3] == 0  # coin transparent
    assert cut.getpixel((cut.width // 2, cut.height - 5))[3] == 255  # buste opaque


def test_keep_main_subject_removes_islands() -> None:
    mask = Image.new("L", (400, 400), 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle((100, 50, 300, 400), fill=255)  # personne
    draw.ellipse((360, 20, 380, 40), fill=255)  # reste de décor
    cleaned = br.keep_main_subject(mask)
    assert cleaned.getpixel((200, 200)) == 255
    assert cleaned.getpixel((370, 30)) == 0


def test_ai_cutout_when_model_available() -> None:
    pytest.importorskip("onnxruntime")
    if br.model_path() is None:
        pytest.skip("modèle de détourage absent (tools/download_models.py)")
    cut = br.remove_background(_studio_photo(), "ai")
    assert cut.mode == "RGBA" and cut.getpixel((1, 1))[3] < 40


def test_model_download_checks_its_fingerprint(tmp_path: Path, monkeypatch) -> None:
    class _Response(io.BytesIO):
        headers = {"Content-Length": "4"}

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(br, "user_model_path", lambda: tmp_path / "models" / "m.onnx")
    monkeypatch.setattr(br.urllib.request, "urlopen", lambda req, timeout: _Response(b"faux"))
    with pytest.raises(ValueError):
        br.download_model()
    assert not (tmp_path / "models" / "m.onnx").exists()


def _profile(tmp_path: Path, **extra) -> ChurchProfile:
    photo = tmp_path / "pasteur.png"
    br.remove_background(_studio_photo(), "plain").save(photo)
    return ChurchProfile(name="Église", pastor_name="Elie Nyembo", pastor_title="Pasteur",
                         pastor_photo=str(photo), **extra)


def test_pastor_screens(tmp_path: Path) -> None:
    profile = _profile(tmp_path, pastor_message="La foi")
    assert pastor_label(profile) == "Pasteur Elie Nyembo"
    screen = render_pastor(profile, subtitle="La foi")
    assert screen.size == (1920, 1080)
    # La photo occupe la moitié gauche, jusqu'au bas de l'écran.
    assert screen.getpixel((520, 1075))[:3] == (20, 30, 70)

    welcome = render_welcome(profile)
    without = render_welcome(ChurchProfile(**{**profile.__dict__, "show_pastor_welcome": False}))
    assert welcome.tobytes() != without.tobytes()

    plain_quote = render_quote(profile, "Dieu est amour", "1 Jean 4:8")
    signed = render_quote(ChurchProfile(**{**profile.__dict__, "show_pastor_quotes": True}),
                          "Dieu est amour", "1 Jean 4:8")
    assert plain_quote.tobytes() != signed.tobytes()


def test_pastor_fields_round_trip(tmp_path: Path) -> None:
    from app.utils.settings import AppSettings

    path = tmp_path / "s.json"
    settings = AppSettings()
    settings.church = ChurchProfile(pastor_name="Elie", pastor_title="Apôtre",
                                    show_pastor_quotes=True)
    settings.save(path)
    loaded = AppSettings.load(path).church
    assert (loaded.pastor_name, loaded.pastor_title, loaded.show_pastor_quotes) == (
        "Elie", "Apôtre", True)


def test_dialogs_and_projection(tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from app.ui.church_profile_dialog import ChurchProfileDialog
    from app.ui.pastor_photo_dialog import PastorPhotoDialog

    source = tmp_path / "photo.jpg"
    _studio_photo().save(source)
    target = tmp_path / "church" / "pasteur.png"
    monkeypatch.setattr(br, "ai_available", lambda: False)  # pas d'IA ici
    photo_dialog = PastorPhotoDialog(source, target)
    try:
        photo_dialog.run_plain()
        assert photo_dialog.result is not None and photo_dialog.result.getpixel((1, 1))[3] == 0
        photo_dialog._save()
        assert target.is_file()
    finally:
        photo_dialog.close()

    dialog = ChurchProfileDialog(ChurchProfile(name="Église"))
    try:
        dialog.pastor_name.setText("Elie Nyembo")
        dialog.pastor_title.setCurrentText("Révérend")
        dialog.set_pastor_photo(str(target))
        profile = dialog.read_profile()
        assert profile.pastor_photo == str(target) and profile.pastor_title == "Révérend"
        assert dialog.preview_kind.currentData() == "pastor"
        assert dialog.preview.pixmap() is not None
    finally:
        dialog.close()

    from app.database.connection import Database, DatabaseConfig
    from app.ui.main_window import MainWindow

    monkeypatch.setattr(MainWindow, "_start_obs_output", lambda self: None)
    monkeypatch.setattr(MainWindow, "_poll_obs_status", lambda self: None)
    db = Database(DatabaseConfig(db_path=tmp_path / "m.db"))
    db.initialize()
    window = MainWindow(db=db)
    try:
        window._settings.church = profile
        window._project_pastor_screen()
        slide = json.loads((window._presentation_dir / "slide.json").read_text("utf-8"))
        assert slide["image"].endswith("predicateur.png")
    finally:
        window.close()
