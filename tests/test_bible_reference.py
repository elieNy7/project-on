from __future__ import annotations

import pytest

from app.utils.bible_reference import parse_reference

BOOKS = [
    {"id": 1, "name": "Genèse"},
    {"id": 19, "name": "Psaume"},
    {"id": 23, "name": "Ésaïe"},
    {"id": 24, "name": "Jérémie"},
    {"id": 43, "name": "Jean"},
    {"id": 46, "name": "1 Corinthiens"},
    {"id": 47, "name": "2 Corinthiens"},
    {"id": 62, "name": "1 Jean"},
]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Jean 3:16", (43, 3, 16)),
        ("jean 3 16", (43, 3, 16)),
        ("Jean 3.16", (43, 3, 16)),
        ("Jean 3", (43, 3, None)),
        ("1 Jean 4:8", (62, 4, 8)),
        ("1jean 4", (62, 4, None)),
        ("1 co 13", (46, 13, None)),
        ("2 Cor 5:17", (47, 5, 17)),
        ("esaie 53:5", (23, 53, 5)),
        ("Ps 23", (19, 23, None)),
        ("  genese 1 1 ", (1, 1, 1)),
    ],
)
def test_parses_references(query, expected) -> None:
    ref = parse_reference(query, BOOKS)
    assert ref is not None
    assert (ref.book_id, ref.chapter, ref.verse) == expected


@pytest.mark.parametrize("query", ["", "lumière", "3:16", "J 3", "Xyz 3", "Jean"])
def test_rejects_non_references(query) -> None:
    assert parse_reference(query, BOOKS) is None


def test_label_uses_book_name() -> None:
    assert parse_reference("jea 3:16", BOOKS).label == "Jean 3:16"


def test_ambiguous_prefix_takes_canonical_order() -> None:
    # "je" fits Jérémie and Jean: the earlier book in the canon wins.
    assert parse_reference("je 3", BOOKS).book_name == "Jérémie"
    # Abbreviations must be a prefix of the name ("jn" is not).
    assert parse_reference("jn 3", BOOKS) is None
