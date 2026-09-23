"""Diaporama de médias : durée par média, enchaînement et restauration."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.database.connection import Database, DatabaseConfig  # noqa: E402
from app.database.dao_media import MediaDao  # noqa: E402
from app.ui.media_tab import MediaTab  # noqa: E402
from app.ui.playlist_tab import PlaylistTab  # noqa: E402
from app.utils.project_on_controller import ProjectOnController  # noqa: E402
from app.utils.slideshow_controller import SlideshowController  # noqa: E402


def _app() -> QApplication:
    """QApplication du test — gardée dans une variable locale par l'appelant.

    PySide6 détruit l'instance dès qu'aucune référence Python ne la retient ;
    un widget créé ensuite ferait tomber le processus (convention des tests
    existants : ``app = QApplication.instance() or QApplication([])``).
    """
    return QApplication.instance() or QApplication([])


def _make_controller(tmp_path: Path) -> ProjectOnController:
    db = Database(DatabaseConfig(db_path=tmp_path / "slideshow.db"))
    db.initialize()
    controller = ProjectOnController(db=db, presentation_dir=tmp_path / "pres")
    controller._db = db  # garde la base vivante pour les asserts
    return controller


def _photo(tmp_path: Path, name: str) -> str:
    path = tmp_path / f"{name}.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    return str(path)


def test_duration_dao_and_migration(tmp_path: Path) -> None:
    db = Database(DatabaseConfig(db_path=tmp_path / "v9.db"))
    db.initialize()
    dao = MediaDao(db)
    media_id = dao.add_media("Photo", _photo(tmp_path, "p"), "image")

    assert dao.get_media(media_id)["duration_seconds"] == 0
    assert dao.set_duration(media_id, 12)
    assert dao.get_media(media_id)["duration_seconds"] == 12
    # Bornage : une valeur absurde ne casse pas la base.
    assert dao.set_duration(media_id, 99999)
    assert dao.get_media(media_id)["duration_seconds"] == 3600
    assert dao.list_media()[0]["duration_seconds"] == 3600


def test_migration_adds_duration_to_existing_database(tmp_path: Path) -> None:
    """Une base 2.4 (v8) doit recevoir la colonne sans perdre ses médias."""
    path = tmp_path / "old.db"
    db = Database(DatabaseConfig(db_path=path))
    db.initialize()
    dao = MediaDao(db)
    media_id = dao.add_media("Ancienne", _photo(tmp_path, "old"), "image")
    with db.connect() as conn:
        conn.execute("ALTER TABLE media_item DROP COLUMN duration_seconds")
        conn.execute("PRAGMA user_version = 8")

    upgraded = Database(DatabaseConfig(db_path=path))
    upgraded.initialize()
    with upgraded.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 9
        cols = [r[1] for r in conn.execute("PRAGMA table_info(media_item)").fetchall()]
    assert "duration_seconds" in cols
    assert MediaDao(upgraded).get_media(media_id)["name"] == "Ancienne"


def test_slideshow_chains_medias_with_their_duration(tmp_path: Path) -> None:
    app = _app()  # noqa: F841 - garde la QApplication vivante
    controller = _make_controller(tmp_path)
    # Un live en place, qui doit être restauré à l'arrêt du diaporama.
    controller.load_program("custom", "Culte", [("Jean 3:16", "Car Dieu a tant aimé")])
    live_slide = controller.current_slide()

    slideshow = SlideshowController(controller)
    slideshow.set_default_duration(0)
    started = slideshow.start(
        [
            {"name": "Photo 1", "path": _photo(tmp_path, "a"), "duration_seconds": 1},
            {"name": "Photo 2", "path": _photo(tmp_path, "b"), "duration_seconds": 1},
        ]
    )
    assert started and slideshow.is_active
    assert controller.program_count == 2
    assert controller.current_row() == 0
    assert controller.current_slide().image_path == _photo(tmp_path, "a")

    # La minuterie du média a bien été armée sur SA durée.
    assert slideshow._timer.interval() == 1000
    slideshow._advance()
    assert controller.current_row() == 1
    assert controller.current_slide().image_path == _photo(tmp_path, "b")

    # Fin de liste : retour au premier média (boucle du diaporama).
    slideshow._advance()
    assert controller.current_row() == 0

    slideshow.stop()
    assert not slideshow.is_active
    assert controller.current_row() == 0
    assert controller.current_slide().reference == live_slide.reference


def test_slideshow_uses_default_duration_when_media_has_none(tmp_path: Path) -> None:
    app = _app()  # noqa: F841 - garde la QApplication vivante
    controller = _make_controller(tmp_path)
    slideshow = SlideshowController(controller)
    slideshow.set_default_duration(7)
    slideshow.start([{"name": "Photo", "path": _photo(tmp_path, "c")}])
    assert slideshow.is_active
    assert slideshow._timer.interval() == 7000

    # Sans durée réglée ni durée par défaut : aucune avance automatique.
    slideshow.stop()
    slideshow.set_default_duration(0)
    slideshow.start([{"name": "Photo", "path": _photo(tmp_path, "d")}])
    assert not slideshow._timer.isActive()
    slideshow.stop()


def test_slideshow_advances_at_video_end(tmp_path: Path) -> None:
    app = _app()  # noqa: F841 - garde la QApplication vivante
    controller = _make_controller(tmp_path)
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\x00")
    slideshow = SlideshowController(controller)
    slideshow.set_default_duration(5)
    slideshow.start(
        [
            {"name": "Clip", "path": str(clip), "duration_seconds": 0},
            {"name": "Photo", "path": _photo(tmp_path, "e")},
        ]
    )
    # Une vidéo donne le tempo : pas de minuterie, on attend la fin de lecture.
    assert slideshow._timer.isActive() is False
    assert slideshow._video_row == 0

    slideshow.on_video_finished()
    assert controller.current_row() == 1
    assert slideshow._timer.interval() == 5000

    # Une vidéo en boucle ne se termine jamais : aucune avance automatique.
    slideshow.stop()
    controller.set_video_loop(True)
    slideshow.start([{"name": "Clip", "path": str(clip)}])
    assert slideshow._video_row is None
    assert not slideshow._timer.isActive()
    slideshow.on_video_finished()
    assert controller.current_row() == 0
    controller.set_video_loop(False)
    slideshow.stop()


def test_slideshow_maps_every_row_to_its_media_duration(tmp_path: Path) -> None:
    """Chaque page projetée retrouve la durée du média qui l'a produite."""
    app = _app()  # noqa: F841 - garde la QApplication vivante
    controller = _make_controller(tmp_path)
    # Forme réelle d'une présentation importée : une entrée par page rendue.
    controller.load_program(
        "image",
        "Deck",
        [("Page 1 (1/3)", ""), ("Page 2 (2/3)", ""), ("Page 3 (3/3)", "")],
        split=False,
        entry_visuals=[
            _photo(tmp_path, "s1"),
            _photo(tmp_path, "s2"),
            _photo(tmp_path, "s3"),
        ],
    )
    slideshow = SlideshowController(controller)
    slideshow._build_row_map([4, 6, 8])
    assert slideshow._rows == [0, 1, 2]
    assert slideshow._durations == {0: 4, 1: 6, 2: 8}

    slideshow.abandon()  # inactif : sans effet, ne lève pas


