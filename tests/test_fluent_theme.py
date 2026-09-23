"""Fluent (Windows 11) theme foundations."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from app.ui import theme, window_effects
from app.ui.theme import Colors, Radius


@pytest.fixture(autouse=True)
def _restore_theme():
    yield
    theme.set_window_backdrop(False)
    theme.set_theme("dark")


def test_backdrop_survives_theme_switch() -> None:
    theme.set_window_backdrop(True)
    theme.set_theme("light")
    assert Colors.WINDOW_BG == "transparent"
    # Opaque tokens are unaffected by the backdrop.
    assert Colors.BG_PRIMARY == "#f3f3f3"

    theme.set_window_backdrop(False)
    assert Colors.WINDOW_BG == "#f3f3f3"


def test_fluent_corner_radii() -> None:
    assert Radius.SM == 4  # controls
    assert Radius.LG == 8  # cards and overlays


@pytest.mark.parametrize("name", ["dark", "light"])
def test_stylesheet_images_exist(name: str) -> None:
    QApplication.instance() or QApplication([])
    theme.set_theme(name)
    qss = theme.build_app_stylesheet()
    urls = re.findall(r'url\("([^"]+)"\)', qss)
    assert urls, "check mark and combo arrow are expected"
    for url in urls:
        assert Path(url).is_file(), url


def test_mica_is_skipped_on_older_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(window_effects, "_windows_build", lambda: 19045)
    assert not window_effects.mica_supported()
    assert window_effects.apply_mica(QWidget()) is False
