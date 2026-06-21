from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ObsOutputSettings:
    font_family: str = "Google Sans"
    text_size: int = 48  # pixels
    ref_size: int = 19  # pixels
    align: str = "center"  # center|left
    show_reference: bool = True
    position: str = "bottom"  # bottom|top|center
    bg_enabled: bool = True  # show/hide background band
    bg_color: str = "rgba(8, 15, 28, 0.86)"
    bg_opacity: float = 0.82  # background-specific opacity 0.0-1.0
    text_color: str = "rgba(255, 255, 255, 0.96)"
    ref_color: str = "rgba(255, 245, 222, 0.82)"
    # Professional text styling
    text_shadow: bool = True
    shadow_color: str = "rgba(0, 0, 0, 0.56)"
    shadow_blur: int = 14  # pixels
    text_stroke: bool = False
    stroke_color: str = "rgba(0, 0, 0, 0.8)"
    stroke_width: int = 1  # pixels
    letter_spacing: int = 0  # pixels
    line_height: float = 1.16  # multiplier
    padding_horizontal: int = 48  # pixels
    padding_vertical: int = 26  # pixels
    max_width: int = 82  # percentage of screen width
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
    bg_color_2: str = "rgba(3, 8, 18, 0.90)"
    bg_gradient_angle: int = 135  # degrees
    bg_mode: str = "color"  # "color" or "image" (mutually exclusive background)
    bg_image: str = ""  # background image path (used only when bg_mode == "image")
    bg_image_fit: str = "cover"  # "cover" (remplir) or "contain" (contenir)
    # Animation refinement
    animation_direction: str = "up"  # up|down|left|right

    def to_obs_config(self) -> dict[str, Any]:
        return {
            "version": int(time.time() * 1000),
            "font_family": str(self.font_family or "Google Sans").strip(),
            "text_size": int(self.text_size or 48),
            "ref_size": int(self.ref_size or 19),
            "align": self.align if self.align in ("center", "left") else "center",
            "show_reference": bool(self.show_reference),
            "position": str(self.position or "bottom"),
            "bg_enabled": bool(self.bg_enabled),
            "bg_color": str(self.bg_color or "rgba(8, 15, 28, 0.86)"),
            "bg_opacity": float(
                self.bg_opacity if self.bg_opacity is not None else 0.82
            ),
            "text_color": str(self.text_color or "rgba(255, 255, 255, 0.96)"),
            "ref_color": str(self.ref_color or "rgba(255, 245, 222, 0.82)"),
            # Professional styling
            "text_shadow": bool(self.text_shadow),
            "shadow_color": str(self.shadow_color or "rgba(0, 0, 0, 0.56)"),
            "shadow_blur": int(self.shadow_blur or 14),
            "text_stroke": bool(self.text_stroke),
            "stroke_color": str(self.stroke_color or "rgba(0, 0, 0, 0.8)"),
            "stroke_width": int(self.stroke_width or 1),
            "letter_spacing": int(self.letter_spacing or 0),
            "line_height": float(self.line_height or 1.16),
            "padding_horizontal": int(self.padding_horizontal or 48),
            "padding_vertical": int(self.padding_vertical or 26),
            "max_width": int(self.max_width or 82),
            "border_radius": int(self.border_radius or 22),
            "animation_enabled": bool(self.animation_enabled),
            "animation_type": str(self.animation_type or "auto"),
            "animation_duration": int(self.animation_duration or 520),
            "font_weight": str(self.font_weight or "bold"),
            "text_transform": str(self.text_transform or "none"),
            "bg_blur": bool(self.bg_blur),
            "bg_blur_amount": int(self.bg_blur_amount or 20),
            "opacity": float(self.opacity if self.opacity is not None else 1.0),
            "bg_gradient_enabled": bool(self.bg_gradient_enabled),
            "bg_color_2": str(self.bg_color_2 or "rgba(3, 8, 18, 0.90)"),
            "bg_gradient_angle": int(self.bg_gradient_angle or 135),
            "bg_mode": "image" if self.bg_mode == "image" else "color",
            "bg_image": str(self.bg_image or ""),
            "bg_image_fit": "contain" if self.bg_image_fit == "contain" else "cover",
            "animation_direction": str(self.animation_direction or "up"),
        }


@dataclass
class ObsSettings:
    mode: str = "web"  # "web" or "ndi"
    web_port: int = 8080
    ndi_source_name: str = "Project-On"
    output: ObsOutputSettings = field(default_factory=ObsOutputSettings)


