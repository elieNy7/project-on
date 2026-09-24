from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.setting_cards import PageHeader, SettingSection
from app.ui.theme import Colors, Radius, Spacing, Typography
from app.utils.translations import tr


class OptionCard(QFrame):
    """Carte d'option sélectionnable."""

    clicked = Signal()

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
    settingsChanged = Signal()  # theme or language picked

    """Dialogue pour les paramètres d'apparence (thème et langue)."""

    def __init__(
        self,
        current_theme: str = "dark",
        current_language: str = "fr",
        parent=None,
        embedded: bool = False,
        mica: bool | None = None,
    ) -> None:
        super().__init__(parent)
        self._embedded = embedded
        # None: the Mica option is not offered (unsupported Windows).
        self._mica = mica
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
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        layout.addWidget(PageHeader(tr("appearance_title"), tr("appearance_subtitle")))

        def _pair(first: QWidget, second: QWidget) -> QWidget:
            box = QWidget(self)
            box.setStyleSheet("background: transparent;")
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(Spacing.SM)
            row.addWidget(first)
            row.addWidget(second)
            return box

        theme_section = SettingSection("Thème de l'interface", "sun.svg")
        self._dark_card = OptionCard(
            tr("dark_theme"), tr("dark_theme_desc"), is_selected=(self._theme == "dark"), parent=self
        )
        self._light_card = OptionCard(
            tr("light_theme"), tr("light_theme_desc"), is_selected=(self._theme == "light"), parent=self
        )
        self._dark_card.clicked.connect(lambda: self._select_theme("dark"))
        self._light_card.clicked.connect(lambda: self._select_theme("light"))
        theme_section.addWidget(_pair(self._dark_card, self._light_card))
        layout.addWidget(theme_section)

        lang_section = SettingSection(tr("language"), "globe.svg")
        self._fr_card = OptionCard(
            tr("french"), tr("french_desc"), is_selected=(self._language == "fr"), parent=self
        )
        self._en_card = OptionCard(
            tr("english"), tr("english_desc"), is_selected=(self._language == "en"), parent=self
        )
        self._fr_card.clicked.connect(lambda: self._select_language("fr"))
        self._en_card.clicked.connect(lambda: self._select_language("en"))
        lang_section.addWidget(_pair(self._fr_card, self._en_card))
        layout.addWidget(lang_section)

        self._mica_box: QCheckBox | None = None
        if self._mica is not None:
            window_section = SettingSection("Fenêtre", "monitor.svg")
            self._mica_box = QCheckBox("Effet Mica (Windows 11)")
            self._mica_box.setToolTip(
                "Laisse transparaître le fond d'écran, teinté, derrière le menu et la barre du haut."
            )
            self._mica_box.setChecked(bool(self._mica))
            self._mica_box.toggled.connect(lambda _on: self.settingsChanged.emit())
            window_section.addWidget(self._mica_box)
            layout.addWidget(window_section)

        note = QLabel(tr("restart_required"), self)
        note.setWordWrap(True)
        note.setStyleSheet(
            f"font-size: {Typography.SIZE_META}px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        layout.addWidget(note)
        layout.addStretch(1)

        # Standalone dialog only: the settings page applies at once.
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        cancel_btn = QPushButton(tr("cancel"), self)
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton(tr("save"), self)
        save_btn.setObjectName("AccentButton")
        save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)
        if self._embedded:  # settings page: every change applies immediately
            cancel_btn.hide()
            save_btn.hide()

    def _select_theme(self, theme: str) -> None:
        self._theme = theme if theme in ("dark", "light") else "dark"
        self._dark_card.set_selected(self._theme == "dark")
        self._light_card.set_selected(self._theme == "light")
        self.settingsChanged.emit()

    def _select_language(self, language: str) -> None:
        self._language = language
        self._fr_card.set_selected(language == "fr")
        self._en_card.set_selected(language == "en")
        self.settingsChanged.emit()

    def get_settings(self) -> tuple[str, str]:
        """Retourne (theme, language)."""
        return self._theme, self._language

    def mica_enabled(self) -> bool | None:
        """Mica switch state, or None when the option is not offered."""
        return self._mica_box.isChecked() if self._mica_box is not None else None
