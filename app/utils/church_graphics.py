"""Profil de l'église et visuels à ses couleurs.

- **Écran d'accueil** projeté avant le culte : titre d'accueil, logo, nom,
  devise, horaires des cultes, réseaux sociaux et QR code ;
- **Écran « Réseaux sociaux »** (fin de culte) : chaque compte de l'église,
  en grand, avec un QR code à scanner ;
- **Images de citations** pour WhatsApp, Facebook, Instagram (carré,
  story, paysage) : verset ou paragraphe, référence, logo, nom et comptes.

Rendu PIL, indépendant de l'écran : les images sont identiques sur tous les
postes et s'enregistrent en PNG.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

FORMATS: dict[str, tuple[str, int, int]] = {
    "square": ("Carré 1080×1080 (Instagram, Facebook)", 1080, 1080),
    "story": ("Story 1080×1920 (WhatsApp, Instagram)", 1080, 1920),
    "landscape": ("Paysage 1920×1080 (YouTube, écran)", 1920, 1080),
}


@dataclass(frozen=True)
class SocialPlatform:
    key: str
    label: str
    color: str  # couleur de la pastille
    placeholder: str


SOCIAL_PLATFORMS: tuple[SocialPlatform, ...] = (
    SocialPlatform("facebook", "Facebook", "#1877F2", "facebook.com/monEglise"),
    SocialPlatform("youtube", "YouTube", "#FF0000", "youtube.com/@monEglise"),
    SocialPlatform("instagram", "Instagram", "#E1306C", "@monEglise"),
    SocialPlatform("whatsapp", "WhatsApp", "#25D366", "+243 81 000 0000"),
    SocialPlatform("tiktok", "TikTok", "#161823", "@monEglise"),
    SocialPlatform("x", "X", "#14171A", "@monEglise"),
    SocialPlatform("telegram", "Telegram", "#229ED9", "t.me/monEglise"),
    SocialPlatform("website", "Site web", "#6B7280", "www.monEglise.org"),
    SocialPlatform("email", "E-mail", "#6B7280", "contact@monEglise.org"),
    SocialPlatform("phone", "Téléphone", "#6B7280", "+243 99 000 0000"),
)
PLATFORM_BY_KEY = {p.key: p for p in SOCIAL_PLATFORMS}

BACKGROUND_MODES = ("gradient", "solid", "image")
QUOTE_STYLES = ("classic", "minimal", "framed")


@dataclass
class ChurchProfile:
    # Identité
    name: str = ""
    motto: str = ""  # devise ou verset de l'église
    logo: str = ""  # chemin d'une image (PNG transparent conseillé)
    contact: str = ""  # contact libre (ancien champ, toujours affiché)
    # Réseaux sociaux : clé de SOCIAL_PLATFORMS → adresse, @compte ou numéro
    socials: dict[str, str] = field(default_factory=dict)
    # Couleurs et police
    primary_color: str = "#0B1E3F"  # fond
    accent_color: str = "#F0BE64"  # filets, référence
    text_color: str = "#FFFFFF"
    font_family: str = "Poppins"
    # Personnalisation
    welcome_title: str = "Bienvenue"
    service_times: str = ""  # une ligne par culte : « Dimanche 9h30 · Culte »
    background_mode: str = "gradient"  # gradient | solid | image
    background_image: str = ""
    background_dim: int = 45  # % d'assombrissement de l'image de fond
    show_socials_welcome: bool = True
    show_socials_quotes: bool = True
    qr_target: str = ""  # réseau vers lequel pointe le QR code ("" = aucun)
    quote_style: str = "classic"  # classic | minimal | framed

    def sanitized(self) -> ChurchProfile:
        defaults = ChurchProfile()
        out = ChurchProfile()
        for name, default in asdict(defaults).items():
            value = getattr(self, name, default)
            if isinstance(default, bool):
                value = bool(value)
            elif isinstance(default, int):
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    value = default
            elif isinstance(default, dict):
                raw = value if isinstance(value, dict) else {}
                value = {
                    str(k): str(v or "").strip()
                    for k, v in raw.items()
                    if str(k) in PLATFORM_BY_KEY and str(v or "").strip()
                }
            else:
                value = str(value if value is not None else "").strip()
            setattr(out, name, value)
        for name in ("primary_color", "accent_color", "text_color"):
            if not _parse_color(getattr(out, name)):
                setattr(out, name, getattr(defaults, name))
        out.font_family = out.font_family or defaults.font_family
        out.background_dim = max(0, min(85, out.background_dim))
        if out.background_mode not in BACKGROUND_MODES:
            out.background_mode = defaults.background_mode
        if out.quote_style not in QUOTE_STYLES:
            out.quote_style = defaults.quote_style
        if out.qr_target and out.qr_target not in out.socials:
            out.qr_target = ""
        return out

    @classmethod
    def from_payload(cls, payload: Any) -> ChurchProfile:
        out = cls()
        if isinstance(payload, dict):
            for name in asdict(out):
                if payload.get(name) is not None:
                    setattr(out, name, payload[name])
        return out.sanitized()

    def social_items(self) -> list[tuple[SocialPlatform, str]]:
        """Comptes renseignés, dans l'ordre des plateformes."""
        return [
            (platform, self.socials[platform.key])
            for platform in SOCIAL_PLATFORMS
            if self.socials.get(platform.key)
        ]


