"""Dialogue de texte rapide : projette immédiatement un texte libre."""

from __future__ import annotations

import re

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from app.ui.icons import app_icon
from app.ui.theme import (
    Colors,
    Radius,
    Spacing,
    Typography,
    get_combo_style,
)
from app.utils.translations import tr


class CustomSlideDialog(QDialog):
    """Dialogue pour créer et projeter un texte rapide."""

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
                font-size: {Typography.SIZE_LABEL}px;
            }}
            QLineEdit {{
                background: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
                padding: 8px 12px;
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_FILTER}px;
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
                font-size: {Typography.SIZE_BODY}px;
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
        self._counter_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: {Typography.SIZE_NUMBER}px;")
        layout.addWidget(self._counter_label)

        self._text_edit.textChanged.connect(self._on_text_changed)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        ok_btn = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText(tr("project"))
            ok_btn.setIcon(app_icon("cast.svg"))
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
            f"color: {color}; font-size: {Typography.SIZE_NUMBER}px; font-weight: {weight};"
        )

    def get_content(self) -> tuple[str, str]:
        return self._title_edit.text(), self._text_edit.toPlainText()
