from __future__ import annotations

from PyQt6.QtCore import QModelIndex, Qt
from PyQt6.QtGui import QStandardItem, QStandardItemModel

from app.utils.models import Slide


class PlaylistRoles:
    ReferenceRole = Qt.ItemDataRole.UserRole + 1
    TextRole = Qt.ItemDataRole.UserRole + 2
    SourceRole = Qt.ItemDataRole.UserRole + 3
    IsFolderRole = Qt.ItemDataRole.UserRole + 4
    SlideDataRole = Qt.ItemDataRole.UserRole + 5
    FolderIdRole = Qt.ItemDataRole.UserRole + 6
    ItemIdRole = Qt.ItemDataRole.UserRole + 7


class PlaylistItem(QStandardItem):
    """Item représentant soit un dossier soit un slide dans la playlist."""

    def __init__(
        self,
        text: str = "",
        is_folder: bool = False,
        slide: Slide | None = None,
        folder_id: int | None = None,
        item_id: int | None = None,
    ) -> None:
        super().__init__(text)
        self._is_folder = is_folder
        self._slide = slide
        self._folder_id = folder_id
        self._item_id = item_id
        self.setEditable(False)
        if is_folder:
            self.setData(True, PlaylistRoles.IsFolderRole)
            if folder_id is not None:
                self.setData(folder_id, PlaylistRoles.FolderIdRole)
        else:
            self.setData(False, PlaylistRoles.IsFolderRole)
            if item_id is not None:
                self.setData(item_id, PlaylistRoles.ItemIdRole)
            if slide:
                self.setData(slide, PlaylistRoles.SlideDataRole)
                self.setData(slide.reference, PlaylistRoles.ReferenceRole)
                self.setData(slide.text, PlaylistRoles.TextRole)
                self.setData(slide.source, PlaylistRoles.SourceRole)

    @property
    def is_folder(self) -> bool:
        return self._is_folder

    @property
    def slide(self) -> Slide | None:
        return self._slide

    @property
    def folder_id(self) -> int | None:
        return self._folder_id

    @property
    def item_id(self) -> int | None:
        return self._item_id