# ── Liens ──────────────────────────────────────────────────────────────────


def display_handle(key: str, value: str) -> str:
    """Adresse lisible à l'écran : sans « https:// » ni « www. »."""
    text = re.sub(r"^https?://", "", str(value or "").strip(), flags=re.IGNORECASE)
    text = re.sub(r"^www\.", "", text, flags=re.IGNORECASE).rstrip("/")
    if key == "email":
        text = re.sub(r"^mailto:", "", text, flags=re.IGNORECASE)
    return text


def link_url(key: str, value: str) -> str:
    """Lien complet (QR code) à partir de ce que l'église a saisi."""
    value = str(value or "").strip()
    if not value:
        return ""
    if re.match(r"^(https?://|mailto:|tel:)", value, re.IGNORECASE):
        return value
    handle = value.lstrip("@/")
    digits = re.sub(r"[^\d+]", "", value)
    if key == "whatsapp":
        return f"https://wa.me/{digits.lstrip('+')}"
    if key == "phone":
        return f"tel:{digits}"
    if key == "email":
        return f"mailto:{value}"
    if "." in handle and "/" in handle or key == "website":
        return f"https://{re.sub(r'^www[.]', 'www.', handle)}"
    bases = {
        "facebook": "https://facebook.com/",
        "youtube": "https://youtube.com/@",
        "instagram": "https://instagram.com/",
        "tiktok": "https://tiktok.com/@",
        "x": "https://x.com/",
        "telegram": "https://t.me/",
    }
    return bases.get(key, "https://") + handle


# ── Outils de dessin ───────────────────────────────────────────────────────


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
            font = ImageFont.truetype(candidate, max(8, int(size)))
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
    """Fond : dégradé, couleur unie ou image assombrie (réglage de l'église)."""
    from PIL import Image

    top = _rgb(profile.primary_color, "#0B1E3F")
    if profile.background_mode == "image" and profile.background_image:
        path = Path(profile.background_image)
        if path.is_file():
            try:
                source = Image.open(path).convert("RGB")
                scale = max(width / source.width, height / source.height)
                resized = source.resize(
                    (max(1, int(source.width * scale)), max(1, int(source.height * scale)))
                )
                left = (resized.width - width) // 2
                upper = (resized.height - height) // 2
                image = resized.crop((left, upper, left + width, upper + height)).convert("RGBA")
                veil = Image.new("RGBA", (width, height),
                                 (0, 0, 0, int(255 * profile.background_dim / 100)))
                return Image.alpha_composite(image, veil)
            except Exception:
                pass
    if profile.background_mode == "solid":
        return Image.new("RGBA", (width, height), (*top, 255))
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


