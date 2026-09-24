"""Startup splash: Fluent (Windows 11) card following the app theme.

Logo, name, the real loading step with a spinning ring, and a thin progress
bar that glides between steps. The card fades in, and fades out once the
main window is on screen.
"""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.ui.icons import app_logo_icon
from app.ui.theme import Colors, Radius, Typography
from app.utils.translations import tr
from app.version import __version__

_SHADOW_MARGIN = 24


class _ProgressRing(QWidget):
    """Indeterminate Fluent ring: an accent arc turning on a faint track."""

    def __init__(self, size: int = 16, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self) -> None:
        self._angle = (self._angle + 8) % 360
        self.update()

    def stop(self) -> None:
        self._timer.stop()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        stroke = 2.0
        rect = QRectF(self.rect()).adjusted(stroke, stroke, -stroke, -stroke)
        track = QColor(Colors.TEXT_PRIMARY)
        track.setAlphaF(0.08)
        painter.setPen(QPen(track, stroke))
        painter.drawEllipse(rect)
        pen = QPen(QColor(Colors.ACCENT_PRIMARY), stroke)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, -self._angle * 16, 100 * 16)


class _ProgressBar(QWidget):
    """Thin Fluent progress bar whose value is animatable."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(3)
        self._value = 0.0

    def _get_value(self) -> float:
        return self._value

    def _set_value(self, value: float) -> None:
        self._value = max(0.0, min(100.0, float(value)))
        self.update()

    value = Property(float, _get_value, _set_value)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        rect = QRectF(self.rect())
        radius = rect.height() / 2
        track = QColor(Colors.TEXT_PRIMARY)
        track.setAlphaF(0.08)
        painter.setBrush(track)
        painter.drawRoundedRect(rect, radius, radius)
        if self._value > 0:
            filled = QRectF(rect)
            filled.setWidth(max(rect.height(), rect.width() * self._value / 100.0))
            painter.setBrush(QColor(Colors.ACCENT_PRIMARY))
            painter.drawRoundedRect(filled, radius, radius)


class SplashScreen(QWidget):
    """Startup splash screen (Fluent card, real loading steps)."""

    loadingFinished = Signal()

    CARD_WIDTH = 440
    CARD_HEIGHT = 280

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SplashScreen
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(
            self.CARD_WIDTH + 2 * _SHADOW_MARGIN, self.CARD_HEIGHT + 2 * _SHADOW_MARGIN
        )

        self.container = QFrame(self)
        self.container.setObjectName("SplashCard")
        self.container.setGeometry(
            _SHADOW_MARGIN, _SHADOW_MARGIN, self.CARD_WIDTH, self.CARD_HEIGHT
        )
        self.container.setStyleSheet(
            f"""
            QFrame#SplashCard {{
                background: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.XXL}px;
            }}
            QLabel {{ background: transparent; border: none; }}
            """
        )
        shadow = QGraphicsDropShadowEffect(self.container)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.container.setGraphicsEffect(shadow)

        self._progress = 0
        self._init_ui()

        self._progress_anim = QPropertyAnimation(self.progress_bar, b"value", self)
        self._progress_anim.setDuration(260)
        self._progress_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.x() + (geo.width() - self.width()) // 2,
                geo.y() + (geo.height() - self.height()) // 2,
            )

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setWindowOpacity(0.0)
        self._animate_opacity(1.0, 180)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(32, 32, 32, 24)
        layout.setSpacing(0)
        layout.addStretch(1)

        logo = QLabel(self.container)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ratio = self.devicePixelRatioF() or 1.0
        pixmap = app_logo_icon().pixmap(round(64 * ratio), round(64 * ratio))
        pixmap.setDevicePixelRatio(ratio)
        logo.setPixmap(pixmap)
        logo.setFixedHeight(64)
        self.logo_label = logo
        layout.addWidget(logo)
        layout.addSpacing(16)

        self.title = QLabel(tr("app_name"), self.container)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-family: '{Typography.FAMILY}';"
            f" font-size: 28px; font-weight: {Typography.WEIGHT_SEMIBOLD};"
        )
        layout.addWidget(self.title)
        layout.addSpacing(2)

        self.subtitle = QLabel(tr("splash_tagline"), self.container)
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-family: '{Typography.FAMILY}';"
            f" font-size: {Typography.SIZE_CONTROL}px;"
        )
        layout.addWidget(self.subtitle)
        layout.addStretch(1)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(8)
        self.ring = _ProgressRing(16, self.container)
        status_row.addWidget(self.ring, 0, Qt.AlignmentFlag.AlignVCenter)
        self.status_label = QLabel(tr("loading"), self.container)
        self.status_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-family: '{Typography.FAMILY}';"
            f" font-size: {Typography.SIZE_FILTER}px;"
        )
        status_row.addWidget(self.status_label, 1)
        self.version_label = QLabel(f"v{__version__}", self.container)
        self.version_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-family: '{Typography.FAMILY}';"
            f" font-size: {Typography.SIZE_META}px;"
        )
        status_row.addWidget(self.version_label, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(status_row)
        layout.addSpacing(12)

        self.progress_bar = _ProgressBar(self.container)
        layout.addWidget(self.progress_bar)

    def _animate_opacity(self, target: float, duration: int) -> None:
        self._fade.stop()
        self._fade.setDuration(duration)
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(target)
        self._fade.start()

    def progress(self) -> int:
        return self._progress

    def set_progress(self, value: int, status: str = "") -> None:
        """Advance to *value* (0-100) and show the current loading step."""
        self._progress = min(100, max(0, int(value)))
        self._progress_anim.stop()
        self._progress_anim.setStartValue(self.progress_bar.value)
        self._progress_anim.setEndValue(float(self._progress))
        self._progress_anim.start()
        if status:
            self.status_label.setText(status)
        QApplication.processEvents()

    def finish(self, main_window: QWidget) -> None:
        """Complete the bar, show the main window, then fade the splash out."""
        self.set_progress(100, tr("splash_ready"))
        QTimer.singleShot(120, lambda: self._show_main(main_window))

    def _show_main(self, main_window: QWidget) -> None:
        main_window.show()
        self.ring.stop()
        self._fade.finished.connect(self._close_after_fade)
        self._animate_opacity(0.0, 200)

    def _close_after_fade(self) -> None:
        self.close()
        self.loadingFinished.emit()
