import re

from PyQt6.QtCore import QModelIndex, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from app.ui.library_list_presentation import normalize_preview_text
from app.ui.theme import (
    Colors,
    Typography,
    item_hover_color,
    item_selection_color,
    item_separator_color,
)

# Regex to match markers like "p.51 §3", "§123", or "49-1" at the end of a ref
_MARKER_RE = re.compile(r"(?:p\.\s*\d+\s+)?(?:§\d+|\d+-\d+)$")


class ExposeParagraphDelegate(QStyledItemDelegate):
    """Delegate professionnel pour afficher les paragraphes de l'Exposé de façon compacte.
    Affiche la page et le numéro du paragraphe dans une colonne dédiée.
    """

    CARD_PADDING_V = 8
    CARD_PADDING_H = 12
    COLUMN_WIDTH = 85

    def __init__(self, parent=None):
        super().__init__(parent)

        # Setup typography - Initialize with pixel size
        self.marker_font = QFont(Typography.FAMILY)
        self.marker_font.setPixelSize(11)
        self.marker_font.setWeight(QFont.Weight.Bold)

        self.text_font = QFont(Typography.FAMILY)
        self.text_font.setPixelSize(14)
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
        ref = str(index.data(256) or "")
        text = normalize_preview_text(str(index.data(257) or ""))

        # Extract Marker (p.51 §3)
        marker = ""
        match = _MARKER_RE.search(ref)
        if match:
            marker = match.group(0)
        else:
            disp = option.text
            if "|" in disp:
                marker = disp.split("|")[0].strip()

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
        # Vertically centered marker
        painter.drawText(
            int(content_rect.left() + 4),
            int(content_rect.top() + fm_marker.ascent() + 6),
            marker,
        )

        # Draw Paragraph Text (Multi-line elided)
        painter.setFont(self.text_font)
        painter.setPen(self.color_text if is_sel else self.color_text)

        fm_text = QFontMetrics(self.text_font)
        text_start_x = int(content_rect.left() + self.COLUMN_WIDTH)
        available_width = content_rect.right() - text_start_x

        # Two-line text block
        text_rect = QRect(
            text_start_x,
            content_rect.top() + 2,
            available_width,
            content_rect.height() - 4,
        )

        # In PyQt6, elidedText just returns a string, drawText needs string
        elided_text = fm_text.elidedText(
            text, Qt.TextElideMode.ElideRight, available_width * 2
        )
        painter.drawText(
            text_rect, Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignTop, elided_text
        )

        # Subtle bottom border
        painter.setPen(self.color_separator if not is_sel else Qt.PenStyle.NoPen)
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), 52)
