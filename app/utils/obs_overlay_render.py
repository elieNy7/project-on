"""Rendu de la section texte « façon OBS » en PIL, hors de l'interface Qt.

Unique source de vérité du style d'incrustation : la sortie NDI
(:mod:`app.utils.ndi_lower_third`) et la sortie HDMI mixeur
(:mod:`app.ui.mixer_output_window`) composent la même section texte à partir
des mêmes réglages (``obs-config.json``, édités dans « Diffusion & OBS »).

``render_obs_overlay`` renvoie une image RGBA transparente (aucun fond),
``render_obs_overlay_on_color`` la compose sur un fond uni — le vert chroma
de la sortie HDMI, que le mélangeur supprime par chroma key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Vert chroma standard (#00B140) : couleur supprimée par le chroma key
# des mélangeurs (ATEM, Roland V/AV…). Ne pas changer sans mise à jour
# de la documentation d'incrustation.
CHROMA_KEY_GREEN = (0, 177, 64)

# Couleurs de clé proposées à l'opérateur : le magenta et le bleu
# dépannent quand la scène contient du vert (vêtements, plantes, écran).
CHROMA_KEY_COLORS: dict[str, tuple[int, int, int]] = {
    "green": CHROMA_KEY_GREEN,
    "magenta": (255, 0, 255),
    "blue": (0, 82, 255),
}


def chroma_key_rgb(name: str) -> tuple[int, int, int]:
    """RGB de la couleur de clé demandée (vert par défaut)."""
    return CHROMA_KEY_COLORS.get(
        str(name or "").strip().lower(), CHROMA_KEY_GREEN
    )


# Ligne au-dessus de la référence : neutre, sans accent de source —
# le vert biblique sautait à la clé chroma de la sortie HDMI.
REF_DIVIDER_FILL = (255, 255, 255, 90)

# Accents neutres substitués à une couleur de source trop proche de la
# couleur de clé : le chroma du mélangeur la supprimerait (trou dans le
# bandeau). Seuil = distance RGB euclidienne.
_KEY_SAFE_ACCENT = (235, 240, 246)
_KEY_SAFE_ACCENT_2 = (203, 214, 229)
_KEY_PROXIMITY = 200.0


def accent_too_close_to_key(accent, key_rgb) -> bool:
    """Vrai si l'accent risque d'être supprimé par la clé chroma."""
    return (
        (accent[0] - key_rgb[0]) ** 2
        + (accent[1] - key_rgb[1]) ** 2
        + (accent[2] - key_rgb[2]) ** 2
    ) ** 0.5 < _KEY_PROXIMITY


def _parse_rgba_tuple(
    value: str, fallback: tuple[int, int, int, int]
) -> tuple[int, int, int, int]:
    s = str(value or "").strip().lower()
    if not s:
        return fallback
    if s.startswith("rgba") and "(" in s and ")" in s:
        inner = s[s.find("(") + 1 : s.rfind(")")]
        parts = [p.strip() for p in inner.split(",")]
        if len(parts) == 4:
            try:
                r = int(float(parts[0]))
                g = int(float(parts[1]))
                b = int(float(parts[2]))
                a = int(max(0.0, min(1.0, float(parts[3]))) * 255)
                return (r, g, b, a)
            except Exception:
                return fallback
    if s.startswith("rgb") and "(" in s and ")" in s:
        inner = s[s.find("(") + 1 : s.rfind(")")]
        parts = [p.strip() for p in inner.split(",")]
        if len(parts) >= 3:
            try:
                r = int(float(parts[0]))
                g = int(float(parts[1]))
                b = int(float(parts[2]))
                return (r, g, b, 255)
            except Exception:
                return fallback
    if s.startswith("#"):
        raw = s[1:]
        try:
            if len(raw) == 3:
                r = int(raw[0] * 2, 16)
                g = int(raw[1] * 2, 16)
                b = int(raw[2] * 2, 16)
                return (r, g, b, 255)
            if len(raw) >= 6:
                r = int(raw[0:2], 16)
                g = int(raw[2:4], 16)
                b = int(raw[4:6], 16)
                return (r, g, b, 255)
        except Exception:
            return fallback
    return fallback


def _wrap_text(draw, text: str, font, max_width: int) -> str:
    raw = str(text or "").replace("\r", "").strip()
    if not raw:
        return ""
    lines_out: list[str] = []
    for para in raw.split("\n"):
        words = [w for w in para.split(" ") if w]
        if not words:
            lines_out.append("")
            continue
        line = words[0]
        for w in words[1:]:
            test = f"{line} {w}".strip()
            w_px = draw.textlength(test, font=font)
            if w_px <= max_width:
                line = test
            else:
                lines_out.append(line)
                line = w
        lines_out.append(line)
    return "\n".join(lines_out)


@dataclass
class OverlayStyleConfig:
    """Style de la section texte, lu depuis la charge utile OBS.

    Miroir de ``ObsOutputSettings.to_obs_config`` : chaque champ correspond à
    un réglage de la page Navigateur OBS (voir ``presentation/obs-style.css``).
    """

    layout_mode: str = "lower_third"
    panel_side: str = "left"
    safe_area_percent: int = 5
    font_family: str = "Google Sans"
    font_weight: str = "bold"  # normal|bold|light
    text_size: int = 48
    ref_size: int = 24
    align: str = "center"  # center|left|right
    show_reference: bool = True
    reference_style: str = "badge"  # badge|plain|inline
    bg_color: str = "rgba(0, 0, 0, 0.75)"
    bg_opacity: float = 0.88
    text_color: str = "rgba(255, 255, 255, 0.95)"
    ref_color: str = "rgba(255, 255, 255, 0.7)"
    max_width: int = 82
    padding_horizontal: int = 48
    padding_vertical: int = 26
    border_radius: int = 22
    line_height: float = 1.16
    letter_spacing: int = 0  # pixels (page OBS : --letter-spacing)
    # Plancher d'auto-ajustement : en mode bande (lower_third, subtitle),
    # la typographie rétrécit jusqu'à cette taille plutôt que de laisser
    # le bandeau déborder du cadre.
    min_text_size: int = 22
    # Auto-ajustement : la page ne rétrécit QUE si auto_fit est actif et
    # uniform_text_size désactivé. Dans tous les autres cas la taille
    # configurée est respectée telle quelle (bandeau rogné si trop haut).
    auto_fit: bool = False
    uniform_text_size: bool = True
    max_lines: int = 8
    # Parité avec la page Navigateur OBS
    position: str = "bottom"  # bottom|top|center
    band_align: str = "center"  # left|center|right
    offset_x: int = 0
    offset_y: int = 0
    edge_margin: int = 64
    bg_enabled: bool = True
    bg_gradient_enabled: bool = False
    bg_color_2: str = ""
    bg_gradient_angle: int = 135  # degrés (page OBS : --gradient-direction)
    bg_blur: bool = True
    bg_blur_amount: int = 20
    bg_mode: str = "color"  # color|image (image de fond DANS le bandeau)
    bg_image: str = ""
    bg_image_fit: str = "cover"  # cover|contain
    background_dimmer: float = 0.36
    text_transform: str = "none"  # none|uppercase|capitalize
    text_shadow: bool = True
    shadow_color: str = "rgba(0, 0, 0, 0.6)"
    shadow_blur: int = 8
    text_stroke: bool = False
    stroke_color: str = "rgba(0, 0, 0, 0.8)"
    stroke_width: int = 1
    show_kicker: bool = True
    show_accent_bar: bool = True
    accent_mode: str = "auto"  # auto|custom
    accent_color: str = "#74a7f8"
    opacity: float = 1.0
    # Entrée animée (page OBS : animation_*)
    animation_enabled: bool = True
    animation_type: str = "fade"  # none|fade|slide|scale|blur|reveal|auto
    animation_duration: int = 420  # ms
    animation_direction: str = "up"  # up|down|left|right
    animation_style: str = "block"  # block|words

    @classmethod
    def from_payload(cls, cfg: dict[str, Any] | None) -> OverlayStyleConfig:
        cfg = cfg if isinstance(cfg, dict) else {}
        out = cls()
        out.layout_mode = str(cfg.get("layout_mode") or out.layout_mode).lower()
        out.panel_side = str(cfg.get("panel_side") or out.panel_side).lower()
        try:
            out.safe_area_percent = max(
                0, min(15, int(cfg.get("safe_area_percent") or 0))
            )
        except Exception:
            pass
        out.font_family = str(cfg.get("font_family") or out.font_family)
        try:
            out.text_size = int(cfg.get("text_size") or out.text_size)
        except Exception:
            pass
        try:
            out.ref_size = int(cfg.get("ref_size") or out.ref_size)
        except Exception:
            pass
        out.align = str(cfg.get("align") or out.align)
        out.show_reference = bool(
            cfg.get("show_reference")
            if "show_reference" in cfg
            else out.show_reference
        )
        out.bg_color = str(cfg.get("bg_color") or out.bg_color)
        try:
            out.bg_opacity = float(
                cfg.get("bg_opacity") if "bg_opacity" in cfg else out.bg_opacity
            )
        except Exception:
            pass
        out.text_color = str(cfg.get("text_color") or out.text_color)
        out.ref_color = str(cfg.get("ref_color") or out.ref_color)
        for attr in (
            "max_width",
            "padding_horizontal",
            "padding_vertical",
            "border_radius",
        ):
            try:
                value = cfg.get(attr)
                if value is not None:
                    setattr(out, attr, int(value))
            except Exception:
                pass
        try:
            out.line_height = float(cfg.get("line_height") or out.line_height)
        except Exception:
            pass
        try:
            out.min_text_size = max(
                12, min(80, int(cfg.get("min_text_size") or out.min_text_size))
            )
        except Exception:
            pass
        try:
            out.letter_spacing = int(
                cfg.get("letter_spacing")
                if cfg.get("letter_spacing") is not None
                else out.letter_spacing
            )
        except Exception:
            pass
        # Auto-ajustement : mêmes règles que la page (« uniform_text_size »
        # prime : la taille configurée est alors respectée telle quelle).
        out.auto_fit = bool(cfg.get("auto_fit") if "auto_fit" in cfg else out.auto_fit)
        out.uniform_text_size = bool(
            cfg.get("uniform_text_size")
            if "uniform_text_size" in cfg
            else out.uniform_text_size
        )
        try:
            out.max_lines = max(1, min(12, int(cfg.get("max_lines") or out.max_lines)))
        except Exception:
            pass
        out.font_weight = str(cfg.get("font_weight") or out.font_weight).lower()
        out.reference_style = str(
            cfg.get("reference_style") or out.reference_style
        ).lower()
        out.position = str(cfg.get("position") or out.position).lower()
        out.band_align = str(cfg.get("band_align") or out.band_align).lower()
        for attr in ("offset_x", "offset_y"):
            try:
                setattr(out, attr, int(cfg.get(attr) or 0))
            except Exception:
                pass
        try:
            if cfg.get("edge_margin") is not None:
                out.edge_margin = max(0, int(cfg.get("edge_margin")))
        except Exception:
            pass
        out.bg_enabled = bool(
            cfg.get("bg_enabled") if "bg_enabled" in cfg else out.bg_enabled
        )
        out.bg_gradient_enabled = bool(cfg.get("bg_gradient_enabled"))
        out.bg_color_2 = str(cfg.get("bg_color_2") or "")
        try:
            out.bg_gradient_angle = int(
                cfg.get("bg_gradient_angle")
                if cfg.get("bg_gradient_angle") is not None
                else out.bg_gradient_angle
            )
        except Exception:
            pass
        out.bg_blur = bool(cfg.get("bg_blur") if "bg_blur" in cfg else out.bg_blur)
        try:
            out.bg_blur_amount = max(
                0, min(60, int(cfg.get("bg_blur_amount") or out.bg_blur_amount))
            )
        except Exception:
            pass
        out.bg_mode = str(cfg.get("bg_mode") or out.bg_mode).lower()
        out.bg_image = str(cfg.get("bg_image") or "")
        out.bg_image_fit = str(cfg.get("bg_image_fit") or out.bg_image_fit).lower()
        try:
            out.background_dimmer = max(
                0.0,
                min(0.85, float(cfg.get("background_dimmer", out.background_dimmer))),
            )
        except Exception:
            pass
        out.text_transform = str(cfg.get("text_transform") or out.text_transform)
        out.text_shadow = bool(
            cfg.get("text_shadow") if "text_shadow" in cfg else out.text_shadow
        )
        out.shadow_color = str(cfg.get("shadow_color") or out.shadow_color)
        try:
            out.shadow_blur = max(
                0, min(60, int(cfg.get("shadow_blur") or out.shadow_blur))
            )
        except Exception:
            pass
        out.text_stroke = bool(
            cfg.get("text_stroke") if "text_stroke" in cfg else out.text_stroke
        )
        out.stroke_color = str(cfg.get("stroke_color") or out.stroke_color)
        try:
            out.stroke_width = max(
                0, min(12, int(cfg.get("stroke_width") or out.stroke_width))
            )
        except Exception:
            pass
        out.show_kicker = bool(
            cfg.get("show_kicker") if "show_kicker" in cfg else out.show_kicker
        )
        out.show_accent_bar = bool(
            cfg.get("show_accent_bar")
            if "show_accent_bar" in cfg
            else out.show_accent_bar
        )
        out.accent_mode = str(cfg.get("accent_mode") or out.accent_mode)
        out.accent_color = str(cfg.get("accent_color") or out.accent_color)
        out.animation_enabled = bool(
            cfg.get("animation_enabled")
            if "animation_enabled" in cfg
            else out.animation_enabled
        )
        out.animation_type = str(
            cfg.get("animation_type") or out.animation_type
        ).lower()
        try:
            out.animation_duration = max(
                0,
                min(2000, int(cfg.get("animation_duration") or out.animation_duration)),
            )
        except Exception:
            pass
        out.animation_direction = str(
            cfg.get("animation_direction") or out.animation_direction
        ).lower()
        out.animation_style = (
            "words" if str(cfg.get("animation_style") or "") == "words" else "block"
        )
        try:
            out.opacity = max(
                0.0,
                min(1.0, float(cfg.get("opacity") if "opacity" in cfg else out.opacity)),
            )
        except Exception:
            pass
        return out


# ── Palettes de source : miroir exact de `obs-style.css` ─────────────────
# (accent, accent 2, halo, fond du kicker, bordure du kicker, teinte du corps)
SOURCE_PALETTES: dict[str, tuple] = {
    "bible": (
        (86, 214, 129, 255), (181, 243, 202, 255), (86, 214, 129, 61),
        (34, 92, 60, 51), (120, 255, 171, 56), (86, 214, 129, 20),
    ),
    "hymn": (
        (185, 151, 255, 255), (232, 220, 255, 255), (185, 151, 255, 66),
        (72, 41, 114, 51), (185, 151, 255, 61), (185, 151, 255, 23),
    ),
    "sermon": (
        (224, 160, 68, 255), (255, 217, 160, 255), (224, 160, 68, 61),
        (94, 64, 20, 56), (224, 160, 68, 61), (224, 160, 68, 23),
    ),
    "expose": (
        (0, 172, 193, 255), (127, 228, 239, 255), (0, 172, 193, 61),
        (8, 70, 80, 56), (0, 172, 193, 61), (0, 172, 193, 20),
    ),
    "custom": (
        (109, 180, 255, 255), (207, 224, 255, 255), (109, 180, 255, 61),
        (42, 66, 110, 51), (145, 182, 255, 56), (116, 167, 248, 20),
    ),
    "image": (
        (182, 173, 160, 255), (228, 222, 212, 255), (130, 123, 112, 56),
        (58, 54, 48, 56), (182, 173, 160, 56), (130, 123, 112, 20),
    ),
}

# Décorations neutres du panneau (obs-style.css)
PANEL_BORDER = (255, 255, 255, 19)  # border: 1px solid rgba(255,255,255,0.075)
PANEL_INSET_TOP = (255, 255, 255, 11)  # box-shadow inset 0 1px 0 …0.045
PANEL_INSET_BOTTOM = (255, 255, 255, 5)  # box-shadow inset 0 -1px 0 …0.02
SHEEN_COLOR = (255, 255, 255, 10)  # .lt-sheen : rgba(255,255,255,0.04)
TINT_RADIAL = (255, 255, 255, 10)  # .lt-body::after : radial 4 % blanc
REF_BG_NEUTRAL = (4, 9, 18, 87)  # --source-ref-bg : rgba(4,9,18,0.34)
# Hauteur de la pastille de source (.lt-kicker : icône 24 px + 6 px)
KICKER_HEIGHT = 36
REF_BORDER_NEUTRAL = (255, 255, 255, 20)  # rgba(255,255,255,0.08)

# Entrée animée du bandeau : courbe et distance de la page OBS
EASE_IN_CONTROLS = (0.16, 1.0, 0.3, 1.0)  # cubic-bezier(0.16, 1, 0.3, 1)
_TWEEN_DISTANCE = 54  # getDirectionalOffset(direction, 54)


def _cubic_bezier(progress: float, controls: tuple = EASE_IN_CONTROLS) -> float:
    """Évalue une courbe de Bézier CSS (x → y) par dichotomie."""
    p = max(0.0, min(1.0, float(progress)))
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    x1, y1, x2, y2 = controls

    def _axis(t: float, a: float, b: float) -> float:
        return 3.0 * a * t * (1 - t) ** 2 + 3.0 * b * t * t * (1 - t) + t**3

    low, high = 0.0, 1.0
    for _ in range(24):
        mid = (low + high) / 2.0
        if _axis(mid, x1, x2) < p:
            low = mid
        else:
            high = mid
    return _axis((low + high) / 2.0, y1, y2)


def animation_total_ms(cfg_payload: dict[str, Any] | None, text: str = "") -> int:
    """Durée totale de l'entrée du bandeau (ms), 0 si aucune animation.

    Reproduit les temporisations de la page : révélation mot à mot (délai
    initial + cadence + queue du badge) ou animation du bloc entier.
    """
    cfg = OverlayStyleConfig.from_payload(cfg_payload)
    if not cfg.animation_enabled or cfg.animation_type == "none":
        return 0
    duration = max(0, int(cfg.animation_duration))
    if duration <= 0:
        return 0
    if cfg.animation_style != "words":
        return duration
    words = [w for w in str(text or "").split() if w]
    stagger = min(46, max(16, round(980 / len(words)))) if words else 0
    start_delay = 150
    tail_delay = start_delay + min(len(words) * stagger, 480)
    tail_duration = min(max(duration, 260), 520)
    return int(tail_delay + tail_duration)

# Libellés du kicker (obs-script.js : getSourcePresentation)
SOURCE_LABELS = {
    "bible": "Bible",
    "hymn": "Cantique",
    "sermon": "Prédication",
    "expose": "Exposé",
    "image": "Visuel",
    "custom": "Projection",
}


def source_palette(source: str) -> tuple:
    """Palette (accent, accent2, halo, kicker, bordure, teinte) d'une source."""
    return SOURCE_PALETTES.get(str(source or "").lower(), SOURCE_PALETTES["custom"])


