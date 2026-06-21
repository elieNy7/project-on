from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QEvent, QObject, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.ui.bible_book_delegate import BibleBookDelegate
from app.ui.bible_verse_delegate import BibleVerseDelegate
from app.ui.icons import app_icon
from app.ui.library_list_presentation import (
    COMPACT_PREVIEW_BOX_HEIGHT,
    normalize_preview_text,
    truncate_preview,
)
from app.ui.theme import (
    Spacing,
    get_button_style,
    get_combo_style,
    get_input_style,
    get_list_style,
    get_preview_text_style,
    get_scroll_area_style,
    get_splitter_style,
    get_surface_panel_style,
)
from app.utils.translations import tr


class HorizontalScrollFilter(QObject):
    """Event filter to enable horizontal scrolling with the mouse wheel."""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Wheel:
            if isinstance(obj, QScrollArea):
                delta = event.angleDelta().y()
                if delta == 0:
                    delta = event.angleDelta().x()
                hbar = obj.horizontalScrollBar()
                # Use a larger multiplier for smoother, faster scrolling
                hbar.setValue(hbar.value() - int(delta * 1.5))
                return True
        return super().eventFilter(obj, event)


class BibleTab(QFrame):
    translationSelected = pyqtSignal(int)
    bookSelected = pyqtSignal(int)
    chapterSelected = pyqtSignal(int)
    verseActivated = pyqtSignal(str, str)
    versesActivated = pyqtSignal(list)  # list of (ref, text) tuples
    searchRequested = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        self._books: list[dict[str, Any]] = []
        self._current_book_id: int | None = None
        self._current_book_name: str = ""

        # Translation combo
        self.translation_combo = QComboBox(self)
        self.translation_combo.setStyleSheet(get_combo_style())
        self.translation_combo.setMinimumWidth(140)

        # Search
        self.search = QLineEdit(self)
        self.search.setPlaceholderText(tr("search"))
        self.search.setClearButtonEnabled(True)
        self.search.setStyleSheet(get_input_style())

        # Books list
        self.books_list = QListWidget(self)
        self.books_list.setMinimumWidth(120)
        self.books_list.setStyleSheet(get_list_style())
        self.books_list.setItemDelegate(BibleBookDelegate(self.books_list))
        self.books_list.setUniformItemSizes(True)
        self.books_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)

        # Title label above books
        books_label = QLabel(tr("bible"), self)
        books_label.setObjectName("PanelTitle")

        # Chapter bar
        self.chapter_bar = QWidget(self)
        self.chapter_bar.setStyleSheet("background: transparent;")
        self.chapter_bar_layout = QHBoxLayout(self.chapter_bar)
        self.chapter_bar_layout.setContentsMargins(0, 0, 0, 0)
        self.chapter_bar_layout.setSpacing(4)

        self.chapter_scroll = QScrollArea(self)
        self.chapter_scroll.setWidgetResizable(True)
        self.chapter_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.chapter_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )
        self.chapter_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.chapter_scroll.setWidget(self.chapter_bar)
        self.chapter_scroll.setFixedHeight(52)
        self.chapter_scroll.setStyleSheet(get_scroll_area_style())

        # Enable horizontal wheel scrolling
        self._scroll_filter = HorizontalScrollFilter(self)
        self.chapter_scroll.installEventFilter(self._scroll_filter)

        # Verses list (multi-selection enabled)
        self.verses_list = QListWidget(self)
        self.verses_list.setStyleSheet(get_list_style())
        self.verses_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.verses_list.setWordWrap(False)
        self.verses_list.setItemDelegate(BibleVerseDelegate(self.verses_list))
        self.verses_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.verses_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        # self.verses_list.setUniformItemSizes(True) # Disabled for flexible delegate height

        # Verse preview (Modernized)
        self.verse_preview = QPlainTextEdit(self)
        self.verse_preview.setReadOnly(True)
        self.verse_preview.setMaximumHeight(COMPACT_PREVIEW_BOX_HEIGHT)
        self.verse_preview.setPlaceholderText(
            tr("preview_placeholder")
            if hasattr(tr, "preview_placeholder")
            else "Aperçu..."
        )
        self.verse_preview.setStyleSheet(
            get_preview_text_style()
        )

        # Add button
        self.add_verse_btn = QPushButton(tr("add_to_playlist"), self)
        self.add_verse_btn.setIcon(app_icon("plus.svg"))
        self.add_verse_btn.setIconSize(QSize(16, 16))
        self.add_verse_btn.setToolTip(tr("add_verse_tooltip"))
        self.add_verse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_verse_btn.setStyleSheet(get_button_style())

        # Toolbar (Translation only in left panel now)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(Spacing.MD)
        toolbar.addWidget(self.translation_combo, 1)

        # Left panel
        left_widget = QWidget()
        left_widget.setStyleSheet("background: transparent;")
        left = QVBoxLayout(left_widget)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(Spacing.SM)
        left.addLayout(toolbar)
        left.addWidget(books_label)
        left.addWidget(self.books_list, 1)

        # Filter Container with Background (matches Expose tab)
        self.filter_container = QFrame(self)
        self.filter_container.setStyleSheet(get_surface_panel_style())
        filter_layout = QHBoxLayout(self.filter_container)
        filter_layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        filter_layout.setSpacing(Spacing.SM)
        filter_layout.addWidget(self.search, 1)

        # Right panel
        right_widget = QWidget()
        right_widget.setStyleSheet("background: transparent;")
        right = QVBoxLayout(right_widget)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(Spacing.SM)
        right.addWidget(self.chapter_scroll)
        right.addWidget(self.filter_container)
        right.addWidget(self.verses_list, 1)
        right.addWidget(self.verse_preview)
        right.addWidget(self.add_verse_btn)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        # Professional thin handle that reacts to hover
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(get_splitter_style())

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(splitter, 1)

        self.translation_combo.currentIndexChanged.connect(self._on_translation_changed)
        self.books_list.currentItemChanged.connect(self._on_book_changed)
        self.verses_list.itemDoubleClicked.connect(self._on_verse_activated)
        self.verses_list.currentItemChanged.connect(self._on_verse_selection_changed)
        self.add_verse_btn.clicked.connect(self._on_add_verse_clicked)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(
            lambda: self._on_search_changed(self.search.text())
        )
        self.search.textChanged.connect(lambda _t: self._search_timer.start())

    def set_translations(self, translations: list[dict[str, Any]]) -> None:
        self.translation_combo.blockSignals(True)
        self.translation_combo.clear()
        for t in translations:
            tid = int(t["id"])
            label = str(t.get("shortname") or t.get("name") or t.get("module") or tid)
            self.translation_combo.addItem(label, tid)
        if translations:
            self.translation_combo.setCurrentIndex(0)
        self.translation_combo.blockSignals(False)

    def set_books(self, books: list[dict[str, Any]]) -> None:
        self._books = books
        self.books_list.clear()
        for b in books:
            item = QListWidgetItem(str(b.get("name", "")))
            item.setData(256, int(b["id"]))
            self.books_list.addItem(item)
        if books:
            self.books_list.setCurrentRow(0)

    def set_chapters(self, chapters: list[int]) -> None:
        while self.chapter_bar_layout.count():
            w = self.chapter_bar_layout.takeAt(0)
            if w and w.widget():
                w.widget().deleteLater()

        if not chapters:
            self.chapter_bar_layout.addWidget(QLabel("", self.chapter_bar))
            return

        for ch in chapters:
            btn = QPushButton(str(ch), self.chapter_bar)
            btn.setFixedSize(40, 32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setObjectName("IconButton")
            btn.clicked.connect(
                lambda checked=False, c=int(ch): self.chapterSelected.emit(c)
            )
            self.chapter_bar_layout.addWidget(btn)
        self.chapter_bar_layout.addStretch(1)

    def set_verses(self, verses: list[dict[str, Any]]) -> None:
        self.verses_list.clear()
        self.verse_preview.clear()
        for v in verses:
            ref = str(v.get("reference", ""))
            text = str(v.get("text", ""))
            no = v.get("verse")
            no_str = str(int(no)) if no is not None else ""
            normalize_preview_text(text)
            display_text = truncate_preview(text, 100)
            display = f"{no_str:>3}  {display_text}".strip() if no_str else display_text
            item = QListWidgetItem(display)
            item.setData(256, ref)
            item.setData(257, text)
            self.verses_list.addItem(item)

        if verses:
            self.verses_list.setCurrentRow(0)

    def current_book_name(self) -> str:
        return self._current_book_name

    def _on_book_changed(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        book_id = int(current.data(256))
        self._current_book_id = book_id
        self._current_book_name = current.text().strip().split("\n")[0]
        self.bookSelected.emit(book_id)

    def _on_translation_changed(self, index: int) -> None:
        tid = self.translation_combo.currentData()
        if tid is None:
            return
        self.translationSelected.emit(int(tid))

    def _on_verse_activated(self, item: QListWidgetItem) -> None:
        ref = str(item.data(256) or "")
        text = str(item.data(257) or "")
        if not ref and not text:
            return
        self.verseActivated.emit(ref, text)

    def _on_add_verse_clicked(self) -> None:
        selected = self.verses_list.selectedItems()
        if not selected:
            return
        if len(selected) == 1:
            self._on_verse_activated(selected[0])
        else:
            verses = []
            for item in selected:
                ref = str(item.data(256) or "")
                text = str(item.data(257) or "")
                if ref or text:
                    verses.append((ref, text))
            if verses:
                self.versesActivated.emit(verses)

    def _on_verse_selection_changed(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            self.verse_preview.clear()
            return
        ref = str(current.data(256) or "")
        text = str(current.data(257) or "")
        if ref:
            self.verse_preview.setPlainText(f"{ref}\n\n{text}")
        else:
            self.verse_preview.setPlainText(text)

    def _on_search_changed(self, text: str) -> None:
        """Filtre les livres selon le texte de recherche."""
        query = text.strip().lower()
        for i in range(self.books_list.count()):
            item = self.books_list.item(i)
            if item is None:
                continue
            book_name = item.text().lower()
            item.setHidden(query != "" and query not in book_name)
