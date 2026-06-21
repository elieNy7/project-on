"""Generate the bundled default projection backgrounds.

Produces two families of dark images (suited to white projected text) in the
three common projection ratios, written to ``assets/backgrounds/``:

* **Unis** — tasteful dark gradients with a soft vignette.
* **Symboles chrétiens** — the same gradients overlaid with a discreet,
  centred symbol used in the Message (la croix, plus the four-living-creatures
  figures: l'aigle, le lion et l'agneau). The watermark is faint and glows
  softly so the projected white text stays perfectly legible on top.

The animal figures are rendered from silhouettes by game-icons.net
(Lorc & Delapouite), licensed CC BY 3.0 — see ``assets/backgrounds/CREDITS.txt``.

These are seeded into the user's backgrounds folder on first launch
(see ``app_paths.seed_default_backgrounds``).

Run:  py -3 tools/generate_backgrounds.py
"""
from __future__ import annotations

import io
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

# Qt renders the figurative silhouettes (SVG paths) crisply; run head-less.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRectF  # noqa: E402
from PyQt6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PyQt6.QtSvg import QSvgRenderer  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# (slug, start color, end color) — dark so projected white text stays legible
PALETTES = {
    "bleu-nuit": ((10, 24, 48), (27, 58, 107)),
    "or-sombre": ((26, 18, 6), (92, 62, 20)),
    "ardoise": ((14, 17, 23), (42, 51, 64)),
    "pourpre": ((22, 10, 38), (61, 31, 94)),
}

# (slug, width, height)
RATIOS = [
    ("16x9", 1920, 1080),
    ("4x3", 1440, 1080),
    ("9x16", 1080, 1920),
]

ANGLE = 135  # diagonal gradient
VIGNETTE_STRENGTH = 0.55
SUPERSAMPLE = 4  # draw symbols at higher resolution then downscale for clean edges


# ─────────────────────────── base gradient ────────────────────────────
def make_gradient(size: tuple[int, int], c1, c2, angle: int = ANGLE) -> Image.Image:
    w, h = size
    diag = int((w ** 2 + h ** 2) ** 0.5)
    ramp = Image.linear_gradient("L").resize((diag, diag))
    ramp = ramp.rotate(angle, expand=False)
    left = (diag - w) // 2
    top = (diag - h) // 2
    ramp = ramp.crop((left, top, left + w, top + h))
    return ImageOps.colorize(ramp, black=c1, white=c2).convert("RGB")


def add_vignette(img: Image.Image, strength: float = VIGNETTE_STRENGTH) -> Image.Image:
    w, h = img.size
    vig = Image.radial_gradient("L").resize((w, h))
    mask = vig.point(lambda v: int(v * strength))
    overlay = Image.new("RGB", (w, h), (0, 0, 0))
    return Image.composite(overlay, img, mask)


# ─────────────────────────── symbol drawing ───────────────────────────
# All symbols are drawn in solid white on a transparent supersampled layer,
# centred on the canvas. ``unit`` is a length proportional to the canvas so
# symbols scale identically across ratios. Strokes use rounded caps/joins so
# downscaled edges stay smooth and professional.

def _draw_latin_cross(d: ImageDraw.ImageDraw, cx, cy, unit):
    h = unit * 2.6
    w = unit * 1.7
    bar = unit * 0.30          # arm thickness
    top = cy - h * 0.52
    # vertical beam
    d.rounded_rectangle([cx - bar / 2, top, cx + bar / 2, top + h],
                        radius=bar * 0.5, fill=255)
    # horizontal beam (placed ~1/3 from the top)
    yb = top + h * 0.34
    d.rounded_rectangle([cx - w / 2, yb - bar / 2, cx + w / 2, yb + bar / 2],
                        radius=bar * 0.5, fill=255)


