from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.bible_tab import BibleTab
from app.ui.expose_tab import ExposeTab
from app.ui.hymns_tab import HymnsTab
from app.ui.sermons_tab import SermonsTab
from app.ui.settings_tab import SettingsTab
from app.ui.sidebar import Sidebar
from app.ui.theme import Spacing
from app.utils.translations import tr


class LibraryPanel(QFrame):
    slideRequested = pyqtSignal(str, str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("LibraryPanel")
        self.setStyleSheet("background: transparent;")

        self.sidebar = Sidebar(self)
        self.sidebar.addTab(tr("bible"), "book.svg")
        self.sidebar.addTab(tr("hymns"), "music.svg")
        self.sidebar.addTab(tr("sermons"), "mic.svg")
        self.sidebar.addTab("Expose", "file-text.svg")
        self.sidebar.addTab(tr("settings"), "settings.svg")

        self.tab_bar = self.sidebar

        self.stack = QStackedWidget(self)
        self.stack.setStyleSheet("background: transparent;")

        self.bible_tab = BibleTab(self)
        self.hymns_tab = HymnsTab(self)
        self.sermons_tab = SermonsTab(self)
        self.expose_tab = ExposeTab(self)
        self.settings_tab = SettingsTab(self)

        self.stack.addWidget(self.bible_tab)
        self.stack.addWidget(self.hymns_tab)
        self.stack.addWidget(self.sermons_tab)
        self.stack.addWidget(self.expose_tab)
        self.stack.addWidget(self.settings_tab)

        self.header = QLabel(tr("bible"), self)
        self.header.hide()

        self.tabs = self.stack

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.sidebar)

        content_container = QWidget(self)
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(
            Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM
        )
        content_layout.setSpacing(Spacing.MD)
        content_layout.addWidget(self.stack)

        layout.addWidget(content_container, 1)

        self.sidebar.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        tab_names = [tr("bible"), tr("hymns"), tr("sermons"), "Expose", tr("settings")]
        if 0 <= index < len(tab_names):
            self.header.setText(tab_names[index])
