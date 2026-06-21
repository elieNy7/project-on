from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import Colors, Radius, Spacing, Typography
from app.utils.translations import tr


class OptionCard(QFrame):
    """Carte d'option sélectionnable."""

    clicked = pyqtSignal()

    def __init__(
        self, title: str, description: str, is_selected: bool = False, parent=None
    ) -> None:
        super().__init__(parent)
        self._is_selected = is_selected
        self._title = title
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._setup_ui(title, description)
        self._update_style()

    def _setup_ui(self, title: str, description: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        title_label = QLabel(title, self)
        title_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_MD}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            color: {Colors.TEXT_PRIMARY};
            background: transparent;
        """)
        layout.addWidget(title_label)

        desc_label = QLabel(description, self)
        desc_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_SM}px;
            color: {Colors.TEXT_MUTED};
            background: transparent;
        """)
        layout.addWidget(desc_label)

    def _update_style(self) -> None:
        if self._is_selected:
            self.setStyleSheet(f"""
                OptionCard {{
                    background: {Colors.SURFACE_ACTIVE};
                    border: 1px solid {Colors.ACCENT_PRIMARY};
                    border-radius: {Radius.MD}px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                OptionCard {{
                    background: {Colors.BG_PRIMARY};
                    border: 1px solid {Colors.BORDER_DEFAULT};
                    border-radius: {Radius.MD}px;
                }}
                OptionCard:hover {{
                    background: {Colors.SURFACE_HOVER};
                    border-color: {Colors.BORDER_FOCUS};
                }}
            """)

    def set_selected(self, selected: bool) -> None:
        self._is_selected = selected
        self._update_style()

    def is_selected(self) -> bool:
        return self._is_selected

    def mousePressEvent(self, event) -> None:
        self.clicked.emit()
        super().mousePressEvent(event)


class AppearanceSettingsDialog(QDialog):
    """Dialogue pour les paramètres d'apparence (thème et langue)."""

    def __init__(
        self, current_theme: str = "dark", current_language: str = "fr", parent=None
    ) -> None:
        super().__init__(parent)
        self._theme = current_theme if current_theme in ("dark", "light") else "dark"
        self._language = current_language

        self.setWindowTitle(tr("appearance_title"))
        self.setMinimumSize(400, 300)
        self.setStyleSheet(f"""
            QDialog {{
                background: {Colors.BG_SECONDARY};
            }}
        """)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL)
        layout.setSpacing(Spacing.LG)

        # Header
        header = QLabel(tr("appearance_title"), self)
        header.setStyleSheet(f"""
            font-size: {Typography.SIZE_2XL}px;
            font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_PRIMARY};
        """)
        layout.addWidget(header)

        subtitle = QLabel(tr("appearance_subtitle"), self)
        subtitle.setStyleSheet(f"""
            font-size: {Typography.SIZE_SM}px;
            color: {Colors.TEXT_MUTED};
            margin-bottom: {Spacing.MD}px;
        """)
        layout.addWidget(subtitle)

        # ── Scrollable content ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        # Stylize scrollbar
        scroll.verticalScrollBar().setStyleSheet(f"""
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {Colors.BORDER_DEFAULT};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {Colors.ACCENT_PRIMARY};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(Spacing.LG)

        # === THEME SECTION ===
        theme_label = QLabel(tr("theme"), self)
        theme_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_SM}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            color: {Colors.TEXT_SECONDARY};
            text-transform: uppercase;
            letter-spacing: 1px;
        """)
        content_layout.addWidget(theme_label)

        theme_container = QHBoxLayout()
        theme_container.setSpacing(Spacing.SM)

        self._dark_card = OptionCard(
            tr("dark_theme"),
            tr("dark_theme_desc"),
            is_selected=(self._theme == "dark"),
            parent=self,
        )
        self._light_card = OptionCard(
            tr("light_theme"),
            tr("light_theme_desc"),
            is_selected=(self._theme == "light"),
            parent=self,
        )

        self._dark_card.clicked.connect(lambda: self._select_theme("dark"))
        self._light_card.clicked.connect(lambda: self._select_theme("light"))

        theme_container.addWidget(self._dark_card)
        theme_container.addWidget(self._light_card)
        content_layout.addLayout(theme_container)

        # === LANGUAGE SECTION ===
        lang_label = QLabel(tr("language"), self)
        lang_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_SM}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            color: {Colors.TEXT_SECONDARY};
            text-transform: uppercase;
            letter-spacing: 1px;
        """)
        content_layout.addWidget(lang_label)

        lang_container = QHBoxLayout()
        lang_container.setSpacing(Spacing.SM)

        self._fr_card = OptionCard(
            tr("french"),
            tr("french_desc"),
            is_selected=(self._language == "fr"),
            parent=self,
        )
        self._en_card = OptionCard(
            tr("english"),
            tr("english_desc"),
            is_selected=(self._language == "en"),
            parent=self,
        )

        self._fr_card.clicked.connect(lambda: self._select_language("fr"))
        self._en_card.clicked.connect(lambda: self._select_language("en"))

        lang_container.addWidget(self._fr_card)
        lang_container.addWidget(self._en_card)
        content_layout.addLayout(lang_container)

        content_layout.addStretch(1)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        # Note
        note = QLabel(tr("restart_required"), self)
        note.setStyleSheet(f"""
            font-size: {Typography.SIZE_XS}px;
            color: {Colors.TEXT_DISABLED};
            font-style: italic;
        """)
        note.setWordWrap(True)
        layout.addWidget(note)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(Spacing.SM)

        cancel_btn = QPushButton(tr("cancel"), self)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.SURFACE_HOVER};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.SM}px;
                padding: 10px 24px;
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_SM}px;
                font-weight: {Typography.WEIGHT_MEDIUM};
            }}
            QPushButton:hover {{
                background: {Colors.SURFACE_ACTIVE};
            }}
        """)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton(tr("save"), self)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ACCENT_PRIMARY};
                border: none;
                border-radius: {Radius.SM}px;
                padding: 10px 24px;
                color: #000;
                font-size: {Typography.SIZE_SM}px;
                font-weight: {Typography.WEIGHT_MEDIUM};
            }}
            QPushButton:hover {{
                background: {Colors.ACCENT_LIGHT};
            }}
        """)
        save_btn.clicked.connect(self.accept)

        btn_layout.addStretch(1)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def _select_theme(self, theme: str) -> None:
        self._theme = theme if theme in ("dark", "light") else "dark"
        self._dark_card.set_selected(self._theme == "dark")
        self._light_card.set_selected(self._theme == "light")

    def _select_language(self, language: str) -> None:
        self._language = language
        self._fr_card.set_selected(language == "fr")
        self._en_card.set_selected(language == "en")

    def get_settings(self) -> tuple[str, str]:
        """Retourne (theme, language)."""
        return self._theme, self._language

    @staticmethod
    def edit(
        current_theme: str, current_language: str, parent=None
    ) -> tuple[str, str] | None:
        """Ouvre le dialogue et retourne les nouveaux paramètres ou None si annulé."""
        dialog = AppearanceSettingsDialog(current_theme, current_language, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.get_settings()
        return None