# ── Figurative silhouettes (SVG, viewBox 0 0 512 512) ──────────────────
# Source: game-icons.net — eagle by Lorc, lion by Lorc, sheep by Delapouite.
# Licensed CC BY 3.0 (https://creativecommons.org/licenses/by/3.0/).
_SVG_EAGLE = "M35.31 22.3C27.498 42.766 22.138 64.643 20 87.378l103.705 27.79-4.838 18.052-99.873-26.763c-.012.954-.035 1.905-.035 2.86 0 14.055 1.196 27.83 3.48 41.23h94.146v18.687H26.393c3.368 13.324 7.83 26.207 13.29 38.547l79.184-21.216 4.838 18.05-75.64 20.27c5.994 11.096 12.817 21.67 20.396 31.636l61.933-35.756 9.343 16.183-59.22 34.192c7.782 8.728 16.18 16.885 25.132 24.4l44.73-44.726 13.214 13.215-43.055 43.052c8.963 6.406 18.374 12.215 28.186 17.357l28.734-49.772 16.186 9.346-27.987 48.472c12.545 5.367 25.63 9.697 39.156 12.87.99 3.566 2.08 7.103 3.25 10.593-12.36 9.993-24.163 20.49-35.12 31.728-4.458-2.16-9.46-3.373-14.75-3.373-18.707 0-33.874 15.164-33.874 33.873 0 1.715.13 3.402.377 5.05 2.02-11.514 12.06-20.265 24.153-20.265 3.103 0 6.068.582 8.8 1.633-10.103 12.102-19.193 25.08-26.906 39.23 13.897-7.544 27.684-15.755 41.15-24.764.96 2.63 1.485 5.468 1.485 8.43 0 12.122-8.796 22.184-20.352 24.168 1.685.258 3.412.393 5.168.393 18.71 0 33.873-15.168 33.873-33.875 0-4.17-.757-8.16-2.134-11.848 10.033-7.467 19.823-15.43 29.26-23.984 2.978 5.705 6.203 11.034 9.65 15.818l-43.53 87.17c48.267 22.47 115.7 22.76 157.872 0l-42.13-84.36c3.722-4.81 7.21-10.25 10.426-16.14 8.577 7.617 17.428 14.77 26.483 21.508-1.375 3.685-2.13 7.67-2.13 11.836 0 18.707 15.165 33.873 33.874 33.873 1.758 0 3.486-.132 5.172-.39-11.56-1.983-20.355-12.045-20.355-24.168 0-2.964.525-5.805 1.49-8.435 13.464 9.006 27.247 17.223 41.143 24.767-7.71-14.148-16.78-27.136-26.877-39.238 2.726-1.045 5.682-1.623 8.775-1.623 12.09 0 22.13 8.75 24.15 20.262.246-1.647.377-3.332.377-5.047 0-18.71-15.166-33.873-33.875-33.873-5.275 0-10.268 1.205-14.72 3.355-10.007-10.27-20.74-19.908-31.946-29.12 1.938-5.52 3.658-11.18 5.132-16.886 7.91-2.368 15.65-5.14 23.2-8.283l-28.497-49.356 16.186-9.346 29.34 50.816c9.98-5.11 19.555-10.9 28.672-17.308l-44.146-44.147 13.215-13.216 45.926 45.922c9.145-7.557 17.72-15.785 25.666-24.6l-60.95-35.19 9.343-16.182 63.748 36.804c7.76-10.087 14.746-20.807 20.87-32.07l-77.93-20.883 4.837-18.05 81.534 21.847c5.588-12.533 10.157-25.625 13.584-39.178h-92.836v-18.687h96.777c2.282-13.4 3.48-27.174 3.48-41.23 0-1.19-.025-2.376-.044-3.563L397.652 133.22l-4.836-18.054L499.09 86.69c-2.18-22.49-7.52-44.13-15.254-64.39h-.004C457.315 63.81 400.24 96.234 329.068 109.32c12.67 15.603 20.442 35.52 20.442 57.233 0 31.196-15.723 58.718-39.604 75-21.27-12.407-42.907-28.878-45.52-43.814l17.653-3.81-2.235-10.352c15.67-11.335 33.936-9.138 53.433-.01l-18.302-40.414-41.903 9.04-2.846-13.188V139l-80.87 17.453 20.458 30.266c-8.595 19.678-2.717 41.68 5.45 58.56-27.204-15.57-45.592-44.998-45.592-78.73 0-21.713 7.772-41.63 20.44-57.232C118.904 96.234 61.83 63.81 35.312 22.3zm216.45 132.567c5.244-.056 9.98 3.573 11.13 8.9 1.312 6.085-2.557 12.084-8.644 13.397-6.087 1.313-12.085-2.556-13.398-8.643-1.314-6.085 2.556-12.086 8.642-13.4.76-.163 1.52-.245 2.27-.253z"  # noqa: E501

