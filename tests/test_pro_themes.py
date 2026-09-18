"""Tests Project-On 2.0 : thèmes, aperçu fidèle, boucle vidéo."""

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
from app.utils.project_on_controller import ProjectOnController
from app.utils.settings import AppSettings
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
    from app.ui.slide_canvas import SlideCanvas

    panel = PreviewPanel(settings=AppSettings())
    pix = panel._render_canvas_pixmap("Jean 3:16", "Car Dieu…", source="bible")
    assert pix is not None and pix.width() == SlideCanvas.RENDER_WIDTH


def test_preview_keeps_text_when_output_hidden(qapp):
    """Sortie masquée : l'aperçu opérateur garde les textes visibles ; le
    masque ne part que vers les deux projections (fenêtre + OBS/NDI)."""
    from app.ui.preview_panel import PreviewPanel

    panel = PreviewPanel(settings=AppSettings())
    panel.set_slide("Jean 3:16", "Car Dieu…", source="bible")
    before = panel._render_pixmap_full
    assert before is not None

    captured = {}
    canvas = panel._ensure_canvas()
    original = canvas.render_pixmap

    def spy(slide):
        captured.update(slide)
        return original(slide)

    canvas.render_pixmap = spy
    pix = panel._render_canvas_pixmap(
        "Jean 3:16", "Car Dieu…", source="bible", hidden=True
    )
    assert pix is not None
    assert captured["text"] == "Car Dieu…"
    assert captured["reference"] == "Jean 3:16"
    assert captured["hidden"] is False

    # set_hidden ne re-rend plus : le pixmap affiché reste celui des textes.
    panel.set_hidden(True)
    assert panel._render_pixmap_full is before




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
