from __future__ import annotations

from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv", ".avi"}
POWERPOINT_EXTENSIONS = {".pptx", ".ppsx"}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | POWERPOINT_EXTENSIONS

# File-dialog filter for background pickers (images only).
BACKGROUND_FILE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"

# File-dialog filters for the Media library.
IMAGE_FILE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"
VIDEO_FILE_FILTER = "Vidéos (*.mp4 *.webm *.mov *.mkv *.avi)"
POWERPOINT_FILE_FILTER = "Présentations PowerPoint (*.pptx *.ppsx)"
MEDIA_FILE_FILTER = (
    "Médias (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.mp4 *.webm *.mov *.mkv *.avi)"
)


def is_image_file(path: str | Path | None) -> bool:
    if not path:
        return False
    try:
        return Path(str(path)).suffix.lower() in IMAGE_EXTENSIONS
    except Exception:
        return False


def is_video_file(path: str | Path | None) -> bool:
    if not path:
        return False
    try:
        return Path(str(path)).suffix.lower() in VIDEO_EXTENSIONS
    except Exception:
        return False


def is_powerpoint_file(path: str | Path | None) -> bool:
    if not path:
        return False
    try:
        return Path(str(path)).suffix.lower() in POWERPOINT_EXTENSIONS
    except Exception:
        return False


def is_media_file(path: str | Path | None) -> bool:
    return is_image_file(path) or is_video_file(path) or is_powerpoint_file(path)


def media_kind(path: str | Path | None) -> str:
    """« image », « video » ou « powerpoint » selon l'extension."""
    if is_video_file(path):
        return "video"
    if is_powerpoint_file(path):
        return "powerpoint"
    return "image"
