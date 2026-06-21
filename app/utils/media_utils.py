from __future__ import annotations

from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}

# File-dialog filter for background pickers (images only).
BACKGROUND_FILE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"


def is_image_file(path: str | Path | None) -> bool:
    if not path:
        return False
    try:
        return Path(str(path)).suffix.lower() in IMAGE_EXTENSIONS
    except Exception:
        return False
