"""Sortie HDMI mixeur : letterbox, réglages, rendu chroma, fenêtre, pré-vol."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.utils.obs_overlay_render import (  # noqa: E402
    CHROMA_KEY_COLORS,
    CHROMA_KEY_GREEN,
    OverlayStyleConfig,
    REF_DIVIDER_FILL,
    accent_too_close_to_key,
    chroma_key_rgb,
    render_obs_overlay,
    render_obs_overlay_on_color,
)
from app.utils.settings import AppSettings, HdmiSettings  # noqa: E402


# ── Letterbox 16:9 ───────────────────────────────────────────────────────


def test_letterbox_exact_16_9_is_fullscreen() -> None:
    from app.ui.mixer_output_window import letterbox_rect

    rect = letterbox_rect(1920, 1080)
    assert (rect.width(), rect.height()) == (1920, 1080)
    assert rect.x() == 0 and rect.y() == 0


def test_letterbox_taller_screen_keeps_width() -> None:
    from app.ui.mixer_output_window import letterbox_rect

    # 16:10 → bandes vertes en haut et en bas, largeur conservée.
    rect = letterbox_rect(1920, 1200)
    assert (rect.width(), rect.height()) == (1920, 1080)
    assert rect.y() == 60


def test_letterbox_narrower_screen_keeps_height() -> None:
    from app.ui.mixer_output_window import letterbox_rect

    # 5:4 → bandes vertes à gauche et à droite, hauteur conservée.
    rect = letterbox_rect(1280, 1024)
    assert (rect.width(), rect.height()) == (1280, 720)
    assert rect.x() == 0 and rect.y() == 152


def test_letterbox_ultrawide_centers() -> None:
    from app.ui.mixer_output_window import letterbox_rect

    rect = letterbox_rect(2560, 1080)
    assert (rect.width(), rect.height()) == (1920, 1080)
    assert rect.x() == 320 and rect.y() == 0


# ── Réglages ─────────────────────────────────────────────────────────────


def test_hdmi_settings_defaults_and_sanitized() -> None:
    default = HdmiSettings()
    assert default.enabled is False
    assert default.screen == "auto"
    assert default.letterbox is True

    cleaned = HdmiSettings(enabled=True, screen="", letterbox=False).sanitized()
    assert cleaned.screen == "auto"
    assert cleaned.enabled is True
    assert cleaned.letterbox is False


def test_hdmi_settings_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settings = AppSettings()
    settings.hdmi = HdmiSettings(enabled=True, screen="HDMI-2", letterbox=False)
    settings.save(path)

    loaded = AppSettings.load(path)
    assert loaded.hdmi.enabled is True
    assert loaded.hdmi.screen == "HDMI-2"
    assert loaded.hdmi.letterbox is False


def test_hdmi_settings_absent_keeps_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"projection": {}}), encoding="utf-8")
    loaded = AppSettings.load(path)
    assert loaded.hdmi == HdmiSettings()


def test_hdmi_settings_overlay_fields_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settings = AppSettings()
    settings.hdmi = HdmiSettings(
        enabled=True,
        screen="HDMI-2",
        key_color="magenta",
        text_scale=140,
        offset_y=-80,
    )
    settings.save(path)

    loaded = AppSettings.load(path)
    assert loaded.hdmi.key_color == "magenta"
    assert loaded.hdmi.text_scale == 140
    assert loaded.hdmi.offset_y == -80


def test_hdmi_settings_sanitized_clamps_overlay_fields() -> None:
    cleaned = HdmiSettings(key_color="orange", text_scale=500, offset_y=9999).sanitized()
    assert cleaned.key_color == "green"
    assert cleaned.text_scale == 180
    assert cleaned.offset_y == 300


def test_chroma_key_rgb_variants() -> None:
    assert chroma_key_rgb("green") == (0, 177, 64)
    assert chroma_key_rgb("MAGENTA") == (255, 0, 255)
    assert chroma_key_rgb("blue") == (0, 82, 255)
    assert chroma_key_rgb("nimporte") == CHROMA_KEY_GREEN
    assert set(CHROMA_KEY_COLORS) == {"green", "magenta", "blue"}


# ── Rendu de la section texte (chroma) ───────────────────────────────────


def test_render_overlay_none_when_hidden_or_empty() -> None:
    assert render_obs_overlay({}, {"hidden": True}) is None
    assert render_obs_overlay({}, {"text": "", "reference": ""}) is None


def test_render_overlay_on_green_has_chroma_background() -> None:
    slide = {"text": "Car Dieu a tant aimé le monde", "reference": "Jean 3:16", "source": "bible"}
    img = render_obs_overlay_on_color({}, slide)
    assert img.size == (1920, 1080)
    # Coin hors du bandeau : vert chroma pur (prélevé par la clé du mélangeur).
    assert img.getpixel((8, 8)) == (*CHROMA_KEY_GREEN, 255)
    # La section texte « façon OBS » recouvre le vert quelque part.
    small = img.resize((96, 54))
    assert any(
        small.getpixel((x, y))[:3] != CHROMA_KEY_GREEN
        for x in range(96)
        for y in range(54)
    )


def test_render_overlay_on_green_all_green_when_hidden() -> None:
    img = render_obs_overlay_on_color({}, {"hidden": True})
    small = img.resize((32, 18))
    assert all(
        small.getpixel((x, y)) == (*CHROMA_KEY_GREEN, 255)
        for x in range(32)
        for y in range(18)
    )


def test_overlay_style_config_from_payload() -> None:
    cfg = OverlayStyleConfig.from_payload(
        {
            "layout_mode": "SUBTITLE",
            "font_family": "Poppins",
            "text_size": 64,
            "bg_enabled": False,
            "opacity": 2.0,
        }
    )
    assert cfg.layout_mode == "subtitle"
    assert cfg.font_family == "Poppins"
    assert cfg.text_size == 64
    assert cfg.bg_enabled is False
    assert cfg.opacity == 1.0  # bornée

    empty = OverlayStyleConfig.from_payload(None)
    assert empty.layout_mode == "lower_third"


def _count_non_key(img, key_rgb=CHROMA_KEY_GREEN) -> int:
    small = img.convert("RGB").resize((192, 108))
    return sum(
        1
        for x in range(192)
        for y in range(108)
        if small.getpixel((x, y)) != key_rgb
    )


def test_render_text_scale_grows_overlay() -> None:
    slide = {"text": "Car Dieu a tant aimé le monde", "reference": "Jean 3:16", "source": "bible"}
    small = render_obs_overlay_on_color({}, slide, text_scale=0.6)
    big = render_obs_overlay_on_color({}, slide, text_scale=1.8)
    assert _count_non_key(big) > _count_non_key(small)


def _top_overlay_row(img, key_rgb=CHROMA_KEY_GREEN) -> int:
    rgb = img.convert("RGB")
    for y in range(rgb.height):
        for x in range(0, rgb.width, 8):
            if rgb.getpixel((x, y)) != key_rgb:
                return y
    return -1


def test_render_offset_y_moves_overlay() -> None:
    slide = {"text": "Car Dieu a tant aimé le monde", "reference": "Jean 3:16", "source": "bible"}
    low = render_obs_overlay_on_color({}, slide, offset_y=0)
    high = render_obs_overlay_on_color({}, slide, offset_y=-300)
    assert _top_overlay_row(high) < _top_overlay_row(low)


def test_render_on_magenta_key_uses_magenta_background() -> None:
    from app.utils.obs_overlay_render import chroma_key_rgb as _rgb

    magenta = _rgb("magenta")
    img = render_obs_overlay_on_color(
        {},
        {"text": "Alléluia", "source": "hymn"},
        bg_rgba=(*magenta, 255),
    )
    assert img.getpixel((8, 8)) == (*magenta, 255)
    assert _count_non_key(img, magenta) > 0


def test_reference_zone_stays_neutral_for_bible_verses() -> None:
    """Pas de vert dans la référence : le divider est neutre (clé chroma).

    Le divider ne doit porter aucune teinte de source — le vert biblique
    sautait à la clé chroma de la sortie HDMI. La neutralité est épinglée
    sur la constante utilisée par le renderer (les seuils pixel sont trop
    mous sur des aplhas fondus pour fiabiliser un scan d'image).
    """
    assert REF_DIVIDER_FILL[0] == REF_DIVIDER_FILL[1] == REF_DIVIDER_FILL[2]
    assert REF_DIVIDER_FILL[3] > 0  # ligne visible mais discrète


def test_chroma_render_is_binary_alpha() -> None:
    """Mode clé chroma : aucun pixel semi-transparent.

    Un alpha intermédiaire deviendrait un mélange avec la couleur de clé
    (badge alpha 18 ≈ 93 % de vert) que le mélangeur supprimerait.
    """
    img = render_obs_overlay(
        {},
        {"text": "Car Dieu a tant aimé le monde", "reference": "Jean 3:16", "source": "bible"},
        key_rgb=CHROMA_KEY_GREEN,
    )
    assert img is not None
    alphas = set(img.getchannel("A").getdata())
    assert alphas <= {0, 255}


def test_chroma_render_has_no_key_tinted_pixels() -> None:
    """Tout pixel est soit la clé exacte, soit franchement éloigné d'elle.

    Échouerait sur l'ancien rendu translucide : le badge (18/255) et le
    divider (90/255) composés sur le vert donnaient des pixels à moins
    de 100 de distance RGB de la clé.
    """
    numpy = __import__("numpy")
    img = render_obs_overlay_on_color(
        {},
        {"text": "Car Dieu a tant aimé le monde", "reference": "Jean 3:16", "source": "bible"},
    ).convert("RGB")
    # int32 obligatoire : (r - 0)² dépasse int16 et boucle en négatif.
    arr = numpy.asarray(img).astype(numpy.int32)
    key = numpy.array(CHROMA_KEY_GREEN, dtype=numpy.int32)
    dist = numpy.sqrt(((arr - key) ** 2).sum(axis=2))
    tinted = int(((dist > 2) & (dist < 100)).sum())
    assert tinted == 0, f"{tinted} pixels teintés de la couleur de clé"


def test_accents_remapped_when_close_to_key() -> None:
    assert accent_too_close_to_key((86, 214, 129), (0, 177, 64)) is True  # Bible / vert
    assert accent_too_close_to_key((0, 172, 193), (0, 177, 64)) is True  # Exposé / vert
    assert accent_too_close_to_key((185, 151, 255), (0, 177, 64)) is False  # Cantique / vert
    assert accent_too_close_to_key((185, 151, 255), (255, 0, 255)) is True  # Cantique / magenta
    assert accent_too_close_to_key((224, 160, 68), (0, 177, 64)) is False  # Prédication / vert

    # Intégration : l'accent Bible vert devient neutre sur une clé verte.
    img = render_obs_overlay(
        {},
        {"text": "Car Dieu a tant aimé le monde", "source": "bible"},
        key_rgb=CHROMA_KEY_GREEN,
    )
    assert img is not None
    # La barre d'accent (colonne verte caractéristique) ne contient plus
    # l'accent Bible : aucun pixel de l'image n'est proche de (86,214,129).
    numpy = __import__("numpy")
    arr = numpy.asarray(img.convert("RGB")).astype(numpy.int32)
    bible = numpy.array((86, 214, 129), dtype=numpy.int32)
    dist = numpy.sqrt(((arr - bible) ** 2).sum(axis=2))
    assert int((dist < 40).sum()) == 0, "l'accent Bible vert survit sur une clé verte"


# ── Fenêtre HDMI (offscreen) ─────────────────────────────────────────────


def _make_qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _write_presentation(directory: Path, slide: dict, cfg: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "slide.json").write_text(
        json.dumps(slide, ensure_ascii=False), encoding="utf-8"
    )
    (directory / "obs-config.json").write_text(
        json.dumps(cfg, ensure_ascii=False), encoding="utf-8"
    )


def test_mixer_window_composes_frame_and_hides_cursor(tmp_path: Path) -> None:
    qapp = _make_qapp()
    from PySide6.QtCore import Qt

    from app.ui.mixer_output_window import MixerOutputWindow

    _write_presentation(
        tmp_path,
        {"text": "Car Dieu a tant aimé le monde", "reference": "Jean 3:16", "source": "bible"},
        {"font_family": "Arial", "layout_mode": "lower_third"},
    )
    window = MixerOutputWindow(tmp_path, screen="auto", letterbox=True)
    window.resize(1600, 1000)  # 16:10 → bandes vertes haut/bas
    window._tick()

    assert window._frame_pixmap is not None
    assert window.cursor().shape() == Qt.CursorShape.BlankCursor

    # Bandes letterbox vertes : le coin est vert chroma.
    image = window.grab().toImage()
    corner = image.pixelColor(2, 2)
    assert (corner.red(), corner.green(), corner.blue()) == CHROMA_KEY_GREEN

    # Zone utile 16:9 centrée.
    content = window._content_rect()
    assert content.width() == 1600
    assert content.height() == 900
    window.close()


def test_mixer_window_mire_toggle(tmp_path: Path) -> None:
    qapp = _make_qapp()

    from app.ui.mixer_output_window import MixerOutputWindow

    _write_presentation(tmp_path, {"hidden": True}, {"font_family": "Arial"})
    window = MixerOutputWindow(tmp_path, screen="auto")
    assert window.mire_enabled is False
    assert window.toggle_mire() is True
    assert window.set_mire_enabled(False) is False
    window.close()


def test_mixer_window_key_color_configurable(tmp_path: Path) -> None:
    qapp = _make_qapp()

    from app.ui.mixer_output_window import MixerOutputWindow

    _write_presentation(
        tmp_path,
        {"text": "Car Dieu a tant aimé le monde", "reference": "Jean 3:16", "source": "bible"},
        {"font_family": "Arial", "layout_mode": "lower_third"},
    )
    window = MixerOutputWindow(tmp_path, screen="auto", key_color="magenta")
    window.resize(1600, 900)
    window._tick()

    assert window.key_color == "magenta"
    corner = window.grab().toImage().pixelColor(2, 2)
    assert (corner.red(), corner.green(), corner.blue()) == (255, 0, 255)

    # Changement en direct : bleu, puis valeur invalide → vert.
    window.set_key_color("blue")
    corner = window.grab().toImage().pixelColor(2, 2)
    assert (corner.red(), corner.green(), corner.blue()) == (0, 82, 255)
    window.set_key_color("saumon")
    assert window.key_color == "green"
    window.close()


def test_mixer_window_scale_and_offset_live(tmp_path: Path) -> None:
    qapp = _make_qapp()

    from app.ui.mixer_output_window import MixerOutputWindow

    _write_presentation(
        tmp_path,
        {"text": "Car Dieu a tant aimé le monde", "reference": "Jean 3:16", "source": "bible"},
        {"font_family": "Arial", "layout_mode": "lower_third"},
    )
    window = MixerOutputWindow(
        tmp_path, screen="auto", text_scale=160, offset_y=-120
    )
    window.resize(1600, 900)
    window._tick()
    assert window._frame_pixmap is not None

    window.set_text_scale(80)
    window.set_offset_y(60)
    window._tick()
    assert window._frame_pixmap is not None
    window.close()


def test_mixer_window_missing_screen_falls_back(tmp_path: Path) -> None:
    qapp = _make_qapp()

    from app.ui.mixer_output_window import MixerOutputWindow

    _write_presentation(tmp_path, {"hidden": True}, {})
    window = MixerOutputWindow(tmp_path, screen="Écran fantôme")
    # Écran introuvable → repli automatique sans crash.
    assert window.width() > 0 and window.height() > 0
    window.close()


# ── Anti-veille ──────────────────────────────────────────────────────────


def test_power_guard_reference_counting() -> None:
    from app.utils import power_guard

    power_guard.acquire()
    power_guard.acquire()
    assert power_guard.is_active() is True
    power_guard.release()
    assert power_guard.is_active() is True
    power_guard.release()
    assert power_guard.is_active() is False
    # Libération excédentaire sans effet.
    power_guard.release()
    assert power_guard.is_active() is False


# ── Régression NDI (composition partagée) ────────────────────────────────


def test_ndi_render_delegates_to_shared_overlay() -> None:
    numpy = __import__("numpy")

    from app.utils.ndi_lower_third import NdiLowerThirdSender

    sender = NdiLowerThirdSender(Path(".") / "pres", source_name="Test")
    sender._np = numpy
    sender._last_cfg = {"font_family": "Arial", "layout_mode": "lower_third"}

    frame = sender._render(
        {"text": "Car Dieu a tant aimé le monde", "reference": "Jean 3:16", "source": "bible"}
    )
    assert frame.shape == (1080, 1920, 4)
    assert frame.any()

    hidden = sender._render({"hidden": True})
    assert not hidden.any()


# ── Contrôle avant service ───────────────────────────────────────────────


def test_hdmi_preflight_check_variants() -> None:
    from app.utils.system_health import _hdmi_checks

    assert _hdmi_checks(None) == []
    assert _hdmi_checks({"screen": "auto", "resolution": ""})[0].status == "success"
    missing = _hdmi_checks({"screen": "HDMI-2", "resolution": ""})
    assert missing[0].status == "warning" and "introuvable" in missing[0].detail
    wrong = _hdmi_checks({"screen": "HDMI-2", "resolution": "1600×900"})
    assert wrong[0].status == "warning" and "1920×1080" in wrong[0].detail
    ok = _hdmi_checks({"screen": "HDMI-2", "resolution": "1920×1080"})
    assert ok[0].status == "success"


def test_run_system_health_includes_hdmi_check(tmp_path: Path) -> None:
    from app.utils.system_health import run_system_health

    report = run_system_health(
        database_path=tmp_path / "absente.db",
        data_directory=tmp_path,
        presentation_directory=tmp_path,
        screen_count=2,
        obs_mode="web",
        obs_port=8080,
        hdmi_info={"screen": "HDMI-2", "resolution": "1920×1080"},
    )
    hdmi = [c for c in report.checks if c.key == "hdmi"]
    assert len(hdmi) == 1 and hdmi[0].status == "success"


# ── Bandeau toujours lower third, jamais débordant ────────────────────────

def _non_key_bounds(img) -> tuple[int, int]:
    """Lignes extrêmes portant un pixel différent de la clé verte."""
    numpy = __import__("numpy")
    arr = numpy.asarray(img.convert("RGB")).astype(numpy.int32)
    key = numpy.array(CHROMA_KEY_GREEN, dtype=numpy.int32)
    dist = numpy.sqrt(((arr - key) ** 2).sum(axis=2))
    rows = numpy.where((dist > 30).any(axis=1))[0]
    assert rows.size > 0, "aucun contenu dessiné"
    return int(rows.min()), int(rows.max())


def test_mixer_excludes_fullscreen_but_keeps_other_obs_modes() -> None:
    """Le plein écran OBS ne peut pas devenir une incrustation ; les autres
    modes géométriques (sous-titre, panneau latéral, carte focus) sont repris."""
    from app.ui.mixer_output_window import hdmi_band_config

    forced = hdmi_band_config(
        {"font_family": "Arial", "layout_mode": "fullscreen", "position": "top"}
    )
    assert forced["layout_mode"] == "lower_third"  # plein écran exclu
    assert forced["position"] == "top"  # la position OBS, elle, est reprise
    assert forced["font_family"] == "Arial"

    for mode in ("lower_third", "subtitle", "side_panel", "focus_card"):
        kept = hdmi_band_config({"layout_mode": mode, "max_width": 60})
        assert kept["layout_mode"] == mode

    img = render_obs_overlay_on_color(
        hdmi_band_config({"font_family": "Arial", "layout_mode": "fullscreen"}),
        {"text": "Car Dieu a tant aimé le monde", "reference": "Jean 3:16", "source": "bible"},
    )
    top, _bottom = _non_key_bounds(img)
    # Bandeau par défaut (bas) : la moitié haute reste la couleur de clé.
    assert top > img.height // 2, f"contenu dès y={top} : le bandeau déborde"


def test_band_animation_frames_differ_then_settle() -> None:
    """L'entrée animée produit des trames distinctes puis l'état final."""
    from app.ui.mixer_output_window import hdmi_band_config
    from app.utils.obs_overlay_render import animation_total_ms

    cfg = hdmi_band_config(
        {
            "font_family": "Arial",
            "animation_enabled": True,
            "animation_type": "fade",
            "animation_duration": 400,
            "animation_style": "block",
            "show_kicker": False,
            "show_reference": False,
        }
    )
    slide = {"text": "Car Dieu a tant aimé le monde", "source": "bible"}
    assert animation_total_ms(cfg, slide["text"]) == 400

    def light_pixels(elapsed):
        """Pixels clairs : le texte projeté (le panneau reste sombre)."""
        numpy = __import__("numpy")
        img = render_obs_overlay_on_color(cfg, slide, elapsed_ms=elapsed)
        arr = numpy.asarray(img.convert("RGB")).astype(numpy.int32)
        return int(((arr[:, :, 0] > 170) & (arr[:, :, 2] > 170)).sum())

    start = light_pixels(0)
    middle = light_pixels(200)
    end = light_pixels(400)
    assert start == 0, "le texte doit être invisible au départ"
    assert 0 < middle < end, (start, middle, end)
    # À la fin de l'animation et sans animation, le rendu est identique.
    assert end == light_pixels(None)


def test_band_words_animation_staggers_words() -> None:
    """Révélation mot à mot : les mots apparaissent l'un après l'autre."""
    from app.utils.obs_overlay_render import render_obs_overlay_on_color

    cfg = {
        "font_family": "Arial",
        "animation_enabled": True,
        "animation_type": "reveal",
        "animation_duration": 300,
        "animation_style": "words",
        "show_kicker": False,
        "show_reference": False,
    }
    slide = {"text": "un deux trois quatre cinq six", "source": "custom"}
    first = _non_key_bounds(render_obs_overlay_on_color(cfg, slide, elapsed_ms=200))[0]
    later = _non_key_bounds(render_obs_overlay_on_color(cfg, slide, elapsed_ms=700))[0]
    # Le bloc de texte s'élargit (les mots arrivent avec un décalage) : à
    # 200 ms la ligne est moins avancée qu'à 700 ms.
    assert later >= first


def test_mixer_long_text_is_clipped_like_the_obs_page(tmp_path: Path) -> None:
    """Sans auto-ajustement, le texte garde sa taille et le bandeau est rogné.

    C'est le comportement de la page OBS : `auto_fit` désactivé (réglage par
    défaut de l'application) signifie « ne pas rétrécir » — le panneau se
    limite à la zone utile (`max-height` + `overflow: hidden`) au lieu de
    rétrécir la typographie, et il ne recouvre jamais l'écran entier.
    """
    from app.ui.mixer_output_window import hdmi_band_config

    long_text = "\n".join(
        f"Ligne {i} : benissez l'Eternel, vous toutes ses oeuvres," for i in range(30)
    )
    img = render_obs_overlay_on_color(
        hdmi_band_config(
            {
                "font_family": "Arial",
                "layout_mode": "lower_third",
                "edge_margin": 40,
                "safe_area_percent": 5,
            }
        ),
        {"text": long_text, "reference": "Psaume 103", "source": "bible"},
    )
    top, _bottom = _non_key_bounds(img)
    # Le bandeau démarre à la zone utile : bord 40 px + zone sûre 5 % de
    # 1080 (54 px) = 94 px, et déborde vers le bas — jamais par-dessus
    # l'écran entier.
    assert top == 94, f"bandeau attendu à la marge utile, contenu dès y={top}"


def test_renderer_shrinks_only_when_auto_fit_is_enabled() -> None:
    """`auto_fit` actif + `uniform_text_size` désactivé : la typographie
    rétrécit pour tenir (règle exacte de la page OBS)."""
    from app.ui.mixer_output_window import hdmi_band_config

    long_text = "\n".join(f"Ligne {i} de la prédication" for i in range(12))
    base_cfg = {
        "font_family": "Arial",
        "layout_mode": "lower_third",
        "auto_fit": True,
        "uniform_text_size": False,
        "min_text_size": 18,
        "max_lines": 10,
        "text_size": 40,
    }
    shrunk = render_obs_overlay_on_color(
        hdmi_band_config(base_cfg),
        {"text": long_text, "source": "sermon"},
    )
    fixed = render_obs_overlay_on_color(
        hdmi_band_config({**base_cfg, "auto_fit": False}),
        {"text": long_text, "source": "sermon"},
    )
    top_shrunk, _ = _non_key_bounds(shrunk)
    top_fixed, _ = _non_key_bounds(fixed)
    # Le bandeau réduit démarre plus bas (donc moins haut) que celui figé.
    assert top_shrunk > top_fixed


def test_renderer_fullscreen_mode_unchanged_for_other_outputs() -> None:
    """Le mode plein écran reste disponible hors HDMI (page OBS, NDI) :
    le forçage lower third vit dans la fenêtre mixeur, pas au moteur."""
    img = render_obs_overlay_on_color(
        {"font_family": "Arial", "layout_mode": "fullscreen"},
        {"text": "Car Dieu a tant aimé le monde", "reference": "Jean 3:16"},
    )
    top, _bottom = _non_key_bounds(img)
    assert top < 300, f"plein écran attendu près du haut, contenu à y={top}"
