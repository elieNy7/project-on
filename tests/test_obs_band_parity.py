"""Bandeau HDMI/NDI : le rendu doit lire TOUS les réglages de la page OBS.

Chaque test verrouille un paramètre d'``obs-style.css`` (largeur du bandeau,
marges, kicker, contour, interlettre, styles de référence, angle du dégradé,
image de fond du bandeau, opacité). Les mesures se font sur la boîte réelle
du panneau, jamais sur des coordonnées supposées.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy  # noqa: E402
from PIL import Image  # noqa: E402

from app.utils.obs_overlay_render import (  # noqa: E402
    CHROMA_KEY_GREEN,
    render_obs_overlay,
    render_obs_overlay_on_color,
)

SLIDE = {"text": "Car Dieu a tant aimé le monde", "reference": "Jean 3:16", "source": "bible"}
_KEY = numpy.array(CHROMA_KEY_GREEN, dtype=numpy.int32)


def _rgb(cfg: dict | None, slide: dict | None = SLIDE, **kwargs):
    img = render_obs_overlay_on_color(
        cfg or {}, slide, (*CHROMA_KEY_GREEN, 255), 1920, 1080, **kwargs
    )
    return numpy.asarray(img.convert("RGB")).astype(numpy.int32)


def _panel_box(arr) -> tuple[int, int, int, int]:
    """Boîte englobante du panneau (tout pixel différent de la couleur de clé)."""
    dist = numpy.sqrt(((arr - _KEY) ** 2).sum(axis=2))
    rows = numpy.where((dist > 30).any(axis=1))[0]
    columns = numpy.where((dist > 30).any(axis=0))[0]
    assert rows.size and columns.size, "aucun panneau dessiné"
    return int(rows.min()), int(rows.max()), int(columns.min()), int(columns.max())


def _text_bounds(arr, mask) -> tuple[int, int, int, int]:
    """Boîte des pixels du masque (texte, contour…)."""
    rows = numpy.where(mask.any(axis=1))[0]
    columns = numpy.where(mask.any(axis=0))[0]
    assert rows.size and columns.size, "aucun pixel pour ce masque"
    return int(rows.min()), int(rows.max()), int(columns.min()), int(columns.max())


def _light_mask(arr):
    """Pixels clairs : le texte projeté (blanc sur panneau sombre)."""
    return (arr[:, :, 0] > 190) & (arr[:, :, 1] > 190) & (arr[:, :, 2] > 190)


BASE = {
    "edge_margin": 0,
    "safe_area_percent": 0,
    "show_kicker": False,
    "show_reference": False,
    "bg_color": "rgba(8, 13, 23, 1)",
    "bg_opacity": 1.0,
}


def test_band_follows_obs_max_width() -> None:
    """`max_width` fixe la largeur du bandeau, comme `.lower-third`."""
    narrow = _rgb({**BASE, "max_width": 50})
    wide = _rgb({**BASE, "max_width": 90})

    _, _, left_narrow, right_narrow = _panel_box(narrow)
    _, _, left_wide, right_wide = _panel_box(wide)

    assert 958 <= right_narrow - left_narrow + 1 <= 962, (left_narrow, right_narrow)
    assert 1726 <= right_wide - left_wide + 1 <= 1730, (left_wide, right_wide)
    # Les deux bandeaux sont centrés.
    assert abs((left_narrow + right_narrow) / 2 - 960) <= 2
    assert abs((left_wide + right_wide) / 2 - 960) <= 2


def test_band_padding_moves_the_text_away_from_the_edge() -> None:
    """`padding_horizontal` écarte le texte des bords du panneau."""
    def text_left(padding: int) -> int:
        arr = _rgb(
            {
                **BASE,
                "align": "left",
                "band_align": "left",
                "max_width": 100,
                "padding_horizontal": padding,
                "text_size": 44,
            }
        )
        top, bottom, left, _right = _panel_box(arr)
        mask = _light_mask(arr)
        text_top, text_bottom, text_left, _ = _text_bounds(arr, mask)
        return text_left - left

    # Le tracé du glyphe démarre au bord de la boîte du texte (± 3 px de
    # roulement typographique selon la police).
    assert abs(text_left(48) - 48) <= 3, text_left(48)
    assert abs(text_left(140) - 140) <= 3, text_left(140)


def test_kicker_is_drawn_and_can_be_hidden() -> None:
    """`show_kicker` : la pastille de source allonge le bandeau vers le haut."""
    with_kicker = _rgb({"edge_margin": 0, "safe_area_percent": 0, "show_kicker": True})
    without = _rgb({"edge_margin": 0, "safe_area_percent": 0, "show_kicker": False})
    top_with, bottom_with, _, _ = _panel_box(with_kicker)
    top_without, bottom_without, _, _ = _panel_box(without)
    # Pastille (36 px) + gouttière (12 px) au-dessus du texte.
    assert 44 <= (top_without - top_with) <= 52, (top_with, top_without)
    assert abs(bottom_with - bottom_without) <= 2


def test_text_stroke_and_letter_spacing_are_rendered() -> None:
    """Contour de texte et interlettre : réglages typographiques d'OBS."""
    common = {**BASE, "text_transform": "uppercase", "text_size": 60, "max_width": 100}
    plain = _rgb(common)
    stroked = _rgb(
        {
            **common,
            "text_stroke": True,
            "stroke_color": "rgba(255, 0, 0, 1)",
            "stroke_width": 6,
        }
    )
    red = numpy.abs(stroked - numpy.array([255, 0, 0], numpy.int32)).sum(axis=2) < 90
    assert int(red.sum()) > 200, "contour de texte absent"

    spaced = _rgb({**common, "letter_spacing": 12})

    def text_width(arr) -> int:
        mask = _light_mask(arr)
        _top, _bottom, left, right = _text_bounds(arr, mask)
        return right - left

    assert text_width(spaced) > text_width(plain) + 60


