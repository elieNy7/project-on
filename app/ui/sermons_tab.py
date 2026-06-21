from __future__ import annotations

import re
from typing import Any

from PyQt6.QtCore import QPoint, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
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

from app.ui.icons import app_icon
from app.ui.library_list_presentation import (
    COMPACT_PREVIEW_BOX_HEIGHT,
    normalize_preview_text,
)
from app.ui.sermon_delegate import SermonParagraphDelegate
from app.ui.sermon_list_delegate import SermonListDelegate
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
    get_splitter_style,
    get_surface_panel_style,
)


class SermonsTab(QFrame):
    sermonSelected = pyqtSignal(object)
    paragraphActivated = pyqtSignal(str, str)
    filtersChanged = pyqtSignal()
    paragraphSearchRequested = pyqtSignal(str)  # query text

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        self._sermons: list[dict[str, Any]] = []
        self._current_sermon_title: str = ""
        self._current_sermon_date: str = ""

        # Filters


        self.year_combo = QComboBox(self)
        self.year_combo.addItem("Toutes années", None)
        self.year_combo.setEnabled(False)
        self.year_combo.setMinimumWidth(100)
        self.year_combo.setStyleSheet(get_combo_style())

        self.translator_combo = QComboBox(self)
        self.translator_combo.addItem("Tous les sermons", None)
        self.translator_combo.setEnabled(False)
        self.translator_combo.setStyleSheet(get_combo_style())

        # Search
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Rechercher un sermon...")
        self.search.setClearButtonEnabled(True)
        self.search.setStyleSheet(get_input_style())

        # Paragraph search (right panel)
        self._para_search_mode = False
        self._para_search = QLineEdit(self)
        self._para_search.setPlaceholderText("Rechercher dans tous les paragraphes...")
        self._para_search.setClearButtonEnabled(True)
        self._para_search.setStyleSheet(get_input_style())
        self._para_search.hide()

        self._jump_to_para = QLineEdit(self)
        self._jump_to_para.setPlaceholderText("Filtrer (ex: §12 ou mot)...")
        self._jump_to_para.setFixedWidth(180)
        self._jump_to_para.setClearButtonEnabled(True)
        self._jump_to_para.setStyleSheet(
            get_input_style() + f"border-radius: {Radius.MD}px; padding: 4px 8px;"
        )

        self._copy_btn = QPushButton("Copier", self)
        self._copy_btn.setIcon(app_icon("copy.svg"))
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.setObjectName("IconButton")

        self._para_search_btn = QPushButton(self)
        self._para_search_btn.setIcon(
            app_icon("search.svg")
        )  # Using generic search icon
        self._para_search_btn.setToolTip("Recherche globale dans les paragraphes")
        self._para_search_btn.setCheckable(True)
        self._para_search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._para_search_btn.setObjectName("IconButton")

        # Sermons list
        self.sermons_count_label = QLabel("0 sermons", self)
        self.sermons_count_label.setStyleSheet(
            f"font-size: {Typography.SIZE_XS}px; color: {Colors.TEXT_MUTED};"
        )

        self.sermons_list = QListWidget(self)
        self.sermons_list.setMinimumWidth(140)
        self.sermons_list.setStyleSheet(get_list_style())
        self.sermons_list.setItemDelegate(SermonListDelegate(self.sermons_list))
        self.sermons_list.setUniformItemSizes(True)
        self.sermons_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)

        # Paragraphs list
        self.paragraphs_count_label = QLabel("0 paragraphes", self)
        self.paragraphs_count_label.setStyleSheet(
            f"font-size: {Typography.SIZE_XS}px; color: {Colors.TEXT_MUTED};"
        )

        # Search row (search input + toggle button)
        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(Spacing.SM)
        search_row.addWidget(self.search, 1)
        search_row.addWidget(self._para_search_btn)

        self.btn_refresh = QPushButton(self)
        self.btn_refresh.setIcon(app_icon("refresh.svg"))
        self.btn_refresh.setToolTip("Actualiser (recharger la base de données)")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setObjectName("IconButton")
        search_row.addWidget(self.btn_refresh)

        self.paragraphs_list = QListWidget(self)
        self.paragraphs_list.setStyleSheet(get_list_style())
        self.paragraphs_list.setItemDelegate(
            SermonParagraphDelegate(self.paragraphs_list)
        )
        self.paragraphs_list.setVerticalScrollMode(
            QListWidget.ScrollMode.ScrollPerPixel
        )
        self.paragraphs_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.paragraphs_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.paragraphs_list.customContextMenuRequested.connect(
            self._on_paragraph_context_menu
        )

        self.paragraph_preview = QPlainTextEdit(self)
        self.paragraph_preview.setReadOnly(True)
        self.paragraph_preview.setMaximumHeight(COMPACT_PREVIEW_BOX_HEIGHT)
        self.paragraph_preview.setPlaceholderText("Aperçu du paragraphe sélectionné...")
        self.paragraph_preview.setStyleSheet(
            get_preview_text_style()
        )

        # Preview header with copy button
        preview_header = QFrame()
        preview_header.setStyleSheet(
            f"background: {Colors.BG_TERTIARY}; border: none; border-radius: {Radius.MD}px;"
        )
        preview_header_layout = QHBoxLayout(preview_header)
        preview_header_layout.setContentsMargins(8, 4, 8, 4)
        preview_label = QLabel("APERÇU DU PARAGRAPHE")
        preview_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 1px;"
        )
        preview_header_layout.addWidget(preview_label)
        preview_header_layout.addStretch()
        preview_header_layout.addWidget(self._copy_btn)

        # Add button
        self.add_paragraph_btn = QPushButton(self)
        self.add_paragraph_btn.setText("Ajouter à la playlist")
        self.add_paragraph_btn.setIcon(app_icon("plus.svg"))
        self.add_paragraph_btn.setIconSize(QSize(16, 16))
        self.add_paragraph_btn.setToolTip(
            "Ajouter le paragraphe sélectionné à la playlist"
        )
        self.add_paragraph_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_paragraph_btn.setStyleSheet(get_button_style())

        # Filters container
        self.filters_container = QFrame(self)
        self.filters_container.setStyleSheet(get_surface_panel_style())

        filters_main_layout = QVBoxLayout(self.filters_container)
        filters_main_layout.setContentsMargins(
            Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM
        )
        filters_main_layout.setSpacing(Spacing.SM)

        # Filters row 1: language, year, translator
        filters_row = QHBoxLayout()
        filters_row.setContentsMargins(0, 0, 0, 0)
        filters_row.setSpacing(Spacing.SM)
        filters_row.addWidget(self.year_combo)
        filters_row.addWidget(self.translator_combo, 1)

        # Search row is already defined above, we just reuse it or redefine it carefully. Wait, let's keep it as is since we defined it above and we shouldn't redefine it.
        # Oh, in the original it redefines search_row. Let's merge the refresh button into the second search_row definition.

        search_row2 = QHBoxLayout()
        search_row2.setContentsMargins(0, 0, 0, 0)
        search_row2.setSpacing(Spacing.SM)
        search_row2.addWidget(self.search, 1)
        search_row2.addWidget(self._para_search_btn)
        search_row2.addWidget(self.btn_refresh)

        filters_main_layout.addLayout(filters_row)
        filters_main_layout.addLayout(search_row2)

        # Left panel
        left_widget = QWidget()
        left_widget.setStyleSheet("background: transparent;")
        left = QVBoxLayout(left_widget)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(Spacing.SM)
        left.addWidget(self.filters_container)
        left.addWidget(self.sermons_count_label)
        left.addWidget(self.sermons_list, 1)

        # Header row for paragraphs: Count + Jump to
        para_header_row = QHBoxLayout()
        para_header_row.addWidget(self.paragraphs_count_label)
        para_header_row.addStretch()
        para_header_row.addWidget(self._jump_to_para)

        right_widget = QWidget()
        right_widget.setStyleSheet("background: transparent;")
        right = QVBoxLayout(right_widget)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(Spacing.SM)
        right.addWidget(self._para_search)
        right.addLayout(para_header_row)
        right.addWidget(self.paragraphs_list, 1)
        right.addWidget(preview_header)
        right.addWidget(self.paragraph_preview)
        right.addWidget(self.add_paragraph_btn)

        # Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(get_splitter_style())

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)
        layout.addWidget(splitter, 1)

        self.sermons_list.currentItemChanged.connect(self._on_sermon_changed)
        self.paragraphs_list.itemDoubleClicked.connect(self._on_paragraph_activated)
        self.paragraphs_list.currentItemChanged.connect(
            self._on_paragraph_selection_changed
        )
        self.add_paragraph_btn.clicked.connect(self._on_add_paragraph_clicked)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self.filtersChanged.emit)
        self.search.textChanged.connect(lambda _t: self._search_timer.start())

        self.translator_combo.currentIndexChanged.connect(
            lambda _i: self.filtersChanged.emit()
        )
        self.year_combo.currentIndexChanged.connect(
            lambda _i: self.filtersChanged.emit()
        )
        self._jump_to_para.textChanged.connect(self._filter_paragraphs)
        self._copy_btn.clicked.connect(self._on_copy_paragraph)

        # Paragraph search wiring
        self._para_search_btn.clicked.connect(self._toggle_para_search)
        self._para_search_timer = QTimer(self)
        self._para_search_timer.setSingleShot(True)
        self._para_search_timer.setInterval(400)
        self._para_search_timer.timeout.connect(self._emit_para_search)
        self._para_search.textChanged.connect(
            lambda _t: self._para_search_timer.start()
        )
        self.btn_refresh.clicked.connect(self.filtersChanged.emit)

    def current_language(self) -> str | None:
        return None

    def current_query(self) -> str:
        return str(self.search.text() or "").strip()

    def current_translator(self) -> str | None:
        v = self.translator_combo.currentData()
        return str(v) if v is not None else None

    def current_date_from(self) -> str | None:
        y = self.year_combo.currentData()
        if y is None:
            return None
        if str(y) == "nodate":
            return "__NODATE__"
        return f"{int(y):04d}-01-01"

    def current_date_to(self) -> str | None:
        y = self.year_combo.currentData()
        if y is None:
            return None
        if str(y) == "nodate":
            return "__NODATE__"
        return f"{int(y):04d}-12-31"

    def set_years(self, years: list[int]) -> None:
        current = self.year_combo.currentData()
        self.year_combo.blockSignals(True)
        try:
            self.year_combo.clear()
            self.year_combo.addItem("📅 Toutes années", None)
            self.year_combo.addItem("❓ Sans date", "nodate")
            for y in years:
                yi = int(y)
                label = "00" if yi == 0 else str(yi)
                self.year_combo.addItem(label, yi)
            enabled = bool(years)
            self.year_combo.setEnabled(enabled)
            if current is not None:
                idx = -1
                if str(current) != "nodate":
                    try:
                        idx = self.year_combo.findData(int(current))
                    except Exception:
                        idx = -1
                if idx < 0:
                    idx = self.year_combo.findData(str(current))
                if idx >= 0:
                    self.year_combo.setCurrentIndex(idx)
                else:
                    self.year_combo.setCurrentIndex(0)
        finally:
            self.year_combo.blockSignals(False)

    def set_translators(self, translators: list[str]) -> None:
        current = self.current_translator()
        self.translator_combo.blockSignals(True)
        try:
            self.translator_combo.clear()
            self.translator_combo.addItem("👤 Toutes traductions", None)
            for t in translators:
                label = str(t)
                self.translator_combo.addItem(label, label)
            self.translator_combo.setEnabled(bool(translators))
            if current is not None:
                idx = self.translator_combo.findData(current)
                if idx >= 0:
                    self.translator_combo.setCurrentIndex(idx)
                else:
                    self.translator_combo.setCurrentIndex(0)
            else:
                self.translator_combo.setCurrentIndex(0)
        finally:
            self.translator_combo.blockSignals(False)

    def set_sermons(self, sermons: list[dict[str, Any]]) -> None:
        self._sermons = sermons
        self.sermons_list.clear()

        # Update count label
        count = len(sermons)
        self.sermons_count_label.setText(f"{count} sermon{'s' if count != 1 else ''}")

        for s in sermons:
            title = str(s.get("title", ""))
            date_code = str(s.get("date_code", "") or "")
            date = date_code or str(s.get("date", "") or "")
            translator = str(s.get("translator", "") or "")
            location = str(s.get("location", "") or "")
            tradition = str(s.get("tradition", "") or "")

            # Use translator if tradition is generic "VGR" but we want specific translator info?
            # Actually delegate shows Tradition/Translator badge.
            badge_text = translator or tradition

            # The delegate handles formatting, but we provide a fallback display text
            # for accessibility or if delegate fails
            display = f"{title}"

            item = QListWidgetItem(display)
            item.setData(256, s["id"])
            item.setData(257, title)

            # Set Data for Delegate
            # UserRole = 32
            item.setData(Qt.ItemDataRole.UserRole + 1, title)
            item.setData(Qt.ItemDataRole.UserRole + 2, date)
            item.setData(Qt.ItemDataRole.UserRole + 3, location)
            item.setData(Qt.ItemDataRole.UserRole + 4, badge_text)

            self.sermons_list.addItem(item)

        if sermons:
            # Safely select first item
            if self.sermons_list.count() > 0:
                self.sermons_list.setCurrentRow(0)

    def set_paragraphs(self, paragraphs: list[dict[str, Any]]) -> None:
        self._jump_to_para.blockSignals(True)
        self._jump_to_para.clear()
        self._jump_to_para.blockSignals(False)

        self.paragraphs_list.clear()
        self.paragraph_preview.clear()

        # Update count label
        count = len(paragraphs)
        self.paragraphs_count_label.setText(
            f"{count} paragraphe{'s' if count != 1 else ''}"
        )

        for p in paragraphs:
            no = p.get("paragraph_no")
            para_id = str(p.get("marker") or p.get("para_id") or "")
            text = str(p.get("text", ""))

            # Clean up text for list display (single line)
            clean_text = normalize_preview_text(text)

            # Marker logic: prio para_id (starts with E-), then (n) if at text start
            marker = ""
            if para_id:
                marker = para_id
            else:
                # Try to extract (n) from beginning of text
                m = re.match(r"^\((\d+)\)", text.strip())
                if m:
                    marker = f"({m.group(1)})"
                elif no is not None:
                    marker = f"§{int(no):03d}"

            # Format item for delegate
            # We put the marker in the main text so elidedText can use it if needed,
            # though the delegate handles display.
            display = f"{marker} | {clean_text}"
            item = QListWidgetItem(display)

            ref = str(p.get("reference", "") or p.get("ref", ""))
            item.setData(256, ref)
            item.setData(257, text)
            item.setData(258, marker)
            self.paragraphs_list.addItem(item)

        if paragraphs:
            if self.paragraphs_list.count() > 0:
                self.paragraphs_list.setCurrentRow(0)

    def current_sermon_title(self) -> str:
        return self._current_sermon_title

    def current_sermon_date(self) -> str:
        return self._current_sermon_date

    def _on_sermon_changed(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        sermon_id = current.data(256)
        self._current_sermon_title = str(current.data(257) or "")
        self._current_sermon_date = str(
            current.data(Qt.ItemDataRole.UserRole + 2) or ""
        )
        self.sermonSelected.emit(sermon_id)

    def _on_paragraph_activated(self, item: QListWidgetItem) -> None:
        ref = str(item.data(256) or "")
        text = str(item.data(257) or "")
        if not ref and not text:
            return
        self.paragraphActivated.emit(ref, text)

    def _on_add_paragraph_clicked(self) -> None:
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

    def _filter_paragraphs(self, text: str) -> None:
        query = text.strip().lower()
        if not query:
            for i in range(self.paragraphs_list.count()):
                self.paragraphs_list.item(i).setHidden(False)
            total = self.paragraphs_list.count()
            self.paragraphs_count_label.setText(
                f"{total} paragraphe{'s' if total != 1 else ''}"
            )
            return

        count_visible = 0
        is_num_query = bool(re.match(r"^[§¶]?\d+$", query))
        target_num = re.sub(r"\D", "", query) if is_num_query else ""

        for i in range(self.paragraphs_list.count()):
            item = self.paragraphs_list.item(i)
            display_text = item.text().lower()
            actual_text = str(item.data(257)).lower()
            marker_text = str(item.data(258) or "").lower()
            hide = True

            if is_num_query and target_num:
                # Search for Paragraph number in display text (¶1, §1, (1), etc.)
                m1 = re.search(r"[§¶](\d+)", f"{marker_text} {display_text}")
                m2 = re.match(r"^\((\d+)\)", display_text)
                val1 = m1.group(1) if m1 else ""
                val2 = m2.group(1) if m2 else ""
                
                # Check for exact matches on the number
                target_int = int(target_num)
                if (val1 and int(val1) == target_int) or (
                    val2 and int(val2) == target_int
                ):
                    hide = False
                elif query in marker_text or query in display_text or query in actual_text:
                    hide = False
            else:
                if query in marker_text or query in display_text or query in actual_text:
                    hide = False

            item.setHidden(hide)
            if not hide:
                count_visible += 1

        self.paragraphs_count_label.setText(
            f"{count_visible} résultat{'s' if count_visible != 1 else ''}"
        )

    def _on_copy_paragraph(self) -> None:
        item = self.paragraphs_list.currentItem()
        if item is None:
            return
        text = str(item.data(257) or "")
        QApplication.clipboard().setText(text)

        old_text = self._copy_btn.text()
        self._copy_btn.setText("Copié !")
        QTimer.singleShot(1500, lambda: self._copy_btn.setText(old_text))

    def _on_paragraph_context_menu(self, pos: QPoint) -> None:
        item = self.paragraphs_list.itemAt(pos)
        if not item:
            return

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {Colors.BG_ELEVATED};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 24px;
                border-radius: {Radius.SM}px;
                color: {Colors.TEXT_PRIMARY};
            }}
            QMenu::item:selected {{
                background-color: {Colors.ACCENT_PRIMARY};
                color: white;
            }}
        """)

        copy_action = menu.addAction("Copier le texte")
        add_action = menu.addAction("Ajouter à la playlist")

        action = menu.exec(self.paragraphs_list.mapToGlobal(pos))

        if action == copy_action:
            self._on_copy_paragraph()
        elif action == add_action:
            self._on_paragraph_activated(item)

    # ── Paragraph global search ──────────────────────────────────────

    def _toggle_para_search(self) -> None:
        self._para_search_mode = self._para_search_btn.isChecked()
        self._para_search.setVisible(self._para_search_mode)
        if self._para_search_mode:
            self._para_search.setFocus()
            self.paragraphs_count_label.setText("Entrez un terme de recherche...")
            self.paragraphs_list.clear()
        else:
            self._para_search.clear()
            # Restore normal mode: re-select current sermon to reload its paragraphs
            current = self.sermons_list.currentItem()
            if current is not None:
                sermon_id = current.data(256)
                self.sermonSelected.emit(sermon_id)

    def _emit_para_search(self) -> None:
        query = self._para_search.text().strip()
        if len(query) >= 3:
            self.paragraphSearchRequested.emit(query)
        elif query == "":
            self.paragraphs_list.clear()
            self.paragraphs_count_label.setText("Min. 3 caractères...")

    def set_search_results(self, results: list[dict]) -> None:
        """Display global paragraph search results."""
        self.paragraphs_list.clear()
        self.paragraph_preview.clear()
        count = len(results)
        self.paragraphs_count_label.setText(
            f"{count} résultat{'s' if count != 1 else ''}"
        )
        for r in results:
            sermon_title = str(r.get("sermon_title", ""))
            text = str(r.get("text", ""))
            para_no = r.get("paragraph_no", 0)
            para_id = str(r.get("marker") or r.get("para_id") or "")

            clean_text = normalize_preview_text(text)

            # Marker logic: same as set_paragraphs but prefix with title
            marker = ""
            if para_id:
                marker = para_id
            else:
                m = re.match(r"^\((\d+)\)", text.strip())
                if m:
                    marker = f"({m.group(1)})"
                else:
                    marker = f"§{para_no}"

            display = f"[{sermon_title}] {marker} | {clean_text}"
            item = QListWidgetItem(display)

            ref = str(r.get("reference") or r.get("ref") or "")

            item.setData(256, ref)
            item.setData(257, text)
            item.setData(258, marker)
            self.paragraphs_list.addItem(item)

        if results:
            if self.paragraphs_list.count() > 0:
                self.paragraphs_list.setCurrentRow(0)
