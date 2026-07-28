from __future__ import annotations

import json
from pathlib import Path

from app.utils.obs_controller import ObsController
from app.utils.settings import AppSettings, ObsOutputSettings, ProjectionSettings


PROJECT_ROOT = Path(__file__).resolve().parents[1]


LAYOUT_MODES = {
    "lower_third",
    "fullscreen",
    "side_panel",
    "subtitle",
    "focus_card",
}


def test_obs_modes_are_exported_with_professional_controls() -> None:
    for mode in LAYOUT_MODES:
        config = ObsOutputSettings(
            layout_mode=mode,
            safe_area_percent=7,
            panel_side="right",
            auto_fit=True,
            min_text_size=22,
            max_lines=5,
            reference_style="plain",
            background_dimmer=0.42,
        ).to_obs_config()

        assert config["layout_mode"] == mode
        assert config["safe_area_percent"] == 7
        assert config["panel_side"] == "right"
        assert config["auto_fit"] is True
        assert config["min_text_size"] == 22
        assert config["max_lines"] == 5
        assert config["reference_style"] == "plain"
        assert config["background_dimmer"] == 0.42


def test_local_modes_are_exported_with_screen_and_readability_controls() -> None:
    for mode in LAYOUT_MODES:
        config = ProjectionSettings(
            layout_mode=mode,
            display_screen="DISPLAY2",
            safe_margin=48,
            panel_side="right",
            auto_fit=False,
            min_text_size=20,
            max_lines=7,
            background_dimmer=0.4,
            panel_enabled=True,
            panel_opacity=0.78,
            panel_radius=30,
        ).to_presentation_config()

        assert config["layout_mode"] == mode
        assert config["display_screen"] == "DISPLAY2"
        assert config["safe_margin"] == 48
        assert config["panel_side"] == "right"
        assert config["auto_fit"] is False
        assert config["min_text_size"] == 20
        assert config["max_lines"] == 7
        assert config["background_dimmer"] == 0.4
        assert config["panel_enabled"] is True
        assert config["panel_opacity"] == 0.78
        assert config["panel_radius"] == 30


def test_invalid_modes_fall_back_without_breaking_old_settings(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "projection": {"layout_mode": "unknown", "text_size": 60},
                "obs": {"output": {"layout_mode": "unknown", "text_size": 54}},
            }
        ),
        encoding="utf-8",
    )

    settings = AppSettings.load(path)

    assert settings.projection.to_presentation_config()["layout_mode"] == "fullscreen"
    assert settings.obs.output.to_obs_config()["layout_mode"] == "lower_third"
    assert settings.projection.text_size == 60
    assert settings.obs.output.text_size == 54


def test_obs_frontend_contains_every_layout_contract() -> None:
    html = (PROJECT_ROOT / "presentation" / "obs.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "presentation" / "obs-script.js").read_text(encoding="utf-8")
    style = (PROJECT_ROOT / "presentation" / "obs-style.css").read_text(encoding="utf-8")

    assert 'class="lt-dimmer"' in html
    assert "new URLSearchParams(window.location.search)" in script
    assert "requestedLayout" in script
    assert "--safe-inset" in script
    assert "--safe-inset" in style

    for mode in LAYOUT_MODES:
        assert f"'layout-{mode}'" in script

    for mode in LAYOUT_MODES - {"lower_third"}:
        assert f".layout-{mode}" in style


def test_obs_scene_urls_can_force_each_layout() -> None:
    controller = object.__new__(ObsController)
    controller._web_server = type(
        "ServerStub",
        (),
        {"get_url": lambda self: "http://127.0.0.1:8080/obs"},
    )()

    urls = controller.get_layout_urls()

    assert set(urls) == LAYOUT_MODES
    for mode, url in urls.items():
        assert url == f"http://127.0.0.1:8080/obs?layout={mode}"
    assert controller.get_web_server_url("invalid") == "http://127.0.0.1:8080/obs"
