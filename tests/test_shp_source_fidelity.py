"""SHP sermons: faithful to the PDF (title, place, date, alineas, numbering)."""

from __future__ import annotations

from app.database.connection import Database
from app.database.dao_sermons import SermonsDao
from tools.import_shp_collections import (
    BannerLine,
    ExtractedParagraph,
    ExtractedSermon,
    FileExtraction,
    apply_import,
    marker_gaps,
    parse_banner_metadata,
    printed_banner_date,
    recover_inline_markers,
    split_header_fields,
    starts_alinea,
    _date_code,
)


def _lines(*values: str) -> list[BannerLine]:
    return [BannerLine(value, 1, 100.0 + index * 20) for index, value in enumerate(values)]


# -- Title / place / date -----------------------------------------------------


def test_header_fields_split_on_wide_gaps_only() -> None:
    assert split_header_fields(
        "ALLUMEZ  LA  LUMIERE     PHOENIX AZ USA    Sam 25.01.64"
    ) == ("ALLUMEZ LA LUMIERE", "PHOENIX AZ USA")


def test_header_wrapped_inside_the_location() -> None:
    # Two blue lines "…ETERNELLEMENT     EDMONTON AB" / "CANADA    Ven 27.10.52"
    # are joined by a single space: the place stays whole.
    raw = "JESUS-CHRIST EST LE MEME     EDMONTON AB CANADA    Ven 27.10.52"
    assert split_header_fields(raw) == ("JESUS-CHRIST EST LE MEME", "EDMONTON AB CANADA")


def test_banner_title_with_double_spaces_stays_whole() -> None:
    raw = "ALLUMEZ  LA  LUMIERE     PHOENIX AZ USA    Sam 25.01.64"
    title, location, code = parse_banner_metadata(
        _lines("ALLUMEZ  LA  LUMIERE", "PHOENIX AZ USA       Sam 25.01.64"),
        "ALLUMEZ LA LUMIERE PHOENIX AZ USA Sam 25.01.64",
        raw,
    )
    assert (title, location, code) == ("ALLUMEZ LA LUMIERE", "PHOENIX AZ USA", "64-0125")


def test_banner_location_on_its_own_lines() -> None:
    raw = (
        "L’AIGLE QUI EVEILLE SA COUVEE     REGION DE LA NOUVELLE ANGLETERRE  USA"
        "    00.05.58"
    )
    title, location, _ = parse_banner_metadata(
        _lines(
            "L’AIGLE QUI EVEILLE SA COUVEE",
            "REGION DE LA NOUVELLE ANGLETERRE  USA",
            "00.05.58",
        ),
        "L’AIGLE QUI EVEILLE SA COUVEE REGION DE LA NOUVELLE ANGLETERRE USA 00.05.58",
        raw,
    )
    assert title == "L’AIGLE QUI EVEILLE SA COUVEE"
    assert location == "REGION DE LA NOUVELLE ANGLETERRE USA"


def test_banner_keeps_its_own_spelling_and_punctuation() -> None:
    # The banner is the reference; the repeated header only places the cut.
    raw = "CROIS-TU CELA ?     HOUSTON TX USA    Dim 15.01.50"
    title, location, _ = parse_banner_metadata(
        _lines("CROIS-TU CELA ?", "HOUSTON TX USA       Dim 15.01.50"),
        "CROIS-TU CELA ? HOUSTON TX USA Dim 15.01.50",
        raw,
    )
    assert (title, location) == ("CROIS-TU CELA ?", "HOUSTON TX USA")


def test_printed_date_is_taken_verbatim_from_the_banner() -> None:
    _, header_match = _date_code("X Y Sam 12.04.47")
    banner = _lines("LA FOI EST UNE FERME ASSURANCE", "OAKLAND CA USA       Sam 12.04.47")
    assert printed_banner_date(banner, header_match) == "Sam 12.04.47"
    _, header_match = _date_code("LIGNE DE PRIERE (Lieu inconnu) 00.00.48")
    assert printed_banner_date(_lines("LIGNE DE PRIERE", "00.00.48"), header_match) == "00.00.48"


def test_display_title_changes_case_only() -> None:
    assert Database.title_case_words("L’ANGE DE DIEU") == "L’Ange De Dieu"
    assert Database.title_case_words("QU’Y A-T-Il DANS TA MAIN ?") == "Qu’Y A-t-il Dans Ta Main ?"
    assert (
        Database.title_case_words("JESUS-CHRIST EST LE MEME HIER, AUJOURD’HUI")
        == "Jesus-Christ Est Le Meme Hier, Aujourd’hui"
    )
    assert Database.title_case_words("LE SCEAU II") == "Le Sceau II"
    assert Database.title_case_words("Déjà en casse mixte") == "Déjà en casse mixte"


def test_display_location_keeps_codes() -> None:
    assert Database.display_location("OAKLAND CA USA") == "Oakland CA USA"
    assert Database.display_location("DAWSON CREEK BC CANADA") == "Dawson Creek BC Canada"
    assert Database.display_location("JOHANNESBURG AFRIQUE DU SUD") == "Johannesburg Afrique Du Sud"
    assert Database.display_location("(Lieu inconnu)") == "(Lieu inconnu)"


# -- Alineas and numbering ----------------------------------------------------


def test_alinea_indents() -> None:
    assert not starts_alinea(72.0)  # continuation line
    assert starts_alinea(79.0)  # new alinea
    assert starts_alinea(143.0)  # scripture reading
    assert not starts_alinea(115.0)  # scripture reading, continued


