"""Tests unitaires pour app/database/dao_playlist.py"""

from __future__ import annotations

import pytest
from app.database.connection import Database
from app.database.dao_playlist import PlaylistDao


@pytest.fixture
def dao(db: Database) -> PlaylistDao:
    return PlaylistDao(db)


class TestFolderCRUD:
    def test_create_folder_returns_id(self, dao: PlaylistDao):
        folder_id = dao.create_folder("Service du dimanche")
        assert isinstance(folder_id, int)
        assert folder_id > 0

    def test_list_folders_initially_empty(self, dao: PlaylistDao):
        folders = dao.list_folders()
        assert folders == []

    def test_list_folders_after_create(self, dao: PlaylistDao):
        dao.create_folder("Louange")
        folders = dao.list_folders()
        assert len(folders) == 1
        assert folders[0]["name"] == "Louange"

    def test_get_folder_by_id(self, dao: PlaylistDao):
        folder_id = dao.create_folder("Intercession")
        folder = dao.get_folder(folder_id)
        assert folder is not None
        assert folder["name"] == "Intercession"

    def test_get_nonexistent_folder_returns_none(self, dao: PlaylistDao):
        assert dao.get_folder(99999) is None

    def test_rename_folder(self, dao: PlaylistDao):
        folder_id = dao.create_folder("Ancien nom")
        ok = dao.rename_folder(folder_id, "Nouveau nom")
        assert ok is True
        folder = dao.get_folder(folder_id)
        assert folder["name"] == "Nouveau nom"

    def test_delete_folder(self, dao: PlaylistDao):
        folder_id = dao.create_folder("À supprimer")
        ok = dao.delete_folder(folder_id)
        assert ok is True
        assert dao.get_folder(folder_id) is None

    def test_delete_nonexistent_returns_false(self, dao: PlaylistDao):
        assert dao.delete_folder(99999) is False

    def test_multiple_folders_ordered(self, dao: PlaylistDao):
        dao.create_folder("Premier")
        dao.create_folder("Deuxième")
        dao.create_folder("Troisième")
        folders = dao.list_folders()
        assert len(folders) == 3
        names = [f["name"] for f in folders]
        assert names == ["Premier", "Deuxième", "Troisième"]


class TestItemCRUD:
    def test_add_items_to_root(self, dao: PlaylistDao):
        ids = dao.add_items([("hymn", "Cantique 1", "Je veux chanter")], None)
        assert len(ids) == 1
        assert ids[0] > 0

    def test_list_root_items(self, dao: PlaylistDao):
        dao.add_items([("bible", "Jean 3:16", "Car Dieu a tant aimé le monde")], None)
        items = dao.list_items(folder_id=None)
        assert len(items) == 1
        assert items[0]["reference"] == "Jean 3:16"

    def test_add_items_to_folder(self, dao: PlaylistDao):
        folder_id = dao.create_folder("Service")
        dao.add_items([("sermon", "Para 1", "La foi est...")], folder_id)
        items = dao.list_items(folder_id=folder_id)
        assert len(items) == 1
        assert items[0]["source"] == "sermon"

    def test_delete_item(self, dao: PlaylistDao):
        ids = dao.add_items([("custom", "Titre", "Texte personnalisé")], None)
        item_id = ids[0]
        ok = dao.delete_item(item_id)
        assert ok is True
        items = dao.list_items(folder_id=None)
        assert all(i["id"] != item_id for i in items)

    def test_delete_folder_cascades_items(self, dao: PlaylistDao):
        folder_id = dao.create_folder("Dossier avec items")
        dao.add_items([("bible", "Ps 23:1", "L'Éternel est mon berger")], folder_id)
        dao.delete_folder(folder_id)
        items = dao.list_items(folder_id=folder_id)
        assert items == []
