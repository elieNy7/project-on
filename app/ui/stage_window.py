from __future__ import annotations

"""Écran scène (façon ProPresenter Stage Display).

Fenêtre plein écran dédiée aux orateurs : slide courante en grand, slide
suivante atténuée, horloge et messages de l'opérateur. Le style est
volontairement sobre et indépendant des thèmes de projection : lisibilité
maximale sur un écran de pupitre.
"""

import logging
from typing import Any

log = logging.getLogger(__name__)

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QFontDatabase, QGuiApplication, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.ui.obs_output_settings_dialog import ColorPickerButton, DIALOG_STYLE
from app.utils.fonts import get_available_fonts
from app.utils.translations import tr


def _resolve_family(configured: str) -> str:
    try:
        available = {f.lower() for f in QFontDatabase.families()}
    except Exception:
        available = set()
    for candidate in (configured, "Poppins", "Segoe UI", "Arial"):
        name = str(candidate or "").strip()
        if name and (not available or name.lower() in available):
            return name
    return "sans-serif"


class StageWindow(QWidget):
    """Fenêtre « scène » : courant + suivant + horloge + message."""

    def __init__(self, settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Project-On - Écran scène")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._settings = settings

        self.setStyleSheet(
            f"QWidget {{ background: {settings.bg_color or '#000000'}; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(48, 32, 48, 24)
        root.setSpacing(12)

        # ── Rangée haute : horloge + message ─────────────────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        root.addLayout(top_row)

        self._message_label = QLabel("", self)
        self._message_label.setWordWrap(True)
        self._message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message_label.setStyleSheet(
            "background: rgba(46,160,67,0.18); color: #7ee787;"
            " border: 2px solid rgba(46,160,67,0.55); border-radius: 14px;"
            " padding: 14px 26px; font-weight: 800;"
        )
        self._message_label.hide()
        top_row.addWidget(self._message_label, 1)

        self._clock_label = QLabel("", self)
        self._clock_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        top_row.addWidget(self._clock_label, 0)

        # ── Slide courante ───────────────────────────────────────────
        self._current_ref = QLabel("", self)
        self._current_ref.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._current_ref.setStyleSheet(
            "color: rgba(255,255,255,0.55); font-weight: 700; letter-spacing: 1px;"
            " background: transparent;"
        )
        root.addWidget(self._current_ref, 0)

        self._current_text = QLabel("", self)
        self._current_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._current_text.setWordWrap(True)
        self._current_text.setStyleSheet("background: transparent;")
        root.addWidget(self._current_text, 1)

        # ── Séparateur ───────────────────────────────────────────────
        self._separator = QFrame(self)
        self._separator.setFixedHeight(2)
        self._separator.setStyleSheet(
            "background: rgba(255,255,255,0.14); border: none;"
        )
        root.addWidget(self._separator, 0)

        # ── Slide suivante ───────────────────────────────────────────
        self._next_block = QWidget(self)
        self._next_block.setStyleSheet("background: transparent;")
        next_lay = QVBoxLayout(self._next_block)
        next_lay.setContentsMargins(0, 4, 0, 0)
        next_lay.setSpacing(4)

        self._next_badge = QLabel("À SUIVRE", self._next_block)
        self._next_badge.setStyleSheet(
            "color: rgba(140,200,150,0.75); font-weight: 800; letter-spacing: 3px;"
            " font-size: 18px; background: transparent;"
        )
        next_lay.addWidget(self._next_badge, 0, Qt.AlignmentFlag.AlignHCenter)

        self._next_ref = QLabel("", self._next_block)
        self._next_ref.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._next_ref.setStyleSheet("background: transparent; font-weight: 700;")
        next_lay.addWidget(self._next_ref, 0)

        self._next_text = QLabel("", self._next_block)
        self._next_text.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._next_text.setWordWrap(True)
        self._next_text.setStyleSheet("background: transparent;")
        next_lay.addWidget(self._next_text, 1)
        root.addWidget(self._next_block, 0)

        # ── Horloge & redimensionnement ──────────────────────────────
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start()

        self._apply_settings(settings)

        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self.close)

        self._apply_best_screen_fullscreen(str(settings.display_screen or "auto"))
        self._tick_clock()

    # ── Réglages ──────────────────────────────────────────────────────

    def apply_settings(self, settings) -> None:
        self._settings = settings
        self.setStyleSheet(
            f"QWidget {{ background: {settings.bg_color or '#000000'}; }}"
        )
        self._apply_settings(settings)
        preferred = str(settings.display_screen or "auto")
        if (
            preferred not in ("", "auto")
            and preferred != getattr(self, "_active_screen", "")
        ):
            self._apply_best_screen_fullscreen(preferred)

    def _apply_settings(self, settings) -> None:
        scale = max(1.0, min(3.0, self.height() / 1080.0 or 1.0))
        family = _resolve_family(str(settings.font_family or ""))
        text_size = max(16, int(round(float(settings.text_size or 54) * scale)))
        next_size = max(10, int(round(float(settings.next_size or 30) * scale)))
        clock_size = max(20, int(round(44 * scale)))

        font = QFont(family)
        font.setWeight(QFont.Weight.Bold)
        font.setPixelSize(text_size)
        self._current_text.setFont(font)
        self._current_text.setStyleSheet(
            f"color: {settings.text_color}; background: transparent;"
        )

        ref_font = QFont(family)
        ref_font.setPixelSize(max(12, int(text_size * 0.42)))
        ref_font.setWeight(QFont.Weight.DemiBold)
        self._current_ref.setFont(ref_font)
        self._current_ref.setVisible(bool(settings.show_reference))

        next_font = QFont(family)
        next_font.setPixelSize(next_size)
        next_font.setWeight(QFont.Weight.DemiBold)
        self._next_text.setFont(next_font)
        self._next_text.setStyleSheet(
            f"color: {settings.next_color}; background: transparent;"
        )
        nref_font = QFont(family)
        nref_font.setPixelSize(max(10, int(next_size * 0.5)))
        nref_font.setWeight(QFont.Weight.Bold)
        self._next_ref.setFont(nref_font)
        self._next_ref.setStyleSheet(
            f"color: {settings.next_color}; background: transparent;"
        )

        clock_font = QFont(family)
        clock_font.setPixelSize(clock_size)
        clock_font.setWeight(QFont.Weight.Bold)
        self._clock_label.setFont(clock_font)
        self._clock_label.setStyleSheet(
            "color: rgba(255,255,255,0.85); background: transparent;"
        )
        self._clock_label.setVisible(bool(settings.show_clock))

        self._next_block.setVisible(bool(settings.show_next))
        self._separator.setVisible(bool(settings.show_next))

        msg_font = QFont(family)
        msg_font.setPixelSize(max(18, int(clock_size * 0.7)))
        msg_font.setWeight(QFont.Weight.Bold)
        self._message_label.setFont(msg_font)

    # ── Contenu ───────────────────────────────────────────────────────

    def set_slide(self, slide: dict[str, Any] | None) -> None:
        slide = slide or {}
        if bool(slide.get("hidden")):
            self._current_ref.setText("(masqué)")
            self._current_text.setText("")
            return
        self._current_ref.setText(str(slide.get("reference") or ""))
        self._current_text.setText(str(slide.get("text") or ""))

    def set_next_slide(self, slide: dict[str, Any] | None) -> None:
        slide = slide or {}
        ref = str(slide.get("reference") or "")
        text = str(slide.get("text") or "")
        if not ref and not text:
            self._next_ref.setText("")
            self._next_text.setText("")
            return
        self._next_ref.setText(ref)
        self._next_text.setText(text)

    def show_message(self, text: str) -> None:
        clean = str(text or "").strip()
        if not clean:
            self.clear_message()
            return
        self._message_label.setText(clean)
        self._message_label.show()

    def clear_message(self) -> None:
        self._message_label.hide()
        self._message_label.setText("")

    # ── Divers ────────────────────────────────────────────────────────

    def _tick_clock(self) -> None:
        if not self._settings.show_clock:
            return
        from datetime import datetime

        self._clock_label.setText(datetime.now().strftime("%H:%M"))

    def _apply_best_screen_fullscreen(self, preferred_name: str = "auto") -> None:
        try:
            screens = QGuiApplication.screens()
            if not screens:
                self.showFullScreen()
                return
            target = next(
                (
                    s
                    for s in screens
                    if preferred_name not in ("", "auto")
                    and s.name() == preferred_name
                ),
                None,
            )
            if target is None and len(screens) >= 2:
                primary = QGuiApplication.primaryScreen()
                secondary = [s for s in screens if s != primary]
                if secondary:
                    target = max(
                        secondary,
                        key=lambda s: s.geometry().width() * s.geometry().height(),
                    )
            if target is None:
                target = max(
                    screens, key=lambda s: s.geometry().width() * s.geometry().height()
                )
            self._active_screen = str(target.name() or "")
            geo = target.geometry()
            self.setGeometry(geo)
            self.move(geo.topLeft())
            self.showFullScreen()
        except Exception:
            log.exception("Échec de la sélection de l'écran scène")
            self.showFullScreen()


class StageSettingsDialog(QDialog):
    """Réglages de l'écran scène : écran, tailles, horloge, suivant."""

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("stage_display"))
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setStyleSheet(DIALOG_STYLE)

        form = QFormLayout(self)
        form.setContentsMargins(22, 20, 22, 16)
        form.setSpacing(12)

        self._enabled = QCheckBox(tr("stage_enabled_startup"), self)
        self._enabled.setChecked(bool(settings.enabled))
        form.addRow(self._enabled)

        self._screen = QComboBox(self)
        self._screen.addItem(tr("screen_auto"), "auto")
        for screen in QGuiApplication.screens():
            geo = screen.geometry()
            label = (
                f"{screen.name()} · {geo.width()}×{geo.height()}"
                f"{tr('screen_primary') if screen == QGuiApplication.primaryScreen() else ''}"
            )
            self._screen.addItem(label, screen.name())
        index = self._screen.findData(str(settings.display_screen or "auto"))
        self._screen.setCurrentIndex(index if index >= 0 else 0)
        form.addRow(tr("output_screen"), self._screen)

        self._font = QComboBox(self)
        for family, _path in get_available_fonts():
            self._font.addItem(family, family)
        index = self._font.findData(str(settings.font_family or "Poppins"))
        self._font.setCurrentIndex(index if index >= 0 else 0)
        form.addRow(tr("font_family"), self._font)

        self._text_size = QSpinBox(self)
        self._text_size.setRange(16, 160)
        self._text_size.setValue(int(settings.text_size or 54))
        form.addRow(tr("stage_text_size"), self._text_size)

        self._next_size = QSpinBox(self)
        self._next_size.setRange(10, 120)
        self._next_size.setValue(int(settings.next_size or 30))
        form.addRow(tr("stage_next_size"), self._next_size)

        self._show_clock = QCheckBox(tr("stage_show_clock"), self)
        self._show_clock.setChecked(bool(settings.show_clock))
        form.addRow(self._show_clock)

        self._show_next = QCheckBox(tr("stage_show_next"), self)
        self._show_next.setChecked(bool(settings.show_next))
        form.addRow(self._show_next)

        self._show_reference = QCheckBox(tr("show_reference"), self)
        self._show_reference.setChecked(bool(settings.show_reference))
        form.addRow(self._show_reference)

        self._text_color = ColorPickerButton(str(settings.text_color), self)
        form.addRow(tr("stage_text_color"), self._text_color)

        self._next_color = ColorPickerButton(str(settings.next_color), self)
        form.addRow(tr("stage_next_color"), self._next_color)

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
        from app.utils.settings import StageSettings

        return StageSettings(
            enabled=self._enabled.isChecked(),
            display_screen=str(self._screen.currentData() or "auto"),
            font_family=str(self._font.currentData() or "Poppins"),
            text_size=self._text_size.value(),
            next_size=self._next_size.value(),
            show_clock=self._show_clock.isChecked(),
            show_next=self._show_next.isChecked(),
            show_reference=self._show_reference.isChecked(),
            text_color=self._text_color.color(),
            next_color=self._next_color.color(),
        ).sanitized()
