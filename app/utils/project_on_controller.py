from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QModelIndex, QObject, pyqtSignal
from PyQt6.QtGui import QStandardItem

from app.database.connection import Database
from app.database.dao_playlist import PlaylistDao
from app.utils.models import Slide, SourceType
from app.utils.playlist_model import PlaylistModel, PlaylistRoles
from app.utils.slide_writer import SlideWriter
from app.utils.text_utils import strip_hymn_projection_label


class ProjectOnController(QObject):
    currentSlideChanged = pyqtSignal(object)
    currentRowChanged = pyqtSignal(int)

    _MAX_CHARS_PER_SLIDE = 280
    _OPTIMAL_CHARS = 200
    _MIN_CHARS = 60

    def __init__(self, db: Database, presentation_dir: Path) -> None:
        super().__init__()
        self._db = db
        self._playlist_dao = PlaylistDao(db)
        self._playlist = PlaylistModel()
        self._slide_writer = SlideWriter(presentation_dir=presentation_dir)
        self._current_row = -1
        self._folder_index_map: dict[int, QModelIndex] = {}
        self._item_id_map: dict[int, QModelIndex] = {}
        self._undo_stack: list[dict] = []  # max 20 entries
        self._MAX_UNDO = 20
        self._load_playlist()

        # Connect model changes to persistence
        self._playlist.rowsInserted.connect(self._on_playlist_structure_changed)
        self._playlist.rowsRemoved.connect(self._on_playlist_structure_changed)
        self._playlist.rowsMoved.connect(self._on_playlist_structure_changed)

    @property
    def db(self) -> Database:
        return self._db

    @property
    def playlist_model(self) -> PlaylistModel:
        return self._playlist

    @property
    def slide_writer(self) -> SlideWriter:
        return self._slide_writer

    def add_to_playlist(
        self,
        source: SourceType,
        reference: str,
        text: str,
        parent: QModelIndex | None = None,
    ) -> int:
        return self.add_many_to_playlist(source, [(reference, text)], parent)

    def add_many_to_playlist(
        self,
        source: SourceType,
        entries: list[tuple[str, str]],
        parent: QModelIndex | None = None,
        split: bool = True,
    ) -> int:
        folder_id: int | None = None
        if parent is not None and parent.isValid():
            folder_id = self._playlist.get_folder_id(parent)

        prepared: list[tuple[str, str]] = []
        for reference, text in entries:
            ref_clean = self._clean_text(reference)
            text_clean = self._clean_text(text)
            if source == "hymn":
                text_clean = strip_hymn_projection_label(text_clean)

            if split:
                chunks = self._split_text(text_clean)
            else:
                chunks = [text_clean] if text_clean else []
            total = len(chunks)
            for i, chunk in enumerate(chunks, start=1):
                ref = ref_clean
                if total > 1:
                    ref = f"{ref_clean} ({i}/{total})"
                chunk_clean = self._clean_text(chunk)
                if chunk_clean:
                    prepared.append((ref, chunk_clean))

        if not prepared:
            return -1

        item_ids = self._playlist_dao.add_items(
            [(source, ref, chunk_clean) for ref, chunk_clean in prepared],
            folder_id,
        )

        first_row = -1
        added_ids: list[int] = []
        for item_id, (ref, chunk_clean) in zip(item_ids, prepared, strict=False):
            slide = Slide(source=source, reference=ref, text=chunk_clean)
            row = self._playlist.add_slide(slide, parent, item_id)
            if item_id:
                added_ids.append(item_id)
                idx = self._playlist.index_at_flat_row(row)
                if idx.isValid():
                    self._item_id_map[item_id] = idx
            if first_row == -1:
                first_row = row

        # Push undo entry for the add action
        if added_ids:
            self._push_undo({"action": "add", "item_ids": added_ids})

        if self._current_row == -1 and first_row != -1:
            self.set_current_row(first_row)
        return first_row

    @staticmethod
    def _clean_text(value: object) -> str:
        from app.utils.text_utils import clean_text

        return clean_text(value)

    def _split_text(self, text: str) -> list[str]:
        """Split text into balanced, readable slides (see text_utils)."""
        from app.utils.text_utils import split_text_into_slides

        return split_text_into_slides(text, self._MAX_CHARS_PER_SLIDE, self._MIN_CHARS)

    def set_current_row(self, row: int) -> None:
        flat_count = self._playlist.flat_row_count()
        if flat_count == 0:
            self._current_row = -1
            return
        row = max(0, min(int(row), flat_count - 1))
        slide = self._playlist.slide_at(row)
        if slide is None:
            self._current_row = -1
            return
        self._current_row = row

        presentation_slide = slide
        if slide.source == "hymn" and " - " in slide.reference:
            from app.utils.models import Slide

            presentation_slide = Slide(
                source=slide.source,
                reference=slide.reference.replace(" - ", "\n", 1),
                text=strip_hymn_projection_label(slide.text),
                background=slide.background,
                image_path=slide.image_path,
            )
        elif slide.source == "hymn":
            from app.utils.models import Slide

            presentation_slide = Slide(
                source=slide.source,
                reference=slide.reference,
                text=strip_hymn_projection_label(slide.text),
                background=slide.background,
                image_path=slide.image_path,
            )

        self._slide_writer.write(presentation_slide)
        self.currentRowChanged.emit(row)
        self.currentSlideChanged.emit(presentation_slide)

    def current_row(self) -> int:
        return self._current_row

    def next_slide(self) -> None:
        if self._playlist.flat_row_count() == 0:
            return
        if self._current_row == -1:
            self.set_current_row(0)
            return

        current_idx = self._playlist.index_at_flat_row(self._current_row)
        if current_idx.isValid():
            current_parent = current_idx.parent()
            if current_parent.isValid():
                next_row = self._current_row + 1
                if next_row < self._playlist.flat_row_count():
                    next_idx = self._playlist.index_at_flat_row(next_row)
                    if next_idx.isValid() and next_idx.parent() == current_parent:
                        self.set_current_row(next_row)
                    return
                else:
                    return

        if self._current_row + 1 < self._playlist.flat_row_count():
            self.set_current_row(self._current_row + 1)

    def peek_next_slide(self) -> Slide | None:
        """Return the slide next_slide() would move to, without changing state.

        Used by the stage display to preview the upcoming slide. Mirrors the
        folder-boundary logic of next_slide().
        """
        flat_count = self._playlist.flat_row_count()
        if flat_count == 0:
            return None
        if self._current_row == -1:
            return self._playlist.slide_at(0)

        current_idx = self._playlist.index_at_flat_row(self._current_row)
        if current_idx.isValid() and current_idx.parent().isValid():
            current_parent = current_idx.parent()
            next_row = self._current_row + 1
            if next_row < flat_count:
                next_idx = self._playlist.index_at_flat_row(next_row)
                if next_idx.isValid() and next_idx.parent() == current_parent:
                    return self._playlist.slide_at(next_row)
            return None

        if self._current_row + 1 < flat_count:
            return self._playlist.slide_at(self._current_row + 1)
        return None

    def prev_slide(self) -> None:
        if self._playlist.flat_row_count() == 0:
            return
        if self._current_row == -1:
            self.set_current_row(0)
            return

        current_idx = self._playlist.index_at_flat_row(self._current_row)
        if current_idx.isValid():
            current_parent = current_idx.parent()
            if current_parent.isValid():
                prev_row = self._current_row - 1
                if prev_row >= 0:
                    prev_idx = self._playlist.index_at_flat_row(prev_row)
                    if prev_idx.isValid() and prev_idx.parent() == current_parent:
                        self.set_current_row(prev_row)
                    return
                else:
                    return

        if self._current_row - 1 >= 0:
            self.set_current_row(self._current_row - 1)

    def clear_playlist(self) -> None:
        # Save snapshot for undo
        snapshot = self._snapshot_playlist()
        if snapshot["items"]:
            self._push_undo({"action": "clear", "snapshot": snapshot})

        self._playlist_dao.clear_all_items()
        self._playlist.clear()
        self._item_id_map.clear()
        self._current_row = -1
        self.currentRowChanged.emit(-1)
        self.currentSlideChanged.emit(None)
        self._load_playlist()

    def _load_playlist(self) -> None:
        """Charge les dossiers et les slides depuis la base de données."""
        self._folder_index_map.clear()
        self._item_id_map.clear()

        folders = self._playlist_dao.list_folders()
        for folder in folders:
            folder_id = int(folder["id"])
            name = str(folder["name"])
            index = self._playlist.add_folder(name, None, folder_id)
            self._folder_index_map[folder_id] = index

        items = self._playlist_dao.list_all_items()
        for item in items:
            item_id = int(item["id"])
            folder_id = item["folder_id"]
            source = str(item["source"])
            reference = str(item["reference"])
            text = str(item["text"])

            parent_index: QModelIndex | None = None
            if folder_id is not None:
                parent_index = self._folder_index_map.get(int(folder_id))

            bg = str(item.get("background") or "")
            if source == "image":
                slide = Slide(
                    source="image",
                    reference=reference,
                    text="",
                    image_path=text,
                    background=bg if bg else None,
                )
            else:
                slide = Slide(
                    source=source,
                    reference=reference,
                    text=text,
                    background=bg if bg else None,
                )
            row = self._playlist.add_slide(slide, parent_index, item_id)
            idx = self._playlist.index_at_flat_row(row)
            if idx.isValid():
                self._item_id_map[item_id] = idx

    def create_folder(
        self, name: str, parent: QModelIndex | None = None
    ) -> QModelIndex:
        """Crée un nouveau dossier dans la playlist et le sauvegarde en base."""
        folder_id = self._playlist_dao.create_folder(name)
        index = self._playlist.add_folder(name, parent, folder_id)
        self._folder_index_map[folder_id] = index
        return index

    def delete_folder(self, index: QModelIndex) -> bool:
        """Supprime un dossier de la playlist et de la base de données."""
        if not index.isValid():
            return False
        folder_id = self._playlist.get_folder_id(index)
        if folder_id is None:
            return False
        if self._playlist_dao.delete_folder(folder_id):
            self._playlist.remove_index(index)
            self._folder_index_map.pop(folder_id, None)
            return True
        return False

    def get_folder_index(self, folder_id: int) -> QModelIndex | None:
        """Retourne l'index du dossier par son ID."""
        return self._folder_index_map.get(folder_id)

    def remove_row(self, row: int) -> None:
        flat_count = self._playlist.flat_row_count()
        if flat_count == 0:
            return

        row = int(row)
        if row < 0 or row >= flat_count:
            return

        was_current = row == self._current_row
        old_current = self._current_row

        removed = self._playlist.remove_row(row)
        if not removed:
            return

        new_flat_count = self._playlist.flat_row_count()
        if new_flat_count == 0:
            self._current_row = -1
            self.currentRowChanged.emit(-1)
            self.currentSlideChanged.emit(None)
            return

        if was_current:
            new_row = row
            if new_row >= new_flat_count:
                new_row = new_flat_count - 1
            self.set_current_row(new_row)
            return

        if old_current != -1 and row < old_current:
            self.set_current_row(old_current - 1)

    def remove_index(self, index: QModelIndex) -> None:
        """Supprime un item (slide ou dossier) par son index de modèle."""
        if not index.isValid():
            return

        # Save undo data before deletion
        item_id = self._playlist.get_item_id(index)
        slide = index.data(PlaylistRoles.SlideDataRole) if item_id else None
        if item_id is not None and slide is not None:
            self._push_undo(
                {
                    "action": "remove",
                    "source": slide.source,
                    "reference": slide.reference,
                    "text": slide.text,
                }
            )
            self._playlist_dao.delete_item(item_id)
            self._item_id_map.pop(item_id, None)
        elif item_id is not None:
            self._playlist_dao.delete_item(item_id)
            self._item_id_map.pop(item_id, None)

        flat_row = self._playlist.flat_row_from_index(index)
        was_current = flat_row == self._current_row
        old_current = self._current_row

        removed = self._playlist.remove_index(index)
        if not removed:
            return

        new_flat_count = self._playlist.flat_row_count()
        if new_flat_count == 0:
            self._current_row = -1
            self.currentRowChanged.emit(-1)
            self.currentSlideChanged.emit(None)
            return

        if was_current and flat_row >= 0:
            new_row = flat_row
            if new_row >= new_flat_count:
                new_row = new_flat_count - 1
            self.set_current_row(new_row)
            return

        if old_current != -1 and flat_row >= 0 and flat_row < old_current:
            self.set_current_row(old_current - 1)

    def add_custom_slide(
        self, title: str, text: str, parent: QModelIndex | None = None
    ) -> int:
        """Ajoute une slide personnalisée à la playlist."""
        return self.add_to_playlist("custom", title, text, parent)

    def add_custom_slides(
        self,
        title: str,
        texts: list[str],
        parent: QModelIndex | None = None,
        split: bool = True,
    ) -> int:
        """Ajoute une ou plusieurs slides de texte personnalisées.

        ``split`` smart-splits long blocks at the 280-char limit; pass False to
        keep each text exactly as one slide ("une seule diapo").
        """
        entries = [(title, text) for text in texts if str(text).strip()]
        if not entries:
            return -1
        return self.add_many_to_playlist("custom", entries, parent, split=split)

    def move_index(self, index: QModelIndex, up: bool) -> bool:
        """Déplace un item vers le haut ou vers le bas dans la playlist et la base."""
        if not index.isValid():
            return False

        parent = index.parent()
        row = index.row()
        target_row = row - 1 if up else row + 1

        parent_item = (
            self._playlist.itemFromIndex(parent)
            if parent.isValid()
            else self._playlist.invisibleRootItem()
        )
        if target_row < 0 or target_row >= parent_item.rowCount():
            return False

        # Swap in model
        row_items = parent_item.takeRow(row)
        parent_item.insertRow(target_row, row_items)

        self._playlist._mark_dirty()
        # Persist the new order to the database.
        self.persist_playlist_order()

        return True

    def duplicate_item(self, index: QModelIndex) -> bool:
        """Duplique un slide dans la playlist."""
        if not index.isValid() or self._playlist.is_folder(index):
            return False

        slide = index.data(PlaylistRoles.SlideDataRole)
        if not slide:
            return False

        source_type = index.data(PlaylistRoles.SourceRole)
        parent = index.parent()
        self.add_to_playlist(source_type, slide.reference, slide.text, parent)
        return True

    # ── Undo Stack ─────────────────────────────────────────────────────────

    def _push_undo(self, entry: dict) -> None:
        self._undo_stack.append(entry)
        if len(self._undo_stack) > self._MAX_UNDO:
            self._undo_stack.pop(0)

    def undo(self) -> bool:
        """Undo the last playlist action. Returns True if something was undone."""
        if not self._undo_stack:
            return False
        entry = self._undo_stack.pop()
        action = entry.get("action")

        if action == "add":
            # Remove the items that were added
            for item_id in reversed(entry.get("item_ids", [])):
                self._playlist_dao.delete_item(item_id)
                self._item_id_map.pop(item_id, None)
            self._playlist.clear()
            self._folder_index_map.clear()
            self._item_id_map.clear()
            self._load_playlist()
            new_count = self._playlist.flat_row_count()
            if new_count == 0:
                self._current_row = -1
                self.currentRowChanged.emit(-1)
                self.currentSlideChanged.emit(None)
            elif self._current_row >= new_count:
                self.set_current_row(new_count - 1)
            return True

        if action == "remove":
            # Re-add the removed slide
            source = entry.get("source", "custom")
            ref = entry.get("reference", "")
            text = entry.get("text", "")
            item_id = self._playlist_dao.add_item(source, ref, text, None)
            slide = Slide(source=source, reference=ref, text=text)
            row = self._playlist.add_slide(slide, None, item_id)
            if item_id:
                idx = self._playlist.index_at_flat_row(row)
                if idx.isValid():
                    self._item_id_map[item_id] = idx
            return True

        if action == "clear":
            # Restore snapshot
            snapshot = entry.get("snapshot", {})
            self._restore_snapshot(snapshot)
            return True

        return False

    def _snapshot_playlist(self) -> dict:
        """Create a JSON-serializable snapshot of the current playlist."""
        folders = []
        items = []
        for folder in self._playlist_dao.list_folders():
            folders.append({"id": folder["id"], "name": folder["name"]})
        for item in self._playlist_dao.list_all_items():
            items.append(
                {
                    "source": item["source"],
                    "reference": item["reference"],
                    "text": item["text"],
                    "folder_id": item["folder_id"],
                }
            )
        return {"folders": folders, "items": items}

    def _restore_snapshot(self, snapshot: dict) -> None:
        """Restore playlist from a snapshot dict."""
        self._playlist_dao.clear_all_items()
        self._playlist.clear()
        self._folder_index_map.clear()
        self._item_id_map.clear()

        folder_id_map: dict[int, int] = {}  # old_id -> new_id
        for f in snapshot.get("folders", []):
            new_id = self._playlist_dao.create_folder(f["name"])
            folder_id_map[f["id"]] = new_id

        for item in snapshot.get("items", []):
            fid = item.get("folder_id")
            new_fid = folder_id_map.get(fid) if fid is not None else None
            self._playlist_dao.add_item(
                item["source"],
                item["reference"],
                item["text"],
                new_fid,
            )

        self._load_playlist()
        if self._playlist.flat_row_count() > 0:
            self.set_current_row(0)
        else:
            self._current_row = -1
            self.currentRowChanged.emit(-1)
            self.currentSlideChanged.emit(None)

    # ── Export / Import ───────────────────────────────────────────────────

    def export_playlist(self, path: Path) -> None:
        """Export the current playlist to a JSON file."""
        data = self._snapshot_playlist()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def import_playlist(self, path: Path) -> None:
        """Import a playlist from a JSON file, replacing the current one."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self._restore_snapshot(data)

    # ── Rename Folder ─────────────────────────────────────────────────────

    def rename_folder(self, index: QModelIndex, new_name: str) -> bool:
        """Rename a folder in the playlist and database."""
        if not index.isValid():
            return False
        folder_id = self._playlist.get_folder_id(index)
        if folder_id is None:
            return False
        if self._playlist_dao.rename_folder(folder_id, new_name):
            item = self._playlist.itemFromIndex(index)
            if item is not None:
                item.setText(new_name)
            return True
        return False

    def update_item_content(self, index: QModelIndex, new_reference: str, new_text: str) -> bool:
        """Modifie de façon permanente le texte et la référence d'un item existant (édition rapide playlist)."""
        if not index.isValid():
            return False
        item_id = self._playlist.get_item_id(index)
        if item_id is None:
            return False
        
        # Mettre à jour en base
        cleaned_ref = self._clean_text(new_reference)
        cleaned_tex = self._clean_text(new_text)
        
        if self._playlist_dao.update_item(item_id, cleaned_ref, cleaned_tex):
            # Mettre à jour le modèle PyQt
            item = self._playlist.itemFromIndex(index)
            if item is not None:
                slide = index.data(PlaylistRoles.SlideDataRole)
                if slide is not None:
                    slide.reference = cleaned_ref
                    slide.text = cleaned_tex
                    # Refresh icon/text role cache
                    self._playlist._mark_dirty()
                    
                    # Update live view if currently projecting
                    flat_row = self._playlist.flat_row_from_index(index)
                    if flat_row == self._current_row:
                        self.set_current_row(self._current_row)
            return True
        return False

    def _on_playlist_structure_changed(self, *args) -> None:
        """Triggered when the playlist structure is modified (DnD, add/remove)."""
        self.persist_playlist_order()

    def persist_playlist_order(self) -> None:
        """Saves the current order and hierarchy of the playlist to the database."""
        root = self._playlist.invisibleRootItem()
        self._persist_recursive(root, None)

    def _persist_recursive(
        self, parent_item: QStandardItem, folder_id: int | None
    ) -> None:
        """Helper to recursively save items and their order."""
        from app.utils.playlist_model import PlaylistRoles

        for row in range(parent_item.rowCount()):
            item = parent_item.child(row)
            if item is None:
                continue

            is_folder = item.data(PlaylistRoles.IsFolderRole)
            if is_folder:
                f_id = item.data(PlaylistRoles.FolderIdRole)
                if f_id is not None:
                    self._playlist_dao.update_folder_sort_order(f_id, row)
                    self._persist_recursive(item, f_id)
            else:
                item_id = item.data(PlaylistRoles.ItemIdRole)
                if item_id is not None:
                    self._playlist_dao.update_item_sort_order(item_id, row, folder_id)

    def set_slide_background(self, index: QModelIndex, image_path: str) -> bool:
        """Set the background image for a playlist item and update projection if active."""
        if not index.isValid():
            return False
        item_id = self._playlist.get_item_id(index)
        if item_id is None:
            return False
        slide = index.data(PlaylistRoles.SlideDataRole)
        if slide is None:
            return False
        path_str = image_path.strip()
        if not self._playlist_dao.update_item_background(item_id, path_str):
            return False
        new_slide = Slide(
            source=slide.source,
            reference=slide.reference,
            text=slide.text,
            background=path_str if path_str else None,
            image_path=slide.image_path,
        )
        self._playlist.update_slide_data(index, new_slide)
        flat_row = self._playlist.flat_row_from_index(index)
        if flat_row == self._current_row:
            self._slide_writer.write(new_slide)
            self.currentSlideChanged.emit(new_slide)
        return True

    # ── Professional Preview Logic ────────────────────────────────────────

    def update_live_slide(self, reference: str, text: str) -> None:
        """Update the currently displayed slide (Quick Edit)."""
        # Note: This does NOT update the database or the playlist model permanently.
        # It only updates the live projection and the preview.
        current_slide = self._playlist.slide_at(self._current_row)
        if current_slide:
            text_clean = self._clean_text(text)
            if current_slide.source == "hymn":
                text_clean = strip_hymn_projection_label(text_clean)
            edited = Slide(
                source=current_slide.source,
                reference=self._clean_text(reference),
                text=text_clean,
                image_path=current_slide.image_path,
                background=current_slide.background,
            )
            self._slide_writer.write(edited)
            self.currentSlideChanged.emit(edited)

    def show_logo(self) -> None:
        """Clear the current slide to show the logo/black screen."""
        self.set_current_row(-1)
