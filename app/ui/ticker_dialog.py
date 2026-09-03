from __future__ import annotations

"""Réglages du bandeau défilant d'annonces (projection locale)."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QLabel,
    QWidget,
)

from app.ui.obs_output_settings_dialog import ColorPickerButton, DIALOG_STYLE
from app.utils.translations import tr


class TickerDialog(QDialog):
    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("ticker_settings"))
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setStyleSheet(DIALOG_STYLE)

        form = QFormLayout(self)
        form.setContentsMargins(22, 20, 22, 16)
        form.setSpacing(12)

        self._enabled = QCheckBox(tr("ticker_enable"), self)
        self._enabled.setChecked(bool(settings.enabled))
        form.addRow(self._enabled)

        hint = QLabel(tr("ticker_texts"), self)
        hint.setStyleSheet("color: #a0aabe; background: transparent;")
        form.addRow(hint)

        self._texts = QPlainTextEdit(self)
        self._texts.setPlainText("\n".join(str(t) for t in (settings.texts or [])))
        self._texts.setMinimumHeight(120)
        form.addRow(self._texts)

        self._speed = QSpinBox(self)
        self._speed.setRange(20, 400)
        self._speed.setValue(int(settings.speed or 90))
        self._speed.setSuffix(" px/s")
        form.addRow(tr("ticker_speed"), self._speed)

        self._height = QSpinBox(self)
        self._height.setRange(32, 220)
        self._height.setValue(int(settings.height or 64))
        self._height.setSuffix(" px")
        form.addRow(tr("ticker_height"), self._height)

        self._font_size = QSpinBox(self)
        self._font_size.setRange(14, 90)
        self._font_size.setValue(int(settings.font_size or 30))
        self._font_size.setSuffix(" px")
        form.addRow(tr("stage_text_size"), self._font_size)

        self._bg = ColorPickerButton(str(settings.bg_color), self)
        form.addRow(tr("ticker_bg_color"), self._bg)

        self._fg = ColorPickerButton(str(settings.text_color), self)
        form.addRow(tr("ticker_text_color"), self._fg)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton(tr("cancel"), self)
        ok = QPushButton(tr("save"), self)
        ok.setDefault(True)
        for b in (cancel, ok):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        form.addRow(buttons)

    def get_settings(self):
        from app.utils.settings import TickerSettings

        texts = [
            line.strip()
            for line in self._texts.toPlainText().splitlines()
            if line.strip()
        ]
        return TickerSettings(
            enabled=self._enabled.isChecked(),
            texts=texts,
            speed=self._speed.value(),
            height=self._height.value(),
            bg_color=self._bg.color(),
            text_color=self._fg.color(),
            font_size=self._font_size.value(),
        ).sanitized()
