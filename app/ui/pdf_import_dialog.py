"""Professional PDF Import Dialog with preview."""

from __future__ import annotations

import re
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
)

from app.ui.icons import app_icon
from app.ui.theme import Colors, Radius, Typography, get_input_style, get_list_style
from app.utils.translations import tr

_TITLE_RE = re.compile(r"^(?:[A-Z]+-)?(\d+)\.\s*(.+)$")


class PdfImportDialog(QDialog):
    """Dialog for importing hymns from PDF with preview."""

    def __init__(
        self, hymns: list[dict[str, Any]], pdf_name: str, dao=None, parent=None
    ) -> None:
        super().__init__(parent)
        self._hymns = hymns
        self._selected_hymns_indices: set[int] = set(range(len(hymns)))
        self._dao = dao
        self._edits: dict[int, dict[str, Any]] = {}  # index -> {title, stanzas_text}

        self.setWindowTitle(tr("pdf_import_title", name=pdf_name))
        self.setMinimumSize(800, 600)
        self.resize(900, 650)
        self.setStyleSheet(
            f"background: {Colors.BG_SECONDARY}; color: {Colors.TEXT_PRIMARY};"
        )

        self._init_ui(pdf_name)
        self._populate_list()

    def _init_ui(self, pdf_name: str) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header
        header = QLabel(tr("pdf_found", count=len(self._hymns), name=pdf_name))
        header.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {Colors.TEXT_PRIMARY};"
        )
        layout.addWidget(header)

        # Prefix input
        prefix_group = QGroupBox(tr("pdf_config"))
        prefix_layout = QHBoxLayout(prefix_group)

        prefix_label = QLabel(tr("pdf_prefix"))
        prefix_label.setStyleSheet(f"font-weight: 500; color: {Colors.TEXT_SECONDARY};")
        self.prefix_input = QLineEdit()
        self.prefix_input.setPlaceholderText(tr("pdf_prefix_placeholder"))
        self.prefix_input.setStyleSheet(get_input_style())
        self.prefix_input.setMaximumWidth(100)
        self.prefix_input.textChanged.connect(self._update_preview)

        start_label = QLabel(tr("pdf_start_number"))
        start_label.setStyleSheet(f"font-weight: 500; color: {Colors.TEXT_SECONDARY};")
        self.start_number = QSpinBox()
        self.start_number.setMinimum(1)
        self.start_number.setMaximum(9999)
        self.start_number.setValue(1)
        self.start_number.valueChanged.connect(self._update_preview)
        self.start_number.setStyleSheet(get_input_style())

        prefix_layout.addWidget(prefix_label)
        prefix_layout.addWidget(self.prefix_input)
        prefix_layout.addSpacing(20)
        prefix_layout.addWidget(start_label)
        prefix_layout.addWidget(self.start_number)
        prefix_layout.addStretch()

        layout.addWidget(prefix_group)

        # Splitter for list and preview
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Hymns list
        left_frame = QFrame()
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(0, 0, 0, 0)

        list_label = QLabel(tr("pdf_hymns_to_import"))
        list_label.setStyleSheet(
            f"font-weight: 500; margin-bottom: 4px; color: {Colors.TEXT_SECONDARY};"
        )
        left_layout.addWidget(list_label)

        search_label = QLabel(tr("search"))
        search_label.setStyleSheet(
            f"font-weight: 500; margin-bottom: 2px; color: {Colors.TEXT_SECONDARY};"
        )
        left_layout.addWidget(search_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr("search_hymns_placeholder"))
        self.search_input.setStyleSheet(get_input_style())
        self.search_input.textChanged.connect(self._filter_list)
        left_layout.addWidget(self.search_input)

        self.hymns_list = QListWidget()
        self.hymns_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.hymns_list.setStyleSheet(get_list_style())
        self.hymns_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.hymns_list.currentItemChanged.connect(self._on_current_changed)
        left_layout.addWidget(self.hymns_list)

        # Select all / none buttons
        btn_row = QHBoxLayout()
        self.select_all_btn = QPushButton(tr("pdf_select_all"))
        self.select_all_btn.clicked.connect(self._select_all)
        self.select_none_btn = QPushButton(tr("pdf_select_none"))
        self.select_none_btn.clicked.connect(self._select_none)
        btn_row.addWidget(self.select_all_btn)
        btn_row.addWidget(self.select_none_btn)
        left_layout.addLayout(btn_row)

        splitter.addWidget(left_frame)

        # Right: Preview
        right_frame = QFrame()
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(0, 0, 0, 0)

        preview_label = QLabel(tr("pdf_preview"))
        preview_label.setStyleSheet(
            f"font-weight: 500; margin-bottom: 4px; color: {Colors.TEXT_SECONDARY};"
        )
        right_layout.addWidget(preview_label)

        self.preview_text = QTextEdit()
        self.preview_text.setStyleSheet(f"""
            QTextEdit {{
                background: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.SM}px;
                padding: 12px;
                font-family: 'Segoe UI', sans-serif;
                font-size: {Typography.SIZE_MD}px;
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        self.preview_text.textChanged.connect(self._on_preview_edited)
        right_layout.addWidget(self.preview_text)

        edit_hint = QLabel(
            "💡 Vous pouvez modifier le texte ci-dessus avant l'importation."
        )
        edit_hint.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {Typography.SIZE_XS}px; font-style: italic;"
        )
        right_layout.addWidget(edit_hint)

        splitter.addWidget(right_frame)
        splitter.setSizes([350, 450])

        layout.addWidget(splitter, 1)

        # Status
        self.status_label = QLabel()
        self.status_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {Typography.SIZE_SM}px;"
        )
        layout.addWidget(self.status_label)

        # Buttons
        button_box = QDialogButtonBox()
        self.import_btn = QPushButton(tr("pdf_import"))
        self.import_btn.setIcon(app_icon("file-plus.svg"))
        self.import_btn.setDefault(True)
        self.import_btn.clicked.connect(self.accept)

        cancel_btn = QPushButton(tr("cancel"))
        cancel_btn.clicked.connect(self.reject)

        button_box.addButton(self.import_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        button_box.addButton(cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)

        layout.addWidget(button_box)

    def _populate_list(self) -> None:
        """Populate the hymns list with duplicate detection."""
        self.hymns_list.clear()
        for i, hymn in enumerate(self._hymns):
            title = hymn.get("title", f"Cantique {i + 1}")
            # Check for duplicate
            is_dup = self._dao.hymn_exists(title) if self._dao else False

            stanza_count = len(hymn.get("stanzas", []))
            display = f"{title} ({stanza_count} strophes)"
            if is_dup:
                display += " [Déjà présent]"

            item = QListWidgetItem(display)
            if is_dup:
                item.setForeground(QColor(Colors.TEXT_MUTED))

            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setSelected(not is_dup)  # Deselect duplicates by default
            self.hymns_list.addItem(item)

        self._update_status()
        if self.hymns_list.count() > 0:
            self.hymns_list.setCurrentRow(0)

    def _filter_list(self, text: str) -> None:
        """Filter the hymns list."""
        query = text.lower().strip()
        for i in range(self.hymns_list.count()):
            item = self.hymns_list.item(i)
            item.setHidden(query not in item.text().lower())

    def _on_selection_changed(self) -> None:
        """Update selected hymns list."""
        self._selected_hymns_indices = set()
        for i in range(self.hymns_list.count()):
            item = self.hymns_list.item(i)
            if item and item.isSelected():
                idx = item.data(Qt.ItemDataRole.UserRole)
                if idx is not None:
                    self._selected_hymns_indices.add(idx)
        self._update_status()

    def _on_current_changed(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        """Show preview of current hymn."""
        if current is None:
            self.preview_text.clear()
            return

        idx = current.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx >= len(self._hymns):
            return

        hymn = self._hymns[idx]
        self._show_preview(hymn)

    def _show_preview(self, hymn: dict[str, Any]) -> None:
        """Display hymn preview."""
        # Block signals to avoid recursive edits
        self.preview_text.blockSignals(True)

        idx = self.hymns_list.currentRow()
        if idx >= 0:
            item = self.hymns_list.item(idx)
            inner_idx = item.data(Qt.ItemDataRole.UserRole)
            if inner_idx in self._edits:
                # Show edited raw text
                self.preview_text.setPlainText(self._edits[inner_idx]["raw"])
                self.preview_text.blockSignals(False)
                return

        prefix = self.prefix_input.text().strip().upper() or tr("pdf_default_prefix")
        number = hymn.get("number", 1)

        # Build raw text for editing
        original_title = hymn.get("title", tr("pdf_untitled"))
        match = _TITLE_RE.match(original_title)
        name = match.group(2) if match else original_title

        final_title = f"{prefix}-{number}. {name}"
        stanzas = hymn.get("stanzas", [])

        raw_text = f"TITRE: {final_title}\n\n"
        for i, s in enumerate(stanzas):
            raw_text += f"{s}\n\n"

        self.preview_text.setPlainText(raw_text.strip())
        self.preview_text.blockSignals(False)

    def _on_preview_edited(self) -> None:
        """Handle manual edits in the preview panel."""
        item = self.hymns_list.currentItem()
        if not item:
            return

        idx = item.data(Qt.ItemDataRole.UserRole)
        raw_content = self.preview_text.toPlainText()

        # Parse title and stanzas from edited raw text
        lines = raw_content.split("\n")
        title = ""
        stanzas = []
        current_stanza = []

        for line in lines:
            if line.startswith("TITRE: "):
                title = line[len("TITRE: ") :].strip()
            elif not line.strip():
                if current_stanza:
                    stanzas.append("\n".join(current_stanza))
                    current_stanza = []
            else:
                current_stanza.append(line)

        if current_stanza:
            stanzas.append("\n".join(current_stanza))

        self._edits[idx] = {
            "title": title,
            "stanzas": stanzas,
            "raw": raw_content,
        }

        # Update list item text to reflect new title if changed
        if title:
            item.setText(f"{title} ({len(stanzas)} strophes)")

    def _update_preview(self) -> None:
        """Update preview when prefix changes."""
        current = self.hymns_list.currentItem()
        if current:
            self._on_current_changed(current, None)

    def _update_status(self) -> None:
        """Update status label."""
        total = len(self._hymns)
        selected = len(self._selected_hymns_indices)
        self.status_label.setText(tr("pdf_status", selected=selected, total=total))
        self.import_btn.setEnabled(
            selected > 0 and bool(self.prefix_input.text().strip())
        )

    def _select_all(self) -> None:
        """Select all hymns."""
        self.hymns_list.selectAll()

    def _select_none(self) -> None:
        """Deselect all hymns."""
        self.hymns_list.clearSelection()

    def get_prefix(self) -> str:
        """Get the prefix entered by user."""
        return self.prefix_input.text().strip().upper() or tr("pdf_default_prefix")

    def get_start_number(self) -> int:
        """Get the starting number."""
        return self.start_number.value()

    def get_selected_hymns(self) -> list[dict[str, Any]]:
        """Get list of selected hymns with modifications."""
        result = []
        for i in sorted(list(self._selected_hymns_indices)):
            hymn = self._hymns[i]
            if i in self._edits:
                result.append(
                    {
                        "number": hymn.get("number"),
                        "title": self._edits[i]["title"],
                        "stanzas": self._edits[i]["stanzas"],
                    }
                )
            else:
                # Apply title logic if not edited
                prefix = self.get_prefix()
                number = hymn.get("number", i + 1)
                original_title = hymn.get("title", "")
                match = _TITLE_RE.match(original_title)
                name = match.group(2) if match else original_title

                result.append(
                    {
                        "number": number,
                        "title": f"{prefix}-{number}. {name}",
                        "stanzas": hymn.get("stanzas", []),
                    }
                )
        return result
