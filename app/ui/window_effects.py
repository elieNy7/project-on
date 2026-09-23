"""Windows 11 window chrome: title bars that follow the theme, and Mica.

Title bars are handled by Qt itself once the application colour scheme is set
(Qt >= 6.8 applies DWM dark mode to every framed window). Mica is best effort:
on Windows 10, other platforms, or when a DWM call fails, the main window keeps
its opaque background.
"""

from __future__ import annotations

import ctypes
import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

_log = logging.getLogger(__name__)

_DWMWA_SYSTEMBACKDROP_TYPE = 38
_DWMSBT_MAINWINDOW = 2  # Mica

# First Windows 11 build exposing DWMWA_SYSTEMBACKDROP_TYPE (22H2).
_MICA_MIN_BUILD = 22621


class _Margins(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_int),
        ("right", ctypes.c_int),
        ("top", ctypes.c_int),
        ("bottom", ctypes.c_int),
    ]


def _windows_build() -> int:
    if sys.platform != "win32":
        return 0
    try:
        return int(sys.getwindowsversion().build)
    except Exception:
        return 0


def mica_supported() -> bool:
    """True when the OS can draw a Mica backdrop behind a window."""
    return _windows_build() >= _MICA_MIN_BUILD


def apply_color_scheme(app: QApplication, theme: str) -> None:
    """Make native window chrome (title bars, system dialogs) match the theme."""
    scheme = Qt.ColorScheme.Light if theme == "light" else Qt.ColorScheme.Dark
    try:
        app.styleHints().setColorScheme(scheme)
    except AttributeError:  # Qt < 6.8
        pass


def prepare_for_mica(widget: QWidget) -> None:
    """Must run before the native window exists (i.e. before the first show)."""
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)


def apply_mica(widget: QWidget) -> bool:
    """Put the Mica system backdrop behind ``widget``'s client area.

    Transparent regions of the window (see ``Colors.WINDOW_BG``) then show
    the backdrop; opaque panels are unaffected.
    """
    if not mica_supported():
        return False
    try:
        hwnd = ctypes.c_void_p(int(widget.winId()))
        margins = _Margins(-1, -1, -1, -1)
        dwm = ctypes.windll.dwmapi
        if dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins)) != 0:
            return False
        value = ctypes.c_int(_DWMSBT_MAINWINDOW)
        return (
            dwm.DwmSetWindowAttribute(
                hwnd, _DWMWA_SYSTEMBACKDROP_TYPE, ctypes.byref(value), ctypes.sizeof(value)
            )
            == 0
        )
    except Exception:
        _log.debug("Mica backdrop unavailable", exc_info=True)
        return False
