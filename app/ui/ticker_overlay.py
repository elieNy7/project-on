from __future__ import annotations

"""Bandeau défilant d'annonces (façon ProPresenter ticker).

Widget enfant de la fenêtre de projection, ancré en bas, dessiné par-dessus
la slide. Défilement continu d'une ligne composée de toutes les annonces,
séparées par un point médian.
"""

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QWidget


class TickerOverlay(QWidget):
    """Bandeau défilant ancré en bas de la projection."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._texts: list[str] = []
        self._speed = 90.0  # px/s
        self._font_size = 30
        self._bg_color = QColor(5, 10, 22, int(0.82 * 255))
        self._text_color = QColor(255, 255, 255, int(0.95 * 255))
        self._offset = 0.0
        self._line = ""
        self._line_width = 0.0
        self._sep = "   •   "
        self._last_ms = 0

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._on_tick)

    # ── Configuration ──────────────────────────────────────────────────

    def configure(
        self,
        texts: list[str],
        enabled: bool,
        speed: int = 90,
        height: int = 64,
        bg_color: str = "rgba(5,10,22,0.82)",
        text_color: str = "rgba(255,255,255,0.95)",
        font_size: int = 30,
    ) -> None:
        self._texts = [str(t or "").strip() for t in (texts or []) if str(t or "").strip()]
        self._speed = max(20.0, min(400.0, float(speed or 90)))
        self._font_size = max(14, min(90, int(font_size or 30)))
        self._bg_color = self._color(bg_color, self._bg_color)
        self._text_color = self._color(text_color, self._text_color)
        self.setFixedHeight(max(32, min(220, int(height or 64))))
        self._line = self._sep.join(self._texts)
        self._measure()
        self._offset = 0.0
        self.setVisible(bool(enabled and self._texts))
        if self.isVisible():
            self._last_ms = 0
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def _measure(self) -> None:
        font = QFont(self.font().family())
        font.setPixelSize(self._font_size)
        font.setWeight(QFont.Weight.DemiBold)
        self.setFont(font)
        if self._line:
            metrics = QFontMetrics(font)
            self._line_width = float(metrics.horizontalAdvance(self._line))
        else:
            self._line_width = 0.0

    @staticmethod
    def _color(value: str, fallback: QColor) -> QColor:
        try:
            if "rgba" in str(value):
                import re

                m = re.match(
                    r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)", str(value)
                )
                if m:
                    return QColor(
                        int(m.group(1)),
                        int(m.group(2)),
                        int(m.group(3)),
                        int(float(m.group(4)) * 255),
                    )
            color = QColor(str(value))
            return color if color.isValid() else fallback
        except Exception:
            return fallback

    # ── Défilement ─────────────────────────────────────────────────────

    def _on_tick(self) -> None:
        import time

        now = time.monotonic() * 1000.0
        if not self._last_ms:
            self._last_ms = now
            return
        dt = (now - self._last_ms) / 1000.0
        self._last_ms = now
        span = self._line_width + self.width()
        if span <= 0:
            return
        self._offset += self._speed * dt
        if self._offset > span:
            self._offset = 0.0
        self.update()

    # ── Peinture ───────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        if not self._line:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.fillRect(self.rect(), self._bg_color)

        # Liseré supérieur discret
        painter.setPen(QPen(QColor(255, 255, 255, 26), 1))
        painter.drawLine(0, 0, self.width(), 0)

        painter.setPen(self._text_color)
        x = float(self.width()) - self._offset
        painter.drawText(
            QRectF(x, 0.0, self._line_width + 8.0, float(self.height())),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._line,
        )
