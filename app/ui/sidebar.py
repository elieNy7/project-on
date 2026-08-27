from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.icons import app_icon
from app.ui.theme import Colors, Radius, Spacing, Typography
from app.version import __version__


class SidebarButton(QPushButton):
    """Premium sidebar button with refined active state and subtle glow."""

    def __init__(self, text: str, icon_name: str, parent=None) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._text = text

        self.setText(text)
        self.setIconSize(QSize(20, 20))
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(44)

        # Subtle shadow effect for depth
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(12)
        self._shadow.setXOffset(0)
        self._shadow.setYOffset(2)
        self._shadow.setColor(QColor(0, 0, 0, 40))
        self.setGraphicsEffect(self._shadow)

        self._update_style(False)

    def _update_style(self, checked: bool) -> None:
        icon_color = Colors.ACCENT_PRIMARY if checked else Colors.TEXT_MUTED
        self.setIcon(app_icon(self._icon_name, icon_color))

        if checked:
            self.setStyleSheet(f"""
                QPushButton {{
                    text-align: left;
                    padding: 10px 14px 10px 14px;
                    border: none;
                    border-radius: {Radius.MD}px;
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 {Colors.ACCENT_GLOW_STRONG},
                        stop:1 {Colors.ACCENT_GLOW}
                    );
                    color: {Colors.ACCENT_LIGHT};
                    font-family: {Typography.PRIMARY_FAMILY};
                    font-size: {Typography.SIZE_MD}px;
                    font-weight: {Typography.WEIGHT_SEMIBOLD};
                    margin: 0 0 3px 0;
                    letter-spacing: 0;
                    border: 1px solid {Colors.ACCENT_GLOW_STRONG};
                }}
                QPushButton:hover {{
                    background: {Colors.ACCENT_GLOW_STRONG};
                    border-color: {Colors.ACCENT_PRIMARY};
                }}
            """)
            self._shadow.setColor(QColor(232, 176, 86, 30))
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    text-align: left;
                    padding: 10px 14px 10px 14px;
                    border: 1px solid transparent;
                    border-radius: {Radius.MD}px;
                    background: transparent;
                    color: {Colors.TEXT_MUTED};
                    font-family: {Typography.PRIMARY_FAMILY};
                    font-size: {Typography.SIZE_MD}px;
                    font-weight: {Typography.WEIGHT_MEDIUM};
                    margin: 0 0 3px 0;
                    letter-spacing: 0;
                }}
                QPushButton:hover {{
                    background: {Colors.GLASS_MEDIUM};
                    color: {Colors.TEXT_SECONDARY};
                    border-color: {Colors.BORDER_SUBTLE};
                }}
            """)
            self._shadow.setColor(QColor(0, 0, 0, 40))

    def setChecked(self, checked: bool) -> None:
        super().setChecked(checked)
        self._update_style(checked)


class Sidebar(QFrame):
    """Premium vertical navigation sidebar with glassmorphism header."""

    currentChanged = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(210)
        self.setObjectName("Sidebar")

        self.setStyleSheet(
            f"""
            QFrame#Sidebar {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {Colors.SIDEBAR_GRADIENT_START},
                    stop:1 {Colors.SIDEBAR_GRADIENT_END}
                );
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-right: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.LG}px;
            }}
            """
        )

        self._buttons: list[SidebarButton] = []
        self._current_index = 0

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 16, 14, 14)
        self._layout.setSpacing(Spacing.SM)

        self._build_header()

        # Separator
        self._layout.addWidget(self._make_separator())

        self._nav_container = QWidget(self)
        self._nav_layout = QVBoxLayout(self._nav_container)
        self._nav_layout.setContentsMargins(0, 8, 0, 0)
        self._nav_layout.setSpacing(Spacing.XS)
        self._layout.addWidget(self._nav_container)
        self._layout.addStretch(1)

        # Bottom separator
        self._layout.addWidget(self._make_separator())

        # Footer — la marque vit dans l'en-tête ; ici seulement la version.
        self._footer = QLabel(f"Version {__version__}", self)
        self._footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._footer.setStyleSheet(
            f"""
            QLabel {{
                color: {Colors.TEXT_DISABLED};
                font-size: {Typography.SIZE_2XS}px;
                padding: 4px;
                letter-spacing: 0.5px;
                font-weight: {Typography.WEIGHT_MEDIUM};
            }}
            """
        )
        self._layout.addWidget(self._footer)

    @staticmethod
    def _make_separator() -> QFrame:
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {Colors.BORDER_SUBTLE}; border: none;")
        return sep

    def _build_header(self) -> None:
        header = QFrame(self)
        header.setObjectName("SidebarHeader")
        header.setStyleSheet(
            f"""
            QFrame#SidebarHeader {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {Colors.BG_ELEVATED},
                    stop:1 {Colors.BG_TERTIARY}
                );
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
            }}
            """
        )

        # Add subtle shadow to header
        header_shadow = QGraphicsDropShadowEffect(header)
        header_shadow.setBlurRadius(16)
        header_shadow.setXOffset(0)
        header_shadow.setYOffset(3)
        header_shadow.setColor(QColor(0, 0, 0, 50))
        header.setGraphicsEffect(header_shadow)

        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 16, 16, 16)
        header_layout.setSpacing(Spacing.XS)

        # Top row: eyebrow + icon indicator
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(Spacing.SM)

        eyebrow = QLabel("PROJECT-ON", header)
        eyebrow.setStyleSheet(
            f"""
            QLabel {{
                color: {Colors.ACCENT_PRIMARY};
                font-size: {Typography.SIZE_2XS}px;
                font-weight: {Typography.WEIGHT_BOLD};
                letter-spacing: 1px;
            }}
            """
        )

        # Accent indicator dot
        indicator = QLabel(header)
        indicator.setFixedSize(6, 6)
        indicator.setStyleSheet(
            f"""
            QLabel {{
                background: {Colors.ACCENT_PRIMARY};
                border-radius: 3px;
            }}
            """
        )

        top_row.addWidget(eyebrow)
        top_row.addWidget(indicator)
        top_row.addStretch(1)

        title = QLabel("Bibliothèque", header)
        title_font = QFont(Typography.FAMILY, Typography.SIZE_LG_PT)
        title_font.setWeight(Typography.WEIGHT_BOLD)
        title.setFont(title_font)
        title.setStyleSheet(
            f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_LG}px;
                font-weight: {Typography.WEIGHT_BOLD};
            }}
            """
        )

        subtitle = QLabel("Gestion de présentation", header)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"""
            QLabel {{
                color: {Colors.TEXT_MUTED};
                font-size: {Typography.SIZE_2XS}px;
            }}
            """
        )

        header_layout.addLayout(top_row)
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
