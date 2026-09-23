"""Centralized theme system for Project-On.

Fluent design language (Windows 11): calm layered surfaces, 4/8 px corner
radii, Segoe UI Variable, and Project-On's warm gold as the accent colour.
"""

from __future__ import annotations

from PySide6.QtGui import QColor


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
    """Application color tokens — Fluent (Windows 11) surfaces, gold accent.

    Attribute values are assigned by _apply_palette() from _DARK_PALETTE or
    _LIGHT_PALETTE, so code always reads Colors.* without branching.

    Surface ladder (WinUI 3 naming in brackets):
      WINDOW_BG      window base, shows Mica when enabled [SolidBackgroundBase]
      BG_PRIMARY     opaque window base colour [SolidBackgroundBase]
      BG_SECONDARY   content layer / panels [LayerFillDefault]
      BG_CARD        cards [CardBackgroundFillDefault]
      BG_ELEVATED    flyouts, menus, popups [AcrylicInAppFillDefault]
      BG_SURFACE     rest state of controls [ControlFillDefault]
      BG_INPUT*      text inputs [TextControlFill*]
    """

    SHADOW_COLOR = "rgba(0, 0, 0, 0.26)"
    SHADOW_COLOR_LIGHT = "rgba(0, 0, 0, 0.14)"


# Opaque equivalents of the WinUI 3 alpha fills composited on the base colour,
# so tokens stay valid inside QPainter code and nested widgets.
_DARK_PALETTE = {
    "WINDOW_BG": "#202020",
    "BG_PRIMARY": "#202020",
    "BG_SECONDARY": "#272727",
    "BG_TERTIARY": "#2c2c2c",
    "BG_ELEVATED": "#2c2c2c",
    "BG_SURFACE": "#2d2d2d",
    "BG_CARD": "#2b2b2b",
    "BG_INPUT": "#2d2d2d",
    "BG_INPUT_HOVER": "#323232",
    "BG_INPUT_FOCUS": "#1f1f1f",
    "BG_TOOLTIP": "#2c2c2c",
    "GLASS_LIGHT": "rgba(255, 255, 255, 0.035)",
    "GLASS_MEDIUM": "rgba(255, 255, 255, 0.06)",
    "GLASS_HEAVY": "rgba(255, 255, 255, 0.09)",
    "GLASS_ACCENT": "rgba(240, 190, 100, 0.08)",
    "GLASS_ACCENT_STRONG": "rgba(240, 190, 100, 0.15)",
    "SURFACE": "#2b2b2b",
    "SURFACE_HOVER": "#323232",
    "SURFACE_ACTIVE": "#383838",
    "SURFACE_RAISED": "#3c3c3c",
    "TEXT_PRIMARY": "#ffffff",
    "TEXT_SECONDARY": "#c8c8c8",
    "TEXT_MUTED": "#9d9d9d",
    "TEXT_DISABLED": "#5d5d5d",
    "TEXT_PLACEHOLDER": "#8b8b8b",
    "ACCENT_PRIMARY": "#f0be64",
    "ACCENT_LIGHT": "#f7d48f",
    "ACCENT_DARK": "#d9a441",
    "ACCENT_GLOW": "rgba(240, 190, 100, 0.10)",
    "ACCENT_GLOW_STRONG": "rgba(240, 190, 100, 0.20)",
    "ACCENT_GRADIENT_START": "#f0be64",
    "ACCENT_GRADIENT_END": "#f0be64",
    "ACCENT_SECONDARY": "#60cdff",
    "ACCENT_SECONDARY_GLOW": "rgba(96, 205, 255, 0.12)",
    "ACCENT_SUCCESS": "#6ccb5f",
    "ACCENT_SUCCESS_GLOW": "rgba(108, 203, 95, 0.12)",
    "ACCENT_WARNING": "#fce100",
    "ACCENT_WARNING_GLOW": "rgba(252, 225, 0, 0.12)",
    "ACCENT_DANGER": "#ff99a4",
    "ACCENT_DANGER_GLOW": "rgba(255, 153, 164, 0.12)",
    "SRC_BIBLE": "#6ccb5f",
    "SRC_SERMON": "#f7a35c",
    "SRC_HYMN": "#c7a6ff",
    "SRC_CUSTOM": "#60cdff",
    "SRC_IMAGE": "#9d9d9d",
    "BORDER_SUBTLE": "rgba(255, 255, 255, 0.055)",
    "BORDER_DEFAULT": "rgba(255, 255, 255, 0.085)",
    "BORDER_HOVER": "rgba(255, 255, 255, 0.16)",
    "BORDER_FOCUS": "#f0be64",
    "BORDER_STRONG": "rgba(255, 255, 255, 0.45)",
    "SLIDER_THUMB": "#454545",
    "BORDER_ACCENT": "rgba(240, 190, 100, 0.40)",
    "SHADOW_SM": "0 2px 4px rgba(0, 0, 0, 0.26)",
    "SHADOW_MD": "0 8px 16px rgba(0, 0, 0, 0.26)",
    "SHADOW_LG": "0 32px 64px rgba(0, 0, 0, 0.37)",
    "SHADOW_ACCENT": "0 4px 12px rgba(240, 190, 100, 0.15)",
    "MAIN_GRADIENT_START": "#202020",
    "MAIN_GRADIENT_MID": "#202020",
    "MAIN_GRADIENT_END": "#202020",
    "PANEL_GRADIENT_END": "#272727",
    "SIDEBAR_GRADIENT_START": "#202020",
    "SIDEBAR_GRADIENT_END": "#202020",
    "CARD_GRADIENT_START": "#2b2b2b",
    "CARD_GRADIENT_END": "#2b2b2b",
    "SCROLLBAR_HANDLE": "rgba(255, 255, 255, 0.36)",
    "PROJECT_BUTTON_TEXT": "#1a1a1a",
    "APP_STYLESHEET_NAME": "dark",
}

