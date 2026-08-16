from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ObsOutputSettings:
    layout_mode: str = "lower_third"  # lower_third|fullscreen|side_panel|subtitle|focus_card
    font_family: str = "Poppins"
    text_size: int = 48  # pixels
    ref_size: int = 19  # pixels
    align: str = "center"  # center|left|right (text alignment)
    show_reference: bool = True
    position: str = "bottom"  # bottom|top|center
    # Fine positioning (fully adjustable lower third)
    band_align: str = "center"  # left|center|right — horizontal placement of the band
    offset_x: int = 0  # px horizontal offset (negative = left)
    offset_y: int = 0  # px vertical offset (negative = up)
    edge_margin: int = 64  # px distance kept from the screen edges
    safe_area_percent: int = 5  # broadcast-safe inset as percentage of viewport
    panel_side: str = "left"  # left|right, used by side_panel
    # Branding / decorations
    show_kicker: bool = True  # source badge above the text
    show_accent_bar: bool = True  # coloured accent bar under the band
    accent_mode: str = "auto"  # auto (per-source colour) | custom
    accent_color: str = "#74a7f8"  # used when accent_mode == "custom"
    bg_enabled: bool = True  # show/hide background band
    bg_color: str = "rgba(7, 12, 22, 0.90)"
    bg_opacity: float = 0.88  # background-specific opacity 0.0-1.0
    text_color: str = "rgba(255, 255, 255, 0.97)"
    ref_color: str = "rgba(255, 247, 226, 0.94)"
    # Professional text styling
    text_shadow: bool = True
    shadow_color: str = "rgba(0, 0, 0, 0.66)"
    shadow_blur: int = 14  # pixels
    text_stroke: bool = False
    stroke_color: str = "rgba(0, 0, 0, 0.8)"
    stroke_width: int = 1  # pixels
    letter_spacing: int = 0  # pixels
    line_height: float = 1.16  # multiplier
    padding_horizontal: int = 48  # pixels
    padding_vertical: int = 26  # pixels
    max_width: int = 82  # percentage of screen width
    auto_fit: bool = True
    uniform_text_size: bool = True  # keep the configured size across slides
    min_text_size: int = 24
    max_lines: int = 6
    reference_style: str = "badge"  # badge|plain|inline
    background_dimmer: float = 0.36  # full-canvas readability overlay
    border_radius: int = 22  # pixels
    # Animation
    animation_enabled: bool = True
    animation_type: str = "auto"  # auto|none|fade|slide|scale|blur|reveal
    animation_duration: int = 520  # milliseconds
    # Font weight
    font_weight: str = "bold"  # normal|bold|light
    # Professional options
    text_transform: str = "none"  # none|uppercase|capitalize
    bg_blur: bool = True  # backdrop blur (glass effect)
    bg_blur_amount: int = 20  # px
    opacity: float = 1.0  # overall opacity 0.0-1.0
    # Gradient support
    bg_gradient_enabled: bool = True
    bg_color_2: str = "rgba(2, 6, 14, 0.92)"
    bg_gradient_angle: int = 135  # degrees
    bg_mode: str = "color"  # "color" or "image" (mutually exclusive background)
    bg_image: str = ""  # background image path (used only when bg_mode == "image")
    bg_image_fit: str = "cover"  # "cover" (remplir) or "contain" (contenir)
    # Animation refinement
    animation_direction: str = "up"  # up|down|left|right
    animation_style: str = "block"  # block|words (word-by-word broadcast reveal)

    def to_obs_config(self) -> dict[str, Any]:
        layout_mode = str(self.layout_mode or "lower_third").lower()
        if layout_mode not in (
            "lower_third",
            "fullscreen",
            "side_panel",
            "subtitle",
            "focus_card",
        ):
            layout_mode = "lower_third"
        return {
            "version": int(time.time() * 1000),
            "layout_mode": layout_mode,
            "font_family": str(self.font_family or "Poppins").strip(),
            "text_size": int(self.text_size or 48),
            "ref_size": int(self.ref_size or 19),
            "align": (
                self.align if self.align in ("center", "left", "right") else "center"
            ),
            "show_reference": bool(self.show_reference),
            "position": str(self.position or "bottom"),
            "band_align": (
                self.band_align
                if self.band_align in ("left", "center", "right")
                else "center"
            ),
            "offset_x": int(self.offset_x or 0),
            "offset_y": int(self.offset_y or 0),
            "edge_margin": max(0, int(self.edge_margin if self.edge_margin is not None else 64)),
            "safe_area_percent": max(0, min(15, int(self.safe_area_percent or 0))),
            "panel_side": "right" if self.panel_side == "right" else "left",
            "show_kicker": bool(self.show_kicker),
            "show_accent_bar": bool(self.show_accent_bar),
            "accent_mode": "custom" if self.accent_mode == "custom" else "auto",
            "accent_color": str(self.accent_color or "#74a7f8"),
            "bg_enabled": bool(self.bg_enabled),
            "bg_color": str(self.bg_color or "rgba(7, 12, 22, 0.90)"),
            "bg_opacity": float(
                self.bg_opacity if self.bg_opacity is not None else 0.88
            ),
            "text_color": str(self.text_color or "rgba(255, 255, 255, 0.97)"),
            "ref_color": str(self.ref_color or "rgba(255, 247, 226, 0.94)"),
            # Professional styling
            "text_shadow": bool(self.text_shadow),
            "shadow_color": str(self.shadow_color or "rgba(0, 0, 0, 0.66)"),
            "shadow_blur": int(
                self.shadow_blur if self.shadow_blur is not None else 14
            ),
            "text_stroke": bool(self.text_stroke),
            "stroke_color": str(self.stroke_color or "rgba(0, 0, 0, 0.8)"),
            "stroke_width": int(
                self.stroke_width if self.stroke_width is not None else 1
            ),
            "letter_spacing": int(self.letter_spacing or 0),
            "line_height": float(self.line_height or 1.16),
            "padding_horizontal": int(
                self.padding_horizontal
                if self.padding_horizontal is not None
                else 48
            ),
            "padding_vertical": int(
                self.padding_vertical if self.padding_vertical is not None else 26
            ),
            "max_width": int(self.max_width or 82),
            "auto_fit": bool(self.auto_fit),
            "uniform_text_size": bool(self.uniform_text_size),
            "min_text_size": max(12, int(self.min_text_size or 24)),
            "max_lines": max(1, min(12, int(self.max_lines or 6))),
            "reference_style": (
                self.reference_style
                if self.reference_style in ("badge", "plain", "inline")
                else "badge"
            ),
            "background_dimmer": max(
                0.0,
                min(
                    0.85,
                    float(
                        self.background_dimmer
                        if self.background_dimmer is not None
                        else 0.36
                    ),
                ),
            ),
            "border_radius": int(
                self.border_radius if self.border_radius is not None else 22
            ),
            "animation_enabled": bool(self.animation_enabled),
            "animation_type": str(self.animation_type or "auto"),
            "animation_duration": int(
                self.animation_duration
                if self.animation_duration is not None
                else 520
            ),
            "font_weight": str(self.font_weight or "bold"),
            "text_transform": str(self.text_transform or "none"),
            "bg_blur": bool(self.bg_blur),
            "bg_blur_amount": int(
                self.bg_blur_amount if self.bg_blur_amount is not None else 20
            ),
            "opacity": float(self.opacity if self.opacity is not None else 1.0),
            "bg_gradient_enabled": bool(self.bg_gradient_enabled),
            "bg_color_2": str(self.bg_color_2 or "rgba(2, 6, 14, 0.92)"),
            "bg_gradient_angle": int(
                self.bg_gradient_angle
                if self.bg_gradient_angle is not None
                else 135
            ),
            "bg_mode": "image" if self.bg_mode == "image" else "color",
            "bg_image": str(self.bg_image or ""),
            "bg_image_fit": "contain" if self.bg_image_fit == "contain" else "cover",
            "animation_direction": str(self.animation_direction or "up"),
            "animation_style": (
                "words" if self.animation_style == "words" else "block"
            ),
        }


