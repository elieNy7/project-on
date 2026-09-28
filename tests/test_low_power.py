"""Mode PC modeste : sorties allégées."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.ui.main_window import low_power_obs_overrides, low_power_projection_overrides
from app.utils.settings import AppSettings, ObsSettings


def test_overrides() -> None:
    assert low_power_projection_overrides({"bg_mode": "video"}) == {
        "animation_enabled": False, "animation_type": "none", "ken_burns": False,
        "bg_mode": "color",
    }
    assert "bg_mode" not in low_power_projection_overrides({"bg_mode": "image"})
    assert low_power_obs_overrides()["bg_blur"] is False


def test_setting_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settings = AppSettings()
    settings.appearance.low_power = True
    settings.save(path)
    assert AppSettings.load(path).appearance.low_power is True


def test_obs_controller_serves_light_config(monkeypatch) -> None:
    from app.utils.obs_controller import ObsController

    served = []
    controller = ObsController.__new__(ObsController)
    controller._settings = ObsSettings()

    class _Server:
        def update_config(self, config):
            served.append(config)

    controller._web_server = _Server()
    controller.set_low_power(True)
    assert served[-1]["animation_enabled"] is False and served[-1]["bg_blur"] is False
    controller.set_low_power(False)
    assert served[-1]["animation_enabled"] is True


def test_main_window_applies_low_power(tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from app.database.connection import Database, DatabaseConfig
    from app.ui.main_window import MainWindow

    monkeypatch.setattr(MainWindow, "_start_obs_output", lambda self: None)
    monkeypatch.setattr(MainWindow, "_poll_obs_status", lambda self: None)
    db = Database(DatabaseConfig(db_path=tmp_path / "m.db"))
    db.initialize()
    window = MainWindow(db=db)
    try:
        window._settings.projection.animation_enabled = True
        window._settings.appearance.low_power = True
        window._apply_low_power()
        cfg = json.loads((window._presentation_dir / "config.json").read_text("utf-8"))
        assert cfg["animation_enabled"] is False and cfg["ken_burns"] is False
        obs = json.loads((window._presentation_dir / "obs-config.json").read_text("utf-8"))
        assert obs["animation_enabled"] is False
    finally:
        window.close()
