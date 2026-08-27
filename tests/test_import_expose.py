"""Tests de l'extraction Exposé VGR : fusion de la lecture biblique d'ouverture.

La lecture (référence « Apocalypse x.y-z » + versets imprimés) doit former un
seul paragraphe ; les titres de section collés (« … aux Églises. SARDES »)
doivent être purgés ; les chapitres sans lecture ne doivent pas être touchés.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "expose"))

from import_expose import (  # noqa: E402
    _is_section_heading_fragment,
    _merge_opening_reading,
    _reading_verse_cap,
    _strip_trailing_section_heading,
)


def _paras(*texts: str):
    return [(f"p{11 + i}-1", text) for i, text in enumerate(texts)]


def test_verse_cap_from_reference() -> None:
    assert _reading_verse_cap("Apocalypse 2.8-11") == 4
    assert _reading_verse_cap("Apocalypse 3.14-22") == 9
    assert _reading_verse_cap("Apocalypse 1.9-20") == 12
    assert _reading_verse_cap("Apocalypse 3.7") == 1
    assert _reading_verse_cap("Le présent volume") is None


def test_strip_trailing_section_heading() -> None:
    assert _strip_trailing_section_heading(
        "Que celui qui a des oreilles entende ce que l'Esprit dit aux Églises. SARDES"
    ) == "Que celui qui a des oreilles entende ce que l'Esprit dit aux Églises."
    # Un verset finissant légitimement sur un mot capitalisé est préservé
    assert _strip_trailing_section_heading(
        "les sept chandeliers sont les sept Églises."
    ) == "les sept chandeliers sont les sept Églises."
    # Sans ponctuation finale, on ne retire rien
    assert _strip_trailing_section_heading(
        "dit aux Églises SARDES"
    ) == "dit aux Églises SARDES"


def test_section_heading_fragment() -> None:
    assert _is_section_heading_fragment("SARDES")
    assert _is_section_heading_fragment("aux Âges de l'Église")
    assert not _is_section_heading_fragment(
        "Sardes était la capitale de l'ancienne Lydie."
    )


def test_merge_reading_with_reference_and_cap() -> None:
    paras = _paras(
        "Apocalypse 3.1-6",
        "Écris à l'ange de l'Église de Sardes: Voici ce que dit Celui qui a les "
        "sept Esprits de Dieu.",
        "Sois vigilant, et affermis le reste qui est près de mourir.",
        "Rappelle-toi donc comment tu as reçu et entendu.",
        "Cependant, tu as à Sardes quelques hommes qui n'ont pas souillé leurs "
        "vêtements.",
        "Celui qui vaincra sera revêtu ainsi de vêtements blancs.",
        "Que celui qui a des oreilles entende ce que l'Esprit dit aux Églises. SARDES",
        "Sardes était la capitale de l'ancienne Lydie. Elle passa des mains des "
        "monarques lydiens à celles des Perses, puis fut détruite par un "
        "tremblement de terre terrible au cours de la nuit de 17 après "
        "Jésus-Christ, et rebâtie par Alexandre le Grand qui la restaura selon "
        "son plan initial d'origine.",
    )
    merged = _merge_opening_reading(paras)
    assert len(merged) == 2
    reading = merged[0][1]
    assert reading.startswith("Apocalypse 3.1-6")
    assert reading.endswith("dit aux Églises.")  # « SARDES » purgé
    assert "SARDES" not in reading
    assert merged[1][1].startswith("Sardes était la capitale")


def test_merge_stops_on_long_commentary_without_full_cap() -> None:
    # La référence annonce 12 versets (1.9-20) mais un seul est cité : le
    # commentaire, plus long qu'un verset, arrête la fusion.
    commentary = "Cette série de visions a été donnée à Jean pendant " * 10
    paras = _paras(
        "Apocalypse 1.9-20 Jean à Patmos",
        "Apocalypse 1.9: «Moi Jean, votre frère, et qui ai part avec vous à la "
        "tribulation.»",
        commentary,
        "Suite du commentaire.",
    )
    merged = _merge_opening_reading(paras)
    assert len(merged) == 3
    assert merged[0][1].startswith("Apocalypse 1.9-20")
    assert merged[1][1] == commentary


def test_merge_chapter_one_numbered_verses() -> None:
    verses = [
        "1 “Révélation de Jésus-Christ, que Dieu lui a donnée.",
        "2 lequel a attesté la Parole de Dieu.",
    ]
    unnumbered = [
        "Je fus ravi en Esprit au jour du Seigneur.",
        "et, au milieu des sept chandeliers, quelqu'un qui ressemblait au Fils "
        "de l'Homme.",
    ]
    commentary = "Apocalypse 1.1-3: “Révélation de Jésus-Christ, que Dieu lui " * 12
    paras = _paras(*verses, *unnumbered, commentary)
    merged = _merge_opening_reading(paras)
    assert len(merged) == 2
    reading = merged[0][1]
    assert reading.startswith("1 “Révélation")
    assert reading.endswith("de l'Homme.")
    assert merged[1][1] == commentary


def test_no_merge_without_reading_block() -> None:
    # Chapitre 3 : le commentaire suit directement le titre de section.
    paras = _paras(
        "aux Âges de l'Église",
        "Pour que vous puissiez pleinement comprendre le message des Âges.",
    )
    assert _merge_opening_reading(paras) == paras
    # Chapitre 10 : commentaire direct.
    paras = _paras(
        "Notre étude ayant consisté en un exposé verset par verset.",
        "L'étude que nous avons menée nous a appris.",
    )
    assert _merge_opening_reading(paras) == paras
    # Liste vide.
    assert _merge_opening_reading([]) == []