@dataclass
class ObsScene:
    """A named OBS scene with its own full output style.

    The scene ``id`` (slug) is used in the browser-source URL (?scene=<id>)
    so each OBS scene can render a different look from the same server.
    """

    id: str = ""
    name: str = ""
    output: ObsOutputSettings = field(default_factory=ObsOutputSettings)


def scene_slug(name: str, existing_ids: list[str] | None = None) -> str:
    """Build a URL-safe, unique scene id from a display name.

    Accents are stripped ("Prédication" -> "predication") and the result is
    suffixed with a counter when it collides with an existing id.
    """
    import re
    import unicodedata

    normalized = unicodedata.normalize("NFKD", str(name or "")).encode(
        "ascii", "ignore"
    ).decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    if not slug:
        slug = "scene"
    taken = set(existing_ids or [])
    if slug not in taken:
        return slug
    counter = 2
    while f"{slug}-{counter}" in taken:
        counter += 1
    return f"{slug}-{counter}"


@dataclass
class ObsRemoteSettings:
    """Remote control of OBS through obs-websocket 5.x.

    Lets Project-On switch OBS scenes when the operator projects/hides, and
    create the Project-On browser source automatically.
    """

    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 4455
    password: str = ""
    scene_on_live: str = ""  # OBS scene switched to when a slide goes live
    scene_on_hide: str = ""  # OBS scene switched to when the output is hidden


