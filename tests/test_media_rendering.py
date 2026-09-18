"""Rendu des médias : contenu entier + fond flou, fonds décoratifs intacts."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from app.ui.slide_canvas import SlideCanvas  # noqa: E402

FIELD = (32, 96, 168)


def _app() -> QApplication:
    """QApplication gardée par l'appelant (variable locale) — convention du dépôt."""
    return QApplication.instance() or QApplication([])


def _photo(tmp_path: Path, name: str, size: tuple[int, int]) -> str:
    """Photo plate : détecter un voile ou un rognage devient trivial."""
    path = tmp_path / f"{name}.png"
    Image.new("RGB", size, FIELD).save(path)
    return str(path)


def _canvas(tmp_path: Path, size: tuple[int, int], config: dict | None = None) -> SlideCanvas:
    canvas = SlideCanvas(presentation_dir=tmp_path)
    canvas.resize(*size)
    canvas._apply_config(
        {
            "layout_mode": "fullscreen",
            "bg_color": "#000000",
            **(config or {}),
        }
    )
    return canvas


def test_media_image_is_shown_whole_never_cropped(tmp_path: Path) -> None:
    """Une image 4:3 sur un écran 16:9 garde ses proportions et ses bords."""
    app = _app()  # noqa: F841
    photo = _photo(tmp_path, "photo", (1600, 1200))
    canvas = _canvas(tmp_path, (1920, 1080))
    pixmap = canvas.render_pixmap(
        {"source": "image", "reference": "Photo", "text": "", "image": photo},
        1920,
        1080,
    )
    image = pixmap.toImage()
    assert canvas._media_content is True
    assert canvas.media_layer_active() is True

    # L'image entière est centrée : 1440×1080 pour une source 1600×1200,
    # donc de x=240 à x=1679 — rien n'est rogné à gauche ni à droite.
    assert image.pixelColor(960, 540).getRgb()[:3] == FIELD
    assert image.pixelColor(250, 540).getRgb()[:3] == FIELD   # dans le cadre
    assert image.pixelColor(1670, 540).getRgb()[:3] == FIELD
    assert image.pixelColor(200, 540).getRgb()[:3] != FIELD   # bande gauche
    assert image.pixelColor(1720, 540).getRgb()[:3] != FIELD  # bande droite


def test_media_backdrop_fills_the_bands_with_blur(tmp_path: Path) -> None:
    """Aucune bande noire : le tour est la même image, floutée et assombrie."""
    app = _app()  # noqa: F841
    photo = _photo(tmp_path, "photo", (1600, 1200))
    canvas = _canvas(tmp_path, (1920, 1080))
    pixmap = canvas.render_pixmap(
        {"source": "image", "text": "", "image": photo}, 1920, 1080
    )
    image = pixmap.toImage()

    band = image.pixelColor(100, 540).getRgb()[:3]
    assert band != (0, 0, 0), "le tour ne doit jamais rester noir"
    # Fond assombri de 45 % : plus sombre que l'image, mais de la même teinte.
    assert band[2] < FIELD[2] and band[2] > FIELD[2] * 0.35
    assert band[0] < band[1] < band[2]

    # Le carré de l'image projetée, lui, n'est jamais assombri.
    assert image.pixelColor(960, 540).getRgb()[:3] == FIELD


def test_media_without_caption_gets_no_readability_veil(tmp_path: Path) -> None:
    """Le voile de lisibilité ne s'applique qu'au texte réellement ajouté."""
    app = _app()  # noqa: F841
    photo = _photo(tmp_path, "photo", (1920, 1080))
    canvas = _canvas(tmp_path, (1920, 1080))
    canvas.render_pixmap({"source": "image", "text": "", "image": photo}, 1920, 1080)
    assert canvas._media_caption is False

    canvas.render_pixmap(
        {"source": "image", "text": "Texte ajouté", "image": photo}, 1920, 1080
    )
    assert canvas._media_caption is True


