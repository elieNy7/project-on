from __future__ import annotations

import re

from PyQt6.QtCore import (
    QModelIndex,
    QRegularExpression,
    QSize,
    QSortFilterProxyModel,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTreeView,
    QVBoxLayout,
)

from app.ui.icons import app_icon
from app.ui.playlist_delegate import PlaylistDelegate
from app.ui.theme import (
    Colors,
    Radius,
    Spacing,
    Typography,
    get_combo_style,
    get_panel_style,
    get_tree_style,
)
from app.utils.flow_layout import FlowLayout
from app.utils.playlist_model import PlaylistRoles
from app.utils.translations import tr


class PlaylistFilterProxyModel(QSortFilterProxyModel):
    """Proxy model that filters slides by reference but always shows folders."""

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        source_model = self.sourceModel()
        if source_model is None:
            return True

        index = source_model.index(source_row, 0, source_parent)
        is_folder = source_model.data(index, PlaylistRoles.IsFolderRole)

        # Always show folders (check explicitly for True since it can be None)
        if is_folder is True:
            return True

        # Filter slides by reference + text content
        filter_text = self.filterRegularExpression().pattern()
        if not filter_text:
            return True

        reference = source_model.data(index, PlaylistRoles.ReferenceRole) or ""
        text = source_model.data(index, PlaylistRoles.TextRole) or ""
        needle = filter_text.lower()
        return needle in reference.lower() or needle in text.lower()