_LIGHT_PALETTE = {
    "WINDOW_BG": "#f3f3f3",
    "BG_PRIMARY": "#f3f3f3",
    "BG_SECONDARY": "#f9f9f9",
    "BG_TERTIARY": "#f6f6f6",
    "BG_ELEVATED": "#fcfcfc",
    "BG_SURFACE": "#fbfbfb",
    "BG_CARD": "#fbfbfb",
    "BG_INPUT": "#fbfbfb",
    "BG_INPUT_HOVER": "#f6f6f6",
    "BG_INPUT_FOCUS": "#ffffff",
    "BG_TOOLTIP": "#f9f9f9",
    "GLASS_LIGHT": "rgba(0, 0, 0, 0.024)",
    "GLASS_MEDIUM": "rgba(0, 0, 0, 0.045)",
    "GLASS_HEAVY": "rgba(0, 0, 0, 0.075)",
    "GLASS_ACCENT": "rgba(138, 96, 16, 0.08)",
    "GLASS_ACCENT_STRONG": "rgba(138, 96, 16, 0.15)",
    "SURFACE": "#fbfbfb",
    "SURFACE_HOVER": "#f0f0f0",
    "SURFACE_ACTIVE": "#e8e8e8",
    "SURFACE_RAISED": "#e2e2e2",
    "TEXT_PRIMARY": "#1b1b1b",
    "TEXT_SECONDARY": "#474747",
    "TEXT_MUTED": "#666666",
    "TEXT_DISABLED": "#a0a0a0",
    "TEXT_PLACEHOLDER": "#707070",
    "ACCENT_PRIMARY": "#8a6010",
    "ACCENT_LIGHT": "#76520e",
    "ACCENT_DARK": "#6a4a0c",
    "ACCENT_GLOW": "rgba(138, 96, 16, 0.09)",
    "ACCENT_GLOW_STRONG": "rgba(138, 96, 16, 0.17)",
    "ACCENT_GRADIENT_START": "#8a6010",
    "ACCENT_GRADIENT_END": "#8a6010",
    "ACCENT_SECONDARY": "#005fb8",
    "ACCENT_SECONDARY_GLOW": "rgba(0, 95, 184, 0.10)",
    "ACCENT_SUCCESS": "#0f7b0f",
    "ACCENT_SUCCESS_GLOW": "rgba(15, 123, 15, 0.10)",
    "ACCENT_WARNING": "#9d5d00",
    "ACCENT_WARNING_GLOW": "rgba(157, 93, 0, 0.10)",
    "ACCENT_DANGER": "#c42b1c",
    "ACCENT_DANGER_GLOW": "rgba(196, 43, 28, 0.10)",
    "SRC_BIBLE": "#0f7b0f",
    "SRC_SERMON": "#9d5d00",
    "SRC_HYMN": "#6d4bac",
    "SRC_CUSTOM": "#005fb8",
    "SRC_IMAGE": "#666666",
    "BORDER_SUBTLE": "rgba(0, 0, 0, 0.058)",
    "BORDER_DEFAULT": "rgba(0, 0, 0, 0.09)",
    "BORDER_HOVER": "rgba(0, 0, 0, 0.16)",
    "BORDER_FOCUS": "#8a6010",
    "BORDER_STRONG": "rgba(0, 0, 0, 0.45)",
    "SLIDER_THUMB": "#ffffff",
    "BORDER_ACCENT": "rgba(138, 96, 16, 0.40)",
    "SHADOW_SM": "0 2px 4px rgba(0, 0, 0, 0.14)",
    "SHADOW_MD": "0 8px 16px rgba(0, 0, 0, 0.14)",
    "SHADOW_LG": "0 32px 64px rgba(0, 0, 0, 0.19)",
    "SHADOW_ACCENT": "0 4px 12px rgba(138, 96, 16, 0.12)",
    "MAIN_GRADIENT_START": "#f3f3f3",
    "MAIN_GRADIENT_MID": "#f3f3f3",
    "MAIN_GRADIENT_END": "#f3f3f3",
    "PANEL_GRADIENT_END": "#f9f9f9",
    "SIDEBAR_GRADIENT_START": "#f3f3f3",
    "SIDEBAR_GRADIENT_END": "#f3f3f3",
    "CARD_GRADIENT_START": "#fbfbfb",
    "CARD_GRADIENT_END": "#fbfbfb",
    "SCROLLBAR_HANDLE": "rgba(0, 0, 0, 0.38)",
    "PROJECT_BUTTON_TEXT": "#ffffff",
    "APP_STYLESHEET_NAME": "light",
}


