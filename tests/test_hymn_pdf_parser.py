from __future__ import annotations

from app.database.dao_hymns import HymnsDao
from app.utils.hymn_pdf_parser import (
    parse_hymns_from_lines,
    parse_stanza_sections,
)
from tools.import_swahili_hymns import Line, split_sections


def test_unicode_choeur_is_an_explicit_chorus() -> None:
    sections = parse_stanza_sections(
        [
            "Premier couplet,",
            "suite du couplet.",
            "",
            "Chœur :",
            "",
            "Le texte du refrain,",
            "sa deuxième ligne.",
            "",
            "Deuxième couplet.",
        ],
        repeat_single_chorus=False,
    )

    assert [section.label for section in sections] == [
        "Strophe 1",
        "Refrain",
        "Strophe 2",
    ]
    assert [section.is_chorus for section in sections] == [False, True, False]
    assert sections[1].text.startswith("Choeur:\nLe texte du refrain")
    assert HymnsDao._detect_chorus("Chœur : texte")


def test_single_chorus_is_repeated_after_each_verse_for_projection() -> None:
    sections = parse_stanza_sections(
        ["Premier couplet.", "", "Refrain", "Texte.", "", "Deuxième couplet."],
        repeat_single_chorus=True,
    )

    assert [section.is_chorus for section in sections] == [False, True, False, True]
    assert sections[1].text == sections[3].text


def test_lettered_hymn_numbers_are_preserved() -> None:
    hymns = parse_hymns_from_lines(
        [
            "116a",
            "PREMIER CHANT",
            "",
            "Premier texte.",
            "",
            "116b",
            "SECOND CHANT",
            "",
            "Second texte.",
        ],
        "CI",
    )

    assert [hymn.number for hymn in hymns] == ["CI-116A", "CI-116B"]


def test_swahili_italic_block_is_a_chorus() -> None:
    lines = [
        Line("1. Texte du premier couplet", 0, 0, 0, 0),
        Line("suite", 0, 10, 0, 0),
        Line("refrain en italique", 0, 30, 0, 0, is_italic=True),
        Line("suite du refrain", 0, 40, 0, 0, is_italic=True),
        Line("2. Texte du second couplet", 0, 60, 0, 0),
    ]

    sections = split_sections(lines)

    assert [section.label for section in sections] == [
        "Strophe 1",
        "Refrain",
        "Strophe 2",
    ]
    assert sections[1].is_chorus
    assert sections[1].text.startswith("Choeur:\nrefrain en italique")
