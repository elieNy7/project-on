from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QStackedWidget, QVBoxLayout

from app.ui.bible_tab import BibleTab
from app.ui.expose_tab import ExposeTab
from app.ui.hymns_tab import HymnsTab
from app.ui.media_tab import MediaTab
from app.ui.navigation_rail import NavigationRail
from app.ui.playlist_tab import PlaylistTab
from app.ui.sermons_tab import SermonsTab
from app.ui.settings_tab import SettingsTab
from app.ui.theme import Colors, Radius, Spacing
from app.utils.translations import tr


class LibraryPanel(QFrame):
    slideRequested = Signal(str, str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("LibraryPanel")
        self.setStyleSheet(
            f"""
            QFrame#LibraryPanel {{
                background: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: {Radius.LG}px;
            }}
            """
        )

        # The rail is owned here (tab order = stack order) but laid out by the
        # main window along the window edge, over the backdrop.
        self.rail = NavigationRail()
        self.rail.addTab(tr("bible"), "book.svg")
        self.rail.addTab(tr("hymns"), "music.svg")
        self.rail.addTab(tr("sermons"), "mic.svg")
        self.rail.addTab(tr("expose"), "file-text.svg")
        self.rail.addTab(tr("media"), "image.svg")
        self.rail.addTab(tr("playlist"), "play.svg")
        self.rail.addFooterTab(tr("settings"), "settings.svg")

        # Historical aliases used by controllers and shortcuts.
        self.sidebar = self.rail
        self.tab_bar = self.rail

        self.stack = QStackedWidget(self)
        self.stack.setStyleSheet("background: transparent;")

        self.bible_tab = BibleTab(self)
        self.hymns_tab = HymnsTab(self)
        self.sermons_tab = SermonsTab(self)
        self.expose_tab = ExposeTab(self)
        self.media_tab = MediaTab(self)
        self.playlist_tab = PlaylistTab(self)
        self.settings_tab = SettingsTab(self)

        self.stack.addWidget(self.bible_tab)
        self.stack.addWidget(self.hymns_tab)
        self.stack.addWidget(self.sermons_tab)
        self.stack.addWidget(self.expose_tab)
        self.stack.addWidget(self.media_tab)
        self.stack.addWidget(self.playlist_tab)
        self.stack.addWidget(self.settings_tab)

        # Alias historique utilisé par les contrôleurs existants.
        self.tabs = self.stack

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        layout.setSpacing(Spacing.SM)
        layout.addWidget(self.stack)

        self.rail.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