@dataclass
class ObsSettings:
    mode: str = "web"  # "web" or "ndi"
    web_port: int = 8080
    ndi_source_name: str = "Project-On"
    output: ObsOutputSettings = field(default_factory=ObsOutputSettings)
    scenes: list[ObsScene] = field(default_factory=list)
    remote: ObsRemoteSettings = field(default_factory=ObsRemoteSettings)

    def to_full_obs_config(self) -> dict[str, Any]:
        """Base broadcast config plus one style payload per named scene."""
        config = self.output.to_obs_config()
        config["scenes"] = {
            scene.id: scene.output.to_obs_config()
            for scene in self.scenes
            if scene.id
        }
        return config


@dataclass
class ProjectionSettings:
    layout_mode: str = "fullscreen"  # fullscreen|lower_third|side_panel|subtitle|focus_card
    display_screen: str = "auto"  # auto or QScreen.name()
    safe_margin: int = 32  # pixels
    panel_side: str = "left"  # left|right, used by side_panel
    font_family: str = "Poppins"
    text_size: int = 56  # pixels
    ref_size: int = 24  # pixels
    padding: int = 0  # pixels
    align: str = "center"  # center|left
    position: str = "center"  # top|center|bottom
    slide_style: str = "cinematic"  # cinematic|clean|split
    content_width: int = 88  # percentage of screen width
    content_height: int = 82  # percentage of screen height
    show_reference: bool = True
    reference_position: str = "bottom"  # top|bottom
    uppercase: bool = False  # transform text to uppercase
    text_color: str = "rgba(255,255,255,0.96)"  # main text color
    ref_color: str = "rgba(255,244,214,0.82)"  # reference text color
    bg_color: str = "#07111f"  # background color
    font_weight: str = "bold"  # normal|bold|light
    line_height: float = 1.12  # line height multiplier
    letter_spacing: int = 0  # pixels
    text_shadow: bool = True  # enable text shadow for readability
    shadow_color: str = "rgba(0,0,0,0.88)"  # shadow color
    shadow_blur: int = 18  # shadow blur in pixels
    max_width: int = 100  # percentage of screen width
    # Kept in the schema for old settings files. Local projection is always
    # parameter-driven and uniform; OBS retains its independent auto-fit.
    auto_fit: bool = False
    uniform_text_size: bool = True
    min_text_size: int = 18
    max_lines: int = 8
    background_dimmer: float = 0.34
    panel_enabled: bool = False
    panel_color: str = "rgba(5,12,24,0.86)"
    panel_opacity: float = 0.86
    panel_radius: int = 24
    bg_gradient_enabled: bool = True
    bg_color_2: str = "#0f2744"
    bg_gradient_angle: int = 160
    bg_mode: str = "color"  # "color" or "image" (mutually exclusive background)
    bg_image: str = ""  # background image path (used only when bg_mode == "image")
    bg_image_fit: str = "cover"  # "cover" (remplir) or "contain" (contenir)
    # Slide transitions (local projection)
    animation_enabled: bool = True
    animation_type: str = "fade"  # none|fade|slide|scale|blur|reveal
    animation_duration: int = 420  # milliseconds
    animation_direction: str = "up"  # up|down|left|right (slide/reveal)
    ken_burns: bool = True  # slow zoom on background images

    def to_presentation_config(self) -> dict[str, Any]:
        layout_mode = (self.layout_mode or "fullscreen").lower()
        if layout_mode not in (
            "fullscreen",
            "lower_third",
            "side_panel",
            "subtitle",
            "focus_card",
        ):
            layout_mode = "fullscreen"
        align = (self.align or "center").lower()
        if align not in ("center", "left", "right"):
            align = "center"
        position = (self.position or "center").lower()
        if position not in ("top", "center", "bottom"):
            position = "center"
        slide_style = (self.slide_style or "cinematic").lower()
        if slide_style not in ("cinematic", "clean", "split"):
            slide_style = "cinematic"
        reference_position = (self.reference_position or "bottom").lower()
        if reference_position not in ("top", "bottom"):
            reference_position = "bottom"
        panel_side = (self.panel_side or "left").lower()
        if panel_side not in ("left", "right"):
            panel_side = "left"
        return {
            "layout_mode": layout_mode,
            "display_screen": str(self.display_screen or "auto"),
            "safe_margin": max(0, min(240, int(self.safe_margin or 0))),
            "panel_side": panel_side,
            "font_family": str(self.font_family or "Poppins").strip(),
            "text_size": max(10, min(320, int(self.text_size or 56))),
            "ref_size": max(8, min(160, int(self.ref_size or 24))),
            "padding": max(0, min(160, int(self.padding or 0))),
            "align": align,
            "position": position,
            "slide_style": slide_style,
            "content_width": max(60, min(94, int(self.content_width or 86))),
            "content_height": max(35, min(100, int(self.content_height or 86))),
            "show_reference": bool(self.show_reference),
            "reference_position": reference_position,
            "uppercase": bool(self.uppercase),
            "text_color": str(self.text_color or "rgba(255,255,255,0.96)"),
            "ref_color": str(self.ref_color or "rgba(255,244,214,0.82)"),
            "bg_color": str(self.bg_color or "#07111f"),
            "font_weight": str(self.font_weight or "bold"),
            "line_height": max(0.9, min(2.2, float(self.line_height or 1.18))),
            "letter_spacing": max(-2, min(24, int(self.letter_spacing or 0))),
            "text_shadow": bool(self.text_shadow),
            "shadow_color": str(self.shadow_color or "rgba(0,0,0,0.88)"),
            "shadow_blur": int(
                self.shadow_blur if self.shadow_blur is not None else 18
            ),
            "max_width": max(60, min(100, int(self.max_width or 100))),
            "auto_fit": False,
            "uniform_text_size": True,
            "min_text_size": max(10, int(self.min_text_size or 18)),
            "max_lines": max(1, min(20, int(self.max_lines or 8))),
            "background_dimmer": max(
                0.0,
                min(
                    0.85,
                    float(
                        self.background_dimmer
                        if self.background_dimmer is not None
                        else 0.34
                    ),
                ),
            ),
            "panel_enabled": bool(self.panel_enabled),
            "panel_color": str(self.panel_color or "rgba(5,12,24,0.86)"),
            "panel_opacity": max(
                0.0,
                min(
                    1.0,
                    float(
                        self.panel_opacity
                        if self.panel_opacity is not None
                        else 0.86
                    ),
                ),
            ),
            "panel_radius": max(0, min(96, int(self.panel_radius or 0))),
            "bg_gradient_enabled": bool(self.bg_gradient_enabled),
            "bg_color_2": str(self.bg_color_2 or "#0f2744"),
            "bg_gradient_angle": int(
                self.bg_gradient_angle
                if self.bg_gradient_angle is not None
                else 160
            ),
            "bg_mode": "image" if self.bg_mode == "image" else "color",
            "bg_image": str(self.bg_image or ""),
            "bg_image_fit": "contain" if self.bg_image_fit == "contain" else "cover",
            "animation_enabled": bool(self.animation_enabled),
            "animation_type": str(self.animation_type or "fade"),
            "animation_duration": int(
                self.animation_duration
                if self.animation_duration is not None
                else 420
            ),
            "animation_direction": str(self.animation_direction or "up"),
            "ken_burns": bool(self.ken_burns),
        }


