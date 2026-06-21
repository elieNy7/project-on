from __future__ import annotations

from PyQt6.QtCore import QModelIndex, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from app.ui.theme import (
    Colors,
    Typography,
    item_hover_color,
    item_selection_color,
    selected_badge_text_color,
    selected_text_color,
)


class HymnDelegate(QStyledItemDelegate):
    """Delegate for displaying hymns in the list.
    Displays:
    - Hymn index/ID (Badge)
    - Hymn title
    """

    CARD_PADDING_V = 10
    CARD_PADDING_H = 12

    def __init__(self, parent=None):
        super().__init__(parent)

        # Fonts - Initialize with pixel size
        self.title_font = QFont(Typography.FAMILY)
        self.title_font.setPixelSize(13)
        self.title_font.setWeight(QFont.Weight.Medium)

        self.num_font = QFont(Typography.FAMILY)
        self.num_font.setPixelSize(11)
        self.num_font.setWeight(QFont.Weight.Bold)

        # Colors
        self.color_bg_sel = item_selection_color(strong=True)
        self.color_bg_hover = item_hover_color()
        self.color_text = QColor(Colors.TEXT_PRIMARY)
        self.color_text_muted = QColor(Colors.TEXT_MUTED)
        self.color_accent = QColor(Colors.ACCENT_PRIMARY)
        self.color_num_bg = QColor(Colors.BG_ELEVATED)
        self.color_selected_text = selected_text_color()
        self.color_selected_badge_text = selected_badge_text_color()

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        title = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        badge_text = str(
            index.data(Qt.ItemDataRole.UserRole + 1)
            or index.data(Qt.ItemDataRole.UserRole)
            or index.row() + 1
        )

        rect = option.rect
        is_sel = option.state & QStyle.StateFlag.State_Selected
        is_hover = option.state & QStyle.StateFlag.State_MouseOver

        # Background
        if is_sel:
            painter.fillRect(rect, self.color_bg_sel)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.color_accent)
            painter.drawRoundedRect(
                rect.left() + 2, rect.top() + 4, 3, rect.height() - 8, 1.5, 1.5
            )
        elif is_hover:
            painter.fillRect(rect, self.color_bg_hover)

        content_rect = rect.adjusted(self.CARD_PADDING_H, 0, -self.CARD_PADDING_H, 0)

        # Draw number badge
        badge_width = max(32, min(58, QFontMetrics(self.num_font).horizontalAdvance(badge_text) + 14))
        badge_height = 20
        y_pos = int(rect.center().y() - badge_height / 2)
        num_rect = QRect(content_rect.left(), y_pos, badge_width, badge_height)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.color_num_bg if not is_sel else self.color_accent)
        painter.drawRoundedRect(num_rect, 10, 10)

        painter.setFont(self.num_font)
        painter.setPen(
            self.color_text_muted if not is_sel else self.color_selected_badge_text
        )
        painter.drawText(num_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        # Draw Title
        painter.setFont(self.title_font)
        painter.setPen(self.color_text if not is_sel else self.color_selected_text)

        text_x = num_rect.right() + 12
        text_w = content_rect.right() - text_x
        text_rect = QRect(text_x, rect.top(), text_w, rect.height())

        elided = QFontMetrics(self.title_font).elidedText(
            title, Qt.TextElideMode.ElideRight, text_w
        )
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            elided,
        )

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), 36)
