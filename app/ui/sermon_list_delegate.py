from __future__ import annotations

from PyQt6.QtCore import QModelIndex, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from app.ui.theme import (
    Colors,
    Typography,
    item_hover_color,
    item_selection_color,
    selected_text_color,
)


class SermonListDelegate(QStyledItemDelegate):
    """Delegate pour afficher les sermons dans la liste de gauche.
    Affiche:
    - Titre (Gras)
    - Date & Location (Muted)
    - Tradition/Traducteur (Badge)
    """

    CARD_PADDING_V = 6
    CARD_PADDING_H = 10
    ICON_SIZE = 16

    def __init__(self, parent=None):
        super().__init__(parent)

        # Fonts - Initialize with pixel size
        self.title_font = QFont(Typography.FAMILY)
        self.title_font.setPixelSize(13)
        self.title_font.setWeight(QFont.Weight.Bold)

        self.detail_font = QFont(Typography.FAMILY)
        self.detail_font.setPixelSize(11)
        self.detail_font.setWeight(QFont.Weight.Normal)

        # Colors
        self.color_bg_sel = item_selection_color(strong=True)
        self.color_bg_hover = item_hover_color()
        self.color_text = QColor(Colors.TEXT_PRIMARY)
        self.color_text_muted = QColor(Colors.TEXT_MUTED)
        self.color_accent = QColor(Colors.ACCENT_PRIMARY)
        self.color_badge_bg = QColor(Colors.BG_ELEVATED)
        self.color_badge_text = QColor(Colors.TEXT_SECONDARY)
        self.color_selected_text = selected_text_color()

    @staticmethod
    def _format_date(date_str: str) -> str:
        """Formate le code date SHP en affichage lisible: 63-01-15 -> 15/01/1963"""
        if not date_str or len(date_str) < 8:
            return date_str
        # Format: YY-MM-DD[Suffix]
        parts = date_str.split("-")
        if len(parts) == 3:
            yr = parts[0]
            mo = parts[1]
            dd_sfx = parts[2]  # ex: "15M" ou "15"
            dd = "".join(c for c in dd_sfx if c.isdigit())
            sfx = "".join(c for c in dd_sfx if c.isalpha())
            try:
                yr_int = int(yr)
                year_4d = 1900 + yr_int if yr_int >= 47 else 2000 + yr_int
                label = f"{dd}/{mo}/{year_4d}"
                if sfx and sfx not in ("M", "S", "P"):
                    label += sfx
                elif sfx == "M":
                    label += " M"
                elif sfx == "S":
                    label += " S"
                return label
            except ValueError:
                pass
        return date_str

    @staticmethod
    def _format_location(location: str) -> str:
        """Extrait la ville propre depuis le location complet."""
        if not location or location in ("None", "Lieu inconnu"):
            return ""
        # Garder seulement les 2 premiers mots (ville + état/pays)
        parts = location.strip().split()
        if len(parts) >= 2:
            # Retirer "USA" ou "CANADA" en fin si redondant
            if parts[-1] in ("USA", "CANADA", "SUISSE", "ALLEMAGNE"):
                parts = parts[:-1]
            return " ".join(parts[:2])  # Ville + code état
        return location

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        title = str(index.data(Qt.ItemDataRole.UserRole + 1) or "")
        date_str = str(index.data(Qt.ItemDataRole.UserRole + 2) or "")
        location = str(index.data(Qt.ItemDataRole.UserRole + 3) or "")
        tradition = str(index.data(Qt.ItemDataRole.UserRole + 4) or "")

        if not title:
            title = option.text

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

        content_rect = rect.adjusted(
            self.CARD_PADDING_H,
            self.CARD_PADDING_V // 2,
            -self.CARD_PADDING_H,
            -self.CARD_PADDING_V // 2,
        )

        # Badge dimensions (pre-compute)
        fm_detail = QFontMetrics(self.detail_font)
        badge_text = tradition.upper() if tradition else ""
        badge_w = fm_detail.horizontalAdvance(badge_text) + 10 if badge_text else 0
        badge_h = fm_detail.height() + 4

        # 1. Titre
        painter.setFont(self.title_font)
        painter.setPen(self.color_text if not is_sel else self.color_selected_text)
        fm_title = QFontMetrics(self.title_font)
        available_w = content_rect.width() - badge_w - (4 if badge_w else 0)
        elided_title = fm_title.elidedText(
            title, Qt.TextElideMode.ElideRight, available_w
        )
        painter.drawText(
            content_rect.left(), content_rect.top() + fm_title.ascent(), elided_title
        )

        # 2. Details: date formatée + lieu court
        date_display = self._format_date(date_str)
        loc_display = self._format_location(location)
        details_parts = [p for p in [date_display, loc_display] if p]
        details = "  •  ".join(details_parts)

        if details:
            painter.setFont(self.detail_font)
            painter.setPen(self.color_text_muted)
            y_detail = content_rect.top() + fm_title.height() + 4 + fm_detail.ascent()
            elided_details = fm_detail.elidedText(
                details, Qt.TextElideMode.ElideRight, content_rect.width() - badge_w - 4
            )
            painter.drawText(content_rect.left(), y_detail, elided_details)

        # 3. Badge tradition (droite, centré verticalement)
        if badge_text:
            badge_rect = QRect(
                rect.right() - self.CARD_PADDING_H - badge_w,
                rect.top() + (rect.height() - badge_h) // 2,
                badge_w,
                badge_h,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.color_badge_bg)
            painter.drawRoundedRect(badge_rect, 4, 4)
            painter.setPen(self.color_badge_text)
            painter.setFont(self.detail_font)
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), 44)
