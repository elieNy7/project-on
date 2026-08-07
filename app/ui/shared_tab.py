"""Shared layout primitives for Project-On's library tabs.

Every library tab (Bible, Hymns, Sermons, Exposé) used to build its own
header / filter-bar / card shell by hand, which drifted into inconsistent
looks (missing headers, misplaced search fields, mismatched borders).

This module centralises that skeleton so all tabs share ONE layout language:
a `TabShell` with a unified `SectionHeader` on top, a `FilterBar` for the
search + contextual actions, and a `panel_card` helper for bordered surfaces.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QSplitter,
)

from app.ui.icons import app_icon
from app.ui.theme import Colors, Radius, Spacing, Typography

# ──────────────────────────────────────────────────────────────────────────
#  Shared panel / card helpers
# ──────────────────────────────────────────────────────────────────────────


def panel_card(parent: QWidget | None = None, radius: int = Radius.LG) -> QFrame:
    """A raised surface card used for lists, previews and toolbars everywhere."""
    frame = QFrame(parent)
    frame.setObjectName("Card")
    frame.setStyleSheet(
        f"""
        QFrame#Card {{
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.CARD_GRADIENT_START},
                stop:1 {Colors.CARD_GRADIENT_END}
            );
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {radius}px;
        }}
        """
    )
    return frame


def surface_panel(parent: QWidget | None = None, radius: int = Radius.MD) -> QFrame:
    """A subtle tertiary surface for filter bars and inline panels."""
    frame = QFrame(parent)
    frame.setStyleSheet(
        f"""
        QFrame {{
            background: {Colors.BG_TERTIARY};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: {radius}px;
        }}
        """
    )
    return frame


# ──────────────────────────────────────────────────────────────────────────
#  SectionHeader — the unified tab/section title bar
# ──────────────────────────────────────────────────────────────────────────


class SectionHeader(QFrame):
    """Unified section header used at the top of every tab.

    Layout (left → right):
        [icon]  TITLE  · subtitle            <stretch>  [trailing actions...]

    The icon and title use the accent colour so every section reads as the
    same visual family. Trailing widgets (import buttons, combos, etc.) are
    added through :meth:`add_action`.
    """

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        icon_name: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SectionHeader")
        self.setFixedHeight(52)
        self.setStyleSheet(
            f"""
            QFrame#SectionHeader {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {Colors.BG_TERTIARY},
                    stop:1 {Colors.BG_SECONDARY}
                );
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: {Radius.MD}px;
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, 0, Spacing.MD, 0)
        layout.setSpacing(Spacing.SM)

        self._title = title
        self._subtitle = subtitle

        if icon_name:
            icon_label = QLabel(self)
            icon_label.setPixmap(app_icon(icon_name, Colors.ACCENT_PRIMARY).pixmap(20, 20))
            icon_label.setStyleSheet("background: transparent; border: none;")
            layout.addWidget(icon_label)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)

        self._title_label = QLabel(title, self)
        self._title_label.setObjectName("PanelTitle")
        self._title_label.setStyleSheet(
            f"""
            QLabel#PanelTitle {{
                font-size: {Typography.SIZE_MD}px;
                font-weight: {Typography.WEIGHT_SEMIBOLD};
                color: {Colors.TEXT_PRIMARY};
                background: transparent;
                border: none;
                letter-spacing: 0.3px;
                text-transform: none;
                padding: 0;
            }}
            """
        )
        text_col.addWidget(self._title_label)

        self._subtitle_label = QLabel(subtitle, self)
        self._subtitle_label.setStyleSheet(
            f"""
            QLabel {{
                font-size: {Typography.SIZE_XS}px;
                color: {Colors.TEXT_MUTED};
                background: transparent;
                border: none;
            }}
            """
        )
        self._subtitle_label.setVisible(bool(subtitle))
        text_col.addWidget(self._subtitle_label)

        layout.addLayout(text_col)
        layout.addStretch(1)

        self._actions = QHBoxLayout()
        self._actions.setContentsMargins(0, 0, 0, 0)
        self._actions.setSpacing(Spacing.SM)
        layout.addLayout(self._actions)

    def set_title(self, title: str) -> None:
        self._title = title
        self._title_label.setText(title)

    def set_subtitle(self, subtitle: str) -> None:
        self._subtitle = subtitle
        self._subtitle_label.setText(subtitle)
        self._subtitle_label.setVisible(bool(subtitle))

    def add_action(self, widget: QWidget) -> None:
        """Append a trailing widget (button, combo, …) to the right side."""
        self._actions.addWidget(widget)

    def add_spacer(self, w: int = 8) -> None:
        self._actions.addSpacing(w)


