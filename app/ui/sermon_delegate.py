from __future__ import annotations

from PyQt6.QtCore import QModelIndex, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from app.ui.theme import (
    Colors,
    Typography,
    item_hover_color,
    item_selection_color,
    item_separator_color,
)


class SermonParagraphDelegate(QStyledItemDelegate):
    """Delegate professionnel pour afficher les paragraphes de sermons de façon compacte (une seule ligne)."""

    CARD_PADDING_V = 4
    CARD_PADDING_H = 10
    PARA_ID_WIDTH = 52  # Sufficient space for icons like ¶123 or E-050

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
        self.color_border = QColor(Colors.BORDER_SUBTLE)
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
        ref = str(index.data(256) or "")
        # Get normalized text for the list view
        from app.ui.library_list_presentation import normalize_preview_text

        text = normalize_preview_text(str(index.data(257) or ""))

        # Marker extraction logic (E-1, §001, (12), ¶1)
        para_id = str(index.data(258) or "")
        if not para_id:
            if "§" in ref:
                para_id = "§" + ref.rsplit("§", maxsplit=1)[-1].split(maxsplit=1)[0]
            elif "¶" in ref:
                para_id = "¶" + ref.rsplit("¶", 1)[-1].strip()
            else:
                # Fallback to the marker in display text if present
                disp = option.text
                if "|" in disp:
                    para_id = disp.split("|")[0].strip()

        is_sel = option.state & QStyle.StateFlag.State_Selected
        is_hover = option.state & QStyle.StateFlag.State_MouseOver

        rect = option.rect

        # Selection/Hover highlight
        if is_sel:
            painter.fillRect(rect, self.color_bg_sel)
            # Accent line on the left
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.color_accent)
            painter.drawRect(rect.left(), rect.top() + 2, 3, rect.height() - 4)
        elif is_hover:
            painter.fillRect(rect, self.color_bg_hover)

        content_rect = rect.adjusted(self.CARD_PADDING_H, 0, -self.CARD_PADDING_H, 0)

        # Draw Para ID (Marker)
        painter.setFont(self.marker_font)
        painter.setPen(self.color_accent if is_sel else self.color_text)

        fm_para = QFontMetrics(self.marker_font)
        y_center = int(content_rect.center().y() + (fm_para.ascent() / 2) - 2)

        painter.drawText(int(content_rect.left()), y_center, para_id)

        # Draw Paragraph Text (Single line elided)
        painter.setFont(self.text_font)
        painter.setPen(self.color_text if not is_sel else QColor(Colors.TEXT_PRIMARY))

        fm_text = QFontMetrics(self.text_font)
        text_start_x = int(content_rect.left() + self.PARA_ID_WIDTH)
        available_width = content_rect.right() - text_start_x

        elided_text = fm_text.elidedText(
            text, Qt.TextElideMode.ElideRight, available_width
        )
        painter.drawText(text_start_x, y_center, elided_text)

        # Subtle bottom border
        painter.setPen(self.color_separator)
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), 30)
