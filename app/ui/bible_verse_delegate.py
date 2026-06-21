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
)


class BibleVerseDelegate(QStyledItemDelegate):
    """Delegate professionnel pour afficher les versets de la Bible.
    Affiche le numéro du verset sur le côté et le texte en multi-ligne.
    """

    CARD_PADDING_V = 7
    CARD_PADDING_H = 10
    COLUMN_WIDTH = 30

    def __init__(self, parent=None):
        super().__init__(parent)

        # Setup typography - Initialize with pixel size
        self.marker_font = QFont(Typography.FAMILY)
        self.marker_font.setPixelSize(11)
        self.marker_font.setWeight(QFont.Weight.Bold)

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

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Data
        text = str(index.data(257) or "")
        from app.ui.library_list_presentation import normalize_preview_text

        text = normalize_preview_text(text)

        # Marker (Verse number)
        marker = "1"
        display_text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        # Extract number from "  1  Text..."
        parts = display_text.strip().split("  ", 1)
        if parts:
            marker = parts[0].strip()

        is_sel = option.state & QStyle.StateFlag.State_Selected
        is_hover = option.state & QStyle.StateFlag.State_MouseOver

        rect = option.rect

        # Selection/Hover highlight
        if is_sel:
            painter.fillRect(rect, self.color_bg_sel)
            # Accent line on the left
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

        # Draw Marker
        painter.setFont(self.marker_font)
        painter.setPen(self.color_accent if is_sel else self.color_text_dim)

        fm_marker = QFontMetrics(self.marker_font)
        painter.drawText(
            int(content_rect.left()),
            int(content_rect.top() + fm_marker.ascent() + 4),
            marker,
        )

        # Draw Verse Text (Multi-line elided)
        painter.setFont(self.text_font)
        painter.setPen(self.color_text)

        fm_text = QFontMetrics(self.text_font)
        text_start_x = int(content_rect.left() + self.COLUMN_WIDTH)
        available_width = content_rect.right() - text_start_x

        # Two-line text block
        text_rect = QRect(
            text_start_x, content_rect.top(), available_width, content_rect.height()
        )

        painter.drawText(
            text_rect,
            Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignTop,
            fm_text.elidedText(text, Qt.TextElideMode.ElideRight, available_width * 2),
        )

        # Subtle bottom border
        painter.setPen(self.color_separator)
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        # Allow two full lines of verse text to render without being clipped by
        # the next row (the previous fixed 40px clipped the second line, making
        # multi-line verses look cramped and overlapping).
        line_spacing = QFontMetrics(self.text_font).lineSpacing()
        height = self.CARD_PADDING_V * 2 + line_spacing * 2 + 2
        return QSize(option.rect.width(), max(40, height))
