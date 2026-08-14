"""Centralized theme system for Project-On.

A refined, premium design language for a church presentation
application. Deep obsidian tones with warm gold accents — reverent, cinematic and modern.
"""

from __future__ import annotations

from PyQt6.QtGui import QColor


_current_theme = "dark"


def set_theme(theme: str) -> None:
    """Set the active application theme."""
    global _current_theme
    normalized = str(theme or "dark").lower()
    _current_theme = normalized if normalized in ("dark", "light") else "dark"
    _apply_palette(_current_theme)


def get_theme() -> str:
    """Get the current theme."""
    return _current_theme


class Colors:
    """Application color palette — Premium Dark Mode with Cinematic Accents.

    Default values are the Dark theme. _apply_palette() overwrites them
    at startup so code always reads from Colors.* without branching.
    """

    # ── Base backgrounds ──────────────────────────────────────────────
    BG_PRIMARY = "#04070d"
    BG_SECONDARY = "#090f1a"
    BG_TERTIARY = "#0f1928"
    BG_ELEVATED = "#152234"
    BG_SURFACE = "#1d2d42"
    BG_CARD = "#0d1622"
    BG_INPUT = "#0c1521"
    BG_INPUT_HOVER = "#121e2f"
    BG_INPUT_FOCUS = "#142234"
    BG_TOOLTIP = "#182a3e"

    # ── Glass morphism ────────────────────────────────────────────────
    GLASS_LIGHT = "rgba(203, 213, 225, 0.035)"
    GLASS_MEDIUM = "rgba(203, 213, 225, 0.07)"
    GLASS_HEAVY = "rgba(203, 213, 225, 0.12)"
    GLASS_ACCENT = "rgba(236, 182, 97, 0.08)"
    GLASS_ACCENT_STRONG = "rgba(236, 182, 97, 0.15)"

    # ── Surfaces ──────────────────────────────────────────────────────
    SURFACE = "#0f1928"
    SURFACE_HOVER = "#15283e"
    SURFACE_ACTIVE = "#1c3250"
    SURFACE_RAISED = "#223a58"

    # ── Text ──────────────────────────────────────────────────────────
    TEXT_PRIMARY = "#f2f5f9"
    TEXT_SECONDARY = "#bcc8d8"
    TEXT_MUTED = "#8296ac"
    TEXT_DISABLED = "#4d6075"
    TEXT_PLACEHOLDER = "#5d7288"

    # ── Accents ───────────────────────────────────────────────────────
    ACCENT_PRIMARY = "#ecb661"
    ACCENT_LIGHT = "#f8dd9d"
    ACCENT_DARK = "#c6922f"
    ACCENT_GLOW = "rgba(236, 182, 97, 0.10)"
    ACCENT_GLOW_STRONG = "rgba(236, 182, 97, 0.22)"
    ACCENT_GRADIENT_START = "#d9a541"
    ACCENT_GRADIENT_END = "#f3cd78"

    ACCENT_SECONDARY = "#6db4ff"
    ACCENT_SECONDARY_GLOW = "rgba(109, 180, 255, 0.12)"

    ACCENT_SUCCESS = "#4ade80"
    ACCENT_SUCCESS_GLOW = "rgba(74, 222, 128, 0.12)"
    ACCENT_WARNING = "#f6ad55"
    ACCENT_WARNING_GLOW = "rgba(246, 173, 85, 0.12)"
    ACCENT_DANGER = "#fb7185"
    ACCENT_DANGER_GLOW = "rgba(251, 113, 133, 0.12)"

    # ── Source colors ─────────────────────────────────────────────────
    SRC_BIBLE = "#4ade80"
    SRC_SERMON = "#f6ad55"
    SRC_HYMN = "#c4a7ff"
    SRC_CUSTOM = "#5cb8ff"
    SRC_IMAGE = "#7a8fa8"

    # ── Borders ───────────────────────────────────────────────────────
    BORDER_SUBTLE = "rgba(148, 163, 184, 0.09)"
    BORDER_DEFAULT = "rgba(148, 163, 184, 0.15)"
    BORDER_HOVER = "rgba(203, 213, 225, 0.26)"
    BORDER_FOCUS = "#6db4ff"
    BORDER_ACCENT = "rgba(236, 182, 97, 0.32)"

    # ── Gradients ─────────────────────────────────────────────────────
    MAIN_GRADIENT_START = "#03060b"
    MAIN_GRADIENT_MID = "#060e1a"
    MAIN_GRADIENT_END = "#0a1424"
    PANEL_GRADIENT_END = "#071020"
    SIDEBAR_GRADIENT_START = "#0c1828"
    SIDEBAR_GRADIENT_END = "#090f1a"
    CARD_GRADIENT_START = "#0d1622"
    CARD_GRADIENT_END = "#0b121d"

    # ── Shadows ───────────────────────────────────────────────────────
    SHADOW_COLOR = "rgba(0, 0, 0, 0.50)"
    SHADOW_COLOR_LIGHT = "rgba(0, 0, 0, 0.25)"

    # ── Misc ──────────────────────────────────────────────────────────
    SCROLLBAR_HANDLE = "rgba(148, 163, 184, 0.28)"
    PROJECT_BUTTON_TEXT = "#04070d"
    APP_STYLESHEET_NAME = "dark"


