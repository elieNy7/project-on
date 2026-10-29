"""Redimensionnement Lanczos des visuels, natif quand c'est possible.

Le module Rust (rust/project_on_core) redimensionne sur tous les cœurs et
relâche le GIL : environ deux fois plus vite que Pillow sur les grandes
photos. Sans lui, ou pour un mode d'image qu'il ne connaît pas, Pillow
prend le relais avec le même filtre.
"""

from __future__ import annotations

from PIL import Image

try:
    from project_on_core import resize_lanczos as _native_resize
except ImportError:  # poste de dev non compilé
    _native_resize = None

# Mode Pillow → (canaux, transparence à prémultiplier).
_CHANNELS = {"L": (1, False), "RGB": (3, False), "RGBA": (4, True)}


def resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Équivalent de ``image.resize(size, Image.LANCZOS)``."""
    size = (max(1, int(size[0])), max(1, int(size[1])))
    layout = _CHANNELS.get(image.mode)
    if _native_resize is None or layout is None or size == image.size:
        return image.resize(size, Image.LANCZOS)
    channels, alpha = layout
    data = _native_resize(
        image.tobytes(), image.width, image.height, channels, alpha, size[0], size[1]
    )
    return Image.frombytes(image.mode, size, data)



def contain(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Équivalent de ``ImageOps.contain(image, size, Image.LANCZOS)``."""
    ratio, target = image.width / image.height, size[0] / size[1]
    if ratio > target:
        size = (size[0], round(image.height / image.width * size[0]))
    elif ratio < target:
        size = (round(image.width / image.height * size[1]), size[1])
    return resize(image, size)


def fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Équivalent de ``ImageOps.fit(image, size, Image.LANCZOS)`` (recadrage
    centré au pixel près, puis redimensionnement)."""
    ratio, target = image.width / image.height, size[0] / size[1]
    crop_w, crop_h = float(image.width), float(image.height)
    if ratio > target:
        crop_w = target * image.height
    elif ratio < target:
        crop_h = image.width / target
    left = round((image.width - crop_w) / 2)
    top = round((image.height - crop_h) / 2)
    box = (left, top, left + max(1, round(crop_w)), top + max(1, round(crop_h)))
    if box != (0, 0, image.width, image.height):
        image = image.crop(box)
    return resize(image, size)
