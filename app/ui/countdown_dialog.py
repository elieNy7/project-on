from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from app.ui.theme import Colors, Radius, Spacing, Typography
from app.utils.translations import tr


class CountdownDialog(QDialog):
    """Configure un compte à rebours diffusé en direct avant le culte
    (projection locale, OBS et NDI)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("countdown"))
        self.setMinimumWidth(420)
        self.setStyleSheet(f"""
            QDialog {{
                background: {Colors.BG_PRIMARY};
            }}
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_SM}px;
            }}
            QLineEdit, QSpinBox {{
                background: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
                padding: 8px 12px;
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_MD}px;
            }}
            QLineEdit:focus, QSpinBox:focus {{
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

        layout.addWidget(QLabel(tr("countdown_message"), self))
        self._message_edit = QLineEdit(self)
        self._message_edit.setText(tr("countdown_message_default"))
        layout.addWidget(self._message_edit)

        layout.addWidget(QLabel(tr("countdown_duration"), self))
        self._minutes_spin = QSpinBox(self)
        self._minutes_spin.setRange(1, 180)
        self._minutes_spin.setValue(10)
        self._minutes_spin.setSuffix(" " + tr("minutes"))
        layout.addWidget(self._minutes_spin)

        layout.addWidget(QLabel(tr("countdown_end_message"), self))
        self._end_message_edit = QLineEdit(self)
        self._end_message_edit.setText(tr("countdown_end_message_default"))
        layout.addWidget(self._end_message_edit)

        hint = QLabel(tr("countdown_hint"), self)
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
            ok_btn.setText(tr("countdown_start"))
        cancel_btn = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn:
            cancel_btn.setText(tr("cancel"))
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._minutes_spin.setFocus()

    def get_config(self) -> tuple[str, int, str]:
        """Retourne (message, durée en secondes, message de fin)."""
        message = self._message_edit.text().strip() or tr("countdown_message_default")
        end_message = (
            self._end_message_edit.text().strip()
            or tr("countdown_end_message_default")
        )
        return message, self._minutes_spin.value() * 60, end_message