# ──────────────────────────────────────────────────────────────────────────
#  FilterBar — unified search + contextual controls row
# ──────────────────────────────────────────────────────────────────────────


class FilterBar(QFrame):
    """Single, consistent toolbar row: [leading actions] [search (stretch)] [trailing actions].

    Matching the header's surface treatment so a tab always shows the same
    material for its two horizontal bars.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FilterBar")
        self.setStyleSheet(
            f"""
            QFrame#FilterBar {{
                background: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: {Radius.MD}px;
            }}
            """
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        layout.setSpacing(Spacing.SM)
        self._leading = QHBoxLayout()
        self._leading.setContentsMargins(0, 0, 0, 0)
        self._leading.setSpacing(Spacing.SM)
        self._search_slot = QHBoxLayout()
        self._search_slot.setContentsMargins(0, 0, 0, 0)
        self._search_slot.setSpacing(Spacing.SM)
        self._trailing = QHBoxLayout()
        self._trailing.setContentsMargins(0, 0, 0, 0)
        self._trailing.setSpacing(Spacing.SM)
        layout.addLayout(self._leading)
        layout.addLayout(self._search_slot, 1)
        layout.addLayout(self._trailing)

    def add_leading(self, widget: QWidget) -> None:
        self._leading.addWidget(widget)

    def set_search(self, widget: QWidget) -> None:
        """Place the primary search field in the stretchy centre slot."""
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._search_slot.addWidget(widget)

    def add_trailing(self, widget: QWidget) -> None:
        self._trailing.addWidget(widget)


# ──────────────────────────────────────────────────────────────────────────
#  TabShell — the shared vertical skeleton for every library tab
# ──────────────────────────────────────────────────────────────────────────


class TabShell(QFrame):
    """Vertical skeleton shared by all library tabs.

    ┌──────────────────────────────────────────────┐
    │ SectionHeader (title + icon + actions)         │
    ├──────────────────────────────────────────────┤
    │ FilterBar (search + contextual controls)       │
    ├──────────────────────────────────────────────┤
    │ content  (the tab's splitter / lists)          │
    └──────────────────────────────────────────────┘

    Use :meth:`set_content` to drop in the tab-specific body (usually a
    horizontal QSplitter holding the left/right lists).
    """

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        icon_name: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")

        self.header = SectionHeader(title, subtitle, icon_name, self)
        self.filter_bar = FilterBar(self)

        self._content = QWidget(self)
        self._content.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)
        layout.addWidget(self.header)
        layout.addWidget(self.filter_bar)
        layout.addWidget(self._content, 1)

    @property
    def header_(self) -> SectionHeader:  # pragma: no cover - convenience alias
        return self.header

    def set_content(self, widget: QWidget) -> None:
        """Replace the body widget (clears any previous one)."""
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self._content_layout.addWidget(widget, 1)


# ──────────────────────────────────────────────────────────────────────────
#  DialogHeader — unified title bar for every QDialog
# ──────────────────────────────────────────────────────────────────────────


class DialogHeader(QFrame):
    """Consistent dialog title bar: [icon] Title / subtitle, matching the
    SectionHeader material so every dialog reads as the same family."""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        icon_name: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("DialogHeader")
        self.setFixedHeight(64)
        self.setStyleSheet(
            f"""
            QFrame#DialogHeader {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {Colors.BG_TERTIARY},
                    stop:1 {Colors.BG_SECONDARY}
                );
                border-bottom: 1px solid {Colors.BORDER_DEFAULT};
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(14)

        if icon_name:
            icon_lbl = QLabel(self)
            icon_lbl.setPixmap(app_icon(icon_name, Colors.ACCENT_PRIMARY).pixmap(26, 26))
            icon_lbl.setStyleSheet("background: transparent; border: none;")
            layout.addWidget(icon_lbl)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)

        title_lbl = QLabel(title, self)
        title_lbl.setStyleSheet(
            f"""
            QLabel {{
                font-size: 17px;
                font-weight: {Typography.WEIGHT_BOLD};
                color: {Colors.TEXT_PRIMARY};
                background: transparent;
                border: none;
            }}
            """
        )
        col.addWidget(title_lbl)

        self._subtitle_lbl = QLabel(subtitle, self)
        self._subtitle_lbl.setStyleSheet(
            f"""
            QLabel {{
                font-size: {Typography.SIZE_SM}px;
                color: {Colors.TEXT_SECONDARY};
                background: transparent;
                border: none;
            }}
            """
        )
        self._subtitle_lbl.setVisible(bool(subtitle))
        col.addWidget(self._subtitle_lbl)

        layout.addLayout(col, 1)

    def set_subtitle(self, subtitle: str) -> None:
        self._subtitle_lbl.setText(subtitle)
        self._subtitle_lbl.setVisible(bool(subtitle))


