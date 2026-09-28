"""Reprise après coupure : le programme en direct survit à un arrêt brutal.

À chaque changement du direct, le programme (slides, titre, position,
masquage) est enregistré de façon atomique dans ``data/live-recovery.json``.
Une fermeture normale supprime le fichier. S'il est encore là au démarrage,
c'est que Project-On s'est arrêté brutalement (coupure de courant, plantage) :
l'opérateur peut reprendre exactement là où il était.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.utils.models import Slide

MAX_AGE = timedelta(hours=12)


def snapshot(controller, hidden: bool = False) -> dict[str, Any] | None:
    """État du direct sérialisable (None si rien n'est projeté)."""
    state = controller.capture_live_state()
    if not state.slides or state.current_row < 0:
        return None
    return {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "title": state.title,
        "current_row": state.current_row,
        "entry_start_rows": list(state.entry_start_rows),
        "hidden": bool(hidden),
        "slides": [asdict(s) for s in state.slides],
    }


def save(path: Path, data: dict[str, Any] | None) -> None:
    if data is None:
        clear(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".recovery-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def clear(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def load(path: Path, now: datetime | None = None) -> dict[str, Any] | None:
    """État à reprendre, ou None (absent, illisible ou trop ancien)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        saved = datetime.fromisoformat(str(data["saved_at"]))
        slides = [Slide(**s) for s in data["slides"]]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if (now or datetime.now()) - saved > MAX_AGE or not slides:
        return None
    data["slides"] = slides
    data["saved_at"] = saved
    return data


def restore(controller, data: dict[str, Any]) -> int:
    """Recharge le programme sauvegardé et projette la slide où l'on était."""
    return controller.restore_program(
        data["slides"],
        str(data.get("title") or ""),
        list(data.get("entry_start_rows") or []),
        int(data.get("current_row") or 0),
    )
