from __future__ import annotations

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel

from app.ui.icons import app_icon
from app.ui.theme import Colors, Spacing, Typography


class _StatusPill(QFrame):
    """Small rounded indicator pill with icon + text."""

    def __init__(self, icon_name: str, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            _StatusPill {{
                background: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 9px;
                padding: 0 2px;
            }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 8, 2)
        lay.setSpacing(4)

        self._icon = QLabel(self)
        self._icon.setPixmap(app_icon(icon_name).pixmap(QSize(11, 11)))
        self._icon.setStyleSheet("background: transparent;")
        lay.addWidget(self._icon)

        self._label = QLabel(text, self)
        self._label.setStyleSheet(f"""
            font-size: {Typography.SIZE_XS}px;
            color: {Colors.TEXT_MUTED};
            background: transparent;
            font-weight: 600;
        """)
        lay.addWidget(self._label)

    def set_text(self, text: str) -> None:
        self._label.setText(text)

    def set_icon(self, icon_name: str) -> None:
        self._icon.setPixmap(app_icon(icon_name).pixmap(QSize(11, 11)))

    def set_accent(self, color: str) -> None:
        self._label.setStyleSheet(f"""
            font-size: {Typography.SIZE_XS}px;
            color: {color};
            background: transparent;
            font-weight: 600;
        """)


class StatusBar(QFrame):
    """Minimal, professional status bar."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusBar")
        self.setFixedHeight(30)
        self.setStyleSheet(f"""
            QFrame#StatusBar {{
                background: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 10px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, 0, Spacing.SM, 0)
        layout.setSpacing(Spacing.SM)

        # Live / Hidden indicator
        self._live_pill = _StatusPill("eye.svg", "LIVE", self)
        self._live_pill.set_accent(Colors.ACCENT_SUCCESS)
        layout.addWidget(self._live_pill)

        # Current source type
        self._source_pill = _StatusPill("book.svg", "", self)
        layout.addWidget(self._source_pill)
        self._source_pill.hide()

        # Current slide info
        self._slide_label = QLabel("", self)
        self._slide_label.setStyleSheet(f"""
            font-size: 10px;
            color: {Colors.TEXT_MUTED};
            background: transparent;
        """)
        layout.addWidget(self._slide_label)

        layout.addStretch(1)

        # OBS connection indicator
        self._obs_pill = _StatusPill("obs.svg", "OBS", self)
        self._obs_pill.set_accent(Colors.TEXT_DISABLED)
        self._obs_pill.setToolTip("OBS : non connect\u00e9")
        layout.addWidget(self._obs_pill)

        # Separator
        sep2 = QLabel("\u00b7", self)
        sep2.setStyleSheet(
            f"color: {Colors.TEXT_DISABLED}; background: transparent; font-size: 9px;"
        )
        layout.addWidget(sep2)

        # Slide counter
        self._counter_label = QLabel("", self)
        self._counter_label.setStyleSheet(f"""
            font-size: 10px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            color: {Colors.TEXT_MUTED};
            background: {Colors.BG_TERTIARY};
            border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: 8px;
            padding: 1px 8px;
        """)
        layout.addWidget(self._counter_label)

    # ── Public API ──

    _SOURCE_ICONS = {
        "bible": ("book.svg", Colors.SRC_BIBLE, "Bible"),
        "sermon": ("mic.svg", Colors.SRC_SERMON, "Sermon"),
        "hymn": ("music.svg", Colors.SRC_HYMN, "Cantique"),
        "custom": ("file-plus.svg", Colors.SRC_CUSTOM, "Personnalis\u00e9"),
        "image": ("monitor.svg", Colors.SRC_IMAGE, "Image"),
    }

    def update_slide(self, source: str, reference: str, row: int, total: int) -> None:
        """Update all status bar elements from the current slide."""
        info = self._SOURCE_ICONS.get(
            source, ("file-plus.svg", Colors.TEXT_MUTED, source)
        )
        icon_name, color, label = info
        self._source_pill.set_icon(icon_name)
        self._source_pill.set_text(label)
        self._source_pill.set_accent(color)
        self._source_pill.show()

        ref_display = reference if len(reference) <= 60 else reference[:57] + "..."
        self._slide_label.setText(ref_display)

        if total > 0 and row >= 0:
            self._counter_label.setText(f"{row + 1} / {total}")
        else:
            self._counter_label.setText("")

    def set_hidden(self, hidden: bool) -> None:
        if hidden:
            self._live_pill.set_icon("eye-off.svg")
            self._live_pill.set_text("MASQU\u00c9")
            self._live_pill.set_accent(Colors.ACCENT_DANGER)
        else:
            self._live_pill.set_icon("eye.svg")
            self._live_pill.set_text("LIVE")
            self._live_pill.set_accent(Colors.ACCENT_SUCCESS)

    def set_obs_connected(self, connected: bool) -> None:
        if connected:
            self._obs_pill.set_accent(Colors.ACCENT_SUCCESS)
            self._obs_pill.setToolTip("OBS : connect\u00e9")
        else:
            self._obs_pill.set_accent(Colors.TEXT_DISABLED)
            self._obs_pill.setToolTip("OBS : non connect\u00e9")

    def clear_slide(self) -> None:
        self._source_pill.hide()
        self._slide_label.setText("")
        self._counter_label.setText("")
