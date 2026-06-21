from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from app.ui.icons import app_icon
from app.ui.theme import Colors, Radius, Spacing, Typography


class SidebarButton(QPushButton):
    """Professional sidebar button with a refined active state."""

    def __init__(self, text: str, icon_name: str, parent=None) -> None:
        super().__init__(parent)
        self._icon_name = icon_name

        self.setText(text)
        self.setIconSize(QSize(20, 20))
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(42)

        self._base_style = f"""
            QPushButton {{
                text-align: left;
                padding: 9px 12px 9px 14px;
                border: none;
                border-radius: {Radius.SM}px;
                background: transparent;
                color: {Colors.TEXT_SECONDARY};
                font-family: {Typography.PRIMARY_FAMILY};
                font-size: {Typography.SIZE_MD}px;
                font-weight: {Typography.WEIGHT_MEDIUM};
                margin: 0 0 2px 0;
                letter-spacing: 0;
            }}
            QPushButton:hover {{
                background: {Colors.GLASS_MEDIUM};
                color: {Colors.TEXT_PRIMARY};
            }}
        """

        self._checked_style = f"""
            QPushButton {{
                text-align: left;
                padding: 9px 12px 9px 14px;
                border: none;
                border-radius: {Radius.SM}px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(216, 170, 90, 0.20),
                    stop:1 rgba(216, 170, 90, 0.07)
                );
                color: {Colors.TEXT_PRIMARY};
                font-family: {Typography.PRIMARY_FAMILY};
                font-size: {Typography.SIZE_MD}px;
                font-weight: {Typography.WEIGHT_SEMIBOLD};
                margin: 0 0 2px 0;
                letter-spacing: 0;
            }}
            QPushButton:hover {{
                background: rgba(216, 170, 90, 0.18);
            }}
        """

        self._update_style(False)

    def _update_style(self, checked: bool) -> None:
        icon_color = Colors.ACCENT_PRIMARY if checked else Colors.TEXT_SECONDARY
        self.setIcon(app_icon(self._icon_name, icon_color))
        self.setStyleSheet(self._checked_style if checked else self._base_style)

    def setChecked(self, checked: bool) -> None:
        super().setChecked(checked)
        self._update_style(checked)


class Sidebar(QFrame):
    """Professional vertical navigation sidebar."""

    currentChanged = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(196)
        self.setObjectName("Sidebar")

        self.setStyleSheet(
            f"""
            QFrame#Sidebar {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {Colors.SIDEBAR_GRADIENT_START},
                    stop:1 {Colors.BG_SECONDARY}
                );
                border: none;
            }}
            """
        )

        self._buttons: list[SidebarButton] = []
        self._current_index = 0

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 14, 12, 12)
        self._layout.setSpacing(Spacing.SM)

        self._build_header()

        self._nav_container = QWidget(self)
        self._nav_layout = QVBoxLayout(self._nav_container)
        self._nav_layout.setContentsMargins(0, 0, 0, 0)
        self._nav_layout.setSpacing(Spacing.XS)
        self._layout.addWidget(self._nav_container)
        self._layout.addStretch(1)

        self._footer = QLabel("Project-On", self)
        self._footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._footer.setStyleSheet(
            f"""
            QLabel {{
                color: {Colors.TEXT_MUTED};
                font-size: {Typography.SIZE_XS}px;
                padding: 6px 4px 0 4px;
                letter-spacing: 0.7px;
            }}
            """
        )
        self._layout.addWidget(self._footer)

    def _build_header(self) -> None:
        header = QFrame(self)
        header.setStyleSheet(
            f"""
            QFrame {{
                background: {Colors.BG_TERTIARY};
                border: none;
                border-radius: {Radius.MD}px;
            }}
            """
        )

        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 14, 14, 14)
        header_layout.setSpacing(Spacing.XS)

        eyebrow = QLabel("PROJECT-ON", header)
        eyebrow.setStyleSheet(
            f"""
            QLabel {{
                color: {Colors.ACCENT_PRIMARY};
                font-size: {Typography.SIZE_XS}px;
                font-weight: {Typography.WEIGHT_BOLD};
                letter-spacing: 0;
            }}
            """
        )

        title = QLabel("Bibliotheque", header)
        title.setStyleSheet(
            f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_LG}px;
                font-weight: {Typography.WEIGHT_BOLD};
            }}
            """
        )

        subtitle = QLabel("Presentation", header)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"""
            QLabel {{
                color: {Colors.TEXT_MUTED};
                font-size: {Typography.SIZE_XS}px;
            }}
            """
        )

        header_layout.addWidget(eyebrow)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        self._layout.addWidget(header)

    def addTab(self, text: str, icon_name: str) -> int:
        btn = SidebarButton(text, icon_name, self)
        idx = len(self._buttons)
        btn.clicked.connect(lambda checked=False, i=idx: self._on_button_clicked(i))
        self._buttons.append(btn)
        self._nav_layout.addWidget(btn)

        if len(self._buttons) == 1:
            btn.setChecked(True)

        return len(self._buttons) - 1

    def _on_button_clicked(self, index: int) -> None:
        if index != self._current_index:
            self.setCurrentIndex(index)

    def setCurrentIndex(self, index: int) -> None:
        if 0 <= index < len(self._buttons):
            if 0 <= self._current_index < len(self._buttons):
                self._buttons[self._current_index].setChecked(False)

            self._buttons[index].setChecked(True)
            self._current_index = index
            self.currentChanged.emit(index)

    def currentIndex(self) -> int:
        return self._current_index
