"""Profil de l'église, écran d'accueil et images de citations."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.ui.bible_tab import join_references
from app.utils.church_graphics import ChurchProfile, render_quote, render_welcome
from app.utils.settings import AppSettings

ROOT = Path(__file__).resolve().parents[1]


def test_profile_sanitized_and_round_trip(tmp_path: Path) -> None:
    profile = ChurchProfile.from_payload({"name": " Tabernacle ", "primary_color": "bleu"})
    assert profile.name == "Tabernacle"
    assert profile.primary_color == ChurchProfile().primary_color  # couleur invalide
    path = tmp_path / "s.json"
    settings = AppSettings()
    settings.church = ChurchProfile(name="Église", accent_color="#112233")
    settings.save(path)
    loaded = AppSettings.load(path).church
    assert loaded.name == "Église" and loaded.accent_color == "#112233"


def test_quote_formats_and_colors() -> None:
    profile = ChurchProfile(name="Église", primary_color="#102030",
                            logo=str(ROOT / "assets" / "logo" / "app icon.png"))
    for fmt, size in (("square", (1080, 1080)), ("story", (1080, 1920)),
                      ("landscape", (1920, 1080))):
        image = render_quote(profile, "Dieu est amour. " * 20, "1 Jean 4:8", fmt)
        assert image.size == size
    corner = render_quote(profile, "Court", "", "square").getpixel((2, 0))
    assert all(abs(a - b) <= 1 for a, b in zip(corner[:3], (16, 32, 48)))
    welcome = render_welcome(profile, 960, 540)
    assert welcome.size == (960, 540)


def test_join_references() -> None:
    assert join_references(["Jean 3:16"]) == "Jean 3:16"
    assert join_references(["Jean 3:16", "Jean 3:17", "Jean 3:18"]) == "Jean 3:16-18"
    assert join_references(["Jean 3:36", "Jean 4:1"]) == "Jean 3:36 – Jean 4:1"


def test_dialogs_and_welcome_projection(tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from app.database.connection import Database, DatabaseConfig
    from app.ui.church_profile_dialog import ChurchProfileDialog, QuoteImageDialog
    from app.ui.main_window import MainWindow

    dialog = ChurchProfileDialog(ChurchProfile(name="Église test"))
    emitted = []
    dialog.profileChanged.connect(emitted.append)
    dialog.motto.setText("Christ est la lumière")
    dialog._emit()
    assert emitted[-1].motto == "Christ est la lumière"
    assert dialog.preview.pixmap() is not None
    dialog.close()

    quote = QuoteImageDialog(ChurchProfile(name="Église"), "Jean 3:16", "Car Dieu…")
    quote.format.setCurrentIndex(quote.format.findData("story"))
    assert quote.image().size == (1080, 1920)
    quote.close()

    monkeypatch.setattr(MainWindow, "_start_obs_output", lambda self: None)
    monkeypatch.setattr(MainWindow, "_poll_obs_status", lambda self: None)
    db = Database(DatabaseConfig(db_path=tmp_path / "m.db"))
    db.initialize()
    window = MainWindow(db=db)
    try:
        window._settings.church = ChurchProfile(name="Église test")
        window._project_welcome_screen()
        slide = json.loads((window._presentation_dir / "slide.json").read_text("utf-8"))
        assert slide["image"].endswith("accueil.png") and Path(slide["image"]).is_file()
    finally:
        window.close()
