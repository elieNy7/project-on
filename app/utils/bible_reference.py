"""Parse Bible references typed by the operator ("Jean 3:16", "1 co 13",
"esaie 53.5", "Ps 23") against the book names of a translation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from app.utils.text_utils import unaccent

# "<book> <chapter>[ :.,space <verse>]" — the book may start with 1-3.
_REFERENCE = re.compile(
    r"^\s*(?P<book>(?:[1-3]\s*)?[^\d\s][^\d]*?)\s*"
    r"(?P<chapter>\d{1,3})"
    r"(?:\s*[:.,\s]\s*(?P<verse>\d{1,3}))?\s*$"
)


@dataclass(frozen=True)
class BibleReference:
    book_id: int
    book_name: str
    chapter: int
    verse: int | None = None

    @property
    def label(self) -> str:
        base = f"{self.book_name} {self.chapter}"
        return f"{base}:{self.verse}" if self.verse is not None else base


def _key(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", unaccent(str(text)).lower())


def match_book(query: str, books: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    """Exact name first, then the first book (canonical order) whose name
    starts with the typed prefix. At least two letters are required."""
    wanted = _key(query)
    if len(re.sub(r"\d", "", wanted)) < 2:
        return None
    candidates = list(books)
    for book in candidates:
        if _key(book.get("name", "")) == wanted:
            return book
    for book in candidates:
        if _key(book.get("name", "")).startswith(wanted):
            return book
    return None


def parse_reference(query: str, books: Iterable[dict[str, Any]]) -> BibleReference | None:
    match = _REFERENCE.match(str(query or ""))
    if not match:
        return None
    book = match_book(match.group("book"), books)
    if book is None:
        return None
    chapter = int(match.group("chapter"))
    verse = match.group("verse")
    if chapter < 1:
        return None
    return BibleReference(
        book_id=int(book["id"]),
        book_name=str(book.get("name", "")).strip(),
        chapter=chapter,
        verse=int(verse) if verse else None,
    )
