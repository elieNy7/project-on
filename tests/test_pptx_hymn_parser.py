from __future__ import annotations

from app.utils.pptx_parser import parse_slides_as_hymn
from tools.import_cantique_adoration_folder import clean_source_title


def test_repeated_block_inside_verse_slides_becomes_chorus() -> None:
    hymn = parse_slides_as_hymn(
        [
            "CHANT\nPremier couplet\nDeuxième ligne\nVoici notre refrain commun\nNous le chantons encore",
            "Second couplet\nAutre ligne\nVoici notre refrain commun\nNous le chantons encore",
            "Troisième couplet\nDernière ligne\nVoici notre refrain commun\nNous le chantons encore",
        ],
        "CHANT",
    )

    assert hymn is not None
    assert [section["is_chorus"] for section in hymn["sections"]] == [
        False,
        True,
        False,
        True,
        False,
        True,
    ]
    assert hymn["sections"][0]["text"] == "Premier couplet\nDeuxième ligne"
    assert "refrain commun" in hymn["sections"][1]["text"]


def test_multiple_explicit_choruses_keep_original_order() -> None:
    hymn = parse_slides_as_hymn(
        [
            "Couplet français",
            "Chœur: Refrain français",
            "Couplet lingala",
            "ChœurAlleluya, refrain lingala",
        ],
        "Cantique bilingue",
    )

    assert hymn is not None
    assert [section["is_chorus"] for section in hymn["sections"]] == [
        False,
        True,
        False,
        True,
    ]
    assert "Refrain français" in hymn["sections"][1]["text"]
    assert "refrain lingala" in hymn["sections"][3]["text"]


def test_source_title_removes_powerpoint_copy_noise() -> None:
    assert (
        clean_source_title(
            "Comment te louer [Lecture seule][Compatibility Mode] (2)"
        )
        == "Comment te louer"
    )
