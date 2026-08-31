"""Onglet Playlists : UI (offscreen) et intégration LibraryController."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402

from app.database.dao_playlist import PlaylistDao  # noqa: E402


# ── UI : PlaylistTab ─────────────────────────────────────────────────────────

def _make_tab():
    from PyQt6.QtWidgets import QApplication

    from app.ui.playlist_tab import PlaylistTab

    app = QApplication.instance() or QApplication([])
    return app, PlaylistTab()


def test_set_folders_keeps_selection_and_selects_fallback():
    _app, tab = _make_tab()
    received: list[object] = []
    tab.folderSelected.connect(received.append)

    tab.set_folders([{"id": 7, "name": "Culte"}, {"id": 9, "name": "Louange"}])
    assert tab.current_folder_id() == 7
    assert received == [7]

    # Rechargement : la sélection 7 est conservée, pas de signal parasite.
    received.clear()
    tab.set_folders([{"id": 7, "name": "Culte"}, {"id": 9, "name": "Louange"}])
    assert tab.current_folder_id() == 7
    assert received == []

    # Le dossier disparaît → repli sur le premier.
    tab.set_folders([{"id": 9, "name": "Louange"}])
    assert tab.current_folder_id() == 9


def test_set_items_fills_list_and_preview():
    _app, tab = _make_tab()
    tab.set_items(
        [
            {"id": 1, "reference": "Jean 3:16", "text": "Car Dieu a tant aimé…"},
            {"id": 2, "reference": "Annonce", "text": "Repas de midi"},
        ]
    )
    assert tab.items_list.count() == 2
    assert tab.info_label.text() == "2 slide(s)"
    assert tab.selected_item_id() == 1
    assert "Jean 3:16" in tab.preview.toPlainText()


def test_play_signals_payload():
    _app, tab = _make_tab()
    tab.set_items([{"id": 4, "reference": "R", "text": "T"}])
    activated: list[int] = []
    play: list[object] = []
    tab.itemActivated.connect(activated.append)
    tab.playRequested.connect(play.append)

    tab._on_item_double_clicked(tab.items_list.item(0))
    assert activated == [4]

    tab.play_btn.click()
    assert play == [4]

    # Sans sélection → None (début de playlist).
    tab.items_list.clear()
    tab.play_btn.click()
    assert play == [4, None]


# ── Intégration : LibraryController + DAO + projection ──────────────────────

def _make_controller(tmp_path: Path):
    from PyQt6.QtCore import QObject, pyqtSignal
    from PyQt6.QtWidgets import QApplication

    from app.database.connection import Database, DatabaseConfig
    from app.ui.playlist_tab import PlaylistTab
    from app.utils.library_controller import LibraryController
    from app.utils.project_on_controller import ProjectOnController

    class _StubTab(QObject):
        """Onglet minimal : les signaux câblés par _wire + no-op pour le reste."""

        translationSelected = pyqtSignal(int)
        bookSelected = pyqtSignal(int)
        chapterSelected = pyqtSignal(int)
        verseActivated = pyqtSignal(str, str)
        versesActivated = pyqtSignal(list)
        hymnSelected = pyqtSignal(int)
        stanzaActivated = pyqtSignal(str, str)
        stanzasActivated = pyqtSignal(list)
        hymnActivated = pyqtSignal(int)
        importScanRequested = pyqtSignal()
        importPdfFileRequested = pyqtSignal()
        importPptxFileRequested = pyqtSignal()
        importPptxFolderRequested = pyqtSignal()
        deleteRequested = pyqtSignal(int)
        deleteAllRequested = pyqtSignal()
        clearAllHymnsRequested = pyqtSignal()
        sermonSelected = pyqtSignal(int)
        paragraphActivated = pyqtSignal(dict)
        filtersChanged = pyqtSignal()
        paragraphSearchRequested = pyqtSignal(str)
        addToPlaylistRequested = pyqtSignal(list)

        def __getattr__(self, name):
            if name.startswith("__") or name in type(self).__dict__:
                raise AttributeError(name)
            def _noop(*_args, **_kwargs) -> None:
                pass
            return _noop

    app = QApplication.instance() or QApplication([])
    db = Database(DatabaseConfig(db_path=tmp_path / "test.db"))
    db.initialize()

    project = ProjectOnController(db=db, presentation_dir=tmp_path / "pres")
    controller = LibraryController(
        db=db,
        project_controller=project,
        bible_tab=_StubTab(),
        hymns_tab=_StubTab(),
        sermons_tab=_StubTab(),
        expose_tab=None,
        playlist_tab=PlaylistTab(),
    )

    class _ImmediatePool:
        """Exécute les workers dans le thread courant : callbacks synchrone."""

        def start(self, runnable, *_args, **_kwargs) -> None:
            runnable.run()

    controller._pool = _ImmediatePool()

    slide_path = tmp_path / "pres" / "slide.json"
    return app, controller, project, controller._playlist_tab, slide_path


def test_playlist_end_to_end(tmp_path: Path) -> None:
    app, controller, project, tab, slide_path = _make_controller(tmp_path)
    dao = PlaylistDao(db=controller._db)

    controller.on_playlist_folder_create("Culte du dimanche")
    folders = dao.list_folders()
    assert len(folders) == 1
    folder_id = int(folders[0]["id"])
    controller._current_playlist_folder_id = folder_id

    controller.on_playlist_item_create(folder_id, "Jean 3:16", "Car Dieu a tant aimé le monde…")
    controller.on_playlist_item_create(folder_id, "Annonce", "Repas partagé après le culte")
    items = dao.list_items(folder_id)
    assert [it["reference"] for it in items] == ["Jean 3:16", "Annonce"]

    # Déplacement : l'item 2 remonte d'un cran.
    controller.on_playlist_item_move(int(items[1]["id"]), -1)
    items = dao.list_items(folder_id)
    assert [it["reference"] for it in items] == ["Annonce", "Jean 3:16"]

    # Projection depuis l'item « Annonce » (déplacé en tête).
    controller.on_playlist_play(int(items[0]["id"]))
    payload = json.loads(slide_path.read_text(encoding="utf-8"))
    assert payload["source"] == "custom"
    assert payload["reference"] == "Annonce"
    assert payload["hidden"] is False

    # Le programme live suit : titre = nom du dossier, 2 entrées projetables.
    assert project.program_title == "Culte du dimanche"
    assert project.program_count == 2

    # Mise à jour puis suppression d'un slide.
    controller.on_playlist_item_update(int(items[1]["id"]), "Jean 3:16", "Texte corrigé")
    assert dao.list_items(folder_id)[1]["text"] == "Texte corrigé"
    controller.on_playlist_item_delete(int(items[0]["id"]))
    assert len(dao.list_items(folder_id)) == 1

    # Renommage puis suppression du dossier (les slides partent en cascade).
    controller.on_playlist_folder_rename(folder_id, "Culte spécial")
    assert dao.get_folder(folder_id)["name"] == "Culte spécial"
    controller.on_playlist_folder_delete(folder_id)
    assert dao.list_folders() == []
    assert dao.list_items(folder_id) == []
    app.processEvents()


class _QuietStubTab(QObject):
    """Onglet minimal : les signaux câblés par _wire + affichages no-op."""

    translationSelected = pyqtSignal(int)
    bookSelected = pyqtSignal(int)
    chapterSelected = pyqtSignal(int)
    verseActivated = pyqtSignal(str, str)
    versesActivated = pyqtSignal(list)
    hymnSelected = pyqtSignal(int)
    stanzaActivated = pyqtSignal(str, str)
    stanzasActivated = pyqtSignal(list)
    hymnActivated = pyqtSignal(int)
    importScanRequested = pyqtSignal()
    importPdfFileRequested = pyqtSignal()
    importPptxFileRequested = pyqtSignal()
    importPptxFolderRequested = pyqtSignal()
    deleteRequested = pyqtSignal(int)
    deleteAllRequested = pyqtSignal()
    clearAllHymnsRequested = pyqtSignal()
    sermonSelected = pyqtSignal(int)
    paragraphActivated = pyqtSignal(dict)
    filtersChanged = pyqtSignal()
    paragraphSearchRequested = pyqtSignal(str)

    def set_books(self, *_a) -> None:
        pass

    def set_chapters(self, *_a) -> None:
        pass

    def set_verses(self, *_a) -> None:
        pass

    def set_hymns(self, *_a) -> None:
        pass

    def set_stanzas(self, *_a) -> None:
        pass

    def set_sermons(self, *_a) -> None:
        pass

    def set_paragraphs(self, *_a) -> None:
        pass
