from __future__ import annotations

"""Réglages → Raccourcis : une touche par action, compatible Stream Deck."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui.obs_output_settings_dialog import DIALOG_STYLE
from app.ui.setting_cards import PageHeader, SettingSection
from app.ui.theme import Colors, Typography
from app.utils.shortcuts import ACTIONS, ShortcutSettings


class ShortcutSettingsDialog(QDialog):
    shortcutsChanged = Signal(ShortcutSettings)

    def __init__(self, settings: ShortcutSettings, parent=None, embedded: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Raccourcis")
        self.setStyleSheet(DIALOG_STYLE)
        self.resize(620, 720)
        self._settings = (settings or ShortcutSettings()).sanitized()
        self._edits: dict[str, QKeySequenceEdit] = {}

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setSpacing(14)
        layout.addWidget(PageHeader(
            "Raccourcis",
            "Une touche par action : clavier, télécommande de présentation ou Stream Deck.",
            on_reset=self._reset_defaults,
        ))
        if embedded:
            layout.setContentsMargins(16, 16, 16, 16)
            main_layout.addWidget(content)
        else:
            layout.setContentsMargins(24, 20, 24, 16)
            scroll = QScrollArea(self)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidget(content)
            main_layout.addWidget(scroll, 1)

        hint = QLabel(
            "Stream Deck : ajoutez l'action « Raccourci clavier » (Hotkey) et "
            "tapez la même touche. Télécommande de présentation : elle envoie "
            "Page suivante / Page précédente, déjà reliées au slide suivant et "
            "précédent. Les flèches, Échap et Ctrl+1…7 restent fixes."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; background: {Colors.ACCENT_SECONDARY_GLOW};"
            f"border: 1px solid {Colors.BORDER_DEFAULT}; border-radius: 6px; padding: 10px;"
            f"font-size: {Typography.SIZE_FILTER}px;"
        )
        layout.addWidget(hint)

        section = SettingSection("Actions", "zap.svg")
        effective = self._settings.effective()
        for item in ACTIONS:
            edit = QKeySequenceEdit(QKeySequence(effective.get(item.id, "")))
            edit.setMaximumSequenceLength(1)
            edit.setMinimumWidth(150)
            edit.editingFinished.connect(self._on_change)
            clear = QPushButton("✕")
            clear.setToolTip("Désactiver ce raccourci")
            clear.setFixedWidth(30)
            clear.clicked.connect(lambda _c=False, e=edit: (e.clear(), self._on_change()))
            box = QWidget()
            box.setStyleSheet("background: transparent;")
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            row.addWidget(edit)
            row.addWidget(clear)
            section.addRow(item.label, box, f"Par défaut : {item.default}")
            self._edits[item.id] = edit
        layout.addWidget(section)

        self._warning = QLabel("")
        self._warning.setWordWrap(True)
        self._warning.setStyleSheet(
            f"color: {Colors.ACCENT_WARNING}; background: transparent; border: none;"
            f"font-size: {Typography.SIZE_FILTER}px;"
        )
        layout.addWidget(self._warning)
        layout.addStretch(1)
        self._refresh_warning()

    def read_settings(self) -> ShortcutSettings:
        keys = {
            action_id: edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
            for action_id, edit in self._edits.items()
        }
        return ShortcutSettings(keys=keys).sanitized()

    def _refresh_warning(self) -> None:
        conflicts = self.read_settings().conflicts()
        if not conflicts:
            self._warning.setText("")
            return
        labels = {a.id: a.label for a in ACTIONS}
        parts = [
            f"« {key} » : " + ", ".join(labels.get(i, i) for i in ids)
            for key, ids in conflicts.items()
        ]
        self._warning.setText(
            "Touche en double ou réservée — seule la première action répondra : "
            + " ; ".join(parts)
        )

    def _on_change(self, *_args) -> None:
        self._refresh_warning()
        self.shortcutsChanged.emit(self.read_settings())

    def _reset_defaults(self) -> None:
        for item in ACTIONS:
            self._edits[item.id].setKeySequence(QKeySequence(item.default))
        self._on_change()
