"""Mise à jour intégrée (GitHub Releases)."""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.utils import updater

RELEASE = {
    "tag_name": "v2.7.0",
    "html_url": "https://github.com/elieNy7/project-on/releases/tag/v2.7.0",
    "body": "Notes",
    "assets": [
        {"name": "ProjectOn_2.7.0_Portable.zip", "size": 10,
         "browser_download_url": "https://github.com/elieNy7/project-on/releases/download/v2.7.0/ProjectOn_2.7.0_Portable.zip"},
        {"name": "ProjectOn_2.7.0_Setup.exe", "size": 11,
         "browser_download_url": "https://github.com/elieNy7/project-on/releases/download/v2.7.0/ProjectOn_2.7.0_Setup.exe"},
    ],
}


def test_versions() -> None:
    assert updater.is_newer("2.7.0", "2.6.2")
    assert updater.is_newer("v2.10.0", "2.9.9")
    assert not updater.is_newer("2.6.2", "2.6.2")
    assert not updater.is_newer("2.6.1", "2.6.2")


def test_parse_release_picks_setup_and_rejects_foreign_hosts() -> None:
    info = updater.parse_release(RELEASE)
    assert info.version == "2.7.0" and info.url.endswith("_Setup.exe") and info.size == 11
    evil = dict(RELEASE, assets=[dict(RELEASE["assets"][1],
                browser_download_url="https://evil.example/ProjectOn_2.7.0_Setup.exe")])
    assert updater.parse_release(evil) is None
    assert updater.parse_release(dict(RELEASE, prerelease=True)) is None
    digest = "a" * 64
    assert updater.parse_release(dict(RELEASE, body=f"SHA-256 : {digest}")).sha256 == digest


class _Response(io.BytesIO):
    def __init__(self, data: bytes, url: str) -> None:
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}
        self._url = url

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def test_download_verifies_size_and_hash(tmp_path: Path, monkeypatch) -> None:
    data = b"installeur"
    good = "https://objects.githubusercontent.com/x"
    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda req, timeout: _Response(data, good))
    info = updater.UpdateInfo("2.7.0", RELEASE["assets"][1]["browser_download_url"],
                              len(data), "", "", hashlib.sha256(data).hexdigest())
    path = updater.download(info, tmp_path)
    assert path.name == "ProjectOn_2.7.0_Setup.exe" and path.read_bytes() == data

    bad = updater.UpdateInfo("2.7.0", info.url, len(data) + 5, "", "")
    with pytest.raises(ValueError):
        updater.download(bad, tmp_path / "b")
    assert not list((tmp_path / "b").glob("*.exe"))

    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda req, timeout: _Response(data, "https://evil.example/x"))
    with pytest.raises(ValueError):
        updater.download(info, tmp_path / "c")


def test_update_dialog_shows_new_version() -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from app.ui.update_dialog import UpdateDialog

    dialog = UpdateDialog(auto_check=False)
    try:
        dialog._on_checked(updater.parse_release(RELEASE), "")
        assert "2.7.0" in dialog.status.text() and not dialog.install_btn.isHidden()
        dialog._on_checked(None, "timeout")
        assert "Internet" in dialog.status.text() and dialog.install_btn.isHidden()
    finally:
        dialog.close()
