from __future__ import annotations

from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "social"
LOGO = ROOT / "assets" / "logo" / "app icon.png"
CAPTURE = ROOT / "video-promo" / "public" / "captures" / "12-demo-projection.png"
FONTS = ROOT / "assets" / "fonts" / "Poppins"


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def clean_logo(size: int) -> Image.Image:
    logo = Image.open(LOGO).convert("RGBA")
    px = logo.load()
    for y in range(logo.height):
        for x in range(logo.width):
            r, g, b, a = px[x, y]
            if a > 0 and r < 6 and g < 6 and b < 6:
                px[x, y] = (r, g, b, 0)
    logo.thumbnail((size, size), Image.Resampling.LANCZOS)
    return logo


def cover_image(path: Path, size: tuple[int, int]) -> Image.Image:
    img = Image.open(path).convert("RGB")
    sw, sh = size
    scale = max(sw / img.width, sh / img.height)
    nw, nh = int(img.width * scale), int(img.height * scale)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - sw) // 2
    top = (nh - sh) // 2
    return img.crop((left, top, left + sw, top + sh))


def gradient_bg(size: tuple[int, int]) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size, "#07111f")
    px = img.load()
    for y in range(h):
        for x in range(w):
            nx = x / w
            ny = y / h
            r = int(7 + 12 * nx + 2 * (1 - ny))
            g = int(13 + 24 * nx + 5 * (1 - ny))
            b = int(28 + 44 * nx + 12 * (1 - ny))
            px[x, y] = (r, g, b)
    return img.convert("RGBA")


def add_glow(img: Image.Image, x: int, y: int, radius: int, color: tuple[int, int, int, int]) -> None:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for rr in range(radius, 0, -10):
        a = int(color[3] * (1 - rr / radius) ** 2)
        d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=color[:3] + (a,))
    img.alpha_composite(overlay)


def rounded_shadow(img: Image.Image, box: tuple[int, int, int, int], radius: int) -> None:
    x0, y0, x1, y1 = box
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((x0 + 12, y0 + 18, x1 + 12, y1 + 18), radius=radius, fill=(0, 0, 0, 120))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    img.alpha_composite(shadow)


def draw_wrapped(
    d: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    width_chars: int,
    fnt: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    line_gap: int,
) -> int:
    x, y = xy
    for line in wrap(text, width=width_chars):
        d.text((x, y), line, font=fnt, fill=fill)
        y += fnt.size + line_gap
    return y


