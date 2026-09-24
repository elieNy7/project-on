"""Global search across the libraries (Bible, sermons, Exposé, media,
playlists — hymns are deliberately left out). Pure data layer: runs in a worker thread and returns plain dicts
that the UI lists and the library controller knows how to reveal.

Each hit: {"kind", "title", "subtitle", ...navigation payload}.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable

from app.utils.bible_reference import _REFERENCE, parse_reference
from app.utils.text_utils import unaccent

log = logging.getLogger(__name__)

# Display order of the result groups.
KINDS = ("bible", "sermon", "expose", "media", "playlist")

KIND_LABELS = {
    "bible": "Bible",
    "sermon": "Prédications",
    "expose": "Exposés",
    "media": "Médias",
    "playlist": "Playlists",
}

MIN_QUERY = 2  # titles, references, names
MIN_TEXT_QUERY = 3  # full-text searches in verses, stanzas, paragraphs


@dataclass
class SearchContext:
    """Library state the search must respect (current translation, etc.)."""

    bible_translation_id: int | None = None
    sermon_language: str = "fr"
    sermon_translator: str | None = None
    expose_translator: str = "VGR"
    per_kind: int = 5


@dataclass
class SearchDeps:
    db: Any
    bible_dao: Any
    sermons_dao: Any
    media_dao: Any
    playlist_dao: Any


def warm_up(deps: SearchDeps, ctx: SearchContext) -> None:
    """Build the verse index ahead of the first keystroke."""
    if ctx.bible_translation_id is not None:
        _guard("bible", lambda: _verses_for(deps.db, int(ctx.bible_translation_id)))


def looks_like_reference(query: str) -> bool:
    """"Ps 23", "Jean 3:16": skip paragraph full-text search (pure noise)."""
    return _REFERENCE.match(str(query or "")) is not None


# Accent-free verse index per translation, built once in a worker thread:
# a Python unaccent() UDF over ~31k rows per query costs up to a second.
_verse_index: dict[int, list[tuple[int, int, int, str, str]]] = {}
_verse_index_lock = threading.Lock()


def _verses_for(db, translation_id: int) -> list[tuple[int, int, int, str, str]]:
    with _verse_index_lock:
        cached = _verse_index.get(translation_id)
        if cached is not None:
            return cached
        with db.connect() as conn:
            rows = conn.execute(
                """
                SELECT book, chapter, verse, text
                FROM bible_translation_verse
                WHERE translation_id = ?
                ORDER BY book, chapter, verse
                """,
                (int(translation_id),),
            ).fetchall()
        index = [
            (int(r[0]), int(r[1]), int(r[2]), str(r[3] or ""), unaccent(str(r[3] or "")).lower())
            for r in rows
        ]
        _verse_index[translation_id] = index
        return index


def _one_line(text: Any, limit: int = 140) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _guard(kind: str, fn) -> list[dict[str, Any]]:
    """One failing library must not hide the results of the others."""
    try:
        return fn()
    except Exception:
        log.exception("Recherche globale : échec de la source %s", kind)
        return []


def search_bible(bible_dao, db, query: str, ctx: SearchContext) -> list[dict[str, Any]]:
    tid = ctx.bible_translation_id
    hits: list[dict[str, Any]] = []
    books = bible_dao.list_translation_books(tid) if tid is not None else bible_dao.list_books()

    ref = parse_reference(query, books)
    if ref is not None:
        text = ""
        if ref.verse is not None and tid is not None:
            for v in bible_dao.list_translation_verses(tid, ref.book_id, ref.chapter):
                if int(v["verse"]) == ref.verse:
                    text = str(v["text"])
                    break
        hits.append(
            {
                "kind": "bible",
                "title": ref.label,
                "subtitle": _one_line(text) if text else "Ouvrir le chapitre",
                "book_id": ref.book_id,
                "chapter": ref.chapter,
                "verse": ref.verse,
            }
        )
        return hits

    if tid is None or len(query.strip()) < MIN_TEXT_QUERY:
        return hits
    names = {int(b["id"]): str(b.get("name", "")) for b in books}
    needle = unaccent(" ".join(query.split())).lower()
    for book, chapter, verse, text, folded in _verses_for(db, int(tid)):
        if needle in folded:
            hits.append(
                {
                    "kind": "bible",
                    "title": f"{names.get(book, book)} {chapter}:{verse}",
                    "subtitle": _one_line(text),
                    "book_id": book,
                    "chapter": chapter,
                    "verse": verse,
                }
            )
            if len(hits) >= ctx.per_kind:
                break
    return hits


def search_sermons(sermons_dao, query: str, ctx: SearchContext) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    q = query.strip()
    for s in sermons_dao.list_sermons(
        language=ctx.sermon_language,
        title_query=q,
        translator=ctx.sermon_translator,
        limit=ctx.per_kind,
    ):
        date = str(s.get("printed_date") or s.get("date_code") or s.get("date") or "")
        hits.append(
            {
                "kind": "sermon",
                "title": str(s.get("title") or ""),
                "subtitle": f"Prédication · {date}" if date else "Prédication",
                "sermon_id": s["id"],
                "query": None,
            }
        )

    if len(q) >= MIN_TEXT_QUERY and not looks_like_reference(q):
        for p in sermons_dao.search_paragraphs(
            q,
            language=ctx.sermon_language,
            translator=ctx.sermon_translator,
            limit=ctx.per_kind,
            substring_fallback=False,
        ):
            marker = str(p.get("marker") or p.get("para_id") or "")
            hits.append(
                {
                    "kind": "sermon",
                    "title": f"{p.get('sermon_title', '')} {marker}".strip(),
                    "subtitle": _one_line(p.get("text")),
                    "sermon_id": p.get("sermon_id"),
                    "marker": marker,
                    "query": q,
                }
            )
    return hits


def search_expose(sermons_dao, query: str, ctx: SearchContext) -> list[dict[str, Any]]:
    q = query.strip()
    if len(q) < MIN_TEXT_QUERY or looks_like_reference(q):
        return []
    hits = []
    for p in sermons_dao.search_expose(q, translator=ctx.expose_translator, limit=ctx.per_kind):
        ref = str(p.get("reference") or p.get("ref") or "")
        hits.append(
            {
                "kind": "expose",
                "title": ref or str(p.get("title") or "Exposé"),
                "subtitle": _one_line(p.get("text")),
                "reference": ref,
                "query": q,
            }
        )
    return hits


def _name_hits(rows, kind: str, id_key: str, query: str, ctx: SearchContext, subtitle) -> list[dict]:
    needle = unaccent(query.strip()).lower()
    hits = []
    for row in rows:
        name = str(row.get("name") or "")
        if needle in unaccent(name).lower():
            hits.append({"kind": kind, "title": name, "subtitle": subtitle(row), id_key: int(row["id"])})
            if len(hits) >= ctx.per_kind:
                break
    return hits


def _media_subtitle(row: dict[str, Any]) -> str:
    return {"image": "Image", "video": "Vidéo", "pptx": "Présentation"}.get(
        str(row.get("kind")), "Média"
    )


SOURCES: dict[str, Callable[[SearchDeps, str, SearchContext], list[dict[str, Any]]]] = {
    "bible": lambda d, q, c: search_bible(d.bible_dao, d.db, q, c),
    "sermon": lambda d, q, c: search_sermons(d.sermons_dao, q, c),
    "expose": lambda d, q, c: search_expose(d.sermons_dao, q, c),
    "media": lambda d, q, c: _name_hits(
        d.media_dao.list_media(), "media", "media_id", q, c, _media_subtitle
    ),
    "playlist": lambda d, q, c: _name_hits(
        d.playlist_dao.list_folders(), "playlist", "folder_id", q, c, lambda _r: "Playlist"
    ),
}


def search_source(kind: str, deps: SearchDeps, query: str, ctx: SearchContext) -> list[dict[str, Any]]:
    """Hits of one library; never raises (a failing source yields nothing)."""
    q = str(query or "").strip()
    if len(q) < MIN_QUERY:
        return []
    return _guard(kind, lambda: SOURCES[kind](deps, q, ctx))


def run_global_search(deps: SearchDeps, query: str, ctx: SearchContext) -> list[dict[str, Any]]:
    """All hits, grouped in KINDS order (sequential; the UI runs sources in
    parallel through search_source)."""
    return [hit for kind in KINDS for hit in search_source(kind, deps, query, ctx)]