_DARK_PALETTE = {
    "BG_PRIMARY": "#04070d",
    "BG_SECONDARY": "#090f1a",
    "BG_TERTIARY": "#0f1928",
    "BG_ELEVATED": "#152234",
    "BG_SURFACE": "#1d2d42",
    "BG_CARD": "#0d1622",
    "BG_INPUT": "#0c1521",
    "BG_INPUT_HOVER": "#121e2f",
    "BG_INPUT_FOCUS": "#142234",
    "BG_TOOLTIP": "#182a3e",
    "GLASS_LIGHT": "rgba(203, 213, 225, 0.035)",
    "GLASS_MEDIUM": "rgba(203, 213, 225, 0.07)",
    "GLASS_HEAVY": "rgba(203, 213, 225, 0.12)",
    "GLASS_ACCENT": "rgba(236, 182, 97, 0.08)",
    "GLASS_ACCENT_STRONG": "rgba(236, 182, 97, 0.15)",
    "SURFACE": "#0f1928",
    "SURFACE_HOVER": "#15283e",
    "SURFACE_ACTIVE": "#1c3250",
    "SURFACE_RAISED": "#223a58",
    "TEXT_PRIMARY": "#f2f5f9",
    "TEXT_SECONDARY": "#bcc8d8",
    "TEXT_MUTED": "#8296ac",
    "TEXT_DISABLED": "#4d6075",
    "TEXT_PLACEHOLDER": "#5d7288",
    "ACCENT_PRIMARY": "#ecb661",
    "ACCENT_LIGHT": "#f8dd9d",
    "ACCENT_DARK": "#c6922f",
    "ACCENT_GLOW": "rgba(236, 182, 97, 0.10)",
    "ACCENT_GLOW_STRONG": "rgba(236, 182, 97, 0.22)",
    "ACCENT_GRADIENT_START": "#d9a541",
    "ACCENT_GRADIENT_END": "#f3cd78",
    "ACCENT_SECONDARY": "#6db4ff",
    "ACCENT_SECONDARY_GLOW": "rgba(109, 180, 255, 0.12)",
    "ACCENT_SUCCESS": "#4ade80",
    "ACCENT_SUCCESS_GLOW": "rgba(74, 222, 128, 0.12)",
    "ACCENT_WARNING": "#f6ad55",
    "ACCENT_WARNING_GLOW": "rgba(246, 173, 85, 0.12)",
    "ACCENT_DANGER": "#fb7185",
    "ACCENT_DANGER_GLOW": "rgba(251, 113, 133, 0.12)",
    "SRC_BIBLE": "#4ade80",
    "SRC_SERMON": "#f6ad55",
    "SRC_HYMN": "#c4a7ff",
    "SRC_CUSTOM": "#6db4ff",
    "SRC_IMAGE": "#8296ac",
    "BORDER_SUBTLE": "rgba(148, 163, 184, 0.09)",
    "BORDER_DEFAULT": "rgba(148, 163, 184, 0.15)",
    "BORDER_HOVER": "rgba(203, 213, 225, 0.26)",
    "BORDER_FOCUS": "#6db4ff",
    "BORDER_ACCENT": "rgba(236, 182, 97, 0.32)",
    "SHADOW_SM": "0 2px 8px rgba(0, 0, 0, 0.35)",
    "SHADOW_MD": "0 8px 32px rgba(0, 0, 0, 0.50)",
    "SHADOW_LG": "0 24px 64px rgba(0, 0, 0, 0.65)",
    "SHADOW_ACCENT": "0 4px 20px rgba(236, 182, 97, 0.15)",
    "MAIN_GRADIENT_START": "#03060b",
    "MAIN_GRADIENT_MID": "#060e1a",
    "MAIN_GRADIENT_END": "#0a1424",
    "PANEL_GRADIENT_END": "#071020",
    "SIDEBAR_GRADIENT_START": "#0c1828",
    "SIDEBAR_GRADIENT_END": "#090f1a",
    "CARD_GRADIENT_START": "#0d1622",
    "CARD_GRADIENT_END": "#0b121d",
    "SCROLLBAR_HANDLE": "rgba(148, 163, 184, 0.28)",
    "PROJECT_BUTTON_TEXT": "#04070d",
    "APP_STYLESHEET_NAME": "dark",
}

