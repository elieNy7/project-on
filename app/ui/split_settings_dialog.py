from __future__ import annotations

"""Réglages du découpage des textes longs et des strophes de cantiques."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.ui.obs_output_settings_dialog import DIALOG_STYLE
from app.ui.setting_cards import PageHeader, SettingSection
from app.ui.theme import Colors, Radius, Typography
from app.utils.settings import SplitSettings
from app.utils.text_utils import split_hymn_stanza, split_text_into_slides

_SAMPLE_TEXT = (
    "§12 Et je crois que le Seigneur nous a parlé ce matin. Il y a un temps "
    "pour toute chose, dit l'Écriture, un temps pour semer et un temps pour "
    "récolter.\n"
    "Frère, ne vous découragez pas : Dieu tient toujours Sa Parole. Il l'a "
    "tenue pour Abraham, Il l'a tenue pour Moïse, et Il la tiendra pour vous "
    "aujourd'hui, si seulement vous croyez."
)

_SAMPLE_STANZA = (
    "À toi la gloire, ô Ressuscité !\n"
    "À toi la victoire pour l'éternité !\n"
    "Brillant de lumière, l'ange est descendu,\n"
    "Il roule la pierre du tombeau vaincu.\n"
    "Vois-le paraître : c'est lui, c'est Jésus,\n"
    "Ton Sauveur, ton Maître ! Oh ! ne doute plus !"
)


class SplitSettingsDialog(QDialog):
    """Découpage en parties « réf (1/3) » : textes longs et cantiques."""

    splitChanged = Signal(SplitSettings)

    def __init__(self, settings: SplitSettings, parent=None, embedded: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Découpage des textes")
        self.setMinimumSize(560, 560)
        self.resize(620, 760)
        self.setStyleSheet(DIALOG_STYLE)
        settings = (settings or SplitSettings()).sanitized()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        header = PageHeader(
            "Découpage des textes",
            "Paragraphes longs et strophes répartis en parties navigables (1/2, 2/2…).",
            on_reset=self._reset_defaults,
        )
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setSpacing(14)
        layout.addWidget(header)
        if embedded:
            layout.setContentsMargins(16, 16, 16, 16)
            main_layout.addWidget(content)
        else:
            layout.setContentsMargins(24, 20, 24, 16)
            scroll = QScrollArea(self)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
            scroll.setWidget(content)
            main_layout.addWidget(scroll, 1)

        # ═══════ Textes longs ═══════
        text_section = SettingSection("Paragraphes et textes longs", "text.svg")
        self._text_enabled = QCheckBox("Diviser les textes longs en plusieurs parties")
        text_section.addWidget(self._text_enabled)
        self._max_chars = QSpinBox()
        self._max_chars.setRange(120, 800)
        self._max_chars.setSingleStep(20)
        self._max_chars.setSuffix(" car.")
        text_section.addRow(
            "Longueur maximale d'une partie",
            self._max_chars,
            "280 par défaut ; plus petit = texte plus grand et plus de parties",
        )
        self._keep_line_breaks = QCheckBox("Garder les alinéas et les retours à la ligne")
        text_section.addWidget(self._keep_line_breaks)
        text_hint = QLabel(
            "Coupe d'abord entre les alinéas, puis en fin de phrase, puis aux "
            "virgules ; les parties ont des longueurs proches (pas de dernière "
            "partie de trois mots)."
        )
        text_hint.setWordWrap(True)
        text_hint.setStyleSheet(self._hint_style())
        text_section.addWidget(text_hint)
        layout.addWidget(text_section)

        # ═══════ Cantiques ═══════
        hymn_section = SettingSection("Cantiques", "music.svg")
        self._hymn_enabled = QCheckBox("Diviser les strophes longues")
        hymn_section.addWidget(self._hymn_enabled)
        self._hymn_max_lines = QSpinBox()
        self._hymn_max_lines.setRange(2, 12)
        self._hymn_max_lines.setSuffix(" vers")
        hymn_section.addRow(
            "Vers par partie au maximum",
            self._hymn_max_lines,
            "Une strophe de 8 vers devient 2 parties de 4 vers",
        )
        self._hymn_couplets = QCheckBox("Garder les vers deux par deux (rimes)")
        hymn_section.addWidget(self._hymn_couplets)
        layout.addWidget(hymn_section)

        # ═══════ Affichage ═══════
        display_section = SettingSection("Affichage", "eye.svg")
        self._show_counter = QCheckBox("Afficher le numéro de partie dans la référence (1/2)")
        display_section.addWidget(self._show_counter)
        layout.addWidget(display_section)

        # ═══════ Aperçu du découpage ═══════
        preview_section = SettingSection("Aperçu du découpage", "check-circle.svg")
        self._preview = QLabel()
        self._preview.setWordWrap(True)
        self._preview.setTextFormat(Qt.TextFormat.PlainText)
        self._preview.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY};
            background: {Colors.BG_ELEVATED};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.SM}px;
            padding: 10px 12px;
            font-size: {Typography.SIZE_FILTER}px;
        """)
        preview_section.addWidget(self._preview)
        layout.addWidget(preview_section)
        layout.addStretch(1)

        btn_frame = QFrame(self)
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(24, 12, 24, 12)
        btn_layout.addStretch(1)
        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        save_btn = QPushButton("Enregistrer")
        save_btn.setObjectName("AccentButton")
        save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(save_btn)
        btn_frame.setVisible(not embedded)
        main_layout.addWidget(btn_frame)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(200)
        self._debounce.timeout.connect(self._emit_changed)

        self._set_values(settings)
        for box in (
            self._text_enabled,
            self._keep_line_breaks,
            self._hymn_enabled,
            self._hymn_couplets,
            self._show_counter,
        ):
            box.toggled.connect(self._on_change)
        for spin in (self._max_chars, self._hymn_max_lines):
            spin.valueChanged.connect(self._on_change)
        self._refresh()

    @staticmethod
    def _hint_style() -> str:
        return (
            f"color: {Colors.TEXT_SECONDARY}; background: transparent; "
            f"border: none; font-size: {Typography.SIZE_META}px;"
        )

    def _set_values(self, settings: SplitSettings) -> None:
        self._text_enabled.setChecked(settings.text_enabled)
        self._max_chars.setValue(settings.max_chars)
        self._keep_line_breaks.setChecked(settings.keep_line_breaks)
        self._hymn_enabled.setChecked(settings.hymn_enabled)
        self._hymn_max_lines.setValue(settings.hymn_max_lines)
        self._hymn_couplets.setChecked(settings.hymn_keep_couplets)
        self._show_counter.setChecked(settings.show_part_counter)

    def read_settings(self) -> SplitSettings:
        return SplitSettings(
            text_enabled=self._text_enabled.isChecked(),
            max_chars=self._max_chars.value(),
            keep_line_breaks=self._keep_line_breaks.isChecked(),
            hymn_enabled=self._hymn_enabled.isChecked(),
            hymn_max_lines=self._hymn_max_lines.value(),
            hymn_keep_couplets=self._hymn_couplets.isChecked(),
            show_part_counter=self._show_counter.isChecked(),
        ).sanitized()

    def _reset_defaults(self) -> None:
        self._set_values(SplitSettings())

    def _on_change(self, *_args) -> None:
        self._refresh()
        self._debounce.start()

    def _emit_changed(self) -> None:
        self.splitChanged.emit(self.read_settings())

    def _refresh(self) -> None:
        text_on = self._text_enabled.isChecked()
        self._max_chars.setEnabled(text_on)
        self._keep_line_breaks.setEnabled(text_on)
        hymn_on = self._hymn_enabled.isChecked()
        self._hymn_max_lines.setEnabled(hymn_on)
        self._hymn_couplets.setEnabled(hymn_on)
        self._preview.setText(self.preview_text(self.read_settings()))

    @staticmethod
    def preview_text(settings: SplitSettings) -> str:
        """Résumé lisible du découpage d'un paragraphe et d'une strophe types."""
        if settings.text_enabled:
            parts = split_text_into_slides(
                _SAMPLE_TEXT, settings.max_chars, 60,
                keep_line_breaks=settings.keep_line_breaks,
            )
        else:
            parts = [_SAMPLE_TEXT]
        if settings.hymn_enabled:
            verses = split_hymn_stanza(
                _SAMPLE_STANZA, settings.hymn_max_lines, max(settings.max_chars, 120),
                keep_couplets=settings.hymn_keep_couplets,
            )
        else:
            verses = [_SAMPLE_STANZA]

        def block(title: str, chunks: list[str]) -> str:
            lines = [f"{title} — {len(chunks)} partie{'s' if len(chunks) > 1 else ''}"]
            for index, chunk in enumerate(chunks, start=1):
                counter = f" ({index}/{len(chunks)})" if settings.show_part_counter and len(chunks) > 1 else ""
                lines.append(f"▸ Partie{counter} · {len(chunk)} car.")
                lines.append(chunk)
            return "\n".join(lines)

        return block("Paragraphe de sermon", parts) + "\n\n" + block("Strophe de 6 vers", verses)