@dataclass
class AppearanceSettings:
    theme: str = "dark"  # "dark" or "light"
    language: str = "fr"  # "fr" or "en"


def _gs(d: dict, key: str, default: str) -> str:
    """Get string from dict with fallback."""
    v = d.get(key)
    return str(v) if v is not None and str(v).strip() else default


def _gi(d: dict, key: str, default: int) -> int:
    """Get int from dict with fallback and validation."""
    try:
        v = d.get(key)
        if v is None:
            return default
        # Ensure font sizes and other pixel values are strictly positive if they seem to be UI sizes
        val = int(v)
        if "size" in key.lower():
            return max(val, 8) if val > 0 else default
        return val
    except (ValueError, TypeError):
        return default


def _gf(d: dict, key: str, default: float) -> float:
    """Get float from dict with fallback and validation."""
    try:
        v = d.get(key)
        if v is None:
            return default
        val = float(v)
        if "line_height" in key.lower():
            return max(val, 0.5)
        if "opacity" in key.lower():
            return max(0.0, min(1.0, val))
        return val
    except (ValueError, TypeError):
        return default


def _gb(d: dict, key: str, default: bool) -> bool:
    """Get bool from dict with fallback."""
    return bool(d[key]) if key in d else default


def _read_obs_output(d: dict, out: ObsOutputSettings) -> ObsOutputSettings:
    """Populate ``out`` from a serialized ObsOutputSettings dict."""
    if not isinstance(d, dict):
        return out
    out.layout_mode = _gs(d, "layout_mode", out.layout_mode)
    out.font_family = _gs(d, "font_family", out.font_family)
    out.text_size = _gi(d, "text_size", out.text_size)
    out.ref_size = _gi(d, "ref_size", out.ref_size)
    out.align = _gs(d, "align", out.align)
    out.show_reference = _gb(d, "show_reference", out.show_reference)
    out.position = _gs(d, "position", out.position)
    out.band_align = _gs(d, "band_align", out.band_align)
    out.offset_x = _gi(d, "offset_x", out.offset_x)
    out.offset_y = _gi(d, "offset_y", out.offset_y)
    out.edge_margin = _gi(d, "edge_margin", out.edge_margin)
    out.safe_area_percent = _gi(d, "safe_area_percent", out.safe_area_percent)
    out.panel_side = _gs(d, "panel_side", out.panel_side)
    out.show_kicker = _gb(d, "show_kicker", out.show_kicker)
    out.show_accent_bar = _gb(d, "show_accent_bar", out.show_accent_bar)
    out.accent_mode = _gs(d, "accent_mode", out.accent_mode)
    out.accent_color = _gs(d, "accent_color", out.accent_color)
    out.bg_enabled = _gb(d, "bg_enabled", out.bg_enabled)
    out.bg_color = _gs(d, "bg_color", out.bg_color)
    out.bg_opacity = _gf(d, "bg_opacity", out.bg_opacity)
    out.text_color = _gs(d, "text_color", out.text_color)
    out.ref_color = _gs(d, "ref_color", out.ref_color)
    out.text_shadow = _gb(d, "text_shadow", out.text_shadow)
    out.shadow_color = _gs(d, "shadow_color", out.shadow_color)
    out.shadow_blur = _gi(d, "shadow_blur", out.shadow_blur)
    out.text_stroke = _gb(d, "text_stroke", out.text_stroke)
    out.stroke_color = _gs(d, "stroke_color", out.stroke_color)
    out.stroke_width = _gi(d, "stroke_width", out.stroke_width)
    out.letter_spacing = _gi(d, "letter_spacing", out.letter_spacing)
    out.line_height = _gf(d, "line_height", out.line_height)
    out.padding_horizontal = _gi(d, "padding_horizontal", out.padding_horizontal)
    out.padding_vertical = _gi(d, "padding_vertical", out.padding_vertical)
    out.max_width = _gi(d, "max_width", out.max_width)
    out.auto_fit = _gb(d, "auto_fit", out.auto_fit)
    out.uniform_text_size = _gb(d, "uniform_text_size", out.uniform_text_size)
    out.min_text_size = _gi(d, "min_text_size", out.min_text_size)
    out.max_lines = _gi(d, "max_lines", out.max_lines)
    out.reference_style = _gs(d, "reference_style", out.reference_style)
    out.background_dimmer = _gf(d, "background_dimmer", out.background_dimmer)
    out.border_radius = _gi(d, "border_radius", out.border_radius)
    out.animation_enabled = _gb(d, "animation_enabled", out.animation_enabled)
    out.animation_type = _gs(d, "animation_type", out.animation_type)
    out.animation_duration = _gi(d, "animation_duration", out.animation_duration)
    out.font_weight = _gs(d, "font_weight", out.font_weight)
    out.text_transform = _gs(d, "text_transform", out.text_transform)
    out.bg_blur = _gb(d, "bg_blur", out.bg_blur)
    out.bg_blur_amount = _gi(d, "bg_blur_amount", out.bg_blur_amount)
    out.opacity = _gf(d, "opacity", out.opacity)
    out.bg_gradient_enabled = _gb(d, "bg_gradient_enabled", out.bg_gradient_enabled)
    out.bg_color_2 = _gs(d, "bg_color_2", out.bg_color_2)
    out.bg_gradient_angle = _gi(d, "bg_gradient_angle", out.bg_gradient_angle)
    out.bg_mode = _gs(d, "bg_mode", out.bg_mode)
    out.bg_image = _gs(d, "bg_image", out.bg_image)
    out.bg_image_fit = _gs(d, "bg_image_fit", out.bg_image_fit)
    out.animation_direction = _gs(d, "animation_direction", out.animation_direction)
    out.animation_style = _gs(d, "animation_style", out.animation_style)
    return out