_LIGHT_PALETTE = {
    # ── Sanctuary Light — warm parchment & morning gold ────────────────
    # A complete redesign: warm ivory backgrounds instead of cold slate,
    # deep espresso ink, and a rich bronze-gold accent that keeps the
    # app's identity readable on bright surfaces.
    "BG_PRIMARY": "#f6f1e7",
    "BG_SECONDARY": "#fdfaf3",
    "BG_TERTIARY": "#eee7d8",
    "BG_ELEVATED": "#fffdf8",
    "BG_SURFACE": "#e6dcc8",
    "BG_CARD": "#fbf7ec",
    "BG_INPUT": "#f2ecdd",
    "BG_INPUT_HOVER": "#eae2cf",
    "BG_INPUT_FOCUS": "#fffdf6",
    "BG_TOOLTIP": "#2e2620",
    "GLASS_LIGHT": "rgba(93, 76, 54, 0.03)",
    "GLASS_MEDIUM": "rgba(93, 76, 54, 0.06)",
    "GLASS_HEAVY": "rgba(93, 76, 54, 0.11)",
    "GLASS_ACCENT": "rgba(166, 113, 18, 0.09)",
    "GLASS_ACCENT_STRONG": "rgba(166, 113, 18, 0.17)",
    "SURFACE": "#eee7d8",
    "SURFACE_HOVER": "#e6dcc6",
    "SURFACE_ACTIVE": "#dccfb2",
    "SURFACE_RAISED": "#d3c4a2",
    "TEXT_PRIMARY": "#2a231a",
    "TEXT_SECONDARY": "#544a3a",
    "TEXT_MUTED": "#7f7462",
    "TEXT_DISABLED": "#b0a58f",
    "TEXT_PLACEHOLDER": "#a3967f",
    "ACCENT_PRIMARY": "#a67112",
    "ACCENT_LIGHT": "#c28d20",
    "ACCENT_DARK": "#7c540a",
    "ACCENT_GLOW": "rgba(166, 113, 18, 0.10)",
    "ACCENT_GLOW_STRONG": "rgba(166, 113, 18, 0.20)",
    "ACCENT_GRADIENT_START": "#8f5f0c",
    "ACCENT_GRADIENT_END": "#c28d20",
    "ACCENT_SECONDARY": "#2e6cad",
    "ACCENT_SECONDARY_GLOW": "rgba(46, 108, 173, 0.10)",
    "ACCENT_SUCCESS": "#1c7f45",
    "ACCENT_SUCCESS_GLOW": "rgba(28, 127, 69, 0.10)",
    "ACCENT_WARNING": "#b2690e",
    "ACCENT_WARNING_GLOW": "rgba(178, 105, 14, 0.10)",
    "ACCENT_DANGER": "#c23a2e",
    "ACCENT_DANGER_GLOW": "rgba(194, 58, 46, 0.10)",
    "SRC_BIBLE": "#1c7f45",
    "SRC_SERMON": "#b2690e",
    "SRC_HYMN": "#7a4fc0",
    "SRC_CUSTOM": "#2e6cad",
    "SRC_IMAGE": "#7f7462",
    "BORDER_SUBTLE": "rgba(93, 76, 54, 0.08)",
    "BORDER_DEFAULT": "rgba(93, 76, 54, 0.13)",
    "BORDER_HOVER": "rgba(93, 76, 54, 0.24)",
    "BORDER_FOCUS": "#2e6cad",
    "BORDER_ACCENT": "rgba(166, 113, 18, 0.32)",
    "SHADOW_SM": "0 2px 8px rgba(74, 58, 34, 0.10)",
    "SHADOW_MD": "0 8px 32px rgba(74, 58, 34, 0.14)",
    "SHADOW_LG": "0 24px 64px rgba(74, 58, 34, 0.18)",
    "SHADOW_ACCENT": "0 4px 20px rgba(166, 113, 18, 0.16)",
    "MAIN_GRADIENT_START": "#f0e9d8",
    "MAIN_GRADIENT_MID": "#f6f1e7",
    "MAIN_GRADIENT_END": "#fbf7ec",
    "PANEL_GRADIENT_END": "#fdfaf3",
    "SIDEBAR_GRADIENT_START": "#fbf7ec",
    "SIDEBAR_GRADIENT_END": "#f3eddd",
    "CARD_GRADIENT_START": "#fffdf8",
    "CARD_GRADIENT_END": "#f7f2e4",
    "SCROLLBAR_HANDLE": "rgba(93, 76, 54, 0.26)",
    "PROJECT_BUTTON_TEXT": "#fffdf6",
    "APP_STYLESHEET_NAME": "light",
}


def _apply_palette(theme: str) -> None:
    palette = _LIGHT_PALETTE if theme == "light" else _DARK_PALETTE
    for key, value in palette.items():
        setattr(Colors, key, value)


class Spacing:
    """Consistent spacing scale (px)."""

    NONE = 0
    XXS = 2
    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 20
    XXL = 28
    XXXL = 40
    GUTTER = 16


class Radius:
    """Border radius scale (px)."""

    NONE = 0
    XS = 4
    SM = 8
    MD = 12
    LG = 14
    XL = 18
    XXL = 24
    FULL = 9999


class Typography:
    """Application typography scale and semantic text roles.

    The legacy ``SIZE_*`` values remain available for existing components, while
    the semantic roles below make the hierarchy explicit: readable labels and
    body copy, compact filters, and deliberately quiet numerical metadata.
    """

    PRIMARY_FAMILY = "'Poppins', 'Segoe UI', sans-serif"
    FAMILY = "Poppins"

    SIZE_2XS = 10
    SIZE_2XS_PT = 7
    SIZE_XS = 11
    SIZE_XS_PT = 8
    SIZE_SM = 12
    SIZE_SM_PT = 9
    SIZE_MD = 14
    SIZE_MD_PT = 11
    SIZE_LG = 15
    SIZE_LG_PT = 12
    SIZE_XL = 18
    SIZE_XL_PT = 14
    SIZE_2XL = 20
    SIZE_2XL_PT = 15
    SIZE_3XL = 24
    SIZE_3XL_PT = 18
    SIZE_4XL = 32
    SIZE_4XL_PT = 24

    # Semantic desktop roles. Keep compact information small without making
    # controls themselves smaller or harder to target.
    SIZE_NUMBER = 10
    SIZE_META = 11
    SIZE_FILTER = 12
    SIZE_CONTROL = 13
    SIZE_BODY = 14
    SIZE_LABEL = 14
    SIZE_SECTION = 15
    SIZE_TITLE = 18
    SIZE_DIALOG_TITLE = 20

    WEIGHT_NORMAL = 400
    WEIGHT_MEDIUM = 500
    WEIGHT_SEMIBOLD = 600
    WEIGHT_BOLD = 700
    WEIGHT_EXTRABOLD = 800

    LINE_HEIGHT_TIGHT = 1.2
    LINE_HEIGHT_NORMAL = 1.5
    LINE_HEIGHT_RELAXED = 1.75


class Shadows:
    """Pre-defined shadow values."""

    @staticmethod
    def sm() -> str:
        return f"0 2px 8px {Colors.SHADOW_COLOR}"

    @staticmethod
    def md() -> str:
        return f"0 8px 32px {Colors.SHADOW_COLOR}"

    @staticmethod
    def lg() -> str:
        return f"0 24px 64px {Colors.SHADOW_COLOR}"

    @staticmethod
    def accent() -> str:
        return f"0 4px 20px rgba(236, 182, 97, 0.15)"

    @staticmethod
    def inset() -> str:
        return f"inset 0 1px 2px {Colors.SHADOW_COLOR_LIGHT}"


# ═══════════════════════════════════════════════════════════════════════
#  Shared scrollbar snippet
# ═══════════════════════════════════════════════════════════════════════


