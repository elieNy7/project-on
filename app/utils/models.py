from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SourceType = Literal["bible", "sermon", "hymn", "custom", "image"]


@dataclass(frozen=True)
class Slide:
    source: SourceType
    reference: str
    text: str
    background: str | None = None
    image_path: str | None = None
