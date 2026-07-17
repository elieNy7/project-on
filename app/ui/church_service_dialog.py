from __future__ import annotations

from datetime import date

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)

from app.ui.theme import Colors, Radius, Spacing, Typography
from app.utils.translations import tr


class ChurchServiceDialog(QDialog):
    """Génère un « Ordre du culte » complet : un dossier de playlist avec une
    slide prête à projeter pour chaque élément du culte (accueil, louange,
    prédication, offrande, annonces, Sainte-Cène, …)."""

    # (translation key of the section title, translation key of the slide text,
    #  checked by default)
    SECTIONS = [
        ("sec_welcome", "sec_welcome_text", True),
        ("sec_worship", "sec_worship_text", True),
        ("sec_prayer", "sec_prayer_text", True),
        ("sec_reading", "sec_reading_text", True),
        ("sec_sermon", "sec_sermon_text", True),
        ("sec_offering", "sec_offering_text", True),
        ("sec_announcements", "sec_announcements_header", True),
        ("sec_communion", "sec_communion_text", False),
        ("sec_baptism", "sec_baptism_text", False),
        ("sec_dedication", "sec_dedication_text", False),
        ("sec_closing", "sec_closing_text", True),
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("church_service"))
        self.setMinimumSize(540, 620)
        self.setStyleSheet(f"""
            QDialog {{
                background: {Colors.BG_PRIMARY};
            }}
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_SM}px;
            }}
            QLineEdit {{
                background: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
                padding: 8px 12px;
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_MD}px;
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
                font-size: {Typography.SIZE_MD}px;
            }}
            QPlainTextEdit:focus {{
                border-color: {Colors.BORDER_FOCUS};
            }}
            QCheckBox {{
                color: {Colors.TEXT_PRIMARY};
                spacing: 8px;
                font-size: {Typography.SIZE_SM}px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 5px;
                border: 1px solid {Colors.BORDER_DEFAULT};
                background: {Colors.BG_ELEVATED};
            }}
            QCheckBox::indicator:checked {{
                background: {Colors.ACCENT_PRIMARY};
                border: 1px solid {Colors.ACCENT_PRIMARY};
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

        layout.addWidget(QLabel(tr("church_service_title"), self))
        self._title_edit = QLineEdit(self)
        self._title_edit.setPlaceholderText(tr("church_service_title_placeholder"))
        layout.addWidget(self._title_edit)

        layout.addWidget(QLabel(tr("church_name"), self))
        self._church_edit = QLineEdit(self)
        self._church_edit.setPlaceholderText(tr("church_name_placeholder"))
        layout.addWidget(self._church_edit)

        layout.addWidget(QLabel(tr("church_preacher"), self))
        self._preacher_edit = QLineEdit(self)
        self._preacher_edit.setPlaceholderText(tr("church_preacher_placeholder"))
        layout.addWidget(self._preacher_edit)

        layout.addWidget(QLabel(tr("church_theme"), self))
        self._theme_edit = QLineEdit(self)
        self._theme_edit.setPlaceholderText(tr("church_theme_placeholder"))
        layout.addWidget(self._theme_edit)

        layout.addWidget(QLabel(tr("church_sections"), self))
        sections_grid = QGridLayout()
        sections_grid.setHorizontalSpacing(Spacing.MD)
        sections_grid.setVerticalSpacing(6)
        self._section_checks: list[tuple[str, str, QCheckBox]] = []
        for i, (title_key, text_key, checked) in enumerate(self.SECTIONS):
            check = QCheckBox(tr(title_key), self)
            check.setChecked(checked)
            self._section_checks.append((title_key, text_key, check))
            sections_grid.addWidget(check, i // 2, i % 2)
        layout.addLayout(sections_grid)

        layout.addWidget(QLabel(tr("church_announcements"), self))
        self._announcements_edit = QPlainTextEdit(self)
        self._announcements_edit.setPlaceholderText(
            tr("church_announcements_placeholder")
        )
        self._announcements_edit.setMaximumHeight(110)
        layout.addWidget(self._announcements_edit)

        hint = QLabel(tr("church_sections_hint"), self)
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
            ok_btn.setText(tr("add"))
        cancel_btn = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn:
            cancel_btn.setText(tr("cancel"))
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._title_edit.setFocus()

    def get_folder_name(self) -> str:
        title = self._title_edit.text().strip() or tr("church_service")
        today = date.today().strftime("%d/%m/%Y")
        return f"{title} — {today}"

    def get_slides(self) -> list[tuple[str, str]]:
        """Retourne les slides (titre, texte) de l'ordre du culte."""
        church = self._church_edit.text().strip()
        preacher = self._preacher_edit.text().strip()
        theme = self._theme_edit.text().strip()
        announcements = [
            line.strip(" -\t")
            for line in self._announcements_edit.toPlainText().splitlines()
            if line.strip()
        ]

        def join_lines(*parts: str) -> str:
            return "\n".join(p for p in parts if p.strip())

        slides: list[tuple[str, str]] = []
        for title_key, text_key, check in self._section_checks:
            if not check.isChecked():
                continue
            title = tr(title_key)
            if title_key == "sec_welcome":
                text = join_lines(tr(text_key), church, theme)
            elif title_key == "sec_sermon":
                text = join_lines(tr(text_key), theme, preacher)
            elif title_key == "sec_reading":
                text = join_lines(tr(text_key), theme)
            elif title_key == "sec_announcements":
                if announcements:
                    numbered = "\n".join(
                        f"{i + 1}. {line}" for i, line in enumerate(announcements)
                    )
                    text = join_lines(tr("sec_announcements_header"), numbered)
                else:
                    text = tr("sec_announcements_header")
            elif title_key == "sec_closing":
                text = join_lines(tr(text_key), church)
            else:
                text = tr(text_key)
            if text.strip():
                slides.append((title, text))
        return slides