_SVG_LION = "M123.885 20.447c-10.348.467-21.337 3.146-32.194 5.366l62.492 65.628-21.645.188c-29.376.187-75.695 6.154-103.555 22.303l31.756 51.576-40.625 21.098v56.577l46.54 26.32-46.54 40.076v32.268c28.217-1.233 60.63.636 89.135-8.907l31.902-10.658-21.828 25.586c-18.76 22-29.782 55.133-50.736 87.713 31.91-2.394 63.352-7.65 96.8-25.81l16.026-8.683-9.746 77.124c26.333-12.19 52.103-28.923 71.178-49.055 22.683-23.94 35.713-50.49 33.36-72.71l-.074-.75c-18.488-12.687-32.26-31.173-39.236-54.18-8.414-27.753-5.867-62.33 6.643-101.145-26.406-4.04-46.536-14.637-57.307-30.11-12.33-17.716-14.222-39.26-7.738-57.018 6.483-17.758 22.29-32.165 43.437-33.4 20.558-1.195 44.48 10.033 69.972 36.102 11.368 4.11 21.73 8.034 31.14 11.94 2.434-21.395-1.46-38.033-10.408-52.9-8.41-13.975-23.217-26.43-41.1-38.582l4.27 42.888-16.425-10.985C222.37 43.57 168.973 18.49 123.885 20.597l.002-.225zm100.387 77.997c-.436.008-.866 0-1.29 0h-.002c-13.54.785-22.545 9.105-26.937 21.135-4.393 12.03-3.243 27.353 5.51 39.93 8.755 12.576 25.128 23.158 53.548 24.784l12.595.69-4.344 11.827c-14.837 40.46-16.242 73.928-8.577 99.212 7.66 25.267 24.04 42.795 47.305 52.56h.037l108.59 38.474c5.65-11.9 11.672-23.813 17.988-35.71-4.997 2.188-10.513 3.41-16.32 3.41-22.52 0-40.78-18.262-40.78-40.782 0-22.518 18.26-40.78 40.78-40.78 20.66 0 37.697 15.373 40.373 35.3 10.666-18.062 21.885-36 33.48-53.683l-103.224-52.377-4.746-5.732c-3.93-13.556-11.515-23.32-26.39-33.324-14.876-10.002-37.034-19.57-67.784-30.623l-2.08-.767-1.53-1.607c-23.283-24.532-42.7-32.278-56.202-32.024zm119.04 89.93c8.272 0 14.657 6.387 14.657 14.657 0 8.274-6.387 14.688-14.658 14.688-8.27 0-14.687-6.414-14.687-14.687 0-8.27 6.416-14.655 14.687-14.655z"  # noqa: E501

