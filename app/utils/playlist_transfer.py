"""Versioned portable playlist archives; no dependency on the active profile."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile

MAX_BYTES = 2 * 1024**3
MAX_FILES = 10000
MAX_MANIFEST = 8 * 1024**2


def _check_cancel(cancel):
    if cancel and cancel.is_set():
        raise InterruptedError("Transfert annulé avant insertion")


def _member(name):
    path = PurePosixPath(name)
    if not name or "\\" in name or ":" in name or path.is_absolute() or ".." in path.parts:
        raise ValueError("Chemin d'archive non autorisé")
    return path


def manifest(name, items):
    return {"app": "Project-On", "format": 2, "name": name, "items": [
        {key: str(it.get(key) or ("custom" if key == "source" else ""))
         for key in ("source", "reference", "text", "background")}
        for it in items]}


def _validate(payload, fallback):
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("Format de playlist invalide")
    if payload.get("format", 1) not in (1, 2):
        raise ValueError("Version de playlist non prise en charge")
    if len(payload["items"]) > MAX_FILES:
        raise ValueError("Trop d'éléments")
    items = []
    for item in payload["items"]:
        if not isinstance(item, dict):
            raise ValueError("Élément de playlist invalide")
        row = {}
        for key in ("source", "reference", "text", "background"):
            value = item.get(key) or ("custom" if key == "source" else "")
            if not isinstance(value, str):
                raise ValueError("Champ de playlist invalide")
            row[key] = value
        if row["text"].strip() or row["background"]:
            items.append(row)
    if not items:
        raise ValueError("Playlist vide")
    return str(payload.get("name") or fallback), items


def export_playlist(path, name, items, cancel=None):
    """Publish a ZIP atomically. Missing media fails, never silently drops it."""
    path = Path(path)
    payload = manifest(name, items)
    _validate(payload, path.stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    os.close(fd)
    total = 0
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            names = {}
            for row in payload["items"]:
                _check_cancel(cancel)
                if not row["background"]:
                    continue
                source = Path(row["background"])
                if not source.is_file():
                    raise ValueError(f"Média absent : {source}")
                key = str(source.resolve())
                if key not in names:
                    total += source.stat().st_size
                    if total > MAX_BYTES:
                        raise ValueError("Archive supérieure à la limite de 2 Gio")
                    member = f"media/{len(names):05d}{source.suffix.lower()}"
                    _member(member)
                    with source.open("rb") as src, archive.open(member, "w") as dst:
                        while block := src.read(1024 * 1024):
                            _check_cancel(cancel)
                            dst.write(block)
                    names[key] = member
                row["background"] = names[key]
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if len(data) > MAX_MANIFEST:
                raise ValueError("Manifeste trop volumineux")
            archive.writestr("manifest.json", data)
        _check_cancel(cancel)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return len(payload["items"])


def read_playlist(path, media_directory, cancel=None):
    """Return name/items, importing assets into an explicit destination.

    Legacy JSON format 1 remains readable. Assets use content-derived names;
    no archive member is extracted by its supplied filesystem path.
    """
    path, media_directory = Path(path), Path(media_directory)
    if not zipfile.is_zipfile(path):
        if path.stat().st_size > MAX_MANIFEST:
            raise ValueError("Manifeste trop volumineux")
        name, items = _validate(json.loads(path.read_text(encoding="utf-8-sig")), path.stem)
        for row in items:
            if row["background"]:
                source = Path(row["background"])
                if not source.is_absolute():
                    source = path.parent / source
                row["background"] = str(_store(source, media_directory, cancel))
        return name, items
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_BYTES:
            raise ValueError("Archive trop volumineuse")
        members = {}
        for info in infos:
            _member(info.filename)
            if info.filename in members or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Membre dupliqué ou lien non autorisé")
            members[info.filename] = info
        info = members.get("manifest.json")
        if info is None or info.file_size > MAX_MANIFEST:
            raise ValueError("Manifeste absent ou trop volumineux")
        name, items = _validate(json.loads(archive.read(info)), path.stem)
        # Validate every reference before writing any asset.
        for row in items:
            member = row["background"]
            if member:
                _member(member)
                if member not in members or members[member].is_dir():
                    raise ValueError(f"Média absent de l'archive : {member}")
        media_directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=media_directory) as staging:
            resolved = {}
            for row in items:
                _check_cancel(cancel)
                member = row["background"]
                if not member:
                    continue
                if member not in resolved:
                    target = Path(staging) / (str(len(resolved)) + PurePosixPath(member).suffix)
                    with archive.open(member) as src, target.open("wb") as dst:
                        while block := src.read(1024 * 1024):
                            _check_cancel(cancel)
                            dst.write(block)
                    resolved[member] = str(_store(target, media_directory, cancel))
                row["background"] = resolved[member]
        return name, items


def _store(source, directory, cancel=None):
    directory.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
    digest = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as dst, Path(source).open("rb") as src:
            while block := src.read(1024 * 1024):
                _check_cancel(cancel)
                digest.update(block)
                dst.write(block)
        target = directory / (digest.hexdigest() + Path(source).suffix.lower())
        _check_cancel(cancel)
        if not target.exists():
            os.replace(temporary, target)
        else:
            with target.open("rb") as existing:
                if hashlib.file_digest(existing, "sha256").hexdigest() != digest.hexdigest():
                    raise ValueError("Média existant endommagé ; aucun écrasement")
        return target
    finally:
        Path(temporary).unlink(missing_ok=True)


def import_playlist(path, dao, media_directory, cancel=None):
    name, items = read_playlist(path, media_directory, cancel)
    _check_cancel(cancel)
    return dao.import_folder(name, items)
