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

import copy
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
    # Pasteur : visage de l'église, présent sur toutes ses publications.
    # La photo est importée déjà sans arrière-plan (PNG transparent).
    pastor_name: str = ""
    pastor_title: str = "Pasteur"
    pastor_photo: str = ""
    # Orateur du jour (vide = le pasteur prêche) et titre du message.
    speaker_name: str = ""
    speaker_title: str = ""
    speaker_photo: str = ""
    speaker_message: str = ""
    # Orateur sur les slides de projection : all | sermon | off
    speaker_on_slides: str = "all"
    speaker_slides_side: str = "right"  # right | left
    speaker_slides_size: int = 20  # hauteur de la photo, % de l'écran
    # Orateur sur OBS, NDI et HDMI (à côté du bandeau) : all | sermon | off
    speaker_on_broadcast: str = "all"
    speaker_broadcast_size: int = 16  # hauteur de la photo, % du cadre
    # Photos de l'église (culte, louange, assemblée, bâtiment) : fonds des
    # miniatures YouTube. Copiées dans les données de Project-On.
    photos: list[str] = field(default_factory=list)

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
            elif isinstance(default, list):
                seen: list[str] = []
                for item in value if isinstance(value, list) else []:
                    item = str(item or "").strip()
                    if item and item not in seen:
                        seen.append(item)
                value = seen[:40]
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
        if out.speaker_on_slides not in ("all", "sermon", "off"):
            out.speaker_on_slides = "all"
        if out.speaker_slides_side not in ("right", "left"):
            out.speaker_slides_side = "right"
        out.speaker_slides_size = max(10, min(40, int(out.speaker_slides_size)))
        if out.speaker_on_broadcast not in ("all", "sermon", "off"):
            out.speaker_on_broadcast = "all"
        out.speaker_broadcast_size = max(10, min(40, int(out.speaker_broadcast_size)))
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
            # 2.7 préversion : « message du jour » rattaché au pasteur.
            if payload.get("pastor_message") and not payload.get("speaker_message"):
                out.speaker_message = str(payload["pastor_message"])
            # Anciennes hauteurs par défaut (grande photo) → petite photo.
            if payload.get("speaker_slides_size") == 42:
                out.speaker_slides_size = cls.speaker_slides_size
            if payload.get("speaker_broadcast_size") == 34:
                out.speaker_broadcast_size = cls.speaker_broadcast_size
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
        y += int(70 * unit)
    # Le visage de l'église : photo et nom du pasteur sur chaque publication.
    _pastor_corner(image, draw, profile, unit * 0.8, accent, text_rgb,
                   int(width * 0.24), int(height * 0.28), margin=int(margin * 0.35))
    return image


def _photo_image(photo: str, max_w: int, max_h: int):
    """Photo importée (PNG transparent conseillé), redimensionnée ; None si absente."""
    from PIL import Image

    path = Path(photo) if photo else None
    if path is None or not path.is_file():
        return None
    try:
        image = Image.open(path).convert("RGBA")
    except Exception:
        return None
    scale = min(max_w / image.width, max_h / image.height)
    size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    return image.resize(size, Image.LANCZOS)


def _pastor_image(profile: ChurchProfile, max_w: int, max_h: int):
    return _photo_image(profile.pastor_photo, max_w, max_h)


def pastor_label(profile: ChurchProfile) -> str:
    return " ".join(p for p in (profile.pastor_title, profile.pastor_name) if p).strip()


def has_guest_speaker(profile: ChurchProfile) -> bool:
    """Vrai si l'orateur du jour n'est pas le pasteur."""
    return bool(profile.speaker_name.strip())


def speaker_info(profile: ChurchProfile) -> tuple[str, str, str]:
    """(titre, nom, photo) de l'orateur du jour — le pasteur par défaut."""
    if has_guest_speaker(profile):
        return profile.speaker_title, profile.speaker_name, profile.speaker_photo
    return profile.pastor_title, profile.pastor_name, profile.pastor_photo


def speaker_slide_badge(profile: ChurchProfile) -> dict[str, Any]:
    """Réglage « orateur sur les slides » transmis à la projection (config.json)."""
    profile = profile.sanitized()
    title, name, photo = speaker_info(profile)
    return {
        "mode": profile.speaker_on_slides,
        "side": profile.speaker_slides_side,
        "size": profile.speaker_slides_size,
        "photo": photo if photo and Path(photo).is_file() else "",
        "title": title,
        "name": name,
    }


def speaker_broadcast_badge(profile: ChurchProfile) -> dict[str, Any]:
    """Orateur à côté du bandeau OBS, NDI et HDMI (même côté que les slides)."""
    badge = speaker_slide_badge(profile)
    profile = profile.sanitized()
    badge["mode"] = profile.speaker_on_broadcast
    badge["size"] = profile.speaker_broadcast_size
    return badge


def speaker_label(profile: ChurchProfile) -> str:
    title, name, _photo = speaker_info(profile)
    return " ".join(p for p in (title, name) if p).strip()


def _pastor_caption(draw, profile: ChurchProfile, cx: int, y: int, unit: float,
                    accent, text_rgb, scale: float = 1.0) -> None:
    """Titre (petit, couleur d'accent) puis nom du pasteur, centrés sur cx."""
    if profile.pastor_title:
        draw.text((cx, y), profile.pastor_title.upper(),
                  font=_font(profile.font_family, int(24 * unit * scale)), fill=accent,
                  anchor="ma")
        y += int(34 * unit * scale)
    if profile.pastor_name:
        draw.text((cx, y), profile.pastor_name,
                  font=_font(profile.font_family, int(34 * unit * scale)), fill=text_rgb,
                  anchor="ma")