@dataclass
class AppSettings:
    projection: ProjectionSettings = field(default_factory=ProjectionSettings)
    obs: ObsSettings = field(default_factory=ObsSettings)
    appearance: AppearanceSettings = field(default_factory=AppearanceSettings)

    @staticmethod
    def default_path(project_root: Path) -> Path:
        return project_root / "data" / "settings.json"

    @classmethod
    def load(cls, path: Path) -> AppSettings:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return cls()
        if not isinstance(payload, dict):
            return cls()

        projection = ProjectionSettings()
        p = payload.get("projection")
        if isinstance(p, dict):
            projection.layout_mode = _gs(
                p, "layout_mode", projection.layout_mode
            )
            projection.display_screen = _gs(
                p, "display_screen", projection.display_screen
            )
            projection.safe_margin = _gi(p, "safe_margin", projection.safe_margin)
            projection.panel_side = _gs(p, "panel_side", projection.panel_side)
            projection.font_family = _gs(p, "font_family", projection.font_family)
            projection.text_size = _gi(p, "text_size", projection.text_size)
            projection.ref_size = _gi(p, "ref_size", projection.ref_size)
            projection.padding = _gi(p, "padding", projection.padding)
            projection.align = _gs(p, "align", projection.align)
            projection.position = _gs(p, "position", projection.position)
            projection.slide_style = _gs(p, "slide_style", projection.slide_style)
            projection.content_width = _gi(
                p, "content_width", projection.content_width
            )
            projection.content_height = _gi(
                p, "content_height", projection.content_height
            )
            projection.show_reference = _gb(
                p, "show_reference", projection.show_reference
            )
            projection.reference_position = _gs(
                p, "reference_position", projection.reference_position
            )
            projection.uppercase = _gb(p, "uppercase", projection.uppercase)
            projection.text_color = _gs(p, "text_color", projection.text_color)
            projection.ref_color = _gs(p, "ref_color", projection.ref_color)
            projection.bg_color = _gs(p, "bg_color", projection.bg_color)
            projection.font_weight = _gs(p, "font_weight", projection.font_weight)
            projection.line_height = _gf(p, "line_height", projection.line_height)
            projection.letter_spacing = _gi(
                p, "letter_spacing", projection.letter_spacing
            )
            projection.text_shadow = _gb(p, "text_shadow", projection.text_shadow)
            projection.shadow_color = _gs(p, "shadow_color", projection.shadow_color)
            projection.shadow_blur = _gi(p, "shadow_blur", projection.shadow_blur)
            projection.max_width = _gi(p, "max_width", projection.max_width)
            # Migrate legacy grow-to-fill preferences to the fixed local
            # projection contract introduced in 1.5.1.
            projection.auto_fit = False
            projection.uniform_text_size = True
            projection.min_text_size = _gi(
                p, "min_text_size", projection.min_text_size
            )
            projection.max_lines = _gi(p, "max_lines", projection.max_lines)
            projection.background_dimmer = _gf(
                p, "background_dimmer", projection.background_dimmer
            )
            projection.panel_enabled = _gb(
                p, "panel_enabled", projection.panel_enabled
            )
            projection.panel_color = _gs(
                p, "panel_color", projection.panel_color
            )
            projection.panel_opacity = _gf(
                p, "panel_opacity", projection.panel_opacity
            )
            projection.panel_radius = _gi(
                p, "panel_radius", projection.panel_radius
            )
            projection.bg_gradient_enabled = _gb(
                p, "bg_gradient_enabled", projection.bg_gradient_enabled
            )
            projection.bg_color_2 = _gs(p, "bg_color_2", projection.bg_color_2)
            projection.bg_gradient_angle = _gi(
                p, "bg_gradient_angle", projection.bg_gradient_angle
            )
            projection.bg_mode = _gs(p, "bg_mode", projection.bg_mode)
            projection.bg_image = _gs(p, "bg_image", projection.bg_image)
            projection.bg_image_fit = _gs(
                p, "bg_image_fit", projection.bg_image_fit
            )
            projection.animation_enabled = _gb(
                p, "animation_enabled", projection.animation_enabled
            )
            projection.animation_type = _gs(
                p, "animation_type", projection.animation_type
            )
            projection.animation_duration = _gi(
                p, "animation_duration", projection.animation_duration
            )
            projection.animation_direction = _gs(
                p, "animation_direction", projection.animation_direction
            )
            projection.ken_burns = _gb(p, "ken_burns", projection.ken_burns)

        obs = ObsSettings()
        o = payload.get("obs")
        if isinstance(o, dict):
            obs.mode = _gs(o, "mode", obs.mode)
            if obs.mode not in ("web", "ndi"):
                obs.mode = "web"
            obs.web_port = _gi(o, "web_port", obs.web_port)
            obs.ndi_source_name = _gs(o, "ndi_source_name", obs.ndi_source_name)

            _read_obs_output(o.get("output"), obs.output)

            scenes = o.get("scenes")
            if isinstance(scenes, list):
                seen_ids: list[str] = []
                for raw in scenes:
                    if not isinstance(raw, dict):
                        continue
                    scene_name = _gs(raw, "name", "")
                    scene_id = _gs(raw, "id", "")
                    if not scene_id:
                        scene_id = scene_slug(scene_name or "scene", seen_ids)
                    elif scene_id in seen_ids:
                        scene_id = scene_slug(scene_id, seen_ids)
                    seen_ids.append(scene_id)
                    scene = ObsScene(id=scene_id, name=scene_name or scene_id)
                    _read_obs_output(raw.get("output"), scene.output)
                    obs.scenes.append(scene)

            remote_raw = o.get("remote")
            if isinstance(remote_raw, dict):
                obs.remote.enabled = _gb(remote_raw, "enabled", obs.remote.enabled)
                obs.remote.host = _gs(remote_raw, "host", obs.remote.host) or "127.0.0.1"
                try:
                    obs.remote.port = int(remote_raw.get("port", obs.remote.port))
                except (TypeError, ValueError):
                    pass
                obs.remote.password = str(remote_raw.get("password") or "")
                obs.remote.scene_on_live = str(remote_raw.get("scene_on_live") or "")
                obs.remote.scene_on_hide = str(remote_raw.get("scene_on_hide") or "")

        appearance = AppearanceSettings()
        a = payload.get("appearance")
        if isinstance(a, dict):
            appearance.theme = _gs(a, "theme", appearance.theme).lower()
            if appearance.theme not in ("dark", "light"):
                appearance.theme = "dark"
            appearance.language = _gs(a, "language", appearance.language)
            if appearance.language not in ("fr", "en"):
                appearance.language = "fr"

        # Guard: if a background image was selected but the file no longer
        # exists (e.g. removed during a defaults upgrade), fall back to the
        # colour background so the projection isn't left blank.
        for cfg in (projection, obs.output):
            if cfg.bg_mode == "image" and (
                not cfg.bg_image or not Path(cfg.bg_image).is_file()
            ):
                cfg.bg_mode = "color"

        return cls(projection=projection, obs=obs, appearance=appearance)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "projection": asdict(self.projection),
            "obs": asdict(self.obs),
            "appearance": asdict(self.appearance),
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(path)
