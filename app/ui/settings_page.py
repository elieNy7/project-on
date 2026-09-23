"""Unified settings page (Windows 11 Settings layout).

A section list on the left, the section on the right. Sections host the
existing settings screens in embedded mode: there is no Apply / Cancel,
every change takes effect immediately (the main window saves it).
Each section is rebuilt from the current settings whenever it is shown, so
it never displays stale values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.icons import app_icon
from app.ui.navigation_rail import RailItem
from app.ui.theme import (
    Colors,
    Radius,
    Typography,
    get_icon_button_style,
    get_scroll_area_style,
)

HOME = "home"

_embedded_classes: dict[type, type] = {}


def embed_dialog(cls: type[QDialog], *args, **kwargs) -> QDialog:
    """Instantiate a settings dialog as a plain child widget.

    Accept / reject become no-ops (Enter or Escape must not hide a page), and
    the dialog is built in ``embedded`` mode, without Cancel / Save buttons.
    """
    embedded_cls = _embedded_classes.get(cls)
    if embedded_cls is None:
        embedded_cls = type(
            f"Embedded{cls.__name__}",
            (cls,),
            {
                "accept": lambda self: None,
                "reject": lambda self: None,
                "done": lambda self, _result: None,
            },
        )
        _embedded_classes[cls] = embedded_cls
    dialog = embedded_cls(*args, embedded=True, **kwargs)
    dialog.setWindowFlags(Qt.WindowType.Widget)
    dialog.setMinimumSize(0, 0)
    dialog.setSizeGripEnabled(False)
    return dialog


def watch_inputs(root: QWidget, callback: Callable[[], None], delay_ms: int = 700) -> QTimer:
    """Call ``callback`` once the operator stops editing any input of ``root``.

    Typing "8080" in a port field restarts nothing four times: changes are
    coalesced until the fields have been idle for ``delay_ms``.
    """
    timer = QTimer(root)
    timer.setSingleShot(True)
    timer.setInterval(delay_ms)
    timer.timeout.connect(callback)
    for w in root.findChildren(QLineEdit):
        w.textEdited.connect(timer.start)
        w.editingFinished.connect(timer.start)
    for w in root.findChildren(QAbstractSpinBox):
        if hasattr(w, "valueChanged"):
            w.valueChanged.connect(timer.start)
    for w in root.findChildren(QComboBox):
        w.currentIndexChanged.connect(timer.start)
    for w in root.findChildren(QSlider):
        w.valueChanged.connect(timer.start)
    for w in root.findChildren(QAbstractButton):
        if w.isCheckable():
            w.toggled.connect(timer.start)
    return timer


@dataclass
class _Section:
    key: str
    label: str
    icon: str
    factory: Callable[[], QWidget]
    item: RailItem


class InfoBar(QFrame):
    """Fluent InfoBar: short non-blocking message above the section."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("InfoBar")
        self.setStyleSheet(
            f"""
            QFrame#InfoBar {{
                background: {Colors.ACCENT_SECONDARY_GLOW};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.SM}px;
            }}
            """
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 6, 8)
        icon = QLabel(self)
        icon.setPixmap(app_icon("info.svg", Colors.ACCENT_SECONDARY).pixmap(16, 16))
        layout.addWidget(icon)
        self._text = QLabel("", self)
        self._text.setWordWrap(True)
        self._text.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: {Typography.SIZE_FILTER}px; background: transparent;"
        )
        layout.addWidget(self._text, 1)
        close = QPushButton(self)
        close.setIcon(app_icon("x-circle.svg", Colors.TEXT_SECONDARY))
        close.setStyleSheet(get_icon_button_style(26))
        close.setToolTip("Fermer")
        close.clicked.connect(self.hide)
        layout.addWidget(close)
        self.hide()

    def show_message(self, text: str) -> None:
        self._text.setText(text)
        self.show()


class SettingsPage(QWidget):
    """Section list + section host. ``home`` is the overview page."""

    sectionShown = Signal(str)

    def __init__(self, home: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsPage")
        self._sections: dict[str, _Section] = {}
        self._current: str | None = None
        self._current_widget: QWidget | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        nav = QWidget(self)
        nav.setFixedWidth(196)
        self._nav = QVBoxLayout(nav)
        self._nav.setContentsMargins(0, 4, 0, 4)
        self._nav.setSpacing(2)
        title = QLabel("Paramètres", nav)
        title.setStyleSheet(
            f"font-size: {Typography.SIZE_TITLE}px; font-weight: {Typography.WEIGHT_SEMIBOLD};"
            f" color: {Colors.TEXT_PRIMARY}; padding: 4px 12px 10px 12px; background: transparent;"
        )
        self._nav.addWidget(title)
        self._nav_items = QVBoxLayout()
        self._nav_items.setSpacing(2)
        self._nav.addLayout(self._nav_items)
        self._nav.addStretch(1)
        layout.addWidget(nav)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(8)
        self.info_bar = InfoBar(self)
        right.addWidget(self.info_bar)
        self._stack = QStackedWidget(self)
        self._stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._stack.addWidget(home)
        # Sections scroll inside the page: a wide screen (OBS lower third)
        # must never squeeze the live monitors next to the settings.
        self._host = QScrollArea(self._stack)
        self._host.setWidgetResizable(True)
        self._host.setFrameShape(QFrame.Shape.NoFrame)
        self._host.setStyleSheet(get_scroll_area_style())
        self._stack.addWidget(self._host)
        right.addWidget(self._stack, 1)
        layout.addLayout(right, 1)

        self._home = home
        self.register(HOME, "Accueil", "layout-dashboard.svg", lambda: home)
        self.show_section(HOME)

    # ── Sections ──

    def register(self, key: str, label: str, icon: str, factory: Callable[[], QWidget]) -> None:
        item = RailItem(label, icon, self)
        item.clicked.connect(lambda _c=False, k=key: self.show_section(k))
        self._nav_items.addWidget(item)
        self._sections[key] = _Section(key, label, icon, factory, item)

    def keys(self) -> list[str]:
        return list(self._sections)

    def current_key(self) -> str | None:
        return self._current

    def current_widget(self) -> QWidget | None:
        return self._home if self._current == HOME else self._current_widget

    def show_section(self, key: str) -> None:
        section = self._sections.get(key)
        if section is None:
            return
        for s in self._sections.values():
            s.item.setChecked(s.key == key)
        self.info_bar.hide()
        self._drop_current()
        self._current = key
        if key == HOME:
            self._stack.setCurrentWidget(self._home)
        else:
            widget = section.factory()
            self._current_widget = widget
            self._host.setWidget(widget)
            widget.show()
            self._stack.setCurrentWidget(self._host)
        self.sectionShown.emit(key)

    def refresh_current(self) -> None:
        """Rebuild the visible section from the current settings."""
        if self._current is not None:
            self.show_section(self._current)

    def _drop_current(self) -> None:
        widget, self._current_widget = self._current_widget, None
        if widget is not None:
            self._host.takeWidget()
            widget.hide()
            widget.deleteLater()
