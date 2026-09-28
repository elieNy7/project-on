from __future__ import annotations

"""Éditeur de cantique : titre, numéro, strophes et refrain.

Les strophes sont saisies dans une seule zone de texte, séparées par une
ligne vide (comme sur une feuille de chants). Une strophe dont la première
ligne est « Refrain » (ou « Chœur ») est le refrain ; le bouton « Refrain »
bascule la strophe où se trouve le curseur. La liste de droite montre en
direct le découpage reconnu.
"""

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.ui.obs_output_settings_dialog import DIALOG_STYLE
from app.ui.setting_cards import PageHeader, SettingSection
from app.ui.theme import Colors, Typography, get_accent_button_style

_CHORUS_RE = re.compile(
    r"^\s*(?:dernier\s+)?(?:ch(?:oe|œ)urs?|refrain|chorus)\b\s*[:.\-–—]?\s*",
    re.IGNORECASE,
)


def parse_stanzas(text: str) -> list[tuple[str, bool]]:
    """Texte saisi → [(strophe sans son libellé, est_refrain)]."""
    blocks = re.split(r"\n\s*\n+", str(text or "").replace("\r", "").strip())
    out: list[tuple[str, bool]] = []
    for block in blocks:
        lines = [line.rstrip() for line in block.strip().split("\n")]
        lines = [line for line in lines if line.strip()]
        if not lines:
            continue
        is_chorus = bool(_CHORUS_RE.match(lines[0]))
        if is_chorus:
            rest = _CHORUS_RE.sub("", lines[0], count=1).strip()
            lines = ([rest] if rest else []) + lines[1:]
        body = "\n".join(line.strip() for line in lines).strip()
        if body:
            out.append((body, is_chorus))
    return out


def compose_text(stanzas: list[tuple[str, bool]]) -> str:
    """[(strophe, est_refrain)] → texte éditable (refrain préfixé)."""
    blocks = []
    for body, is_chorus in stanzas:
        blocks.append(f"Refrain\n{body}" if is_chorus else body)
    return "\n\n".join(blocks)


