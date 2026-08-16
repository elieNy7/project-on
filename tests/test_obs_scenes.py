"""Tests des nouveautés OBS 1.6 : styles par scène, contrôle distant."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.utils.obs_controller import ObsController
from app.utils.obs_websocket import (
    build_browser_source_settings,
    build_identify_payload,
    compute_obs_auth_hash,
)
from app.utils.settings import (
    AppSettings,
    ObsOutputSettings,
    ObsScene,
    ObsSettings,
    scene_slug,
)


def test_scene_slug_strips_accents_and_is_url_safe() -> None:
    assert scene_slug("Prédication") == "predication"
    assert scene_slug("Louange 2026!") == "louange-2026"
    assert scene_slug("") == "scene"
    assert scene_slug(",,,") == "scene"


def test_scene_slug_guarantees_uniqueness() -> None:
    existing = ["predication"]
    assert scene_slug("Prédication", existing) == "predication-2"
    existing.append("predication-2")
    assert scene_slug("predication", existing) == "predication-3"


def test_obs_settings_scenes_round_trip(tmp_path: Path) -> None:
    settings = AppSettings()
    settings.obs.web_port = 9099
    settings.obs.output.text_size = 61
    scene = ObsScene(id="louange", name="Louange")
    scene.output.layout_mode = "fullscreen"
    scene.output.text_size = 72
    scene.output.animation_style = "words"
    settings.obs.scenes = [scene]
    settings.obs.remote = type(settings.obs.remote)(
        enabled=True,
        host="192.168.1.20",
        port=4455,
        password="secret",
        scene_on_live="Direct louange",
        scene_on_hide="Accueil",
    )

    path = tmp_path / "settings.json"
    settings.save(path)

    loaded = AppSettings.load(path)
    assert loaded.obs.web_port == 9099
    assert loaded.obs.output.text_size == 61
    assert len(loaded.obs.scenes) == 1
    restored = loaded.obs.scenes[0]
    assert restored.id == "louange"
    assert restored.name == "Louange"
    assert restored.output.layout_mode == "fullscreen"
    assert restored.output.text_size == 72
    assert restored.output.animation_style == "words"
    assert loaded.obs.remote.enabled is True
    assert loaded.obs.remote.host == "192.168.1.20"
    assert loaded.obs.remote.password == "secret"
    assert loaded.obs.remote.scene_on_live == "Direct louange"
    assert loaded.obs.remote.scene_on_hide == "Accueil"


def test_legacy_settings_load_without_scenes_or_remote(tmp_path: Path) -> None:
    """settings.json d'une version < 1.6 doit charger sans scènes ni remote."""
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "projection": {},
                "obs": {"mode": "web", "web_port": 8080},
                "appearance": {"theme": "dark", "language": "fr"},
            }
        ),
        encoding="utf-8",
    )
    loaded = AppSettings.load(path)
    assert loaded.obs.scenes == []
    assert loaded.obs.remote.enabled is False
    assert loaded.obs.remote.port == 4455


def test_duplicate_scene_ids_are_made_unique_on_load(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "obs": {
                    "scenes": [
                        {"id": "x", "name": "Un"},
                        {"id": "x", "name": "Deux"},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    loaded = AppSettings.load(path)
    ids = [s.id for s in loaded.obs.scenes]
    assert len(ids) == 2
    assert len(set(ids)) == 2


def test_to_full_obs_config_embeds_scene_payloads() -> None:
    obs = ObsSettings()
    obs.output.text_size = 50
    scene = ObsScene(id="predication", name="Prédication")
    scene.output.text_size = 44
    scene.output.layout_mode = "side_panel"
    obs.scenes = [scene]

    config = obs.to_full_obs_config()

    assert config["text_size"] == 50
    assert set(config["scenes"].keys()) == {"predication"}
    scene_cfg = config["scenes"]["predication"]
    assert scene_cfg["text_size"] == 44
    assert scene_cfg["layout_mode"] == "side_panel"
    # Chaque payload embarque sa propre version (cache-busting indépendant).
    assert "version" in scene_cfg


def test_animation_style_is_validated_in_config() -> None:
    assert ObsOutputSettings(animation_style="words").to_obs_config()[
        "animation_style"
    ] == "words"
    assert ObsOutputSettings(animation_style="bogus").to_obs_config()[
        "animation_style"
    ] == "block"


def test_controller_scene_urls_and_config_broadcast() -> None:
    controller = ObsController(settings=ObsSettings(web_port=18080))
    scene = ObsScene(id="louange", name="Louange")
    controller.settings.scenes = [scene]

    urls = controller.get_scene_urls()
    assert urls == {"louange": "http://127.0.0.1:18080/obs?scene=louange"}

    started = controller.start_web_server()
    try:
        assert started is True
        import urllib.request

        with urllib.request.urlopen(
            "http://127.0.0.1:18080/api/config", timeout=5
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert "scenes" in payload
        assert "louange" in payload["scenes"]
    finally:
        controller.stop()


def test_obs_auth_hash_matches_reference_vector() -> None:
    """Vecteur calculé à la main selon la spéc obs-websocket v5."""
    # sha256("pwd+salt") → base64 → +challenge → sha256 → base64
    hash_value = compute_obs_auth_hash("pwd", "salt", "challenge")
    import base64
    import hashlib

    secret = hashlib.sha256(b"pwdsalt").digest()
    expected = base64.b64encode(
        hashlib.sha256(base64.b64encode(secret) + b"challenge").digest()
    ).decode("ascii")
    assert hash_value == expected


def test_identify_payload_omits_auth_when_no_challenge() -> None:
    payload = build_identify_payload("secret", "", "")
    assert "authentication" not in payload
    assert payload["rpcVersion"] == 1

    payload = build_identify_payload("secret", "salt", "challenge")
    assert payload["authentication"] == compute_obs_auth_hash(
        "secret", "salt", "challenge"
    )


def test_browser_source_settings_are_1080p() -> None:
    settings = build_browser_source_settings("http://127.0.0.1:8080/obs")
    assert settings["url"] == "http://127.0.0.1:8080/obs"
    assert settings["width"] == 1920
    assert settings["height"] == 1080