def _paragraph(marker: str, *alineas: str) -> ExtractedParagraph:
    return ExtractedParagraph(marker, "\n".join(alineas), 1, 1, tuple(alineas))


def _sermon(*paragraphs: ExtractedParagraph) -> ExtractedSermon:
    return ExtractedSermon(
        title="T", location="L", date_code="50-0810", header="T L 10.08.50",
        source_path="shp/50/50.pdf", source_page=1, paragraphs=list(paragraphs),
    )


def test_paragraph_swallowed_by_previous_one_is_recovered() -> None:
    sermon = _sermon(
        _paragraph("5", "Premier alinéa.", "Ça ne l’est pas. Je crois…6. Quelqu’un m’a dit.", "Suite."),
        _paragraph("7", "Septième."),
    )
    assert recover_inline_markers(sermon) == ["6"]
    assert [p.marker for p in sermon.paragraphs] == ["5", "6", "7"]
    assert sermon.paragraphs[0].parts == ("Premier alinéa.", "Ça ne l’est pas. Je crois…")
    assert sermon.paragraphs[1].parts == ("Quelqu’un m’a dit.", "Suite.")
    assert marker_gaps(sermon) == []


def test_numbers_that_do_not_fill_a_gap_stay_in_the_text() -> None:
    sermon = _sermon(
        _paragraph("8", "Lisons 2 Rois chapitre 4. Et elle fit seller l’ânesse."),
        _paragraph("10", "Dix."),
    )
    assert recover_inline_markers(sermon) == []
    assert marker_gaps(sermon) == ["8>10"]


# -- Database -----------------------------------------------------------------


def test_import_stores_alineas_and_printed_fields(db) -> None:
    with db.connect() as connection:
        connection.execute("DELETE FROM sermon_paragraph")
        connection.execute("DELETE FROM sermon")
        connection.execute(
            "INSERT INTO sermon (id, title, date, tradition, language) "
            "VALUES (1, 'EXPOSE', 'BK-AGES-CH01', 'VGR', 'fr')"
        )
        connection.execute(
            "INSERT INTO sermon_paragraph (sermon_id, paragraph_no, ref, text, marker) "
            "VALUES (1, 1, 'EXPOSE §1', 'Texte', '§1')"
        )
    sermon = ExtractedSermon(
        title="L’ANGE DE DIEU", location="PHOENIX AZ USA", date_code="47-1102",
        header="L’ANGE DE DIEU PHOENIX AZ USA Dim 02.11.47", source_path="shp/47/47.pdf",
        source_page=3, printed_date="Dim 02.11.47",
        paragraphs=[_paragraph("1", "Premier.", "Deuxième alinéa."), _paragraph("2", "Suite.")],
    )
    result = FileExtraction("shp/47/47.pdf", 1, [sermon], [], 0.0)

    applied = apply_import(db.db_path, [result], backup_dir=None, vacuum=False)

    assert applied["shp_paragraphs"] == 3
    with db.connect() as connection:
        row = connection.execute(
            "SELECT title, canonical_title, location, printed_location, printed_date "
            "FROM sermon WHERE tradition = 'SHP'"
        ).fetchone()
        assert tuple(row) == (
            "L’ANGE DE DIEU", "L’Ange De Dieu", "Phoenix AZ USA", "PHOENIX AZ USA", "Dim 02.11.47",
        )
        rows = connection.execute(
            "SELECT p.marker, p.text FROM sermon_paragraph p JOIN sermon s ON s.id = p.sermon_id "
            "WHERE s.tradition = 'SHP' ORDER BY p.paragraph_no"
        ).fetchall()
        assert [tuple(r) for r in rows] == [
            ("§1", "Premier."), ("§1", "Deuxième alinéa."), ("§2", "Suite."),
        ]
    listed = SermonsDao(db).list_sermons(translator="SHP")
    assert listed[0]["printed_date"] == "Dim 02.11.47"
    assert listed[0]["title"] == "L’Ange De Dieu"


# -- Phrase search ------------------------------------------------------------


def test_fts_query_supports_exact_phrases() -> None:
    assert SermonsDao._fts_query('foi "ferme assurance"') == 'foi* "ferme assurance"'
    assert SermonsDao._fts_query("« la Parole parlée »") == '"la parole parlee"'


def test_phrase_search_matches_only_the_exact_expression(db) -> None:
    with db.connect() as connection:
        connection.execute("DELETE FROM sermon_paragraph")
        connection.execute("DELETE FROM sermon")
        connection.execute(
            "INSERT INTO sermon (id, title, date, tradition, language) "
            "VALUES (1, 'S', '60-0101', 'SHP', 'fr')"
        )
        connection.executemany(
            "INSERT INTO sermon_paragraph (sermon_id, paragraph_no, ref, text, marker) "
            "VALUES (1, ?, 'S', ?, ?)",
            [
                (1, "La foi est une ferme assurance.", "§1"),
                (2, "Une assurance ferme dans la foi.", "§2"),
            ],
        )
        connection.execute("DROP TABLE IF EXISTS sermon_paragraph_fts")
        db._ensure_sermon_fts(connection)
    dao = SermonsDao(db)
    exact = dao.search_paragraphs('"ferme assurance"', language="fr", substring_fallback=False)
    words = dao.search_paragraphs("ferme assurance", language="fr", substring_fallback=False)
    assert [hit["marker"] for hit in exact] == ["§1"]
    assert sorted(hit["marker"] for hit in words) == ["§1", "§2"]
