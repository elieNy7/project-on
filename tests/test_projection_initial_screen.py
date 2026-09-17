from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QRect
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication

from app.ui.projection_window import ProjectionWindow


class ScreenStub:
    def __init__(self, name: str, geometry: QRect) -> None:
        self._name = name
        self._geometry = geometry

    def name(self) -> str:
        return self._name

    def geometry(self) -> QRect:
        return self._geometry


@pytest.mark.parametrize(
    ("config", "expected_screen"),
    [
        ({"display_screen": "PRIMARY"}, "PRIMARY"),
        ({"display_screen": "PROJECTOR"}, "PROJECTOR"),
        ({"display_screen": "auto"}, "PROJECTOR"),
        ({"display_screen": "DISCONNECTED"}, "PROJECTOR"),
        ({"display_screen": ""}, "PROJECTOR"),
        (None, "PROJECTOR"),
        ("invalid-json", "PROJECTOR"),
    ],
)
def test_first_fullscreen_uses_configured_screen(
    tmp_path, monkeypatch, config, expected_screen
) -> None:
    app = QApplication.instance() or QApplication([])
    primary = ScreenStub("PRIMARY", QRect(0, 0, 1280, 720))
    projector = ScreenStub("PROJECTOR", QRect(1280, 0, 1920, 1080))
    monkeypatch.setattr(QGuiApplication, "screens", lambda: [primary, projector])
    monkeypatch.setattr(QGuiApplication, "primaryScreen", lambda: primary)
    shown_on = []
    monkeypatch.setattr(
        ProjectionWindow,
        "showFullScreen",
        lambda window: shown_on.append(window._active_display_screen),
    )
    if config is not None:
        raw = config if isinstance(config, str) else json.dumps(config)
        (tmp_path / "config.json").write_text(raw, encoding="utf-8")

    window = ProjectionWindow(tmp_path)
    try:
        assert shown_on == [expected_screen]
        assert window._active_display_screen == expected_screen
    finally:
        window.close()
        app.processEvents()
