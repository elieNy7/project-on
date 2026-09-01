"""Médias : DAO, projection image/vidéo et playlists avec visuels."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402

from app.database.connection import Database, DatabaseConfig  # noqa: E402
from app.database.dao_media import MediaDao  # noqa: E402
from app.database.dao_playlist import PlaylistDao  # noqa: E402
from app.ui.media_tab import MediaTab  # noqa: E402
from app.utils.project_on_controller import ProjectOnController  # noqa: E402
from tests.test_playlist_tab import _QuietStubTab  # noqa: E402


def _make_db(tmp_path: Path) -> Database:
    db = Database(DatabaseConfig(db_path=tmp_path / "media.db"))
    db.initialize()
    return db


def test_media_dao_crud(tmp_path: Path) -> None:
    dao = MediaDao(_make_db(tmp_path))

    media_id = dao.add_media("Intro", "C:/media/intro.png", "image")
    assert dao.add_media("Intro", "C:/media/intro.png", "image") == media_id  # idempotent

    dao.add_media("Clip", "C:/media/clip.mp4", "video")
    items = dao.list_media()
    assert [i["kind"] for i in items] == ["image", "video"]

    assert dao.rename_media(media_id, "Ouverture")
    assert dao.get_media(media_id)["name"] == "Ouverture"
    assert dao.delete_media(media_id)
    assert dao.get_media(media_id) is None


def test_load_program_with_visuals(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    controller = ProjectOnController(db=db, presentation_dir=tmp_path / "pres")

    controller.load_program(
        "custom",
        "Culte",
        [("Image 1", ""), ("Clip bienvenue", ""), ("Jean 3:16", "Car Dieu a tant aimé…")],
        entry_visuals=[
            str(tmp_path / "img.png"),
            str(tmp_path / "clip.mp4"),
            "",
        ],
    )

    assert controller.program_count == 3
    first = controller._program_slides[0]
    assert first.source == "image" and first.image_path == str(tmp_path / "img.png")
    video = controller._program_slides[1]
    assert video.source == "video" and video.video_path == str(tmp_path / "clip.mp4")
    assert video.text == ""
    assert controller._program_slides[2].text.startswith("Car Dieu")


def test_slide_writer_video_payload(tmp_path: Path) -> None:
    from app.utils.models import Slide
    from app.utils.slide_writer import SlideWriter

    writer = SlideWriter(presentation_dir=tmp_path / "pres")
    writer.write(
        Slide(
            source="video",
            reference="Clip bienvenue",
            text="",
            video_path=str(tmp_path / "clip.mp4"),
        )
    )
    payload = json.loads((tmp_path / "pres" / "slide.json").read_text(encoding="utf-8"))
    assert payload["video"] == str(tmp_path / "clip.mp4")
    assert payload["video_playing"] is False
    assert payload["video_reset"] is False

    writer.set_video_playing(True)
    payload = json.loads((tmp_path / "pres" / "slide.json").read_text(encoding="utf-8"))
    assert payload["video_playing"] is True

    writer.set_video_reset()
    payload = json.loads((tmp_path / "pres" / "slide.json").read_text(encoding="utf-8"))
    assert payload["video_reset"] is True
    assert payload["video_playing"] is False


def test_playlist_with_media_item_projects_video(tmp_path: Path) -> None:
    from PyQt6.QtWidgets import QApplication

    from app.ui.playlist_tab import PlaylistTab
    from app.utils.library_controller import LibraryController

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
    dao = PlaylistDao(db)

    folder_id = dao.create_folder("Culte média")
    controller._current_playlist_folder_id = folder_id
    video_path = str(tmp_path / "clip.mp4")
    dao.add_item("media", "Clip bienvenue", "", folder_id=folder_id, background=video_path)
    dao.add_item(
        "custom", "Annonce", "Repas partagé après le culte", folder_id=folder_id
    )

    controller.on_playlist_play(None)
    payload = json.loads((tmp_path / "pres" / "slide.json").read_text(encoding="utf-8"))
    assert payload["source"] == "video"
    assert payload["video"] == video_path
    assert project.program_count == 2

    # Le second élément (texte) suit normalement.
    project.next_slide()
    payload = json.loads((tmp_path / "pres" / "slide.json").read_text(encoding="utf-8"))
    assert payload["reference"] == "Annonce"
    app.processEvents()


def test_media_tab_gallery_population(tmp_path: Path) -> None:
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    tab = MediaTab()
    tab.set_media(
        [
            {"id": 1, "name": "Image 1", "path": str(tmp_path / "missing.png"), "kind": "image"},
            {"id": 2, "name": "Clip", "path": str(tmp_path / "clip.mp4"), "kind": "video"},
        ]
    )
    assert tab.gallery.count() == 2
    assert tab.info_label.text() == "2 médias"
    tab.gallery.setCurrentRow(0)
    media = tab.selected_media()
    assert media and media["name"] == "Image 1"
    app.processEvents()
