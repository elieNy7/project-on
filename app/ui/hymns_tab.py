from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.ui.hymn_delegate import HymnDelegate
from app.ui.hymn_stanza_delegate import HymnStanzaDelegate
from app.ui.icons import app_icon
from app.ui.library_list_presentation import (
    COMPACT_PREVIEW_BOX_HEIGHT,
    truncate_preview,
)
from app.ui.theme import (
    Spacing,
    get_button_style,
    get_input_style,
    get_list_style,
    get_menu_style,
    get_preview_text_style,
    get_splitter_style,
    get_surface_panel_style,
)
from app.utils.translations import tr


class HymnsTab(QFrame):
    hymnSelected = pyqtSignal(int)
    hymnActivated = pyqtSignal(int)  # Add entire hymn
    stanzaActivated = pyqtSignal(str, str)  # Ref, Text
    stanzasActivated = pyqtSignal(list)  # List of (Ref, Text)
    importPptxFileRequested = pyqtSignal()
    importPptxFolderRequested = pyqtSignal()
    importPdfFileRequested = pyqtSignal()
    importScanRequested = pyqtSignal()
    deleteRequested = pyqtSignal(int)
    deleteAllRequested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        self._current_hymn_id: int | None = None
        self._current_hymn_title: str = ""

        # Search
        self.search = QLineEdit(self)
        self.search.setPlaceholderText(tr("search"))
        self.search.setClearButtonEnabled(True)
        self.search.setStyleSheet(get_input_style())

        # Import button (with menu)
        self.import_btn = QPushButton(" Importer", self)
        self.import_btn.setIcon(app_icon("upload.svg"))
        self.import_btn.setIconSize(QSize(16, 16))
        self.import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_btn.setStyleSheet(get_button_style())

        # Import Menu
        import_menu = QMenu(self)
        import_menu.setStyleSheet(get_menu_style())

        action_pptx_file = import_menu.addAction("Importer un fichier PowerPoint")
        action_pptx_folder = import_menu.addAction("Importer un dossier PowerPoint")
        import_menu.addSeparator()
        action_pdf = import_menu.addAction("Importer un fichier PDF")

        action_pptx_file.triggered.connect(self.importPptxFileRequested.emit)
        action_pptx_folder.triggered.connect(self.importPptxFolderRequested.emit)
        action_pdf.triggered.connect(self.importPdfFileRequested.emit)

        self.import_btn.setMenu(import_menu)

        # Labels (Consistency with Bible design)
        hymns_label = QLabel(tr("hymns") if hasattr(tr, "hymns") else "Cantiques", self)
        hymns_label.setObjectName("PanelTitle")

        # Hymns list
        self.hymns_list = QListWidget(self)
        self.hymns_list.setStyleSheet(get_list_style())
        self.hymns_list.setItemDelegate(HymnDelegate(self.hymns_list))
        self.hymns_list.setUniformItemSizes(True)
        self.hymns_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)

        # Stanzas list (multi-selection)
        self.stanzas_list = QListWidget(self)
        self.stanzas_list.setStyleSheet(get_list_style())
        self.stanzas_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.stanzas_list.setWordWrap(False)
        self.stanzas_list.setItemDelegate(HymnStanzaDelegate(self.stanzas_list))
        self.stanzas_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)

        # Preview box
        self.preview_box = QPlainTextEdit(self)
        self.preview_box.setReadOnly(True)
        self.preview_box.setMaximumHeight(COMPACT_PREVIEW_BOX_HEIGHT)
        self.preview_box.setStyleSheet(
            get_preview_text_style()
        )

        # Add Button
        self.add_btn = QPushButton(tr("add_to_playlist"), self)
        self.add_btn.setIcon(app_icon("plus.svg"))
        self.add_btn.setIconSize(QSize(16, 16))
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.setStyleSheet(get_button_style())

        # Delete Button (Menu for single/all)
        self.delete_btn = QPushButton(self)
        self.delete_btn.setIcon(app_icon("trash.svg"))
        self.delete_btn.setFixedSize(36, 36)
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.setObjectName("IconButton")

        delete_menu = QMenu(self)
        delete_menu.setStyleSheet(import_menu.styleSheet())  # Reuse menu style
        action_delete_one = delete_menu.addAction(tr("delete_selected"))
        delete_menu.addSeparator()
        action_delete_all = delete_menu.addAction("Tout supprimer")

        action_delete_one.triggered.connect(self._on_delete_clicked)
        action_delete_all.triggered.connect(self._on_delete_all_clicked)

        self.delete_btn.setMenu(delete_menu)

        # Action bar (bottom right)
        action_bar = QHBoxLayout()
        action_bar.setContentsMargins(0, 0, 0, 0)
        action_bar.setSpacing(Spacing.SM)
        action_bar.addWidget(self.add_btn, 1)
        action_bar.addWidget(self.delete_btn)

        # Left Header
        left_header = QHBoxLayout()
        left_header.setContentsMargins(0, 0, 0, 0)
        left_header.setSpacing(Spacing.MD)
        left_header.addWidget(hymns_label)
        left_header.addStretch()
        left_header.addWidget(self.import_btn)

        # Layouts
        left_widget = QWidget()
        left = QVBoxLayout(left_widget)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(Spacing.SM)
        left.addLayout(left_header)
        left.addWidget(self.hymns_list, 1)

        # Filter Container
        self.filter_container = QFrame(self)
        self.filter_container.setStyleSheet(get_surface_panel_style())
        filter_layout = QHBoxLayout(self.filter_container)
        filter_layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        filter_layout.addWidget(self.search, 1)

        right_widget = QWidget()
        right = QVBoxLayout(right_widget)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(Spacing.SM)
        right.addWidget(self.filter_container)
        right.addWidget(self.stanzas_list, 1)
        right.addWidget(self.preview_box)
        right.addLayout(action_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(get_splitter_style())

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(splitter)

        # Connections
        self.hymns_list.currentItemChanged.connect(self._on_hymn_changed)
        self.stanzas_list.itemDoubleClicked.connect(self._on_stanza_double_clicked)
        self.stanzas_list.currentItemChanged.connect(self._on_stanza_selection_changed)
        self.add_btn.clicked.connect(self._on_add_clicked)
        self.delete_btn.clicked.connect(self._on_delete_clicked)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(
            lambda: self._filter_hymns(self.search.text())
        )
        self.search.textChanged.connect(lambda _t: self._search_timer.start())

    def set_hymns(self, hymns: list[dict[str, Any]]) -> None:
        self.hymns_list.clear()
        for h in hymns:
            title = str(h.get("title") or "Sans titre")
            number = str(h.get("number") or "")
            search_key = str(h.get("title_search") or f"{title} {number}").lower()
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, int(h["id"]))
            item.setData(Qt.ItemDataRole.UserRole + 1, number or int(h["id"]))
            item.setData(Qt.ItemDataRole.UserRole + 2, search_key)
            item.setData(Qt.ItemDataRole.UserRole + 3, h.get("original_title", title))
            self.hymns_list.addItem(item)

        if self.hymns_list.count() > 0:
            self.hymns_list.setCurrentRow(0)

    def select_hymn(self, hymn_id: int) -> None:
        for i in range(self.hymns_list.count()):
            item = self.hymns_list.item(i)
            if int(item.data(Qt.ItemDataRole.UserRole)) == hymn_id:
                self.hymns_list.setCurrentRow(i)
                self.hymns_list.scrollToItem(item)
                break

    def set_stanzas(self, stanzas: list[dict[str, Any]]) -> None:
        self.stanzas_list.clear()
        self.preview_box.clear()
        for s in stanzas:
            content = str(s.get("text", ""))
            ref = str(s.get("reference", ""))
            label = str(s.get("label") or "")
            preview = truncate_preview(content, 80)
            item = QListWidgetItem(preview)
            item.setData(Qt.ItemDataRole.UserRole, (ref, content))
            item.setData(Qt.ItemDataRole.UserRole + 1, label)
            self.stanzas_list.addItem(item)

        if self.stanzas_list.count() > 0:
            self.stanzas_list.setCurrentRow(0)

    def current_hymn_title(self) -> str:
        return self._current_hymn_title

    def _on_hymn_changed(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        if current:
            hid = int(current.data(Qt.ItemDataRole.UserRole))
            self._current_hymn_id = hid
            self._current_hymn_title = current.text()
            self.hymnSelected.emit(hid)
        else:
            self._current_hymn_id = None
            self._current_hymn_title = ""
            self.stanzas_list.clear()

    def _on_stanza_double_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, tuple) and len(data) == 2:
            ref, content = data
            self.stanzaActivated.emit(ref, content)

    def _on_add_clicked(self) -> None:
        """Add selected stanzas when several are selected; otherwise add the hymn."""
        selected = self.stanzas_list.selectedItems()
        if len(selected) > 1:
            payload = []
            for item in selected:
                data = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(data, tuple) and len(data) == 2:
                    payload.append(data)
            if payload:
                self.stanzasActivated.emit(payload)
                return

        if self._current_hymn_id is not None:
            self.hymnActivated.emit(self._current_hymn_id)

    def _on_stanza_selection_changed(
        self, current: QListWidgetItem | None, prev: QListWidgetItem | None
    ) -> None:
        if current:
            data = current.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, tuple) and len(data) == 2:
                ref, content = data
                if ref:
                    self.preview_box.setPlainText(f"{ref}\n\n{content}")
                else:
                    self.preview_box.setPlainText(content)
        else:
            self.preview_box.clear()

    def _on_delete_clicked(self) -> None:
        if self._current_hymn_id is not None:
            self.deleteRequested.emit(self._current_hymn_id)

    def _on_delete_all_clicked(self) -> None:
        self.deleteAllRequested.emit()

    def _filter_hymns(self, text: str) -> None:
        query = text.lower().strip()
        for i in range(self.hymns_list.count()):
            item = self.hymns_list.item(i)
            searchable = f"{item.text()} {item.data(Qt.ItemDataRole.UserRole + 2) or ''}".lower()
            visible = query in searchable
            item.setHidden(not visible)