def _scrollbar_v() -> str:
    return f"""
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 6px 2px;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical {{
            background: {Colors.SCROLLBAR_HANDLE};
            border-radius: 5px;
            min-height: 40px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {Colors.ACCENT_PRIMARY};
        }}
        QScrollBar::handle:vertical:pressed {{
            background: {Colors.ACCENT_DARK};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
    """


def _scrollbar_h() -> str:
    return f"""
        QScrollBar:horizontal {{
            background: transparent;
            height: 10px;
            margin: 2px 6px;
            border-radius: 5px;
        }}
        QScrollBar::handle:horizontal {{
            background: {Colors.SCROLLBAR_HANDLE};
            border-radius: 5px;
            min-width: 56px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {Colors.ACCENT_PRIMARY};
        }}

        QScrollBar::handle:horizontal:pressed {{
            background: {Colors.ACCENT_DARK};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: transparent;
        }}
    """


def _tooltip_bg() -> str:
    return "#ffffff" if Colors.APP_STYLESHEET_NAME == "light" else Colors.BG_TOOLTIP


def _tooltip_text() -> str:
    return "#111827" if Colors.APP_STYLESHEET_NAME == "light" else Colors.TEXT_PRIMARY


def color_with_alpha(color: str, alpha: int) -> QColor:
    qcolor = QColor(color)
    qcolor.setAlpha(alpha)
    return qcolor


def item_hover_color() -> QColor:
    if get_theme() == "light":
        return color_with_alpha("#172033", 12)
    return color_with_alpha("#cbd5e1", 14)


def item_selection_color(strong: bool = False) -> QColor:
    alpha = 38 if get_theme() == "light" else 32
    if strong:
        alpha += 12
    return color_with_alpha(Colors.ACCENT_PRIMARY, alpha)


def item_separator_color() -> QColor:
    if get_theme() == "light":
        return color_with_alpha("#172033", 18)
    return color_with_alpha("#94a3b8", 22)


def selected_text_color() -> QColor:
    return QColor(Colors.TEXT_PRIMARY)


def selected_badge_text_color() -> QColor:
    return QColor("#ffffff" if get_theme() == "light" else Colors.BG_PRIMARY)


# ═══════════════════════════════════════════════════════════════════════
#  Component style helpers
# ═══════════════════════════════════════════════════════════════════════


def get_panel_style() -> str:
    return f"""
        QFrame#Panel {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {Colors.BG_SECONDARY},
                stop:1 {Colors.PANEL_GRADIENT_END}
            );
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.LG}px;
        }}
    """


def get_card_style() -> str:
    return f"""
        QFrame#Card {{
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.CARD_GRADIENT_START},
                stop:1 {Colors.CARD_GRADIENT_END}
            );
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.LG}px;
        }}
    """


def get_list_style(
    accent: str = Colors.ACCENT_PRIMARY, borderless: bool = False
) -> str:
    if borderless:
        frame = f"background: transparent;\n            border: none;"
    else:
        frame = (
            f"background: {Colors.BG_SECONDARY};\n"
            f"            border: 1px solid {Colors.BORDER_SUBTLE};\n"
            f"            border-radius: {Radius.MD}px;"
        )
    return f"""
        QListWidget {{
            {frame}
            outline: none;
            padding: 6px;
        }}
        QListWidget::item {{
            padding: 8px 12px;
            border-radius: {Radius.SM}px;
            margin: 1px 2px;
            color: {Colors.TEXT_SECONDARY};
            font-size: {Typography.SIZE_MD}px;
            border: 1px solid transparent;
        }}
        QListWidget::item:selected {{
            background: {Colors.ACCENT_GLOW};
            color: {Colors.ACCENT_LIGHT};
            border: 1px solid {Colors.ACCENT_GLOW_STRONG};
            font-weight: {Typography.WEIGHT_SEMIBOLD};
        }}
        QListWidget::item:hover:!selected {{
            background: {Colors.GLASS_MEDIUM};
            color: {Colors.TEXT_PRIMARY};
        }}
        {_scrollbar_v()}
    """


def get_tree_style() -> str:
    return f"""
        QTreeView {{
            background: {Colors.BG_SECONDARY};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.MD}px;
            outline: none;
            padding: 6px;
        }}
        QTreeView::item {{
            border-radius: {Radius.SM}px;
            margin: 2px 0;
            padding: 6px 6px;
            font-size: {Typography.SIZE_BODY}px;
            color: {Colors.TEXT_PRIMARY};
            background: transparent;
        }}
        QTreeView::item:selected {{
            background: transparent;
        }}
        QTreeView::item:hover:!selected {{
            background: transparent;
        }}
        QTreeView::branch {{
            background: transparent;
            border: none;
            image: none;
        }}
        QTreeView::branch:has-children:open,
        QTreeView::branch:has-children:closed {{
            image: none;
        }}
        {_scrollbar_v()}
    """


def get_input_style() -> str:
    return f"""
        QLineEdit {{
            background: {Colors.BG_INPUT};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.MD}px;
            padding: 8px 14px;
            font-size: {Typography.SIZE_FILTER}px;
            color: {Colors.TEXT_PRIMARY};
            selection-background-color: {Colors.ACCENT_GLOW_STRONG};
            selection-color: {Colors.ACCENT_PRIMARY};
        }}
        QLineEdit:hover {{
            background: {Colors.BG_INPUT_HOVER};
            border-color: {Colors.BORDER_HOVER};
        }}
        QLineEdit:focus {{
            background: {Colors.BG_INPUT_FOCUS};
            border: 1px solid {Colors.BORDER_FOCUS};
        }}
        QLineEdit::placeholder {{
            color: {Colors.TEXT_PLACEHOLDER};
        }}
    """


