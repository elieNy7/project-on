"""Suggestion flyout of the global search (Fluent AutoSuggestBox).

An overlay child of the window, anchored under the search field. Results are
grouped by library and arrive progressively, one group per source. Typing
focus never leaves the field: arrows move the selection, Enter opens the
hit, Escape closes the flyout.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QModelIndex, QObject, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from app.ui.icons import app_icon
from app.ui.theme import Colors, Radius, Typography, item_hover_color, item_selection_color
from app.utils.global_search import KIND_LABELS, KINDS

_HIT = Qt.ItemDataRole.UserRole
_HEADER = Qt.ItemDataRole.UserRole + 1

_ICONS = {
    "bible": "book.svg",
    "sermon": "mic.svg",
    "expose": "file-text.svg",
    "media": "image.svg",
    "playlist": "play.svg",
}


class _HitDelegate(QStyledItemDelegate):
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        if index.data(_HEADER):
            return QSize(option.rect.width(), 30)
        hit = index.data(_HIT) or {}
        return QSize(option.rect.width(), 52 if hit.get("subtitle") else 36)

    def paint(self, p: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(4, 1, -4, -1)
        font = QFont(option.font)

        header = index.data(_HEADER)
        if header:
            font.setPixelSize(Typography.SIZE_META)
            font.setWeight(QFont.Weight.DemiBold)
            p.setFont(font)
            p.setPen(QColor(Colors.TEXT_SECONDARY))
            p.drawText(
                rect.adjusted(10, 6, -10, 0),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                str(header),
            )
            p.restore()
            return

        hit: dict[str, Any] = index.data(_HIT) or {}
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hovered:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(item_selection_color() if selected else item_hover_color())
            p.drawRoundedRect(rect, Radius.SM, Radius.SM)
        if selected:
            p.setBrush(QColor(Colors.ACCENT_PRIMARY))
            p.drawRoundedRect(QRect(rect.left(), rect.center().y() - 8, 3, 16), 1.5, 1.5)

        icon = app_icon(_ICONS.get(str(hit.get("kind")), "search.svg"), Colors.TEXT_SECONDARY)
        icon.paint(p, QRect(rect.left() + 12, rect.center().y() - 8, 16, 16))

        text_left = rect.left() + 40
        width = rect.width() - 52
        subtitle = str(hit.get("subtitle") or "")

        font.setPixelSize(Typography.SIZE_CONTROL)
        font.setWeight(QFont.Weight.DemiBold if subtitle else QFont.Weight.Normal)
        p.setFont(font)
        p.setPen(QColor(Colors.TEXT_PRIMARY))
        title_rect = QRect(text_left, rect.top() + (7 if subtitle else 0), width, 20 if subtitle else rect.height())
        title = p.fontMetrics().elidedText(str(hit.get("title") or ""), Qt.TextElideMode.ElideRight, width)
        p.drawText(title_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), title)

        if subtitle:
            font.setPixelSize(Typography.SIZE_META)
            font.setWeight(QFont.Weight.Normal)
            p.setFont(font)
            p.setPen(QColor(Colors.TEXT_SECONDARY))
            sub = p.fontMetrics().elidedText(subtitle, Qt.TextElideMode.ElideRight, width)
            p.drawText(
                QRect(text_left, rect.top() + 27, width, 18),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                sub,
            )
        p.restore()


class GlobalSearchPopup(QFrame):
    """Grouped, progressive result list anchored under a QLineEdit."""

    hitActivated = Signal(dict)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("GlobalSearchPopup")
        self.setStyleSheet(
            f"""
            QFrame#GlobalSearchPopup {{
                background: {Colors.BG_ELEVATED};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.LG}px;
            }}
            QListWidget {{ background: transparent; border: none; outline: none; }}
            """
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 70))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        self._list = QListWidget(self)
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # typing stays in the field
        self._list.setMouseTracking(True)
        self._list.setItemDelegate(_HitDelegate(self._list))
        self._list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self._list.itemClicked.connect(self._on_clicked)
        layout.addWidget(self._list)

        self._status = QLabel("", self)
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: {Typography.SIZE_FILTER}px;"
            " padding: 14px; background: transparent;"
        )
        layout.addWidget(self._status)

        self._anchor: QLineEdit | None = None
        self._groups: dict[str, list[dict[str, Any]]] = {}
        # Until the operator moves the selection, it follows the first hit
        # (groups arrive in any order but are listed in library order).
        self._user_moved = False
        # False once the flyout is dismissed: late groups must not reopen it.
        self._active = False
        self.hide()

    # ── Anchoring and keyboard ──

    def attach(self, line_edit: QLineEdit) -> None:
        self._anchor = line_edit
        line_edit.installEventFilter(self)

    # Keys the field handles itself: without this, application shortcuts
    # (Escape hides the live projection, Enter projects) would fire while the
    # operator is only typing a search.
    _OWN_KEYS = (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Up, Qt.Key.Key_Down)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if obj is self._anchor:
            if event.type() == QEvent.Type.ShortcutOverride and event.key() in self._OWN_KEYS:
                event.accept()
                return False
            if event.type() == QEvent.Type.KeyPress and self.isVisible():
                key = event.key()
                if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                    self._user_moved = True
                    self._move(1 if key == Qt.Key.Key_Down else -1)
                    return True
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self._activate_current()
                    return True
                if key == Qt.Key.Key_Escape:
                    self.dismiss()
                    return True
            elif event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                obj.clear()
                obj.clearFocus()
                return True
            elif event.type() == QEvent.Type.FocusOut:
                self.dismiss()
        return super().eventFilter(obj, event)

    def reposition(self) -> None:
        if self._anchor is None or self.parentWidget() is None:
            return
        parent = self.parentWidget()
        top_left = self._anchor.mapTo(parent, QPoint(0, self._anchor.height() + 4))
        width = max(self._anchor.width(), 560)
        width = min(width, parent.width() - top_left.x() - 12)
        rows = sum(self._list.sizeHintForIndex(self._list.model().index(r, 0)).height()
                   for r in range(self._list.count()))
        body = rows + 10 if self._list.count() else self._status.sizeHint().height() + 8
        height = min(max(body, 48), int(parent.height() * 0.7), 520)
        self.setGeometry(top_left.x(), top_left.y(), width, height)
        self.raise_()

    # ── Results ──

    def begin(self) -> None:
        """A new query started: results will stream in per library."""
        self._groups = {}
        self._user_moved = False
        self._active = True
        self._render(searching=True)

    def dismiss(self) -> None:
        self._active = False
        self.hide()

    def add_group(self, kind: str, hits: list[dict[str, Any]]) -> None:
        if not self._active:
            return
        self._groups[kind] = hits
        self._render(searching=len(self._groups) < len(KINDS))

    def _render(self, searching: bool) -> None:
        current = self.current_hit() if self._user_moved else None
        self._list.clear()
        for kind in KINDS:
            hits = self._groups.get(kind) or []
            if not hits:
                continue
            header = QListWidgetItem()
            header.setData(_HEADER, KIND_LABELS.get(kind, kind))
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(header)
            for hit in hits:
                item = QListWidgetItem(str(hit.get("title") or ""))
                item.setData(_HIT, hit)
                item.setToolTip(str(hit.get("subtitle") or ""))
                self._list.addItem(item)
                if current is not None and hit == current:
                    self._list.setCurrentItem(item)

        has_rows = self._list.count() > 0
        self._list.setVisible(has_rows)
        self._status.setVisible(not has_rows)
        self._status.setText("Recherche…" if searching else "Aucun résultat")
        if has_rows and self._list.currentItem() is None:
            self._list.setCurrentRow(-1)
            self._move(1)
        self.reposition()
        self.show()

    def current_hit(self) -> dict[str, Any] | None:
        item = self._list.currentItem()
        return item.data(_HIT) if item is not None else None

    def _move(self, step: int) -> None:
        count = self._list.count()
        if not count:
            return
        row = self._list.currentRow()
        for _ in range(count):
            row = (row + step) % count
            if self._list.item(row).data(_HIT) is not None:
                self._list.setCurrentRow(row)
                return

    def _activate_current(self) -> None:
        hit = self.current_hit()
        if hit is not None:
            self.dismiss()
            self.hitActivated.emit(hit)

    def _on_clicked(self, item: QListWidgetItem) -> None:
        if item.data(_HIT) is not None:
            self._list.setCurrentItem(item)
            self._activate_current()
