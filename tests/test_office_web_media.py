"""PowerPoint (rendu fidèle) et purge des pages web dans les Médias."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.database.connection import Database, DatabaseConfig  # noqa: E402
from app.database.dao_media import MediaDao  # noqa: E402
from app.database.dao_playlist import PlaylistDao  # noqa: E402
from app.utils.project_on_controller import ProjectOnController  # noqa: E402
from tests.test_playlist_tab import _QuietStubTab  # noqa: E402


def _make_db(tmp_path: Path) -> Database:
    db = Database(DatabaseConfig(db_path=tmp_path / "web.db"))
    db.initialize()
    return db


def test_media_kind_powerpoint() -> None:
    from app.utils.media_utils import media_kind

    assert media_kind("presentation.pptx") == "powerpoint"
    assert media_kind("SHOW.PPSX") == "powerpoint"
    assert media_kind("image.png") == "image"


def test_media_dao_purges_web_entries(tmp_path: Path) -> None:
    """Les pages web ne sont plus projetables : elles sont purgées."""
    dao = MediaDao(_make_db(tmp_path))
    dao.add_media("Ancien site", "https://example.org", "web")
    dao.add_media("Photo", str(tmp_path / "photo.png"), "image")

    removed = dao.purge_web_media()

    assert removed == 1
    assert [m["kind"] for m in dao.list_media()] == ["image"]


def test_load_media_rejects_urls(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    controller = ProjectOnController(db=db, presentation_dir=tmp_path / "pres")

    assert controller.load_media("https://example.org/don", "Dons") == -1
    assert controller.program_count == 0


def test_playlist_powerpoint_expands_rendered_slides(tmp_path: Path) -> None:
    """Un item PowerPoint développe ses slides rendues (cache pré-rempli)."""
    from PySide6.QtWidgets import QApplication

    from app.ui.playlist_tab import PlaylistTab
    from app.utils.library_controller import LibraryController
    from app.utils.office_renderer import pptx_slides_dir

    app = QApplication.instance() or QApplication([])
    db = _make_db(tmp_path)
    project = ProjectOnController(db=db, presentation_dir=tmp_path / "pres")
    controller = LibraryController(
        db=db,
        project_controller=project,
        bible_tab=_QuietStubTab(),
        hymns_tab=_QuietStubTab(),
        sermons_tab=_QuietStubTab(),
        expose_tab=None,
        playlist_tab=PlaylistTab(),
    )

    class _ImmediatePool:
        def start(self, runnable, *_args, **_kwargs) -> None:
            runnable.run()

    controller._pool = _ImmediatePool()

    fake_pptx = tmp_path / "predication.pptx"
    fake_pptx.write_bytes(b"PK\x03\x04")  # signature zip (pptx = zip)
    cache_dir = pptx_slides_dir(fake_pptx)
    for i in (1, 2, 3):
        (cache_dir / f"slide-{i:02d}.png").write_bytes(
            b"\x89PNG\r\n\x1a\n"  # en-tête PNG suffisant pour le test
        )
    # Un cache n'est réutilisé que s'il porte le marqueur d'achèvement
    # (empreinte du fichier source + nombre de slides).
    from app.utils.office_renderer import _write_complete_marker

    _write_complete_marker(cache_dir, fake_pptx, 3)

    dao = PlaylistDao(db)
    folder_id = dao.create_folder("Avec présentation")
    controller._current_playlist_folder_id = folder_id
    dao.add_item(
        "media", "Prédication PPT", "", folder_id=folder_id, background=str(fake_pptx)
    )

    controller.on_playlist_play(None)
    payload = json.loads((tmp_path / "pres" / "slide.json").read_text(encoding="utf-8"))
    assert payload["source"] == "image"
    assert "predication" in payload["image"].lower()
    assert project.program_count == 3
    app.processEvents()