# Cache des couches lourdes : les trames d'animation ne recalculent que le
# contenu animé (image identique à l'octet près pour les mêmes réglages).
_LAYER_CACHE: dict = {}
_LAYER_CACHE_LIMIT = 48


def _cached(key, builder):
    """Résultat mémoïsé d'un calcul d'image (jamais muté par les appelants)."""
    hit = _LAYER_CACHE.get(key)
    if hit is None:
        hit = builder()
        if len(_LAYER_CACHE) >= _LAYER_CACHE_LIMIT:
            _LAYER_CACHE.clear()
        _LAYER_CACHE[key] = hit
    return hit


def clear_layer_cache() -> None:
    """Vide le cache (changement de réglages, tests)."""
    _LAYER_CACHE.clear()


def _with_alpha(layer, factor: float):
    """Nouvelle image dont l'opacité est multipliée (sans muter l'original)."""
    from PIL import Image  # type: ignore

    if factor >= 0.999:
        return layer
    out = layer.copy()
    out.putalpha(out.getchannel("A").point(lambda a: int(a * float(factor))))
    return out


def _blend(
    fill: tuple[int, int, int, int], base: tuple[int, int, int], alpha: float
) -> tuple[int, int, int, int]:
    """Compose une couleur semi-transparente sur une base opaque."""
    a = max(0.0, min(1.0, float(alpha)))
    return (
        int(base[0] + (fill[0] - base[0]) * a),
        int(base[1] + (fill[1] - base[1]) * a),
        int(base[2] + (fill[2] - base[2]) * a),
        fill[3] if fill[3] >= 255 else int(fill[3] * a) if a < 1.0 else fill[3],
    )