_SVG_AGNEAU = "M392.8 107.5c9.3 5.3 25.8 9.3 40 9.2 7.7-.1 14.6-1.2 19.5-3.2 5-1.8 6.9-4.9 8.9-8.8-9.2-6.08-22.1-12.27-31.8-12.87-14.9.53-28.8 8.13-36.6 15.67zm-253 20.2c-1.7 5.5-7.9 8.1-13 5.4-26.5-14.5-50.46-6.9-67.71 8.7-35.93 32.6-45.13 87.3-32.47 145.7 7.31 33.6 18.99 53 41.29 62.8 0 .1.1.1.15.1 2.22 1 4.21 1.9 6.09 2.8l4.61-22c1.02-4.9 5.8-8 10.66-7s7.98 5.8 6.96 10.7l-23.5 112c4.79 7.2 16.4 1.2 21.3-1.2l38.12-106.5c10.8-9.4 21.2-19 28.7-29.2 6.6-9.1 10.4-18.4 10.6-23.5.2-5 4.4-8.9 9.4-8.7 5 .2 9 4.6 8.6 9.6-.6 11.2-6.2 22.4-14 33.2-7.3 10-16.7 19.6-27.2 27.2l-3.3 8.9c6.9 8.7 13.4 13.8 19.6 16.8 8.8 4.1 17.7 4.6 28.5 3.3 16.4-1.9 34.6-12.9 43.5-37.2 2.8-7.7 13.6-8 16.8-.5 7.7 21.2 36.1 32.6 55.1 24l-3.9-23.3c-.8-4.9 2.5-9.6 7.4-10.4 4.9-.9 9.6 2.5 10.4 7.4l17.6 105.9c9.2 6.3 14.5 2.4 19.9-4.4l-13.8-114.4c-.7-5.3 3.3-10 8.6-10.2 4.8-.2 8.8 3.3 9.3 8l4.3 35.7c5.1-1.2 9.1-2.5 12.4-5 4.3-3.2 8.5-8.7 12.1-21.5 1.7-6 9-8.5 14.1-4.7 13.6 8.3 27.4-1.8 35.6-12.2 12.9-16.5 14.7-42.4 13.2-69.2-2.1.3-4.2.5-6.3.6-8.8.5-17.9-.9-25.7-4.4-12.4-7-22-18.4-28.2-28.9-3.9-6.8-7.3-13.7-10.5-20-5.4 9.9-11 23.1-19.2 25-12.5 2.1-23.9-3.7-29.8-12.7-5.9-8.9-7.4-20.2-4.8-31.1 2.7-11.7 9.8-38.3 22.6-56.1 2.2-2.9 4.5-5.3 6.8-7.4-7.5-3.1-16.2-3.8-22.9-3.8-5.8 0-13.5 1.8-19.7 5-6.2 3.3-10.7 7.8-12.2 11.8-3.2 8.5-15.5 7.5-17.3-1.3-3.8-22.78-53.9-17.8-65.6 2-3.8 7-14.1 5.9-16.5-1.7-8.1-22.61-62.7-21.3-66.7 5.9zm345-1.5c1.7 16.4 3.5 32.2 4.2 45.6 1.8 6.5 6 18.9 8.7 7.3.9-4.1.8-11-.4-18.6-.1-7.1-14.5-47.3-12.5-34.3zm-112.7-2.5c-11.9 15-19.2 37.4-23.3 53.7-.6 5.8-.6 12.6 2.3 17.1 2.3 3.4 4.8 5.2 9.4 5 5.8-9.4 12.1-19.8 15.6-28.2-1.2-7.9-2.8-19.9-3.6-31.4-.4-5.8-.6-11.2-.4-16.2zm94.4 2.4c-2.4 1.6-4.8 3.1-7.5 4.1-7.8 3.2-16.8 4.4-26 4.5-14.8.1-30.2-2.7-42.9-8.4 0 3.6.1 7.7.4 12.3.9 12.6 3 27.2 4 33.5 10.5 16.6 19.9 44.4 36.8 52.5 5.8 2 11.9 3.1 17.2 2.9 6-.4 10.6-2.6 11.5-3.7 3.5-8 5.9-15.2 7.3-22.3 2.1-10.9 3.4-23.3 3.6-31.6.3-6.4-.6-13.3-1.1-18.7-1.4 4.1-5.7 6.6-10 5.9-4.3-.7-7.5-4.4-7.5-8.8 0-5.1 4.2-9.2 9.3-9 3 0 5.8 1.7 7.4 4.3-.9-6.1-1.4-12-2.5-17.5zm-58.3 16.5c4.9.2 8.7 4.2 8.7 9 0 5-4 9-9 9-4.9 0-9-4-9-9s4.2-9.1 9.3-9zm47.5 48.3c3.7-.1 6.5 1.9 6.5 6.2 0 7.8-5.8 15-12.7 19l-1-23.1c2.5-1.4 5-2.1 7.2-2.1zm-24.1 2c1.8-.1 3.9.4 5.8 1.3l3.8 22.5c-6-3.7-15.4-3.6-16.5-16.1-.5-5.2 2.8-7.7 6.9-7.7zm-30.9 164.2c-3.7 5.1-7.6 9.1-12.6 12.1l16.6 62c7.6 1.5 15.9 1 19.2-5.1zm-241.2 33.7l1.5 46.8c7.9 7.9 12.9 4.8 19.7-3l-3.7-39.5c-6.3-.9-12.6-2.2-17.5-4.3z"  # noqa: E501

