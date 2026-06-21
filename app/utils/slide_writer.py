from __future__ import annotations

import json
import time
from pathlib import Path

from app.utils.models import Slide
from app.utils.text_utils import strip_hymn_projection_label


class SlideWriter:
    def __init__(self, presentation_dir: Path) -> None:
        self._presentation_dir = presentation_dir
        self._slide_path = presentation_dir / "slide.json"
        self._hidden = False
        self._last_slide: Slide | None = None

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
                "hidden": True,
            }
        else:
            text = self._last_slide.text
            if self._last_slide.source == "hymn":
                text = strip_hymn_projection_label(text)
            payload = {
                "reference": self._last_slide.reference,
                "text": text,
                "source": self._last_slide.source,
                "background": self._last_slide.background or "",
                "image": self._last_slide.image_path or "",
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
