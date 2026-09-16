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
    """Style de la section texte, lu depuis la charge utile OBS."""

    layout_mode: str = "lower_third"
    panel_side: str = "left"
    safe_area_percent: int = 5
    font_family: str = "Google Sans"
    text_size: int = 48
    ref_size: int = 24
    align: str = "center"  # center|left|right
    show_reference: bool = True
    bg_color: str = "rgba(0, 0, 0, 0.75)"
    bg_opacity: float = 0.88
    text_color: str = "rgba(255, 255, 255, 0.95)"
    ref_color: str = "rgba(255, 255, 255, 0.7)"
    max_width: int = 82
    padding_horizontal: int = 48
    padding_vertical: int = 26
    border_radius: int = 22
    line_height: float = 1.16
    # Parité avec la page Navigateur OBS
    position: str = "bottom"  # bottom|top|center
    band_align: str = "center"  # left|center|right
    offset_x: int = 0
    offset_y: int = 0
    edge_margin: int = 64
    bg_enabled: bool = True
    bg_gradient_enabled: bool = False
    bg_color_2: str = ""
    text_transform: str = "none"  # none|uppercase
    text_shadow: bool = True
    show_accent_bar: bool = True
    accent_mode: str = "auto"  # auto|custom
    accent_color: str = "#74a7f8"
    opacity: float = 1.0

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
        out.text_transform = str(cfg.get("text_transform") or out.text_transform)
        out.text_shadow = bool(
            cfg.get("text_shadow") if "text_shadow" in cfg else out.text_shadow
        )
        out.show_accent_bar = bool(
            cfg.get("show_accent_bar")
            if "show_accent_bar" in cfg
            else out.show_accent_bar
        )
        out.accent_mode = str(cfg.get("accent_mode") or out.accent_mode)
        out.accent_color = str(cfg.get("accent_color") or out.accent_color)
        try:
            out.opacity = max(
                0.0,
                min(1.0, float(cfg.get("opacity") if "opacity" in cfg else out.opacity)),
            )
        except Exception:
            pass
        return out


