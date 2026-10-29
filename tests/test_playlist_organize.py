"""Playlist : réordonner, supprimer, dupliquer, copier / déplacer et annuler."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.database.connection import Database, DatabaseConfig
from app.database.dao_playlist import PlaylistDao
from app.ui.playlist_tab import PlaylistTab
from app.utils.library_controller import LibraryController


def _dao(tmp_path: Path) -> PlaylistDao:
    db = Database(DatabaseConfig(db_path=tmp_path / "t.db"))
    db.initialize()
    return PlaylistDao(db=db)


def _refs(dao: PlaylistDao, folder: int) -> list[str]:
    return [it["reference"] for it in dao.list_items(folder)]


def _fill(dao: PlaylistDao, folder: int, refs: str) -> list[int]:
    return dao.add_items([("custom", r, f"texte {r}") for r in refs], folder_id=folder)


def test_dao_reorder_delete_duplicate(tmp_path: Path) -> None:
    dao = _dao(tmp_path)
    folder = dao.create_folder("Culte")
    a, b, c, d = _fill(dao, folder, "ABCD")
    assert dao.reorder_items(folder, [c, a, d, b])
    assert _refs(dao, folder) == list("CADB")
    assert not dao.reorder_items(folder, [c, a])  # ordre incomplet refusé
    copies = dao.duplicate_items([a, b])
    assert _refs(dao, folder) == list("CAADBB")  # chaque copie suit l'original
    assert len(copies) == 2
    assert dao.delete_items([c, *copies]) == 3
    assert _refs(dao, folder) == list("ADB")


def test_dao_copy_and_move_to_another_playlist(tmp_path: Path) -> None:
    dao = _dao(tmp_path)
    first, second = dao.create_folder("Un"), dao.create_folder("Deux")
    a, b, c = _fill(dao, first, "ABC")
    _fill(dao, second, "X")
    dao.copy_items([c, a], second)
    assert _refs(dao, second) == list("XAC")  # ordre de la playlist d'origine
    assert _refs(dao, first) == list("ABC")
    dao.move_items_to_folder([b], second)
    assert _refs(dao, first) == list("AC")
    assert _refs(dao, second) == list("XACB")


def test_dao_restore_brings_back_the_same_ids(tmp_path: Path) -> None:
    dao = _dao(tmp_path)
    folder = dao.create_folder("Culte")
    ids = _fill(dao, folder, "ABC")
    snapshot = dao.snapshot_folders([folder])
    dao.delete_items(ids[:2])
    assert dao.restore_folders(snapshot)
    assert [it["id"] for it in dao.list_items(folder)] == ids
    dao.delete_folder(folder)
    assert not dao.restore_folders(snapshot)  # playlist supprimée : refus


def _controller(tmp_path: Path):
    QApplication.instance() or QApplication([])
    dao = _dao(tmp_path)
    controller = LibraryController.__new__(LibraryController)
    controller._playlist_dao = dao
    controller._playlist_tab = PlaylistTab()
    controller.refresh_playlists = lambda **_k: None

    def refresh(select_ids=None):
        items = dao.list_items(controller._current_playlist_folder_id)
        controller._playlist_tab.set_items(items, select_ids=select_ids)
        controller._playlist_tab.set_undo_available(bool(controller._undo_stack))

    controller._refresh_playlist_items = refresh
    return controller, dao


def test_every_change_can_be_undone_in_order(tmp_path: Path) -> None:
    controller, dao = _controller(tmp_path)
    folder, other = dao.create_folder("Culte"), dao.create_folder("Jeunesse")
    controller._current_playlist_folder_id = folder
    controller._commit_to_playlist(folder, "", [("A", "a"), ("B", "b"), ("C", "c")], "bible")
    a, b, c = (it["id"] for it in dao.list_items(folder))

    controller.on_playlist_items_reordered([c, b, a])
    controller.on_playlist_items_duplicate([b])
    controller.on_playlist_items_move_to_folder([a], other)
    controller.on_playlist_items_delete([c])
    assert _refs(dao, folder) == ["B", "B"]
    assert _refs(dao, other) == ["A"]
    assert controller._playlist_tab.undo_btn.isEnabled()

    controller.on_playlist_undo()  # suppression
    assert _refs(dao, folder) == ["C", "B", "B"]
    controller.on_playlist_undo()  # déplacement vers « Jeunesse »
    assert _refs(dao, folder) == ["C", "B", "B", "A"]
    assert _refs(dao, other) == []
    controller.on_playlist_undo()  # duplication
    controller.on_playlist_undo()  # réordonnancement
    assert _refs(dao, folder) == ["A", "B", "C"]
    assert [it["id"] for it in dao.list_items(folder)] == [a, b, c]
    controller.on_playlist_undo()  # ajout depuis la Bible
    assert _refs(dao, folder) == []
    controller.on_playlist_undo()  # plus rien : sans effet
    assert not controller._playlist_tab.undo_btn.isEnabled()


def test_deleting_a_playlist_drops_its_undo_steps(tmp_path: Path) -> None:
    controller, dao = _controller(tmp_path)
    folder = dao.create_folder("Culte")
    controller._current_playlist_folder_id = folder
    controller._commit_to_playlist(folder, "", [("A", "a")])
    controller.on_playlist_folder_delete(folder)
    assert controller._undo_stack == []


def test_tab_moves_the_whole_selection_and_reports_drag_order() -> None:
    app = QApplication.instance() or QApplication([])
    tab = PlaylistTab()
    tab.set_items([{"id": i, "reference": r, "text": ""} for i, r in enumerate("ABCDE", 1)],
                  select_ids=[2, 4])
    assert tab.selected_item_ids() == [2, 4]
    orders = []
    tab.itemsReordered.connect(orders.append)
    tab._move_selected(-1)
    assert orders[-1] == [2, 1, 4, 3, 5]
    tab._move_selected(1)
    assert orders[-1] == [1, 3, 2, 5, 4]

    # Glisser-déposer : la liste est déjà réordonnée par Qt, l'ordre final
    # part une seule fois.
    orders.clear()
    tab.items_list.model().moveRows(tab.items_list.rootIndex(), 4, 1,
                                    tab.items_list.rootIndex(), 0)
    tab._on_rows_moved()
    for _ in range(5):
        app.processEvents()
    assert orders == [[5, 1, 2, 3, 4]]


def test_delete_key_removes_every_selected_item(monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    tab = PlaylistTab()
    tab.set_items([{"id": i, "reference": r, "text": ""} for i, r in enumerate("ABC", 1)],
                  select_ids=[1, 3])
    monkeypatch.setattr(tab, "_confirm_delete", lambda _message: True)
    deleted = []
    tab.itemsDeleteRequested.connect(deleted.append)
    tab._on_delete_item_clicked()
    assert deleted == [[1, 3]]


SECTIONS = [
    {"id": 10, "name": "Louange", "duration_min": 15, "item_id": 1},
    {"id": 11, "name": "Prédication", "duration_min": 40, "item_id": 4},
    {"id": 12, "name": "Annonces", "duration_min": 5, "item_id": None},  # sans slide
]


def _sectioned_tab() -> PlaylistTab:
    QApplication.instance() or QApplication([])
    tab = PlaylistTab()
    tab.set_items([{"id": i, "reference": r, "text": ""} for i, r in enumerate("ABCDE", 1)])
    tab.set_sections(SECTIONS)
    return tab


def _rows(tab: PlaylistTab) -> list[str]:
    from app.ui.playlist_tab import ROLE_REF, ROLE_SECTION

    out = []
    for row in range(tab.items_list.count()):
        item = tab.items_list.item(row)
        section = item.data(ROLE_SECTION)
        label = f"[{section['name']} {section['count']}]" if section else item.data(ROLE_REF)
        out.append(label + (" (masqué)" if item.isHidden() else ""))
    return out


def test_sections_become_headers_above_their_first_slide() -> None:
    tab = _sectioned_tab()
    assert _rows(tab) == ["[Louange 3]", "A", "B", "C", "[Prédication 2]", "D", "E"]
    assert tab.item_ids() == [1, 2, 3, 4, 5]  # les en-têtes ne comptent pas
    assert tab.items_list.currentItem().data(256) == 1  # jamais un en-tête


def test_clicking_a_header_folds_its_section() -> None:
    from app.ui.playlist_tab import ROLE_SECTION

    tab = _sectioned_tab()
    header = tab.items_list.item(0)
    tab._on_item_clicked(header)
    assert _rows(tab)[:4] == ["[Louange 3]", "A (masqué)", "B (masqué)", "C (masqué)"]
    assert header.data(ROLE_SECTION)["collapsed"]
    # Le repli survit à un rechargement (nouvel ordre, autre sélection…).
    tab.set_items([{"id": i, "reference": r, "text": ""} for i, r in enumerate("ABCDE", 1)])
    assert _rows(tab)[1] == "A (masqué)"
    tab._on_item_clicked(tab.items_list.item(0))
    assert "masqué" not in " ".join(_rows(tab))


def test_section_signals_and_safe_actions_on_headers() -> None:
    tab = _sectioned_tab()
    tab.items_list.setCurrentRow(0)  # en-tête courant
    edits = []
    tab.itemUpdateRequested.connect(lambda *a: edits.append(a))
    tab._on_edit_item_clicked()
    assert edits == []
    assert tab.selected_item_id() is None
    assert tab.media_entries() == []


def test_service_plan_panel_publishes_and_links_sections(tmp_path) -> None:
    from app.database.dao_service_plan import ServicePlanDao
    from app.ui.service_plan_panel import ServicePlanPanel

    QApplication.instance() or QApplication([])
    db = Database(DatabaseConfig(db_path=tmp_path / "t.db"))
    db.initialize()
    dao = PlaylistDao(db=db)
    folder = dao.create_folder("Culte")
    _a, b = _fill(dao, folder, "AB")
    plan = ServicePlanDao(db)
    section = plan.add_section(folder, "Louange", 10)
    panel = ServicePlanPanel(plan)
    published = []
    panel.sectionsChanged.connect(published.append)
    panel.set_folder(folder)
    assert published[-1][0]["item_id"] is None
    panel.start_section_at(section, b)
    assert published[-1][0]["item_id"] == b
    panel.detach_section(section)
    assert published[-1][0]["item_id"] is None
