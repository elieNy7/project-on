"""Centralized theme system for Project-On.

A refined, premium design language for a church presentation
application dedicated to the Message of William Branham.
Deep obsidian tones with warm gold accents — reverent, cinematic and modern.
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
    BG_PRIMARY = "#07111f"
    BG_SECONDARY = "#0c1828"
    BG_TERTIARY = "#122238"
    BG_ELEVATED = "#182c45"
    BG_SURFACE = "#203752"
    GLASS_LIGHT = "rgba(203, 213, 225, 0.045)"
    GLASS_MEDIUM = "rgba(203, 213, 225, 0.085)"
    GLASS_HEAVY = "rgba(203, 213, 225, 0.14)"
    SURFACE = "#122238"
    SURFACE_HOVER = "#1a304a"
    SURFACE_ACTIVE = "#243e5c"
    TEXT_PRIMARY = "#f8fafc"
    TEXT_SECONDARY = "#cbd5e1"
    TEXT_MUTED = "#91a2b8"
    TEXT_DISABLED = "#5f7086"
    ACCENT_PRIMARY = "#f0b85b"
    ACCENT_LIGHT = "#ffd58a"
    ACCENT_GLOW = "rgba(240, 184, 91, 0.12)"
    ACCENT_GLOW_STRONG = "rgba(240, 184, 91, 0.24)"
    ACCENT_SECONDARY = "#5cb8ff"
    ACCENT_SUCCESS = "#4ade80"
    ACCENT_WARNING = "#f6ad55"
    ACCENT_DANGER = "#fb7185"
    SRC_BIBLE = "#4ade80"
    SRC_SERMON = "#f6ad55"
    SRC_HYMN = "#c4a7ff"
    SRC_CUSTOM = "#5cb8ff"
    SRC_IMAGE = "#91a2b8"
    BORDER_SUBTLE = "rgba(148, 163, 184, 0.10)"
    BORDER_DEFAULT = "rgba(148, 163, 184, 0.17)"
    BORDER_HOVER = "rgba(203, 213, 225, 0.28)"
    BORDER_FOCUS = "#5cb8ff"
    PROJECT_BUTTON_TEXT = "#07111f"
    MAIN_GRADIENT_START = "#050c16"
    MAIN_GRADIENT_END = "#0a1a2d"
    PANEL_GRADIENT_END = "#091523"
    SIDEBAR_GRADIENT_START = "#11243b"
    APP_STYLESHEET_NAME = "dark"


_DARK_PALETTE = {
    "BG_PRIMARY": "#07111f",
    "BG_SECONDARY": "#0c1828",
    "BG_TERTIARY": "#122238",
    "BG_ELEVATED": "#182c45",
    "BG_SURFACE": "#203752",
    "GLASS_LIGHT": "rgba(203, 213, 225, 0.045)",
    "GLASS_MEDIUM": "rgba(203, 213, 225, 0.085)",
    "GLASS_HEAVY": "rgba(203, 213, 225, 0.14)",
    "SURFACE": "#122238",
    "SURFACE_HOVER": "#1a304a",
    "SURFACE_ACTIVE": "#243e5c",
    "TEXT_PRIMARY": "#f8fafc",
    "TEXT_SECONDARY": "#cbd5e1",
    "TEXT_MUTED": "#91a2b8",
    "TEXT_DISABLED": "#5f7086",
    "ACCENT_PRIMARY": "#f0b85b",
    "ACCENT_LIGHT": "#ffd58a",
    "ACCENT_GLOW": "rgba(240, 184, 91, 0.12)",
    "ACCENT_GLOW_STRONG": "rgba(240, 184, 91, 0.24)",
    "ACCENT_SECONDARY": "#5cb8ff",
    "ACCENT_SUCCESS": "#4ade80",
    "ACCENT_WARNING": "#f6ad55",
    "ACCENT_DANGER": "#fb7185",
    "SRC_BIBLE": "#4ade80",
    "SRC_SERMON": "#f6ad55",
    "SRC_HYMN": "#c4a7ff",
    "SRC_CUSTOM": "#5cb8ff",
    "SRC_IMAGE": "#91a2b8",
    "BORDER_SUBTLE": "rgba(148, 163, 184, 0.10)",
    "BORDER_DEFAULT": "rgba(148, 163, 184, 0.17)",
    "BORDER_HOVER": "rgba(203, 213, 225, 0.28)",
    "BORDER_FOCUS": "#5cb8ff",
    "SHADOW_SM": "0 2px 4px rgba(0, 0, 0, 0.3)",
    "SHADOW_MD": "0 8px 24px rgba(0, 0, 0, 0.45)",
    "SHADOW_LG": "0 24px 64px rgba(0, 0, 0, 0.6)",
    "PROJECT_BUTTON_TEXT": "#07111f",
    "MAIN_GRADIENT_START": "#050c16",
    "MAIN_GRADIENT_END": "#0a1a2d",
    "PANEL_GRADIENT_END": "#091523",
    "SIDEBAR_GRADIENT_START": "#11243b",
    "APP_STYLESHEET_NAME": "dark",
}


_LIGHT_PALETTE = {
    "BG_PRIMARY": "#f3f6fb",
    "BG_SECONDARY": "#ffffff",
    "BG_TERTIARY": "#edf3fa",
    "BG_ELEVATED": "#ffffff",
    "BG_SURFACE": "#dce7f3",
    "GLASS_LIGHT": "rgba(20, 28, 42, 0.025)",
    "GLASS_MEDIUM": "rgba(20, 28, 42, 0.065)",
    "GLASS_HEAVY": "rgba(20, 28, 42, 0.12)",
    "SURFACE": "#edf3fa",
    "SURFACE_HOVER": "#e1ebf6",
    "SURFACE_ACTIVE": "#d3e0ee",
    "TEXT_PRIMARY": "#132238",
    "TEXT_SECONDARY": "#40536b",
    "TEXT_MUTED": "#63758b",
    "TEXT_DISABLED": "#9aa8b8",
    "ACCENT_PRIMARY": "#9a5d0b",
    "ACCENT_LIGHT": "#9c5f12",
    "ACCENT_GLOW": "rgba(154, 93, 11, 0.11)",
    "ACCENT_GLOW_STRONG": "rgba(154, 93, 11, 0.20)",
    "ACCENT_SECONDARY": "#0b72d0",
    "ACCENT_SUCCESS": "#15803d",
    "ACCENT_WARNING": "#c47a16",
    "ACCENT_DANGER": "#d33f3f",
    "SRC_BIBLE": "#15803d",
    "SRC_SERMON": "#c47a16",
    "SRC_HYMN": "#7c3aed",
    "SRC_CUSTOM": "#2563eb",
    "SRC_IMAGE": "#64748b",
    "BORDER_SUBTLE": "rgba(20, 28, 42, 0.07)",
    "BORDER_DEFAULT": "rgba(20, 28, 42, 0.12)",
    "BORDER_HOVER": "rgba(20, 28, 42, 0.22)",
    "BORDER_FOCUS": "#0b72d0",
    "SHADOW_SM": "0 2px 4px rgba(15, 23, 42, 0.08)",
    "SHADOW_MD": "0 8px 24px rgba(15, 23, 42, 0.12)",
    "SHADOW_LG": "0 24px 64px rgba(15, 23, 42, 0.16)",
    "PROJECT_BUTTON_TEXT": "#ffffff",
    "MAIN_GRADIENT_START": "#eaf1f8",
    "MAIN_GRADIENT_END": "#f8fbff",
    "PANEL_GRADIENT_END": "#ffffff",
    "SIDEBAR_GRADIENT_START": "#f9fbfe",
    "APP_STYLESHEET_NAME": "light",
}


def _apply_palette(theme: str) -> None:
    palette = _LIGHT_PALETTE if theme == "light" else _DARK_PALETTE
    for key, value in palette.items():
        setattr(Colors, key, value)


class Spacing:
    """Consistent spacing scale (px)."""

    NONE = 0
    XS = 4
    SM = 8
    MD = 12
    LG = 18
    XL = 28
    XXL = 44
    GUTTER = 16


class Radius:
    """Border radius scale (px)."""

    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 20
    FULL = 9999


class Typography:
    """Font sizes and weights."""

    PRIMARY_FAMILY = "'Poppins', 'Segoe UI', sans-serif"
    FAMILY = "Poppins"

    SIZE_XS = 11
    SIZE_XS_PT = 8
    SIZE_SM = 12
    SIZE_SM_PT = 9
    SIZE_MD = 13
    SIZE_MD_PT = 10
    SIZE_LG = 15
    SIZE_LG_PT = 11
    SIZE_XL = 18
    SIZE_XL_PT = 13
    SIZE_2XL = 22
    SIZE_2XL_PT = 16
    SIZE_3XL = 28
    SIZE_3XL_PT = 21
    SIZE_4XL = 36
    SIZE_4XL_PT = 27

    WEIGHT_NORMAL = 400
    WEIGHT_MEDIUM = 500
    WEIGHT_SEMIBOLD = 600
    WEIGHT_BOLD = 700


# ═══════════════════════════════════════════════════════════════════════
#  Shared scrollbar snippet
# ═══════════════════════════════════════════════════════════════════════

_SCROLLBAR_V = f"""
    QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        margin: 4px 2px;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(255, 255, 255, 0.06);
        border-radius: 3px;
        min-height: 40px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: rgba(255, 255, 255, 0.12);
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
"""

_SCROLLBAR_H = f"""
    QScrollBar:horizontal {{
        background: transparent;
        height: 6px;
        margin: 2px 4px;
    }}
    QScrollBar::handle:horizontal {{
        background: rgba(255, 255, 255, 0.06);
        border-radius: 3px;
        min-width: 40px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: rgba(255, 255, 255, 0.12);
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: transparent;
    }}
