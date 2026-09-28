"""Orateur du jour sur OBS (page navigateur), NDI et HDMI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw

from app.utils.church_graphics import ChurchProfile, speaker_broadcast_badge
from app.utils.obs_overlay_render import render_obs_overlay, render_obs_overlay_on_color

ROOT = Path(__file__).resolve().parents[1]
RED = (200, 30, 40)
SLIDE = {"text": "Maintenant la foi est une ferme assurance", "reference": "Hébreux 11:1",
         "source": "bible"}


def _cutout(path: Path) -> Path:
    image = Image.new("RGBA", (300, 400), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((100, 20, 200, 120), fill=(*RED, 180))  # bord semi-transparent
    draw.rectangle((60, 130, 240, 400), fill=(*RED, 255))
    image.save(path)
    return path


def _badge(tmp_path: Path, **extra) -> dict:
    profile = ChurchProfile(speaker_name="Jean Kabasele", speaker_title="Évangéliste",
                            speaker_photo=str(_cutout(tmp_path / "o.png")), **extra)
    return speaker_broadcast_badge(profile)


def _band_bbox(image):
    """Boîte du bandeau (pixels opaques dans la moitié gauche/centre)."""
    alpha = image.getchannel("A").point(lambda a: 255 if a > 200 else 0)
    return alpha.getbbox()


def test_broadcast_badge_settings(tmp_path: Path) -> None:
    badge = _badge(tmp_path, speaker_on_broadcast="sermon", speaker_broadcast_size=30)
    assert (badge["mode"], badge["size"], badge["name"]) == ("sermon", 30, "Jean Kabasele")
    assert ChurchProfile(speaker_on_broadcast="bof").sanitized().speaker_on_broadcast == "all"


def test_ndi_hdmi_render_places_speaker_beside_the_band(tmp_path: Path) -> None:
    plain = render_obs_overlay({}, SLIDE, 1920, 1080)
    with_speaker = render_obs_overlay({"speaker_badge": _badge(tmp_path)}, SLIDE, 1920, 1080)
    # Photo en bas à droite, bandeau décalé vers la gauche.
    r, g, b, a = with_speaker.getpixel((1920 - 100, 1080 - 95))
    assert a == 255 and r > 150 and g < 80
    assert _band_bbox(with_speaker)[0] < _band_bbox(plain)[0]

    # Prédications seulement : rien sur un verset.
    sermon_only = {"speaker_badge": _badge(tmp_path, speaker_on_broadcast="sermon")}
    assert render_obs_overlay(sermon_only, SLIDE, 1920, 1080).tobytes() == plain.tobytes()
    # Slide masquée : rien du tout.
    assert render_obs_overlay({"speaker_badge": _badge(tmp_path)}, {**SLIDE, "hidden": True}) is None


def test_hdmi_chroma_key_photo_has_hard_edges(tmp_path: Path) -> None:
    from app.ui.mixer_output_window import hdmi_band_config

    key = (0, 177, 64)
    image = render_obs_overlay_on_color(
        hdmi_band_config({"speaker_badge": _badge(tmp_path)}, "subtitle"), SLIDE,
        bg_rgba=(*key, 255),
    )
    head = image.crop((1920 - 300, 1080 - 180, 1920, 1080 - 75)).convert("RGB")
    # Aucun mélange photo / couleur de clé : chaque pixel est la clé ou la photo.
    pixels = list(head.get_flattened_data() if hasattr(head, "get_flattened_data")
                  else head.getdata())
    mixed = [p for p in pixels if p != key and p[1] > 90]
    assert any(p[0] > 150 for p in pixels)
    assert not mixed, mixed[:5]


def test_obs_controller_and_web_server_serve_speaker(tmp_path: Path) -> None:
    from app.utils.obs_web_server import ObsWebServer
    from app.utils.settings import ObsSettings

    badge = _badge(tmp_path)
    server = ObsWebServer(port=18097)
    assert server.start()
    try:
        config = ObsSettings().to_full_obs_config()
        config["speaker_badge"] = badge
        server.update_config(config)
        with urllib.request.urlopen("http://127.0.0.1:18097/api/speaker-photo", timeout=5) as r:
            assert r.read() == Path(badge["photo"]).read_bytes()
        badge_off = {**badge, "photo": str(tmp_path / "absente.png")}
        server.update_config({**config, "speaker_badge": badge_off})
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen("http://127.0.0.1:18097/api/speaker-photo", timeout=5)
    finally:
        server.stop()

    from app.utils.obs_controller import ObsController

    served = []
    controller = ObsController.__new__(ObsController)
    controller._settings = ObsSettings()

    class _Server:
        def update_config(self, cfg):
            served.append(cfg)

    controller._web_server = _Server()
    controller.set_speaker_badge(badge)
    assert served[-1]["speaker_badge"]["name"] == "Jean Kabasele"


def test_obs_page_has_speaker_block() -> None:
    page = (ROOT / "presentation" / "obs.html").read_text("utf-8")
    assert 'id="speaker-photo"' in page and 'id="speaker-name"' in page
    assert "--speaker-reserve" in (ROOT / "presentation" / "obs-style.css").read_text("utf-8")


def test_obs_script_is_valid_javascript() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js absent")
    subprocess.run([node, "--check", str(ROOT / "presentation" / "obs-script.js")], check=True)


def test_main_window_writes_badge_for_ndi_and_hdmi(tmp_path: Path, monkeypatch) -> None:
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
        window._settings.church = ChurchProfile(speaker_name="Jean Kabasele",
                                                speaker_on_broadcast="sermon")
        window._write_obs_config()
        cfg = json.loads((window._presentation_dir / "obs-config.json").read_text("utf-8"))
        assert cfg["speaker_badge"]["name"] == "Jean Kabasele"
        assert cfg["speaker_badge"]["mode"] == "sermon"
    finally:
        window.close()


def test_speaker_photo_is_small_by_default(tmp_path: Path) -> None:
    profile = ChurchProfile.from_payload({"speaker_slides_size": 42, "speaker_broadcast_size": 34})
    # Anciennes valeurs par défaut (grande photo) ramenées à la petite photo.
    assert (profile.speaker_slides_size, profile.speaker_broadcast_size) == (20, 16)
    assert ChurchProfile(speaker_broadcast_size=70).sanitized().speaker_broadcast_size == 40

    image = render_obs_overlay({"speaker_badge": _badge(tmp_path)}, SLIDE, 1920, 1080)
    opaque = image.getchannel("A").point(lambda a: 255 if a > 250 else 0)
    right = opaque.crop((1700, 0, 1920, 1080)).getbbox()
    assert right[1] > 1080 * 0.8  # la photo occupe moins d'un cinquième de la hauteur