def _pastor_corner(image, draw, profile: ChurchProfile, unit: float, accent, text_rgb,
                   max_w: int, max_h: int, side: str = "left", margin: int = 0) -> int:
    """Photo du pasteur posée au bas de l'image, avec son nom ; renvoie sa largeur."""
    from PIL import ImageDraw

    photo = _pastor_image(profile, max_w, max_h)
    if photo is None:
        return 0
    width, height = image.size
    x = margin if side == "left" else width - margin - photo.width
    image.alpha_composite(photo, (x, height - photo.height))
    if pastor_label(profile):
        scale = max(0.6, min(1.0, photo.width / (320 * unit)))
        caption_top = height - int(104 * unit * scale)
        veil_w = max(photo.width, int(300 * unit * scale))
        cx = x + photo.width // 2
        ImageDraw.Draw(image).rounded_rectangle(
            (cx - veil_w // 2, caption_top - int(12 * unit * scale),
             cx + veil_w // 2, height - int(14 * unit * scale)),
            radius=int(14 * unit), fill=(0, 0, 0, 150),
        )
        _pastor_caption(draw, profile, cx, caption_top, unit, accent, text_rgb, scale)
    return photo.width


def render_welcome(profile: ChurchProfile, width: int = 1920, height: int = 1080):
    """Écran d'accueil : titre, logo, nom, devise, horaires, pasteur, réseaux, QR."""
    from PIL import ImageDraw

    profile = profile.sanitized()
    image = _background(width, height, profile)
    draw = ImageDraw.Draw(image)
    accent = _rgb(profile.accent_color, "#F0BE64")
    text_rgb = _rgb(profile.text_color, "#FFFFFF")
    unit = min(width, height) / 1080

    # Photo du pasteur en bas à gauche : le contenu se décale vers la droite.
    photo_w = _pastor_corner(image, draw, profile, unit, accent, text_rgb,
                             int(width * 0.30), int(height * 0.72), margin=int(40 * unit))
    pastor = photo_w or None
    left_reserved = int(40 * unit) + photo_w if photo_w else 0
    cx = (left_reserved + width) // 2 if pastor is not None else width // 2
    text_w = int((width - left_reserved) * 0.86) if pastor is not None else int(width * 0.8)

    socials = profile.show_socials_welcome and bool(profile.social_items())
    y = int(height * (0.10 if profile.service_times or socials else 0.16))
    if profile.welcome_title:
        draw.text((cx, y), profile.welcome_title.upper(),
                  font=_font(profile.font_family, int(34 * unit)), fill=accent, anchor="ma")
        y += int(64 * unit)
    logo_h = _paste_logo(image, profile, cx, y, int(220 * unit))
    y += logo_h + int(40 * unit) if logo_h else int(60 * unit)
    name = profile.name or "Bienvenue"
    font, lines, size = _fit_text(draw, name, profile.font_family, text_w,
                                  int(240 * unit), start=int(104 * unit), minimum=int(46 * unit))
    for line in lines:
        draw.text((cx, y), line, font=font, fill=text_rgb, anchor="ma")
        y += int(size * 1.15)
    y += int(16 * unit)
    draw.line([(cx - int(90 * unit), y), (cx + int(90 * unit), y)],
              fill=accent, width=max(2, int(5 * unit)))
    y += int(36 * unit)
    if profile.motto:
        motto_font = _font(profile.font_family, int(42 * unit), bold=False)
        for line in _wrap(draw, profile.motto, motto_font, int(text_w * 0.88)):
            draw.text((cx, y), line, font=motto_font, fill=(*text_rgb, 225), anchor="ma")
            y += int(56 * unit)
    if profile.service_times:
        y += int(18 * unit)
        times_font = _font(profile.font_family, int(32 * unit))
        for line in [l.strip() for l in profile.service_times.splitlines() if l.strip()][:4]:
            draw.text((cx, y), line, font=times_font, fill=accent, anchor="ma")
            y += int(46 * unit)
    if has_guest_speaker(profile) or profile.speaker_message:
        y += int(18 * unit)
        draw.text((cx, y), f"Orateur du jour : {speaker_label(profile)}",
                  font=_font(profile.font_family, int(32 * unit), bold=False),
                  fill=text_rgb, anchor="ma")
        y += int(44 * unit)
        if profile.speaker_message:
            draw.text((cx, y), f"« {profile.speaker_message} »",
                      font=_font(profile.font_family, int(30 * unit), bold=False),
                      fill=(*text_rgb, 210), anchor="ma")

    # Bas de l'écran : réseaux sociaux (centrés), QR code (à droite).
    qr_platform = PLATFORM_BY_KEY.get(profile.qr_target)
    qr = qr_image(link_url(profile.qr_target, profile.socials.get(profile.qr_target, "")),
                  int(170 * unit), profile.qr_target) if qr_platform else None
    bottom = height - int(60 * unit)
    right_reserved = 0
    if qr is not None:
        qx, qy = width - qr.width - int(60 * unit), bottom - qr.height - int(30 * unit)
        image.alpha_composite(qr, (qx, qy))
        draw.text((qx + qr.width // 2, qy + qr.height + int(10 * unit)),
                  qr_platform.label, font=_font(profile.font_family, int(22 * unit)),
                  fill=text_rgb, anchor="ma")
        right_reserved = qr.width + int(90 * unit)
    if socials:
        free_left = left_reserved + int(40 * unit)
        free_right = width - right_reserved - int(40 * unit)
        if pastor is None and qr is not None:
            free_left = right_reserved  # rangée centrée sur l'écran
        strip_cx = (free_left + free_right) // 2
        rows = 2 if len(profile.social_items()) > 3 else 1
        _socials_strip(image, draw, profile, strip_cx,
                       bottom - int(52 * unit) * rows - int(10 * unit),
                       max(400, free_right - free_left), unit, text_rgb, limit=6)
    elif profile.contact:
        draw.text((cx, bottom - int(30 * unit)), profile.contact,
                  font=_font(profile.font_family, int(30 * unit), bold=False),
                  fill=accent, anchor="ma")
    return image


def render_speaker(profile: ChurchProfile, width: int = 1920, height: int = 1080,
                   kicker: str = "Orateur du jour", subtitle: str | None = None):
    """Écran de l'orateur du jour : photo en grand, titre, nom, message.

    Sans orateur invité, c'est le pasteur. Avec un invité, le pasteur reste
    présent (petite photo et nom en bas à droite) : il est sur toutes les
    publications de l'église.
    """
    from PIL import ImageDraw

    profile = profile.sanitized()
    image = _background(width, height, profile)
    draw = ImageDraw.Draw(image)
    accent = _rgb(profile.accent_color, "#F0BE64")
    text_rgb = _rgb(profile.text_color, "#FFFFFF")
    unit = min(width, height) / 1080
    title, name, photo_path = speaker_info(profile)
    message = profile.speaker_message if subtitle is None else subtitle
    photo = _photo_image(photo_path, int(width * 0.46), int(height * 0.94))
    if photo is not None:
        image.alpha_composite(photo, (int(width * 0.27) - photo.width // 2 + int(20 * unit),
                                      height - photo.height))
        left, text_w = int(width * 0.52), int(width * 0.42)
    else:
        left, text_w = int(width * 0.12), int(width * 0.76)
    if has_guest_speaker(profile):
        # Le pasteur de l'église, en médaillon dans le coin.
        _pastor_corner(image, draw, profile, unit * 0.75, accent, text_rgb,
                       int(width * 0.16), int(height * 0.34), side="right",
                       margin=int(50 * unit))
    y = int(height * 0.28)
    if kicker:
        draw.text((left, y), kicker.upper(), font=_font(profile.font_family, int(34 * unit)),
                  fill=accent, anchor="la")
        y += int(62 * unit)
    if title:
        draw.text((left, y), title, font=_font(profile.font_family, int(44 * unit), bold=False),
                  fill=(*text_rgb, 220), anchor="la")
        y += int(62 * unit)
    font, lines, size = _fit_text(draw, name or "Orateur", profile.font_family, text_w,
                                  int(280 * unit), start=int(96 * unit), minimum=int(44 * unit),
                                  line_factor=1.1)
    for line in lines:
        draw.text((left, y), line, font=font, fill=text_rgb, anchor="la")
        y += int(size * 1.1)
    y += int(20 * unit)
    draw.line([(left, y), (left + int(140 * unit), y)], fill=accent, width=max(2, int(6 * unit)))
    y += int(40 * unit)
    if message:
        sub_font = _font(profile.font_family, int(40 * unit), bold=False)
        for line in _wrap(draw, message, sub_font, text_w)[:3]:
            draw.text((left, y), line, font=sub_font, fill=text_rgb, anchor="la")
            y += int(54 * unit)
    if profile.name:
        draw.text((left, height - int(110 * unit)), profile.name,
                  font=_font(profile.font_family, int(30 * unit), bold=False),
                  fill=(*text_rgb, 200), anchor="la")
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
    photo_w = _pastor_corner(image, draw, profile, unit, accent, text_rgb,
                             int(width * 0.26), int(height * 0.66), margin=int(40 * unit))
    list_left = margin if qr is not None else int(width * 0.26)
    if photo_w:
        list_left = max(list_left, int(40 * unit) + photo_w + int(50 * unit))
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
    if not photo_w:
        _paste_logo(image, profile, width // 2, height - int(120 * unit), int(80 * unit))
    return image


# ── Miniature YouTube ──────────────────────────────────────────────────────

THUMBNAIL_SIZE = (1280, 720)  # format recommandé par YouTube (16:9)
THUMBNAIL_MAX_BYTES = 2 * 1024 * 1024  # limite d'envoi de YouTube


THUMBNAIL_LAYOUTS: dict[str, str] = {
    "split": "Orateur en grand",
    "boxed": "Titre surligné",
    "band": "Bandeau en bas",
    "center": "Titre centré",
}

THUMBNAIL_COMPOSITIONS: dict[str, str] = {
    "mosaic": "Photos de l'église (mosaïque)",
    "photo": "Une photo de l'église",
    "plain": "Fond uni de l'église",
}

# Passage d'une photo à l'autre dans la mosaïque (« fusion »).
THUMBNAIL_BLENDS: dict[str, str] = {
    "slant": "Coupe inclinée",
    "fade": "Fondu (fusion des photos)",
    "straight": "Coupe droite",
}

# Mélange de la couleur de l'église avec les photos.
THUMBNAIL_TINT_MODES: dict[str, str] = {
    "duotone": "Duotone (ombres et lumières)",
    "color": "Voile de couleur",
    "multiply": "Produit (plus sombre)",
    "screen": "Éclaircir",
    "overlay": "Incrustation (contraste)",
    "soft_light": "Lumière douce",
}

# Réglages numériques de l'image : nom → (minimum, maximum, valeur par défaut).
THUMBNAIL_IMAGE_SETTINGS: dict[str, tuple[int, int, int]] = {
    "tint_strength": (0, 100, 45),  # intensité de la couleur de l'église
    "brightness": (-50, 50, 0),
    "contrast": (-50, 50, 12),
    "saturation": (-100, 100, 15),  # -100 = noir et blanc
    "darkness": (0, 80, 20),  # assombrir l'arrière-plan
    "blur_amount": (0, 20, 3),  # flou de l'arrière-plan
    "vignette": (0, 100, 45),  # coins assombris
    "grain": (0, 30, 0),  # grain photo
    "text_veil": (0, 100, 80),  # voile sombre derrière le titre
    "glow": (0, 100, 60),  # halo de couleur derrière l'orateur
    "blend_width": (5, 100, 40),  # largeur du fondu entre photos (%)
    "focus_y": (0, 100, 50),  # cadrage vertical des photos (0 = haut)
    "zoom": (100, 200, 100),  # zoom dans les photos (%)
}

# Champs d'une miniature gardés dans un modèle (le titre, la date et la
# référence changent à chaque culte : ils ne sont pas enregistrés).
THUMBNAIL_MODEL_FIELDS = ("layout", "label", "background", "photo_side", "show_speaker",
                          "uppercase", "accent", "composition", "photos", "blend",
                          "tint_mode", *THUMBNAIL_IMAGE_SETTINGS)


@dataclass
class ThumbnailSpec:
    """Contenu d'une miniature : titre, bandeau, date, orateur, fond, mise en page."""

    title: str = ""
    label: str = "Culte du dimanche"
    date: str = ""
    reference: str = ""
    background: str = ""  # image de fond (sinon le fond de l'église)
    photo_side: str = "right"  # right | left
    show_speaker: bool = True
    uppercase: bool = True
    layout: str = "split"  # voir THUMBNAIL_LAYOUTS
    accent: str = ""  # couleur d'accent du modèle ("" = celle de l'église)
    # Arrière-plan composé des photos de l'église (voir THUMBNAIL_COMPOSITIONS).
    composition: str = "mosaic"
    photos: list[str] = field(default_factory=list)  # choisies ; vide = toutes
    blend: str = "slant"  # voir THUMBNAIL_BLENDS
    tint_mode: str = "duotone"  # voir THUMBNAIL_TINT_MODES
    # Réglages de l'image (voir THUMBNAIL_IMAGE_SETTINGS).
    tint_strength: int = 45
    brightness: int = 0
    contrast: int = 12
    saturation: int = 15
    darkness: int = 20
    blur_amount: int = 3
    vignette: int = 45
    grain: int = 0
    text_veil: int = 80
    glow: int = 60
    blend_width: int = 40
    focus_y: int = 50
    zoom: int = 100

    def sanitized(self) -> ThumbnailSpec:
        out = ThumbnailSpec(**{k: getattr(self, k) for k in asdict(self)})
        if out.composition not in THUMBNAIL_COMPOSITIONS:
            out.composition = "mosaic"
        if out.blend not in THUMBNAIL_BLENDS:
            out.blend = "slant"
        if out.tint_mode not in THUMBNAIL_TINT_MODES:
            out.tint_mode = "duotone"
        out.photos = [str(p) for p in (out.photos if isinstance(out.photos, list) else [])
                      if str(p or "").strip()][:12]
        for name, (low, high, default) in THUMBNAIL_IMAGE_SETTINGS.items():
            try:
                value = int(getattr(out, name))
            except (TypeError, ValueError):
                value = default
            setattr(out, name, max(low, min(high, value)))
        if out.layout not in THUMBNAIL_LAYOUTS:
            out.layout = "split"
        if out.photo_side not in ("right", "left"):
            out.photo_side = "right"
        out.accent = "#{:02X}{:02X}{:02X}".format(*_parse_color(out.accent)) \
            if _parse_color(out.accent) else ""
        for name in ("title", "label", "date", "reference", "background"):
            setattr(out, name, str(getattr(out, name) or ""))
        out.show_speaker, out.uppercase = bool(out.show_speaker), bool(out.uppercase)
        return out

    def model(self, name: str) -> dict[str, Any]:
        """Modèle réutilisable (nom + mise en page, bandeau, fond, couleur…)."""
        spec = self.sanitized()
        return {"name": str(name).strip(),
                **{k: copy.copy(getattr(spec, k)) for k in THUMBNAIL_MODEL_FIELDS}}

    def with_model(self, model: dict[str, Any]) -> ThumbnailSpec:
        """Applique un modèle en gardant le titre, la date et la référence."""
        values = asdict(self)
        values.update({k: model[k] for k in THUMBNAIL_MODEL_FIELDS if k in model})
        # Modèles enregistrés avant les réglages détaillés (cases à cocher).
        if "tint" in model and "tint_strength" not in model:
            values["tint_strength"] = 45 if model["tint"] else 0
        if "blur" in model and "blur_amount" not in model:
            values["blur_amount"] = 3 if model["blur"] else 0
        return ThumbnailSpec(**values).sanitized()

    def with_image_defaults(self) -> ThumbnailSpec:
        """Mêmes contenu et fond, réglages de l'image remis par défaut."""
        values = asdict(self)
        values.update({k: d for k, (_lo, _hi, d) in THUMBNAIL_IMAGE_SETTINGS.items()})
        values["tint_mode"] = "duotone"
        return ThumbnailSpec(**values).sanitized()


BUILTIN_THUMBNAIL_MODELS: tuple[dict[str, Any], ...] = (
    ThumbnailSpec(label="Culte du dimanche").model("Culte du dimanche"),
    ThumbnailSpec(label="En direct", layout="band", blend="fade").model("En direct"),
    ThumbnailSpec(label="Enseignement", layout="center", composition="photo",
                  darkness=45, blur_amount=6, tint_mode="color").model("Enseignement"),
    ThumbnailSpec(label="Culte de prière", layout="boxed", photo_side="left", blend="fade",
                  tint_mode="soft_light", tint_strength=60).model("Prière"),
    ThumbnailSpec(label="Conférence", layout="boxed", blend="straight", contrast=25,
                  grain=8).model("Conférence"),
    ThumbnailSpec(label="Témoignage", layout="split", photo_side="left", uppercase=False,
                  composition="photo", tint_strength=0, saturation=-20, vignette=65,
                  grain=10).model("Témoignage"),
)


def sanitize_thumbnail_models(models: Any) -> list[dict[str, Any]]:
    """Modèles enregistrés par l'église : noms uniques et non vides, 50 au plus."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for model in models if isinstance(models, list) else []:
        if not isinstance(model, dict):
            continue
        name = str(model.get("name") or "").strip()[:60]
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append(ThumbnailSpec().with_model(model).model(name))
    return out[:50]


def _highlight_words(text: str) -> list[tuple[str, bool]]:
    """« Le *vrai* repos » → mots, les mots entre astérisques en couleur d'accent."""
    words: list[tuple[str, bool]] = []
    highlighted = False
    for chunk in re.split(r"(\*)", str(text or "")):
        if chunk == "*":
            highlighted = not highlighted
            continue
        words.extend((word, highlighted) for word in chunk.split())
    return words


def _wrap_words(draw, words: list[tuple[str, bool]], font, width: int):
    lines: list[list[tuple[str, bool]]] = []
    current: list[tuple[str, bool]] = []
    for word in words:
        candidate = " ".join(w for w, _h in current + [word])
        if current and draw.textlength(candidate, font=font) > width:
            lines.append(current)
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(current)
    return lines


def _cover(path: str, width: int, height: int, focus_y: float = 0.5, zoom: float = 1.0):
    """Image remplissant le cadre ; None si illisible.

    ``focus_y`` : partie gardée en hauteur (0 = haut, 1 = bas) ; ``zoom`` ≥ 1.
    """
    from PIL import Image

    try:
        source = Image.open(path).convert("RGB")
    except Exception:
        return None
    scale = max(width / source.width, height / source.height) * max(1.0, zoom)
    resized = source.resize(
        (max(1, int(source.width * scale)), max(1, int(source.height * scale))), Image.LANCZOS
    )
    left = (resized.width - width) // 2
    upper = int((resized.height - height) * max(0.0, min(1.0, focus_y)))
    return resized.crop((left, upper, left + width, upper + height)).convert("RGBA")


def _horizontal_veil(width: int, height: int, strength: int, reverse: bool,
                     reach: float = 0.8):
    """Voile noir dégradé (fort du côté du texte) pour lire le titre sur tout fond.

    ``reach`` : part de la largeur couverte avant que le voile disparaisse.
    """
    from PIL import Image

    veil = Image.new("L", (width, 1))
    for x in range(width):
        t = x / max(1, width - 1)
        t = 1 - t if reverse else t
        veil.putpixel((x, 0), int(strength * max(0.0, 1 - t / reach) ** 0.8))
    shade = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    shade.putalpha(veil.resize((width, height)))
    return shade


def _fit_title(draw, words, family: str, box_w: int, box_h: int, unit: float,
               max_lines: int = 4, start: int = 118):
    size = int(start * unit)
    minimum = int(44 * unit)
    while True:
        font = _font(family, size)
        lines = _wrap_words(draw, words, font, box_w)
        line_h = int(size * 1.08)
        if (len(lines) * line_h <= box_h and len(lines) <= max_lines) or size <= minimum:
            return font, lines, size, line_h
        size = max(minimum, int(size * 0.92))


def _draw_title(draw, lines, font, size: int, line_h: int, x: int, width: int, top: int,
                accent, text_rgb, align: str = "left", boxed: bool = False) -> None:
    """Titre mot à mot (mots surlignés en accent) ; « boxed » : lignes sur pavés."""
    space = draw.textlength(" ", font=font)
    stroke = max(2, int(size * 0.07))
    pad = int(size * 0.16)
    for line in lines:
        line_w = sum(draw.textlength(w, font=font) for w, _h in line) + space * (len(line) - 1)
        lx = x + (width - line_w) / 2 if align == "center" else x
        if boxed:
            draw.rectangle((lx - pad, top + int(size * 0.1), lx + line_w + pad,
                            top + int(size * 1.2)), fill=(*accent, 255))
        for word, highlighted in line:
            if boxed:
                # Pavé d'accent : texte sombre, mot surligné en blanc cerclé.
                fill = (255, 255, 255) if highlighted else (12, 16, 28)
                width_stroke = max(2, int(size * 0.05)) if highlighted else 0
                stroke_fill = (12, 16, 28)
            else:
                fill = accent if highlighted else text_rgb
                width_stroke, stroke_fill = stroke, (0, 0, 0)
            draw.text((lx, top), word, font=font, fill=fill,
                      stroke_width=width_stroke, stroke_fill=stroke_fill)
            lx += draw.textlength(word, font=font) + space
        top += line_h + (int(size * 0.2) if boxed else 0)


def _pills(draw, values: list[str], font, x: int, y: int, unit: float, accent,
           max_w: int, center: bool = False) -> int:
    """Bandeau et date en pastilles ; renvoie la hauteur occupée (0 si vide).

    Une pastille qui ne tient pas sur la ligne passe à la ligne suivante.
    """
    values = [v.strip().upper() for v in values if v and v.strip()]
    if not values:
        return 0
    pad_x, pill_h, gap = int(18 * unit), int(48 * unit), int(12 * unit)
    rows: list[list[tuple[int, str, int]]] = [[]]
    used = 0
    for index, value in enumerate(values):
        pill_w = int(draw.textlength(value, font=font)) + pad_x * 2
        if rows[-1] and used + gap + pill_w > max_w:
            rows.append([])
            used = 0
        used += (gap if rows[-1] else 0) + pill_w
        rows[-1].append((index, value, pill_w))
    for row_index, row in enumerate(rows):
        row_w = sum(w for _i, _v, w in row) + gap * (len(row) - 1)
        px = x + (max_w - row_w) // 2 if center else x
        py = y + row_index * (pill_h + gap)
        for index, value, pill_w in row:
            fill = (*accent, 255) if index == 0 else (255, 255, 255, 235)
            draw.rounded_rectangle((px, py, px + pill_w, py + pill_h),
                                   radius=int(10 * unit), fill=fill)
            draw.text((px + pill_w // 2, py + pill_h // 2), value, font=font,
                      fill=(12, 16, 28), anchor="mm")
            px += pill_w + gap
    return len(rows) * pill_h + (len(rows) - 1) * gap


def _medallion(photo, diameter: int, accent):
    """Photo détourée dans un médaillon rond sur fond d'accent."""
    from PIL import Image, ImageDraw

    disc = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter - 1, diameter - 1), fill=255)
    inner = Image.new("RGBA", (diameter, diameter), (*accent, 255))
    scaled = photo.copy()
    scaled.thumbnail((int(diameter * 1.1), int(diameter * 1.15)))
    inner.alpha_composite(scaled, ((diameter - scaled.width) // 2,
                                   max(0, diameter - scaled.height + int(diameter * 0.08))))
    disc.paste(inner, (0, 0), mask)
    ring = ImageDraw.Draw(disc)
    ring.ellipse((0, 0, diameter - 1, diameter - 1), outline=(255, 255, 255, 255),
                 width=max(3, diameter // 40))
    return disc


def thumbnail_photos(profile: ChurchProfile, spec: ThumbnailSpec) -> list[str]:
    """Photos du fond : image choisie, puis photos cochées (ou toutes)."""
    paths = [spec.background] if spec.background else []
    paths += spec.photos or profile.photos
    out: list[str] = []
    for path in paths:
        if path and path not in out and Path(path).is_file():
            out.append(path)
    return out


def _mix(a, b, t: float) -> tuple[int, int, int]:
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))  # type: ignore[return-value]


def _grade_photo(image, profile: ChurchProfile, spec: ThumbnailSpec, unit: float):
    """Traitement « miniature » : flou, lumière, couleur de l'église, grain."""
    from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

    rgb = image.convert("RGB")
    if spec.blur_amount:
        rgb = rgb.filter(ImageFilter.GaussianBlur(spec.blur_amount * 0.9 * unit))
    rgb = ImageEnhance.Contrast(rgb).enhance(1 + spec.contrast / 100)
    rgb = ImageEnhance.Color(rgb).enhance(max(0.0, 1 + spec.saturation / 100))
    if spec.tint_strength:
        base = _rgb(profile.primary_color, "#0B1E3F")
        accent = _rgb(spec.accent or profile.accent_color, "#F0BE64")
        strength = spec.tint_strength / 100
        size = rgb.size
        if spec.tint_mode == "duotone":
            # Ombres dans la couleur de l'église, lumières chaudes (accent).
            toned = ImageOps.colorize(
                ImageOps.grayscale(rgb), black=_mix(base, (0, 0, 0), 0.55),
                white=_mix(accent, (255, 255, 255), 0.65), mid=_mix(base, accent, 0.5))
        elif spec.tint_mode == "color":
            toned = Image.new("RGB", size, base)
            strength *= 0.7
        elif spec.tint_mode == "multiply":
            toned = ImageChops.multiply(rgb, Image.new("RGB", size, _mix(base, (255,) * 3, 0.45)))
        elif spec.tint_mode == "screen":
            toned = ImageChops.screen(rgb, Image.new("RGB", size, _mix(accent, (0,) * 3, 0.55)))
        elif spec.tint_mode == "overlay":
            toned = ImageChops.overlay(rgb, Image.new("RGB", size, accent))
        else:  # soft_light
            toned = ImageChops.soft_light(rgb, Image.new("RGB", size, _mix(base, accent, 0.5)))
        rgb = Image.blend(rgb, toned, strength)
    light = (1 + spec.brightness / 100) * (1 - spec.darkness / 100)
    if abs(light - 1) > 1e-3:
        rgb = ImageEnhance.Brightness(rgb).enhance(max(0.0, light))
    if spec.grain:
        noise = Image.effect_noise(rgb.size, spec.grain * 3).convert("RGB")
        rgb = ImageChops.add(rgb, noise, scale=1.0, offset=-128)
    return rgb.convert("RGBA")


def _vignette(width: int, height: int, strength: int = 170):
    """Coins assombris : le regard va au centre, comme sur les vraies miniatures."""
    from PIL import Image, ImageDraw, ImageFilter

    small = Image.new("L", (width // 8, height // 8), max(0, min(255, strength)))
    ImageDraw.Draw(small).ellipse((-width // 80, -height // 60, width // 8 + width // 80,
                                   height // 8 + height // 60), fill=0)
    mask = small.filter(ImageFilter.GaussianBlur(max(2, width // 90))).resize((width, height))
    shade = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    shade.putalpha(mask)
    return shade


def _cover_spec(path: str, width: int, height: int, spec: ThumbnailSpec):
    """Photo recadrée selon le cadrage vertical et le zoom de la miniature."""
    return _cover(path, width, height, focus_y=spec.focus_y / 100, zoom=spec.zoom / 100)


def _mosaic(paths: list[str], width: int, height: int, unit: float, spec: ThumbnailSpec):
    """2 ou 3 photos : panneaux inclinés, droits ou fondus ; (image, séparations)."""
    from PIL import Image, ImageDraw

    count = min(3, len(paths))
    if spec.blend == "fade":
        return _mosaic_fade(paths[:count], width, height, spec), []
    slant = int(90 * unit) if spec.blend == "slant" else 0
    cuts = [int(width * i / count) for i in range(1, count)]
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    lines = []
    for index in range(count):
        left = cuts[index - 1] if index else None
        right = cuts[index] if index < count - 1 else None
        polygon = [
            (left + slant if left is not None else 0, 0),
            (right + slant if right is not None else width, 0),
            (right - slant if right is not None else width, height),
            (left - slant if left is not None else 0, height),
        ]
        xs = [x for x, _y in polygon]
        panel_w = max(1, max(xs) - min(xs))
        photo = _cover_spec(paths[index], panel_w, height, spec)
        if photo is None:
            continue
        mask = Image.new("L", (width, height), 0)
        ImageDraw.Draw(mask).polygon(polygon, fill=255)
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        layer.paste(photo, (max(0, min(xs)), 0))
        canvas.paste(layer, (0, 0), mask)
        if right is not None:
            lines.append(((right + slant, 0), (right - slant, height)))
    return canvas, lines


def _mosaic_fade(paths: list[str], width: int, height: int, spec: ThumbnailSpec):
    """Photos fondues les unes dans les autres (fusion sans séparation)."""
    from PIL import Image

    count = len(paths)
    panel = width / count
    fade = int(panel * spec.blend_width / 100)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    for index, path in enumerate(paths):
        x0 = int(index * panel) - (fade // 2 if index else 0)
        x1 = int((index + 1) * panel) + (fade // 2 if index < count - 1 else 0)
        photo = _cover_spec(path, max(1, x1 - x0), height, spec)
        if photo is None:
            continue
        ramp = Image.new("L", (photo.width, 1), 255)
        if index and fade:
            for x in range(min(fade, photo.width)):
                t = x / max(1, fade - 1)
                ramp.putpixel((x, 0), int(255 * (t * t * (3 - 2 * t))))  # lissé
        photo.putalpha(ramp.resize(photo.size))
        canvas.alpha_composite(photo, (x0, 0))
    return canvas


def thumbnail_background(profile: ChurchProfile, spec: ThumbnailSpec,
                         width: int, height: int):
    """Fond de miniature composé des photos de l'église (ou fond uni)."""
    from PIL import Image, ImageDraw, ImageEnhance

    spec = spec.sanitized()
    unit = height / 720
    paths = thumbnail_photos(profile, spec)
    vignette = int(spec.vignette * 2.5)
    if spec.composition == "plain" or not paths:
        image = _background(width, height, profile)
        light = (1 + spec.brightness / 100) * (1 - spec.darkness / 100)
        if abs(light - 1) > 1e-3:
            image = ImageEnhance.Brightness(image.convert("RGB")).enhance(light).convert("RGBA")
        return Image.alpha_composite(image, _vignette(width, height, vignette))
    lines = []
    if spec.composition == "mosaic" and len(paths) >= 2:
        image, lines = _mosaic(paths, width, height, unit, spec)
    else:
        image = _cover_spec(paths[0], width, height, spec)
        if image is None:
            return _background(width, height, profile)
    image = _grade_photo(image, profile, spec, unit)
    if vignette:
        image = Image.alpha_composite(image, _vignette(width, height, vignette))
    if lines:
        accent = _rgb(spec.accent or profile.accent_color, "#F0BE64")
        draw = ImageDraw.Draw(image)
        for start, end in lines:
            draw.line([start, end], fill=(*accent, 255), width=max(4, int(7 * unit)))
    return image


def render_youtube_thumbnail(profile: ChurchProfile, spec: ThumbnailSpec,
                             width: int = THUMBNAIL_SIZE[0], height: int = THUMBNAIL_SIZE[1]):
    """Miniature YouTube : grand titre lisible, orateur détouré, logo et date.

    Mises en page (``spec.layout``) : split (orateur en grand à côté du
    titre), boxed (titre sur pavés de couleur), band (bandeau en bas),
    center (titre centré, orateur en médaillon). Les mots du titre écrits
    entre astérisques (« Le *vrai* repos ») prennent la couleur d'accent.
    """
    from PIL import Image, ImageDraw, ImageFilter

    profile = profile.sanitized()
    spec = spec.sanitized()
    layout = spec.layout
    accent = _rgb(spec.accent or profile.accent_color, "#F0BE64")
    text_rgb = _rgb(profile.text_color, "#FFFFFF")
    unit = height / 720
    margin = int(52 * unit)
    family = profile.font_family

    image = thumbnail_background(profile, spec, width, height)

    speaker_title, speaker_name, photo_path = speaker_info(profile)
    source_photo = None
    if spec.show_speaker:
        max_h = 0.98 if layout != "center" else 0.5
        source_photo = _photo_image(photo_path, int(width * 0.46), int(height * max_h))
    photo = source_photo if layout != "center" else None
    on_left = spec.photo_side == "left"
    centered = layout == "center"

    # Voile : dégradé côté texte, uniforme pour un titre centré. Plus léger
    # sur les photos de l'église pour qu'elles restent bien visibles.
    photo_bg = spec.composition != "plain" and bool(thumbnail_photos(profile, spec))
    veil = spec.text_veil / 80  # 80 = réglage par défaut
    if centered:
        alpha = int(min(255, (80 if photo_bg else 130) * veil))
        image = Image.alpha_composite(image, Image.new("RGBA", (width, height), (0, 0, 0, alpha)))
    elif spec.text_veil:
        image = Image.alpha_composite(image, _horizontal_veil(
            width, height, int(min(255, (200 if photo_bg else 215) * veil)),
            on_left and photo is not None, reach=0.62 if photo_bg else 0.8))

    text_left, text_right = margin, width - margin
    if photo is not None:
        px = margin // 2 if on_left else width - photo.width - margin // 2
    if photo is not None and spec.glow:
        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        radius = int(min(photo.width, photo.height) * 0.46)
        cx, cy = px + photo.width // 2, height - int(photo.height * 0.52)
        ImageDraw.Draw(glow).ellipse(
            (cx - radius, cy - radius, cx + radius, cy + radius),
            fill=(*accent, int(spec.glow * 2.5)),
        )
        image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(int(60 * unit))))
    if photo is not None:
        if on_left:
            text_left = px + photo.width + int(10 * unit)
        else:
            text_right = px - int(10 * unit)
    text_w = max(int(width * 0.42), text_right - text_left)

    # Bandeau en bas : pavé sombre sous le titre (la photo passe devant).
    band_top = int(height * 0.48)
    if layout == "band":
        dark = tuple(max(0, int(c * 0.35)) for c in _rgb(profile.primary_color, "#0B1E3F"))
        band = Image.new("RGBA", (width, height - band_top), (*dark, 236))
        image.alpha_composite(band, (0, band_top))
        ImageDraw.Draw(image).rectangle((0, band_top, width, band_top + int(8 * unit)),
                                        fill=(*accent, 255))
    if photo is not None:
        shadow = Image.new("RGBA", photo.size, (0, 0, 0, 0))
        shadow.putalpha(photo.getchannel("A").point(lambda a: int(a * 0.55)))
        image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(int(14 * unit))),
                              (px + int(10 * unit), height - photo.height))
        image.alpha_composite(photo, (px, height - photo.height))
    if layout == "boxed":
        frame = max(6, int(10 * unit))
        ImageDraw.Draw(image).rectangle((0, 0, width - 1, height - 1), outline=(*accent, 255),
                                        width=frame)
    draw = ImageDraw.Draw(image)

    # En-tête : logo + nom de l'église.
    y = margin
    logo = None
    if profile.logo and Path(profile.logo).is_file():
        try:
            logo = Image.open(profile.logo).convert("RGBA")
            logo.thumbnail((int(170 * unit), int(62 * unit)))
        except Exception:
            logo = None
    name_font = _font(family, int(28 * unit))
    if centered:
        header_h = 0
        if logo is not None:
            image.alpha_composite(logo, ((width - logo.width) // 2, y))
            header_h = logo.height + int(8 * unit)
        if profile.name:
            draw.text((width // 2, y + header_h), profile.name, font=name_font, fill=text_rgb,
                      anchor="ma", stroke_width=max(1, int(2 * unit)), stroke_fill=(0, 0, 0))
            header_h += int(36 * unit)
        y += max(header_h, int(34 * unit)) + int(18 * unit)
    else:
        logo_h = logo_w = 0
        if logo is not None:
            image.alpha_composite(logo, (text_left, y))
            logo_h, logo_w = logo.height, logo.width
        if profile.name:
            nx = text_left + (logo_w + int(14 * unit) if logo_h else 0)
            draw.text((nx, y + (logo_h // 2 if logo_h else int(16 * unit))), profile.name,
                      font=name_font, fill=text_rgb, anchor="lm",
                      stroke_width=max(1, int(2 * unit)), stroke_fill=(0, 0, 0))
        y += max(logo_h, int(34 * unit)) + int(26 * unit)

    pill_font = _font(family, int(28 * unit))
    pills_h = _pills(draw, [spec.label, spec.date], pill_font,
                     margin if centered else text_left, y, unit, accent,
                     max_w=width - 2 * margin if centered else text_w, center=centered)
    if pills_h:
        y += pills_h + int(22 * unit)

    # Pied : orateur (titre + nom) et référence biblique.
    speaker_line = (" ".join(p for p in (speaker_title, speaker_name) if p).strip()
                    if spec.show_speaker else "")
    footer_h = int(110 * unit) if (speaker_line or spec.reference) else 0
    if centered and source_photo is not None:
        footer_h = max(footer_h, int(130 * unit))
    footer_top = height - margin - footer_h

    text = spec.title.strip() or "Titre de la prédication"
    if spec.uppercase:
        text = text.upper()
    words = _highlight_words(text)
    boxed = layout == "boxed"
    if layout == "band":
        box_top = band_top + int(30 * unit)
        box_h = footer_top - box_top - int(6 * unit)
        font, lines, size, line_h = _fit_title(draw, words, family, text_w, box_h, unit,
                                               max_lines=2, start=100)
        ty = box_top
    else:
        box_h = footer_top - y - int(16 * unit)
        box_w = width - 2 * margin if centered else text_w - (int(20 * unit) if boxed else 0)
        # Pavés : chaque ligne prend ~18 % de hauteur en plus (espacement).
        font, lines, size, line_h = _fit_title(draw, words, family, box_w,
                                               int(box_h * 0.84) if boxed else box_h, unit,
                                               max_lines=3 if boxed else 4)
        if boxed:
            total = len(lines) * (line_h + int(size * 0.2))
        else:
            total = len(lines) * line_h
        ty = y + max(0, (box_h - total) // 2)
    _draw_title(draw, lines, font, size, line_h,
                margin if centered else text_left + (int(size * 0.16) if boxed else 0),
                width - 2 * margin if centered else text_w, ty, accent, text_rgb,
                align="center" if centered else "left", boxed=boxed)

    if not footer_h:
        return image
    if centered:
        cx = width // 2
        fy = footer_top + int(10 * unit)
        if source_photo is not None:
            diameter = int(120 * unit)
            disc = _medallion(source_photo, diameter, accent)
            name_w = draw.textlength(speaker_line, font=_font(family, int(38 * unit)))
            block_w = diameter + int(20 * unit) + name_w
            left = int(cx - block_w / 2)
            image.alpha_composite(disc, (left, footer_top + (footer_h - diameter) // 2))
            tx = left + diameter + int(20 * unit)
            draw = ImageDraw.Draw(image)
            draw.text((tx, fy + int(22 * unit)), speaker_line, font=_font(family, int(38 * unit)),
                      fill=text_rgb, stroke_width=max(1, int(3 * unit)), stroke_fill=(0, 0, 0))
            if spec.reference:
                draw.text((tx, fy + int(70 * unit)), spec.reference,
                          font=_font(family, int(28 * unit), bold=False), fill=accent)
            return image
        if speaker_line:
            draw.text((cx, fy), speaker_line, font=_font(family, int(40 * unit)), fill=text_rgb,
                      anchor="ma", stroke_width=max(1, int(3 * unit)), stroke_fill=(0, 0, 0))
        if spec.reference:
            draw.text((cx, fy + (int(50 * unit) if speaker_line else 0)), spec.reference,
                      font=_font(family, int(30 * unit), bold=False), fill=accent, anchor="ma")
        return image
    fy = footer_top + int(20 * unit)
    draw.rectangle((text_left, fy, text_left + int(8 * unit), fy + int(76 * unit)), fill=accent)
    fx = text_left + int(24 * unit)
    if speaker_line:
        draw.text((fx, fy), speaker_line, font=_font(family, int(40 * unit)),
                  fill=text_rgb, stroke_width=max(1, int(3 * unit)), stroke_fill=(0, 0, 0))
    if spec.reference:
        draw.text((fx, fy + (int(48 * unit) if speaker_line else int(18 * unit))),
                  spec.reference, font=_font(family, int(30 * unit), bold=False),
                  fill=accent, stroke_width=max(1, int(2 * unit)), stroke_fill=(0, 0, 0))
    return image


def save_thumbnail(image, path: Path) -> Path:
    """Enregistre la miniature sous la limite de 2 Mo de YouTube.

    PNG si le fichier tient sous la limite, sinon JPEG de qualité décroissante.
    """
    from io import BytesIO

    path = Path(path)
    rgb = image.convert("RGB")
    if path.suffix.lower() == ".png":
        buffer = BytesIO()
        rgb.save(buffer, "PNG", optimize=True)
        if buffer.tell() <= THUMBNAIL_MAX_BYTES:
            path.write_bytes(buffer.getvalue())
            return path
        path = path.with_suffix(".jpg")
    for quality in (95, 90, 85, 80, 70, 60):
        buffer = BytesIO()
        rgb.save(buffer, "JPEG", quality=quality, optimize=True, progressive=True)
        if buffer.tell() <= THUMBNAIL_MAX_BYTES:
            break
    path.write_bytes(buffer.getvalue())
    return path
