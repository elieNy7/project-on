"""Tests de l'archive complète (bundle) et de sa restauration sûre.

Aucun accès au profil réel : tout se passe dans tmp_path. La restauration
n'est autorisée que vers un dossier inexistant — jamais dans un profil actif.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import zipfile
from pathlib import Path

import pytest

from app.utils.backup_manager import (
    create_backup_bundle,
    restore_backup_bundle,
)


def _make_profile(root: Path) -> dict[str, Path]:
    data = root / "data"
    data.mkdir(parents=True)
    db = data / "project_on.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE hymn (id INTEGER PRIMARY KEY, title TEXT)")
        conn.execute("INSERT INTO hymn (title) VALUES ('Grâce')")
    settings = data / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "appearance": {"theme": "dark"},
                "obs": {
                    "remote": {"password": secrets.token_urlsafe(24), "port": 4444}
                },
            }
        ),
        encoding="utf-8",
    )
    media = root / "media"
    media.mkdir()
    (media / "image.png").write_bytes(b"PNGDATA")
    backgrounds = root / "backgrounds"
    backgrounds.mkdir()
    (backgrounds / "fond.png").write_bytes(b"BGFOND")
    return {
        "db": db,
        "settings": settings,
        "media": media,
        "backgrounds": backgrounds,
    }


def test_bundle_contains_db_media_backgrounds_and_sanitized_settings(tmp_path):
    profile = _make_profile(tmp_path / "profile")
    archive = tmp_path / "sauvegarde.projecton"

    result = create_backup_bundle(
        profile["db"],
        archive,
        media_root=profile["media"],
        backgrounds_root=profile["backgrounds"],
        settings_file=profile["settings"],
    )

    assert result.path == archive.resolve()
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        manifest = json.loads(bundle.read("manifest.json"))
        settings_payload = json.loads(bundle.read(manifest["settings"]))
    assert manifest["format"] == "project-on-backup"
    assert isinstance(manifest["format_version"], int)
    assert manifest["database"] in names
    assert "media/image.png" in names
    assert "backgrounds/fond.png" in names
    # Secret exclu de l'archive.
    assert "password" not in json.dumps(settings_payload)
    assert settings_payload["appearance"]["theme"] == "dark"


def test_restore_bundle_rebuilds_profile_on_fresh_target(tmp_path):
    profile = _make_profile(tmp_path / "profile")
    archive = tmp_path / "sauvegarde.projecton"
    create_backup_bundle(
        profile["db"],
        archive,
        media_root=profile["media"],
        backgrounds_root=profile["backgrounds"],
        settings_file=profile["settings"],
    )

    target = tmp_path / "restored"
    restored = restore_backup_bundle(archive, target)

    assert (restored / "data" / "project_on.db").is_file()
    with sqlite3.connect(restored / "data" / "project_on.db") as conn:
        assert conn.execute("SELECT title FROM hymn").fetchone()[0] == "Grâce"
    assert (restored / "media" / "image.png").read_bytes() == b"PNGDATA"
    assert (restored / "backgrounds" / "fond.png").read_bytes() == b"BGFOND"
    settings = json.loads(
        (restored / "data" / "settings.json").read_text(encoding="utf-8")
    )
    assert "password" not in json.dumps(settings)


def test_restore_refuses_existing_target(tmp_path):
    profile = _make_profile(tmp_path / "profile")
    archive = tmp_path / "sauvegarde.projecton"
    create_backup_bundle(profile["db"], archive)
    target = tmp_path / "restored"
    target.mkdir()
    with pytest.raises(ValueError):
        restore_backup_bundle(archive, target)


def test_restore_refuses_corrupted_archive(tmp_path):
    profile = _make_profile(tmp_path / "profile")
    archive = tmp_path / "sauvegarde.projecton"
    create_backup_bundle(profile["db"], archive, media_root=profile["media"])
    corrupted = tmp_path / "corrompu.projecton"
    with zipfile.ZipFile(archive) as original, zipfile.ZipFile(corrupted, "w") as changed:
        for name in original.namelist():
            changed.writestr(name, b"BADDATA" if name == "media/image.png" else original.read(name))
    with pytest.raises(ValueError):
        restore_backup_bundle(corrupted, tmp_path / "restored")


def test_restore_refuses_archive_without_manifest(tmp_path):
    archive = tmp_path / "sans-manifeste.projecton"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("data/project_on.db", b"whatever")
    with pytest.raises(ValueError):
        restore_backup_bundle(archive, tmp_path / "restored")


def test_bundle_reports_missing_referenced_files(tmp_path):
    profile = _make_profile(tmp_path / "profile")
    missing = profile["media"] / "image.png"
    with sqlite3.connect(profile["db"]) as conn:
        conn.execute("CREATE TABLE media_item (path TEXT)")
        conn.execute("INSERT INTO media_item VALUES (?)", (str(missing),))
    missing.unlink()
    archive = tmp_path / "sauvegarde.projecton"
    with pytest.raises(FileNotFoundError):
        create_backup_bundle(profile["db"], archive, media_root=profile["media"])
    assert not archive.exists()


def test_restore_relocates_external_references(tmp_path):
    profile = _make_profile(tmp_path / "profile")
    external = tmp_path / "external.png"
    external.write_bytes(b"external")
    with sqlite3.connect(profile["db"]) as conn:
        conn.execute("CREATE TABLE media_item (path TEXT)")
        conn.execute("CREATE TABLE playlist_item (background TEXT)")
        conn.execute("INSERT INTO media_item VALUES (?)", (str(external),))
        conn.execute("INSERT INTO playlist_item VALUES (?)", (str(external),))
    archive = tmp_path / "bundle.zip"
    create_backup_bundle(profile["db"], archive)
    external.unlink()
    target = restore_backup_bundle(archive, tmp_path / "restored")
    with sqlite3.connect(target / "data/project_on.db") as conn:
        path = Path(conn.execute("SELECT path FROM media_item").fetchone()[0])
        assert path.is_relative_to(target)
        assert path.read_bytes() == b"external"
        assert conn.execute("SELECT background FROM playlist_item").fetchone()[0] == str(path)