def test_media_tab_exposes_duration_and_slideshow(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QMenu

    app = _app()  # noqa: F841 - garde la QApplication vivante
    tab = MediaTab()
    captured: list = []
    durations: list = []
    tab.slideshowRequested.connect(lambda medias: captured.append(medias))
    tab.itemDurationRequested.connect(lambda mid, sec: durations.append((mid, sec)))

    tab.set_media(
        [
            {"id": 1, "name": "A", "path": "C:/a.png", "kind": "image", "duration_seconds": 5},
            {"id": 2, "name": "B", "path": "C:/b.png", "kind": "image", "duration_seconds": 0},
        ]
    )
    assert len(tab.all_medias()) == 2
    # La durée réglée est visible dans la galerie.
    assert "5 s" in tab.gallery.item(0).text()

    # Sans sélection, le bouton enchaîne toute la bibliothèque.
    tab.gallery.clearSelection()
    tab.gallery.setCurrentItem(None)
    tab._on_slideshow_clicked()
    assert captured and len(captured[0]) == 2
    assert captured[0][0]["duration_seconds"] == 5

    # Avec une sélection (Ctrl+clic), seuls les médias cochés sont enchaînés.
    tab.gallery.setCurrentRow(1)
    assert tab.selected_media()["duration_seconds"] == 0
    tab._on_slideshow_clicked()
    assert len(captured[-1]) == 1
    assert captured[-1][0]["name"] == "B"

    menu = QMenu(tab)
    custom, actions = tab._build_duration_menu(menu, tab.selected_media() or {})
    assert custom is not None
    assert len(actions) == len(tab._DURATION_CHOICES) + 1
    assert sorted(actions.values()) == [0, 3, 5, 8, 10, 15, 30]


def test_playlist_exposes_media_entries(tmp_path: Path) -> None:
    import sys

    print("A debut", flush=True)
    app = _app()  # noqa: F841 - garde la QApplication vivante
    print("B app", flush=True)
    tab = PlaylistTab()
    print("C onglet", flush=True)
    tab.set_items(
        [
            {"id": 1, "reference": "Slide texte", "text": "Bonjour", "source": "custom"},
            {
                "id": 2,
                "reference": "Photo",
                "text": "",
                "source": "media",
                "background": "C:/photos/p1.png",
            },
            {
                "id": 3,
                "reference": "Clip",
                "text": "",
                "source": "media",
                "background": "C:/videos/c1.mp4",
            },
        ]
    )
    print("D items", flush=True)
    entries = tab.media_entries()
    print("E entries", entries, flush=True)
    sys.stdout.flush()
    assert entries == [
        {"name": "Photo", "path": "C:/photos/p1.png"},
        {"name": "Clip", "path": "C:/videos/c1.mp4"},
    ]
    print("F fin", flush=True)


def test_slideshow_entries_enriched_from_library(tmp_path: Path, monkeypatch) -> None:
    """Depuis une playlist : type et durée retrouvés dans la bibliothèque."""
    from app.utils import library_controller as library_module
    from app.utils.library_controller import LibraryController
    from tests.test_playlist_tab import _QuietStubTab

    app = _app()  # noqa: F841 - garde la QApplication vivante

    class _ImmediatePool:
        """Exécute les workers dans le thread courant (callbacks synchrones)."""

        def start(self, runnable, *_args, **_kwargs) -> None:
            runnable.run()

    monkeypatch.setattr(
        library_module.QThreadPool,
        "globalInstance",
        staticmethod(lambda: _ImmediatePool()),
    )

    db = Database(DatabaseConfig(db_path=tmp_path / "lib.db"))
    db.initialize()
    controller = ProjectOnController(db=db, presentation_dir=tmp_path / "pres")
    dao = MediaDao(db)
    media_id = dao.add_media("Photo", _photo(tmp_path, "lib"), "image")
    dao.set_duration(media_id, 6)

    library = LibraryController(
        db=db,
        project_controller=controller,
        bible_tab=_QuietStubTab(),
        hymns_tab=_QuietStubTab(),
        sermons_tab=_QuietStubTab(),
        expose_tab=None,
        playlist_tab=None,
        media_tab=None,
    )
    entries = library.slideshow_entries([{"name": "Photo", "path": _photo(tmp_path, "lib")}])
    assert entries == [
        {
            "name": "Photo",
            "path": _photo(tmp_path, "lib"),
            "kind": "image",
            "duration_seconds": 6,
        }
    ]
    # Un chemin inconnu de la bibliothèque reste projetable (type déduit).
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\x00")
    assert library.slideshow_entries([{"path": str(clip)}]) == [
        {"name": "", "path": str(clip), "kind": "video", "duration_seconds": 0}
    ]
