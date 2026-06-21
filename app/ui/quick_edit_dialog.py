from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)

from app.ui.theme import Colors, Radius, Spacing, Typography
from app.utils.translations import tr


class QuickEditDialog(QDialog):
    """A minimal modal dialog to quickly edit the current slide text and reference."""

    def __init__(self, reference: str, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("quick_edit"))
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        self.setStyleSheet(f"""
            QDialog {{
                background: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
            }}
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Typography.SIZE_XS}px;
                font-weight: {Typography.WEIGHT_SEMIBOLD};
            }}
            QLineEdit, QPlainTextEdit {{
                background: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
                padding: 10px;
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_MD}px;
            }}
            QLineEdit:focus, QPlainTextEdit:focus {{
                border-color: {Colors.BORDER_FOCUS};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(Spacing.MD)

        # Reference field
        ref_label = QLabel(tr("quick_edit_ref"))
        self.ref_edit = QLineEdit(reference)
        layout.addWidget(ref_label)
        layout.addWidget(self.ref_edit)

        # Text field
        text_label = QLabel(tr("quick_edit_text"))
        self.text_edit = QPlainTextEdit(text)
        layout.addWidget(text_label)
        layout.addWidget(self.text_edit, 1)

        # Buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        # Style buttons
        save_btn = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        save_btn.setText(tr("quick_edit_apply"))
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ACCENT_PRIMARY};
                color: #000;
                border: none;
                border-radius: {Radius.MD}px;
                padding: 8px 20px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {Colors.ACCENT_LIGHT};
            }}
        """)

        cancel_btn = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.setText(tr("cancel"))
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background: {Colors.SURFACE_HOVER};
                border-color: {Colors.ACCENT_PRIMARY};
            }}
        """)

        layout.addWidget(self.buttons)

    @classmethod
    def edit(cls, reference: str, text: str, parent=None) -> tuple[str, str] | None:
        """Helper to show dialog and return (ref, text) or None."""
        dialog = cls(reference, text, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.ref_edit.text(), dialog.text_edit.toPlainText()
        return None
