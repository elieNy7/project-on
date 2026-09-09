"""Bandeau défilant : réglages, diffusion OBS et composition NDI."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.utils.settings import ObsSettings, TickerSettings  # noqa: E402


def _payload() -> dict:
    return TickerSettings(
        enabled=True,
        texts=["Culte dimanche 10 h", "Réunion mercredi 19 h"],
        speed=120,
        height=72,
        bg_color="rgba(0,0,0,0.9)",
        text_color="#ffffff",
        font_size=32,
    ).to_payload()


def test_ticker_payload_fields() -> None:
    payload = _payload()
    assert payload["enabled"] is True
    assert payload["texts"] == ["Culte dimanche 10 h", "Réunion mercredi 19 h"]
    assert payload["speed"] == 120
    assert payload["height"] == 72
    assert payload["font_size"] == 32
    # Le payload ne transporte que les champs d'affichage (pas la playlist
    # d'annonces, propre à la projection locale).
    assert "announcement_folder_id" not in payload


def test_full_obs_config_embeds_ticker() -> None:
    obs = ObsSettings()
    assert obs.to_full_obs_config()["ticker"] == {}

    config = obs.to_full_obs_config(ticker=_payload())
    assert config["ticker"]["enabled"] is True
    assert "scenes" in config
    assert "layout_mode" in config


def test_controller_diffuses_ticker_to_web_server() -> None:
    from app.utils.obs_controller import ObsController

    captured: dict = {}

    class _StubServer:
        def update_config(self, config: dict) -> None:
            captured.update(config)

    controller = ObsController(ObsSettings())
    controller._web_server = _StubServer()
    controller.update_ticker(_payload())

    assert captured["ticker"]["enabled"] is True
    assert captured["ticker"]["speed"] == 120


def test_ndi_sender_composes_ticker_band() -> None:
    numpy = __import__("numpy")

    from app.utils.ndi_lower_third import NdiLowerThirdSender

    sender = NdiLowerThirdSender(Path(".") / "pres", source_name="Test")
    sender._np = numpy
    sender._last_cfg = {
        "font_family": "Arial",
        "ticker": {
            "enabled": True,
            "texts": ["Culte dimanche 10 h"],
            "speed": 90,
            "height": 64,
            "font_size": 30,
            "bg_color": "rgba(0, 0, 0, 0.9)",
            "text_color": "#ffffff",
        },
    }

    sender._refresh_ticker_resources()
    assert sender._ticker_res is not None
    assert sender._ticker_res["height"] == 64

    base = numpy.zeros((sender._height, sender._width, 4), dtype=numpy.uint8)
    frame = sender._apply_ticker(base, 0.0)

    # La bande basse porte le fond (alpha) ; le reste de l'image est intact.
    band_alpha = frame[-64:, :, 3]
    assert band_alpha.max() > 0
    top = frame[: sender._height - 64, :, :]
    assert not top.any()

    # Inactif : aucune ressource, l'image passe sans modification.
    sender._last_cfg = {"ticker": {"enabled": False}}
    sender._refresh_ticker_resources()
    assert sender._ticker_res is None
    frame2 = sender._apply_ticker(base, 0.0)
    assert frame2 is base