def render_obs_overlay(
    cfg_payload: dict[str, Any] | None,
    slide: dict[str, Any] | None,
    width: int = 1920,
    height: int = 1080,
    *,
    text_scale: float = 1.0,
    offset_y: int = 0,
    key_rgb: tuple[int, int, int] | None = None,
) -> Any:
    """Compose la section texte « façon OBS » sur fond transparent.

    ``text_scale`` (sortie HDMI) agrandit ou réduit typographie et
    marges internes sans toucher au style OBS partagé ; ``offset_y``
    décale le bandeau verticalement (px @1080).

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
    from PIL import Image, ImageDraw, ImageFont  # type: ignore

    cfg = OverlayStyleConfig.from_payload(cfg_payload)

    scale = max(0.5, min(2.0, float(text_scale or 1.0)))
    if scale != 1.0:
        cfg.text_size = int(cfg.text_size * scale)
        cfg.ref_size = max(10, int(cfg.ref_size * scale))
        cfg.padding_horizontal = max(4, int(cfg.padding_horizontal * scale))
        cfg.padding_vertical = max(2, int(cfg.padding_vertical * scale))
        cfg.border_radius = int(cfg.border_radius * scale)
    if offset_y:
        cfg.offset_y = int(cfg.offset_y) + int(offset_y)

    if not slide or bool(slide.get("hidden")):
        return None

    text = str(slide.get("text") or "")
    ref = str(slide.get("reference") or "")
    if not text.strip() and not ref.strip():
        return None

    if str(cfg.text_transform).lower() == "uppercase":
        text = text.upper()
        ref = ref.upper()

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Polices
    def _load_font(px: int):
        try:
            return ImageFont.truetype(cfg.font_family, px)
        except Exception:
            try:
                return ImageFont.truetype("arial.ttf", px)
            except Exception:
                return ImageFont.load_default()

    font_text = _load_font(int(cfg.text_size))
    font_ref = _load_font(int(cfg.ref_size))

    layout_mode = str(cfg.layout_mode or "lower_third").lower()
    max_width_pct = max(40, min(100, int(cfg.max_width)))
    box_max_w = int(width * max_width_pct / 100)
    pad_x = max(0, min(110, int(cfg.padding_horizontal)))
    pad_y = max(0, min(80, int(cfg.padding_vertical)))
    accent_gap = max(10, int(26 * scale))
    accent_w = max(3, int(7 * scale))
    inner_w = max(320, box_max_w - (pad_x * 2) - accent_w - accent_gap)
    wrapped_text = _wrap_text(draw, text, font_text, inner_w)

    text_fill = _parse_rgba_tuple(cfg.text_color, (255, 255, 255, 242))
    ref_fill = _parse_rgba_tuple(cfg.ref_color, (255, 255, 255, 178))
    source = str(slide.get("source") or "custom").lower()
    # Palette canonique — miroir de theme.Colors.SRC_* et de obs-style.css
    accents = {
        "bible": ((86, 214, 129, 245), (181, 243, 202, 220)),
        "sermon": ((224, 160, 68, 245), (255, 217, 160, 220)),
        "hymn": ((185, 151, 255, 245), (232, 220, 255, 220)),
        "expose": ((0, 172, 193, 245), (127, 228, 239, 220)),
        "custom": ((116, 167, 248, 245), (207, 224, 255, 220)),
        "image": ((130, 123, 112, 245), (228, 222, 212, 220)),
    }
    accent, accent_2 = accents.get(source, accents["custom"])
    if str(cfg.accent_mode).lower() == "custom":
        custom = _parse_rgba_tuple(cfg.accent_color, accent)
        accent = (custom[0], custom[1], custom[2], 245)
        accent_2 = (custom[0], custom[1], custom[2], 220)
    if key_rgb is not None and accent_too_close_to_key(accent, key_rgb):
        # Accent de source trop proche de la couleur de clé : le
        # mélangeur le supprimerait (barre/liseré verts de la Bible sur
        # une clé verte) → neutre key-safe.
        accent = (*_KEY_SAFE_ACCENT, 245)
        accent_2 = (*_KEY_SAFE_ACCENT_2, 220)

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

        Sans cela, badge (alpha 18), divider (alpha 90) et lettering
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

    line_spacing = max(4, int(cfg.text_size * (cfg.line_height - 1) * 0.72))
    bbox = draw.multiline_textbbox(
        (0, 0), wrapped_text, font=font_text, spacing=line_spacing, align="left"
    )
    text_w = (bbox[2] - bbox[0]) if bbox else 0
    text_h = (bbox[3] - bbox[1]) if bbox else 0

    ref_block = ""
    ref_w = 0
    ref_h = 0
    if cfg.show_reference and ref.strip():
        ref_block = _wrap_text(draw, ref, font_ref, inner_w)
        ref_bbox = draw.multiline_textbbox(
            (0, 0), ref_block, font=font_ref, spacing=4, align="left"
        )
        ref_w = (ref_bbox[2] - ref_bbox[0]) if ref_bbox else 0
        ref_h = (ref_bbox[3] - ref_bbox[1]) if ref_bbox else 0

    divider_gap = 15 if ref_block else 0
    ref_badge_h = ref_h + 14 if ref_block else 0
    content_w = min(inner_w, max(text_w, ref_w + 42, 340))
    box_w = min(box_max_w, content_w + pad_x * 2 + accent_w + accent_gap)
    box_h = text_h + ref_badge_h + divider_gap + pad_y * 2
    box_h = max(box_h, int(136 * scale))

    # ── Placement du bandeau (position + band_align + décalages fins) ──
    safe_margin = int(min(width, height) * cfg.safe_area_percent / 100)
    margin = max(0, int(cfg.edge_margin)) + safe_margin
    if layout_mode == "fullscreen":
        box_w = width - (margin * 2)
        box_h = height - (margin * 2)
    elif layout_mode == "side_panel":
        box_h = height - (margin * 2)
    elif layout_mode == "subtitle":
        box_w = min(box_w, width - (margin * 2))
    elif layout_mode == "focus_card":
        box_w = min(box_w, width - (margin * 2))
        box_h = max(box_h, int(height * 0.48))

    band_align = str(cfg.band_align).lower()
    if layout_mode == "side_panel":
        box_x = width - box_w - margin if cfg.panel_side == "right" else margin
    elif band_align == "left":
        box_x = margin
    elif band_align == "right":
        box_x = width - box_w - margin
    else:
        box_x = int((width - box_w) / 2)

    position = str(cfg.position).lower()
    if layout_mode in ("fullscreen", "side_panel", "focus_card"):
        box_y = int((height - box_h) / 2)
    elif position == "top":
        box_y = margin
    elif position == "center":
        box_y = int((height - box_h) / 2)
    else:
        box_y = height - box_h - margin

    box_x += int(cfg.offset_x)
    box_y += int(cfg.offset_y)
    box_x = max(-box_w, min(width, box_x))
    box_y = max(-box_h, min(height, box_y))

    radius = max(0, min(48, int(cfg.border_radius)))

    if cfg.bg_enabled:
        bg = _parse_rgba_tuple(cfg.bg_color, (8, 15, 28, int(0.82 * 255)))
        bg_alpha = int(255 * max(0.0, min(1.0, cfg.bg_opacity)))
        if key_rgb is not None:
            # Mode clé chroma : panneau totalement opaque — sa
            # transparence laisserait voir la couleur de clé.
            bg_alpha = 255
        bg = (bg[0], bg[1], bg[2], bg_alpha)

        if key_rgb is None:
            for offset, alpha in ((18, 34), (8, 48)):
                draw.rounded_rectangle(
                    [box_x, box_y + offset, box_x + box_w, box_y + box_h + offset],
                    radius=radius,
                    fill=(0, 0, 0, alpha),
                )

        if cfg.bg_gradient_enabled and cfg.bg_color_2.strip():
            # Dégradé vertical bicolore dans un masque à coins arrondis.
            bg2 = _parse_rgba_tuple(cfg.bg_color_2, bg)
            bg2 = (bg2[0], bg2[1], bg2[2], bg_alpha)
            grad = Image.new("RGBA", (1, max(2, box_h)))
            for gy in range(grad.height):
                t = gy / (grad.height - 1)
                grad.putpixel(
                    (0, gy),
                    (
                        int(bg[0] + (bg2[0] - bg[0]) * t),
                        int(bg[1] + (bg2[1] - bg[1]) * t),
                        int(bg[2] + (bg2[2] - bg[2]) * t),
                        bg_alpha,
                    ),
                )
            grad = grad.resize((max(1, box_w), max(2, box_h)))
            mask = Image.new("L", grad.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                [0, 0, grad.width - 1, grad.height - 1], radius=radius, fill=255
            )
            img.paste(grad, (box_x, box_y), mask)
        else:
            draw.rounded_rectangle(
                [box_x, box_y, box_x + box_w, box_y + box_h],
                radius=radius,
                fill=bg,
            )

        if cfg.show_accent_bar:
            draw.rounded_rectangle(
                [
                    box_x + pad_x,
                    box_y + box_h - 2,
                    box_x + box_w - pad_x,
                    box_y + box_h,
                ],
                radius=2,
                fill=_flat(accent_2),
            )

    accent_x = box_x + pad_x
    accent_y = box_y + pad_y
    if cfg.bg_enabled and cfg.show_accent_bar:
        draw.rounded_rectangle(
            [accent_x, accent_y, accent_x + accent_w, box_y + box_h - pad_y],
            radius=accent_w,
            fill=_flat(accent),
        )

    content_x = accent_x + accent_w + accent_gap
    content_block_h = text_h + ref_badge_h + divider_gap
    content_y = box_y + max(
        pad_y,
        int((box_h - content_block_h) / 2)
        if layout_mode in ("fullscreen", "side_panel", "focus_card")
        else pad_y,
    )
    cfg_align = str(cfg.align).lower()
    align_mode = cfg_align if cfg_align in ("left", "right") else "center"
    if align_mode == "left":
        text_x = content_x
        anchor = None
    elif align_mode == "right":
        text_x = content_x + content_w
        anchor = "ra"
    else:
        text_x = content_x + content_w // 2
        anchor = "ma"

    if cfg.text_shadow:
        draw.multiline_text(
            (text_x + (2 if align_mode == "left" else 0), content_y + 3),
            wrapped_text,
            font=font_text,
            fill=_flat((0, 0, 0, 132)),
            spacing=line_spacing,
            align=align_mode,
            anchor=anchor,
        )
    draw.multiline_text(
        (text_x, content_y),
        wrapped_text,
        font=font_text,
        fill=_flat(text_fill),
        spacing=line_spacing,
        align=align_mode,
        anchor=anchor,
    )

    if ref_block:
        divider_y = content_y + text_h + 14
        draw.line(
            [content_x, divider_y, content_x + content_w, divider_y],
            fill=_flat(REF_DIVIDER_FILL),
            width=2,
        )
        badge_y = divider_y + 14
        badge_w = min(content_w, ref_w + 42)
        if align_mode == "left":
            badge_x = content_x
        elif align_mode == "right":
            badge_x = content_x + content_w - badge_w
        else:
            badge_x = content_x + (content_w - badge_w) // 2
        draw.rounded_rectangle(
            [badge_x, badge_y, badge_x + badge_w, badge_y + ref_badge_h],
            radius=ref_badge_h // 2,
            fill=_flat((255, 255, 255, 18)),
        )
        if align_mode == "center":
            ref_x = badge_x + badge_w // 2
            ref_anchor = "ma"
        elif align_mode == "right":
            ref_x = badge_x + badge_w - 20
            ref_anchor = "ra"
        else:
            ref_x = badge_x + 20
            ref_anchor = None
        draw.multiline_text(
            (ref_x, badge_y + 7),
            ref_block,
            font=font_ref,
            fill=_flat(ref_fill),
            spacing=4,
            align=align_mode,
            anchor=ref_anchor,
        )

    if key_rgb is not None:
        # Mode clé chroma : aucune opacité globale — elle réintroduirait
        # de la transparence sur la couleur de clé.
        return img
    opacity = max(0.0, min(1.0, float(cfg.opacity)))
    if opacity < 1.0:
        alpha = img.getchannel("A").point(lambda a: int(a * opacity))
        img.putalpha(alpha)
    return img


def render_obs_overlay_on_color(
    cfg_payload: dict[str, Any] | None,
    slide: dict[str, Any] | None,
    bg_rgba: tuple[int, int, int, int] = (*CHROMA_KEY_GREEN, 255),
    width: int = 1920,
    height: int = 1080,
    *,
    text_scale: float = 1.0,
    offset_y: int = 0,
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
    )
    if overlay is not None:
        return Image.alpha_composite(base, overlay)
    return base