"""


def _scrollbar_v() -> str:
    return f"""
        QScrollBar:vertical {{
            background: {Colors.GLASS_LIGHT};
            width: 10px;
            margin: 4px 2px;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical {{
            background: {Colors.BORDER_HOVER};
            border-radius: 5px;
            min-height: 48px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {Colors.ACCENT_LIGHT};
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
            background: {Colors.GLASS_LIGHT};
            height: 10px;
            margin: 3px 8px;
            border-radius: 5px;
        }}
        QScrollBar::handle:horizontal {{
            background: {Colors.BORDER_HOVER};
            border-radius: 5px;
            min-width: 64px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {Colors.ACCENT_LIGHT};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: transparent;
        }}
    """


def _tooltip_bg() -> str:
    return "#ffffff" if Colors.APP_STYLESHEET_NAME == "light" else Colors.BG_ELEVATED


def _tooltip_text() -> str:
    return "#111827" if Colors.APP_STYLESHEET_NAME == "light" else Colors.TEXT_PRIMARY


def color_with_alpha(color: str, alpha: int) -> QColor:
    qcolor = QColor(color)
    qcolor.setAlpha(alpha)
    return qcolor


def item_hover_color() -> QColor:
    if get_theme() == "light":
        return color_with_alpha("#172033", 14)
    return color_with_alpha("#cbd5e1", 18)


def item_selection_color(strong: bool = False) -> QColor:
    alpha = 42 if get_theme() == "light" else 38
    if strong:
        alpha += 10
    return color_with_alpha(Colors.ACCENT_PRIMARY, alpha)


def item_separator_color() -> QColor:
    if get_theme() == "light":
        return color_with_alpha("#172033", 22)
    return color_with_alpha("#94a3b8", 30)


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


def get_list_style(accent: str = Colors.ACCENT_PRIMARY) -> str:
    return f"""
        QListWidget {{
            background: {Colors.BG_SECONDARY};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.MD}px;
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
            font-size: 13px;
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
            background: {Colors.BG_SECONDARY};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.MD}px;
            padding: 7px 12px;
            font-size: {Typography.SIZE_MD}px;
            color: {Colors.TEXT_PRIMARY};
            selection-background-color: {Colors.ACCENT_GLOW_STRONG};
            selection-color: {Colors.ACCENT_PRIMARY};
        }}
        QLineEdit:focus {{
            background: {Colors.BG_ELEVATED};
            border: 1px solid {Colors.BORDER_FOCUS};
        }}
        QLineEdit::placeholder {{
            color: {Colors.TEXT_MUTED};
        }}
    """


def get_combo_style() -> str:
    return f"""
        QComboBox {{
            background: {Colors.BG_SECONDARY};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.MD}px;
            padding: 5px 12px;
            font-size: {Typography.SIZE_SM}px;
            color: {Colors.TEXT_PRIMARY};
            min-height: 24px;
        }}
        QComboBox:hover {{
            background: {Colors.SURFACE_HOVER};
        }}
        QComboBox:focus {{
            background: {Colors.BG_ELEVATED};
            border: 1px solid {Colors.BORDER_FOCUS};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}
        QComboBox::down-arrow {{
            image: none;
            width: 0;
        }}
        QComboBox QAbstractItemView {{
            background-color: {Colors.BG_ELEVATED};
            border: none;
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
            font-size: {Typography.SIZE_MD}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            color: {Colors.TEXT_PRIMARY};
        }}
        QPushButton:hover {{
            background: {Colors.SURFACE_ACTIVE};
            border: 1px solid {Colors.BORDER_HOVER};
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
            width: 1px;
        }}
        QSplitter::handle:vertical {{
            height: 1px;
        }}
        QSplitter::handle:hover {{
            background: {Colors.BORDER_FOCUS};
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
                padding: 8px 14px;
                font-size: {Typography.SIZE_SM}px;
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
            padding: 8px 14px;
            font-size: {Typography.SIZE_SM}px;
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
            background: {Colors.BG_SECONDARY};
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
            placeholder-text-color: {Colors.TEXT_MUTED};
        }}
        QPlainTextEdit:focus {{
            border: 1px solid {Colors.BORDER_FOCUS};
        }}
    """


def get_label_style(size: int = Typography.SIZE_MD, muted: bool = False) -> str:
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
            font-size: {Typography.SIZE_XL}px;
            font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_PRIMARY};
            background: transparent;
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
            padding: 7px 14px;
            border-radius: {Radius.SM}px;
            color: {Colors.TEXT_PRIMARY};
            font-size: {Typography.SIZE_SM}px;
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


# ═══════════════════════════════════════════════════════════════════════
#  Main window style
# ═══════════════════════════════════════════════════════════════════════


def get_main_window_style() -> str:
    return f"""
        QMainWindow {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {Colors.MAIN_GRADIENT_START},
                stop:0.55 {Colors.BG_PRIMARY},
                stop:1 {Colors.MAIN_GRADIENT_END}
            );
        }}
        QWidget {{
            color: {Colors.TEXT_PRIMARY};
            font-family: {Typography.FAMILY};
            font-size: {Typography.SIZE_MD}px;
        }}
        QToolTip {{
            background-color: {_tooltip_bg()};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.SM}px;
            padding: 5px 10px;
            color: {_tooltip_text()};
            font-size: {Typography.SIZE_SM}px;
            opacity: 255;
        }}
    """


def build_app_stylesheet() -> str:
    """Return the global QSS for the currently selected theme."""
    return f"""
        QWidget {{
            font-family: "Poppins", "Segoe UI", sans-serif;
            font-size: {Typography.SIZE_MD}px;
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
            font-size: {Typography.SIZE_SM}px;
            font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.ACCENT_PRIMARY};
            padding: 12px 16px;
            letter-spacing: 0;
            text-transform: uppercase;
        }}

        QLabel#TopBarTitle {{
            font-size: {Typography.SIZE_LG}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            color: {Colors.TEXT_PRIMARY};
        }}

        QLabel#DescLabel {{
            color: {Colors.TEXT_MUTED};
            font-size: {Typography.SIZE_SM}px;
            border: none;
            background: transparent;
        }}

        QFrame#Panel,
        QFrame#BottomBar {{
            background: {Colors.BG_SECONDARY};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.LG}px;
        }}

        QFrame#TopBar {{
            background: {Colors.BG_TERTIARY};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {Radius.MD}px;
            min-height: 52px;
        }}

        QLineEdit,
        QSpinBox,
        QTextEdit,
        QPlainTextEdit,
        QComboBox {{
            background-color: {Colors.BG_SECONDARY};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.MD}px;
            padding: 7px 12px;
            color: {Colors.TEXT_PRIMARY};
            selection-background-color: {Colors.ACCENT_GLOW_STRONG};
            selection-color: {Colors.ACCENT_LIGHT};
        }}

        QLineEdit:hover,
        QSpinBox:hover,
        QComboBox:hover {{
            background-color: {Colors.SURFACE_HOVER};
            border-color: {Colors.BORDER_HOVER};
        }}

        QLineEdit:focus,
        QSpinBox:focus,
        QComboBox:focus {{
            background-color: {Colors.BG_ELEVATED};
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
        }}

        QToolTip {{
            background-color: {_tooltip_bg()};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.MD}px;
            color: {_tooltip_text()};
            padding: 8px 10px;
            opacity: 255;
        }}

        QMenu::item {{
            padding: 7px 14px;
            border-radius: {Radius.SM}px;
            color: {Colors.TEXT_PRIMARY};
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
            font-weight: {Typography.WEIGHT_SEMIBOLD};
        }}

        QPushButton:hover {{
            background: {Colors.SURFACE_HOVER};
            border-color: {Colors.BORDER_HOVER};
            color: {Colors.ACCENT_LIGHT};
        }}

        QPushButton:pressed {{
            background: {Colors.SURFACE_ACTIVE};
        }}

        QPushButton:disabled {{
            color: {Colors.TEXT_DISABLED};
            background: transparent;
            border-color: {Colors.BORDER_SUBTLE};
        }}

        QPushButton#ProjectButton {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {Colors.ACCENT_PRIMARY},
                stop:1 {Colors.ACCENT_LIGHT}
            );
            color: {Colors.PROJECT_BUTTON_TEXT};
            border: 1px solid {Colors.ACCENT_LIGHT};
            font-weight: {Typography.WEIGHT_BOLD};
        }}

        QPushButton#ProjectButton:hover {{
            background: {Colors.ACCENT_LIGHT};
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
        }}

        QTabWidget::pane {{
            background: transparent;
            border: none;
        }}

        QTabBar::tab {{
            background: transparent;
            padding: 10px 22px;
            color: {Colors.TEXT_MUTED};
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            border-bottom: 2px solid transparent;
        }}

        QTabBar::tab:hover {{
            color: {Colors.TEXT_PRIMARY};
            background: {Colors.GLASS_LIGHT};
        }}

        QTabBar::tab:selected {{
            color: {Colors.ACCENT_PRIMARY};
            border-bottom: 2px solid {Colors.ACCENT_PRIMARY};
        }}

        QCheckBox,
        QRadioButton {{
            color: {Colors.TEXT_SECONDARY};
            spacing: 8px;
        }}

        QCheckBox::indicator,
        QRadioButton::indicator {{
            width: 16px;
            height: 16px;
            border: 1px solid {Colors.BORDER_HOVER};
            background: {Colors.BG_SECONDARY};
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

        QCheckBox::indicator:checked,
        QRadioButton::indicator:checked {{
            background: {Colors.ACCENT_PRIMARY};
            border-color: {Colors.ACCENT_PRIMARY};
        }}

        QProgressBar {{
            background: {Colors.BG_TERTIARY};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: 6px;
            text-align: center;
            color: {Colors.TEXT_PRIMARY};
            font-size: {Typography.SIZE_XS}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            height: 6px;
        }}

        QProgressBar::chunk {{
            background: {Colors.ACCENT_PRIMARY};
            border-radius: 6px;
        }}

        QSlider::groove:horizontal {{
            height: 4px;
            background: {Colors.SURFACE_HOVER};
            border-radius: 2px;
        }}

        QSlider::sub-page:horizontal,
        QSlider::sub-page:vertical {{
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
            border-color: {Colors.BG_TERTIARY};
        }}

        QGroupBox {{
            color: {Colors.TEXT_SECONDARY};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.MD}px;
            margin-top: 16px;
            padding-top: 12px;
            font-size: {Typography.SIZE_XS}px;
            font-weight: {Typography.WEIGHT_BOLD};
            letter-spacing: 0;
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

        QHeaderView::section {{
            background: {Colors.BG_ELEVATED};
            color: {Colors.TEXT_SECONDARY};
            font-size: {Typography.SIZE_XS}px;
            font-weight: {Typography.WEIGHT_BOLD};
            padding: 8px 12px;
            border: none;
            border-bottom: 1px solid {Colors.BORDER_SUBTLE};
        }}

        QHeaderView::section:hover {{
            background: {Colors.SURFACE_HOVER};
            color: {Colors.TEXT_SECONDARY};
        }}

        QScrollBar:vertical {{
            background: {Colors.GLASS_LIGHT};
            width: 10px;
            margin: 4px 2px;
            border-radius: 5px;
        }}

        QScrollBar::handle:vertical {{
            background: {Colors.BORDER_HOVER};
            border-radius: 5px;
            min-height: 48px;
        }}

        QScrollBar::handle:vertical:hover {{
            background: {Colors.ACCENT_LIGHT};
        }}

        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical,
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {{
            background: none;
            height: 0;
        }}

        QScrollBar:horizontal {{
            background: {Colors.GLASS_LIGHT};
            height: 10px;
            margin: 3px 8px;
            border-radius: 5px;
        }}

        QScrollBar::handle:horizontal {{
            background: {Colors.BORDER_HOVER};
            border-radius: 5px;
            min-width: 64px;
        }}

        QScrollBar::handle:horizontal:hover {{
            background: {Colors.ACCENT_LIGHT};
        }}

        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal,
        QScrollBar::add-page:horizontal,
        QScrollBar::sub-page:horizontal {{
            background: none;
            width: 0;
        }}
    """


_apply_palette(_current_theme)
