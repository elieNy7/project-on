from __future__ import annotations

COMPACT_PREVIEW_MAX_CHARS = 160
COMPACT_PREVIEW_MAX_CHARS_SEARCH = 140
COMPACT_PREVIEW_BOX_HEIGHT = 140


def normalize_preview_text(text: str) -> str:
    return " ".join(str(text or "").split())


def truncate_preview(text: str, limit: int = COMPACT_PREVIEW_MAX_CHARS) -> str:
    clean = normalize_preview_text(text)
    if len(clean) <= limit:
        return clean
    return clean[:limit] + "..."