def make_card(filename: str, size: tuple[int, int], layout: str) -> None:
    w, h = size
    img = gradient_bg(size)
    add_glow(img, int(w * 0.18), int(h * 0.16), int(w * 0.42), (72, 196, 239, 85))
    add_glow(img, int(w * 0.88), int(h * 0.14), int(w * 0.46), (255, 178, 48, 95))
    d = ImageDraw.Draw(img)

    logo = clean_logo(int(min(w, h) * (0.18 if layout != "story" else 0.16)))
    accent = (246, 182, 63, 255)
    cyan = (75, 196, 239, 240)
    white = (248, 250, 252, 255)
    muted = (203, 213, 225, 235)

    capture = cover_image(CAPTURE, (int(w * 0.58), int(h * 0.42)))
    capture = capture.convert("RGBA")
    overlay = Image.new("RGBA", capture.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rectangle((0, 0, *capture.size), fill=(0, 0, 0, 24))
    capture.alpha_composite(overlay)

    if layout == "landscape":
        margin = 56
        logo_pos = (margin, 46)
        img.alpha_composite(logo, logo_pos)
        text_x = margin
        title_y = 190
        shot_box = (w - capture.width - 50, 96, w - 50, 96 + capture.height)
        rounded_shadow(img, shot_box, 28)
        mask = Image.new("L", capture.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, *capture.size), radius=28, fill=255)
        img.paste(capture, shot_box[:2], mask)
        d.rounded_rectangle((text_x, title_y - 26, text_x + 138, title_y - 16), radius=5, fill=accent)
        d.rounded_rectangle((text_x + 154, title_y - 26, text_x + 230, title_y - 16), radius=5, fill=cyan)
        d.text((text_x, title_y), "Telechargez", font=font("Poppins-Bold.ttf", 58), fill=white)
        d.text((text_x, title_y + 70), "ProjectOn", font=font("Poppins-Bold.ttf", 70), fill=accent)
        y = draw_wrapped(d, "Le logiciel de projection pour vos cultes: Bible, cantiques, predications et OBS.", (text_x, title_y + 160), 38, font("Poppins-Medium.ttf", 28), muted, 8)
        d.rounded_rectangle((text_x, y + 22, text_x + 410, y + 78), radius=18, fill=(246, 182, 63, 255))
        d.text((text_x + 24, y + 34), "Lien dans la description", font=font("Poppins-SemiBold.ttf", 24), fill=(7, 12, 23, 255))
    elif layout == "story":
        img.alpha_composite(logo, ((w - logo.width) // 2, 110))
        d.text((72, 385), "ProjectOn", font=font("Poppins-Bold.ttf", 94), fill=white)
        d.text((72, 500), "est pret pour votre culte", font=font("Poppins-SemiBold.ttf", 42), fill=accent)
        shot_w, shot_h = int(w * 0.86), int(h * 0.34)
        shot = cover_image(CAPTURE, (shot_w, shot_h)).convert("RGBA")
        shot_box = ((w - shot_w) // 2, 690, (w + shot_w) // 2, 690 + shot_h)
        rounded_shadow(img, shot_box, 34)
        mask = Image.new("L", shot.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, *shot.size), radius=34, fill=255)
        img.paste(shot, shot_box[:2], mask)
        y = draw_wrapped(d, "Preparez la Bible, les cantiques et les predications dans une seule playlist.", (72, 1360), 26, font("Poppins-Medium.ttf", 42), muted, 10)
        d.rounded_rectangle((72, y + 50, w - 72, y + 126), radius=24, fill=accent)
        d.text((112, y + 68), "Telechargez et utilisez", font=font("Poppins-Bold.ttf", 34), fill=(7, 12, 23, 255))
    else:
        margin = 58
        img.alpha_composite(logo, (margin, margin))
        d.rounded_rectangle((margin, 280, margin + 150, 292), radius=6, fill=accent)
        d.rounded_rectangle((margin + 170, 280, margin + 260, 292), radius=6, fill=cyan)
        d.text((margin, 315), "Telechargez", font=font("Poppins-Bold.ttf", 66), fill=white)
        d.text((margin, 390), "ProjectOn", font=font("Poppins-Bold.ttf", 82), fill=accent)
        y = draw_wrapped(d, "Projetez vos versets, cantiques et predications avec clarte.", (margin, 510), 31, font("Poppins-Medium.ttf", 34), muted, 10)
        shot_w, shot_h = w - margin * 2, 330
        shot = cover_image(CAPTURE, (shot_w, shot_h)).convert("RGBA")
        shot_box = (margin, y + 42, margin + shot_w, y + 42 + shot_h)
        rounded_shadow(img, shot_box, 28)
        mask = Image.new("L", shot.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, *shot.size), radius=28, fill=255)
        img.paste(shot, shot_box[:2], mask)
        d.rounded_rectangle((margin, h - 135, w - margin, h - 70), radius=22, fill=(246, 182, 63, 255))
        d.text((margin + 32, h - 119), "Lien de telechargement dans la description", font=font("Poppins-SemiBold.ttf", 25), fill=(7, 12, 23, 255))

    # Small footer.
    footer = "Bible - Cantiques - Predications - Projection - OBS"
    bbox = d.textbbox((0, 0), footer, font=font("Poppins-Medium.ttf", 18))
    d.text(((w - (bbox[2] - bbox[0])) // 2, h - 34), footer, font=font("Poppins-Medium.ttf", 18), fill=(148, 163, 184, 190))

    OUT.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(OUT / filename, quality=96)
    print(OUT / filename)


def main() -> int:
    make_card("projecton-social-square.png", (1080, 1080), "square")
    make_card("projecton-social-story.png", (1080, 1920), "story")
    make_card("projecton-social-landscape.png", (1200, 628), "landscape")
    make_card("projecton-social-whatsapp.png", (1080, 1350), "square")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