def _linear_gradient(size: tuple[int, int], stops, angle_deg: float):
    """Dégradé linéaire CSS (0° = vers le haut, 90° = vers la droite)."""
    key = (
        "grad",
        int(size[0]),
        int(size[1]),
        tuple((round(float(s[0]), 4), tuple(int(v) for v in s[1])) for s in stops),
        round(float(angle_deg), 3),
    )
    return _cached(key, lambda: _linear_gradient_build(size, stops, angle_deg))


def _linear_gradient_build(size: tuple[int, int], stops, angle_deg: float):
    """Calcul effectif d'un dégradé linéaire (mémoïsé)."""
    import math

    import numpy as np
    from PIL import Image  # type: ignore

    width, height = max(1, int(size[0])), max(1, int(size[1]))
    rad = math.radians(float(angle_deg or 0.0))
    dx, dy = math.sin(rad), -math.cos(rad)
    xs = np.arange(width, dtype="float32") - (width - 1) / 2.0
    ys = np.arange(height, dtype="float32") - (height - 1) / 2.0
    projection = ys[:, None] * dy + xs[None, :] * dx
    span = float(projection.max() - projection.min())
    t = (projection - projection.min()) / span if span > 0 else np.zeros_like(projection)
    positions = [float(s[0]) for s in stops]
    # Table de 256 teintes : bien plus rapide qu'une interpolation par pixel.
    lut = np.arange(256, dtype="float32") / 255.0
    table = np.zeros((256, 4), dtype="uint8")
    for channel in range(4):
        values = np.interp(lut, positions, [float(s[1][channel]) for s in stops])
        table[:, channel] = np.clip(values, 0, 255).astype("uint8")
    indexes = np.clip((t * 255.0).round(), 0, 255).astype("uint8")
    return Image.fromarray(table[indexes], "RGBA")


def _radial_fade(size: tuple[int, int], origin, radius_ratio: float, color):
    """Halo radial CSS : dégradé circulaire depuis `origin` (fractions 0..1)."""
    key = (
        "radial",
        int(size[0]),
        int(size[1]),
        round(float(origin[0]), 3),
        round(float(origin[1]), 3),
        round(float(radius_ratio), 3),
        tuple(int(v) for v in color),
    )
    return _cached(key, lambda: _radial_fade_build(size, origin, radius_ratio, color))


def _radial_fade_build(size: tuple[int, int], origin, radius_ratio: float, color):
    """Calcul effectif d'un halo radial (mémoïsé)."""
    import numpy as np
    from PIL import Image  # type: ignore

    width, height = max(1, int(size[0])), max(1, int(size[1]))
    xs = np.arange(width, dtype="float32") / max(1, width - 1)
    ys = np.arange(height, dtype="float32") / max(1, height - 1)
    dist = np.sqrt(
        ((xs[None, :] - float(origin[0])) * (width / max(1, height))) ** 2
        + (ys[:, None] - float(origin[1])) ** 2
    )
    t = np.clip(1.0 - dist / max(1e-6, float(radius_ratio)), 0.0, 1.0)
    arr = np.zeros((height, width, 4), dtype="uint8")
    for channel in range(3):
        arr[:, :, channel] = int(color[channel])
    arr[:, :, 3] = (t * color[3]).astype("uint8")
    return Image.fromarray(arr, "RGBA")


def _rounded_mask(size: tuple[int, int], radius: int):
    key = ("mask", int(size[0]), int(size[1]), int(radius))
    return _cached(key, lambda: _rounded_mask_build(size, radius))


def _rounded_mask_build(size: tuple[int, int], radius: int):
    from PIL import Image, ImageDraw  # type: ignore

    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, max(0, size[0] - 1), max(0, size[1] - 1)],
        radius=max(0, int(radius)),
        fill=255,
    )
    return mask


def _soft_shadow(panel_size, radius, offset, blur, color, spread=0):
    """Ombre portée CSS : rect rétréci du `spread`, décalé, puis flouté.

    Renvoie ``(couche, marge)`` : la couche déborde de ``marge`` pixels
    autour du panneau pour que le flou ne soit pas rogné — l'appelant la
    compose à ``(x - marge, y - marge)``.
    """
    key = (
        "shadow",
        int(panel_size[0]),
        int(panel_size[1]),
        int(radius),
        int(offset[0]),
        int(offset[1]),
        float(blur),
        tuple(int(v) for v in color),
        int(spread),
    )
    return _cached(
        key, lambda: _soft_shadow_build(panel_size, radius, offset, blur, color, spread)
    )


def _soft_shadow_build(panel_size, radius, offset, blur, color, spread=0):
    from PIL import Image, ImageDraw, ImageFilter  # type: ignore

    width, height = max(1, int(panel_size[0])), max(1, int(panel_size[1]))
    margin = int(max(2.0, blur * 1.6))
    layer = Image.new("RGBA", (width + margin * 2, height + margin * 2), (0, 0, 0, 0))
    left = margin + spread + int(offset[0])
    top = margin + spread + int(offset[1])
    right = margin + width - spread + int(offset[0])
    bottom = margin + height - spread + int(offset[1])
    ImageDraw.Draw(layer).rounded_rectangle(
        [left, top, max(left, right), max(top, bottom)],
        radius=max(0, int(radius - spread)),
        fill=color,
    )
    if blur > 0:
        layer = layer.filter(ImageFilter.GaussianBlur(blur / 2.0))
    return layer, margin


_FONT_PATH_CACHE: dict = {}


def _font_file(family: str, weight: str) -> str | None:
    """Fichier TTF embarqué correspondant à (famille, graisse).

    La page OBS charge les Google Fonts par @font-face ; ici on retrouve le
    fichier dans ``assets/fonts`` — sinon la famille retomberait sur Arial.
    """
    key = (str(family or ""), str(weight or ""))
    if key in _FONT_PATH_CACHE:
        return _FONT_PATH_CACHE[key]
    found = _font_file_lookup(family, weight)
    _FONT_PATH_CACHE[key] = found
    return found


def _font_file_lookup(family: str, weight: str) -> str | None:
    from app.utils.app_paths import assets_dir

    fonts_dir = assets_dir() / "fonts"
    if not fonts_dir.is_dir():
        return None
    wanted = str(family or "").strip().lower().replace(" ", "").replace("_", "")
    if not wanted or wanted in ("system-ui", "sans-serif", "segoeui"):
        return None
    weight = str(weight or "").strip().lower()
    bold = weight in ("bold", "bolder", "700", "800", "900", "600", "semibold")
    light = weight in ("light", "lighter", "300", "200", "100")

    candidates: list[str] = []
    for folder in sorted(fonts_dir.iterdir()):
        if not folder.is_dir():
            continue
        if folder.name.lower().replace(" ", "").replace("_", "") != wanted:
            continue
        files = sorted(folder.rglob("*.ttf"))
        if not files:
            continue
        def rank(path) -> tuple[int, str]:
            name = path.name.lower()
            if "italic" in name:
                return (9, name)
            if bold and ("bold" in name or "wght" in name or "700" in name):
                return (0, name)
            if light and ("light" in name or "300" in name):
                return (0, name)
            if "regular" in name:
                return (1, name)
            return (2, name)

        candidates.extend(str(p) for p in sorted(files, key=rank))
        break
    return candidates[0] if candidates else None


def _tracked_width(draw, line: str, font, spacing: float) -> float:
    if not line:
        return 0.0
    return sum(draw.textlength(ch, font=font) for ch in line) + spacing * max(
        0, len(line) - 1
    )


def _draw_tracked(
    draw,
    x: float,
    y: float,
    line: str,
    font,
    fill,
    spacing: float,
    align: str,
    anchor_x: str,
    *,
    stroke_width: int = 0,
    stroke_fill=None,
) -> None:
    """Écrit une ligne avec interlettre (PIL n'a pas de tracking natif)."""
    if not line:
        return
    width = _tracked_width(draw, line, font, spacing)
    if anchor_x == "center":
        cursor = x - width / 2.0
    elif anchor_x == "right":
        cursor = x - width
    else:
        cursor = x
    for index, char in enumerate(line):
        draw.text(
            (cursor, y),
            char,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
            anchor="la",
        )
        cursor += draw.textlength(char, font=font)
        if index < len(line) - 1:
            cursor += spacing


