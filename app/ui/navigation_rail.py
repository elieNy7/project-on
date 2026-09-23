"""Fluent navigation rail (Windows 11 NavigationView, left mode).

Transparent over the window backdrop, collapsible to an icon strip. Keeps the
tab API of the former sidebar (addTab / setCurrentIndex / currentIndex /
currentChanged) so controllers and shortcuts are unchanged.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QAbstractButton, QFrame, QVBoxLayout, QWidget

from app.ui.icons import app_icon
from app.ui.theme import Colors, Typography, item_hover_color, item_selection_color

EXPANDED_WIDTH = 216
COMPACT_WIDTH = 56
_ITEM_HEIGHT = 40
_ICON = 18
_ICON_X = 16


class RailItem(QAbstractButton):
    """One navigation entry: icon, label, hover fill and selection pill."""

    def __init__(self, text: str, icon_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(text)
        self._icon_name = icon_name
        self._compact = False
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(_ITEM_HEIGHT)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(text)
        self._refresh_icons()

    def _refresh_icons(self) -> None:
        self._icon_idle = app_icon(self._icon_name, Colors.TEXT_SECONDARY)
        self._icon_active = app_icon(self._icon_name, Colors.TEXT_PRIMARY)

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        self.setToolTip(self.text() if compact else "")
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(EXPANDED_WIDTH - 8, _ITEM_HEIGHT)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(4, 2, -4, -2)

        if self.isChecked():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(item_selection_color())
            p.drawRoundedRect(rect, 4, 4)
            pill_h = 16 if not self.isDown() else 10
            pill = QRectF(rect.left(), rect.center().y() - pill_h / 2, 3, pill_h)
            p.setBrush(QColor(Colors.ACCENT_PRIMARY))
            p.drawRoundedRect(pill, 1.5, 1.5)
        elif self.underMouse():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(item_hover_color())
            p.drawRoundedRect(rect, 4, 4)

        icon = self._icon_active if self.isChecked() else self._icon_idle
        icon_top = int(rect.center().y() - _ICON / 2)
        icon.paint(p, _ICON_X, icon_top, _ICON, _ICON)

        if not self._compact:
            font = self.font()
            font.setPixelSize(Typography.SIZE_BODY)
            font.setWeight(
                QFont.Weight.DemiBold if self.isChecked() else QFont.Weight.Normal
            )
            p.setFont(font)
            p.setPen(
                QColor(Colors.TEXT_PRIMARY if self.isChecked() else Colors.TEXT_SECONDARY)
            )
            text_rect = QRectF(_ICON_X + _ICON + 14, rect.top(), rect.width() - 48, rect.height())
            p.drawText(
                text_rect,
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                self.text(),
            )
        p.end()


class NavigationRail(QFrame):
    """Left navigation rail with a pane toggle, main items and footer items."""

    currentChanged = Signal(int)
    compactChanged = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("NavigationRail")
        self.setStyleSheet("QFrame#NavigationRail { background: transparent; border: none; }")
        self.setFixedWidth(EXPANDED_WIDTH)

        self._items: list[RailItem] = []
        self._current_index = -1
        self._compact = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 8)
        layout.setSpacing(2)

        self.toggle_button = RailItem("Réduire le menu", "menu.svg", self)
        self.toggle_button.setCheckable(False)
        self.toggle_button.setFixedWidth(COMPACT_WIDTH)
        self.toggle_button.set_compact(True)  # icon only, label as tooltip
        self.toggle_button.clicked.connect(lambda: self.set_compact(not self._compact))
        layout.addWidget(self.toggle_button)
        layout.addSpacing(4)

        self._main = QVBoxLayout()
        self._main.setSpacing(2)
        layout.addLayout(self._main)
        layout.addStretch(1)

        self._footer = QVBoxLayout()
        self._footer.setSpacing(2)
        layout.addLayout(self._footer)

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.valueChanged.connect(lambda w: self.setFixedWidth(int(w)))

    # ── Tab API (compatible with the former Sidebar) ──

    def addTab(self, text: str, icon_name: str) -> int:  # noqa: N802
        return self._add(text, icon_name, self._main)

    def addFooterTab(self, text: str, icon_name: str) -> int:  # noqa: N802
        return self._add(text, icon_name, self._footer)

    def _add(self, text: str, icon_name: str, target: QVBoxLayout) -> int:
        item = RailItem(text, icon_name, self)
        item.set_compact(self._compact)
        index = len(self._items)
        item.clicked.connect(lambda _checked=False, i=index: self._on_clicked(i))
        self._items.append(item)
        target.addWidget(item)
        if index == 0:
            self.setCurrentIndex(0)
        return index

    def _on_clicked(self, index: int) -> None:
        if index == self._current_index:
            self._items[index].setChecked(True)  # a click must not uncheck
            return
        self.setCurrentIndex(index)

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        if not 0 <= index < len(self._items):
            return
        for i, item in enumerate(self._items):
            item.setChecked(i == index)
        if index != self._current_index:
            self._current_index = index
            self.currentChanged.emit(index)

    def currentIndex(self) -> int:  # noqa: N802
        return self._current_index

    def count(self) -> int:
        return len(self._items)

    # ── Compact mode ──

    def is_compact(self) -> bool:
        return self._compact

    def set_compact(self, compact: bool, animate: bool = True) -> None:
        compact = bool(compact)
        if compact == self._compact:
            return
        self._compact = compact
        for item in self._items:
            item.set_compact(compact)
        self.toggle_button.setText("Développer le menu" if compact else "Réduire le menu")
        self.toggle_button.set_compact(True)
        target = COMPACT_WIDTH if compact else EXPANDED_WIDTH
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self.width())
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self.setFixedWidth(target)
        self.compactChanged.emit(compact)
