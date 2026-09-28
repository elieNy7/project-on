"""Miniature YouTube (1280×720) aux couleurs de l'église."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw

from app.utils.church_graphics import (
    THUMBNAIL_MAX_BYTES,
    ChurchProfile,
    ThumbnailSpec,
    _highlight_words,
    render_youtube_thumbnail,
    save_thumbnail,
)

RED = (200, 30, 40)


def _cutout(path: Path) -> Path:
    image = Image.new("RGBA", (300, 400), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((100, 20, 200, 120), fill=(*RED, 255))
    draw.rectangle((60, 130, 240, 400), fill=(*RED, 255))
    image.save(path)
    return path


def _profile(tmp_path: Path) -> ChurchProfile:
    return ChurchProfile(name="Église La Grâce", pastor_title="Pasteur", pastor_name="Elie",
                         pastor_photo=str(_cutout(tmp_path / "p.png")),
                         accent_color="#F0BE64")


def test_highlighted_words() -> None:
    assert _highlight_words("Le *vrai* repos") == [("Le", False), ("vrai", True), ("repos", False)]
    assert _highlight_words("*Jésus revient*") == [("Jésus", True), ("revient", True)]


def test_thumbnail_size_speaker_side_and_accent(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    spec = ThumbnailSpec(title="Le *vrai* repos", date="28 septembre")
    image = render_youtube_thumbnail(profile, spec)
    assert image.size == (1280, 720)

    def red_columns(img):
        rgb = img.convert("RGB")
        return [x for x in range(0, 1280, 8)
                if any(rgb.getpixel((x, y)) == RED for y in range(400, 720, 8))]

    right = red_columns(image)
    assert right and min(right) > 640  # orateur à droite
    left = red_columns(render_youtube_thumbnail(profile, ThumbnailSpec(title="Foi",
                                                                        photo_side="left")))
    assert left and max(left) < 640
    # Mot entre astérisques : couleur d'accent présente dans la zone du titre.
    title_zone = image.convert("RGB").crop((40, 180, 700, 560))
    assert (240, 190, 100) in set(title_zone.get_flattened_data() if hasattr(title_zone, "get_flattened_data") else title_zone.getdata())
    # Sans orateur : pas de photo.
    alone = render_youtube_thumbnail(profile, ThumbnailSpec(title="Foi", show_speaker=False))
    assert not red_columns(alone)


def test_background_image_and_save_under_youtube_limit(tmp_path: Path) -> None:
    noise = Image.effect_noise((1600, 900), 120).convert("RGB")  # image difficile à compresser
    noise.save(tmp_path / "fond.png")
    spec = ThumbnailSpec(title="Marcher par la foi", background=str(tmp_path / "fond.png"))
    image = render_youtube_thumbnail(_profile(tmp_path), spec)
    written = save_thumbnail(image, tmp_path / "mini.png")
    assert written.stat().st_size <= THUMBNAIL_MAX_BYTES
    assert Image.open(written).size == (1280, 720)


def test_thumbnail_dialog_and_shortcut(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from app.ui.church_profile_dialog import ThumbnailDialog, french_date
    from app.utils.shortcuts import ShortcutSettings

    assert french_date(date(2026, 9, 27)) == "Dimanche 27 septembre 2026"
    assert ShortcutSettings().key_for("thumbnail") == "Ctrl+Shift+Y"
    dialog = ThumbnailDialog(_profile(tmp_path), title="Le *vrai* repos")
    try:
        spec = dialog.spec()
        assert spec.title == "Le *vrai* repos" and spec.label == "Culte du dimanche"
        dialog.side.setCurrentIndex(1)
        assert dialog.spec().photo_side == "left"
        assert dialog.image().size == (1280, 720)
    finally:
        dialog.close()
