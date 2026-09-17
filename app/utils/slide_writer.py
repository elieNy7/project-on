from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from app.utils.models import Slide
from app.utils.text_utils import strip_hymn_projection_label


@dataclass(frozen=True)
class LiveSnapshot:
    """Complete public live state, restorable identically."""

    slide: Slide | None
    hidden: bool
    video_playing: bool
    video_loop: bool


class SlideWriter:
    def __init__(self, presentation_dir: Path) -> None:
        self._presentation_dir = presentation_dir
        self._slide_path = presentation_dir / "slide.json"
        self._hidden = False
        self._last_slide: Slide | None = None
        self._video_playing = False
        self._video_reset = False
        self._video_loop = False

    @property
    def slide_path(self) -> Path:
        return self._slide_path

    @property
    def is_hidden(self) -> bool:
        return self._hidden

    def set_hidden(self, hidden: bool) -> None:
        """Show or hide the text on projection and OBS."""
        self._hidden = hidden
        self._write_current()

    def toggle_hidden(self) -> bool:
        """Toggle visibility and return new state."""
        self._hidden = not self._hidden
        self._write_current()
        return self._hidden

    def write(self, slide: Slide) -> None:
        self._last_slide = slide
        # Une nouvelle slide repart en pause : la lecture vidéo est manuelle.
        self._video_playing = False
        self._write_current()

    def set_video_playing(self, playing: bool) -> None:
        """Commande play/pause pour la vidéo en direct (controlée par l'opérateur)."""
        self._video_playing = bool(playing)
        self._write_current()

    def set_video_reset(self) -> None:
        """Stop : remet la vidéo au début et en pause (une seule écriture)."""
        self._video_playing = False
        self._video_reset = True
        self._write_current()
        self._video_reset = False

    def set_video_loop(self, loop: bool) -> None:
        """Boucle : relance automatique de la vidéo à la fin."""
        self._video_loop = bool(loop)
        self._write_current()

    @property
    def video_loop(self) -> bool:
        return self._video_loop

    @property
    def video_playing(self) -> bool:
        return self._video_playing

    def snapshot(self) -> LiveSnapshot:
        """Capture the complete live state (slide, masking, video)."""
        return LiveSnapshot(
            slide=self._last_slide,
            hidden=self._hidden,
            video_playing=self._video_playing,
            video_loop=self._video_loop,
        )

    def restore(self, snapshot: LiveSnapshot) -> None:
        """Restore a state captured by :meth:`snapshot` exactly."""
        self._hidden = bool(snapshot.hidden)
        self._video_playing = bool(snapshot.video_playing)
        self._video_loop = bool(snapshot.video_loop)
        # Réécrit toujours la sortie : l'affichage distant (projection, OBS,
        # NDI) a pu rester sur les annonces, la restauration doit repousser
        # l'état capturé même s'il n'a pas changé en mémoire.
        self._last_slide = snapshot.slide
        # Reset is a one-shot command, not persistent playback state.
        self._video_reset = False
        self._write_current()

    def _write_current(self) -> None:
        self._presentation_dir.mkdir(parents=True, exist_ok=True)

        if self._hidden or self._last_slide is None:
            payload = {
                "reference": "",
                "text": "",
                "source": "",
                "background": "",
                "image": "",
                "video": "",
                "video_playing": False,
                "video_reset": False,
                "video_loop": self._video_loop,
                "hidden": True,
            }
        else:
            text = self._last_slide.text
            if self._last_slide.source == "hymn":
                text = strip_hymn_projection_label(text)
            has_video = bool(self._last_slide.video_path)
            payload = {
                "reference": self._last_slide.reference,
                "text": text,
                "source": self._last_slide.source,
                "background": self._last_slide.background or "",
                "image": self._last_slide.image_path or "",
                "video": self._last_slide.video_path or "",
                "video_playing": self._video_playing if has_video else False,
                "video_reset": self._video_reset if has_video else False,
                "video_loop": self._video_loop if has_video else False,
                "hidden": False,
            }

        tmp_path = self._slide_path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # Retry loop for Windows file locking
        for attempt in range(5):
            try:
                tmp_path.replace(self._slide_path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05)