# ──────────────────────────────────────────────────────────────────────────
#  AppTitleBar — common window title bar shared by the main window
# ──────────────────────────────────────────────────────────────────────────


class AppTitleBar(QFrame):
    """The single, unified title bar pinned at the top of the main window.

    Shows the app identity (logo + name + tagline) on the left and a cluster
    of global action buttons on the right. Its material matches SectionHeader
    / TopBar so the whole application reads as one design language.
    """

    settingsRequested = pyqtSignal()
    shortcutsRequested = pyqtSignal()
    aboutRequested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AppTitleBar")
        self.setFixedHeight(56)
        self.setStyleSheet(
            f"""
            QFrame#AppTitleBar {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {Colors.BG_TERTIARY},
                    stop:1 {Colors.BG_SECONDARY}
                );
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: {Radius.LG}px;
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, 0, Spacing.MD, 0)
        layout.setSpacing(Spacing.SM)

        logo = QLabel(self)
        logo.setPixmap(app_icon("monitor.svg", Colors.ACCENT_PRIMARY).pixmap(22, 22))
        logo.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(logo)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(1)
        title = QLabel("Project-On", self)
        title.setStyleSheet(
            f"""
            QLabel {{
                font-size: {Typography.SIZE_LG}px;
                font-weight: {Typography.WEIGHT_BOLD};
                color: {Colors.TEXT_PRIMARY};
                background: transparent;
                border: none;
            }}
            """
        )
        tagline = QLabel("Gestion de présentation", self)
        tagline.setStyleSheet(
            f"""
            QLabel {{
                font-size: {Typography.SIZE_XS}px;
                color: {Colors.TEXT_MUTED};
                background: transparent;
                border: none;
            }}
            """
        )
        col.addWidget(title)
        col.addWidget(tagline)
        layout.addLayout(col)
        layout.addStretch(1)

        self._btn_settings = self._make_button("settings.svg", "Paramètres", self.settingsRequested)
        self._btn_shortcuts = self._make_button("keyboard.svg", "Raccourcis", self.shortcutsRequested)
        self._btn_about = self._make_button("info.svg", "À propos", self.aboutRequested)
        layout.addWidget(self._btn_shortcuts)
        layout.addWidget(self._btn_about)
        layout.addWidget(self._btn_settings)

    def _make_button(self, icon_name: str, tooltip: str, signal) -> QPushButton:
        btn = QPushButton(self)
        btn.setIcon(app_icon(icon_name, Colors.TEXT_SECONDARY))
        btn.setIconSize(__import__("PyQt6.QtCore", fromlist=["QSize"]).QSize(16, 16))
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(38, 38)
        btn.setObjectName("IconButton")
        btn.clicked.connect(signal.emit)
        return btn


# ──────────────────────────────────────────────────────────────────────────
#  vertical_split — full-width stacked splitter (no overlap, tab-owned ratio)
# ──────────────────────────────────────────────────────────────────────────


def vertical_split(
    top: QWidget,
    bottom: QWidget,
    top_stretch: int = 1,
    bottom_stretch: int = 2,
    parent: QWidget | None = None,
) -> QWidget:
    """Stack ``top`` over ``bottom`` filling the FULL column height.

    Uses a QVBoxLayout with explicit stretch factors (more reliable than a
    QSplitter, which honours each widget's minimumSizeHint over the stretch and
    would starve a small list). The list widgets are Expanding with
    minimumHeight(0), so they fill their share without overflowing/covering the
    panel below. Both panels keep the FULL column width.

    A thin styled separator line between the two keeps the visual "divider"
    language consistent with the main window's draggable splitter.

    The stretch factors are owned per-tab so the ratio can differ by tab.
    """
    container = QWidget(parent)
    container.setStyleSheet("background: transparent;")
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    layout.addWidget(top, top_stretch)
    layout.addWidget(_divider_line(), 0)
    layout.addWidget(bottom, bottom_stretch)
    return container


def _divider_line() -> QFrame:
    """Thin horizontal separator matching the app's border language."""
    line = QFrame()
    line.setFixedHeight(1)
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f"background: {Colors.BORDER_SUBTLE}; border: none;")
    return line
