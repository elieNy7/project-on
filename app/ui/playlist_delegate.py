"""Delegate personnalisé pour afficher les slides de la playlist avec un design moderne."""

from __future__ import annotations

from PyQt6.QtCore import QModelIndex, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTreeView

from app.ui.theme import Colors, Typography, get_theme
from app.utils.playlist_model import PlaylistRoles

# ═══════════════════════════════════════════════════════════════════════════
#  Source colours / labels
# ═══════════════════════════════════════════════════════════════════════════
_SOURCE_COLORS: dict[str, tuple[QColor, str]] = {
    "bible": (QColor(Colors.SRC_BIBLE), "Bible"),
    "sermon": (QColor(Colors.SRC_SERMON), "Sermon"),
    "hymn": (QColor(Colors.SRC_HYMN), "Cantique"),
    "expose": (QColor("#00acc1"), "Exposé"),
    "custom": (QColor(Colors.SRC_CUSTOM), "Texte"),
    "image": (QColor(Colors.SRC_IMAGE), "Image"),
}


# ═══════════════════════════════════════════════════════════════════════════
#  Shared palette  (keeps everything in one place)
# ═══════════════════════════════════════════════════════════════════════════
def _with_alpha(color: str, alpha: int) -> QColor:
    qcolor = QColor(color)
    qcolor.setAlpha(alpha)
    return qcolor


class _P:
    """Palette constants based on global theme."""

    IS_LIGHT = get_theme() == "light"
    CARD_BG = _with_alpha("#ffffff", 230 if IS_LIGHT else 6)
    CARD_SEL_BG = (
        QColor("#fff1d2") if IS_LIGHT else _with_alpha(Colors.ACCENT_PRIMARY, 26)
    )
    CARD_SEL_BG_2 = (
        QColor("#ffffff") if IS_LIGHT else _with_alpha(Colors.BG_ELEVATED, 72)
    )
    CARD_SEL_BORDER = _with_alpha(Colors.ACCENT_PRIMARY, 170 if IS_LIGHT else 80)
    CARD_HOVER = _with_alpha(
        "#f8fbff" if IS_LIGHT else "#ffffff", 245 if IS_LIGHT else 10
    )

    FOLDER_BG = _with_alpha("#ffffff", 220 if IS_LIGHT else 6)
    FOLDER_SEL_BG = (
        QColor("#fff1d2") if IS_LIGHT else _with_alpha(Colors.ACCENT_PRIMARY, 26)
    )
    FOLDER_SEL_BG_2 = (
        QColor("#ffffff") if IS_LIGHT else _with_alpha(Colors.BG_ELEVATED, 72)
    )
    FOLDER_HOVER_BG = _with_alpha(
        "#f8fbff" if IS_LIGHT else "#ffffff", 245 if IS_LIGHT else 8
    )
    FOLDER_ACCENT = QColor(Colors.ACCENT_PRIMARY)
    FOLDER_TEXT = QColor(Colors.TEXT_SECONDARY)
    FOLDER_TEXT_SEL = QColor(Colors.TEXT_PRIMARY if IS_LIGHT else Colors.ACCENT_PRIMARY)
    FOLDER_CHEVRON = QColor(Colors.TEXT_MUTED)

    ACCENT = QColor(Colors.ACCENT_PRIMARY)
    REF_NORMAL = QColor(Colors.TEXT_SECONDARY)
    REF_SEL = QColor("#8a560f" if IS_LIGHT else Colors.ACCENT_PRIMARY)
    TEXT_NORMAL = QColor("#5f6b7a" if IS_LIGHT else Colors.TEXT_MUTED)
    TEXT_SEL = QColor(Colors.TEXT_PRIMARY)
    SEPARATOR = _with_alpha("#172033" if IS_LIGHT else "#ffffff", 28 if IS_LIGHT else 10)
    NUMBER_BG = _with_alpha(Colors.ACCENT_PRIMARY, 24 if IS_LIGHT else 26)
    NUMBER_TEXT = QColor(Colors.ACCENT_PRIMARY)
    NUMBER_TEXT.setAlpha(180)


