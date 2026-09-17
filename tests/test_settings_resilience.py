from __future__ import annotations

import json
import secrets

import pytest

from app.utils.settings import AppSettings
from app.utils import settings_storage


def test_corrupt_file_recovers_last_saved_settings(tmp_path):
    path = tmp_path / "settings.json"
    settings = AppSettings()
    settings.projection.text_size = 71
    settings.save(path)
    path.write_text("{corrompu", encoding="utf-8")
    recovered = AppSettings.load(path)
    assert recovered.projection.text_size == 71
    assert "récupérés" in recovered.load_warning


def test_invalid_file_preserved_when_saving_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{corrompu", encoding="utf-8")
    loaded = AppSettings.load(path)
    assert "par défaut" in loaded.load_warning
    loaded.save(path)
    preserved = list(tmp_path.glob("settings.json.corrupt-*"))
    assert len(preserved) == 1
    assert preserved[0].read_text(encoding="utf-8") == "{corrompu"
    assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)


def test_missing_settings_is_silent(tmp_path):
    assert not AppSettings.load(tmp_path / "absent.json").load_warning


def test_secret_roundtrip_and_legacy_migration(tmp_path):
    pytest.importorskip("win32crypt")
    path = tmp_path / "settings.json"
    secret = secrets.token_urlsafe(24)
    path.write_text(json.dumps({"obs": {"remote": {"password": secret}}}), encoding="utf-8")
    settings = AppSettings.load(path)
    assert settings.obs.remote.password == secret
    settings.save(path)
    assert AppSettings.load(path).obs.remote.password == secret
    assert secret not in path.read_text(encoding="utf-8")
    assert secret not in path.with_suffix(".json.bak").read_text(encoding="utf-8")


def test_protection_failure_does_not_overwrite_settings(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    settings = AppSettings()
    settings.save(path)
    original = path.read_bytes()
    settings.obs.remote.password = secrets.token_urlsafe(24)

    def unavailable(value):
        raise RuntimeError("Protection indisponible")

    monkeypatch.setattr(settings_storage, "protect_secret", unavailable)
    with pytest.raises(RuntimeError, match="Protection indisponible"):
        settings.save(path)
    assert path.read_bytes() == original
