"""Mise à jour intégrée depuis les versions publiées sur GitHub.

Quand Internet est disponible, Project-On lit la dernière version publiée
(API GitHub Releases), la compare à la sienne puis, à la demande de
l'opérateur, télécharge l'installeur ``ProjectOn_<version>_Setup.exe`` et le
lance. L'installeur conserve la base, les playlists et les réglages.

Sécurité : téléchargement uniquement en HTTPS depuis github.com, taille
vérifiée contre celle annoncée par GitHub, empreinte SHA-256 vérifiée quand
les notes de version la publient, fichier publié seulement s'il est complet.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from app.version import __version__

REPOSITORY = "elieNy7/project-on"
LATEST_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
_ALLOWED_HOSTS = {"github.com", "objects.githubusercontent.com",
                  "release-assets.githubusercontent.com"}


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    url: str
    size: int
    notes: str
    page: str
    sha256: str = ""


def parse_version(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", str(value or ""))
    return tuple(int(n) for n in numbers[:4]) or (0,)


def is_newer(remote: str, local: str = __version__) -> bool:
    return parse_version(remote) > parse_version(local)


def parse_release(payload: dict) -> UpdateInfo | None:
    """Version et installeur d'une réponse « releases/latest »."""
    if not isinstance(payload, dict) or payload.get("draft") or payload.get("prerelease"):
        return None
    version = str(payload.get("tag_name") or "").lstrip("vV")
    for asset in payload.get("assets") or []:
        name = str(asset.get("name") or "")
        if re.fullmatch(r"ProjectOn_[\d.]+_Setup\.exe", name):
            url = str(asset.get("browser_download_url") or "")
            if urlparse(url).scheme != "https" or urlparse(url).hostname not in _ALLOWED_HOSTS:
                return None
            notes = str(payload.get("body") or "")
            digest = re.search(r"SHA-?256[^0-9a-fA-F]*([0-9a-fA-F]{64})", notes)
            return UpdateInfo(
                version=version,
                url=url,
                size=int(asset.get("size") or 0),
                notes=notes,
                page=str(payload.get("html_url") or ""),
                sha256=digest.group(1).lower() if digest else "",
            )
    return None


def check_latest(timeout: float = 8.0) -> UpdateInfo | None:
    """Dernière version publiée (None sans Internet ou sans installeur)."""
    request = urllib.request.Request(
        LATEST_URL,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": f"Project-On/{__version__}"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return parse_release(json.loads(response.read().decode("utf-8")))


def download(info: UpdateInfo, folder: Path,
             progress: Callable[[int, int], None] | None = None,
             cancelled: Callable[[], bool] = lambda: False,
             timeout: float = 30.0) -> Path:
    """Télécharge l'installeur et le vérifie ; renvoie son chemin."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / Path(urlparse(info.url).path).name
    partial = target.with_suffix(".part")
    digest = hashlib.sha256()
    received = 0
    request = urllib.request.Request(info.url, headers={"User-Agent": f"Project-On/{__version__}"})
    with urllib.request.urlopen(request, timeout=timeout) as response, partial.open("wb") as out:
        final_host = urlparse(response.geturl()).hostname
        if final_host not in _ALLOWED_HOSTS:
            raise ValueError(f"Téléchargement redirigé vers un hôte inattendu : {final_host}")
        total = int(response.headers.get("Content-Length") or info.size or 0)
        while True:
            if cancelled():
                raise InterruptedError("Téléchargement annulé.")
            block = response.read(512 * 1024)
            if not block:
                break
            out.write(block)
            digest.update(block)
            received += len(block)
            if progress is not None:
                progress(received, total)
    try:
        if info.size and received != info.size:
            raise ValueError(f"Fichier incomplet ({received} / {info.size} octets).")
        if info.sha256 and digest.hexdigest() != info.sha256:
            raise ValueError("Empreinte SHA-256 différente de celle publiée.")
    except ValueError:
        partial.unlink(missing_ok=True)
        raise
    partial.replace(target)
    return target


def launch_installer(path: Path) -> None:
    """Lance l'installeur (Windows) ; l'application doit ensuite se fermer."""
    import os
    import subprocess
    import sys

    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:  # pragma: no cover - Project-On est distribué pour Windows
        subprocess.Popen([str(path)])