class HymnEditorDialog(QDialog):
    """Créer ou modifier un cantique."""

    def __init__(
        self,
        parent=None,
        *,
        title: str = "",
        number: str = "",
        language: str = "fr",
        stanzas: list[tuple[str, bool]] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Modifier le cantique" if stanzas else "Nouveau cantique")
        self.setStyleSheet(DIALOG_STYLE)
        self.resize(820, 620)

        self.title_edit = QLineEdit(title)
        self.title_edit.setPlaceholderText("À toi la gloire")
        self.number_edit = QLineEdit(number)
        self.number_edit.setPlaceholderText("ex. 42")
        self.number_edit.setMaximumWidth(120)
        self.language = QComboBox()
        for label, code in (("Français", "fr"), ("Lingala", "ln"), ("Kiswahili", "sw"),
                            ("Tshiluba", "lua"), ("Kikongo", "kg"), ("English", "en")):
            self.language.addItem(label, code)
        index = self.language.findData(language or "fr")
        if index < 0:
            self.language.addItem(language, language)
            index = self.language.count() - 1
        self.language.setCurrentIndex(index)

        infos = SettingSection("Cantique", "music.svg")
        infos.addRow("Titre", self.title_edit)
        infos.addRow("Numéro", self.number_edit)
        infos.addRow("Langue", self.language)
        self.title_edit.setMinimumWidth(260)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(
            "Strophe 1, ligne 1\nStrophe 1, ligne 2\n\nRefrain\nLigne du refrain\n\n"
            "Strophe 2…\n\n(une ligne vide sépare les strophes)"
        )
        self.editor.setPlainText(compose_text(stanzas or []))
        self.editor.textChanged.connect(self._refresh_preview)

        self.chorus_btn = QPushButton("Refrain")
        self.chorus_btn.setToolTip("Marquer / démarquer comme refrain la strophe du curseur")
        self.chorus_btn.clicked.connect(self.toggle_chorus_at_cursor)
        hint = QLabel("Une ligne vide sépare les strophes.")
        hint.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: {Typography.SIZE_META}px;"
            " background: transparent; border: none;"
        )
        tools = QHBoxLayout()
        tools.addWidget(self.chorus_btn)
        tools.addWidget(hint, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.editor, 1)
        left_layout.addLayout(tools)

        self.preview = QListWidget()
        self.preview.setWordWrap(True)
        self.preview.setAlternatingRowColors(False)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        recognised = QLabel("Découpage reconnu")
        recognised.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: {Typography.SIZE_META}px;"
            " background: transparent;"
        )
        right_layout.addWidget(recognised)
        right_layout.addWidget(self.preview, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([520, 280])

        lyrics = SettingSection("Paroles", "file-plus.svg")
        lyrics.addWidget(splitter)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save = buttons.button(QDialogButtonBox.StandardButton.Save)
        save.setText("Enregistrer")
        save.setStyleSheet(get_accent_button_style())
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(14)
        layout.addWidget(PageHeader(
            self.windowTitle(),
            "Le découpage en strophes et refrain se voit en direct à droite.",
        ))
        layout.addWidget(infos)
        layout.addWidget(lyrics, 1)
        layout.addWidget(buttons)
        self._refresh_preview()

    # ── Données ──────────────────────────────────────────────────────

    def stanzas(self) -> list[tuple[str, bool]]:
        return parse_stanzas(self.editor.toPlainText())

    def values(self) -> dict:
        return {
            "title": self.title_edit.text().strip(),
            "number": self.number_edit.text().strip() or None,
            "language": str(self.language.currentData() or "fr"),
            "stanzas": self.stanzas(),
        }

    # ── Interface ────────────────────────────────────────────────────

    def _refresh_preview(self) -> None:
        self.preview.clear()
        verse = chorus = 0
        for body, is_chorus in self.stanzas():
            if is_chorus:
                chorus += 1
                label = "Refrain" if chorus == 1 else f"Refrain {chorus}"
            else:
                verse += 1
                label = f"Strophe {verse}"
            lines = body.count("\n") + 1
            first = body.split("\n", 1)[0]
            self.preview.addItem(f"{label} · {lines} ligne(s)\n{first}")

    def toggle_chorus_at_cursor(self) -> None:
        """Ajoute ou retire « Refrain » en tête de la strophe du curseur."""
        text = self.editor.toPlainText().replace("\r", "")
        position = self.editor.textCursor().position()
        # Début de la strophe : après la dernière ligne vide avant le curseur.
        before = text[:position]
        match = None
        for match in re.finditer(r"\n\s*\n", before):
            pass
        start = match.end() if match else 0
        while start < len(text) and text[start] == "\n":
            start += 1
        line_end = text.find("\n", start)
        first_line = text[start: line_end if line_end >= 0 else len(text)]
        if _CHORUS_RE.match(first_line) and not _CHORUS_RE.sub("", first_line).strip():
            # Ligne « Refrain » seule : on la retire (avec son retour à la ligne).
            end = line_end + 1 if line_end >= 0 else len(text)
            new_text = text[:start] + text[end:]
            new_position = max(start, position - (end - start))
        elif _CHORUS_RE.match(first_line):
            new_text = text[:start] + _CHORUS_RE.sub("", first_line, count=1) + text[start + len(first_line):]
            new_position = start
        else:
            new_text = text[:start] + "Refrain\n" + text[start:]
            new_position = position + len("Refrain\n")
        self.editor.setPlainText(new_text)
        cursor = self.editor.textCursor()
        cursor.setPosition(min(new_position, len(new_text)))
        self.editor.setTextCursor(cursor)
        self.editor.moveCursor(QTextCursor.MoveOperation.NoMove)

    def _on_accept(self) -> None:
        values = self.values()
        if not values["title"]:
            QMessageBox.warning(self, "Titre manquant", "Donnez un titre au cantique.")
            return
        if not values["stanzas"]:
            QMessageBox.warning(self, "Paroles manquantes", "Saisissez au moins une strophe.")
            return
        self.accept()