_window_backdrop = False


def _apply_palette(theme: str) -> None:
    palette = _LIGHT_PALETTE if theme == "light" else _DARK_PALETTE
    for key, value in palette.items():
        setattr(Colors, key, value)
    if _window_backdrop:
        Colors.WINDOW_BG = "transparent"


def set_window_backdrop(translucent: bool) -> None:
    """Let the main window base show the system backdrop (Mica)."""
    global _window_backdrop
    _window_backdrop = bool(translucent)
    _apply_palette(_current_theme)


def window_backdrop_enabled() -> bool:
    return _window_backdrop


_apply_palette(_current_theme)


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
    """Corner radii — Fluent uses 4 px for controls and 8 px for cards/overlays."""

    NONE = 0
    XS = 2
    SM = 4
    MD = 4
    LG = 8
    XL = 8
    XXL = 12
    FULL = 9999


class Typography:
    """Application typography scale and semantic text roles.

    The legacy ``SIZE_*`` values remain available for existing components, while
    the semantic roles below make the hierarchy explicit: readable labels and
    body copy, compact filters, and deliberately quiet numerical metadata.
    """

    # Segoe UI Variable ships with Windows 11; Qt falls back to Segoe UI on 10.
    PRIMARY_FAMILY = "'Segoe UI Variable Text', 'Segoe UI', sans-serif"
    FAMILY = "Segoe UI Variable Text"

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
        return Colors.SHADOW_ACCENT

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
            width: 8px;
            margin: 4px 2px;
        }}
        QScrollBar::handle:vertical {{
            background: {Colors.SCROLLBAR_HANDLE};
            border-radius: 2px;
            min-height: 40px;
        }}
        QScrollBar::handle:vertical:hover,
        QScrollBar::handle:vertical:pressed {{
            background: {Colors.TEXT_MUTED};
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
            height: 8px;
            margin: 2px 4px;
        }}
        QScrollBar::handle:horizontal {{
            background: {Colors.SCROLLBAR_HANDLE};
            border-radius: 2px;
            min-width: 56px;
        }}
        QScrollBar::handle:horizontal:hover,
        QScrollBar::handle:horizontal:pressed {{
            background: {Colors.TEXT_MUTED};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: transparent;
        }}
    """


def _tooltip_bg() -> str:
    return Colors.BG_TOOLTIP


def _tooltip_text() -> str:
    return Colors.TEXT_PRIMARY


def color_with_alpha(color: str, alpha: int) -> QColor:
    qcolor = QColor(color)
    qcolor.setAlpha(alpha)
    return qcolor


def _argb(color: QColor) -> str:
    return color.name(QColor.NameFormat.HexArgb)


def item_hover_color() -> QColor:
    # Fluent SubtleFillColorSecondary
    if get_theme() == "light":
        return color_with_alpha("#000000", 10)
    return color_with_alpha("#ffffff", 15)


def item_selection_color(strong: bool = False) -> QColor:
    # Fluent list selection is a neutral fill; the accent lives in the
    # selection pill on the left edge, not in the background.
    if get_theme() == "light":
        return color_with_alpha("#000000", 18 if strong else 10)
    return color_with_alpha("#ffffff", 24 if strong else 15)


def item_separator_color() -> QColor:
    if get_theme() == "light":
        return color_with_alpha("#000000", 15)
    return color_with_alpha("#ffffff", 14)


def selected_text_color() -> QColor:
    return QColor(Colors.TEXT_PRIMARY)


def selected_badge_text_color() -> QColor:
    return QColor(Colors.PROJECT_BUTTON_TEXT)


# ═══════════════════════════════════════════════════════════════════════
#  Component style helpers
# ═══════════════════════════════════════════════════════════════════════


def _join(selector: str, state: str) -> str:
    return ", ".join(f"{part.strip()}{state}" for part in selector.split(","))


def _input_rules(selector: str, padding: str) -> str:
    """Fluent text control: flat fill, stronger bottom stroke, and an accent
    underline while focused."""
    return f"""
        {selector} {{
            background: {Colors.BG_INPUT};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-bottom: 1px solid {Colors.BORDER_STRONG};
            border-radius: {Radius.MD}px;
            padding: {padding};
            color: {Colors.TEXT_PRIMARY};
            selection-background-color: {Colors.ACCENT_PRIMARY};
            selection-color: {Colors.PROJECT_BUTTON_TEXT};
        }}
        {_join(selector, ":hover")} {{
            background: {Colors.BG_INPUT_HOVER};
        }}
        {_join(selector, ":focus")} {{
            background: {Colors.BG_INPUT_FOCUS};
            border-bottom: 2px solid {Colors.BORDER_FOCUS};
        }}
        {_join(selector, ":disabled")} {{
            color: {Colors.TEXT_DISABLED};
            border-bottom: 1px solid {Colors.BORDER_DEFAULT};
        }}
    """


def _button_rules(padding: str, font_size: int) -> str:
    """Fluent standard button: flat control fill, hairline stroke, regular
    weight, subtle hover and a dimmed pressed state."""
    return f"""
        QPushButton {{
            background: {Colors.BG_SURFACE};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.SM}px;
            padding: {padding};
            font-size: {font_size}px;
            font-weight: {Typography.WEIGHT_NORMAL};
            color: {Colors.TEXT_PRIMARY};
        }}
        QPushButton:hover {{
            background: {Colors.SURFACE_HOVER};
        }}
        QPushButton:pressed {{
            background: {Colors.BG_SECONDARY};
            color: {Colors.TEXT_SECONDARY};
        }}
        QPushButton:disabled {{
            background: {Colors.BG_SECONDARY};
            border: 1px solid {Colors.BORDER_SUBTLE};
            color: {Colors.TEXT_DISABLED};
        }}
    """


def _menu_rules() -> str:
    return f"""
        QMenu {{
            background: {Colors.BG_ELEVATED};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.LG}px;
            padding: 4px;
        }}
        QMenu::item {{
            padding: 7px 28px 7px 12px;
            margin: 1px 0;
            border-radius: {Radius.SM}px;
            color: {Colors.TEXT_PRIMARY};
            font-size: {Typography.SIZE_CONTROL}px;
        }}
        QMenu::item:selected {{
            background: {_argb(item_selection_color())};
            color: {Colors.TEXT_PRIMARY};
        }}
        QMenu::item:disabled {{
            color: {Colors.TEXT_DISABLED};
        }}
        QMenu::separator {{
            height: 1px;
            background: {Colors.BORDER_DEFAULT};
            margin: 4px 0;
        }}
    """


def get_panel_style() -> str:
    return f"""
        QFrame#Panel {{
            background: {Colors.BG_SECONDARY};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.LG}px;
        }}
    """


def get_card_style() -> str:
    return f"""
        QFrame#Card {{
            background: {Colors.BG_CARD};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.LG}px;
        }}
    """


def get_list_style(
    accent: str = Colors.ACCENT_PRIMARY, borderless: bool = False
) -> str:
    if borderless:
        frame = "background: transparent;\n            border: none;"
    else:
        frame = (
            f"background: {Colors.BG_SECONDARY};\n"
            f"            border: 1px solid {Colors.BORDER_SUBTLE};\n"
            f"            border-radius: {Radius.LG}px;"
        )
    return f"""
        QListWidget {{
            {frame}
            outline: none;
            padding: 4px;
        }}
        QListWidget::item {{
            padding: 7px 12px 7px 9px;
            border-radius: {Radius.SM}px;
            margin: 1px 2px;
            color: {Colors.TEXT_PRIMARY};
            font-size: {Typography.SIZE_BODY}px;
            border: none;
            border-left: 3px solid transparent;
        }}
        QListWidget::item:selected {{
            background: {_argb(item_selection_color())};
            color: {Colors.TEXT_PRIMARY};
            border-left: 3px solid {Colors.ACCENT_PRIMARY};
        }}
        QListWidget::item:hover:!selected {{
            background: {_argb(item_hover_color())};
        }}
        {_scrollbar_v()}
    """


def get_tree_style() -> str:
    return f"""
        QTreeView {{
            background: {Colors.BG_SECONDARY};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.LG}px;
            outline: none;
            padding: 4px;
        }}
        QTreeView::item {{
            border-radius: {Radius.SM}px;
            margin: 1px 0;
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
        {_input_rules("QLineEdit", "6px 11px")}
        QLineEdit {{
            font-size: {Typography.SIZE_FILTER}px;
        }}
        QLineEdit::placeholder {{
            color: {Colors.TEXT_PLACEHOLDER};
        }}
    """


def get_combo_style() -> str:
    from app.ui.icons import icon_file

    arrow = icon_file("chevron-down.svg", Colors.TEXT_SECONDARY, stroke_width=1.75)
    return f"""
        QComboBox {{
            background: {Colors.BG_SURFACE};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.MD}px;
            padding: 5px 11px;
            font-size: {Typography.SIZE_FILTER}px;
            color: {Colors.TEXT_PRIMARY};
            min-height: 22px;
        }}
        QComboBox:hover {{
            background: {Colors.SURFACE_HOVER};
        }}
        QComboBox:focus {{
            border: 1px solid {Colors.BORDER_FOCUS};
        }}
        QComboBox:disabled {{
            color: {Colors.TEXT_DISABLED};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 28px;
        }}
        QComboBox::down-arrow {{
            image: url("{arrow}");
            width: 12px;
            height: 12px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {Colors.BG_ELEVATED};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.LG}px;
            selection-background-color: {_argb(item_selection_color())};
            selection-color: {Colors.TEXT_PRIMARY};
            color: {Colors.TEXT_PRIMARY};
            outline: none;
            padding: 4px;
        }}
    """


def get_button_style(accent: str = Colors.ACCENT_PRIMARY) -> str:
    """Fluent standard button."""
    return _button_rules(f"6px {Spacing.LG}px", Typography.SIZE_CONTROL)


def get_compact_button_style(accent: str = Colors.ACCENT_PRIMARY) -> str:
    """Bouton compact pour les barres d'actions d'onglets.

    Même contrat visuel que :func:`get_button_style`, en réduit.
    """
    return _button_rules("4px 10px", Typography.SIZE_META)


def get_accent_button_style() -> str:
    """Fluent accent button: solid accent fill, contrasting text."""
    return f"""
        QPushButton {{
            background: {Colors.ACCENT_PRIMARY};
            border: 1px solid {Colors.ACCENT_DARK};
            border-radius: {Radius.SM}px;
            padding: 6px {Spacing.LG}px;
            font-size: {Typography.SIZE_CONTROL}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            color: {Colors.PROJECT_BUTTON_TEXT};
        }}
        QPushButton:hover {{
            background: {Colors.ACCENT_LIGHT};
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
    return f"""
        QPushButton {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: {Radius.SM}px;
            min-width: {size}px; max-width: {size}px;
            min-height: {size}px; max-height: {size}px;
        }}
        QPushButton:hover {{
            background: {Colors.GLASS_MEDIUM};
        }}
        QPushButton:pressed {{
            background: {Colors.GLASS_LIGHT};
        }}
        QPushButton:checked {{
            background: {Colors.ACCENT_GLOW};
            border: 1px solid {Colors.BORDER_ACCENT};
        }}
    """


def get_splitter_style() -> str:
    return f"""
        QSplitter::handle {{
            background: transparent;
            margin: 0;
        }}
        QSplitter::handle:horizontal {{
            width: 4px;
        }}
        QSplitter::handle:vertical {{
            height: 4px;
        }}
        QSplitter::handle:hover {{
            background: {Colors.BORDER_HOVER};
        }}
    """


def get_tab_button_style(active: bool = False) -> str:
    """Fluent pivot item: the selected label is primary text over a short
    accent underline; idle items use secondary text."""
    if active:
        return f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-bottom: 3px solid {Colors.ACCENT_PRIMARY};
                border-radius: 0;
                padding: 8px 14px;
                font-size: {Typography.SIZE_CONTROL}px;
                font-weight: {Typography.WEIGHT_SEMIBOLD};
                color: {Colors.TEXT_PRIMARY};
            }}
        """
    return f"""
        QPushButton {{
            background: transparent;
            border: none;
            border-bottom: 3px solid transparent;
            border-radius: 0;
            padding: 8px 14px;
            font-size: {Typography.SIZE_CONTROL}px;
            font-weight: {Typography.WEIGHT_NORMAL};
            color: {Colors.TEXT_SECONDARY};
        }}
        QPushButton:hover {{
            color: {Colors.TEXT_PRIMARY};
        }}
    """


def get_header_style() -> str:
    return """
        QFrame {
            background: transparent;
            border: none;
            border-radius: 0;
        }
    """


def get_surface_panel_style(radius: int = Radius.LG) -> str:
    return f"""
        QFrame {{
            background: {Colors.BG_CARD};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {radius}px;
        }}
    """


def get_preview_text_style() -> str:
    return f"""
        {_input_rules("QPlainTextEdit", "10px 12px")}
        QPlainTextEdit {{
            placeholder-text-color: {Colors.TEXT_PLACEHOLDER};
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
            font-size: {Typography.SIZE_DIALOG_TITLE}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            color: {Colors.TEXT_PRIMARY};
            background: transparent;
        }}
    """


def get_subtitle_style() -> str:
    return f"""
        QLabel {{
            font-size: {Typography.SIZE_CONTROL}px;
            font-weight: {Typography.WEIGHT_NORMAL};
            color: {Colors.TEXT_SECONDARY};
            background: transparent;
        }}
    """


def get_badge_style(color: str = Colors.ACCENT_PRIMARY) -> str:
    return f"""
        QLabel {{
            background: {Colors.GLASS_MEDIUM};
            color: {color};
            border-radius: {Radius.SM}px;
            padding: 2px 8px;
            font-size: {Typography.SIZE_NUMBER}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
        }}
    """


def get_menu_style() -> str:
    return _menu_rules()


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
            background: {Colors.BG_CARD};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.LG}px;
            padding: 4px;
        }}
    """


