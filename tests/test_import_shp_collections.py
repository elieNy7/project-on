from __future__ import annotations

from tools.import_shp_collections import (
    BannerLine,
    ExtractedParagraph,
    ExtractedSermon,
    FileExtraction,
    _date_code,
    apply_import,
    parse_banner_metadata,
    parse_paragraph_start,
)


def _lines(*values: str) -> list[BannerLine]:
    return [BannerLine(value, 1, 100.0 + index * 20) for index, value in enumerate(values)]


def test_parse_banner_with_wrapped_title_and_location() -> None:
    header = (
        "POURQUOI LES GENS SONT SI BALLOTES? OU LE VOILE INTERIEUR "
        "JEFFERSONVILLE IN USA Dim 01.01.56"
    )
    title, location, code = parse_banner_metadata(
        _lines(
            "POURQUOI LES GENS SONT SI BALLOTES? OU LE VOILE",
            "INTERIEUR                                               JEFFERSONVILLE IN",
            "USA       Dim 01.01.56",
        ),
        header,
    )

    assert title == "POURQUOI LES GENS SONT SI BALLOTES? OU LE VOILE INTERIEUR"
    assert location == "JEFFERSONVILLE IN USA"
    assert code == "56-0101"


def test_parse_banner_with_unknown_day_and_wrapped_location() -> None:
    title, location, code = parse_banner_metadata(
        _lines(
            "LA COMMUNION                                               PHOENIX AZ",
            "USA       00.11.47",
        ),
        "LA COMMUNION PHOENIX AZ USA 00.11.47",
    )

    assert title == "LA COMMUNION"
    assert location == "PHOENIX AZ USA"
    assert code == "47-1100"


def test_date_code_keeps_service_suffix() -> None:
    code, _ = _date_code("CEREMONIE DE MARIAGE TUCSON AZ USA Sam 16.01.65X")

    assert code == "65-0116X"


def test_date_code_accepts_missing_pdf_separator() -> None:
    code, match = _date_code("LES CONFERENCES PHOENIX AZ USA Dim 28.02 60")

    assert code == "60-0228"
    assert match.group("year_sep") == " "


def test_paragraph_marker_ignores_overlaid_page_number() -> None:
    assert parse_paragraph_start("9. 11. Et la meme Lumiere", "11") == (
        "11",
        "Et la meme Lumiere",
    )


def test_paragraph_marker_preserves_letter_suffix() -> None:
    assert parse_paragraph_start("26b. Une tres douce petite", "26b") == (
        "26b",
        "Une tres douce petite",
    )


def test_paragraph_marker_accepts_space_before_dot() -> None:
    assert parse_paragraph_start("136 .Je ne pense pas", "136") == (
        "136",
        "Je ne pense pas",
    )


def test_paragraph_marker_accepts_missing_dot_when_isolated() -> None:
    assert parse_paragraph_start("1", None) == ("1", "")


def test_apply_import_preserves_vgr_bss_and_expose(db) -> None:
    marker = f"{chr(0xA7)}1"
    with db.connect() as connection:
        connection.execute("DELETE FROM sermon_paragraph")
        connection.execute("DELETE FROM sermon")
        rows = [
            (101, "EXPOSE", "BK-AGES-CH01", "VGR"),
            (102, "SERMON VGR", "60-0101", "VGR"),
            (103, "SERMON BSS", "60-0102", "BSS"),
        ]
        connection.executemany(
            """
            INSERT INTO sermon
                (id, title, date, tradition, language, source_path, sort_key,
                 location, canonical_title, title_search)
            VALUES (?, ?, ?, ?, 'fr', '', '', '', '', '')
            """,
            rows,
        )
        connection.executemany(
            """
            INSERT INTO sermon_paragraph
                (sermon_id, paragraph_no, ref, text, marker)
            VALUES (?, 1, ?, ?, ?)
            """,
            [
                (101, f"EXPOSE {marker}", "Texte expose", marker),
                (102, f"SERMON VGR {marker}", "Texte VGR", marker),
                (103, f"SERMON BSS {marker}", "Texte BSS", marker),
            ],
        )

    result = FileExtraction(
        source_path="shp/60/60.pdf",
        page_count=1,
        warnings=[],
        elapsed_seconds=0.0,
        sermons=[
            ExtractedSermon(
                title="SERMON SHP",
                location="PHOENIX AZ USA",
                date_code="60-0103",
                header="SERMON SHP PHOENIX AZ USA Dim 03.01.60",
                source_path="shp/60/60.pdf",
                source_page=1,
                paragraphs=[
                    ExtractedParagraph(
                        marker="1",
                        text="Texte SHP",
                        page_start=1,
                        page_end=1,
                    )
                ],
            )
        ],
    )

    applied = apply_import(db.db_path, [result], backup_dir=None, vacuum=False)

    assert applied["preserved_translations"] == {
        "BSS": {"sermons": 1, "paragraphs": 1},
        "VGR": {"sermons": 1, "paragraphs": 1},
    }
    with db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM sermon WHERE tradition = 'SHP'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM sermon WHERE tradition IN ('VGR', 'BSS')"
        ).fetchone()[0] == 3