def test_reference_styles_follow_obs() -> None:
    """`reference_style` : badge (pastille) plus haut que le texte nu."""
    def ref_height(style: str) -> tuple[int, int]:
        arr = _rgb(
            {
                "edge_margin": 0,
                "safe_area_percent": 0,
                "show_kicker": False,
                "max_width": 60,
                "reference_style": style,
            }
        )
        return _panel_box(arr)[:2]

    badge_top, badge_bottom = ref_height("badge")
    plain_top, plain_bottom = ref_height("plain")
    # La pastille (padding 7 px + rayon) dépasse la hauteur du texte nu.
    assert (badge_bottom - badge_top) > (plain_bottom - plain_top)
    assert badge_bottom == plain_bottom  # même bord bas


def test_gradient_angle_is_applied() -> None:
    """`bg_gradient_angle` oriente le dégradé du panneau (pas un axe fixe)."""
    cfg = {
        "bg_gradient_enabled": True,
        "bg_color": "rgba(255, 0, 0, 1)",
        "bg_color_2": "rgba(0, 0, 255, 1)",
        "bg_opacity": 1.0,
        "bg_blur": False,
        "show_kicker": False,
        "show_reference": False,
        "edge_margin": 0,
        "safe_area_percent": 0,
        "max_width": 60,
    }

    def sample(angle: int):
        arr = _rgb({**cfg, "bg_gradient_angle": angle})
        top, bottom, left, right = _panel_box(arr)
        inset = 24
        return (
            arr[top + inset, left + inset],      # coin haut-gauche
            arr[top + inset, right - inset],     # coin haut-droit
            arr[bottom - inset, left + inset],   # coin bas-gauche
        )

    for right_to_left in (sample(90),):
        top_left, top_right, _bottom_left = right_to_left
        # 90° → vers la droite : rouge à gauche, bleu à droite.
        assert top_left[0] > top_left[2], top_left.tolist()
        assert top_right[2] > top_right[0], top_right.tolist()

    top_to_bottom = sample(180)
    top_left, top_right, bottom_left = top_to_bottom
    # 180° → vers le bas : rouge en haut, bleu en bas.
    assert top_left[0] > top_left[2]
    assert top_right[0] > top_right[2]
    assert bottom_left[2] > bottom_left[0]