def get_combo_style() -> str:
    return f"""
        QComboBox {{
            background: {Colors.BG_INPUT};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.MD}px;
            padding: 6px 14px;
            font-size: {Typography.SIZE_FILTER}px;
            color: {Colors.TEXT_PRIMARY};
            min-height: 26px;
        }}
        QComboBox:hover {{
            background: {Colors.BG_INPUT_HOVER};
            border-color: {Colors.BORDER_HOVER};
        }}
        QComboBox:focus {{
            background: {Colors.BG_INPUT_FOCUS};
            border: 1px solid {Colors.BORDER_FOCUS};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}
        QComboBox::down-arrow {{
            image: none;
            width: 0;
        }}
        QComboBox QAbstractItemView {{
            background-color: {Colors.BG_ELEVATED};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.SM}px;
            selection-background-color: {Colors.ACCENT_GLOW_STRONG};
            selection-color: {Colors.ACCENT_PRIMARY};
            color: {Colors.TEXT_PRIMARY};
            outline: none;
            padding: 4px;
        }}
    """


def get_button_style(accent: str = Colors.ACCENT_PRIMARY) -> str:
    """Flat, professional button style."""
    return f"""
        QPushButton {{
            background: {Colors.BG_SURFACE};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.SM}px;
            padding: 8px {Spacing.LG}px;
            font-size: {Typography.SIZE_CONTROL}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            color: {Colors.TEXT_PRIMARY};
        }}
        QPushButton:hover {{
            background: {Colors.SURFACE_ACTIVE};
            border-color: {Colors.BORDER_HOVER};
            color: {Colors.ACCENT_LIGHT};
        }}
        QPushButton:pressed {{
            background: {Colors.BG_ELEVATED};
        }}
        QPushButton:disabled {{
            background: transparent;
            border: 1px solid {Colors.BORDER_SUBTLE};
            color: {Colors.TEXT_DISABLED};
        }}
    """


def get_accent_button_style() -> str:
    """Primary accent button with gradient."""
    return f"""
        QPushButton {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {Colors.ACCENT_GRADIENT_START},
                stop:1 {Colors.ACCENT_GRADIENT_END}
            );
            border: 1px solid {Colors.ACCENT_DARK};
            border-radius: {Radius.SM}px;
            padding: 8px {Spacing.LG}px;
            font-size: {Typography.SIZE_CONTROL}px;
            font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.PROJECT_BUTTON_TEXT};
        }}
        QPushButton:hover {{
            background: {Colors.ACCENT_LIGHT};
            border-color: {Colors.ACCENT_PRIMARY};
        }}
        QPushButton:pressed {{
            background: {Colors.ACCENT_DARK};
        }}
        QPushButton:disabled {{
            background: {Colors.BG_SURFACE};
            border-color: {Colors.BORDER_SUBTLE};
            color: {Colors.TEXT_DISABLED};
        }}
    """


def get_icon_button_style(size: int = 32) -> str:
    radius = Radius.SM if size < 36 else Radius.MD
    return f"""
        QPushButton {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: {radius}px;
            min-width: {size}px; max-width: {size}px;
            min-height: {size}px; max-height: {size}px;
        }}
        QPushButton:hover {{
            background: {Colors.GLASS_MEDIUM};
            border: 1px solid {Colors.BORDER_SUBTLE};
        }}
        QPushButton:pressed {{
            background: {Colors.GLASS_HEAVY};
        }}
        QPushButton:checked {{
            background: {Colors.ACCENT_GLOW};
            border: 1px solid {Colors.ACCENT_GLOW_STRONG};
        }}
    """


def get_splitter_style() -> str:
    return f"""
        QSplitter::handle {{
            background: transparent;
            margin: 0;
        }}
        QSplitter::handle:horizontal {{
            width: 2px;
        }}
        QSplitter::handle:vertical {{
            height: 2px;
        }}
        QSplitter::handle:hover {{
            background: {Colors.ACCENT_PRIMARY};
        }}
    """


def get_tab_button_style(active: bool = False) -> str:
    if active:
        return f"""
            QPushButton {{
                background: {Colors.ACCENT_GLOW};
                border: none;
                border-bottom: 2px solid {Colors.ACCENT_PRIMARY};
                border-radius: 0;
                padding: 10px 16px;
                font-size: {Typography.SIZE_CONTROL}px;
                font-weight: {Typography.WEIGHT_SEMIBOLD};
                color: {Colors.ACCENT_PRIMARY};
            }}
        """
    return f"""
        QPushButton {{
            background: transparent;
            border: none;
            border-bottom: 2px solid transparent;
            border-radius: 0;
            padding: 10px 16px;
            font-size: {Typography.SIZE_CONTROL}px;
            font-weight: {Typography.WEIGHT_MEDIUM};
            color: {Colors.TEXT_MUTED};
        }}
        QPushButton:hover {{
            color: {Colors.TEXT_SECONDARY};
            background: {Colors.GLASS_MEDIUM};
        }}
    """


def get_header_style() -> str:
    return f"""
        QFrame {{
            background: {Colors.BG_SECONDARY};
            border: none;
            border-radius: 0;
        }}
    """


def get_surface_panel_style(radius: int = Radius.MD) -> str:
    return f"""
        QFrame {{
            background: {Colors.BG_TERTIARY};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {radius}px;
        }}
    """


def get_preview_text_style() -> str:
    return f"""
        QPlainTextEdit {{
            background-color: {Colors.BG_SECONDARY};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.MD}px;
            padding: 12px;
            color: {Colors.TEXT_PRIMARY};
            selection-background-color: {Colors.ACCENT_GLOW_STRONG};
            selection-color: {Colors.TEXT_PRIMARY};
            placeholder-text-color: {Colors.TEXT_PLACEHOLDER};
        }}
        QPlainTextEdit:focus {{
            border: 1px solid {Colors.BORDER_FOCUS};
        }}
    """


