"""Windows 11 style building blocks shared by the settings screens.

SettingRow is one setting card (label and wrapping description on the
left, control on the right); SettingSection groups cards under a title;
PageHeader is the title row of a settings screen.
"""

from __future__ import annotations

from typing import Callable, Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.icons import app_icon
from app.ui.theme import Colors, Radius, Typography


class SettingRow(QFrame):
    """Windows 11 setting card: label and description on the left (they wrap
    on narrow widths), the control on the right."""

    def __init__(self, label: str, widget: QWidget, description: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("SettingRow")
        self.setStyleSheet(f"""
            QFrame#SettingRow {{
                background: {Colors.BG_CARD};
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: {Radius.SM}px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(16)

        label_col = QVBoxLayout()
        label_col.setSpacing(2)

        lbl = QLabel(label)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"font-size: {Typography.SIZE_BODY}px; color: {Colors.TEXT_PRIMARY};"
            " border: none; background: transparent;"
        )
        label_col.addWidget(lbl)

        if description:
            desc = QLabel(description)
            desc.setWordWrap(True)
            desc.setStyleSheet(
                f"font-size: {Typography.SIZE_META}px; color: {Colors.TEXT_SECONDARY};"
                " border: none; background: transparent;"
            )
            label_col.addWidget(desc)

        layout.addLayout(label_col, 1)
        layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
        self._toggle = widget if isinstance(widget, QCheckBox) else None
        if self._toggle is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        # A switch card toggles when clicked anywhere, like Windows Settings.
        if (
            self._toggle is not None
            and self._toggle.isEnabled()
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self._toggle.toggle()
        super().mouseReleaseEvent(event)


class SettingSection(QFrame):
    """A group of setting cards under a plain section title (Windows 11)."""

    def __init__(self, title: str, icon_name: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet("SettingSection { background: transparent; border: none; }")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)

        header = QHBoxLayout()
        header.setContentsMargins(2, 0, 0, 6)
        header.setSpacing(8)
        if icon_name:
            icon_label = QLabel()
            icon_label.setPixmap(app_icon(icon_name, Colors.TEXT_SECONDARY).pixmap(16, 16))
            icon_label.setStyleSheet("background: transparent; border: none;")
            header.addWidget(icon_label)
        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"font-size: {Typography.SIZE_BODY}px; font-weight: {Typography.WEIGHT_SEMIBOLD};"
            f" color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;"
        )
        header.addWidget(title_label, 1)
        self._layout.addLayout(header)

    def addRow(self, label: str, widget: QWidget, description: str = "") -> None:
        self._layout.addWidget(SettingRow(label, widget, description))

    def addWidget(self, widget: QWidget) -> None:
        if isinstance(widget, QCheckBox) and widget.text():
            # A checkbox label cannot wrap: it becomes a setting card whose
            # (wrapping) title is the label, with the box on the right.
            text = widget.text()
            widget.setText("")
            widget.setAccessibleName(text)
            self._layout.addWidget(SettingRow(text, widget, widget.toolTip()))
            return
        self._layout.addWidget(widget)


class PageHeader(QWidget):
    """Title, one-line explanation and an optional "Réinitialiser" button."""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        on_reset: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(2)
        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"font-size: {Typography.SIZE_DIALOG_TITLE}px; font-weight: {Typography.WEIGHT_SEMIBOLD};"
            f" color: {Colors.TEXT_PRIMARY}; background: transparent;"
        )
        col.addWidget(title_label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setWordWrap(True)
            sub.setStyleSheet(
                f"font-size: {Typography.SIZE_FILTER}px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
            )
            col.addWidget(sub)
        layout.addLayout(col, 1)
        self.reset_button: QPushButton | None = None
        if on_reset is not None:
            self.reset_button = QPushButton("Réinitialiser")
            self.reset_button.setToolTip("Revenir aux réglages par défaut de cet écran")
            self.reset_button.clicked.connect(on_reset)
            layout.addWidget(self.reset_button, 0, Qt.AlignmentFlag.AlignTop)


def fit_combos(root: QWidget, skip: Iterable[QComboBox] = (), chars: int = 12) -> None:
    """Drop-downs keep a reasonable width instead of their longest entry, so
    a screen fits next to the live monitors; the open list shows every
    choice in full."""
    skipped = set(map(id, skip))
    for combo in root.findChildren(QComboBox):
        if id(combo) in skipped:
            continue
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(chars)
        # The selected choice may be clipped: its full text stays reachable.
        combo.setToolTip(combo.currentText())
        combo.currentTextChanged.connect(combo.setToolTip)