class PlaylistToolButton(QPushButton):
    """Bouton toolbar avec icône et texte optionnel."""

    def __init__(
        self,
        icon_name: str,
        tooltip: str,
        parent=None,
        checkable: bool = False,
        text: str = "",
    ) -> None:
        super().__init__(parent)
        self.setIcon(app_icon(icon_name, "#a0aabe"))
        self.setIconSize(QSize(16, 16))
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(checkable)
        self._icon_name = icon_name
        if text:
            self.setText(text)
        self._setup_style()

    def _setup_style(self) -> None:
        self.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_TERTIARY};
                border: none;
                border-radius: {Radius.SM}px;
                min-width: 32px; max-width: 32px;
                min-height: 32px; max-height: 32px;
            }}
            QPushButton:hover {{
                background: {Colors.SURFACE_HOVER};
            }}
            QPushButton:pressed {{
                background: {Colors.SURFACE_ACTIVE};
            }}
            QPushButton:checked {{
                background: {Colors.ACCENT_GLOW};
                border: none;
            }}
            QPushButton:disabled {{
                background: transparent;
                border: none;
            }}
        """)


class PlaylistPanel(QFrame):
    slideSelected = pyqtSignal(int)
    removeRequested = pyqtSignal(int)
    removeIndexRequested = pyqtSignal(object)
    clearRequested = pyqtSignal()
    folderCreateRequested = pyqtSignal(str)
    folderDeleteRequested = pyqtSignal(object)
    folderRenameRequested = pyqtSignal(object, str)  # (index, new_name)
    customSlideRequested = pyqtSignal(str, str)  # title, text
    customSlidesRequested = pyqtSignal(str, list, bool)  # title, texts, split
    moveRequested = pyqtSignal(object, bool)  # (index, is_up)
    duplicateRequested = pyqtSignal(object)  # index
    editRequested = pyqtSignal(object)  # index
    undoRequested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PlaylistPanel")
        self._model = None
        self._proxy_model = None
        self._selected_folder_id: int | None = None
        self._folder_index_by_id: dict[int, QModelIndex] = {}
        # Accordion folders: opening one folder collapses its siblings.
        self._suppress_accordion = False

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setObjectName("Panel")
        self.setStyleSheet(get_panel_style())

        # ── Header: title + count + action buttons ────────────────────────
        header = QFrame(self)
        header.setObjectName("TopBar")
        header.setStyleSheet(f"""
            QFrame#TopBar {{
                background: {Colors.BG_TERTIARY};
                border: none;
                border-radius: {Radius.MD}px;
            }}
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 10, 14, 10)
        header_layout.setSpacing(Spacing.SM)

        self.title = QLabel(tr("playlist"), header)
        self.title.setStyleSheet(
            f"font-size: 18px; font-weight: {Typography.WEIGHT_BOLD}; color: {Colors.TEXT_PRIMARY}; background: transparent;"
        )
        header_layout.addWidget(self.title)

        self._count_label = QLabel(f"0 {tr('playlist_elements')}", header)
        self._count_label.setStyleSheet(f"""
            color: {Colors.ACCENT_PRIMARY};
            background: {Colors.ACCENT_GLOW};
            border: none;
            border-radius: 8px;
            padding: 3px 8px;
            font-size: {Typography.SIZE_XS}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
        """)
        header_layout.addWidget(self._count_label)
        header_layout.addStretch(1)

        # ── Search bar ────────────────────────────────────────────────────
        self._search_edit = QLineEdit(self)
        self._search_edit.setPlaceholderText(tr("search"))
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setFixedHeight(36)
        self._search_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: {Radius.MD}px;
                padding: 7px 12px;
                font-size: {Typography.SIZE_MD}px;
                color: {Colors.TEXT_PRIMARY};
                selection-background-color: {Colors.ACCENT_GLOW_STRONG};
                selection-color: {Colors.ACCENT_PRIMARY};
            }}
            QLineEdit:focus {{
                background: {Colors.BG_ELEVATED};
                border: 1px solid {Colors.BORDER_FOCUS};
            }}
            QLineEdit::placeholder {{
                color: {Colors.TEXT_MUTED};
            }}
        """)
        self._search_edit.textChanged.connect(self._on_search_changed)

        # ── Toolbar: add / folder / combo / delete ────────────────────────
        toolbar = QFrame(self)
        toolbar.setStyleSheet(f"""
            background: transparent;
            border: none;
        """)
        toolbar_layout = FlowLayout(
            toolbar, margin=0, hSpacing=Spacing.SM, vSpacing=Spacing.SM
        )
        toolbar.setContentsMargins(10, 8, 10, 8)

        self.custom_slide_button = PlaylistToolButton(
            "plus.svg", tr("add_custom_slide"), toolbar
        )
        self.folder_button = PlaylistToolButton(
            "folder-open.svg", tr("new_folder"), toolbar
        )

        toolbar_layout.addWidget(self.custom_slide_button)
        toolbar_layout.addWidget(self.folder_button)

        self._folder_combo = QComboBox(toolbar)
        self._folder_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._folder_combo.setMinimumWidth(100)
        self._folder_combo.setFixedHeight(32)
        self._folder_combo.setStyleSheet(get_combo_style())
        self._folder_combo.currentIndexChanged.connect(self._on_folder_combo_changed)
        toolbar_layout.addWidget(self._folder_combo)

        self.remove_button = PlaylistToolButton(
            "trash.svg", tr("playlist_remove"), toolbar
        )
        self.remove_button.setEnabled(False)
        self.clear_button = PlaylistToolButton(
            "trash-all.svg", tr("playlist_clear"), toolbar
        )

        toolbar_layout.addWidget(self.remove_button)
        toolbar_layout.addWidget(self.clear_button)

        # ── Tree view ─────────────────────────────────────────────────
        self.tree_view = QTreeView(self)
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setWordWrap(True)
        self.tree_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree_view.setExpandsOnDoubleClick(False)
        self.tree_view.setAnimated(True)
        self.tree_view.setIndentation(0)
        self.tree_view.setItemDelegate(PlaylistDelegate(self))
        self.tree_view.setStyleSheet(get_tree_style())
        self.tree_view.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        # Drag & Drop
        self.tree_view.setDragEnabled(True)
        self.tree_view.setAcceptDrops(True)
        self.tree_view.setDropIndicatorShown(True)
        self.tree_view.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.tree_view.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self._on_context_menu)

        # ── Empty state ───────────────────────────────────────────────────
        self._empty_state = QFrame(self)
        self._empty_state.setStyleSheet(f"""
            background: {Colors.BG_TERTIARY};
            border: none;
            border-radius: {Radius.LG}px;
        """)
        empty_layout = QVBoxLayout(self._empty_state)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(Spacing.SM)

        empty_icon = QLabel(self._empty_state)
        empty_icon.setPixmap(app_icon("music.svg", Colors.TEXT_MUTED).pixmap(48, 48))
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)

        empty_text = QLabel(tr("playlist_empty"), self._empty_state)
        empty_text.setStyleSheet(
            f"font-size: 14px; font-weight: 500; color: {Colors.TEXT_SECONDARY};"
        )
        empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_text)

        empty_hint = QLabel(tr("playlist_empty_hint"), self._empty_state)
        empty_hint.setStyleSheet(
            f"font-size: {Typography.SIZE_XS}px; color: {Colors.TEXT_DISABLED};"
        )
        empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_hint)

        self._empty_state.hide()

        # ── Main layout ──────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.SM)
        layout.addWidget(header)
        layout.addWidget(self._search_edit)
        layout.addWidget(toolbar)
        layout.addWidget(self.tree_view, 1)
        layout.addWidget(self._empty_state, 1)

        self.tree_view.clicked.connect(self._on_item_clicked)
        self.tree_view.doubleClicked.connect(self._on_item_double_clicked)
        self.remove_button.clicked.connect(self._on_remove_clicked)
        self.clear_button.clicked.connect(self._on_clear_clicked)
        self.folder_button.clicked.connect(self._on_folder_clicked)
        self.custom_slide_button.clicked.connect(self._on_custom_slide_clicked)

        # Keyboard shortcuts
        self._delete_shortcut = QShortcut(QKeySequence.StandardKey.Delete, self)
        self._delete_shortcut.activated.connect(self._on_remove_clicked)

        self._search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self._search_shortcut.activated.connect(self._focus_search)

        self._move_up_shortcut = QShortcut(QKeySequence("Ctrl+Up"), self)
        self._move_up_shortcut.activated.connect(lambda: self._on_move_item(True))

        self._move_down_shortcut = QShortcut(QKeySequence("Ctrl+Down"), self)
        self._move_down_shortcut.activated.connect(lambda: self._on_move_item(False))

        self._duplicate_shortcut = QShortcut(QKeySequence("Ctrl+D"), self)
        self._duplicate_shortcut.activated.connect(self._on_duplicate_item)

    def set_model(self, model) -> None:
        self._model = model

        # Create custom proxy model for filtering (shows folders, filters slides)
        self._proxy_model = PlaylistFilterProxyModel(self)
        self._proxy_model.setSourceModel(model)
        self._proxy_model.setRecursiveFilteringEnabled(True)

        self.tree_view.setModel(self._proxy_model)
        self.tree_view.expanded.connect(self._on_folder_expanded)

        self._refresh_folder_combo()
        self._update_remove_state()
        self._update_count()
        self._update_empty_state()
        self._update_action_state()

        sel = self.tree_view.selectionModel()
        if sel is not None:
            sel.currentChanged.connect(lambda _c, _p: self._update_remove_state())
            sel.currentChanged.connect(self._on_tree_current_changed)

        # Connect to model changes to update count and grid
        if model is not None:
            model.rowsInserted.connect(self._on_model_changed)
            model.rowsRemoved.connect(self._on_model_changed)
            model.modelReset.connect(self._on_model_changed)

    def _on_model_changed(self) -> None:
        if self._proxy_model is not None:
            self._proxy_model.invalidateFilter()
        self._refresh_folder_combo()
        self._update_count()
        self._update_empty_state()
        self._update_action_state()

    def _update_count(self) -> None:
        if self._model is None:
            self._count_label.setText(f"0 {tr('playlist_elements')}")
            return
        # Use flat_row_count (correct method name)
        count = (
            self._model.flat_row_count()
            if hasattr(self._model, "flat_row_count")
            else self._model.rowCount()
        )
        label = tr("playlist_element") if count == 1 else tr("playlist_elements")
        self._count_label.setText(f"{count} {label}")

    def _update_empty_state(self) -> None:
        if self._model is None:
            is_empty = True
        else:
            is_empty = self._model.rowCount() == 0
        self._empty_state.setVisible(is_empty)
        self.tree_view.setVisible(not is_empty)

    def _update_action_state(self) -> None:
        has_items = False
        if self._model is not None:
            has_items = self._model.rowCount() > 0
        self.clear_button.setEnabled(has_items)

    def set_current_row(self, row: int) -> None:
        if self._model is None:
            return
        if not hasattr(self._model, "index_at_flat_row"):
            return
        idx = self._model.index_at_flat_row(row)
        if not idx.isValid():
            return

        # Update list view
        if self._proxy_model is not None:
            view_idx = self._proxy_model.mapFromSource(idx)
        else:
            view_idx = idx
        if view_idx.isValid():
            self.tree_view.setCurrentIndex(view_idx)
            self.tree_view.scrollTo(
                view_idx, QAbstractItemView.ScrollHint.PositionAtCenter
            )
        self._update_remove_state()

    def _update_remove_state(self) -> None:
        idx = self.tree_view.currentIndex()
        self.remove_button.setEnabled(idx.isValid())

    def _on_folder_expanded(self, index: QModelIndex) -> None:
        """Accordion behaviour: when a folder is opened, collapse its siblings."""
        if self._suppress_accordion or self._proxy_model is None or self._model is None:
            return
        parent = index.parent()
        self._suppress_accordion = True
        try:
            for row in range(self._proxy_model.rowCount(parent)):
                sibling = self._proxy_model.index(row, 0, parent)
                if not sibling.isValid() or sibling == index:
                    continue
                source_sibling = self._proxy_model.mapToSource(sibling)
                is_folder = self._model.data(
                    source_sibling, PlaylistRoles.IsFolderRole
                )
                if is_folder is True and self.tree_view.isExpanded(sibling):
                    self.tree_view.collapse(sibling)
        finally:
            self._suppress_accordion = False

    def _on_item_clicked(self, index: QModelIndex) -> None:
        self._update_remove_state()
        if self._model is None or self._proxy_model is None:
            return
        # Map proxy index to source index
        source_index = self._proxy_model.mapToSource(index)
        is_folder = self._model.data(source_index, PlaylistRoles.IsFolderRole)
        if is_folder is True:
            if self.tree_view.isExpanded(index):
                self.tree_view.collapse(index)
            else:
                self.tree_view.expand(index)
            return
        flat_row = self._model.flat_row_from_index(source_index)
        if flat_row >= 0:
            self.slideSelected.emit(flat_row)

    def _on_item_double_clicked(self, index: QModelIndex) -> None:
        if self._model is None or self._proxy_model is None:
            return
        source_index = self._proxy_model.mapToSource(index)
        is_folder = self._model.data(source_index, PlaylistRoles.IsFolderRole)
        if is_folder is True:
            return
        flat_row = self._model.flat_row_from_index(source_index)
        if flat_row >= 0:
            self.slideSelected.emit(flat_row)

    def _on_remove_clicked(self) -> None:
        """Supprimer les éléments sélectionnés."""
        if self._model is None:
            return

        indexes = self.tree_view.selectionModel().selectedIndexes()
        if not indexes:
            return

        # Use a set to avoid duplicating operations (TreeView might have 1 col, but safe check)
        source_indexes = []
        for idx in indexes:
            src = self._proxy_model.mapToSource(idx) if self._proxy_model else idx
            if src.isValid() and src not in source_indexes:
                source_indexes.append(src)

        # Sort descending by row so deletions don't shift prior rows
        source_indexes.sort(key=lambda idx: idx.row(), reverse=True)

        folder_prompted = False
        for idx in source_indexes:
            is_folder = self._model.data(idx, PlaylistRoles.IsFolderRole)
            if is_folder:
                if not folder_prompted:
                    dialog = ConfirmDialog(
                        tr("confirm_delete"), tr("confirm_delete_folder_msg"), self
                    )
                    if dialog.exec() == QDialog.DialogCode.Rejected:
                        continue
                    folder_prompted = True
                self.folderDeleteRequested.emit(idx)
            else:
                self.removeIndexRequested.emit(idx)

    def _on_context_menu(self, pos) -> None:
        """Afficher le menu contextuel sur un élément de la playlist."""
        index = self.tree_view.indexAt(pos)
        if not index.isValid():
            return

        menu = QMenu(self)
        from app.ui.theme import get_menu_style

        menu.setStyleSheet(get_menu_style())

        # Determine if folder or slide
        source_index = (
            self._proxy_model.mapToSource(index) if self._proxy_model else index
        )
        is_folder = (
            self._model.data(source_index, PlaylistRoles.IsFolderRole)
            if self._model
            else False
        )

        if is_folder:
            rename_act = menu.addAction(app_icon("settings.svg"), tr("rename_folder"))
            rename_act.triggered.connect(lambda: self._on_rename_folder(source_index))
            menu.addSeparator()
            delete_act = menu.addAction(app_icon("trash.svg"), tr("delete_folder"))
            delete_act.triggered.connect(self._on_remove_clicked)
        else:
            # Slide actions
            play_act = menu.addAction(app_icon("monitor.svg"), tr("project"))
            play_act.triggered.connect(lambda: self._on_item_double_clicked(index))

            edit_act = menu.addAction(app_icon("pencil.svg"), tr("edit"))
            edit_act.triggered.connect(lambda: self.editRequested.emit(source_index))

            menu.addSeparator()

            up_act = menu.addAction(app_icon("chevron-up.svg"), tr("move_up"))
            up_act.triggered.connect(lambda: self._on_move_item(True))

            down_act = menu.addAction(app_icon("chevron-down.svg"), tr("move_down"))
            down_act.triggered.connect(lambda: self._on_move_item(False))

            dup_act = menu.addAction(app_icon("plus.svg"), tr("duplicate"))
            dup_act.triggered.connect(self._on_duplicate_item)

            menu.addSeparator()

            remove_act = menu.addAction(app_icon("trash.svg"), tr("remove"))
            remove_act.triggered.connect(self._on_remove_clicked)

        menu.exec(self.tree_view.viewport().mapToGlobal(pos))

    def _on_clear_clicked(self) -> None:
        if self._model is None or self._model.rowCount() == 0:
            return
        dialog = ConfirmDialog(
            tr("confirm_clear_playlist"),
            tr("confirm_clear_playlist_msg"),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.clearRequested.emit()

    def _on_folder_clicked(self) -> None:
        dialog = InputDialog(tr("new_folder"), tr("folder_name"), parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = dialog.get_text()
            if name.strip():
                self.folderCreateRequested.emit(name.strip())

    def get_selected_folder_index(self) -> QModelIndex | None:
        """Retourne l'index du dossier sélectionné ou None (source model index)."""
        if self._model is None:
            return None

        idx = self.tree_view.currentIndex()
        if not idx.isValid() or self._proxy_model is None:
            return None
        source_idx = self._proxy_model.mapToSource(idx)
        is_folder = self._model.data(source_idx, PlaylistRoles.IsFolderRole)
        if is_folder is True:
            return source_idx
        parent_idx = source_idx.parent()
        return parent_idx if parent_idx.isValid() else None

    def select_and_expand_folder(self, source_index: QModelIndex) -> None:
        """Sélectionne et étend un dossier dans la vue (prend un index du source model)."""
        if not source_index.isValid() or self._proxy_model is None:
            return
        # Map source index to proxy index
        proxy_index = self._proxy_model.mapFromSource(source_index)
        if proxy_index.isValid():
            self.tree_view.setCurrentIndex(proxy_index)
            self.tree_view.expand(proxy_index)
            self.tree_view.scrollTo(
                proxy_index, QAbstractItemView.ScrollHint.EnsureVisible
            )
        if self._model is not None and hasattr(self._model, "get_folder_id"):
            self._set_selected_folder_id(self._model.get_folder_id(source_index))

    def _refresh_folder_combo(self) -> None:
        if not hasattr(self, "_folder_combo"):
            return
        self._folder_index_by_id.clear()
        self._folder_combo.blockSignals(True)
        self._folder_combo.clear()
        self._folder_combo.addItem(tr("playlist_root"), None)

        if (
            self._model is not None
            and hasattr(self._model, "get_folders")
            and hasattr(self._model, "get_folder_id")
        ):
            for name, idx in self._model.get_folders():
                folder_id = self._model.get_folder_id(idx)
                if folder_id is None:
                    continue
                self._folder_index_by_id[folder_id] = idx
                self._folder_combo.addItem(name, folder_id)

        self._folder_combo.blockSignals(False)
        self._set_selected_folder_id(self._selected_folder_id)

    def _set_selected_folder_id(self, folder_id: int | None) -> None:
        self._selected_folder_id = folder_id
        if not hasattr(self, "_folder_combo"):
            return
        for i in range(self._folder_combo.count()):
            if self._folder_combo.itemData(i, Qt.ItemDataRole.UserRole) == folder_id:
                if self._folder_combo.currentIndex() != i:
                    self._folder_combo.blockSignals(True)
                    self._folder_combo.setCurrentIndex(i)
                    self._folder_combo.blockSignals(False)
                return
        if self._folder_combo.currentIndex() != 0:
            self._folder_combo.blockSignals(True)
            self._folder_combo.setCurrentIndex(0)
            self._folder_combo.blockSignals(False)

    def _on_folder_combo_changed(self, _index: int) -> None:
        folder_id = self._folder_combo.currentData(Qt.ItemDataRole.UserRole)
        self._selected_folder_id = folder_id
        if self._proxy_model is not None and folder_id is not None:
            source_idx = self._folder_index_by_id.get(folder_id)
            if source_idx is not None:
                proxy_idx = self._proxy_model.mapFromSource(source_idx)
                if proxy_idx.isValid():
                    self.tree_view.setCurrentIndex(proxy_idx)
                    self.tree_view.expand(proxy_idx)

    def _on_tree_current_changed(
        self, current: QModelIndex, _previous: QModelIndex
    ) -> None:
        if self._model is None or self._proxy_model is None:
            return
        if not current.isValid():
            self._set_selected_folder_id(None)
            return
        source_idx = self._proxy_model.mapToSource(current)
        if not source_idx.isValid():
            self._set_selected_folder_id(None)
            return
        is_folder = self._model.data(source_idx, PlaylistRoles.IsFolderRole)
        if is_folder is True:
            folder_id = (
                self._model.get_folder_id(source_idx)
                if hasattr(self._model, "get_folder_id")
                else None
            )
            self._set_selected_folder_id(folder_id)
            return
        p = source_idx.parent()
        if p.isValid() and (self._model.data(p, PlaylistRoles.IsFolderRole) is True):
            folder_id = (
                self._model.get_folder_id(p)
                if hasattr(self._model, "get_folder_id")
                else None
            )
            self._set_selected_folder_id(folder_id)
            return
        self._set_selected_folder_id(None)

    def _on_custom_slide_clicked(self) -> None:
        dialog = CustomSlideDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            title, _text = dialog.get_content()
            texts, split = dialog.get_slides()
            if texts:
                self.customSlidesRequested.emit(
                    title.strip() or tr("custom_slide_default"), texts, split
                )

    def _on_conference_slide_clicked(self) -> None:
        dialog = ConferenceSlideDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        for title, text in dialog.get_slides():
            if text.strip():
                self.customSlideRequested.emit(title.strip(), text.strip())

    def _on_search_changed(self, text: str) -> None:
        """Filter playlist items based on search text (reference + content)."""
        search_text = text.strip()

        # Filter tree view using proxy model
        if self._proxy_model is not None:
            escaped = QRegularExpression.escape(search_text)
            self._proxy_model.setFilterRegularExpression(
                QRegularExpression(
                    escaped, QRegularExpression.PatternOption.CaseInsensitiveOption
                ),
            )
            # Expand all to show filtered results (accordion disabled so the
            # search reveals matches in every folder, not just the last one).
            if search_text:
                self._suppress_accordion = True
                self.tree_view.expandAll()
                self._suppress_accordion = False
            else:
                self.tree_view.collapseAll()

    def _on_move_item(self, up: bool) -> None:
        idx = self.tree_view.currentIndex()
        if not idx.isValid():
            return
        source_index = self._proxy_model.mapToSource(idx) if self._proxy_model else idx
        self.moveRequested.emit(source_index, up)

    def _on_duplicate_item(self) -> None:
        idx = self.tree_view.currentIndex()
        if not idx.isValid():
            return
        source_index = self._proxy_model.mapToSource(idx) if self._proxy_model else idx
        self.duplicateRequested.emit(source_index)

    def _focus_search(self) -> None:
        """Focus the search bar."""
        self._search_edit.setFocus()
        self._search_edit.selectAll()

    def _on_rename_folder(self, source_index) -> None:
        """Show a dialog to rename a folder."""
        if self._model is None:
            return
        current_name = self._model.data(source_index, Qt.ItemDataRole.DisplayRole) or ""
        dialog = InputDialog(
            tr("rename_folder"),
            tr("rename_folder_prompt"),
            default_text=current_name,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_name = dialog.get_text()
            if new_name.strip():
                self.folderRenameRequested.emit(source_index, new_name.strip())


class ConfirmDialog(QDialog):
    """Dialogue de confirmation avec style moderne."""

    def __init__(self, title: str, message: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(350)
        self.setStyleSheet(f"""
            QDialog {{
                background: {Colors.BG_PRIMARY};
            }}
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_MD}px;
            }}
            QPushButton {{
                background: {Colors.SURFACE_HOVER};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
                padding: 8px 18px;
                color: {Colors.TEXT_PRIMARY};
                font-weight: {Typography.WEIGHT_MEDIUM};
            }}
            QPushButton:hover {{
                background: {Colors.SURFACE_ACTIVE};
            }}
            QPushButton#danger {{
                background: rgba(239, 68, 68, 0.15);
                border-color: rgba(239, 68, 68, 0.3);
                color: {Colors.ACCENT_DANGER};
            }}
            QPushButton#danger:hover {{
                background: rgba(239, 68, 68, 0.25);
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        layout.setSpacing(Spacing.LG)

        msg_label = QLabel(message, self)
        msg_label.setWordWrap(True)
        layout.addWidget(msg_label)

        button_box = QDialogButtonBox(self)
        btn_yes = button_box.addButton(tr("yes"), QDialogButtonBox.ButtonRole.YesRole)
        btn_yes.setObjectName("danger")
        btn_no = button_box.addButton(tr("no"), QDialogButtonBox.ButtonRole.NoRole)

        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)


class InputDialog(QDialog):
    """Dialogue de saisie avec style moderne."""

    def __init__(
        self, title: str, label: str, default_text: str = "", parent=None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(350)
        self.setStyleSheet(f"""
            QDialog {{
                background: {Colors.BG_PRIMARY};
            }}
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_SM}px;
            }}
            QLineEdit {{
                background: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
                padding: 8px 12px;
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_MD}px;
            }}
            QLineEdit:focus {{
                border-color: {Colors.BORDER_FOCUS};
            }}
            QPushButton {{
                background: {Colors.SURFACE_HOVER};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
                padding: 8px 18px;
                color: {Colors.TEXT_PRIMARY};
                font-weight: {Typography.WEIGHT_MEDIUM};
            }}
            QPushButton:hover {{
                background: {Colors.SURFACE_ACTIVE};
            }}
            QPushButton:default {{
                background: rgba(201, 168, 76, 0.20);
                border-color: rgba(201, 168, 76, 0.35);
                color: {Colors.ACCENT_LIGHT};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        layout.setSpacing(Spacing.MD)

        msg_label = QLabel(label, self)
        layout.addWidget(msg_label)

        self._input = QLineEdit(self)
        self._input.setText(default_text)
        layout.addWidget(self._input)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._input.setFocus()
        self._input.selectAll()

    def get_text(self) -> str:
        return self._input.text()


class ConferenceSlideDialog(QDialog):
    """Create ready-to-project slides for broad event use cases."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("event_slides"))
        self.setMinimumSize(520, 620)
        self.setStyleSheet(f"""
            QDialog {{
                background: {Colors.BG_PRIMARY};
            }}
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_SM}px;
            }}
            QComboBox, QLineEdit, QSpinBox {{
                background: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
                padding: 8px 12px;
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_MD}px;
            }}
            QComboBox:focus, QLineEdit:focus, QSpinBox:focus {{
                border-color: {Colors.BORDER_FOCUS};
            }}
            QPlainTextEdit {{
                background: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
                padding: 8px;
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_MD}px;
            }}
            QPlainTextEdit:focus {{
                border-color: {Colors.BORDER_FOCUS};
            }}
            QPushButton {{
                background: {Colors.SURFACE_HOVER};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
                padding: 8px 18px;
                color: {Colors.TEXT_PRIMARY};
                font-weight: {Typography.WEIGHT_MEDIUM};
            }}
            QPushButton:hover {{
                background: {Colors.SURFACE_ACTIVE};
            }}
            QPushButton:default {{
                background: rgba(201, 168, 76, 0.20);
                border-color: rgba(201, 168, 76, 0.35);
                color: {Colors.ACCENT_LIGHT};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        layout.setSpacing(Spacing.MD)

        event_label = QLabel(tr("event_type"), self)
        layout.addWidget(event_label)

        self._event_combo = QComboBox(self)
        self._event_combo.addItem(tr("event_general"), "general")
        self._event_combo.addItem(tr("event_corporate"), "corporate")
        self._event_combo.addItem(tr("event_training"), "training")
        self._event_combo.addItem(tr("event_workshop"), "workshop")
        self._event_combo.addItem(tr("event_webinar"), "webinar")
        self._event_combo.addItem(tr("event_panel"), "panel")
        self._event_combo.addItem(tr("event_expo"), "expo")
        layout.addWidget(self._event_combo)

        type_label = QLabel(tr("slide_format"), self)
        layout.addWidget(type_label)

        self._type_combo = QComboBox(self)
        self._type_combo.addItem(tr("slide_kit"), "kit")
        self._type_combo.addItem(tr("slide_session"), "session")
        self._type_combo.addItem(tr("slide_agenda"), "agenda")
        self._type_combo.addItem(tr("slide_speaker"), "speaker")
        self._type_combo.addItem(tr("slide_panel"), "panel")
        self._type_combo.addItem(tr("slide_break"), "break")
        self._type_combo.addItem(tr("slide_networking"), "networking")
        self._type_combo.addItem(tr("slide_qa"), "qa")
        self._type_combo.addItem(tr("slide_announcement"), "announcement")
        self._type_combo.addItem(tr("slide_sponsor"), "sponsor")
        self._type_combo.addItem(tr("slide_info"), "info")
        self._type_combo.addItem(tr("slide_countdown"), "countdown")
        self._type_combo.addItem(tr("slide_cta"), "cta")
        layout.addWidget(self._type_combo)

        title_label = QLabel(tr("event_title"), self)
        layout.addWidget(title_label)
        self._title_edit = QLineEdit(self)
        self._title_edit.setPlaceholderText(tr("event_title_placeholder"))
        layout.addWidget(self._title_edit)

        speaker_label = QLabel(tr("event_speaker"), self)
        layout.addWidget(speaker_label)
        self._speaker_edit = QLineEdit(self)
        self._speaker_edit.setPlaceholderText(tr("event_speaker_placeholder"))
        layout.addWidget(self._speaker_edit)

        org_label = QLabel(tr("event_org"), self)
        layout.addWidget(org_label)
        self._org_edit = QLineEdit(self)
        self._org_edit.setPlaceholderText(tr("event_org_placeholder"))
        layout.addWidget(self._org_edit)

        detail_label = QLabel(tr("event_detail"), self)
        layout.addWidget(detail_label)
        self._detail_edit = QLineEdit(self)
        self._detail_edit.setPlaceholderText(tr("event_detail_placeholder"))
        layout.addWidget(self._detail_edit)

        minutes_label = QLabel(tr("event_duration"), self)
        layout.addWidget(minutes_label)
        self._minutes_spin = QSpinBox(self)
        self._minutes_spin.setRange(1, 180)
        self._minutes_spin.setValue(10)
        self._minutes_spin.setSuffix(" " + tr("minutes"))
        layout.addWidget(self._minutes_spin)

        notes_label = QLabel(tr("event_notes"), self)
        layout.addWidget(notes_label)
        self._notes_edit = QPlainTextEdit(self)
        self._notes_edit.setPlaceholderText(
            tr("event_notes_placeholder")
        )
        layout.addWidget(self._notes_edit, 1)

        hint = QLabel(
            tr("event_kit_hint"),
            self,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {Typography.SIZE_XS}px;"
        )
        layout.addWidget(hint)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        ok_btn = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setText(tr("add"))
        cancel_btn = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn:
            cancel_btn.setText(tr("cancel"))
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._title_edit.setFocus()

    def get_slides(self) -> list[tuple[str, str]]:
        event_type = str(self._event_combo.currentData() or "general")
        kind = str(self._type_combo.currentData() or "session")
        title = self._title_edit.text().strip() or self._default_title(event_type)
        speaker = self._speaker_edit.text().strip()
        organization = self._org_edit.text().strip()
        detail = self._detail_edit.text().strip()
        notes = self._notes_edit.toPlainText().strip()
        minutes = self._minutes_spin.value()

        def join_lines(*parts: str) -> str:
            return "\n".join(part for part in parts if part.strip())

        def notes_or(default: str) -> str:
            return notes if notes else default

        agenda = self._agenda_text(notes)

        if kind == "kit":
            return self._build_event_kit(
                event_type,
                title,
                speaker,
                organization,
                detail,
                agenda,
                minutes,
                notes,
                join_lines,
            )

        if kind == "agenda":
            return [(tr("slide_agenda"), join_lines(tr("agenda_header"), agenda))]
        if kind == "speaker":
            return [(tr("slide_speaker"), join_lines(speaker or tr("slide_speaker"), title, organization, detail))]
        if kind == "panel":
            return [(tr("slide_panel"), join_lines(tr("panel_header"), title, speaker, detail))]
        if kind == "break":
            return [(tr("slide_break"), tr("break_template").format(minutes=minutes))]
        if kind == "networking":
            return [(tr("slide_networking"), join_lines(tr("networking_header"), notes_or(tr("networking_default_text")), detail))]
        if kind == "qa":
            return [(tr("slide_qa"), join_lines(tr("qa_header"), title))]
        if kind == "announcement":
            return [(tr("slide_announcement"), join_lines(title, notes or detail))]
        if kind == "sponsor":
            return [(tr("slide_sponsor"), join_lines(tr("sponsor_header"), organization or title, detail))]
        if kind == "info":
            return [(tr("slide_info"), join_lines(tr("info_header"), notes_or(detail or tr("info_default_text"))))]
        if kind == "countdown":
            return [(tr("slide_countdown"), tr("countdown_template").format(minutes=minutes))]
        if kind == "cta":
            return [(tr("slide_cta"), join_lines(tr("cta_header"), notes_or(detail or tr("cta_default_text"))))]
        return [(tr("slide_session"), join_lines(title, speaker, organization, detail, notes))]

    @staticmethod
    def _agenda_text(notes: str) -> str:
        from app.utils.translations import tr
        lines = [line.strip(" -\t") for line in notes.splitlines() if line.strip()]
        if not lines:
            lines = [tr("agenda_default_1"), tr("agenda_default_2"), tr("agenda_default_3"), tr("agenda_default_4")]
        return "\n".join(f"{index + 1}. {line}" for index, line in enumerate(lines))

    @staticmethod
    def _default_title(event_type: str) -> str:
        from app.utils.translations import tr
        defaults = {
            "corporate": tr("default_title_corporate"),
            "training": tr("default_title_training"),
            "workshop": tr("default_title_workshop"),
            "webinar": tr("default_title_webinar"),
            "panel": tr("default_title_panel"),
            "expo": tr("default_title_expo"),
        }
        return defaults.get(event_type, tr("default_title_event"))

    @staticmethod
    def _build_event_kit(
        event_type: str,
        title: str,
        speaker: str,
        organization: str,
        detail: str,
        agenda: str,
        minutes: int,
        notes: str,
        join_lines,
    ) -> list[tuple[str, str]]:
        from app.utils.translations import tr
        common = [
            (tr("kit_welcome"), join_lines(tr("kit_welcome_header"), title, organization, detail)),
            (tr("slide_agenda"), join_lines(tr("agenda_header"), agenda)),
        ]

        if event_type == "training":
            middle = [
                (tr("kit_objectives"), join_lines(tr("kit_objectives_header"), notes or tr("kit_objectives_default"))),
                (tr("kit_exercise"), tr("kit_exercise_text")),
            ]
        elif event_type == "workshop":
            middle = [
                (tr("kit_workshop"), join_lines(tr("kit_workshop_header"), title, tr("kit_workshop_default"))),
                (tr("kit_debrief"), tr("kit_debrief_text")),
            ]
        elif event_type == "webinar":
            middle = [
                (tr("kit_live"), join_lines(tr("kit_live_header"), title, speaker)),
                (tr("kit_interaction"), tr("kit_interaction_webinar")),
            ]
        elif event_type == "panel":
            middle = [
                (tr("kit_panel"), join_lines(tr("panel_header"), title, speaker)),
                (tr("kit_questions"), tr("kit_questions_panel")),
            ]
        elif event_type == "expo":
            middle = [
                (tr("kit_expo"), join_lines(tr("kit_expo_header"), title, organization)),
                (tr("kit_networking"), tr("kit_networking_expo")),
            ]
        elif event_type == "corporate":
            middle = [
                (tr("slide_session"), join_lines(title, speaker, organization)),
                (tr("kit_decision"), tr("kit_decision_text")),
            ]
        else:
            middle = [
                (tr("slide_session"), join_lines(title, speaker, organization)),
                (tr("kit_interaction"), tr("kit_interaction_general")),
            ]

        closing = [
            (tr("slide_break"), tr("break_template").format(minutes=minutes)),
            (tr("slide_qa"), join_lines(tr("qa_header"), title)),
            (tr("slide_info"), join_lines(tr("info_header"), detail or tr("info_default_footer"))),
            (tr("kit_closing"), join_lines(tr("kit_closing_header"), notes or tr("kit_closing_default"))),
        ]
        return common + middle + closing


class CustomSlideDialog(QDialog):
    """Dialogue pour créer une slide personnalisée."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("custom_slide_title"))
        self.setMinimumSize(450, 350)
        self.setStyleSheet(f"""
            QDialog {{
                background: {Colors.BG_PRIMARY};
            }}
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_SM}px;
            }}
            QLineEdit {{
                background: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
                padding: 8px 12px;
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_MD}px;
            }}
            QLineEdit:focus {{
                border-color: {Colors.BORDER_FOCUS};
            }}
            QPlainTextEdit {{
                background: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
                padding: 8px;
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_MD}px;
            }}
            QPlainTextEdit:focus {{
                border-color: {Colors.BORDER_FOCUS};
            }}
            QPushButton {{
                background: {Colors.SURFACE_HOVER};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
                padding: 8px 18px;
                color: {Colors.TEXT_PRIMARY};
                font-weight: {Typography.WEIGHT_MEDIUM};
            }}
            QPushButton:hover {{
                background: {Colors.SURFACE_ACTIVE};
            }}
            QPushButton:default {{
                background: rgba(201, 168, 76, 0.20);
                border-color: rgba(201, 168, 76, 0.35);
                color: {Colors.ACCENT_LIGHT};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        layout.setSpacing(Spacing.MD)

        # Title field
        title_label = QLabel(tr("custom_slide_name"), self)
        layout.addWidget(title_label)

        self._title_edit = QLineEdit(self)
        self._title_edit.setPlaceholderText(tr("custom_slide_name_placeholder"))
        layout.addWidget(self._title_edit)

        # Text field
        text_label = QLabel(tr("custom_slide_text"), self)
        layout.addWidget(text_label)

        self._text_edit = QPlainTextEdit(self)
        self._text_edit.setPlaceholderText(tr("custom_slide_text_placeholder"))
        layout.addWidget(self._text_edit, 1)

        # Split mode
        mode_row = QHBoxLayout()
        mode_row.setSpacing(Spacing.SM)
        mode_label = QLabel(tr("custom_slide_split"), self)
        self._mode_combo = QComboBox(self)
        self._mode_combo.addItem(tr("custom_slide_split_auto"), "auto")
        self._mode_combo.addItem(tr("custom_slide_split_paragraph"), "paragraph")
        self._mode_combo.addItem(tr("custom_slide_split_single"), "single")
        self._mode_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mode_combo.setStyleSheet(get_combo_style())
        self._mode_combo.currentIndexChanged.connect(self._on_text_changed)
        mode_row.addWidget(mode_label)
        mode_row.addWidget(self._mode_combo, 1)
        layout.addLayout(mode_row)

        # Character Counter
        self._counter_label = QLabel("", self)
        self._counter_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: {Typography.SIZE_XS}px;")
        layout.addWidget(self._counter_label)

        self._text_edit.textChanged.connect(self._on_text_changed)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._text_edit.setFocus()
        self._on_text_changed()

    def get_mode(self) -> str:
        return str(self._mode_combo.currentData() or "auto")

    def get_slides(self) -> tuple[list[str], bool]:
        """Return (texts, split) for the chosen mode.

        - auto:      one block, smart-split by the controller (split=True)
        - paragraph: one entry per blank-line-separated paragraph (split=True)
        - single:    one slide, never split (split=False)
        """
        text = self._text_edit.toPlainText().strip()
        if not text:
            return [], True
        mode = self.get_mode()
        if mode == "single":
            return [text], False
        if mode == "paragraph":
            paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
            return (paragraphs or [text]), True
        return [text], True

    def _slide_count(self) -> int:
        from app.utils.text_utils import split_text_into_slides

        texts, split = self.get_slides()
        if not texts:
            return 0
        if not split:
            return len(texts)
        return sum(max(1, len(split_text_into_slides(t))) for t in texts)

    def _on_text_changed(self) -> None:
        count = len(self._text_edit.toPlainText().strip())
        slides = self._slide_count()
        if count == 0:
            self._counter_label.setText(tr("custom_slide_count_empty"))
            highlight = False
        else:
            label = tr("slide") if slides == 1 else tr("slides")
            self._counter_label.setText(f"{count} {tr('characters')} • {slides} {label}")
            highlight = slides > 1
        color = Colors.ACCENT_PRIMARY if highlight else Colors.TEXT_MUTED
        weight = "bold" if highlight else "normal"
        self._counter_label.setStyleSheet(
            f"color: {color}; font-size: {Typography.SIZE_XS}px; font-weight: {weight};"
        )

    def get_content(self) -> tuple[str, str]:
        return self._title_edit.text(), self._text_edit.toPlainText()
