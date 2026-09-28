"""Export pour le montage vidéo : images transparentes + sous-titres + minutage.

Chaque slide de l'historique devient une image PNG 1920×1080 à fond
transparent, composée exactement comme la sortie OBS (même style). Le
dossier contient aussi ``sous-titres.srt`` et ``minutage.csv`` (heure,
durée, image) : les monteurs (DaVinci Resolve, Premiere, CapCut) posent les
images sur la piste au-dessus de la vidéo aux instants indiqués.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from app.utils.service_log import LogEvent, slide_segments, to_srt


def _slug(value: str, limit: int = 40) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
    return value[:limit] or "slide"


def export_montage(
    events: list[LogEvent],
    folder: Path,
    obs_config: dict[str, Any] | None = None,
    *,
    origin: datetime | None = None,
    width: int = 1920,
    height: int = 1080,
) -> dict[str, Any]:
    """Écrit les PNG transparents, le SRT et le minutage ; renvoie un bilan."""
    from app.utils.obs_overlay_render import render_obs_overlay

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    segments = slide_segments(events)
    rendered: dict[tuple[str, str, str], str] = {}
    rows = []
    origin = origin or (segments[0][0] if segments else None)
    for start, stop, event in segments:
        key = (event.source, event.reference, event.text)
        name = rendered.get(key)
        if name is None:
            image = render_obs_overlay(
                obs_config or {},
                {"text": event.text, "reference": event.reference, "source": event.source},
                width,
                height,
            )
            if image is None:
                continue
            name = f"{len(rendered) + 1:03d}_{_slug(event.reference or event.text)}.png"
            image.save(folder / name)
            rendered[key] = name
        offset = (start - origin).total_seconds() if origin else 0.0
        rows.append([
            start.strftime("%H:%M:%S"),
            f"{max(0.0, offset):.1f}",
            f"{(stop - start).total_seconds():.1f}",
            name,
            event.reference.replace("\n", " "),
        ])
    with (folder / "minutage.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["Heure", "Début (s)", "Durée (s)", "Image", "Référence"])
        writer.writerows(rows)
    (folder / "sous-titres.srt").write_text(to_srt(events, origin), encoding="utf-8")
    return {"images": len(rendered), "segments": len(rows), "folder": str(folder)}


def load_obs_config(presentation_dir: Path | None) -> dict[str, Any]:
    if presentation_dir is None:
        return {}
    try:
        payload = json.loads((Path(presentation_dir) / "obs-config.json").read_text("utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError):
        return {}