class PlaylistModel(QStandardItemModel):
    def __init__(self) -> None:
        super().__init__()
        self._flat_slides: list[tuple[QModelIndex, Slide]] = []
        self._dirty = True
        # Mark dirty on any structural change (needed for DnD moves)
        self.rowsInserted.connect(lambda *_: self._mark_dirty())
        self.rowsRemoved.connect(lambda *_: self._mark_dirty())
        self.rowsMoved.connect(lambda *_: self._mark_dirty())

    def supportedDropActions(self) -> Qt.DropAction:
        return Qt.DropAction.MoveAction

    def supportedDragActions(self) -> Qt.DropAction:
        return Qt.DropAction.MoveAction

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        default = super().flags(index)
        if not index.isValid():
            return default | Qt.ItemFlag.ItemIsDropEnabled
        item = self.itemFromIndex(index)
        if isinstance(item, PlaylistItem) and item.is_folder:
            return (
                default | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled
            )
        return default | Qt.ItemFlag.ItemIsDragEnabled

    def _rebuild_flat_list(self) -> None:
        """Reconstruit la liste plate des slides pour la navigation."""
        if not self._dirty:
            return
        self._flat_slides.clear()
        self._collect_slides(self.invisibleRootItem())
        self._dirty = False

    def _mark_dirty(self) -> None:
        self._dirty = True

    def _collect_slides(self, parent_item: QStandardItem) -> None:
        """Collecte récursivement tous les slides."""
        for row in range(parent_item.rowCount()):
            item = parent_item.child(row)
            if item is None:
                continue
            if isinstance(item, PlaylistItem):
                if item.is_folder:
                    self._collect_slides(item)
                elif item.slide is not None:
                    self._flat_slides.append((item.index(), item.slide))
            else:
                slide = item.data(PlaylistRoles.SlideDataRole)
                if slide is not None:
                    self._flat_slides.append((item.index(), slide))

    def add_folder(
        self, name: str, parent: QModelIndex | None = None, folder_id: int | None = None
    ) -> QModelIndex:
        """Ajoute un nouveau dossier."""
        folder_item = PlaylistItem(name, is_folder=True, folder_id=folder_id)
        if parent is not None and parent.isValid():
            parent_item = self.itemFromIndex(parent)
            if parent_item is not None:
                parent_item.appendRow(folder_item)
            else:
                self.appendRow(folder_item)
        else:
            self.appendRow(folder_item)
        return folder_item.index()

    def get_folder_id(self, index: QModelIndex) -> int | None:
        """Retourne l'ID du dossier pour un index donné."""
        if not index.isValid():
            return None
        item = self.itemFromIndex(index)
        if isinstance(item, PlaylistItem) and item.is_folder:
            return item.folder_id
        return None

    def add_slide(
        self,
        slide: Slide,
        parent: QModelIndex | None = None,
        item_id: int | None = None,
    ) -> int:
        """Ajoute un slide, optionnellement dans un dossier."""
        display_text = f"{slide.reference}\n{slide.text}"
        slide_item = PlaylistItem(
            display_text, is_folder=False, slide=slide, item_id=item_id
        )

        if parent is not None and parent.isValid():
            parent_item = self.itemFromIndex(parent)
            if (
                parent_item is not None
                and isinstance(parent_item, PlaylistItem)
                and parent_item.is_folder
            ):
                parent_item.appendRow(slide_item)
            else:
                self.appendRow(slide_item)
        else:
            self.appendRow(slide_item)

        self._mark_dirty()
        return self.flat_row_count() - 1

    def get_item_id(self, index: QModelIndex) -> int | None:
        """Retourne l'ID de l'item pour un index donné."""
        if not index.isValid():
            return None
        item = self.itemFromIndex(index)
        if isinstance(item, PlaylistItem) and not item.is_folder:
            return item.item_id
        return None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        """Retourne le nombre de lignes pour un parent donné."""
        return super().rowCount(parent)

    def flat_row_count(self) -> int:
        """Retourne le nombre total de slides (sans les dossiers)."""
        self._rebuild_flat_list()
        return len(self._flat_slides)

    def slide_at(self, flat_row: int) -> Slide | None:
        """Retourne le slide à l'index plat donné."""
        self._rebuild_flat_list()
        if flat_row < 0 or flat_row >= len(self._flat_slides):
            return None
        return self._flat_slides[flat_row][1]

    def index_at_flat_row(self, flat_row: int) -> QModelIndex:
        """Retourne l'index du modèle pour un index plat donné."""
        self._rebuild_flat_list()
        if flat_row < 0 or flat_row >= len(self._flat_slides):
            return QModelIndex()
        return self._flat_slides[flat_row][0]

    def flat_row_from_index(self, index: QModelIndex) -> int:
        """Retourne l'index plat pour un index de modèle donné."""
        self._rebuild_flat_list()
        for i, (idx, _) in enumerate(self._flat_slides):
            if idx == index:
                return i
        return -1

    def clear(self) -> None:
        """Vide la playlist."""
        self.removeRows(0, self.rowCount())
        self._flat_slides.clear()
        self._dirty = False

    def remove_row(self, flat_row: int) -> bool:
        """Supprime un slide par son index plat."""
        self._rebuild_flat_list()
        if flat_row < 0 or flat_row >= len(self._flat_slides):
            return False
        index = self._flat_slides[flat_row][0]
        if not index.isValid():
            return False
        parent = index.parent()
        self.removeRow(index.row(), parent)
        self._mark_dirty()
        return True

    def remove_index(self, index: QModelIndex) -> bool:
        """Supprime un item (slide ou dossier) par son index."""
        if not index.isValid():
            return False
        parent = index.parent()
        self.removeRow(index.row(), parent)
        self._mark_dirty()
        return True

    def get_folders(self) -> list[tuple[str, QModelIndex]]:
        """Retourne la liste des dossiers (nom, index)."""
        folders: list[tuple[str, QModelIndex]] = []
        self._collect_folders(self.invisibleRootItem(), folders)
        return folders

    def _collect_folders(
        self, parent_item: QStandardItem, folders: list[tuple[str, QModelIndex]]
    ) -> None:
        """Collecte récursivement tous les dossiers."""
        for row in range(parent_item.rowCount()):
            item = parent_item.child(row)
            if item is None:
                continue
            if isinstance(item, PlaylistItem) and item.is_folder:
                folders.append((item.text(), item.index()))
                self._collect_folders(item, folders)

    def update_slide_data(self, index: QModelIndex, new_slide: Slide) -> bool:
        """Update the slide stored in an item (e.g. after changing background)."""
        if not index.isValid():
            return False
        item = self.itemFromIndex(index)
        if not isinstance(item, PlaylistItem) or item.is_folder:
            return False
        item._slide = new_slide
        item.setText(f"{new_slide.reference}\n{new_slide.text}")
        item.setData(new_slide, PlaylistRoles.SlideDataRole)
        item.setData(new_slide.reference, PlaylistRoles.ReferenceRole)
        item.setData(new_slide.text, PlaylistRoles.TextRole)
        item.setData(new_slide.source, PlaylistRoles.SourceRole)
        self._mark_dirty()
        return True

    def is_folder(self, index: QModelIndex) -> bool:
        """Vérifie si l'index correspond à un dossier."""
        if not index.isValid():
            return False
        item = self.itemFromIndex(index)
        if isinstance(item, PlaylistItem):
            return item.is_folder
        return item.data(PlaylistRoles.IsFolderRole)
