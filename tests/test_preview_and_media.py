"""Aperçu fidèle, boucle vidéo, médias — et réglages hérités des thèmes."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.database.connection import Database, DatabaseConfig
from app.database.dao_media import MediaDao
from app.utils.project_on_controller import ProjectOnController
from app.utils.settings import AppSettings
from app.utils.slide_writer import SlideWriter
from app.utils.models import Slide


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings_path(tmp_path: Path) -> Path:
    return tmp_path / "settings.json"


def test_legacy_theme_settings_load_and_are_dropped(settings_path):
    """Projection themes were removed: an older settings.json that still
    carries them loads normally, keeps its projection style (the active
    theme's style was mirrored there) and saves without the theme keys."""
    settings_path.write_text(
        json.dumps(
            {
                "projection": {"font_family": "Passion One", "text_size": 45},
                "themes": [{"id": "dimanche", "name": "DIMANCHE", "style": {"text_size": 70}}],
                "theme_assignments": {"hymn": "dimanche"},
                "active_theme_id": "default",
            }
        ),
        encoding="utf-8",
    )
    settings = AppSettings.load(settings_path)
    assert settings.projection.font_family == "Passion One"
    assert settings.projection.text_size == 45
    assert not settings.load_warning

    settings.save(settings_path)
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert not {"themes", "theme_assignments", "active_theme_id"} & set(saved)


def test_preview_renders_pixmap(qapp):
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
