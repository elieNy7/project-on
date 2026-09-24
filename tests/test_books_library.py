"""« Livres » tab: book import rules, catalogue, and sermon alineas."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from app.database.dao_sermons import SermonsDao
from app.utils import app_paths
from app.utils.library_controller import LibraryController

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from import_books import (  # noqa: E402
    Chapter,
    Segmenter,
    clean_ocr_text,
    clean_text,
    is_ocr_garbage,
    join_lines,
)


# -- Import rules -------------------------------------------------------------


def _chapter() -> Chapter:
    return Chapter("TR-TEST", "Test", 0, "test.pdf")


def test_indented_first_line_opens_a_paragraph() -> None:
    chapter, seg = _chapter(), Segmenter()
    seg.line(chapter, 1, "Premier paragraphe qui", True)
    seg.line(chapter, 1, "continue ici.", False)
    seg.line(chapter, 1, "Second paragraphe.", True)
    seg.line(chapter, 2, "Suite du second sur la page 2.", False)
    seg.flush()
    assert [(p.page, p.text) for p in chapter.paragraphs] == [
        (1, "Premier paragraphe qui continue ici."),
        (1, "Second paragraphe. Suite du second sur la page 2."),
    ]
    assert [m for m, _ in chapter.numbered()] == ["1-1", "1-2"]


def test_verse_stays_one_paragraph_with_line_breaks() -> None:
    chapter, seg = _chapter(), Segmenter()
    seg.line(chapter, 3, "“Versez de l’encre dans les ondes,", True)
    seg.line(chapter, 3, "Changez le ciel en parchemin;", True)
    seg.line(chapter, 3, "Ne serait pas suffisant.”", True)
    seg.line(chapter, 3, "— Cooper", True)
    seg.line(chapter, 3, "Après ce chant, la réunion commence.", True)
    seg.flush()
    assert [p.text for p in chapter.paragraphs] == [
        "“Versez de l’encre dans les ondes,\nChangez le ciel en parchemin;\nNe serait pas suffisant.”",
        "— Cooper",
        "Après ce chant, la réunion commence.",
    ]


def test_indented_quote_continues_in_lowercase_on_one_line() -> None:
    chapter, seg = _chapter(), Segmenter()
    seg.line(chapter, 5, "Et l’Éternel ouvrit les yeux du serviteur, qui vit la", True)
    seg.line(chapter, 5, "montagne pleine de chevaux.", True)
    seg.flush()
    assert chapter.paragraphs[0].text == (
        "Et l’Éternel ouvrit les yeux du serviteur, qui vit la montagne pleine de chevaux."
    )


def test_compound_word_split_at_line_end_is_rejoined() -> None:
    assert join_lines(["une auréole, au-", "dessus de la tête"]) == "une auréole, au-dessus de la tête"


def test_vgr_fonts_dashes_and_ornaments() -> None:
    assert clean_text("Et je^j’avais dormi, la_la tête") == "Et je—j’avais dormi, la—la tête"
    assert clean_text("LA RÉPRIMANDE `") == "LA RÉPRIMANDE"


def test_ocr_common_misreads_are_fixed() -> None:
    assert clean_ocr_text("n’est-ce pasQ Il l'a dit") == "n’est-ce pas? Il l’a dit"
    assert clean_ocr_text("l’EvangiIe") == "l’Evangile"
    assert clean_ocr_text("Il a dit") == "Il a dit"  # « Il » en début de mot intact


def test_decorative_titles_misread_by_ocr_are_dropped() -> None:
    lexicon = {"de", "la", "elle", "le", "ange", "église", "laodicée"}
    assert is_ocr_garbage("d30e de d’Ozae de oZodicee", lexicon)
    assert is_ocr_garbage("Q/fdŒano gunhano", lexicon)
    assert not is_ocr_garbage("Elle mourut.", lexicon)
    assert not is_ocr_garbage("Boniface III,", lexicon)


# -- Catalogue ----------------------------------------------------------------


def _seed_books(db) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM sermon_paragraph")
        conn.execute("DELETE FROM sermon")
        rows = [
            (1, "INTRODUCTION", "BK-AGES-CH00", "VGR", "BK-AGES-CH00"),
            (2, "Introduction", "BK-SENT-CH00", "VGR", "BK-SENT-CH00"),
            (3, "Un étrange défi", "BK-SENT-CH01", "VGR", "BK-SENT-CH01"),
            (4, "Le Messager", "TR-MESS", "VGR", "TR-002"),
            (5, "Au-delà du rideau du temps", "TR-BEYO", "VGR", "TR-001"),
            (6, "La foi", "47-0412", "VGR", "47-0412"),
        ]
        conn.executemany(
            "INSERT INTO sermon (id, title, date, tradition, language, sort_key, canonical_title) "
            "VALUES (?, ?, ?, ?, 'fr', ?, ?)",
            [(i, t, d, tr, sk, t) for i, t, d, tr, sk in rows],
        )
        conn.executemany(
            "INSERT INTO sermon_paragraph (sermon_id, paragraph_no, ref, text, marker) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (1, 11001, "11-1", "Apocalypse 1.1-3.", "11-1"),
                (2, 1001, "1-1", "La vie de William Branham.", "1-1"),
                (5, 3001, "3-1", "L’autre matin, j’étais au lit.", "3-1"),
                (3, 1001, "1-1", "Les portes du grand auditorium s’ouvrent.", "1-1"),
                (4, 2001, "2-1", "Écris à l’ange de l’Église de Laodicée.", "2-1"),
                (6, 1, "§1", "Les portes du tabernacle.", "§1"),
            ],
        )
        conn.executemany(
            "INSERT OR REPLACE INTO library_book (key, title, date_prefix, tradition, sort_order) "
            "VALUES (?, ?, ?, 'VGR', ?)",
            [("sent", "Un homme envoyé de Dieu", "BK-SENT-", 10), ("brochures", "Brochures", "TR-", 30)],
        )


def test_books_listed_with_their_chapters(db) -> None:
    _seed_books(db)
    dao = SermonsDao(db)
    assert [b["key"] for b in dao.list_books()] == ["ages-vgr", "sent", "brochures"]
    assert [(c["chapter_num"], c["title"]) for c in dao.list_book_chapters("sent")] == [
        (0, "Introduction"), (1, "Un étrange défi"),
    ]
    # Brochures : ordre du catalogue, numérotées par leur position.
    assert [(c["chapter_num"], c["title"]) for c in dao.list_book_chapters("brochures")] == [
        (1, "Au-delà du rideau du temps"), (2, "Le Messager"),
    ]
    assert dao.book_of_chapter(4)["key"] == "brochures"


def test_book_search_and_sermons_stay_separate(db) -> None:
    _seed_books(db)
    dao = SermonsDao(db)
    hits = dao.search_book("laodicee", "brochures")
    assert [(h["marker"], h["title"]) for h in hits] == [("2-1", "Le Messager")]
    # Les chapitres de livres ne sont pas des sermons.
    assert [s["date"] for s in dao.list_sermons(translator="VGR")] == ["47-0412"]
    assert dao.search_book("portes", "sent")[0]["marker"] == "1-1"


# -- Sermon alineas -----------------------------------------------------------


def test_alineas_of_a_paragraph_are_projected_together() -> None:
    entries = [
        ("47-0412 - La Foi - §1", "Premier alinéa."),
        ("47-0412 - La Foi - §1", "Deuxième alinéa."),
        ("47-0412 - La Foi - §2", "Suite."),
    ]
    assert LibraryController._group_alineas(entries) == [
        ("47-0412 - La Foi - §1", "Premier alinéa.\nDeuxième alinéa."),
        ("47-0412 - La Foi - §2", "Suite."),
    ]


# -- Data pack ----------------------------------------------------------------


def test_data_pack_brings_books_and_their_catalogue(tmp_path, db) -> None:
    _seed_books(db)
    pack = tmp_path / "pack.db"
    source = sqlite3.connect(db.db_path)
    target = sqlite3.connect(pack)
    source.backup(target)
    source.close()
    target.close()
    with db.connect() as conn:
        conn.execute("DELETE FROM sermon_paragraph WHERE sermon_id IN (3, 4)")
        conn.execute("DELETE FROM sermon WHERE id IN (2, 3, 4, 5)")
        conn.execute("DELETE FROM library_book WHERE key IN ('sent', 'brochures')")
        conn.execute("INSERT OR REPLACE INTO app_meta (key, value) VALUES ('data_pack_version', '3')")

    assert app_paths.upgrade_data_pack(db.db_path, pack)
    dao = SermonsDao(db)
    assert [b["key"] for b in dao.list_books()] == ["ages-vgr", "sent", "brochures"]
    assert dao.search_book("laodicee", "brochures")
