from __future__ import annotations

from PyQt6.QtCore import QModelIndex, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from app.ui.theme import (
    Colors,
    Typography,
    item_hover_color,
    item_selection_color,
    item_separator_color,
    selected_text_color,
)


class HymnStanzaDelegate(QStyledItemDelegate):
    """Delegate for displaying hymn stanzas with a layout consistent with Bible verses."""

    CARD_PADDING_V = 4
    CARD_PADDING_H = 10

    def __init__(self, parent=None):
        super().__init__(parent)

        self.text_font = QFont(Typography.FAMILY)
        self.text_font.setPixelSize(13)
        self.text_font.setWeight(QFont.Weight.Normal)

        # Colors from theme
        self.color_bg_sel = item_selection_color()
        self.color_bg_hover = item_hover_color()
        self.color_separator = item_separator_color()
        self.color_text = QColor(Colors.TEXT_PRIMARY)
        self.color_text_dim = QColor(Colors.TEXT_MUTED)
        self.color_accent = QColor(Colors.ACCENT_PRIMARY)
        self.color_selected_text = selected_text_color()

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Data
        data = index.data(Qt.ItemDataRole.UserRole)
        ref = ""
        text = ""
        if isinstance(data, tuple) and len(data) == 2:
            ref, text = data

        is_sel = option.state & QStyle.StateFlag.State_Selected
        is_hover = option.state & QStyle.StateFlag.State_MouseOver

        rect = option.rect

        # Selection/Hover highlight
        if is_sel:
            painter.fillRect(rect, self.color_bg_sel)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.color_accent)
            painter.drawRect(rect.left(), rect.top() + 4, 3, rect.height() - 8)
        elif is_hover:
            painter.fillRect(rect, self.color_bg_hover)

        content_rect = rect.adjusted(
            self.CARD_PADDING_H,
            self.CARD_PADDING_V,
            -self.CARD_PADDING_H,
            -self.CARD_PADDING_V,
        )

        painter.setFont(self.text_font)
        painter.setPen(self.color_selected_text if is_sel else self.color_text)

        fm_text = QFontMetrics(self.text_font)
        text_start_x = int(content_rect.left())
        available_width = content_rect.width()

        text_rect = QRect(
            text_start_x, content_rect.top(), available_width, content_rect.height()
        )

        from app.ui.library_list_presentation import normalize_preview_text

        clean_text = normalize_preview_text(text)

        painter.drawText(
            text_rect,
            Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignTop,
            fm_text.elidedText(
                clean_text, Qt.TextElideMode.ElideRight, available_width * 2
            ),
        )

        # Subtle bottom border
        painter.setPen(self.color_separator)
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), 40)
