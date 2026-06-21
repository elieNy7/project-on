"""Keyboard shortcuts help dialog for Project-On."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import Colors, Radius, Typography
from app.utils.translations import tr

_SHORTCUTS: list[tuple[str, str]] = [
    # (translation_key, shortcut_display)
    ("shortcut_nav_next", "→  /  ↓"),
    ("shortcut_nav_prev", "←  /  ↑"),
    ("shortcut_hide", "B  /  Space"),
    ("shortcut_delete", "Delete"),
    ("shortcut_search", "Ctrl+F"),
    ("shortcut_undo", "Ctrl+Z"),
    ("shortcut_move_up", "Ctrl+↑"),
    ("shortcut_move_down", "Ctrl+↓"),
    ("shortcut_duplicate", "Ctrl+D"),
    ("shortcut_help", "F1"),
    ("shortcut_tab_bible", "Ctrl+1"),
    ("shortcut_tab_hymns", "Ctrl+2"),
    ("shortcut_tab_sermons", "Ctrl+3"),
    ("shortcut_tab_expose", "Ctrl+4"),
    ("shortcut_tab_settings", "Ctrl+5"),
    ("shortcut_projection", "F5"),
    ("shortcut_escape", "Escape"),
]


class ShortcutsDialog(QDialog):
    """Modal dialog listing all available keyboard shortcuts."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("keyboard_shortcuts"))
        self.setMinimumSize(480, 460)
        self.setMaximumSize(560, 640)
        self.setStyleSheet(f"""
            QDialog {{
                background: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.LG}px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Title
        title = QLabel(tr("keyboard_shortcuts"), self)
        title.setStyleSheet(f"""
            font-size: {Typography.SIZE_2XL}px;
            font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_PRIMARY};
        """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Scrollable list
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
        """)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        rows_layout = QVBoxLayout(container)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(2)

        # Header
        header = self._make_row(
            tr("shortcut_action"),
            tr("shortcut_key"),
            is_header=True,
        )
        rows_layout.addWidget(header)

        # Shortcut rows
        for key, shortcut in _SHORTCUTS:
            row = self._make_row(tr(key), shortcut)
            rows_layout.addWidget(row)

        rows_layout.addStretch(1)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        # Close button
        close_btn = QPushButton(tr("close"), self)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_ELEVATED};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
                padding: 8px 32px;
                color: {Colors.ACCENT_PRIMARY};
                font-size: {Typography.SIZE_SM}px;
                font-weight: {Typography.WEIGHT_SEMIBOLD};
            }}
            QPushButton:hover {{
                background: {Colors.SURFACE_HOVER};
                border-color: {Colors.ACCENT_PRIMARY};
            }}
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignCenter)

    @staticmethod
    def _make_row(label: str, shortcut: str, is_header: bool = False) -> QWidget:
        row = QWidget()
        bg = Colors.BG_PRIMARY if not is_header else f"{Colors.ACCENT_PRIMARY}15"
        row.setStyleSheet(f"""
            background: {bg};
            border-radius: {Radius.SM}px;
        """)
        h = QHBoxLayout(row)
        h.setContentsMargins(12, 8, 12, 8)
        h.setSpacing(8)

        weight = Typography.WEIGHT_SEMIBOLD if is_header else Typography.WEIGHT_MEDIUM
        color_label = Colors.ACCENT_LIGHT if is_header else Colors.TEXT_SECONDARY
        color_key = Colors.ACCENT_LIGHT if is_header else Colors.TEXT_PRIMARY

        lbl = QLabel(label)
        lbl.setStyleSheet(f"""
            font-size: {Typography.SIZE_SM}px;
            font-weight: {weight};
            color: {color_label};
            background: transparent;
        """)
        h.addWidget(lbl, 1)

        key_lbl = QLabel(shortcut)
        key_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        if is_header:
            key_lbl.setStyleSheet(f"""
                font-size: {Typography.SIZE_SM}px;
                font-weight: {weight};
                color: {color_key};
                background: transparent;
            """)
        else:
            key_lbl.setStyleSheet(f"""
                font-size: {Typography.SIZE_XS}px;
                font-weight: {Typography.WEIGHT_BOLD};
                color: {color_key};
                background: {Colors.BG_ELEVATED};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 4px;
                padding: 2px 8px;
            """)
        h.addWidget(key_lbl)

        return row