def test_band_background_image_is_used(tmp_path: Path) -> None:
    """`bg_mode: image` pose l'image DANS le bandeau, comme la page OBS."""
    image_path = tmp_path / "band.png"
    Image.new("RGB", (400, 200), (0, 200, 0)).save(image_path)
    arr = _rgb(
        {
            "bg_mode": "image",
            "bg_image": str(image_path),
            "bg_image_fit": "cover",
            "background_dimmer": 0.0,
            "show_kicker": False,
            "show_reference": False,
            "edge_margin": 0,
            "safe_area_percent": 0,
            "max_width": 60,
        }
    )
    top, _bottom, left, right = _panel_box(arr)
    # Coin haut-gauche du panneau : la teinte verte de l'image de fond.
    sample = arr[top + 12, left + 12]
    assert sample[1] > sample[0] and sample[1] > sample[2], sample.tolist()


def test_opacity_is_applied_outside_chroma() -> None:
    """`opacity` globale : la trame NDI est bien atténuée."""
    slide = {"text": "Car Dieu a tant aimé le monde", "source": "bible"}
    opaque = render_obs_overlay({"opacity": 1.0}, slide, 1920, 1080)
    faded = render_obs_overlay({"opacity": 0.4}, slide, 1920, 1080)
    assert int(numpy.asarray(opaque)[:, :, 3].max()) == 255
    assert int(numpy.asarray(faded)[:, :, 3].max()) == int(255 * 0.4)


def test_every_obs_parameter_is_read() -> None:
    """Aucun réglage de style OBS n'est ignoré lors de la lecture."""
    from app.utils.obs_overlay_render import OverlayStyleConfig
    from app.utils.settings import ObsOutputSettings

    payload = ObsOutputSettings(
        font_family="Poppins",
        text_size=58,
        ref_size=26,
        line_height=1.4,
        letter_spacing=4,
        font_weight="bold",
        text_transform="uppercase",
        text_stroke=True,
        stroke_color="rgba(255, 0, 0, 1)",
        stroke_width=4,
        text_shadow=True,
        shadow_color="rgba(0, 0, 0, 0.8)",
        shadow_blur=12,
        show_kicker=True,
        reference_style="badge",
        show_accent_bar=True,
        bg_gradient_enabled=True,
        bg_gradient_angle=120,
        bg_color="rgba(10, 20, 40, 0.9)",
        bg_color_2="rgba(40, 20, 10, 0.9)",
        bg_opacity=0.8,
        max_width=70,
        padding_horizontal=70,
        padding_vertical=40,
        border_radius=28,
        edge_margin=30,
        safe_area_percent=4,
        offset_x=12,
        offset_y=-8,
        align="center",
        band_align="center",
        position="bottom",
    ).to_obs_config()

    cfg = OverlayStyleConfig.from_payload(payload)
    for champ, attendu in (
        ("font_family", "Poppins"),
        ("text_size", 58),
        ("ref_size", 26),
        ("line_height", 1.4),
        ("letter_spacing", 4),
        ("font_weight", "bold"),
        ("text_transform", "uppercase"),
        ("text_stroke", True),
        ("stroke_width", 4),
        ("shadow_blur", 12),
        ("show_kicker", True),
        ("reference_style", "badge"),
        ("show_accent_bar", True),
        ("bg_gradient_enabled", True),
        ("bg_gradient_angle", 120),
        ("bg_opacity", 0.8),
        ("max_width", 70),
        ("padding_horizontal", 70),
        ("padding_vertical", 40),
        ("border_radius", 28),
        ("edge_margin", 30),
        ("safe_area_percent", 4),
        ("offset_x", 12),
        ("offset_y", -8),
    ):
        assert getattr(cfg, champ) == attendu, champ


def test_subtitle_mode_follows_the_page() -> None:
    """Mode sous-titre : bandeau plus plat, sans pastille de source."""
    base = {
        **BASE,
        "max_width": 100,
        "padding_vertical": 60,
        "border_radius": 40,
        "show_kicker": True,
    }
    lower = _rgb({**base, "layout_mode": "lower_third"})
    subtitle = _rgb({**base, "layout_mode": "subtitle"})

    top_lower, bottom_lower, _left, _right = _panel_box(lower)
    top_sub, bottom_sub, _left2, _right2 = _panel_box(subtitle)
    # Padding réduit (0,65×) et pastille masquée : bandeau plus court.
    assert (bottom_sub - top_sub) < (bottom_lower - top_lower)

    # La pastille de source n'apparaît qu'en bandeau classique.
    light_sub = _light_mask(subtitle).sum()
    light_lower = _light_mask(lower).sum()
    assert light_sub < light_lower


