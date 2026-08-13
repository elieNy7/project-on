from __future__ import annotations

import json
import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication, QLabel

from app.ui.obs_output_settings_dialog import (
    ObsOutputSettingsDialog,
    ObsPreviewWidget,
)
from app.ui.preview_panel import PreviewPanel
from app.ui.projection_window import ProjectionWindow
from app.ui.settings_dialog import ProjectionSettingsDialog
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
        assert config["uniform_text_size"] is True
        assert config["min_text_size"] == 22
        assert config["max_lines"] == 5
        assert config["reference_style"] == "plain"
        assert config["background_dimmer"] == 0.42


def test_local_projection_export_honours_operator_settings() -> None:
    for mode in LAYOUT_MODES:
        config = ProjectionSettings(
            layout_mode=mode,
            display_screen="DISPLAY2",
            safe_margin=48,
            panel_side="right",
            auto_fit=False,
            uniform_text_size=True,
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
        assert config["uniform_text_size"] is True
        assert config["min_text_size"] == 20
        assert config["max_lines"] == 7
        assert config["background_dimmer"] == 0.4
        assert config["panel_enabled"] is True
        assert config["panel_opacity"] == 0.78
        assert config["panel_radius"] == 30
        assert config["position"] == "center"
        assert config["reference_position"] == "bottom"


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
    assert settings.projection.auto_fit is False
    assert settings.projection.uniform_text_size is True
    assert settings.obs.output.uniform_text_size is True


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


def test_zero_value_controls_survive_export_and_reload(tmp_path) -> None:
    settings = AppSettings(
        projection=ProjectionSettings(
            padding=0,
            shadow_blur=0,
            panel_opacity=0.0,
            bg_gradient_angle=0,
            animation_duration=0,
            uniform_text_size=False,
        )
    )
    settings.obs.output = ObsOutputSettings(
        padding_horizontal=0,
        padding_vertical=0,
        border_radius=0,
        shadow_blur=0,
        stroke_width=0,
        bg_blur_amount=0,
        bg_gradient_angle=0,
        animation_duration=0,
        uniform_text_size=False,
    )
    path = tmp_path / "settings.json"
    settings.save(path)
    loaded = AppSettings.load(path)

    local = loaded.projection.to_presentation_config()
    obs = loaded.obs.output.to_obs_config()
    assert local["padding"] == 0
    assert local["shadow_blur"] == 0
    assert local["panel_opacity"] == 0.0
    assert local["bg_gradient_angle"] == 0
    assert local["animation_duration"] == 0
    assert local["auto_fit"] is False
    assert local["uniform_text_size"] is True
    assert obs["padding_horizontal"] == 0
    assert obs["padding_vertical"] == 0
    assert obs["border_radius"] == 0
    assert obs["shadow_blur"] == 0
    assert obs["stroke_width"] == 0
    assert obs["bg_blur_amount"] == 0
    assert obs["bg_gradient_angle"] == 0
    assert obs["animation_duration"] == 0
    assert obs["uniform_text_size"] is False


def test_obs_preview_main_text_size_has_visible_effect() -> None:
    app = QApplication.instance() or QApplication([])
    settings = ObsOutputSettings(text_size=32, auto_fit=False)
    preview = ObsPreviewWidget(settings)
    preview.resize(960, 540)

    image = QImage(preview.size(), QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    preview.render(painter)
    painter.end()
    small = preview._last_effective_text_size

    preview.update_settings(ObsOutputSettings(text_size=96, auto_fit=False))
    painter = QPainter(image)
    preview.render(painter)
    painter.end()
    large = preview._last_effective_text_size

    assert large >= small * 2
    preview.close()
    app.processEvents()


def test_local_projection_main_text_size_has_visible_effect(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = ProjectionWindow(tmp_path)
    window.resize(1280, 720)
    slide = {"text": "La foi transforme notre vie.", "reference": "Romains 10:17"}

    small_cfg = ProjectionSettings(
        text_size=32,
        auto_fit=False,
        content_width=88,
        max_width=88,
    ).to_presentation_config()
    window._apply_config(small_cfg)
    window._render_slide_content(slide)
    small = window.text_label.font().pixelSize()

    large_cfg = ProjectionSettings(
        text_size=84,
        auto_fit=False,
        content_width=88,
        max_width=88,
    ).to_presentation_config()
    window._apply_config(large_cfg)
    window._render_slide_content(slide)
    large = window.text_label.font().pixelSize()

    # The readability floor may lift the small size (never too small on a
    # projector), but the configured size must still have a visible effect.
    assert small >= 32
    assert large == 84
    assert small < large
    window.close()
    app.processEvents()


def test_local_projection_uses_safe_area_instead_of_inner_padding(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = ProjectionWindow(tmp_path)
    window.resize(1280, 720)

    no_padding = ProjectionSettings(
        layout_mode="lower_third", padding=0
    ).to_presentation_config()
    window._apply_config(no_padding)
    margins = window._shell_layout.contentsMargins()
    assert (margins.left(), margins.top()) == (0, 0)

    custom_padding = ProjectionSettings(padding=64).to_presentation_config()
    window._apply_config(custom_padding)
    margins = window._shell_layout.contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
        0,
        0,
        0,
        0,
    )
    window.close()
    app.processEvents()


def test_local_projection_size_is_constant_for_every_text_length(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = ProjectionWindow(tmp_path)
    window.resize(1280, 720)
    config = ProjectionSettings(
        text_size=64,
        # Legacy variable-fit values must no longer override the operator's
        # explicit local projection size.
        auto_fit=True,
        uniform_text_size=False,
        min_text_size=18,
        max_lines=4,
    ).to_presentation_config()
    window._apply_config(config)

    sizes = []
    for text in (
        "Dieu est amour.",
        " ".join(["Cette longue slide doit conserver exactement la même taille."] * 14),
    ):
        window._render_slide_content({"text": text, "reference": "Référence"})
        sizes.append(window.text_label.font().pixelSize())

    assert sizes == [64, 64]
    window.close()
    app.processEvents()


def test_local_projection_honours_fit_settings_and_validates_layout(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = ProjectionWindow(tmp_path)
    window.resize(1280, 720)
    config = ProjectionSettings(
        text_size=64,
        auto_fit=True,
        uniform_text_size=False,
        min_text_size=18,
        max_lines=4,
    ).to_presentation_config()
    window._apply_config(config)
    assert window._config["layout_mode"] == "fullscreen"
    assert window._config["position"] == "center"
    assert window._config["auto_fit"] is False
    assert window._config["uniform_text_size"] is True
    assert window._config["panel_enabled"] is False

    # Invalid legacy values fall back to safe defaults instead of breaking.
    window._apply_config(
        {**config, "layout_mode": "unknown", "position": "nowhere"}
    )
    assert window._config["layout_mode"] == "fullscreen"
    assert window._config["position"] == "center"
    window.close()
    app.processEvents()


def test_local_projection_never_breaks_words_and_centers_the_content_block(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    window = ProjectionWindow(tmp_path)
    window.resize(1280, 720)
    config = ProjectionSettings(
        text_size=72,
        content_width=60,
        align="right",
        text_shadow=False,
    ).to_presentation_config()
    window._apply_config(config)
    window._render_slide_content(
        {
            "text": "La projection professionnellement lisible respecte chaque mot.",
            "reference": "Référence complète",
        }
    )

    rendered_text = window.text_label.text()
    assert "professionnellement" in rendered_text
    assert "professionnelle\nment" not in rendered_text
    assert window.text_label.textFormat() == Qt.TextFormat.PlainText
    assert window.text_label.alignment() & Qt.AlignmentFlag.AlignRight
    assert window.text_label.alignment() & Qt.AlignmentFlag.AlignVCenter
    assert window.text_label.graphicsEffect() is None
    assert window.ref_label.graphicsEffect() is None
    assert config["text_shadow"] is False
    spacer_count = sum(
        1
        for index in range(window._content_layout.count())
        if window._content_layout.itemAt(index).spacerItem() is not None
    )
    assert spacer_count == 2

    local_style = (PROJECT_ROOT / "presentation" / "style.css").read_text(
        encoding="utf-8"
    )
    assert "overflow-wrap: anywhere" not in local_style
    assert "overflow-wrap: normal" in local_style
    assert "hyphens: none" in local_style
    window.close()
    app.processEvents()


def test_operator_preview_keeps_uniform_size_between_slides() -> None:
    app = QApplication.instance() or QApplication([])
    settings = AppSettings(
        projection=ProjectionSettings(
            text_size=60,
            auto_fit=True,
            uniform_text_size=True,
        )
    )
    preview = PreviewPanel(settings=settings)

    sizes = []
    for text in (
        "Texte court",
        " ".join(["Texte volontairement beaucoup plus long"] * 30),
    ):
        preview.set_slide("Référence", text)
        match = re.search(r"font-size:\s*(\d+)px", preview.slide_view.styleSheet())
        assert match is not None
        sizes.append(int(match.group(1)))

    assert sizes[0] == sizes[1]
    preview.close()
    app.processEvents()


def test_settings_dialogs_expose_auto_grow_as_the_default() -> None:
    app = QApplication.instance() or QApplication([])
    local_dialog = ProjectionSettingsDialog(ProjectionSettings())
    obs_dialog = ObsOutputSettingsDialog(ObsOutputSettings())

    assert local_dialog._uniform_text_size.isChecked() is True
    assert local_dialog._uniform_text_size.isEnabled() is False
    assert local_dialog._auto_fit.isEnabled() is False
    assert local_dialog._auto_fit.isChecked() is False
    assert local_dialog.read_settings().uniform_text_size is True
    assert obs_dialog._uniform_text_size.isChecked() is True
    assert obs_dialog._auto_fit.isEnabled() is False
    assert obs_dialog.get_settings().uniform_text_size is True

    local_labels = {
        label.text().strip() for label in local_dialog.findChildren(QLabel)
    }
    assert "Composition" not in local_labels
    assert "Côté du panneau" not in local_labels
    assert "Marges intérieures" not in local_labels
    assert "Placement du bloc" not in local_labels
    assert "Position de la référence" not in local_labels
    assert "Afficher un panneau derrière le texte" not in local_labels
    local_settings = local_dialog.read_settings()
    assert local_settings.layout_mode == "fullscreen"
    assert local_settings.position == "center"
    assert local_settings.auto_fit is False
    assert local_settings.panel_enabled is False

    local_dialog.close()
    obs_dialog.close()
    app.processEvents()


def test_obs_frontend_preserves_zero_value_controls() -> None:
    script = (PROJECT_ROOT / "presentation" / "obs-script.js").read_text(
        encoding="utf-8"
    )

    assert "cfg.padding_horizontal ?? 52" in script
    assert "cfg.padding_vertical ?? 30" in script
    assert "cfg.border_radius ?? 14" in script
    assert "cfg.shadow_blur ?? 8" in script
    assert "Math.max(12, Math.round(baseTextSize))" in script
    assert "Number(currentConfig.min_text_size || 24)" in script
    assert "currentConfig.uniform_text_size !== false" in script

    local_script = (PROJECT_ROOT / "presentation" / "script.js").read_text(
        encoding="utf-8"
    )
    assert "content length never changes size" in local_script
    assert "shellEl.scrollHeight" not in local_script