SVG_SYMBOLS = {
    "aigle": _SVG_EAGLE,
    "lion": _SVG_LION,
    "agneau": _SVG_AGNEAU,
}

SYMBOL_DRAWERS = {
    "croix": _draw_latin_cross,
}

# (model slug, palette slug, symbol slug, watermark opacity 0..1)
SYMBOL_MODELS = [
    ("croix", "bleu-nuit", "croix", 0.12),
    ("aigle", "or-sombre", "aigle", 0.13),
    ("lion", "pourpre", "lion", 0.13),
    ("agneau", "ardoise", "agneau", 0.14),
]

_QAPP = None


def _ensure_qapp() -> None:
    global _QAPP
    if _QAPP is None and QGuiApplication.instance() is None:
        _QAPP = QGuiApplication([])


def _render_svg_mask(path_d: str, box: int) -> Image.Image:
    """Rasterise a white SVG path (512 viewBox) into a square 'L' mask."""
    _ensure_qapp()
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
        f'<path d="{path_d}" fill="#ffffff"/></svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    img = QImage(box, box, QImage.Format.Format_ARGB32)
    img.fill(0)
    painter = QPainter(img)
    renderer.render(painter, QRectF(0, 0, box, box))
    painter.end()

    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    pil = Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")
    return pil.split()[3]  # alpha channel = white silhouette mask


def render_symbol_layer(size: tuple[int, int], symbol: str) -> Image.Image:
    """Return an 'L' mask (white symbol on black) at the canvas size."""
    w, h = size
    ss = SUPERSAMPLE
    layer = Image.new("L", (w * ss, h * ss), 0)
    if symbol in SVG_SYMBOLS:
        box = int(min(w, h) * ss * 0.46)
        mask = _render_svg_mask(SVG_SYMBOLS[symbol], box)
        layer.paste(mask, ((w * ss - box) // 2, (h * ss - box) // 2))
    else:
        d = ImageDraw.Draw(layer)
        cx, cy = w * ss / 2, h * ss / 2
        unit = min(w, h) * ss * 0.16  # symbol scale
        SYMBOL_DRAWERS[symbol](d, cx, cy, unit)
    return layer.resize((w, h), Image.LANCZOS)


def apply_symbol(base: Image.Image, symbol: str, opacity: float) -> Image.Image:
    w, h = base.size
    mask = render_symbol_layer((w, h), symbol)

    # soft outer glow: blurred copy of the mask, low intensity
    glow = mask.filter(ImageFilter.GaussianBlur(radius=max(w, h) * 0.012))
    glow = glow.point(lambda v: int(v * opacity * 0.5))

    core = mask.point(lambda v: int(v * opacity))

    white = Image.new("RGB", (w, h), (255, 255, 255))
    out = Image.composite(white, base, glow)   # glow first (under)
    out = Image.composite(white, out, core)     # crisp symbol on top
    return out


# ──────────────────────────────── main ────────────────────────────────
def main() -> None:
    out_dir = ROOT / "assets" / "backgrounds"
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    # Family 1 — plain gradients
    for pal_slug, (c1, c2) in PALETTES.items():
        for ratio_slug, w, h in RATIOS:
            img = add_vignette(make_gradient((w, h), c1, c2))
            dest = out_dir / f"bg-{pal_slug}_{ratio_slug}.png"
            img.save(dest, "PNG", optimize=True)
            count += 1
            print(f"  uni     {dest.name} ({w}x{h})")

    # Family 2 — Christian symbol watermarks
    for model_slug, pal_slug, symbol, opacity in SYMBOL_MODELS:
        c1, c2 = PALETTES[pal_slug]
        for ratio_slug, w, h in RATIOS:
            img = add_vignette(make_gradient((w, h), c1, c2))
            img = apply_symbol(img, symbol, opacity)
            dest = out_dir / f"bg-symbole-{model_slug}_{ratio_slug}.png"
            img.save(dest, "PNG", optimize=True)
            count += 1
            print(f"  symbole {dest.name} ({w}x{h})")

    print(f"\nGenerated {count} backgrounds in {out_dir}")


if __name__ == "__main__":
    main()
