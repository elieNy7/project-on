"""Profil de l'église et visuels à ses couleurs.

- **Écran d'accueil** projeté avant le culte : logo, nom, devise ;
- **Images de citations** pour WhatsApp, Facebook, Instagram (carré,
  story, paysage) : verset ou paragraphe, référence, logo et nom.

Rendu PIL, indépendant de l'écran : les images sont identiques sur tous les
postes et s'enregistrent en PNG.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

FORMATS: dict[str, tuple[str, int, int]] = {
    "square": ("Carré 1080×1080 (Instagram, Facebook)", 1080, 1080),
    "story": ("Story 1080×1920 (WhatsApp, Instagram)", 1080, 1920),
    "landscape": ("Paysage 1920×1080 (YouTube, écran)", 1920, 1080),
}


@dataclass
class ChurchProfile:
    name: str = ""
    motto: str = ""  # devise ou verset de l'église
    logo: str = ""  # chemin d'une image (PNG transparent conseillé)
    primary_color: str = "#0B1E3F"  # fond
    accent_color: str = "#F0BE64"  # filets, référence
    text_color: str = "#FFFFFF"
    font_family: str = "Poppins"
    contact: str = ""  # site, page Facebook, @compte…

    def sanitized(self) -> ChurchProfile:
        out = ChurchProfile(**{k: str(v or "").strip() for k, v in asdict(self).items()})
        defaults = ChurchProfile()
        for name in ("primary_color", "accent_color", "text_color"):
            if not _parse_color(getattr(out, name)):
                setattr(out, name, getattr(defaults, name))
        out.font_family = out.font_family or defaults.font_family
        return out

    @classmethod
    def from_payload(cls, payload: Any) -> ChurchProfile:
        out = cls()
        if isinstance(payload, dict):
            for name in asdict(out):
                if payload.get(name) is not None:
                    setattr(out, name, payload[name])
        return out.sanitized()


def _parse_color(value: str) -> tuple[int, int, int] | None:
    value = str(value or "").strip()
    match = re.fullmatch(r"#?([0-9a-fA-F]{6})", value)
    if match:
        raw = match.group(1)
        return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    match = re.fullmatch(r"rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*[\d.]+)?\)", value)
    if match:
        return tuple(min(255, int(match.group(i))) for i in (1, 2, 3))  # type: ignore[return-value]
    return None


def _rgb(value: str, fallback: str) -> tuple[int, int, int]:
    return _parse_color(value) or _parse_color(fallback) or (0, 0, 0)


def _font(family: str, size: int, bold: bool = True):
    from PIL import ImageFont

    from app.utils.obs_overlay_render import _font_file

    for candidate in (
        _font_file(family, "bold" if bold else "normal"),
        _font_file("Poppins", "bold" if bold else "normal"),
        "arial.ttf",
        "DejaVuSans.ttf",
    ):
        if not candidate:
            continue
        try:
            font = ImageFont.truetype(candidate, int(size))
            if "[wght]" in str(candidate):
                try:
                    font.set_variation_by_axes([700 if bold else 400])
                except Exception:
                    pass
            return font
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap(draw, text: str, font, width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in str(text or "").replace("\r", "").split("\n"):
        words = paragraph.split()
        if not words:
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if draw.textlength(candidate, font=font) <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _fit_text(draw, text: str, family: str, box_w: int, box_h: int,
              start: int, minimum: int, line_factor: float = 1.28):
    """Plus grande taille de police dont le texte tient dans la boîte."""
    size = start
    while True:
        font = _font(family, size)
        lines = _wrap(draw, text, font, box_w)
        height = int(len(lines) * size * line_factor)
        if height <= box_h or size <= minimum:
            return font, lines, size
        size = max(minimum, int(size * 0.92))


def _background(width: int, height: int, profile: ChurchProfile):
    """Fond dégradé vertical à partir de la couleur principale."""
    from PIL import Image

    top = _rgb(profile.primary_color, "#0B1E3F")
    bottom = tuple(max(0, int(c * 0.55)) for c in top)
    gradient = Image.new("RGB", (1, height))
    for y in range(height):
        t = y / max(1, height - 1)
        gradient.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return gradient.resize((width, height)).convert("RGBA")


def _paste_logo(image, profile: ChurchProfile, center_x: int, top: int, max_h: int) -> int:
    """Colle le logo centré ; renvoie la hauteur occupée (0 sans logo)."""
    from PIL import Image

    path = Path(profile.logo) if profile.logo else None
    if path is None or not path.is_file():
        return 0
    try:
        logo = Image.open(path).convert("RGBA")
    except Exception:
        return 0
    logo.thumbnail((max_h * 3, max_h))
    image.alpha_composite(logo, (center_x - logo.width // 2, top))
    return logo.height


def render_quote(profile: ChurchProfile, text: str, reference: str = "",
                 fmt: str = "square"):
    """Image de citation (verset, paragraphe) aux couleurs de l'église."""
    from PIL import ImageDraw

    profile = profile.sanitized()
    _label, width, height = FORMATS.get(fmt, FORMATS["square"])
    image = _background(width, height, profile)
    draw = ImageDraw.Draw(image)
    accent = _rgb(profile.accent_color, "#F0BE64")
    text_rgb = _rgb(profile.text_color, "#FFFFFF")
    margin = int(min(width, height) * 0.09)
    unit = min(width, height) / 1080

    # Pied : logo + nom de l'église + contact.
    footer_h = int(150 * unit)
    footer_top = height - margin - footer_h
    name_font = _font(profile.font_family, int(34 * unit))
    small_font = _font(profile.font_family, int(24 * unit), bold=False)
    logo_h = _paste_logo(image, profile, width // 2, footer_top, int(70 * unit))
    y = footer_top + (logo_h + int(10 * unit) if logo_h else int(30 * unit))
    if profile.name:
        draw.text((width // 2, y), profile.name, font=name_font, fill=text_rgb, anchor="ma")
        y += int(44 * unit)
    if profile.contact:
        draw.text((width // 2, y), profile.contact, font=small_font,
                  fill=(*text_rgb, 190), anchor="ma")

    # Guillemet décoratif, texte centré, filet et référence.
    quote_font = _font("Playfair Display", int(200 * unit))
    draw.text((width // 2, margin - int(40 * unit)), "“", font=quote_font,
              fill=(*accent, 150), anchor="ma")
    area_top = margin + int(140 * unit)
    ref_block = int(110 * unit) if reference else 0
    area_h = footer_top - area_top - ref_block - int(40 * unit)
    font, lines, size = _fit_text(
        draw, text, profile.font_family, width - 2 * margin, area_h,
        start=int(64 * unit), minimum=int(26 * unit),
    )
    line_h = int(size * 1.28)
    y = area_top + max(0, (area_h - line_h * len(lines)) // 2)
    for line in lines:
        draw.text((width // 2, y), line, font=font, fill=text_rgb, anchor="ma")
        y += line_h
    if reference:
        y += int(24 * unit)
        draw.line(
            [(width // 2 - int(60 * unit), y), (width // 2 + int(60 * unit), y)],
            fill=accent, width=max(2, int(4 * unit)),
        )
        draw.text((width // 2, y + int(22 * unit)), reference.replace("\n", " — "),
                  font=_font(profile.font_family, int(36 * unit)), fill=accent, anchor="ma")
    return image


def render_welcome(profile: ChurchProfile, width: int = 1920, height: int = 1080):
    """Écran d'accueil projeté avant le culte : logo, nom, devise."""
    from PIL import ImageDraw

    profile = profile.sanitized()
    image = _background(width, height, profile)
    draw = ImageDraw.Draw(image)
    accent = _rgb(profile.accent_color, "#F0BE64")
    text_rgb = _rgb(profile.text_color, "#FFFFFF")
    unit = min(width, height) / 1080
    y = int(height * 0.18)
    logo_h = _paste_logo(image, profile, width // 2, y, int(260 * unit))
    y += logo_h + int(50 * unit) if logo_h else int(160 * unit)
    name = profile.name or "Bienvenue"
    font, lines, size = _fit_text(draw, name, profile.font_family, int(width * 0.8),
                                  int(260 * unit), start=int(110 * unit), minimum=int(48 * unit))
    for line in lines:
        draw.text((width // 2, y), line, font=font, fill=text_rgb, anchor="ma")
        y += int(size * 1.15)
    y += int(20 * unit)
    draw.line([(width // 2 - int(90 * unit), y), (width // 2 + int(90 * unit), y)],
              fill=accent, width=max(2, int(5 * unit)))
    y += int(40 * unit)
    if profile.motto:
        motto_font = _font(profile.font_family, int(46 * unit), bold=False)
        for line in _wrap(draw, profile.motto, motto_font, int(width * 0.7)):
            draw.text((width // 2, y), line, font=motto_font, fill=(*text_rgb, 220), anchor="ma")
            y += int(62 * unit)
    if profile.contact:
        draw.text((width // 2, height - int(90 * unit)), profile.contact,
                  font=_font(profile.font_family, int(30 * unit), bold=False),
                  fill=accent, anchor="ma")
    return image
