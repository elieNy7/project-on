"""Atomic settings storage and user-bound Windows secret protection."""
from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
import threading
from pathlib import Path

log = logging.getLogger(__name__)
_lock = threading.RLock()


def protect_secret(secret: str) -> str:
    if not secret:
        return ""
    import win32crypt

    protected = win32crypt.CryptProtectData(
        secret.encode("utf-8"), "Project-On OBS", None, None, None, 1
    )
    return base64.b64encode(protected).decode("ascii")


def unprotect_secret(value: str) -> str:
    if not value:
        return ""
    import win32crypt

    _, data = win32crypt.CryptUnprotectData(
        base64.b64decode(value, validate=True), None, None, None, 1
    )
    return data.decode("utf-8")


def _read_payload(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("La racine des paramètres doit être un objet JSON.")
    return payload


def load_payload(path: Path) -> tuple[dict, str]:
    try:
        return _read_payload(path), ""
    except FileNotFoundError:
        if not path.with_suffix(path.suffix + ".bak").exists():
            return {}, ""
    except (OSError, ValueError, UnicodeError):
        log.warning("Paramètres illisibles : %s", path)
    try:
        payload = _read_payload(path.with_suffix(path.suffix + ".bak"))
        return payload, "Paramètres récupérés depuis la dernière sauvegarde valide. Vérifiez vos réglages avant de projeter."
    except (OSError, ValueError, UnicodeError):
        return {}, "Paramètres illisibles : valeurs par défaut utilisées. Le fichier original sera conservé à la prochaine sauvegarde."


def _publish(path: Path, data: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def save_payload(path: Path, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        if path.exists():
            try:
                previous = _read_payload(path)
            except (ValueError, UnicodeError):
                fd, name = tempfile.mkstemp(prefix=path.name + ".corrupt-", dir=path.parent)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(path.read_bytes())
            else:
                # A legacy plaintext password must not survive in the backup.
                remote = previous.get("obs", {}).get("remote", {}) if isinstance(previous.get("obs"), dict) else {}
                if isinstance(remote, dict):
                    remote.pop("password", None)
                _publish(path.with_suffix(path.suffix + ".bak"), json.dumps(previous, ensure_ascii=False, indent=2).encode("utf-8"))
        _publish(path, data)
        _publish(path.with_suffix(path.suffix + ".bak"), data)
