"""Top command bar: brand, global search and live output status.

Replaces the former bottom status bar and keeps its public API
(update_slide, clear_slide, set_hidden, set_project_active,
set_obs_connected, set_hdmi_active) so the main window wiring is unchanged.
Every output state is spelled out in text, never by colour alone.
"""

from __future__ import annotations

import html

from PySide6.QtCore import QRectF, QSize, Qt, QTime, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QWidget,
)

from app.ui.icons import app_icon, app_logo_pixmap
from app.ui.theme import Colors, Radius, Typography, item_hover_color, to_qcolor
from app.utils.translations import tr


class StatusChip(QAbstractButton):
    """Compact output indicator: state dot, label, subtle hover."""

    def __init__(self, key: str, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self._dot = Colors.TEXT_DISABLED
        self.setText(label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(28)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def set_state(self, label: str, dot_color: str, tooltip: str) -> None:
        self.setText(label)
        self._dot = dot_color
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.updateGeometry()
        self.update()

    def _font(self) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(Typography.SIZE_META)
        font.setWeight(QFont.Weight.DemiBold)
        return font

    def sizeHint(self) -> QSize:  # noqa: N802
        width = QFontMetrics(self._font()).horizontalAdvance(self.text())
        return QSize(width + 30, 28)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(item_hover_color() if self.underMouse() else to_qcolor(Colors.GLASS_LIGHT))
        p.drawRoundedRect(rect, Radius.SM, Radius.SM)

        p.setBrush(QColor(self._dot))
        p.drawEllipse(QRectF(10, rect.center().y() - 3.5, 7, 7))

        p.setFont(self._font())
        p.setPen(QColor(Colors.TEXT_PRIMARY))
        p.drawText(
            QRectF(22, 0, rect.width() - 26, rect.height()),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            self.text(),
        )
        p.end()


class CommandBar(QFrame):
    """Transparent bar above the content, over the window backdrop."""

    outputClicked = Signal(str)  # "projection" | "obs" | "hdmi" | "ndi"

    _SOURCES = {
        "bible": ("SRC_BIBLE", "Bible"),
        "sermon": ("SRC_SERMON", "Prédication"),
        "hymn": ("SRC_HYMN", "Cantique"),
        "custom": ("SRC_CUSTOM", "Texte"),
        "image": ("SRC_IMAGE", "Média"),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CommandBar")
        self.setStyleSheet("QFrame#CommandBar { background: transparent; border: none; }")
        self.setFixedHeight(48)

        self._project_active = False
        self._hidden = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 6, 0, 6)
        layout.setSpacing(8)

        logo = QLabel(self)
        logo.setPixmap(app_logo_pixmap(18))
        logo.setFixedSize(18, 18)
        logo.setScaledContents(True)
        layout.addWidget(logo)
        brand = QLabel("Project-On", self)
        brand.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: {Typography.SIZE_FILTER}px;"
            f" font-weight: {Typography.WEIGHT_SEMIBOLD}; background: transparent;"
        )
        layout.addWidget(brand)
        layout.addSpacing(24)

        self.search_edit = QLineEdit(self)
        self.search_edit.setObjectName("GlobalSearch")
        self.search_edit.setPlaceholderText(tr("global_search_placeholder"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumWidth(280)
        self.search_edit.setMaximumWidth(560)
        self.search_edit.addAction(
            QAction(app_icon("search.svg", Colors.TEXT_SECONDARY), "", self.search_edit),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.search_edit.setAccessibleName(tr("global_search_placeholder"))
        layout.addWidget(self.search_edit, 3)
        layout.addStretch(1)

        # Current slide: source, reference and position in the programme.
        self._slide_label = QLabel("", self)
        self._slide_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: {Typography.SIZE_META}px;"
            " background: transparent;"
        )
        self._slide_label.setMaximumWidth(360)
        layout.addWidget(self._slide_label)

        self._chips: dict[str, StatusChip] = {}
        for key in ("projection", "obs", "hdmi", "ndi"):
            chip = StatusChip(key, key.upper(), self)
            chip.clicked.connect(lambda _c=False, k=key: self.outputClicked.emit(k))
            self._chips[key] = chip
            layout.addWidget(chip)

        self._clock = QLabel("", self)
        self._clock.setToolTip("Heure locale")
        self._clock.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: {Typography.SIZE_FILTER}px;"
            f" font-weight: {Typography.WEIGHT_SEMIBOLD}; background: transparent;"
            " padding: 0 6px 0 4px;"
        )
        layout.addWidget(self._clock)

        self._refresh_projection()
        self.set_obs_connected(False)
        self.set_hdmi_active(False)
        self.set_ndi_active(False)

        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._tick_time)
        self._clock_timer.start()
        self._tick_time()

    def chip(self, key: str) -> StatusChip:
        return self._chips[key]

    # ── Slide information ──

    def update_slide(self, source: str, reference: str, row: int, total: int) -> None:
        color_token, label = self._SOURCES.get(source, ("TEXT_MUTED", source))
        color = getattr(Colors, color_token, Colors.TEXT_MUTED)
        ref = " ".join(str(reference or "").split())
        if len(ref) > 48:
            ref = ref[:45] + "…"
        position = f"  ·  {row + 1}/{total}" if total > 0 and row >= 0 else ""
        self._slide_label.setText(
            f'<span style="color:{color}">●</span>&nbsp; '
            f"{html.escape(str(label))} — {html.escape(ref)}{position}"
        )
        self._slide_label.setToolTip(str(reference or ""))

    def clear_slide(self) -> None:
        self._slide_label.setText("")
        self._slide_label.setToolTip("")

    # ── Output states ──

    def set_hidden(self, hidden: bool) -> None:
        self._hidden = hidden
        self._refresh_projection()

    def set_project_active(self, active: bool) -> None:
        self._project_active = active
        self._refresh_projection()

    def _refresh_projection(self) -> None:
        chip = self._chips["projection"]
        if not self._project_active:
            chip.set_state("Projection", Colors.TEXT_DISABLED, "Projection : fenêtre fermée")
        elif self._hidden:
            chip.set_state("Masqué", Colors.ACCENT_DANGER, "Projection : texte masqué (Échap)")
        else:
            chip.set_state("En direct", Colors.ACCENT_SUCCESS, "Projection : en direct")

    def set_obs_connected(self, connected: bool) -> None:
        self._chips["obs"].set_state(
            "OBS",
            Colors.ACCENT_SUCCESS if connected else Colors.TEXT_DISABLED,
            "OBS : sortie active" if connected else "OBS : sortie arrêtée",
        )

    def set_hdmi_active(self, active: bool, label: str = "") -> None:
        self._chips["hdmi"].set_state(
            f"HDMI · {label}" if active and label else "HDMI",
            Colors.ACCENT_SUCCESS if active else Colors.TEXT_DISABLED,
            "HDMI mixeur : incrustation en direct" if active else "HDMI mixeur : éteint",
        )

    def set_ndi_active(self, active: bool) -> None:
        self._chips["ndi"].set_state(
            "NDI",
            Colors.ACCENT_SUCCESS if active else Colors.TEXT_DISABLED,
            "NDI : diffusion en cours" if active else "NDI : éteint",
        )

    def _tick_time(self) -> None:
        self._clock.setText(QTime.currentTime().toString("HH:mm"))
