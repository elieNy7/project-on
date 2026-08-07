from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QEvent, QSize, Qt, QTimer, pyqtSignal
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

from app.ui.expose_delegate import ExposeParagraphDelegate
from app.ui.expose_list_delegate import ExposeListDelegate
from app.ui.icons import app_icon
from app.ui.library_list_presentation import (
    COMPACT_PREVIEW_BOX_HEIGHT,
    truncate_preview,
)
from app.ui.shared_tab import TabShell
from app.ui.theme import (
    Colors,
    Radius,
    Spacing,
    Typography,
    get_button_style,
    get_combo_style,
    get_input_style,
    get_list_style,
    get_preview_text_style,
    get_scroll_area_style,
    get_splitter_style,
    get_surface_panel_style,
)


from app.utils.flow_layout import FlowLayout


class ExposeTab(QFrame):
    """Tab for the 'Exposé des Sept Âges de l'Église' book."""

    chapterSelected = pyqtSignal(object)
    pageSelected = pyqtSignal(int)
    paragraphActivated = pyqtSignal(str, str, str)
    searchRequested = pyqtSignal(str)
    translatorChanged = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        self._chapters: list[dict[str, Any]] = []
        self._current_chapter_id: int | None = None
        self._current_chapter_title: str = ""

        # ── Left panel: chapters list ────────────────────────────────────
        self.chapters_list = QListWidget(self)
        self.chapters_list.setMinimumWidth(120)
        self.chapters_list.setStyleSheet(get_list_style(borderless=True))
        self.chapters_list.setItemDelegate(ExposeListDelegate(self.chapters_list))
        self.chapters_list.setUniformItemSizes(True)
        self.chapters_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)

        # Title label above chapters
        chapters_label = QLabel(self.tr("Chapitres"), self)
        chapters_label.setObjectName("PanelTitle")

        left_widget = QWidget()
        left_widget.setStyleSheet("background: transparent;")
        left = QVBoxLayout(left_widget)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(Spacing.SM)
        left.addWidget(chapters_label)
        left.addWidget(self.chapters_list, 1)

        # ── Right panel: page bar + paragraphs ───────────────────────────

        # Page number bar — wraps over multiple rows so every page stays visible
        self.page_bar = QWidget(self)
        self.page_bar.setStyleSheet("background: transparent;")
        self.page_bar_layout = FlowLayout(self.page_bar, margin=2, hSpacing=4, vSpacing=4)

        self._page_buttons: dict[int, QPushButton] = {}
        self._current_page: int | None = None

        self.page_scroll = QScrollArea(self)
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.page_scroll.setWidget(self.page_bar)
        self.page_scroll.setFixedHeight(48)
        self.page_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.page_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.page_scroll.setStyleSheet(get_scroll_area_style())
        self.page_scroll.viewport().installEventFilter(self)

        # Page info label
        self.page_info_label = QLabel("", self)
        self.page_info_label.setStyleSheet(
            f"font-size: {Typography.SIZE_XS}px; color: {Colors.TEXT_MUTED};",
        )

        # Search Bar
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Rechercher dans l'Exposé...")
        self.search_input.setStyleSheet(get_input_style())
        self.search_input.setFixedHeight(38)
        self.search_input.addAction(
            app_icon("search.svg"), QLineEdit.ActionPosition.LeadingPosition
        )
        self.search_input.setClearButtonEnabled(True)

        self.btn_refresh = QPushButton(self)
        self.btn_refresh.setIcon(app_icon("refresh.svg"))
        self.btn_refresh.setToolTip("Actualiser (recharger la base de données)")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setFixedHeight(38)
        self.btn_refresh.setObjectName("IconButton")

        # Paragraphs list
        self.paragraphs_list = QListWidget(self)
        self.paragraphs_list.setStyleSheet(get_list_style(borderless=True))
        self.paragraphs_list.setWordWrap(False)
        self.paragraphs_list.setItemDelegate(ExposeParagraphDelegate(self))
        self.paragraphs_list.setVerticalScrollMode(
            QListWidget.ScrollMode.ScrollPerPixel
        )
        self.paragraphs_list.setTextElideMode(Qt.TextElideMode.ElideRight)

        self.paragraph_preview = QPlainTextEdit(self)
        self.paragraph_preview.setReadOnly(True)
        self.paragraph_preview.setMaximumHeight(COMPACT_PREVIEW_BOX_HEIGHT)
        self.paragraph_preview.setPlaceholderText(
            self.tr("Aperçu du paragraphe sélectionné...")
        )
        self.paragraph_preview.setStyleSheet(f"""
            {get_preview_text_style()}
            QPlainTextEdit {{
                font-family: {Typography.FAMILY};
                font-size: 14px;
            }}
        """)

        # Add button
        self.add_btn = QPushButton("Ajouter à la playlist", self)
        self.add_btn.setIcon(app_icon("plus.svg"))
        self.add_btn.setIconSize(QSize(16, 16))
        self.add_btn.setToolTip("Ajouter le paragraphe sélectionné à la playlist")
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.setStyleSheet(get_button_style())

        # Translator selection
        self.translator_combo = QComboBox(self)
        self.translator_combo.addItem("VGR (Standard)", "VGR")
        self.translator_combo.addItem("SHP (Shekinah)", "SHP")
        self.translator_combo.setMinimumWidth(160)
        self.translator_combo.setFixedHeight(38)
        self.translator_combo.setStyleSheet(get_combo_style())

        right_widget = QWidget()
        right_widget.setStyleSheet("background: transparent;")
        right = QVBoxLayout(right_widget)
        right.setContentsMargins(Spacing.SM, 0, 0, 0)
        right.setSpacing(Spacing.SM)
        right.addWidget(self.page_scroll)
        right.addWidget(self.page_info_label)
        right.addWidget(self.search_input)
        right.addWidget(self.paragraphs_list, 1)
        right.addWidget(self.paragraph_preview)
        right.addWidget(self.add_btn)

        # ── Splitter ─────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(get_splitter_style())

        # ── Unified shell: header + filter bar + splitter body ──
        shell = TabShell("Exposé", "Les Sept Âges de l'Église", "file-text.svg", self)
        shell.header.add_action(self.translator_combo)
        shell.header.add_spacer(8)
        shell.header.add_action(self.btn_refresh)
        shell.filter_bar.set_search(self.search_input)
        shell.set_content(splitter)

        # Signals
        self.chapters_list.currentItemChanged.connect(self._on_chapter_changed)
        self.paragraphs_list.itemDoubleClicked.connect(self._on_paragraph_activated)
        self.paragraphs_list.currentItemChanged.connect(
            self._on_paragraph_selection_changed
        )
        self.add_btn.clicked.connect(self._on_add_clicked)
        self.search_input.textChanged.connect(self._on_search_changed)
        self.translator_combo.currentIndexChanged.connect(self._on_translator_changed)
        self.btn_refresh.clicked.connect(
            lambda: self.translatorChanged.emit(self.current_translator())
        )

    # ── Public API ────────────────────────────────────────────────────────

    def current_translator(self) -> str:
        return self.translator_combo.currentData() or "VGR"

    def set_chapters(self, chapters: list[dict[str, Any]]) -> None:
        self._chapters = chapters
        self.chapters_list.clear()
        for ch in chapters:
            num = ch.get("chapter_num", 0)
            title = ch.get("title", "")

            # Formatting: "Intro" for chapter 0, else "Ch.X"
            num_display = "Intro" if num == 0 else f"Ch.{num}"
            display = f"{num_display}  {title}"

            item = QListWidgetItem(display)
            item.setData(256, ch["id"])
            item.setData(257, title)

            # Set Data for Delegate
            item.setData(Qt.ItemDataRole.UserRole + 1, title)
            item.setData(Qt.ItemDataRole.UserRole + 2, str(num) if num > 0 else "0")

            self.chapters_list.addItem(item)
        if chapters:
            self.chapters_list.setCurrentRow(0)

    def set_search_results(self, paragraphs: list[dict[str, Any]]) -> None:
        """Display search results in the paragraphs list."""
        self.paragraphs_list.clear()
        self.paragraph_preview.clear()

        # Hide page bar when searching
        self.page_scroll.setVisible(False)
        self.page_info_label.setText(f"{len(paragraphs)} résultats")

        for p in paragraphs:
            text = str(p.get("text", ""))
            ref = str(p.get("reference") or p.get("ref") or "")
            marker = str(p.get("marker") or p.get("para_id") or "")

            # Display marker | elided text (delegate will handle the split)
            display = f"{marker or ref} | {text}"
            item = QListWidgetItem(display)
            item.setData(256, ref)
            item.setData(257, text)
            item.setData(258, p.get("title", ""))
            item.setData(259, marker)
            self.paragraphs_list.addItem(item)

        if paragraphs:
            self.paragraphs_list.setCurrentRow(0)

    def set_pages(self, pages: list[int]) -> None:
        # Show page bar when not in search (or search cleared)
        self.page_scroll.setVisible(True)
        # Clear existing page buttons
        while self.page_bar_layout.count():
            w = self.page_bar_layout.takeAt(0)
            if w and w.widget():
                w.widget().deleteLater()
        self._page_buttons.clear()
        self._current_page = None

        if not pages:
            self.page_info_label.setText("")
            self.page_scroll.setFixedHeight(48)
            return

        self.page_info_label.setText(f"{len(pages)} pages")

        fm = None  # shared font metrics — polish once instead of per button
        for pg in pages:
            btn = QPushButton(str(pg), self.page_bar)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._page_btn_style(False))
            fm = self._fit_number_button(btn, str(pg), fm)
            btn.clicked.connect(
                lambda checked=False, p=int(pg): self._on_page_clicked(p)
            )
            self.page_bar_layout.addWidget(btn)
            self._page_buttons[int(pg)] = btn

        QTimer.singleShot(0, self._update_page_bar_height)

    @staticmethod
    def _fit_number_button(btn: QPushButton, text: str, fm=None):
        """Size the button so the number always fits, with comfortable padding.

        Measures with the button's own polished font (stylesheet applied),
        so the result matches what is actually rendered on screen. All page
        buttons share the same stylesheet, so the metrics are computed once
        and reused for the whole bar.
        """
        if fm is None:
            btn.ensurePolished()
            fm = btn.fontMetrics()
        width = max(48, fm.horizontalAdvance(text) + 34)
        btn.setFixedSize(width, 34)
        return fm

    @staticmethod
    def _page_btn_style(active: bool) -> str:
        if active:
            return f"""
                QPushButton {{
                    background: {Colors.ACCENT_GLOW};
                    border: 1px solid {Colors.ACCENT_GLOW_STRONG};
                    border-radius: {Radius.SM}px;
                    color: {Colors.ACCENT_PRIMARY};
                    font-size: {Typography.SIZE_SM}px;
                    font-weight: {Typography.WEIGHT_BOLD};
                }}
            """
        return f"""
            QPushButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: {Radius.SM}px;
                color: {Colors.TEXT_SECONDARY};
                font-size: {Typography.SIZE_SM}px;
                font-weight: {Typography.WEIGHT_SEMIBOLD};
            }}
            QPushButton:hover {{
                background: {Colors.GLASS_MEDIUM};
                color: {Colors.TEXT_PRIMARY};
            }}
            QPushButton:pressed {{
                background: {Colors.ACCENT_GLOW};
                color: {Colors.ACCENT_PRIMARY};
            }}
        """

    def _on_page_clicked(self, pg: int) -> None:
        self.set_current_page(pg)
        self.pageSelected.emit(pg)

    def set_current_page(self, pg: int | None) -> None:
        """Highlight the given page button (None clears the highlight)."""
        self._current_page = pg
        self._apply_page_highlight()
        btn = self._page_buttons.get(pg) if pg is not None else None
        if btn is not None:
            self.page_scroll.ensureWidgetVisible(btn)

    def _apply_page_highlight(self) -> None:
        for num, btn in self._page_buttons.items():
            btn.setStyleSheet(self._page_btn_style(num == self._current_page))

    def _update_page_bar_height(self) -> None:
        """Grow the bar (up to ~4 rows) so wrapped page numbers stay visible."""
        if not self._page_buttons:
            return
        width = self.page_scroll.viewport().width()
        if width <= 0:
            return
        needed = int(self.page_bar_layout.heightForWidth(width)) + 8
        height = max(48, min(needed, 168))
        if height != self.page_scroll.height():
            self.page_scroll.setFixedHeight(height)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.page_scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._update_page_bar_height()
        return super().eventFilter(obj, event)

    def set_paragraphs(self, paragraphs: list[dict[str, Any]]) -> None:
        self.paragraphs_list.clear()
        self.paragraph_preview.clear()
        total = len(paragraphs)
        self.page_info_label.setText(f"{total} paragraphes")
        for p in paragraphs:
            text = str(p.get("text", ""))

            # Use para_id for marker if available (especially for SHP labels like 49-1)
            para_id = p.get("marker") or p.get("para_id")
            if not para_id:
                no = p.get("paragraph_no")
                para_id = f"§{no}" if no is not None else ""

            display_text = truncate_preview(text)

            # Formatted display for delegate (para_id | text)
            display = (
                f"{para_id:>3} | {display_text}".strip() if para_id else display_text
            )

            item = QListWidgetItem(display)
            item.setData(256, str(p.get("ref", "")))
            item.setData(257, text)
            item.setData(259, str(para_id))
            self.paragraphs_list.addItem(item)

        if paragraphs:
            self.paragraphs_list.setCurrentRow(0)

    def current_chapter_title(self) -> str:
        return self._current_chapter_title

    # ── Private slots ─────────────────────────────────────────────────────

    def _on_chapter_changed(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        chapter_id = current.data(256)
        self._current_chapter_id = chapter_id
        self._current_chapter_title = str(current.data(257) or "")
        self.chapterSelected.emit(chapter_id)

    def _on_paragraph_activated(self, item: QListWidgetItem) -> None:
        ref = str(item.data(256) or "")
        text = str(item.data(257) or "")
        title = str(item.data(258) or self._current_chapter_title or "")
        if not ref and not text:
            return
        self.paragraphActivated.emit(ref, text, title)

    def _on_add_clicked(self) -> None:
        item = self.paragraphs_list.currentItem()
        if item is None:
            return
        self._on_paragraph_activated(item)

    def _on_paragraph_selection_changed(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            self.paragraph_preview.clear()
            return
        ref = str(current.data(256) or "")
        text = str(current.data(257) or "")
        if ref:
            self.paragraph_preview.setPlainText(f"{ref}\n\n{text}")
        else:
            self.paragraph_preview.setPlainText(text)

    def _on_search_changed(self, text: str) -> None:
        if not text.strip():
            # If search cleared, we might need to refresh the current page
            # This logic will be handled by the controller emitting pageSelected
            self.pageSelected.emit(-1)  # Special value to signal "restore current page"
            return
        self.searchRequested.emit(text.strip())

    def _on_translator_changed(self, index: int) -> None:
        translator = self.translator_combo.itemData(index) or "VGR"
        self.translatorChanged.emit(translator)