def render_obs_overlay(
    cfg_payload: dict[str, Any] | None,
    slide: dict[str, Any] | None,
    width: int = 1920,
    height: int = 1080,
    *,
    text_scale: float = 1.0,
    offset_y: int = 0,
    key_rgb: tuple[int, int, int] | None = None,
    elapsed_ms: float | None = None,
) -> Any:
    """Compose la section texte « façon OBS » sur fond transparent.

    ``elapsed_ms`` rend une TRAME d'entrée animée (ms depuis l'arrivée du
    texte) : ``None`` produit l'état final, identique à la page stabilisée.

    Le rendu suit la page Navigateur OBS à la lettre (``obs-style.css``) :
    panneau à la largeur réglée, dégradé à l'angle choisi, éventuelle image
    de fond du bandeau, reflet, teinte de source, barre d'accent, kicker,
    texte (police, graisse, interlettre, contour, ombre, transformation),
    séparateur et badge de référence.

    ``text_scale`` (sortie HDMI) agrandit ou réduit typographie et marges
    internes sans toucher au style OBS partagé ; ``offset_y`` décale le
    bandeau verticalement (px @1080). À 1.0 et 0, le rendu est la copie
    exacte de la page OBS.

    ``key_rgb`` active le mode clé chroma (sortie HDMI) : le fond de
    l'appelant est la couleur de clé du mélangeur, donc aucun pixel ne
    doit rester semi-transparent (il deviendrait un mélange avec la clé —
    badge verdâtre, lettering délavé — que le mélangeur supprimerait).
    Le panneau est forcé opaque, chaque remplissage est aplati dessus et
    les accents trop proches de la clé sont remplacés par un neutre.

    Renvoie une image PIL RGBA, ou ``None`` quand il n'y a rien à afficher
    (slide masquée, texte et référence vides) — l'appelant n'a alors qu'à
    présenter son fond.
    """
    from PIL import Image, ImageChops, ImageDraw, ImageFilter  # type: ignore

    cfg = OverlayStyleConfig.from_payload(cfg_payload)

    scale = max(0.5, min(2.0, float(text_scale or 1.0)))
    if scale != 1.0:
        cfg.text_size = int(cfg.text_size * scale)
        cfg.ref_size = max(10, int(cfg.ref_size * scale))
        cfg.padding_horizontal = max(4, int(cfg.padding_horizontal * scale))
        cfg.padding_vertical = max(2, int(cfg.padding_vertical * scale))
        cfg.border_radius = int(cfg.border_radius * scale)
        cfg.letter_spacing = int(cfg.letter_spacing * scale)
    if offset_y:
        cfg.offset_y = int(cfg.offset_y) + int(offset_y)

    if not slide or bool(slide.get("hidden")):
        return None

    text = str(slide.get("text") or "")
    ref = str(slide.get("reference") or "")
    if not text.strip() and not ref.strip():
        return None

    transform = str(cfg.text_transform).lower()
    if transform == "uppercase":
        text = text.upper()
        ref = ref.upper()
    elif transform == "capitalize":
        text = text.title()
        ref = ref.title()

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    # ── Couleurs de source (accent, halo, kicker, teinte du corps) ──────
    source = str(slide.get("source") or "custom").lower()
    accent, accent_2, glow, kicker_bg, kicker_border, body_tint = source_palette(source)
    if str(cfg.accent_mode).lower() == "custom":
        custom = _parse_rgba_tuple(cfg.accent_color, accent)
        accent = (custom[0], custom[1], custom[2], accent[3])
        accent_2 = (custom[0], custom[1], custom[2], accent_2[3])
        glow = (custom[0], custom[1], custom[2], 61)  # rgba(accent, 0.24)
    if key_rgb is not None and accent_too_close_to_key(accent, key_rgb):
        # Accent de source trop proche de la couleur de clé : le mélangeur le
        # supprimerait (barre/liseré verts de la Bible sur une clé verte) →
        # tout le décor coloré passe en neutre key-safe.
        accent = (*_KEY_SAFE_ACCENT, accent[3])
        accent_2 = (*_KEY_SAFE_ACCENT_2, accent_2[3])
        glow = (*_KEY_SAFE_ACCENT, 40)
        kicker_bg = (*_KEY_SAFE_ACCENT_2, 40)
        kicker_border = (*_KEY_SAFE_ACCENT, 51)
        body_tint = (*_KEY_SAFE_ACCENT, 20)

    text_fill = _parse_rgba_tuple(cfg.text_color, (255, 255, 255, 250))
    ref_fill = _parse_rgba_tuple(cfg.ref_color, (255, 255, 255, 178))
    shadow_fill = _parse_rgba_tuple(cfg.shadow_color, (0, 0, 0, 153))
    stroke_fill = _parse_rgba_tuple(cfg.stroke_color, (0, 0, 0, 204))

    # Mode clé chroma : base opaque sur laquelle aplatir les remplissages
    # semi-transparents (le panneau, ou la clé elle-même sans panneau).
    if key_rgb is not None:
        if cfg.bg_enabled:
            parsed = _parse_rgba_tuple(cfg.bg_color, (8, 15, 28, 255))
            base_rgb = (parsed[0], parsed[1], parsed[2])
        else:
            base_rgb = tuple(key_rgb)
    else:
        base_rgb = None

    def _flat(fill):
        """Aplatit un remplissage semi-transparent sur la base opaque.

        Sans cela, badge (alpha 87), séparateur (alpha 107) et lettering
        gardent leur transparence : composés sur la couleur de clé, ils
        deviennent des mélanges verdâtres que le mélangeur supprime.
        """
        if base_rgb is None:
            return fill
        a = fill[3] / 255.0
        if a >= 1.0:
            return (fill[0], fill[1], fill[2], 255)
        return (
            int(base_rgb[0] + (fill[0] - base_rgb[0]) * a),
            int(base_rgb[1] + (fill[1] - base_rgb[1]) * a),
            int(base_rgb[2] + (fill[2] - base_rgb[2]) * a),
            255,
        )

    # ── Polices (fichiers embarqués, graisse respectée) ─────────────────
    def _font(px: int, weight: str | None = None):
        from PIL import ImageFont  # type: ignore

        size = max(8, int(round(px)))
        path = _font_file(cfg.font_family, weight or cfg.font_weight)
        for candidate in (path, "arial.ttf", "DejaVuSans.ttf"):
            if not candidate:
                continue
            try:
                return ImageFont.truetype(candidate, size)
            except Exception:
                continue
        return ImageFont.load_default()

    layout_mode = str(cfg.layout_mode or "lower_third").lower()
    pad_x = max(0, int(cfg.padding_horizontal))
    pad_y = max(0, int(cfg.padding_vertical))
    radius = max(0, int(cfg.border_radius))
    inner_gap = 12  # .lt-inner { gap: 12px; padding: 2px 0 }
    inner_pad_y = 2
    line_height_factor = 1.0

    # Réglages propres à chaque mode géométrique (obs-style.css).
    if layout_mode == "subtitle":
        pad_y = max(16, int(round(pad_y * 0.65)))
        radius = min(radius, 20)
        inner_gap = 6
        line_height_factor = 1.0  # max(1.12, line-height) appliqué plus bas
    elif layout_mode == "side_panel":
        inner_gap = max(10, min(int(height * 0.014), 18))
    elif layout_mode == "focus_card":
        inner_gap = max(10, min(int(height * 0.016), 20))

    # Zone utile : root padding = marge de bord + zone sûre (obs-script.js)
    safe_margin = int(round(min(width, height) * cfg.safe_area_percent / 100))
    inset = max(0, int(cfg.edge_margin)) + safe_margin
    available_w = max(160, width - inset * 2)
    available_h = max(120, height - inset * 2)

    # Largeur du bandeau : `width: var(--max-width)` (page OBS), plancher 390 px,
    # plafonds propres aux modes (`min(var(--max-width), …)`).
    band_w = int(width * max(0, min(140, int(cfg.max_width))) / 100)
    if layout_mode == "subtitle":
        band_w = min(band_w, 1680)
    elif layout_mode == "side_panel":
        band_w = min(band_w, 860)
    elif layout_mode == "focus_card":
        band_w = min(band_w, 1180)
    band_w = max(390, min(band_w, available_w))
    text_area_w = max(120, band_w - pad_x * 2)

    # ── Texte : lignes, mesures, auto-ajustement ────────────────────────
    draw_probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))

    def _lines_for(value: str, font) -> list[str]:
        spacing = int(cfg.letter_spacing)
        wrapped = _wrap_text(draw_probe, value, font, text_area_w)
        lines_out: list[str] = []
        for raw_line in wrapped.split("\n"):
            if _tracked_width(draw_probe, raw_line, font, spacing) <= text_area_w:
                lines_out.append(raw_line)
                continue
            # Un mot plus large que la zone (URL, mot composé) : coupe nette.
            current = ""
            for char in raw_line:
                candidate = current + char
                if (
                    _tracked_width(draw_probe, candidate, font, spacing)
                    > text_area_w
                    and current
                ):
                    lines_out.append(current)
                    current = char
                else:
                    current = candidate
            if current:
                lines_out.append(current)
        return lines_out

    def _measure(size: int, ref_size: int):
        font_text = _font(size, cfg.font_weight)
        font_ref = _font(ref_size, "bold")  # .lt-ref-text { font-weight: 700 }
        body_lines = _lines_for(text, font_text) if text.strip() else []
        ref_lines = _lines_for(ref, font_ref) if (cfg.show_reference and ref.strip()) else []
        line_h = size * max(
            1.12 if layout_mode == "subtitle" else 1.0,
            float(cfg.line_height),
        )
        ref_line_h = ref_size * 1.22
        return font_text, font_ref, body_lines, ref_lines, line_h, ref_line_h

    (
        font_text,
        font_ref,
        body_lines,
        ref_lines,
        line_h,
        ref_line_h,
    ) = _measure(cfg.text_size, cfg.ref_size)

    def _content_height(
        lines: list[str], font, lh: float, refs: list[str], ref_font, ref_lh: float
    ) -> int:
        height_total = 0
        blocks = 0
        if cfg.show_kicker and cfg.bg_enabled:
            # Pastille de source (24 px d'icône + 6 px de marge haute et basse)
            height_total += KICKER_HEIGHT
            blocks += 1
        if lines:
            height_total += int(lh * len(lines))
            blocks += 1
        show_ref = cfg.show_reference and bool(refs) and cfg.reference_style != "inline"
        if show_ref:
            if cfg.reference_style == "badge":
                height_total += int(ref_lh * len(refs)) + 14  # padding 7px
            else:
                height_total += int(ref_lh * len(refs))
            blocks += 1
        if refs:
            blocks += 1  # le séparateur accompagne la référence
        if blocks > 1:
            height_total += inner_gap * (blocks - 1)
        return height_total + inner_pad_y * 2

    content_h = _content_height(
        body_lines, font_text, line_h, ref_lines, font_ref, ref_line_h
    )

    # Auto-ajustement : la page ne rétrécit QUE si `auto_fit` est actif et
    # `uniform_text_size` désactivé (obs-script.js : fitTextToViewport).
    if cfg.auto_fit and not cfg.uniform_text_size:
        mode_caps = {
            "lower_third": 5,
            "fullscreen": 8,
            "side_panel": 10,
            "subtitle": 3,
            "focus_card": 7,
        }
        max_lines = min(max(1, int(cfg.max_lines)), mode_caps.get(layout_mode, cfg.max_lines))
        floor = max(12, int(cfg.min_text_size))
        size = max(floor, int(cfg.text_size))
        ref_size = max(10, int(cfg.ref_size))
        steps = 0
        while steps < 40:
            fits = (
                content_h + pad_y * 2 <= available_h and len(body_lines) <= max_lines
            )
            if fits or size <= floor:
                break
            size = max(floor, size - 2)
            ref_size = max(10, ref_size - 1)
            font_text, font_ref, body_lines, ref_lines, line_h, ref_line_h = _measure(
                size, ref_size
            )
            content_h = _content_height(
                body_lines, font_text, line_h, ref_lines, font_ref, ref_line_h
            )
            steps += 1

    # ── Géométrie du panneau ────────────────────────────────────────────
    band_h = min(content_h + pad_y * 2, available_h)
    if layout_mode == "fullscreen":
        band_w = available_w
        band_h = available_h
    elif layout_mode == "side_panel":
        band_h = available_h
    elif layout_mode == "focus_card":
        # `min-height: min(52vh, 560px)`
        band_h = max(band_h, min(int(height * 0.52), 560))

    band_align = str(cfg.band_align).lower()
    if layout_mode == "side_panel":
        band_x = width - band_w - inset if cfg.panel_side == "right" else inset
    elif band_align == "left":
        band_x = inset
    elif band_align == "right":
        band_x = width - band_w - inset
    else:
        band_x = int((width - band_w) / 2)

    position = str(cfg.position).lower()
    if layout_mode in ("fullscreen", "side_panel", "focus_card"):
        band_y = int((height - band_h) / 2)
    elif position == "top":
        band_y = inset
    elif position == "center":
        band_y = int((height - band_h) / 2)
    else:
        band_y = height - band_h - inset

    band_x += int(cfg.offset_x)
    band_y += int(cfg.offset_y)
    band_x = max(-band_w, min(width, band_x))
    band_y = max(-band_h, min(height, band_y))

    panel = Image.new("RGBA", (band_w, band_h), (0, 0, 0, 0))
    panel_draw = ImageDraw.Draw(panel)

    # ── Fond du panneau : image de bandeau, dégradé ou couleur ──────────
    if cfg.bg_enabled:
        bg = _parse_rgba_tuple(cfg.bg_color, (8, 13, 23, int(0.92 * 255)))
        bg_alpha = int(255 * max(0.0, min(1.0, cfg.bg_opacity)))
        if key_rgb is not None:
            # Mode clé chroma : panneau totalement opaque — sa transparence
            # laisserait voir la couleur de clé.
            bg_alpha = 255
        bg = (bg[0], bg[1], bg[2], bg_alpha)

        painted = False
        if cfg.bg_mode == "image" and cfg.bg_image.strip():
            painted = _paint_band_image(panel, cfg, bg)
        if not painted:
            if cfg.bg_gradient_enabled and cfg.bg_color_2.strip():
                bg2 = _parse_rgba_tuple(cfg.bg_color_2, bg)
                bg2 = (bg2[0], bg2[1], bg2[2], bg_alpha)
                panel.paste(
                    _linear_gradient(
                        (band_w, band_h),
                        ((0.0, bg), (1.0, bg2)),
                        cfg.bg_gradient_angle,
                    ),
                    (0, 0),
                )
            else:
                panel_draw.rectangle([0, 0, band_w, band_h], fill=bg)

        # Teinte de source (radial + diagonale) puis reflet haut
        if cfg.bg_mode != "image":
            if layout_mode == "focus_card":
                # `radial-gradient(circle at 50% 0%, rgba(255,255,255,0.05), …)`
                panel.alpha_composite(
                    _radial_fade((band_w, band_h), (0.5, 0.0), 0.40, (255, 255, 255, 13))
                )
                panel.alpha_composite(
                    _linear_gradient(
                        (band_w, band_h),
                        (
                            (0.0, body_tint if body_tint[3] else (255, 255, 255, 0)),
                            (
                                0.46,
                                (body_tint[0], body_tint[1], body_tint[2], 0)
                                if body_tint[3]
                                else (255, 255, 255, 0),
                            ),
                        ),
                        145.0,
                    )
                )
                tint = _radial_fade((band_w, band_h), (0.12, 0.0), 0.26, (0, 0, 0, 0))
            else:
                tint = _radial_fade((band_w, band_h), (0.12, 0.0), 0.26, TINT_RADIAL)
            panel.alpha_composite(tint)
            if body_tint[3] > 0:
                panel.alpha_composite(
                    _linear_gradient(
                        (band_w, band_h),
                        ((0.0, body_tint), (0.46, (body_tint[0], body_tint[1], body_tint[2], 0))),
                        135.0,
                    )
                )
        sheen_h = max(1, int(band_h * 0.34))
        panel.alpha_composite(
            _linear_gradient(
                (band_w, sheen_h),
                ((0.0, SHEEN_COLOR), (1.0, (SHEEN_COLOR[0], SHEEN_COLOR[1], SHEEN_COLOR[2], 0))),
                180.0,
            ),
            (0, 0),
        )

    # ── Contenu du bandeau (kicker, texte, séparateur, référence) ───────
    content_layer = Image.new("RGBA", (band_w, band_h), (0, 0, 0, 0))
    content = ImageDraw.Draw(content_layer)
    align_mode = str(cfg.align).lower()
    if layout_mode == "side_panel":
        # `#root.layout-side_panel .lt-inner` : texte aligné à gauche.
        align_mode = "left"
    if align_mode not in ("left", "right"):
        align_mode = "center"
    anchor_x = {"left": "left", "center": "center", "right": "right"}[align_mode]
    stack_x = pad_x
    stack_w = max(60, band_w - pad_x * 2)
    text_anchor_x = {
        "left": float(stack_x),
        "center": stack_x + stack_w / 2.0,
        "right": float(stack_x + stack_w),
    }[align_mode]

    tween = _tween_plan(cfg, source, text, elapsed_ms)
    kicker_visible = (
        bool(cfg.show_kicker)
        and cfg.bg_enabled
        and layout_mode != "subtitle"  # `layout-subtitle` masque la pastille
    )

    # Décalage vertical global du bloc (mode panneau latéral / carte focus :
    # le contenu est centré verticalement dans un panneau haut).
    if layout_mode == "side_panel":
        stack_pad_y = max(18, min(int(height * 0.03), 42))
    elif layout_mode == "focus_card":
        stack_pad_y = max(10, min(int(height * 0.016), 20))
        # `.lt-inner { width: min(100%, 920px); margin: 0 auto }`
        if band_w > 920:
            stack_x = (band_w - 920) // 2
            stack_w = 920
            text_anchor_x = {
                "left": float(stack_x),
                "center": stack_x + stack_w / 2.0,
                "right": float(stack_x + stack_w),
            }[align_mode]
    else:
        stack_pad_y = pad_y
    cursor_y = stack_pad_y + inner_pad_y
    # Panneau latéral : le contenu est centré verticalement.
    if layout_mode == "side_panel":
        content_h_side = cursor_y + int(line_h * len(body_lines))
        if kicker_visible:
            content_h_side += KICKER_HEIGHT + inner_gap
        cursor_y = max(cursor_y, int((band_h - (content_h_side - stack_pad_y)) / 2))

    # Kicker : pastille + icône de source + libellé (obs-script.js)
    if kicker_visible:
        kicker_h = KICKER_HEIGHT
        label = SOURCE_LABELS.get(source, SOURCE_LABELS["custom"])
        kicker_dy = -10 * (1.0 - tween["kicker"])  # translateY(-10px) → 0
        kicker_layer = Image.new("RGBA", (band_w, band_h), (0, 0, 0, 0))
        kicker_draw = ImageDraw.Draw(kicker_layer)
        _draw_kicker(
            kicker_draw, stack_x, cursor_y + kicker_dy, kicker_h, label, source,
            accent, accent_2, glow, kicker_bg, kicker_border, _flat, key_rgb,
            align=align_mode, stack_w=stack_w,
        )
        _apply_alpha(kicker_layer, tween["kicker"])
        content_layer.alpha_composite(kicker_layer)
        cursor_y += kicker_h + inner_gap

    # Texte principal : ombre portée, contour, interlettre, entrée animée
    stroke_px = (
        int(round(cfg.stroke_width / 2.0))
        if (cfg.text_stroke and cfg.stroke_width > 0)
        else 0
    )
    text_layer = Image.new("RGBA", (band_w, band_h), (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(text_layer)
    if body_lines:
        if tween["words"] is None:
            _draw_lines(
                text_draw, text_anchor_x, cursor_y, body_lines, font_text,
                _flat(text_fill), cfg.letter_spacing, line_h, anchor_x,
                stroke_width=stroke_px,
                stroke_fill=_flat(stroke_fill) if stroke_px else None,
            )
        else:
            _draw_words_animated(
                text_draw, body_lines, font_text, text_anchor_x, cursor_y,
                line_h, cfg.letter_spacing, _flat(text_fill), align_mode,
                tween["words"],
                stroke_width=stroke_px,
                stroke_fill=_flat(stroke_fill) if stroke_px else None,
            )
        cursor_y += int(line_h * len(body_lines))

    content_layer.alpha_composite(text_layer)

    # Séparateur : ligne dégradée de 620 px max, 1 px, opacité 0.52
    show_ref = cfg.show_reference and bool(ref_lines)
    tail_layer = Image.new("RGBA", (band_w, band_h), (0, 0, 0, 0))
    tail_draw = ImageDraw.Draw(tail_layer)
    if ref_lines and cfg.reference_style != "inline" and layout_mode != "subtitle":
        divider_y = cursor_y + (inner_gap // 2 if body_lines else 0)
        line_w = min(stack_w, 620)
        if align_mode == "left":
            line_x = stack_x
        elif align_mode == "right":
            line_x = stack_x + stack_w - line_w
        else:
            line_x = stack_x + int((stack_w - line_w) / 2)
        divider = _linear_gradient(
            (line_w, 1),
            (
                (0.0, (255, 255, 255, 0)),
                (0.25, (255, 255, 255, 31)),
                (0.5, (255, 255, 255, 107)),
                (0.75, (255, 255, 255, 31)),
                (1.0, (255, 255, 255, 0)),
            ),
            90.0,
        )
        divider = _with_alpha(divider, 0.52)
        tail_layer.alpha_composite(divider, (line_x, divider_y + 1))
        cursor_y = divider_y + 2 + inner_gap // 2

    if show_ref:
        cursor_y = _draw_reference(
            tail_layer, tail_draw, cfg, ref_lines, font_ref, ref_line_h,
            stack_x, stack_w, cursor_y, align_mode, text_anchor_x, anchor_x,
            ref_fill, _flat, key_rgb,
        )
    if tween["active"] and tween["tail"] < 1.0:
        _apply_alpha(tail_layer, tween["tail"])
    content_layer.alpha_composite(tail_layer)

    if tween["active"] and tween["block"] is not None:
        content_layer = _animate_block(content_layer, tween)

    # ── Assemblage : ombre portée, panneau rogné à ses coins, contenu ───
    if key_rgb is None:
        # Page OBS : `drop-shadow(0 28px 72px -26px rgba(0,0,0,0.74))` sur le
        # conteneur, puis `0 18px 44px rgba(0,0,0,0.28)` sur le panneau.
        for blur, alpha, spread, dy in ((72, 189, 26, 28), (44, 71, 0, 18)):
            shadow, margin = _soft_shadow(
                (band_w, band_h), radius, (0, dy), blur, (0, 0, 0, alpha), spread
            )
            img.alpha_composite(shadow, (band_x - margin, band_y - margin))

    band_layer = Image.new("RGBA", (band_w, band_h), (0, 0, 0, 0))
    band_layer.alpha_composite(panel)
    band_layer.alpha_composite(content_layer)
    if cfg.bg_enabled:
        border_layer = Image.new("RGBA", (band_w, band_h), (0, 0, 0, 0))
        border_draw = ImageDraw.Draw(border_layer)
        border_draw.rounded_rectangle(
            [0, 0, band_w - 1, band_h - 1],
            radius=radius,
            outline=_flat(PANEL_BORDER),
            width=1,
        )
        if key_rgb is None:
            border_draw.line(
                [(radius // 2, 1), (band_w - radius // 2, 1)],
                fill=PANEL_INSET_TOP,
            )
            border_draw.line(
                [(radius // 2, band_h - 2), (band_w - radius // 2, band_h - 2)],
                fill=PANEL_INSET_BOTTOM,
            )
        band_layer.alpha_composite(border_layer)

    # Barre d'accent (::before, 4 px) et liseré (3 px) du bas du panneau
    if cfg.bg_enabled and cfg.show_accent_bar:
        _draw_accent_decor(
            band_layer, band_w, band_h, pad_x, accent, accent_2,
            tween["strip"], layout_mode, str(cfg.panel_side),
        )

    # Le contenu ne dépasse jamais du panneau (overflow: hidden côté CSS)
    mask = _rounded_mask((band_w, band_h), radius)
    band_layer.putalpha(
        ImageChops.multiply(band_layer.getchannel("A"), mask)
    )
    img.alpha_composite(band_layer, (band_x, band_y))

    if key_rgb is not None:
        # Mode clé chroma : aucune opacité globale — elle réintroduirait
        # de la transparence sur la couleur de clé.
        return img
    opacity = max(0.0, min(1.0, float(cfg.opacity)))
    if opacity < 1.0:
        alpha_img = img.getchannel("A").point(lambda a: int(a * opacity))
        img.putalpha(alpha_img)
    return img


def _flatten_layer(layer, base_rgb, opacity: float):
    """Aplatit une couche semi-transparente sur une base opaque."""
    from PIL import Image  # type: ignore

    if base_rgb is None:
        return layer
    out = Image.new("RGBA", layer.size, (*base_rgb, 255))
    tmp = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    tmp.alpha_composite(layer)
    tmp.putalpha(tmp.getchannel("A").point(lambda a: int(a * opacity)))
    out.alpha_composite(tmp)
    return out


def _paint_band_image(panel, cfg: OverlayStyleConfig, bg) -> bool:
    """Image de fond DANS le bandeau (`.lt-bg-image` + dimmer)."""
    from PIL import Image, ImageOps  # type: ignore

    cache_key = (
        "band_image",
        str(cfg.bg_image),
        int(panel.size[0]),
        int(panel.size[1]),
        str(cfg.bg_image_fit),
        round(float(cfg.background_dimmer), 3),
    )
    cached = _LAYER_CACHE.get(cache_key)
    if cached is None:
        cached = _paint_band_image_build(cfg, panel.size)
        if cached is None:
            return False
        if len(_LAYER_CACHE) >= _LAYER_CACHE_LIMIT:
            _LAYER_CACHE.clear()
        _LAYER_CACHE[cache_key] = cached
    panel.alpha_composite(cached)
    return True


def _paint_band_image_build(cfg: OverlayStyleConfig, size):
    """Composition mémoïsée de l'image de fond du bandeau."""
    from PIL import Image, ImageOps  # type: ignore

    try:
        with Image.open(cfg.bg_image) as raw:
            image = ImageOps.exif_transpose(raw).convert("RGB")
            image.load()
    except Exception:
        return False
    width, height = int(size[0]), int(size[1])
    if str(cfg.bg_image_fit).lower() == "contain":
        fitted = ImageOps.contain(image, (width, height), Image.LANCZOS)
    else:
        fitted = ImageOps.fit(image, (width, height), Image.LANCZOS)
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    layer.paste(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2))
    # `.lt-body.has-bg-image` : fond sombre + voile d'assombrissement réglable
    layer.alpha_composite(Image.new("RGBA", (width, height), (6, 12, 22, 89)))
    dimmer = max(0.0, min(0.85, float(cfg.background_dimmer)))
    if dimmer > 0:
        layer.alpha_composite(
            Image.new("RGBA", (width, height), (0, 0, 0, int(255 * dimmer)))
        )
    return layer


def _draw_lines(
    draw,
    anchor_x: float,
    y: float,
    lines: list[str],
    font,
    fill,
    letter_spacing: int,
    line_h: float,
    anchor: str,
    *,
    stroke_width: int = 0,
    stroke_fill=None,
) -> None:
    """Écrit un bloc de lignes avec interlettre, à la verticale donnée."""
    spacing = max(0, int(letter_spacing))
    for index, line in enumerate(lines):
        _draw_tracked(
            draw,
            anchor_x,
            y + index * line_h,
            line,
            font,
            fill,
            spacing,
            "left",
            anchor,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )


def _draw_kicker(
    draw,
    stack_x: int,
    y: int,
    height: int,
    label: str,
    source: str,
    accent,
    accent_2,
    glow,
    kicker_bg,
    kicker_border,
    flat,
    key_rgb,
    *,
    align: str,
    stack_w: int,
) -> int:
    """Pastille de source : icône circulaire + libellé (`.lt-kicker`)."""
    from PIL import Image, ImageDraw  # type: ignore

    # Coordonnées entières : l'entrée animée décale la pastille de quelques
    # dixièmes de pixel (PIL refuse les flottants pour les collages).
    stack_x = int(round(stack_x))
    y = int(round(y))
    label_font = None
    from PIL import ImageFont  # type: ignore

    try:
        path = _font_file("Poppins", "bold")
        label_font = ImageFont.truetype(path, 11) if path else None
    except Exception:
        label_font = None
    if label_font is None:
        try:
            label_font = ImageFont.truetype("arialbd.ttf", 11)
        except Exception:
            label_font = ImageFont.load_default()

    tracked = "  ".join(label.upper())  # letter-spacing 0.18em ≈ 2 px à 11 px
    try:
        label_w = int(draw.textlength(tracked, font=label_font))
    except Exception:
        label_w = 60
    icon = 24
    pad_left, pad_right, gap = 7, 13, 9
    pill_w = pad_left + icon + gap + label_w + pad_right

    if align == "left":
        pill_x = stack_x
    elif align == "right":
        pill_x = stack_x + stack_w - pill_w
    else:
        pill_x = stack_x + int((stack_w - pill_w) / 2)

    draw.rounded_rectangle(
        [pill_x, y, pill_x + pill_w, y + height],
        radius=height // 2,
        fill=flat(kicker_bg),
        outline=flat(kicker_border),
        width=1,
    )
    icon_x = pill_x + pad_left
    icon_y = y + (height - icon) // 2
    # Pastille d'icône : dégradé vertical accent → accent 2
    icon_layer = Image.new("RGBA", (icon, icon), (0, 0, 0, 0))
    icon_layer.paste(
        _linear_gradient((icon, icon), ((0.0, accent), (1.0, accent_2)), 180.0),
        (0, 0),
    )
    icon_mask = Image.new("L", (icon, icon), 0)
    ImageDraw.Draw(icon_mask).ellipse([0, 0, icon - 1, icon - 1], fill=255)
    icon_layer.putalpha(icon_mask)
    if key_rgb is None:
        glow_layer = Image.new("RGBA", (icon, icon), (0, 0, 0, 0))
        ImageDraw.Draw(glow_layer).ellipse([0, 0, icon - 1, icon - 1], fill=glow)
        draw._image.alpha_composite(glow_layer, (icon_x, icon_y))
    draw._image.alpha_composite(icon_layer, (icon_x, icon_y))
    _draw_source_glyph(draw, icon_x + icon / 2, icon_y + icon / 2, 13, source)

    draw.text(
        (icon_x + icon + gap, y + height / 2 + 1),
        tracked,
        font=label_font,
        fill=(255, 255, 255, 242),
        anchor="lm",
    )
    return pill_w


def _draw_source_glyph(draw, cx: float, cy: float, size: float, source: str) -> None:
    """Pictogramme simplifié de la source, dans la pastille du kicker."""
    half = size / 2.0
    white = (255, 255, 255, 247)
    if source == "hymn":
        draw.line([(cx - half * 0.3, cy + half * 0.5), (cx - half * 0.3, cy - half * 0.6)], fill=white, width=2)
        draw.line([(cx - half * 0.3, cy - half * 0.6), (cx + half * 0.7, cy - half)], fill=white, width=2)
        draw.ellipse([cx - half * 0.9, cy + half * 0.2, cx + half * 0.1, cy + half], outline=white, width=2)
    elif source == "sermon":
        draw.rounded_rectangle([cx - half * 0.35, cy - half, cx + half * 0.35, cy + half * 0.25], radius=3, outline=white, width=2)
        draw.arc([cx - half * 0.7, cy - half * 0.2, cx + half * 0.7, cy + half], 0, 180, fill=white, width=2)
        draw.line([(cx, cy + half * 0.7), (cx, cy + half)], fill=white, width=2)
    elif source == "expose":
        for index, width_factor in enumerate((1.0, 0.75, 0.5)):
            line_y = cy - half * 0.5 + index * half * 0.5
            draw.line([(cx - half * 0.8, line_y), (cx + half * 0.8 * width_factor, line_y)], fill=white, width=2)
    elif source == "image":
        draw.rounded_rectangle([cx - half * 0.9, cy - half * 0.7, cx + half * 0.9, cy + half * 0.7], radius=2, outline=white, width=2)
        draw.ellipse([cx - half * 0.5, cy - half * 0.4, cx - half * 0.1, cy], fill=white)
    elif source == "custom":
        draw.line([(cx - half * 0.8, cy + half * 0.8), (cx + half * 0.5, cy - half * 0.5)], fill=white, width=2)
        draw.polygon(
            [
                (cx + half * 0.4, cy - half * 0.6),
                (cx + half * 0.9, cy - half * 0.9),
                (cx + half * 0.7, cy - half * 0.4),
            ],
            fill=white,
        )
    else:  # bible : livre ouvert
        draw.line([(cx, cy - half * 0.6), (cx, cy + half * 0.7)], fill=white, width=2)
        draw.line([(cx - half * 0.9, cy - half * 0.5), (cx, cy - half * 0.6)], fill=white, width=2)
        draw.line([(cx + half * 0.9, cy - half * 0.5), (cx, cy - half * 0.6)], fill=white, width=2)
        draw.line([(cx - half * 0.9, cy - half * 0.5), (cx - half * 0.9, cy + half * 0.6)], fill=white, width=2)
        draw.line([(cx + half * 0.9, cy - half * 0.5), (cx + half * 0.9, cy + half * 0.6)], fill=white, width=2)
        draw.line([(cx - half * 0.9, cy + half * 0.6), (cx, cy + half * 0.7)], fill=white, width=2)
        draw.line([(cx + half * 0.9, cy + half * 0.6), (cx, cy + half * 0.7)], fill=white, width=2)


def _draw_reference(
    content_layer,
    draw,
    cfg: OverlayStyleConfig,
    ref_lines: list[str],
    font_ref,
    ref_line_h: float,
    stack_x: int,
    stack_w: int,
    y: float,
    align_mode: str,
    text_anchor_x: float,
    anchor_x: str,
    ref_fill,
    flat,
    key_rgb,
) -> float:
    """Badge de référence : pastille sombre (badge) ou texte nu (plain/inline)."""
    from PIL import Image, ImageDraw  # type: ignore

    style = str(cfg.reference_style).lower()
    if style == "plain":
        _draw_lines(
            draw, text_anchor_x, y, ref_lines, font_ref, flat(ref_fill),
            int(cfg.letter_spacing * 0.6), ref_line_h, anchor_x,
        )
        return y + ref_line_h * len(ref_lines)

    ref_text = "  ".join(line.upper() for line in ref_lines)  # 0.14em ≈ 2 px
    try:
        text_w = int(draw.textlength(ref_text.split("\n")[0], font=font_ref))
    except Exception:
        text_w = 120
    icon = 14
    pad_left, pad_right, gap = 12, 16, 9
    badge_w = min(stack_w, pad_left + icon + gap + text_w + pad_right)
    badge_h = int(ref_line_h) + 14
    if align_mode == "left":
        badge_x = stack_x
    elif align_mode == "right":
        badge_x = stack_x + stack_w - badge_w
    else:
        badge_x = stack_x + int((stack_w - badge_w) / 2)

    badge_layer = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
    badge_draw = ImageDraw.Draw(badge_layer)
    badge_draw.rounded_rectangle(
        [0, 0, badge_w - 1, badge_h - 1],
        radius=badge_h // 2,
        fill=flat(REF_BG_NEUTRAL),
        outline=flat(REF_BORDER_NEUTRAL),
        width=1,
    )
    # Petit pictogramme de référence (livre), opacité 0.7 comme la page
    icon_cx = pad_left + icon / 2.0
    icon_cy = badge_h / 2.0
    icon_color = (ref_fill[0], ref_fill[1], ref_fill[2], int(ref_fill[3] * 0.7))
    badge_draw.rectangle(
        [icon_cx - 5, icon_cy - 6, icon_cx + 5, icon_cy + 6], outline=icon_color, width=1
    )
    badge_draw.line([(icon_cx, icon_cy - 5), (icon_cx, icon_cy + 6)], fill=icon_color, width=1)
    badge_draw.text(
        (pad_left + icon + gap, badge_h / 2.0 + 1),
        ref_text.split("\n")[0],
        font=font_ref,
        fill=flat(ref_fill),
        anchor="lm",
    )
    content_layer.alpha_composite(badge_layer, (badge_x, int(y)))
    return y + badge_h


# ── Entrée animée (miroir de obs-script.js) ──────────────────────────────

# Presets « auto » par source (resolveSourceTransition)
AUTO_PRESETS = {
    "bible": ("fade", "up", 420),
    "hymn": ("slide", "up", 560),
    "sermon": ("fade", "up", 420),
    "expose": ("slide", "right", 520),
    "custom": ("scale", "up", 460),
    "image": ("fade", "up", 700),
}


def _direction_offset(direction: str, distance: float = _TWEEN_DISTANCE):
    """getDirectionalOffset : décalage d'entrée selon la direction."""
    d = str(direction or "up").lower()
    if d == "down":
        return 0.0, distance
    if d == "left":
        return -distance, 0.0
    if d == "right":
        return distance, 0.0
    return 0.0, -distance


def _progress(elapsed_ms: float, delay: float, duration: float, ease) -> float:
    """Progression 0→1 d'un élément (fill: backwards avant son délai)."""
    if duration <= 0:
        return 1.0
    raw = (float(elapsed_ms) - float(delay)) / float(duration)
    return ease(max(0.0, min(1.0, raw)))


def _tween_plan(
    cfg: "OverlayStyleConfig",
    source: str,
    text: str,
    elapsed_ms: float | None,
) -> dict:
    """Plan d'animation d'une trame (elapsed_ms=None → état final)."""
    plan = {
        "active": False,
        "kind": "fade",
        "dir": "up",
        "block": None,
        "kicker": 1.0,
        "words": None,
        "tail": 1.0,
        "strip": 1.0,
    }
    if elapsed_ms is None or not cfg.animation_enabled:
        return plan
    kind = str(cfg.animation_type or "fade").lower()
    direction = str(cfg.animation_direction or "up").lower()
    duration = max(0, int(cfg.animation_duration))
    if kind == "auto":
        preset = AUTO_PRESETS.get(str(source or "").lower(), AUTO_PRESETS["bible"])
        kind, direction, base = preset
        duration = max(duration or 520, base)
    if kind == "none" or duration <= 0:
        return plan

    plan["active"] = True
    plan["kind"] = kind
    plan["dir"] = direction
    # Barre d'accent : entrée en scaleX depuis la gauche.
    strip_duration = min(max(duration * 0.7, 240), 460)
    plan["strip"] = _progress(
        elapsed_ms, 0.0, strip_duration,
        lambda p: _cubic_bezier(p, (0.22, 1.0, 0.36, 1.0)),
    )
    words = [word for word in str(text or "").split() if word]
    if cfg.animation_style == "words" and words:
        stagger = min(46, max(16, round(980 / len(words))))
        word_duration = min(max(duration, 320), 620)
        plan["kicker"] = _progress(
            elapsed_ms, 40.0, min(duration, 380), _cubic_bezier
        )
        plan["words"] = [
            _progress(
                elapsed_ms, 150.0 + index * stagger, word_duration, _cubic_bezier
            )
            for index in range(len(words))
        ]
        plan["tail"] = _progress(
            elapsed_ms,
            150.0 + min(len(words) * stagger, 480),
            min(duration, 420),
            lambda p: _cubic_bezier(p, (0.0, 0.0, 0.58, 1.0)),
        )
        return plan

    plan["kicker"] = _progress(elapsed_ms, 0.0, duration, _cubic_bezier)
    plan["block"] = _progress(elapsed_ms, 0.0, duration, _cubic_bezier)
    plan["tail"] = plan["block"]
    return plan


def _apply_alpha(layer, progress: float):
    """Opacité globale d'un calque (animation d'entrée)."""
    if progress >= 0.999:
        return layer
    if progress <= 0.001:
        layer.putalpha(0)
        return layer
    layer.putalpha(layer.getchannel("A").point(lambda a: int(a * float(progress))))
    return layer


def _animate_block(layer, plan: dict):
    """Entrée du bloc : fondu, glissement, zoom, flou ou révélation."""
    from PIL import Image, ImageChops, ImageDraw, ImageFilter  # type: ignore

    progress = float(plan["block"])
    kind = str(plan["kind"])
    width, height = layer.size
    if kind == "slide":
        dx, dy = _direction_offset(plan["dir"])
        moved = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        moved.alpha_composite(
            layer, (int(dx * (1.0 - progress)), int(dy * (1.0 - progress)))
        )
        layer = moved
    elif kind == "scale":
        layer = _scaled_layer(layer, 0.94 + 0.06 * progress)
    elif kind == "blur":
        radius = 6.0 * (1.0 - progress)
        if radius > 0.4:
            layer = layer.filter(ImageFilter.GaussianBlur(radius))
        layer = _scaled_layer(layer, 1.006 - 0.006 * progress)
    elif kind == "reveal":
        # inset(...) depuis le côté opposé à la direction, coins 24 px
        mask = Image.new("L", layer.size, 0)
        if plan["dir"] == "left":
            box = (0, 0, int(width * progress), height)
        elif plan["dir"] == "right":
            box = (width - int(width * progress), 0, width, height)
        elif plan["dir"] == "down":
            box = (0, 0, width, int(height * progress))
        else:
            box = (0, height - int(height * progress), width, height)
        ImageDraw.Draw(mask).rounded_rectangle(box, radius=24, fill=255)
        layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))

    # La révélation démarre à 0,2 d'opacité (keyframes de la page).
    alpha = 0.2 + 0.8 * progress if kind == "reveal" else progress
    return _apply_alpha(layer, alpha)


def _scaled_layer(layer, scale: float):
    """Zoom d'un calque autour de son centre (aspect conservé)."""
    from PIL import Image  # type: ignore

    if abs(scale - 1.0) < 0.002:
        return layer
    width, height = layer.size
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    zoomed = layer.resize(new_size, Image.LANCZOS)
    canvas = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    canvas.alpha_composite(
        zoomed, ((width - new_size[0]) // 2, (height - new_size[1]) // 2)
    )
    return canvas


def _line_word_offsets(
    line: str, font, spacing: float, anchor_x: float, anchor: str
) -> list:
    """Positions des mots d'une ligne (révélation mot à mot)."""
    from PIL import Image, ImageDraw  # type: ignore

    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    tokens = [token for token in line.split(" ") if token]
    if not tokens:
        return []
    widths = [_tracked_width(probe, token, font, spacing) for token in tokens]
    # L'espace entre deux mots suit la même avance que les caractères :
    # largeur de l'espace + l'interlettre de chaque côté.
    gap = probe.textlength(" ", font=font) + 2.0 * spacing
    total = sum(widths) + gap * (len(tokens) - 1)
    if anchor == "center":
        cursor = anchor_x - total / 2.0
    elif anchor == "right":
        cursor = anchor_x - total
    else:
        cursor = anchor_x
    offsets = []
    for index, token in enumerate(tokens):
        offsets.append((token, cursor))
        cursor += widths[index] + gap
    return offsets


def _draw_words_animated(
    draw,
    lines: list,
    font,
    anchor_x: float,
    top_y: float,
    line_h: float,
    letter_spacing: int,
    fill,
    align: str,
    progresses: list,
    *,
    stroke_width: int = 0,
    stroke_fill=None,
) -> None:
    """Écrit les mots un par un avec leur propre progression d'entrée."""
    anchor = {"left": "left", "center": "center", "right": "right"}[align]
    index = 0
    for row, line in enumerate(lines):
        for token, word_x in _line_word_offsets(
            line, font, float(letter_spacing), anchor_x, anchor
        ):
            progress = progresses[index] if index < len(progresses) else 1.0
            index += 1
            if progress <= 0.001:
                continue
            offset = (1.0 - progress) * 0.38 * font.size  # translateY(0.38em)
            _draw_tracked(
                draw,
                word_x,
                top_y + row * line_h + offset,
                token,
                font,
                fill,
                int(letter_spacing),
                "left",
                "left",
                stroke_width=stroke_width,
                stroke_fill=stroke_fill,
            )


def _draw_accent_decor(
    band_layer,
    band_w: int,
    band_h: int,
    pad_x: int,
    accent,
    accent_2,
    strip_progress: float,
    layout_mode: str,
    panel_side: str,
) -> None:
    """Barre d'accent et liseré du panneau, à la géométrie de la page OBS.

    Bandeau bas : trait de 4 px sur le bord inférieur + liseré de 3 px à
    8 px du bas, qui entre en scaleX depuis la gauche. Panneau latéral :
    la barre devient verticale, sur le côté choisi (`panel_side`).
    """
    from PIL import ImageDraw  # type: ignore

    if layout_mode == "side_panel":
        bar_w = 4
        top = 34
        bottom = max(top + 2, band_h - 34)
        left = 0 if str(panel_side) != "right" else max(0, band_w - bar_w)
        bar = _linear_gradient(
            (bar_w, bottom - top),
            (
                (0.0, (accent[0], accent[1], accent[2], 0)),
                (0.34, accent),
                (0.66, accent_2),
                (1.0, (accent_2[0], accent_2[1], accent_2[2], 0)),
            ),
            180.0,
        )
        band_layer.alpha_composite(bar, (left, top))
        return

    full_w = max(1, band_w - pad_x * 2)
    progress = max(0.0, min(1.0, float(strip_progress)))
    left = pad_x

    bar_h = 4
    width = max(1, int(full_w * progress)) if progress > 0 else 0
    if width:
        bar = _linear_gradient(
            (width, bar_h),
            (
                (0.0, (accent[0], accent[1], accent[2], 0)),
                (0.34, accent),
                (0.66, accent_2),
                (1.0, (accent_2[0], accent_2[1], accent_2[2], 0)),
            ),
            90.0,
        )
        bar = _with_alpha(bar, 0.88)
        band_layer.alpha_composite(bar, (left, band_h - bar_h))

    strip_h = 3
    strip_w = max(1, int(full_w * progress)) if progress > 0 else 0
    if strip_w:
        strip = _linear_gradient(
            (strip_w, strip_h),
            (
                (0.0, (accent[0], accent[1], accent[2], 0)),
                (0.22, accent),
                (0.5, accent_2),
                (0.78, accent),
                (1.0, (accent[0], accent[1], accent[2], 0)),
            ),
            90.0,
        )
        strip = _with_alpha(strip, 0.7)
        band_layer.alpha_composite(strip, (left, band_h - 8 - strip_h))


def render_obs_overlay_on_color(
    cfg_payload: dict[str, Any] | None,
    slide: dict[str, Any] | None,
    bg_rgba: tuple[int, int, int, int] = (*CHROMA_KEY_GREEN, 255),
    width: int = 1920,
    height: int = 1080,
    *,
    text_scale: float = 1.0,
    offset_y: int = 0,
    elapsed_ms: float | None = None,
) -> Any:
    """Section texte « façon OBS » composée sur un fond uni opaque.

    Sortie HDMI mixeur : le fond est la couleur de clé que le mélangeur
    supprime ; le mode clé chroma est donc activé (panneau opaque,
    remplissages aplatis, accents éloignés de la clé) pour que la partie
    visible ne contienne aucun mélange avec la couleur de clé. Une slide
    masquée donne un cadre uni.
    """
    from PIL import Image  # type: ignore

    base = Image.new("RGBA", (width, height), tuple(bg_rgba))
    overlay = render_obs_overlay(
        cfg_payload,
        slide,
        width,
        height,
        text_scale=text_scale,
        offset_y=offset_y,
        key_rgb=(bg_rgba[0], bg_rgba[1], bg_rgba[2]),
        elapsed_ms=elapsed_ms,
    )
    if overlay is not None:
        return Image.alpha_composite(base, overlay)
    return base
