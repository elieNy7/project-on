"""Le style par défaut des sorties (OBS, NDI, HDMI) : un bandeau sobre, comme Pgraphics.

Petit, lisible sur n'importe quelle vidéo, dans la zone de sécurité EBU R 95
(5 % de chaque bord), sans contour, sans majuscules forcées, sans voile sur
toute l'image.
"""

from __future__ import annotations

import re

import pytest

from app.utils.obs_overlay_render import render_obs_overlay
from app.utils.settings import HdmiStyle, ObsOutputSettings

VERSET = {
    "text": "Car Dieu a tant aimé le monde qu'il a donné son Fils unique, afin que quiconque croit en lui ne périsse point",
    "reference": "Jean 3:16",
    "source": "bible",
}
CANTIQUE = {"text": "Grand est ton amour, Seigneur\nTa fidélité demeure à jamais", "source": "hymn"}


def _panel_box(image):
    """La boîte du bandeau (fond couvrant et texte), sans son ombre portée."""
    return image.getchannel("A").point(lambda alpha: 255 if alpha > 200 else 0).getbbox()


def _style_configs():
    obs = ObsOutputSettings().to_obs_config()
    hdmi = {**obs, **HdmiStyle().to_overrides()}
    return {"obs_ndi": obs, "hdmi": hdmi}


@pytest.mark.parametrize("output", ["obs_ndi", "hdmi"])
@pytest.mark.parametrize("slide", [VERSET, CANTIQUE], ids=["verset", "cantique"])
def test_le_bandeau_est_petit_et_dans_la_zone_de_securite(output, slide):
    image = render_obs_overlay(_style_configs()[output], slide, 1920, 1080)
    box = _panel_box(image)
    assert box is not None, "rien n'est dessiné"
    left, top, right, bottom = box
    assert left >= 96 - 2 and right <= 1824 + 2, box
    assert top >= 54 - 2 and bottom <= 1026 + 2, box
    assert bottom - top < 1080 / 3, f"un bandeau bas, pas un pavé : {box}"


def test_le_style_par_defaut_est_sobre():
    style = ObsOutputSettings()
    assert not style.text_stroke and style.text_transform == "none" and style.letter_spacing == 0
    assert style.background_dimmer == 0.0  # la vidéo n'est jamais voilée
    assert style.max_lines <= 3 and style.text_size <= 44
    assert style.safe_area_percent == 5
    assert style.font_family == HdmiStyle().font_family  # une seule famille sur les sorties


def _luminance(rgb) -> float:
    def channel(value: float) -> float:
        value /= 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = rgb
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


@pytest.mark.parametrize("bg_color", [ObsOutputSettings().bg_color, HdmiStyle().bg_color])
def test_le_texte_reste_lisible_sur_une_video_blanche(bg_color):
    """Le fond translucide posé sur la pire image (blanche) garde 4,5:1 (WCAG)."""
    red, green, blue, alpha = (float(part) for part in re.findall(r"[\d.]+", bg_color))
    below = tuple(alpha * value + (1 - alpha) * 255 for value in (red, green, blue))
    light, dark = sorted((_luminance((255, 255, 255)), _luminance(below)), reverse=True)
    assert (light + 0.05) / (dark + 0.05) >= 4.5