def test_side_panel_mode_follows_the_page() -> None:
    """Mode panneau latéral : colonne pleine hauteur, collée au bord choisi."""
    cfg = {
        **BASE,
        "layout_mode": "side_panel",
        "max_width": 45,
        "panel_side": "left",
    }
    arr = _rgb(cfg)
    top, bottom, left, right = _panel_box(arr)
    assert left <= 2, left  # collé au bord gauche (marge de bord nulle)
    assert (right - left + 1) <= 900, (left, right)
    assert (bottom - top + 1) >= 1000, (top, bottom)  # pleine hauteur

    right_side = _rgb({**cfg, "panel_side": "right"})
    _top, _bottom, left_r, right_r = _panel_box(right_side)
    assert right_r >= 1917, right_r


def test_focus_card_mode_follows_the_page() -> None:
    """Carte focus : largeur plafonnée à 1180 px et hauteur minimale marquée."""
    arr = _rgb(
        {
            "edge_margin": 0,
            "safe_area_percent": 0,
            "layout_mode": "focus_card",
            "max_width": 100,
            "show_kicker": False,
            "show_reference": False,
            "bg_color": "rgba(8, 13, 23, 1)",
            "bg_opacity": 1.0,
        }
    )
    top, bottom, left, right = _panel_box(arr)
    assert (right - left + 1) <= 1180, (left, right)
    assert (bottom - top + 1) >= 560, (top, bottom)


def test_long_text_never_overflows_the_panel() -> None:
    """Le texte se replie à la largeur réelle : jamais rogné par le panneau.

    Le retour à la ligne doit tenir compte de l'interlettre (le mesurer sans
    elle faisait déborder les lignes, donc couper les mots sur HDMI/NDI).
    """
    arr = _rgb(
        {
            "edge_margin": 40,
            "safe_area_percent": 4,
            "max_width": 100,
            "padding_horizontal": 100,
            "letter_spacing": 3,
            "text_size": 40,
            "text_transform": "uppercase",
            "show_kicker": False,
            "show_reference": False,
            "bg_color": "rgba(8, 13, 23, 1)",
            "bg_opacity": 1.0,
        },
        slide={
            "text": (
                "Et Dieu les bénit; et Dieu leur dit: Fructifiez, et multipliez, "
                "et remplissez la terre et l assujettissez; et dominez sur les "
                "poissons de la mer, et sur les oiseaux des cieux, et sur tout "
                "être vivant qui se meut sur la terre."
            ),
            "reference": "Genèse 1:28",
            "source": "bible",
        },
    )
    top, bottom, left, right = _panel_box(arr)
    mask = _light_mask(arr)
    text_top, text_bottom, text_left, text_right = _text_bounds(arr, mask)
    # Le texte reste dans la marge interne du panneau (padding 100 px).
    assert text_left >= left + 95, (text_left - left)
    assert text_right <= right - 95, (right - text_right)
    assert text_top >= top and text_bottom <= bottom

    # Le texte occupe plusieurs lignes, équilibrées (text-wrap: balance) :
    # aucune ligne n'est démesurément courte par rapport à la plus longue.
    widths = _line_widths(mask)
    assert len(widths) >= 3, widths
    assert min(widths) >= max(widths) * 0.55, widths


def _line_widths(mask) -> list:
    """Largeur de chaque ligne de texte rendue (bandes de plus de 20 px)."""
    filled_rows = [index for index, filled in enumerate(mask.any(axis=1)) if filled]
    if not filled_rows:
        return []
    bands = []
    start = previous = filled_rows[0]
    for index in filled_rows[1:]:
        if index - previous > 8:  # un trou d'accent ne coupe pas la ligne
            bands.append((start, previous + 1))
            start = index
        previous = index
    bands.append((start, previous + 1))
    widths = []
    for top, bottom in bands:
        if bottom - top <= 20:
            continue
        columns = numpy.where(mask[top:bottom].any(axis=0))[0]
        if columns.size:
            widths.append(int(columns.max() - columns.min() + 1))
    return widths