def get_label_style(size: int = Typography.SIZE_LABEL, muted: bool = False) -> str:
    color = Colors.TEXT_MUTED if muted else Colors.TEXT_PRIMARY
    return f"""
        QLabel {{
            font-size: {size}px;
            color: {color};
            background: transparent;
        }}
    """


def get_title_style() -> str:
    return f"""
        QLabel {{
            font-size: {Typography.SIZE_TITLE}px;
            font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_PRIMARY};
            background: transparent;
        }}
    """


def get_subtitle_style() -> str:
    return f"""
        QLabel {{
            font-size: {Typography.SIZE_CONTROL}px;
            font-weight: {Typography.WEIGHT_MEDIUM};
            color: {Colors.TEXT_SECONDARY};
            background: transparent;
        }}
    """


def get_badge_style(color: str = Colors.ACCENT_PRIMARY) -> str:
    return f"""
        QLabel {{
            background: {Colors.ACCENT_GLOW};
            color: {color};
            border-radius: {Radius.SM}px;
            padding: 2px 8px;
            font-size: {Typography.SIZE_NUMBER}px;
            font-weight: {Typography.WEIGHT_BOLD};
        }}
    """


def get_menu_style() -> str:
    return f"""
        QMenu {{
            background: {Colors.BG_ELEVATED};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.MD}px;
            padding: 6px;
        }}
        QMenu::item {{
            padding: 8px 16px;
            border-radius: {Radius.SM}px;
            color: {Colors.TEXT_PRIMARY};
            font-size: {Typography.SIZE_CONTROL}px;
        }}
        QMenu::item:selected {{
            background: {Colors.ACCENT_GLOW_STRONG};
            color: {Colors.ACCENT_PRIMARY};
        }}
        QMenu::separator {{
            height: 1px;
            background: {Colors.BORDER_SUBTLE};
            margin: 4px 8px;
        }}
    """


def get_scroll_area_style() -> str:
    return f"""
        QScrollArea {{
            background: transparent;
            border: none;
        }}
        {_scrollbar_h()}
        {_scrollbar_v()}
    """


def get_toolbar_style() -> str:
    return f"""
        QFrame#Toolbar {{
            background: {Colors.BG_TERTIARY};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.MD}px;
            padding: 4px;
        }}
    """


def get_divider_style() -> str:
    return f"""
        QFrame#Divider {{
            background: {Colors.BORDER_SUBTLE};
            max-height: 1px;
            min-height: 1px;
        }}
    """


# ═══════════════════════════════════════════════════════════════════════
#  Main window style
# ═══════════════════════════════════════════════════════════════════════


def get_main_window_style() -> str:
    return f"""
        QMainWindow {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {Colors.MAIN_GRADIENT_START},
                stop:0.50 {Colors.MAIN_GRADIENT_MID},
                stop:1 {Colors.MAIN_GRADIENT_END}
            );
        }}
        QWidget {{
            color: {Colors.TEXT_PRIMARY};
            font-family: {Typography.FAMILY};
            font-size: {Typography.SIZE_BODY}px;
        }}
        QToolTip {{
            background-color: {_tooltip_bg()};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.SM}px;
            padding: 6px 12px;
            color: {_tooltip_text()};
            font-size: {Typography.SIZE_CONTROL}px;
            opacity: 255;
        }}
    """