def get_divider_style() -> str:
    return f"""
        QFrame#Divider {{
            background: {Colors.BORDER_DEFAULT};
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
            background: {Colors.WINDOW_BG};
        }}
        QWidget {{
            color: {Colors.TEXT_PRIMARY};
            font-family: {Typography.PRIMARY_FAMILY};
            font-size: {Typography.SIZE_BODY}px;
        }}
        QToolTip {{
            background-color: {_tooltip_bg()};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.SM}px;
            padding: 6px 10px;
            color: {_tooltip_text()};
            font-size: {Typography.SIZE_FILTER}px;
            opacity: 255;
        }}
    """


def build_app_stylesheet() -> str:
    """Return the global QSS for the currently selected theme (Fluent)."""
    from app.ui.icons import icon_file

    check = icon_file("check.svg", Colors.PROJECT_BUTTON_TEXT, stroke_width=3)
    hover = _argb(item_hover_color())
    selected = _argb(item_selection_color())
    return f"""
        QWidget {{
            font-family: {Typography.PRIMARY_FAMILY};
            font-size: {Typography.SIZE_BODY}px;
            color: {Colors.TEXT_PRIMARY};
            outline: none;
            selection-background-color: {Colors.ACCENT_PRIMARY};
            selection-color: {Colors.PROJECT_BUTTON_TEXT};
        }}

        QMainWindow {{
            background: {Colors.WINDOW_BG};
        }}

        QDialog,
        QMessageBox {{
            background: {Colors.BG_PRIMARY};
        }}

        QLabel#PanelTitle {{
            font-size: {Typography.SIZE_SECTION}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            color: {Colors.TEXT_PRIMARY};
            padding: 12px 16px;
        }}

        QLabel#TopBarTitle {{
            font-size: {Typography.SIZE_TITLE}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            color: {Colors.TEXT_PRIMARY};
        }}

        QLabel#DescLabel {{
            color: {Colors.TEXT_SECONDARY};
            font-size: {Typography.SIZE_FILTER}px;
            border: none;
            background: transparent;
        }}

        QLabel#Badge {{
            background: {Colors.GLASS_MEDIUM};
            color: {Colors.TEXT_SECONDARY};
            border-radius: {Radius.SM}px;
            padding: 2px 8px;
            font-size: {Typography.SIZE_NUMBER}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
        }}

        QFrame#Panel,
        QFrame#BottomBar {{
            background: {Colors.BG_SECONDARY};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.LG}px;
        }}

        QFrame#Card,
        QFrame#Toolbar,
        QFrame#TopBar {{
            background: {Colors.BG_CARD};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.LG}px;
        }}

        QFrame#TopBar {{
            min-height: 48px;
        }}

        {_input_rules("QLineEdit, QSpinBox, QDoubleSpinBox", "5px 11px")}
        QLineEdit, QSpinBox, QDoubleSpinBox {{
            font-size: {Typography.SIZE_FILTER}px;
        }}

        {_input_rules("QTextEdit, QPlainTextEdit", "8px 11px")}

        QLineEdit::placeholder {{
            color: {Colors.TEXT_PLACEHOLDER};
        }}

        QSpinBox::up-button, QSpinBox::down-button,
        QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
            width: 18px;
            border: none;
            background: transparent;
        }}

        {get_combo_style()}

        {_menu_rules()}

        QToolTip {{
            background-color: {_tooltip_bg()};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.SM}px;
            color: {_tooltip_text()};
            padding: 6px 10px;
            font-size: {Typography.SIZE_FILTER}px;
            opacity: 255;
        }}

        {_button_rules("6px 16px", Typography.SIZE_CONTROL)}

        QPushButton:focus {{
            border: 1px solid {Colors.BORDER_FOCUS};
        }}

        QPushButton#ProjectButton,
        QPushButton#AccentButton {{
            background: {Colors.ACCENT_PRIMARY};
            color: {Colors.PROJECT_BUTTON_TEXT};
            border: 1px solid {Colors.ACCENT_DARK};
            font-weight: {Typography.WEIGHT_SEMIBOLD};
        }}

        QPushButton#ProjectButton:hover,
        QPushButton#AccentButton:hover {{
            background: {Colors.ACCENT_LIGHT};
        }}

        QPushButton#ProjectButton:pressed,
        QPushButton#AccentButton:pressed {{
            background: {Colors.ACCENT_DARK};
        }}

        QPushButton#IconButton {{
            padding: 6px;
            background: transparent;
            border: 1px solid transparent;
        }}

        QPushButton#IconButton:hover {{
            background: {Colors.GLASS_MEDIUM};
        }}

        QToolButton {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: {Radius.SM}px;
            padding: 4px;
        }}

        QToolButton:hover {{
            background: {Colors.GLASS_MEDIUM};
        }}

        QToolButton:pressed {{
            background: {Colors.GLASS_LIGHT};
        }}

        QListView,
        QTreeView,
        QListWidget,
        QTableView,
        QTableWidget {{
            background-color: {Colors.BG_SECONDARY};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.LG}px;
            color: {Colors.TEXT_PRIMARY};
            font-size: {Typography.SIZE_BODY}px;
        }}

        QListView::item,
        QListWidget::item {{
            padding: 7px 12px;
            border-radius: {Radius.SM}px;
            margin: 1px 2px;
            color: {Colors.TEXT_PRIMARY};
        }}

        QListView::item:hover,
        QListWidget::item:hover {{
            background: {hover};
        }}

        QListView::item:selected,
        QListWidget::item:selected,
        QTableView::item:selected,
        QTableWidget::item:selected {{
            background: {selected};
            color: {Colors.TEXT_PRIMARY};
        }}

        QTabWidget::pane {{
            background: transparent;
            border: none;
        }}

        QTabBar::tab {{
            background: transparent;
            padding: 8px 14px;
            margin: 0 2px;
            color: {Colors.TEXT_SECONDARY};
            font-size: {Typography.SIZE_CONTROL}px;
            border-bottom: 3px solid transparent;
        }}

        QTabBar::tab:hover {{
            color: {Colors.TEXT_PRIMARY};
        }}

        QTabBar::tab:selected {{
            color: {Colors.TEXT_PRIMARY};
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            border-bottom: 3px solid {Colors.ACCENT_PRIMARY};
        }}

        QCheckBox,
        QRadioButton {{
            color: {Colors.TEXT_PRIMARY};
            spacing: 8px;
            font-size: {Typography.SIZE_LABEL}px;
            background: transparent;
        }}

        QCheckBox::indicator,
        QRadioButton::indicator {{
            width: 18px;
            height: 18px;
            border: 1px solid {Colors.BORDER_STRONG};
            background: {Colors.GLASS_LIGHT};
        }}

        QCheckBox::indicator {{
            border-radius: {Radius.SM}px;
        }}

        QRadioButton::indicator {{
            border-radius: 10px;
        }}

        QCheckBox::indicator:hover,
        QRadioButton::indicator:hover {{
            background: {Colors.GLASS_MEDIUM};
        }}

        QCheckBox::indicator:checked {{
            background: {Colors.ACCENT_PRIMARY};
            border-color: {Colors.ACCENT_PRIMARY};
            image: url("{check}");
        }}

        QCheckBox::indicator:checked:hover {{
            background: {Colors.ACCENT_LIGHT};
        }}

        QRadioButton::indicator:checked {{
            background: {Colors.PROJECT_BUTTON_TEXT};
            border: 5px solid {Colors.ACCENT_PRIMARY};
            width: 10px;
            height: 10px;
        }}

        QCheckBox::indicator:disabled,
        QRadioButton::indicator:disabled {{
            border-color: {Colors.TEXT_DISABLED};
            background: transparent;
        }}

        QGroupBox {{
            color: {Colors.TEXT_PRIMARY};
            background: {Colors.BG_CARD};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.LG}px;
            margin-top: 28px;
            padding: 12px;
            font-size: {Typography.SIZE_BODY}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
        }}

        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 2px;
            padding: 0 0 6px 0;
            background: transparent;
            color: {Colors.TEXT_PRIMARY};
        }}

        QProgressBar {{
            background: {Colors.BORDER_STRONG};
            border: none;
            border-radius: 1px;
            text-align: center;
            color: transparent;
            font-size: {Typography.SIZE_NUMBER}px;
            max-height: 3px;
        }}

        QProgressBar::chunk {{
            background: {Colors.ACCENT_PRIMARY};
            border-radius: 1px;
        }}

        QSlider::groove:horizontal {{
            height: 4px;
            background: {Colors.BORDER_STRONG};
            border-radius: 2px;
        }}

        QSlider::sub-page:horizontal {{
            background: {Colors.ACCENT_PRIMARY};
            border-radius: 2px;
        }}

        QSlider::handle:horizontal {{
            width: 10px;
            height: 10px;
            margin: -8px 0;
            background: {Colors.ACCENT_PRIMARY};
            border-radius: 10px;
            border: 5px solid {Colors.SLIDER_THUMB};
        }}

        QSlider::handle:horizontal:hover {{
            background: {Colors.ACCENT_LIGHT};
        }}

        QSlider::groove:vertical {{
            width: 4px;
            background: {Colors.BORDER_STRONG};
            border-radius: 2px;
        }}

        QSlider::add-page:vertical {{
            background: {Colors.ACCENT_PRIMARY};
            border-radius: 2px;
        }}

        QSlider::handle:vertical {{
            width: 10px;
            height: 10px;
            margin: 0 -8px;
            background: {Colors.ACCENT_PRIMARY};
            border-radius: 10px;
            border: 5px solid {Colors.SLIDER_THUMB};
        }}

        QHeaderView {{
            background: transparent;
            border: none;
        }}

        QHeaderView::section {{
            background: transparent;
            color: {Colors.TEXT_SECONDARY};
            font-size: {Typography.SIZE_META}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            padding: 8px 12px;
            border: none;
            border-bottom: 1px solid {Colors.BORDER_DEFAULT};
        }}

        QHeaderView::section:hover {{
            background: {hover};
            color: {Colors.TEXT_PRIMARY};
        }}

        QTableView, QTableWidget {{
            gridline-color: {Colors.BORDER_SUBTLE};
            selection-background-color: {selected};
            selection-color: {Colors.TEXT_PRIMARY};
        }}

        QTableView::item, QTableWidget::item {{
            padding: 6px 12px;
            border: none;
        }}

        {_scrollbar_v()}
        {_scrollbar_h()}
    """