@dataclass
class ProjectionSettings:
    font_family: str = "Google Sans"
    text_size: int = 48  # pixels
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
        align = (self.align or "center").lower()
        if align not in ("center", "left"):
            align = "center"
        slide_style = (self.slide_style or "cinematic").lower()
        if slide_style not in ("cinematic", "clean", "split"):
            slide_style = "cinematic"

        return {
            "font_family": str(self.font_family or "Google Sans").strip(),
            "text_size": int(self.text_size or 48),
            "ref_size": int(self.ref_size or 24),
            "padding": int(self.padding if self.padding is not None else 0),
            "align": align,
            "position": (
                self.position
                if self.position in ("top", "center", "bottom")
                else "center"
            ),
            "slide_style": slide_style,
            "content_width": int(self.content_width or 88),
            "content_height": int(self.content_height or 82),
            "show_reference": bool(self.show_reference),
            "reference_position": (
                self.reference_position
                if self.reference_position in ("top", "bottom")
                else "bottom"
            ),
            "uppercase": bool(self.uppercase),
            "text_color": str(self.text_color or "rgba(255,255,255,0.96)"),
            "ref_color": str(self.ref_color or "rgba(255,244,214,0.82)"),
            "bg_color": str(self.bg_color or "#07111f"),
            "font_weight": str(self.font_weight or "bold"),
            "line_height": float(self.line_height or 1.15),
            "letter_spacing": int(self.letter_spacing or 0),
            "text_shadow": bool(self.text_shadow),
            "shadow_color": str(self.shadow_color or "rgba(0,0,0,0.88)"),
            "shadow_blur": int(self.shadow_blur or 18),
            "max_width": int(self.max_width or 100),
            "bg_gradient_enabled": bool(self.bg_gradient_enabled),
            "bg_color_2": str(self.bg_color_2 or "#0f2744"),
            "bg_gradient_angle": int(self.bg_gradient_angle or 160),
            "bg_mode": "image" if self.bg_mode == "image" else "color",
            "bg_image": str(self.bg_image or ""),
            "bg_image_fit": "contain" if self.bg_image_fit == "contain" else "cover",
            "animation_enabled": bool(self.animation_enabled),
            "animation_type": str(self.animation_type or "fade"),
            "animation_duration": int(self.animation_duration or 420),
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
        if "size" in key.lower() or "padding" in key.lower():
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

            out = o.get("output")
            if isinstance(out, dict):
                obs.output.font_family = _gs(out, "font_family", obs.output.font_family)
                obs.output.text_size = _gi(out, "text_size", obs.output.text_size)
                obs.output.ref_size = _gi(out, "ref_size", obs.output.ref_size)
                obs.output.align = _gs(out, "align", obs.output.align)
                obs.output.show_reference = _gb(
                    out, "show_reference", obs.output.show_reference
                )
                obs.output.position = _gs(out, "position", obs.output.position)
                obs.output.bg_enabled = _gb(out, "bg_enabled", obs.output.bg_enabled)
                obs.output.bg_color = _gs(out, "bg_color", obs.output.bg_color)
                obs.output.bg_opacity = _gf(out, "bg_opacity", obs.output.bg_opacity)
                obs.output.text_color = _gs(out, "text_color", obs.output.text_color)
                obs.output.ref_color = _gs(out, "ref_color", obs.output.ref_color)
                obs.output.text_shadow = _gb(out, "text_shadow", obs.output.text_shadow)
                obs.output.shadow_color = _gs(
                    out, "shadow_color", obs.output.shadow_color
                )
                obs.output.shadow_blur = _gi(out, "shadow_blur", obs.output.shadow_blur)
                obs.output.text_stroke = _gb(out, "text_stroke", obs.output.text_stroke)
                obs.output.stroke_color = _gs(
                    out, "stroke_color", obs.output.stroke_color
                )
                obs.output.stroke_width = _gi(
                    out, "stroke_width", obs.output.stroke_width
                )
                obs.output.letter_spacing = _gi(
                    out, "letter_spacing", obs.output.letter_spacing
                )
                obs.output.line_height = _gf(out, "line_height", obs.output.line_height)
                obs.output.padding_horizontal = _gi(
                    out, "padding_horizontal", obs.output.padding_horizontal
                )
                obs.output.padding_vertical = _gi(
                    out, "padding_vertical", obs.output.padding_vertical
                )
                obs.output.max_width = _gi(out, "max_width", obs.output.max_width)
                obs.output.border_radius = _gi(
                    out, "border_radius", obs.output.border_radius
                )
                obs.output.animation_enabled = _gb(
                    out, "animation_enabled", obs.output.animation_enabled
                )
                obs.output.animation_type = _gs(
                    out, "animation_type", obs.output.animation_type
                )
                obs.output.animation_duration = _gi(
                    out, "animation_duration", obs.output.animation_duration
                )
                obs.output.font_weight = _gs(out, "font_weight", obs.output.font_weight)
                obs.output.text_transform = _gs(
                    out, "text_transform", obs.output.text_transform
                )
                obs.output.bg_blur = _gb(out, "bg_blur", obs.output.bg_blur)
                obs.output.bg_blur_amount = _gi(
                    out, "bg_blur_amount", obs.output.bg_blur_amount
                )
                obs.output.opacity = _gf(out, "opacity", obs.output.opacity)
                obs.output.bg_gradient_enabled = _gb(
                    out, "bg_gradient_enabled", obs.output.bg_gradient_enabled
                )
                obs.output.bg_color_2 = _gs(out, "bg_color_2", obs.output.bg_color_2)
                obs.output.bg_gradient_angle = _gi(
                    out, "bg_gradient_angle", obs.output.bg_gradient_angle
                )
                obs.output.bg_mode = _gs(out, "bg_mode", obs.output.bg_mode)
                obs.output.bg_image = _gs(out, "bg_image", obs.output.bg_image)
                obs.output.bg_image_fit = _gs(
                    out, "bg_image_fit", obs.output.bg_image_fit
                )
                obs.output.animation_direction = _gs(
                    out, "animation_direction", obs.output.animation_direction
                )

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