def build_app_stylesheet() -> str:
    """Return the global QSS for the currently selected theme."""
    return f"""
        QWidget {{
            font-family: "Poppins", "Segoe UI", sans-serif;
            font-size: {Typography.SIZE_BODY}px;
            color: {Colors.TEXT_PRIMARY};
            outline: none;
            selection-background-color: {Colors.ACCENT_GLOW_STRONG};
            selection-color: {Colors.ACCENT_LIGHT};
        }}

        QMainWindow {{
            background: {Colors.BG_PRIMARY};
        }}

        QDialog,
        QMessageBox {{
            background: {Colors.BG_SECONDARY};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.LG}px;
        }}

        QLabel#PanelTitle {{
            font-size: {Typography.SIZE_SECTION}px;
            font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.ACCENT_PRIMARY};
            padding: 12px 16px;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }}

        QLabel#TopBarTitle {{
            font-size: {Typography.SIZE_TITLE}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            color: {Colors.TEXT_PRIMARY};
        }}

        QLabel#DescLabel {{
            color: {Colors.TEXT_MUTED};
            font-size: {Typography.SIZE_CONTROL}px;
            border: none;
            background: transparent;
        }}

        QLabel#Badge {{
            background: {Colors.ACCENT_GLOW};
            color: {Colors.ACCENT_PRIMARY};
            border-radius: {Radius.SM}px;
            padding: 2px 8px;
            font-size: {Typography.SIZE_NUMBER}px;
            font-weight: {Typography.WEIGHT_BOLD};
        }}

        QFrame#Panel,
        QFrame#BottomBar {{
            background: {Colors.BG_SECONDARY};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.LG}px;
        }}

        QFrame#Card {{
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.CARD_GRADIENT_START},
                stop:1 {Colors.CARD_GRADIENT_END}
            );
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.LG}px;
        }}

        QFrame#Toolbar {{
            background: {Colors.BG_TERTIARY};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.MD}px;
        }}

        QFrame#TopBar {{
            background: {Colors.BG_TERTIARY};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.MD}px;
            min-height: 52px;
        }}

        QLineEdit,
        QSpinBox,
        QComboBox {{
            background-color: {Colors.BG_INPUT};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.MD}px;
            padding: 8px 14px;
            color: {Colors.TEXT_PRIMARY};
            selection-background-color: {Colors.ACCENT_GLOW_STRONG};
            selection-color: {Colors.ACCENT_PRIMARY};
            font-size: {Typography.SIZE_FILTER}px;
        }}

        QTextEdit,
        QPlainTextEdit {{
            background-color: {Colors.BG_INPUT};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.MD}px;
            padding: 8px 14px;
            color: {Colors.TEXT_PRIMARY};
            selection-background-color: {Colors.ACCENT_GLOW_STRONG};
            selection-color: {Colors.ACCENT_PRIMARY};
            font-size: {Typography.SIZE_BODY}px;
        }}

        QLineEdit:hover,
        QSpinBox:hover,
        QComboBox:hover {{
            background-color: {Colors.BG_INPUT_HOVER};
            border-color: {Colors.BORDER_HOVER};
        }}

        QLineEdit:focus,
        QSpinBox:focus,
        QComboBox:focus {{
            background-color: {Colors.BG_INPUT_FOCUS};
            border: 1px solid {Colors.BORDER_FOCUS};
        }}

        QComboBox::drop-down {{
            border: none;
            width: 28px;
        }}

        QComboBox QAbstractItemView,
        QMenu {{
            background-color: {Colors.BG_ELEVATED};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.MD}px;
            color: {Colors.TEXT_PRIMARY};
            outline: none;
            padding: 6px;
            font-size: {Typography.SIZE_CONTROL}px;
        }}

        QToolTip {{
            background-color: {_tooltip_bg()};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.MD}px;
            color: {_tooltip_text()};
            padding: 8px 12px;
            font-size: {Typography.SIZE_CONTROL}px;
            opacity: 255;
        }}

        QMenu::item {{
            padding: 8px 16px;
            border-radius: {Radius.SM}px;
            color: {Colors.TEXT_PRIMARY};
            font-size: {Typography.SIZE_CONTROL}px;
        }}

        QMenu::item:selected {{
            background: {Colors.ACCENT_GLOW_STRONG};
            color: {Colors.ACCENT_PRIMARY};
        }}

        QPushButton {{
            background: {Colors.BG_SURFACE};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.SM}px;
            padding: 8px 16px;
            color: {Colors.TEXT_PRIMARY};
            font-size: {Typography.SIZE_CONTROL}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
        }}

        QPushButton:hover {{
            background: {Colors.SURFACE_ACTIVE};
            border-color: {Colors.BORDER_HOVER};
            color: {Colors.ACCENT_LIGHT};
        }}

        QPushButton:pressed {{
            background: {Colors.SURFACE_HOVER};
        }}

        QPushButton:focus {{
            border: 1px solid {Colors.BORDER_ACCENT};
        }}

        QPushButton:disabled {{
            color: {Colors.TEXT_DISABLED};
            background: transparent;
            border-color: {Colors.BORDER_SUBTLE};
        }}

        QPushButton#ProjectButton {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {Colors.ACCENT_GRADIENT_START},
                stop:1 {Colors.ACCENT_GRADIENT_END}
            );
            color: {Colors.PROJECT_BUTTON_TEXT};
            border: 1px solid {Colors.ACCENT_DARK};
            font-weight: {Typography.WEIGHT_BOLD};
        }}

        QPushButton#ProjectButton:hover {{
            background: {Colors.ACCENT_LIGHT};
            border-color: {Colors.ACCENT_PRIMARY};
        }}

        QPushButton#ProjectButton:pressed {{
            background: {Colors.ACCENT_DARK};
        }}

        QPushButton#AccentButton {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {Colors.ACCENT_GRADIENT_START},
                stop:1 {Colors.ACCENT_GRADIENT_END}
            );
            color: {Colors.PROJECT_BUTTON_TEXT};
            border: 1px solid {Colors.ACCENT_DARK};
            font-weight: {Typography.WEIGHT_BOLD};
        }}

        QPushButton#IconButton {{
            padding: 8px;
            background: transparent;
            border: 1px solid transparent;
        }}

        QPushButton#IconButton:hover {{
            background: {Colors.GLASS_MEDIUM};
            border-color: {Colors.BORDER_DEFAULT};
        }}

        QListView,
        QTreeView,
        QListWidget,
        QTableView,
        QTableWidget {{
            background-color: {Colors.BG_SECONDARY};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.MD}px;
            color: {Colors.TEXT_SECONDARY};
            font-size: {Typography.SIZE_BODY}px;
        }}

        QListView::item,
        QListWidget::item {{
            padding: 8px 12px;
            border-radius: {Radius.SM}px;
            margin: 1px 2px;
            color: {Colors.TEXT_SECONDARY};
        }}

        QListView::item:hover,
        QListWidget::item:hover {{
            background: {Colors.GLASS_MEDIUM};
            color: {Colors.TEXT_PRIMARY};
        }}

        QListView::item:selected,
        QListWidget::item:selected,
        QTableView::item:selected,
        QTableWidget::item:selected {{
            background: {Colors.ACCENT_GLOW};
            color: {Colors.ACCENT_LIGHT};
            border: 1px solid {Colors.ACCENT_GLOW_STRONG};
            font-weight: {Typography.WEIGHT_SEMIBOLD};
        }}

        QTabWidget::pane {{
            background: transparent;
            border: none;
        }}

        QTabBar::tab {{
            background: transparent;
            padding: 10px 22px;
            margin: 0 2px;
            color: {Colors.TEXT_MUTED};
            font-size: {Typography.SIZE_CONTROL}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            border-bottom: 2px solid transparent;
        }}

        QTabBar::tab:hover {{
            color: {Colors.TEXT_PRIMARY};
            background: {Colors.GLASS_LIGHT};
            border-top-left-radius: {Radius.SM}px;
            border-top-right-radius: {Radius.SM}px;
        }}

        QTabBar::tab:selected {{
            color: {Colors.ACCENT_PRIMARY};
            border-bottom: 2px solid {Colors.ACCENT_PRIMARY};
        }}

        QCheckBox,
        QRadioButton {{
            color: {Colors.TEXT_SECONDARY};
            spacing: 8px;
            font-size: {Typography.SIZE_LABEL}px;
        }}

        QCheckBox::indicator,
        QRadioButton::indicator {{
            width: 16px;
            height: 16px;
            border: 1px solid {Colors.BORDER_HOVER};
            background: {Colors.BG_INPUT};
        }}

        QCheckBox::indicator {{
            border-radius: 5px;
        }}

        QRadioButton::indicator {{
            border-radius: 8px;
        }}

        QCheckBox::indicator:hover,
        QRadioButton::indicator:hover {{
            border-color: {Colors.ACCENT_PRIMARY};
            background: {Colors.ACCENT_GLOW};
        }}

        QCheckBox::indicator:checked {{
            background: {Colors.ACCENT_PRIMARY};
            border-color: {Colors.ACCENT_PRIMARY};
        }}

        QRadioButton::indicator:checked {{
            background: {Colors.ACCENT_PRIMARY};
            border: 3px solid {Colors.BG_PRIMARY};
            outline: 1px solid {Colors.ACCENT_PRIMARY};
        }}

        QGroupBox {{
            color: {Colors.TEXT_MUTED};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.LG}px;
            margin-top: 16px;
            padding-top: 12px;
            font-size: {Typography.SIZE_META}px;
            font-weight: {Typography.WEIGHT_BOLD};
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }}

        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            top: -1px;
            padding: 0 6px;
            background: {Colors.BG_PRIMARY};
            color: {Colors.TEXT_MUTED};
        }}

        QProgressBar {{
            background: {Colors.BG_TERTIARY};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.SM}px;
            text-align: center;
            color: {Colors.TEXT_PRIMARY};
            font-size: {Typography.SIZE_NUMBER}px;
            font-weight: {Typography.WEIGHT_BOLD};
            height: 6px;
        }}

        QProgressBar::chunk {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {Colors.ACCENT_GRADIENT_START},
                stop:1 {Colors.ACCENT_GRADIENT_END}
            );
            border-radius: {Radius.SM}px;
        }}

        QSlider::groove:horizontal {{
            height: 4px;
            background: {Colors.BG_TERTIARY};
            border-radius: 2px;
        }}

        QSlider::sub-page:horizontal {{
            background: {Colors.ACCENT_PRIMARY};
            border-radius: 2px;
        }}

        QSlider::handle:horizontal {{
            width: 14px;
            height: 14px;
            margin: -5px 0;
            background: {Colors.ACCENT_PRIMARY};
            border-radius: 7px;
            border: 2px solid {Colors.BG_PRIMARY};
        }}

        QSlider::handle:horizontal:hover {{
            background: {Colors.ACCENT_LIGHT};
            border-color: {Colors.BG_SECONDARY};
        }}

        QSlider::groove:vertical {{
            width: 4px;
            background: {Colors.BG_TERTIARY};
            border-radius: 2px;
        }}

        QSlider::sub-page:vertical {{
            background: {Colors.ACCENT_PRIMARY};
            border-radius: 2px;
        }}

        QSlider::handle:vertical {{
            width: 14px;
            height: 14px;
            margin: 0 -5px;
            background: {Colors.ACCENT_PRIMARY};
            border-radius: 7px;
            border: 2px solid {Colors.BG_PRIMARY};
        }}

        QHeaderView {{
            background: transparent;
            border: none;
        }}

        QHeaderView::section {{
            background: {Colors.BG_TERTIARY};
            color: {Colors.TEXT_MUTED};
            font-size: {Typography.SIZE_META}px;
            font-weight: {Typography.WEIGHT_BOLD};
            letter-spacing: 0.5px;
            text-transform: uppercase;
            padding: 8px 12px;
            border: none;
            border-bottom: 1px solid {Colors.BORDER_SUBTLE};
        }}

        QHeaderView::section:hover {{
            background: {Colors.BG_ELEVATED};
            color: {Colors.TEXT_SECONDARY};
        }}

        QTableView, QTableWidget {{
            background: {Colors.BG_SECONDARY};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.MD}px;
            gridline-color: {Colors.BORDER_SUBTLE};
            selection-background-color: {Colors.ACCENT_GLOW};
            selection-color: {Colors.ACCENT_LIGHT};
            color: {Colors.TEXT_SECONDARY};
            font-size: {Typography.SIZE_BODY}px;
        }}

        QTableView::item, QTableWidget::item {{
            padding: 6px 12px;
            border: none;
        }}

        QTableView::item:selected, QTableWidget::item:selected {{
            background: {Colors.ACCENT_GLOW};
            color: {Colors.ACCENT_LIGHT};
        }}

        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 6px 2px;
            border-radius: 5px;
        }}

        QScrollBar::handle:vertical {{
            background: {Colors.SCROLLBAR_HANDLE};
            border-radius: 5px;
            min-height: 40px;
        }}

        QScrollBar::handle:vertical:hover {{
            background: {Colors.ACCENT_PRIMARY};
        }}

        QScrollBar::handle:vertical:pressed {{
            background: {Colors.ACCENT_DARK};
        }}

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}

        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: transparent;
        }}

        QScrollBar:horizontal {{
            background: transparent;
            height: 10px;
            margin: 2px 6px;
            border-radius: 5px;
        }}

        QScrollBar::handle:horizontal {{
            background: {Colors.SCROLLBAR_HANDLE};
            border-radius: 5px;
            min-width: 56px;
        }}

        QScrollBar::handle:horizontal:hover {{
            background: {Colors.ACCENT_PRIMARY};
        }}

        QScrollBar::handle:horizontal:pressed {{
            background: {Colors.ACCENT_DARK};
        }}

        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0;
        }}

        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: transparent;
        }}
    """
