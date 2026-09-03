"""Tests Project-On 2.0 : thèmes, écran scène, ticker, annonces, boucle vidéo."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from app.database.connection import Database, DatabaseConfig
from app.database.dao_media import MediaDao
from app.database.dao_playlist import PlaylistDao
from app.utils.announcement_controller import AnnouncementController
from app.utils.project_on_controller import ProjectOnController
from app.utils.settings import AppSettings, StageSettings, TickerSettings
from app.utils.slide_writer import SlideWriter
from app.utils.models import Slide
from app.utils.themes import (
    DEFAULT_THEME_ID,
    Theme,
    ThemeRegistry,
    builtin_theme_presets,
    default_theme,
    make_theme_id,
)


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings_path(tmp_path: Path) -> Path:
    return tmp_path / "settings.json"


# ── Thèmes ────────────────────────────────────────────────────────────────

def test_settings_seed_default_theme_when_missing(settings_path):
    AppSettings().save(settings_path)
    loaded = AppSettings.load(settings_path)
    assert len(loaded.themes) == 1
    assert loaded.themes[0].id == DEFAULT_THEME_ID
    assert loaded.active_theme_id == DEFAULT_THEME_ID


def test_settings_theme_roundtrip_and_mirror(settings_path):
    settings = AppSettings()
    settings.themes = [default_theme(settings.projection)] + builtin_theme_presets()
    settings.active_theme_id = "or-ancien"
    settings.projection = copy.deepcopy(
        next(t for t in settings.themes if t.id == "or-ancien").style
    )
    settings.theme_assignments = {"hymn": "or-ancien", "bible": "epure-nuit"}
    settings.save(settings_path)

    loaded = AppSettings.load(settings_path)
    assert [t.id for t in loaded.themes] == [
        DEFAULT_THEME_ID,
        "epure-nuit",
        "or-ancien",
        "blanc-minimal",
    ]
    assert loaded.active_theme_id == "or-ancien"
    assert loaded.theme_assignments == {"hymn": "or-ancien", "bible": "epure-nuit"}
    # Le thème actif est persisté depuis le miroir projection.
    active = next(t for t in loaded.themes if t.id == loaded.active_theme_id)
    assert active.style.bg_color == loaded.projection.bg_color
    assert loaded.projection.bg_color == "#120d04"  # Or Ancien


def test_settings_invalid_assignment_dropped(settings_path):
    settings = AppSettings()
    settings.save(settings_path)
    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    payload["theme_assignments"] = {"hymn": "inexistant", "bible": "default"}
    payload["active_theme_id"] = "inexistant"
    settings_path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = AppSettings.load(settings_path)
    assert loaded.theme_assignments == {"bible": DEFAULT_THEME_ID}
    assert loaded.active_theme_id == DEFAULT_THEME_ID


def test_make_theme_id_unique():
    ids = ["nouveau-theme"]
    assert make_theme_id("Nouveau Thème", ids) == "nouveau-theme-2"
    assert make_theme_id("Or & Bleu nuit", []) == "or-bleu-nuit"


def test_theme_registry_resolution():
    config = {
        "themes": {
            "default": {"bg_mode": "color", "bg_color": "#07111f"},
            "cantique": {"bg_mode": "color", "bg_color": "#331104", "text_size": 70},
        },
        "theme_assignments": {"hymn": "cantique"},
        "active_theme": "default",
    }
    registry = ThemeRegistry(config)
    # Source assignée → style du thème ; sinon None (= style global).
    assert registry.style_for("hymn")["bg_color"] == "#331104"
    assert registry.style_for("bible") is None
    assert registry.theme_id_for("hymn") == "cantique"
    assert registry.theme_id_for("sermon") == "default"


def test_theme_registry_fallback_active_missing():
    registry = ThemeRegistry({"active_theme": "inconnu"})
    assert registry.active_id == DEFAULT_THEME_ID


def test_projection_window_applies_per_source_theme(qapp, tmp_path):
    from app.ui.projection_window import ProjectionWindow

    config = {
        "layout_mode": "fullscreen",
        "bg_mode": "color",
        "bg_color": "#07111f",
        "text_size": 56,
        "themes": {
            "default": {"layout_mode": "fullscreen", "text_size": 56},
            "cantique": {"layout_mode": "fullscreen", "text_size": 70},
        },
        "theme_assignments": {"hymn": "cantique"},
        "active_theme": "default",
    }
    (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")
    window = ProjectionWindow(tmp_path)
    window._apply_slide({"text": "a", "reference": "r", "source": "bible"})
    assert window._theme_active is None
    window._apply_slide({"text": "b", "reference": "r", "source": "hymn"})
    assert window._theme_active == "cantique"
    assert window._config["text_size"] == 70
    window._apply_slide({"text": "c", "reference": "r", "source": "sermon"})
    assert window._theme_active is None
    assert window._config["text_size"] == 56


def test_preview_renders_theme_pixmap(qapp):
    from app.ui.preview_panel import PreviewPanel

    panel = PreviewPanel(settings=AppSettings())
    pix = panel._render_canvas_pixmap("Jean 3:16", "Car Dieu…", source="bible")
    assert pix is not None and pix.width() == SlideCanvas_WIDTH
    hidden = panel._render_canvas_pixmap("", "", hidden=True)
    assert hidden is not None


SlideCanvas_WIDTH = 1920


# ── Écran scène ───────────────────────────────────────────────────────────

def test_stage_settings_sanitized():
    raw = StageSettings(text_size=9999, next_size=-4, bg_color="")
    clean = raw.sanitized()
    assert clean.text_size == 160
    assert clean.next_size == 10
    assert clean.bg_color  # fallback appliqué


def test_stage_window_shows_slide_next_and_message(qapp):
    from app.ui.stage_window import StageWindow

    window = StageWindow(StageSettings())
    window.set_slide({"reference": "Jean 3:16", "text": "Car Dieu…", "source": "bible"})
    window.set_next_slide({"reference": "Jean 3:17", "text": "Afin que…"})
    assert window._current_text.text() == "Car Dieu…"
    assert window._next_text.text() == "Afin que…"
    window.show_message("Pasteur, veuillez venir")
    assert window._message_label.isVisible()
    window.clear_message()
    assert not window._message_label.isVisible()
    # Slide masquée
    window.set_slide({"reference": "", "text": "", "hidden": True})
    assert window._current_text.text() == ""


# ── Ticker ────────────────────────────────────────────────────────────────

def test_ticker_settings_roundtrip(settings_path):
    settings = AppSettings()
    settings.ticker = TickerSettings(
        enabled=True, texts=["Annonce A", "Annonce B"], speed=150, height=80
    )
    settings.save(settings_path)
    loaded = AppSettings.load(settings_path)
    assert loaded.ticker.enabled is True
    assert loaded.ticker.texts == ["Annonce A", "Annonce B"]
    assert loaded.ticker.speed == 150


def test_ticker_overlay_renders(qapp):
    from app.ui.ticker_overlay import TickerOverlay

    ticker = TickerOverlay()
    ticker.configure(["Annonce 1", "Annonce 2"], True, speed=120, height=64)
    ticker.resize(1920, 64)
    assert ticker.height() == 64
    pix = ticker.grab()
    assert not pix.isNull()
    ticker.configure([], True)
    assert not ticker.isVisible()


# ── Boucle d'annonces ─────────────────────────────────────────────────────

@pytest.fixture
def live_setup(tmp_path: Path):
    database = Database(DatabaseConfig(db_path=tmp_path / "ann.db"))
    database.initialize()
    controller = ProjectOnController(db=database, presentation_dir=tmp_path)
    controller.load_program("bible", "Jean 3", [("Jean 3:16", "Car Dieu a tant aimé")])
    return controller, PlaylistDao(database)


def test_announcement_loop_restores_live(live_setup):
    controller, playlist_dao = live_setup
    folder_id = playlist_dao.create_folder("Annonces")
    playlist_dao.add_item("custom", "Annonce 1", "Réunion mardi", folder_id=folder_id)
    playlist_dao.add_item("custom", "Annonce 2", "Culte dimanche", folder_id=folder_id)

    controller_announcements = AnnouncementController(controller, playlist_dao)
    controller_announcements.set_folder(folder_id)
    assert controller_announcements.start() is True
    assert controller_announcements.is_active
    assert controller.program_title == "Annonces"
    assert controller.program_count == 2

    controller_announcements.stop()
    assert not controller_announcements.is_active
    assert controller.program_title == "Jean 3"
    assert controller.current_row() == 0
    assert controller.current_slide().text == "Car Dieu a tant aimé"


def test_announcement_loop_needs_playlist(live_setup):
    controller, playlist_dao = live_setup
    controller_announcements = AnnouncementController(controller, playlist_dao)
    assert controller_announcements.start() is False
    assert not controller_announcements.is_active


# ── Boucle vidéo ──────────────────────────────────────────────────────────

def test_slide_writer_video_loop(tmp_path: Path):
    writer = SlideWriter(presentation_dir=tmp_path)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"0")
    writer.write(Slide(source="video", reference="Clip", text="", video_path=str(video)))
    writer.set_video_loop(True)
    payload = json.loads((tmp_path / "slide.json").read_text(encoding="utf-8"))
    assert payload["video_loop"] is True
    writer.write(Slide(source="bible", reference="Jean 3:16", text="…"))
    payload = json.loads((tmp_path / "slide.json").read_text(encoding="utf-8"))
    assert payload["video_loop"] is False  # pas de vidéo → boucle éteinte


def test_media_loop_column_and_dao(db):
    dao = MediaDao(db)
    media_id = dao.add_media("Vidéo", "C:/fake/video.mp4", "video")
    assert dao.get_media(media_id)["loop"] == 0
    assert dao.set_loop(media_id, True) is True
    assert dao.get_media(media_id)["loop"] == 1
    listing = [m for m in dao.list_media() if m["id"] == media_id]
    assert listing[0]["loop"] == 1


def test_media_item_v8_migration_on_legacy_base(tmp_path: Path):
    """Une table media_item pré-2.0 (sans colonne loop) est patchée par v8."""
    import sqlite3

    legacy = tmp_path / "legacy.db"
    database = Database(DatabaseConfig(db_path=legacy))
    conn = None
    try:
        conn = sqlite3.connect(legacy)
        conn.execute(
            "CREATE TABLE media_item (id INTEGER PRIMARY KEY, name TEXT NOT NULL,"
            " path TEXT NOT NULL UNIQUE, kind TEXT NOT NULL DEFAULT 'image',"
            " sort_order INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.commit()
        database._apply_migration_v8(conn)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(media_item)").fetchall()]
        assert "loop" in cols
    finally:
        if conn is not None:
            conn.close()