def test_background_image_keeps_its_historic_rendering(tmp_path: Path) -> None:
    """Un fond décoratif (diapo texte) n'est pas traité comme un média."""
    app = _app()  # noqa: F841
    photo = _photo(tmp_path, "fond", (1600, 1200))
    canvas = _canvas(tmp_path, (1920, 1080), {"background_dimmer": 0.34})
    pixmap = canvas.render_pixmap(
        {"source": "custom", "reference": "Jean 3:16", "text": "Car Dieu…", "background": photo},
        1920,
        1080,
    )
    image = pixmap.toImage()
    assert canvas._media_content is False
    assert canvas.media_layer_active() is False
    # Cadrage « cover » (réglage historique) : l'image remplit tout l'écran.
    assert image.pixelColor(5, 540).getRgb()[:3] != (0, 0, 0)


def test_media_fit_and_backdrop_settings_change_rendering(tmp_path: Path) -> None:
    """Les réglages média sont relus à chaud (cache invalidé)."""
    app = _app()  # noqa: F841
    photo = _photo(tmp_path, "photo", (1600, 1200))
    canvas = _canvas(tmp_path, (1920, 1080))
    slide = {"source": "image", "text": "", "image": photo}

    contain = canvas.render_pixmap(slide, 1920, 1080).toImage()
    assert contain.pixelColor(100, 540).getRgb()[:3] != FIELD  # bande à gauche

    canvas._apply_config({"layout_mode": "fullscreen", "bg_color": "#000000", "media_fit": "cover"})
    cover = canvas.render_pixmap(slide, 1920, 1080).toImage()
    assert cover.pixelColor(100, 540).getRgb()[:3] == FIELD  # l'image remplit

    canvas._apply_config(
        {"layout_mode": "fullscreen", "bg_color": "#000000", "media_backdrop": "black"}
    )
    black = canvas.render_pixmap(slide, 1920, 1080).toImage()
    assert black.pixelColor(100, 540).getRgb()[:3] == (0, 0, 0)


def test_missing_media_file_falls_back_silently(tmp_path: Path) -> None:
    """Un fichier disparu ne casse jamais la projection."""
    app = _app()  # noqa: F841
    canvas = _canvas(tmp_path, (1920, 1080), {"bg_color": "#123456"})
    pixmap = canvas.render_pixmap(
        {"source": "image", "text": "", "image": str(tmp_path / "absent.png")},
        1920,
        1080,
    )
    assert canvas.media_layer_active() is False
    assert pixmap.toImage().pixelColor(960, 540).getRgb()[:3] == (0x12, 0x34, 0x56)


def test_hidden_slide_never_renders_media(tmp_path: Path) -> None:
    """« Masquer les écritures » vaut aussi pour un média."""
    app = _app()  # noqa: F841
    photo = _photo(tmp_path, "photo", (1600, 1200))
    canvas = _canvas(tmp_path, (1920, 1080), {"bg_color": "#101010"})
    canvas.render_pixmap(
        {"source": "image", "text": "", "image": photo, "hidden": True}, 1920, 1080
    )
    assert canvas._media_content is False
    assert canvas.media_layer_active() is False


def test_media_frame_composition_is_opaque_for_transitions(tmp_path: Path) -> None:
    """Le média participe aux transitions : trame opaque plein cadre."""
    app = _app()  # noqa: F841
    from PyQt6.QtCore import QSize

    photo = _photo(tmp_path, "photo", (1600, 1200))
    canvas = _canvas(tmp_path, (1920, 1080))
    assert canvas.compose_media_frame(QSize(1920, 1080)) is None  # aucun média

    canvas.render_pixmap({"source": "image", "text": "", "image": photo}, 1920, 1080)
    frame = canvas.compose_media_frame(QSize(1920, 1080))
    assert frame is not None
    assert frame.width() == 1920 and frame.height() == 1080
    image = frame.toImage()
    assert image.pixelColor(100, 540).alpha() == 255
    assert image.pixelColor(960, 540).getRgb()[:3] == FIELD