def qr_image(url: str, size: int, logo_key: str = ""):
    """QR code blanc à coins arrondis (None si la bibliothèque manque).

    ``logo_key`` place le logo du réseau au centre ; la correction d'erreur
    haute (30 %) garde le code lisible malgré le logo.
    """
    if not url:
        return None
    try:
        import qrcode
        from PIL import Image, ImageDraw
    except Exception:
        return None
    level = qrcode.constants.ERROR_CORRECT_H if logo_key else qrcode.constants.ERROR_CORRECT_M
    code = qrcode.QRCode(border=2, box_size=10, error_correction=level)
    code.add_data(url)
    code.make(fit=True)
    matrix = code.make_image(fill_color="black", back_color="white").convert("RGBA")
    matrix = matrix.resize((size, size), Image.NEAREST)
    card = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 12, fill=255)
    card.paste(matrix, (0, 0), mask)
    badge = social_badge(logo_key, int(size * 0.22)) if logo_key else None
    if badge is not None:
        ring = int(size * 0.26)
        offset = (size - ring) // 2
        ImageDraw.Draw(card).ellipse((offset, offset, offset + ring, offset + ring),
                                     fill=(255, 255, 255, 255))
        card.alpha_composite(badge, ((size - badge.width) // 2, (size - badge.height) // 2))
    return card


_BADGE_CACHE: dict[tuple[str, int], Any] = {}


def _social_mask(key: str):
    """Masque blanc du logo (assets/social/<réseau>.png), ou None."""
    from PIL import Image

    from app.utils.app_paths import resource_root

    path = resource_root() / "assets" / "social" / f"{key}.png"
    try:
        return Image.open(path).convert("RGBA").getchannel("A")
    except Exception:
        return None


def social_badge(key: str, diameter: int):
    """Pastille ronde au logo officiel du réseau (image RGBA, mise en cache).

    Logos Simple Icons (CC0) et Lucide (ISC) recolorés aux couleurs des
    marques : Facebook et Telegram bleus au glyphe blanc, YouTube rouge au
    bouton blanc, Instagram en dégradé, TikTok noir aux reflets cyan/rose…
    """
    from PIL import Image, ImageDraw

    diameter = max(8, int(diameter))
    cache_key = (key, diameter)
    if cache_key in _BADGE_CACHE:
        return _BADGE_CACHE[cache_key]
    platform = PLATFORM_BY_KEY.get(key)
    if platform is None:
        return None
    mask = _social_mask(key)
    scale = 4
    size = diameter * scale
    badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(badge)
    brand = _rgb(platform.color, "#6B7280")
    white = (255, 255, 255, 255)

    def glyph(fraction: float, color, dx: float = 0.0, dy: float = 0.0) -> None:
        if mask is None:
            return
        side = int(size * fraction)
        resized = mask.resize((side, side), Image.LANCZOS)
        layer = Image.new("RGBA", (side, side), color)
        layer.putalpha(resized)
        offset = ((size - side) // 2 + int(dx * size), (size - side) // 2 + int(dy * size))
        badge.alpha_composite(layer, offset)

    if mask is None:
        # Logo introuvable : pastille à la couleur de la marque + initiale.
        draw.ellipse((0, 0, size - 1, size - 1), fill=(*brand, 255))
        font = _font("Poppins", int(size * 0.45))
        draw.text((size / 2, size / 2), platform.label[:1], font=font, fill=white, anchor="mm")
    elif key in ("facebook", "telegram"):
        # Logo rond officiel : glyphe bleu plein cadre sur un disque blanc.
        inset = int(size * 0.12)
        draw.ellipse((inset, inset, size - inset, size - inset), fill=white)
        glyph(1.0, (*brand, 255))
    elif key == "youtube":
        draw.ellipse((0, 0, size - 1, size - 1), fill=white)
        draw.rectangle((int(size * 0.36), int(size * 0.34), int(size * 0.66), int(size * 0.66)),
                       fill=white)
        glyph(0.74, (*brand, 255))
    elif key == "instagram":
        # Dégradé officiel (jaune → rose → violet), en diagonale.
        stops = [(254, 218, 117), (250, 126, 30), (214, 41, 118), (150, 47, 191), (79, 91, 213)]
        gradient = Image.new("RGBA", (size, size))
        pixels = gradient.load()
        for yy in range(size):
            for xx in range(0, size, 2):
                t = ((size - yy) + xx) / (2 * size)
                pos = t * (len(stops) - 1)
                i = min(int(pos), len(stops) - 2)
                f = pos - i
                c = tuple(int(stops[i][k] + (stops[i + 1][k] - stops[i][k]) * f) for k in range(3))
                pixels[xx, yy] = (*c, 255)
                if xx + 1 < size:
                    pixels[xx + 1, yy] = (*c, 255)
        circle = Image.new("L", (size, size), 0)
        ImageDraw.Draw(circle).ellipse((0, 0, size - 1, size - 1), fill=255)
        badge.paste(gradient, (0, 0), circle)
        glyph(0.56, white)
    elif key == "tiktok":
        draw.ellipse((0, 0, size - 1, size - 1), fill=(0, 0, 0, 255))
        glyph(0.54, (37, 244, 238, 255), -0.018, -0.018)
        glyph(0.54, (254, 44, 85, 255), 0.018, 0.018)
        glyph(0.54, white)
    elif key == "x":
        draw.ellipse((0, 0, size - 1, size - 1), fill=(0, 0, 0, 255))
        glyph(0.5, white)
    elif key == "whatsapp":
        draw.ellipse((0, 0, size - 1, size - 1), fill=(*brand, 255))
        glyph(0.6, white)
    else:  # site web, e-mail, téléphone (icônes Lucide)
        draw.ellipse((0, 0, size - 1, size - 1), fill=(*brand, 255))
        glyph(0.54, white)

    result = badge.resize((diameter, diameter), Image.LANCZOS)
    _BADGE_CACHE[cache_key] = result
    return result


def _badge(image, x: int, y: int, platform: SocialPlatform, diameter: int) -> None:
    """Colle la pastille du réseau (logo officiel) à la position donnée."""
    badge = social_badge(platform.key, diameter)
    if badge is not None:
        image.alpha_composite(badge, (int(x), int(y)))


def _socials_strip(image, draw, profile: ChurchProfile, center_x: int, y: int,
                   max_width: int, unit: float, text_rgb, limit: int = 4) -> int:
    """Rangée(s) centrée(s) « pastille + @compte » ; renvoie la hauteur utilisée."""
    items = profile.social_items()[:limit]
    if not items:
        return 0
    size = int(28 * unit)
    font = _font(profile.font_family, size, bold=False)
    diameter = int(size * 1.25)
    gap = int(34 * unit)
    pieces = []
    for platform, value in items:
        label = display_handle(platform.key, value)
        width = diameter + int(10 * unit) + int(draw.textlength(label, font=font))
        pieces.append((platform, label, width))
    rows: list[list] = [[]]
    row_width = 0
    for piece in pieces:
        extra = piece[2] + (gap if rows[-1] else 0)
        if rows[-1] and row_width + extra > max_width:
            rows.append([])
            row_width = 0
            extra = piece[2]
        rows[-1].append(piece)
        row_width += extra
    line_h = int(diameter * 1.45)
    for index, row in enumerate(rows):
        total = sum(p[2] for p in row) + gap * (len(row) - 1)
        x = center_x - total // 2
        top = y + index * line_h
        for platform, label, width in row:
            _badge(image, x, top, platform, diameter)
            draw.text((x + diameter + int(10 * unit), top + diameter / 2), label,
                      font=font, fill=(*text_rgb, 235), anchor="lm")
            x += width + gap
    return line_h * len(rows)


# ── Visuels ────────────────────────────────────────────────────────────────


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

    if profile.quote_style == "framed":
        inset = int(margin * 0.45)
        draw.rounded_rectangle(
            (inset, inset, width - inset, height - inset),
            radius=int(28 * unit), outline=(*accent, 200), width=max(2, int(4 * unit)),
        )

    # Pied : logo, nom de l'église, contact et réseaux sociaux.
    socials = profile.show_socials_quotes and bool(profile.social_items())
    footer_h = int((150 + (70 if socials else 0)) * unit)
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
        y += int(36 * unit)
    if socials:
        _socials_strip(image, draw, profile, width // 2, y + int(6 * unit),
                       width - 2 * margin, unit * 0.8, text_rgb, limit=3)

    # Guillemet décoratif (style classique), texte centré, filet et référence.
    if profile.quote_style == "classic":
        quote_font = _font("Playfair Display", int(200 * unit))
        draw.text((width // 2, margin - int(40 * unit)), "“", font=quote_font,
                  fill=(*accent, 150), anchor="ma")
    area_top = margin + int((140 if profile.quote_style == "classic" else 60) * unit)
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
    """Écran d'accueil : titre, logo, nom, devise, horaires, réseaux, QR code."""
    from PIL import ImageDraw

    profile = profile.sanitized()
    image = _background(width, height, profile)
    draw = ImageDraw.Draw(image)
    accent = _rgb(profile.accent_color, "#F0BE64")
    text_rgb = _rgb(profile.text_color, "#FFFFFF")
    unit = min(width, height) / 1080
    socials = profile.show_socials_welcome and bool(profile.social_items())
    y = int(height * (0.10 if profile.service_times or socials else 0.16))
    if profile.welcome_title:
        draw.text((width // 2, y), profile.welcome_title.upper(),
                  font=_font(profile.font_family, int(34 * unit)), fill=accent, anchor="ma")
        y += int(64 * unit)
    logo_h = _paste_logo(image, profile, width // 2, y, int(220 * unit))
    y += logo_h + int(40 * unit) if logo_h else int(60 * unit)
    name = profile.name or "Bienvenue"
    font, lines, size = _fit_text(draw, name, profile.font_family, int(width * 0.8),
                                  int(240 * unit), start=int(104 * unit), minimum=int(46 * unit))
    for line in lines:
        draw.text((width // 2, y), line, font=font, fill=text_rgb, anchor="ma")
        y += int(size * 1.15)
    y += int(16 * unit)
    draw.line([(width // 2 - int(90 * unit), y), (width // 2 + int(90 * unit), y)],
              fill=accent, width=max(2, int(5 * unit)))
    y += int(36 * unit)
    if profile.motto:
        motto_font = _font(profile.font_family, int(42 * unit), bold=False)
        for line in _wrap(draw, profile.motto, motto_font, int(width * 0.7)):
            draw.text((width // 2, y), line, font=motto_font, fill=(*text_rgb, 225), anchor="ma")
            y += int(56 * unit)
    if profile.service_times:
        y += int(18 * unit)
        times_font = _font(profile.font_family, int(32 * unit))
        for line in [l.strip() for l in profile.service_times.splitlines() if l.strip()][:4]:
            draw.text((width // 2, y), line, font=times_font, fill=accent, anchor="ma")
            y += int(46 * unit)

    # Bas de l'écran : réseaux sociaux (centrés), QR code (à droite).
    qr_platform = PLATFORM_BY_KEY.get(profile.qr_target)
    qr = qr_image(link_url(profile.qr_target, profile.socials.get(profile.qr_target, "")),
                  int(170 * unit), profile.qr_target) if qr_platform else None
    bottom = height - int(60 * unit)
    if qr is not None:
        qx, qy = width - qr.width - int(60 * unit), bottom - qr.height - int(30 * unit)
        image.alpha_composite(qr, (qx, qy))
        draw.text((qx + qr.width // 2, qy + qr.height + int(10 * unit)),
                  qr_platform.label, font=_font(profile.font_family, int(22 * unit)),
                  fill=text_rgb, anchor="ma")
    if socials:
        strip_width = width - 2 * int(80 * unit) - (qr.width + int(60 * unit) if qr else 0) * 2
        rows = 2 if len(profile.social_items()) > 3 else 1
        _socials_strip(image, draw, profile, width // 2,
                       bottom - int(52 * unit) * rows - int(10 * unit),
                       max(400, strip_width), unit, text_rgb, limit=6)
    elif profile.contact:
        draw.text((width // 2, bottom - int(30 * unit)), profile.contact,
                  font=_font(profile.font_family, int(30 * unit), bold=False),
                  fill=accent, anchor="ma")
    return image


def render_socials(profile: ChurchProfile, width: int = 1920, height: int = 1080,
                   title: str = "Restons connectés"):
    """Écran « Réseaux sociaux » : comptes en grand + QR code à scanner."""
    from PIL import ImageDraw

    profile = profile.sanitized()
    image = _background(width, height, profile)
    draw = ImageDraw.Draw(image)
    accent = _rgb(profile.accent_color, "#F0BE64")
    text_rgb = _rgb(profile.text_color, "#FFFFFF")
    unit = min(width, height) / 1080
    margin = int(110 * unit)
    draw.text((width // 2, margin), title,
              font=_font(profile.font_family, int(76 * unit)), fill=text_rgb, anchor="ma")
    if profile.name:
        draw.text((width // 2, margin + int(100 * unit)), profile.name,
                  font=_font(profile.font_family, int(34 * unit), bold=False),
                  fill=accent, anchor="ma")

    items = profile.social_items()[:7]
    qr_platform = PLATFORM_BY_KEY.get(profile.qr_target)
    qr = qr_image(link_url(profile.qr_target, profile.socials.get(profile.qr_target, "")),
                  int(380 * unit), profile.qr_target) if qr_platform else None
    list_left = margin if qr is not None else int(width * 0.26)
    list_top = margin + int(210 * unit)
    available = height - list_top - margin
    row_h = min(int(112 * unit), available // max(1, len(items))) if items else 0
    diameter = int(row_h * 0.62)
    label_font = _font(profile.font_family, int(row_h * 0.26), bold=False)
    value_font = _font(profile.font_family, int(row_h * 0.36))
    for index, (platform, value) in enumerate(items):
        top = list_top + index * row_h
        _badge(image, list_left, top, platform, diameter)
        tx = list_left + diameter + int(26 * unit)
        draw.text((tx, top - int(4 * unit)), platform.label, font=label_font,
                  fill=(*text_rgb, 170), anchor="la")
        draw.text((tx, top + int(row_h * 0.26)), display_handle(platform.key, value),
                  font=value_font, fill=text_rgb, anchor="la")
    if not items:
        draw.text((width // 2, height // 2), "Ajoutez vos réseaux dans Réglages → Profil de l'église",
                  font=_font(profile.font_family, int(34 * unit), bold=False),
                  fill=(*text_rgb, 200), anchor="mm")
    if qr is not None:
        qx = width - margin - qr.width
        qy = list_top + max(0, (available - qr.height) // 2 - int(20 * unit))
        image.alpha_composite(qr, (qx, qy))
        draw.text((qx + qr.width // 2, qy + qr.height + int(18 * unit)),
                  f"Scannez · {qr_platform.label}",
                  font=_font(profile.font_family, int(30 * unit)), fill=accent, anchor="ma")
    _paste_logo(image, profile, width // 2, height - int(120 * unit), int(80 * unit))
    return image