class PlaylistDelegate(QStyledItemDelegate):
    """Delegate moderne pour afficher les slides avec un design professionnel."""

    SLIDE_MIN_HEIGHT = 72
    SLIDE_PADDING = 12
    REFERENCE_FONT_SIZE = 11
    TEXT_FONT_SIZE = 13
    TAG_FONT_SIZE = 9
    BORDER_RADIUS = 8
    FOLDER_HEIGHT = 38
    FOLDER_RADIUS = 6

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # Pre-create fonts (avoid re-creating on every paint)
        self._folder_font = QFont(Typography.FAMILY)
        self._folder_font.setPixelSize(13)
        self._folder_font.setWeight(QFont.Weight.DemiBold)

        self._chevron_font = QFont(Typography.FAMILY)
        self._chevron_font.setPixelSize(11)

        self._tag_font = QFont(Typography.FAMILY)
        self._tag_font.setPixelSize(max(10, self.TAG_FONT_SIZE))
        self._tag_font.setWeight(QFont.Weight.Bold)

        self._ref_font = QFont(Typography.FAMILY)
        self._ref_font.setPixelSize(max(11, self.REFERENCE_FONT_SIZE))
        self._ref_font.setWeight(QFont.Weight.DemiBold)

        self._text_font = QFont(Typography.FAMILY)
        self._text_font.setPixelSize(max(12, self.TEXT_FONT_SIZE))

    # ──────────────────────────────────────────────────────────────────
    #  Size hint
    # ──────────────────────────────────────────────────────────────────
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        if index.data(PlaylistRoles.IsFolderRole):
            return QSize(option.rect.width(), self.FOLDER_HEIGHT)

        text = index.data(PlaylistRoles.TextRole) or ""
        fm = QFontMetrics(self._text_font)

        avail_w = max(
            200,
            (
                (option.rect.width() - self.SLIDE_PADDING * 2 - 44)
                if option.rect.width() > 0
                else 250
            ),
        )
        text_rect = fm.boundingRect(
            QRect(0, 0, avail_w, 2000),
            Qt.TextFlag.TextWordWrap,
            text,
        )
        h = 24 + 4 + min(text_rect.height(), fm.height() * 3) + self.SLIDE_PADDING * 2
        return QSize(option.rect.width(), int(max(self.SLIDE_MIN_HEIGHT, h)))

    # ──────────────────────────────────────────────────────────────────
    #  Paint dispatcher
    # ──────────────────────────────────────────────────────────────────
    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        item_rect = option.rect.adjusted(3, 1, -3, -1)

        if index.data(PlaylistRoles.IsFolderRole):
            self._paint_folder(painter, option, index, item_rect)
        else:
            self._paint_slide(painter, option, index, item_rect)

        painter.restore()

    # ══════════════════════════════════════════════════════════════════
    #  FOLDER
    # ══════════════════════════════════════════════════════════════════
    def _paint_folder(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
        rect: QRect,
    ) -> None:
        is_sel = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hov = bool(option.state & QStyle.StateFlag.State_MouseOver)

        # Determine expanded state
        is_expanded = False
        tree = option.widget
        if isinstance(tree, QTreeView):
            is_expanded = tree.isExpanded(index)

        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), self.FOLDER_RADIUS, self.FOLDER_RADIUS)

        # ── Background ─────────────────────────────────────────────
        if is_sel:
            rect_f = QRectF(rect)
            grad = QLinearGradient(rect_f.topLeft(), rect_f.bottomRight())
            grad.setColorAt(0, _P.FOLDER_SEL_BG)
            grad.setColorAt(1, _P.FOLDER_SEL_BG_2)
            painter.fillPath(path, QBrush(grad))

            # Subtler border
            painter.setPen(QPen(_P.CARD_SEL_BORDER, 1))
            painter.drawPath(path)
        elif is_hov:
            painter.fillPath(path, QBrush(_P.FOLDER_HOVER_BG))
        else:
            painter.fillPath(path, QBrush(_P.FOLDER_BG))

        # ── Left accent pip ────────────────────────────────────────
        pip_h = 20
        pip_y = rect.y() + (rect.height() - pip_h) / 2
        pip = QRectF(rect.x() + 1, pip_y, 3, pip_h)
        pip_path = QPainterPath()
        pip_path.addRoundedRect(pip, 1.5, 1.5)
        pip_color = (
            _P.FOLDER_ACCENT if (is_sel or is_expanded) else QColor(161, 161, 170, 80)
        )
        painter.fillPath(pip_path, QBrush(pip_color))

        cx = rect.x() + 14

        # ── Chevron indicator ──────────────────────────────────────
        chevron = "▾" if is_expanded else "▸"
        painter.setFont(self._chevron_font)
        chev_color = _P.FOLDER_ACCENT if (is_sel or is_expanded) else _P.FOLDER_CHEVRON
        painter.setPen(chev_color)
        chev_rect = QRect(cx, rect.y(), 14, rect.height())
        painter.drawText(
            chev_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            chevron,
        )
        cx += 18

        # ── Folder icon (📁 emoji-free: small square) ─────────────
        icon_sz = 16
        icon_y = rect.y() + (rect.height() - icon_sz) / 2
        icon_color = (
            _P.FOLDER_ACCENT if (is_sel or is_expanded) else QColor(161, 161, 170, 140)
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(
            QBrush(QColor(icon_color.red(), icon_color.green(), icon_color.blue(), 30))
        )
        icon_path = QPainterPath()
        icon_path.addRoundedRect(QRectF(cx, icon_y, icon_sz, icon_sz), 3, 3)
        painter.drawPath(icon_path)
        # Inner folder tab
        painter.setBrush(QBrush(icon_color))
        tab = QPainterPath()
        tab.addRoundedRect(QRectF(cx + 2, icon_y + 2, 6, 3), 1, 1)
        painter.drawPath(tab)
        # Inner folder body
        body = QPainterPath()
        body.addRoundedRect(
            QRectF(cx + 2, icon_y + 6, icon_sz - 4, icon_sz - 8), 1.5, 1.5
        )
        painter.drawPath(body)
        cx += icon_sz + 8

        # ── Folder name ────────────────────────────────────────────
        folder_name = index.data(Qt.ItemDataRole.DisplayRole) or "Dossier"
        painter.setFont(self._folder_font)
        text_color = _P.FOLDER_TEXT_SEL if (is_sel or is_expanded) else _P.FOLDER_TEXT
        painter.setPen(text_color)
        name_rect = QRect(
            cx, rect.y(), rect.width() - (cx - rect.x()) - 50, rect.height()
        )
        fm = QFontMetrics(self._folder_font)
        elided = fm.elidedText(
            folder_name, Qt.TextElideMode.ElideRight, name_rect.width()
        )
        painter.drawText(
            name_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided,
        )

        # ── Child count badge ──────────────────────────────────────
        child_count = index.model().rowCount(index) if index.model() else 0
        if child_count > 0:
            count_text = str(child_count)
            badge_font = QFont(Typography.FAMILY)
            badge_font.setPixelSize(10)
            badge_font.setWeight(QFont.Weight.Bold)
            badge_fm = QFontMetrics(badge_font)
            badge_w = max(20, badge_fm.horizontalAdvance(count_text) + 10)
            badge_h = 18
            badge_x = rect.right() - badge_w - 10
            badge_y = rect.y() + (rect.height() - badge_h) / 2

            badge_path = QPainterPath()
            badge_path.addRoundedRect(
                QRectF(badge_x, badge_y, badge_w, badge_h), badge_h / 2, badge_h / 2
            )
            painter.fillPath(badge_path, QBrush(_P.NUMBER_BG))
            painter.setFont(badge_font)
            painter.setPen(_P.NUMBER_TEXT)
            painter.drawText(
                QRect(int(badge_x), int(badge_y), int(badge_w), int(badge_h)),
                Qt.AlignmentFlag.AlignCenter,
                count_text,
            )

    # ══════════════════════════════════════════════════════════════════
    #  SLIDE CARD
    # ══════════════════════════════════════════════════════════════════
    def _paint_slide(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
        rect: QRect,
    ) -> None:
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), self.BORDER_RADIUS, self.BORDER_RADIUS)

        is_sel = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hov = bool(option.state & QStyle.StateFlag.State_MouseOver)

        # ── Background ─────────────────────────────────────────────
        if is_sel:
            rect_f = QRectF(rect)
            grad = QLinearGradient(rect_f.topLeft(), rect_f.bottomRight())
            grad.setColorAt(0, _P.CARD_SEL_BG)
            grad.setColorAt(1, _P.CARD_SEL_BG_2)
            painter.fillPath(path, QBrush(grad))
            painter.setPen(QPen(_P.CARD_SEL_BORDER, 1))
            painter.drawPath(path)
            # Left accent bar
            accent = QRectF(rect.x(), rect.y() + 6, 3, rect.height() - 12)
            ap = QPainterPath()
            ap.addRoundedRect(accent, 1.5, 1.5)
            painter.fillPath(ap, QBrush(_P.ACCENT))
        elif is_hov:
            painter.fillPath(path, QBrush(_P.CARD_HOVER))
            painter.setPen(QPen(_P.SEPARATOR, 1))
            painter.drawPath(path)
        else:
            painter.fillPath(path, QBrush(_P.CARD_BG))

        # Bottom separator
        if not is_sel:
            painter.setPen(QPen(_P.SEPARATOR, 1))
            painter.drawLine(
                rect.x() + 12, rect.bottom(), rect.right() - 12, rect.bottom()
            )

        # ── Content area ───────────────────────────────────────────
        left_pad = self.SLIDE_PADDING + 6
        cx = rect.x() + left_pad
        cy = rect.y() + self.SLIDE_PADDING
        cw = rect.width() - left_pad - self.SLIDE_PADDING
        ch = rect.height() - self.SLIDE_PADDING * 2

        # ── Source tag ─────────────────────────────────────────────
        source = index.data(PlaylistRoles.SourceRole) or "custom"
        tag_color, tag_label = _SOURCE_COLORS.get(source, _SOURCE_COLORS["custom"])

        tag_fm = QFontMetrics(self._tag_font)
        tag_w = tag_fm.horizontalAdvance(tag_label) + 10
        tag_h = tag_fm.height() + 2
        tag_rect = QRectF(cx, cy, tag_w, tag_h)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(
            QBrush(QColor(tag_color.red(), tag_color.green(), tag_color.blue(), 20))
        )
        painter.drawRoundedRect(tag_rect, 4, 4)

        painter.setFont(self._tag_font)
        painter.setPen(tag_color.lighter(105))
        painter.drawText(
            tag_rect,
            Qt.AlignmentFlag.AlignCenter,
            tag_label,
        )

        # ── Reference (after tag, same line) ───────────────────────
        reference = index.data(PlaylistRoles.ReferenceRole) or ""
        ref_x = cx + tag_w + 10
        ref_w = cw - tag_w - 10
        if reference and ref_w > 30:
            painter.setFont(self._ref_font)
            painter.setPen(_P.REF_SEL if is_sel else _P.REF_NORMAL)
            ref_fm = QFontMetrics(self._ref_font)
            elided_ref = ref_fm.elidedText(
                reference, Qt.TextElideMode.ElideRight, int(ref_w)
            )
            painter.drawText(
                QRect(int(ref_x), int(cy), int(ref_w), int(tag_h)),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                elided_ref,
            )

        # ── Body text ──────────────────────────────────────────────
        text = index.data(PlaylistRoles.TextRole) or ""
        if text:
            text_y = cy + tag_h + 3
            text_h = ch - tag_h - 3
            text_h = max(text_h, 10)

            painter.setFont(self._text_font)
            painter.setPen(_P.TEXT_SEL if is_sel else _P.TEXT_NORMAL)

            fm = QFontMetrics(self._text_font)
            max_lines = max(1, int(text_h) // fm.height())
            max_lines = min(max_lines, 3)

            remaining = text.replace("\n", " ")
            y_cursor = int(text_y)
            for i in range(max_lines):
                if not remaining:
                    break
                if i == max_lines - 1:
                    line = fm.elidedText(
                        remaining, Qt.TextElideMode.ElideRight, int(cw)
                    )
                    painter.drawText(int(cx), y_cursor + fm.ascent(), line)
                    break
                line_text = ""
                for ch_idx, ch_char in enumerate(remaining):
                    test = remaining[: ch_idx + 1]
                    if fm.horizontalAdvance(test) > cw:
                        sp = test.rfind(" ")
                        if sp > 0:
                            line_text = remaining[:sp]
                            remaining = remaining[sp:].lstrip()
                        else:
                            line_text = test
                            remaining = remaining[ch_idx + 1 :]
                        break
                else:
                    line_text = remaining
                    remaining = ""
                painter.drawText(int(cx), y_cursor + fm.ascent(), line_text)
                y_cursor += fm.height()
