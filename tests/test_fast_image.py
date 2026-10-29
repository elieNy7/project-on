"""Redimensionnement natif des visuels et caches des aperçus."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from app.utils import church_graphics as cg
from app.utils import fast_image


def _photo(size=(640, 480)) -> Image.Image:
    """Dégradé + formes : contours nets comme une vraie photo."""
    image = Image.linear_gradient("L").resize(size).convert("RGB")
    image.paste((200, 40, 60), (size[0] // 4, size[1] // 4, size[0] // 2, size[1] // 2))
    return image


def _max_diff(a: Image.Image, b: Image.Image) -> int:
    extrema = ImageChops.difference(a, b).getextrema()
    if isinstance(extrema[0], int):  # une seule bande (mode L)
        extrema = (extrema,)
    return max(high for _low, high in extrema)


native = pytest.mark.skipif(
    fast_image._native_resize is None, reason="module natif non compilé sur ce poste"
)


@native
@pytest.mark.parametrize("mode", ["RGB", "L"])
@pytest.mark.parametrize("size", [(160, 120), (97, 300), (1280, 960)])
def test_native_resize_matches_pillow_closely(mode, size):
    image = _photo().convert(mode)
    ours = fast_image.resize(image, size)
    assert ours.mode == mode and ours.size == size
    assert _max_diff(ours, image.resize(size, Image.LANCZOS)) <= 16


@native
def test_native_resize_premultiplies_alpha_like_pillow():
    image = _photo().convert("RGBA")
    alpha = Image.new("L", image.size, 0)
    alpha.paste(255, (100, 100, 400, 380))  # sujet détouré sur fond transparent
    image.putalpha(alpha)
    ours = fast_image.resize(image, (200, 150)).convert("RGBa")
    theirs = image.resize((200, 150), Image.LANCZOS).convert("RGBa")
    assert _max_diff(ours, theirs) <= 16


def test_fallback_and_unknown_modes_use_pillow(monkeypatch):
    image = _photo((64, 48))
    monkeypatch.setattr(fast_image, "_native_resize", None)
    assert fast_image.resize(image, (20, 15)).tobytes() == image.resize(
        (20, 15), Image.LANCZOS).tobytes()
    monkeypatch.undo()
    palette = image.convert("P")
    assert fast_image.resize(palette, (20, 15)).mode == "P"
    assert fast_image.resize(image, image.size).size == image.size


def _profile(tmp_path: Path) -> cg.ChurchProfile:
    photo = tmp_path / "eglise.jpg"
    _photo((900, 600)).save(photo)
    return cg.ChurchProfile(name="Église", photos=[str(photo)], accent_color="#F0BE64")


def test_thumbnail_background_is_reused_while_typing_the_title(tmp_path, monkeypatch):
    profile = _profile(tmp_path)
    calls = []
    draw = cg._draw_thumbnail_background
    monkeypatch.setattr(cg, "_draw_thumbnail_background",
                        lambda *a: calls.append(1) or draw(*a))
    cg._BACKGROUND_CACHE.clear()
    spec = cg.ThumbnailSpec(title="Le repos", composition="single")
    first = cg.render_youtube_thumbnail(profile, spec)
    second = cg.render_youtube_thumbnail(profile, replace(spec, title="Le vrai repos"))
    assert len(calls) == 1  # le fond n'est dessiné qu'une fois
    assert first.tobytes() != second.tobytes()  # le titre, lui, change
    cg.render_youtube_thumbnail(profile, replace(spec, tint_strength=80))
    assert len(calls) == 2  # un réglage d'image redessine le fond


def test_replaced_photo_invalidates_caches(tmp_path):
    profile = _profile(tmp_path)
    cg._BACKGROUND_CACHE.clear()
    spec = cg.ThumbnailSpec(title="Foi", composition="single", tint_strength=0)
    before = cg.render_youtube_thumbnail(profile, spec)
    photo = Path(profile.photos[0])
    Image.new("RGB", (900, 600), (10, 200, 10)).save(photo)
    stat = photo.stat()
    os.utime(photo, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    after = cg.render_youtube_thumbnail(profile, spec)
    assert before.tobytes() != after.tobytes()


def test_cached_images_are_copies(tmp_path):
    profile = _profile(tmp_path)
    path = profile.photos[0]
    first = cg._resized_source(path, "RGB", (300, 200))
    first.paste((0, 0, 0), (0, 0, 300, 200))  # un rendu dessine dessus
    again = cg._resized_source(path, "RGB", (300, 200))
    assert again.getpixel((150, 100)) != (0, 0, 0)
