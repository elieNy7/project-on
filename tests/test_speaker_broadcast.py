"""L'orateur du jour n'apparaît plus sur OBS (page navigateur), NDI ni HDMI."""

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

from app.utils.church_graphics import ChurchProfile, speaker_slide_badge
from app.utils.obs_overlay_render import render_obs_overlay

ROOT = Path(__file__).resolve().parents[1]
RED = (200, 30, 40)
SLIDE = {"text": "Maintenant la foi est une ferme assurance", "reference": "Hébreux 11:1",
         "source": "bible"}


def _badge(tmp_path: Path) -> dict:
    image = Image.new("RGBA", (300, 400), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((60, 130, 240, 400), fill=(*RED, 255))
    image.save(tmp_path / "o.png")
    profile = ChurchProfile(speaker_name="Jean Kabasele", speaker_title="Évangéliste",
                            speaker_photo=str(tmp_path / "o.png"))
    return speaker_slide_badge(profile)


def test_ndi_hdmi_render_ignores_speaker_badge(tmp_path: Path) -> None:
    plain = render_obs_overlay({}, SLIDE, 1920, 1080)
    with_badge = render_obs_overlay({"speaker_badge": _badge(tmp_path)}, SLIDE, 1920, 1080)
    assert with_badge.tobytes() == plain.tobytes()


def test_old_broadcast_settings_are_ignored() -> None:
    profile = ChurchProfile.from_payload({"speaker_slides_size": 42,
                                          "speaker_on_broadcast": "all",
                                          "speaker_broadcast_size": 34})
    assert profile.speaker_slides_size == 20
    assert not hasattr(profile, "speaker_on_broadcast")


def test_web_server_no_longer_serves_speaker_photo(tmp_path: Path) -> None:
    from app.utils.obs_web_server import ObsWebServer
    from app.utils.settings import ObsSettings

    server = ObsWebServer(port=18097)
    assert server.start()
    try:
        config = ObsSettings().to_full_obs_config()
        config["speaker_badge"] = _badge(tmp_path)
        server.update_config(config)
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen("http://127.0.0.1:18097/api/speaker-photo", timeout=5)
    finally:
        server.stop()


def test_obs_page_has_no_speaker_block() -> None:
    page = (ROOT / "presentation" / "obs.html").read_text("utf-8")
    assert 'id="speaker' not in page
    assert "speaker" not in (ROOT / "presentation" / "obs-style.css").read_text("utf-8")
    assert "speaker" not in (ROOT / "presentation" / "obs-script.js").read_text("utf-8")


def test_obs_script_is_valid_javascript() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js absent")
    subprocess.run([node, "--check", str(ROOT / "presentation" / "obs-script.js")], check=True)


def test_main_window_writes_no_badge_for_obs(tmp_path: Path, monkeypatch) -> None:
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
        window._settings.church = ChurchProfile(speaker_name="Jean Kabasele")
        window._write_obs_config()
        cfg = json.loads((window._presentation_dir / "obs-config.json").read_text("utf-8"))
        assert "speaker_badge" not in cfg
    finally:
        window.close()
