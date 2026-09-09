from __future__ import annotations

"""Réglages du bandeau défilant d'annonces.

Le même réglage alimente la projection locale, la source Navigateur OBS
et la sortie NDI ; un aperçu en bas du dialogue montre le rendu.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.ui.obs_output_settings_dialog import ColorPickerButton, DIALOG_STYLE
from app.ui.ticker_overlay import TickerOverlay
from app.utils.translations import tr


class TickerDialog(QDialog):
    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("ticker_settings"))
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setStyleSheet(DIALOG_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 16)
        root.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(12)
        root.addLayout(form)

        self._enabled = QCheckBox(tr("ticker_enable"), self)
        self._enabled.setChecked(bool(settings.enabled))
        form.addRow(self._enabled)

        hint = QLabel(tr("ticker_texts"), self)
        hint.setStyleSheet("color: #a0aabe; background: transparent;")
        form.addRow(hint)

        self._texts = QPlainTextEdit(self)
        self._texts.setPlainText("\n".join(str(t) for t in (settings.texts or [])))
        self._texts.setMinimumHeight(110)
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

        # ── Aperçu live (le rendu réel, composant de projection) ────────
        preview_label = QLabel("Aperçu en direct — affiché en bas de la "
                               "projection locale, des sources OBS et du NDI", self)
        preview_label.setStyleSheet("color: #a0aabe; background: transparent;")
        root.addWidget(preview_label)

        preview_frame = QFrame(self)
        preview_frame.setFixedHeight(140)
        preview_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #17253b, stop:1 #0b1220);
                border: 1px solid #2a3550;
                border-radius: 10px;
            }
        """)
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.addStretch(1)
        self._preview = TickerOverlay(preview_frame)
        preview_layout.addWidget(self._preview)
        root.addWidget(preview_frame)

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
        root.addLayout(buttons)

        # Aperçu réactif : chaque réglage reconfigure la bande.
        self._texts.textChanged.connect(self._update_preview)
        self._speed.valueChanged.connect(self._update_preview)
        self._height.valueChanged.connect(self._update_preview)
        self._font_size.valueChanged.connect(self._update_preview)
        self._bg.colorChanged.connect(self._update_preview)
        self._fg.colorChanged.connect(self._update_preview)
        self._enabled.toggled.connect(self._update_preview)
        self._update_preview()

    def _update_preview(self, *_args) -> None:
        self._preview.configure(
            texts=self.get_texts(),
            enabled=self._enabled.isChecked(),
            speed=self._speed.value(),
            height=self._height.value(),
            bg_color=self._bg.color(),
            text_color=self._fg.color(),
            font_size=self._font_size.value(),
        )

    def get_texts(self) -> list[str]:
        return [
            line.strip()
            for line in self._texts.toPlainText().splitlines()
            if line.strip()
        ]

    def get_settings(self):
        from app.utils.settings import TickerSettings

        return TickerSettings(
            enabled=self._enabled.isChecked(),
            texts=self.get_texts(),
            speed=self._speed.value(),
            height=self._height.value(),
            bg_color=self._bg.color(),
            text_color=self._fg.color(),
            font_size=self._font_size.value(),
        ).sanitized()
