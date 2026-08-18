"""Tests du programme live : projection directe depuis la bibliothèque."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.utils.project_on_controller import ProjectOnController


def _make_controller(tmp_path: Path) -> tuple[ProjectOnController, Path]:
    from app.database.connection import Database, DatabaseConfig

    db = Database(DatabaseConfig(db_path=tmp_path / "test.db"))
    db.initialize()
    controller = ProjectOnController(db=db, presentation_dir=tmp_path / "pres")
    return controller, tmp_path / "pres" / "slide.json"


def test_load_program_projects_focus_entry_and_sets_title(tmp_path: Path) -> None:
    controller, slide_path = _make_controller(tmp_path)

    row = controller.load_program(
        "sermon",
        "Sermon de test",
        [("S - P1", "Premier"), ("S - P2", "Second"), ("S - P3", "Troisième")],
        focus_entry=2,
    )

    assert row == 2
    assert controller.program_count == 3
    assert controller.program_title == "Sermon de test"
    assert controller.current_row() == 2

    payload = json.loads(slide_path.read_text(encoding="utf-8"))
    assert payload["reference"] == "S - P3"
    assert payload["text"] == "Troisième"


def test_load_program_splits_long_texts_into_parts(tmp_path: Path) -> None:
    controller, _ = _make_controller(tmp_path)
    long_text = " ".join(f"phrase numéro {i} du texte long." for i in range(40))
    assert len(long_text) > 280  # le texte doit être découpé

    controller.load_program("sermon", "Sermon long", [("Réf", long_text)])

    assert controller.program_count > 1
    refs = [s.reference for s in controller._program_slides]
    assert refs[0] == "Réf (1/%d)" % controller.program_count
    assert refs[-1] == "Réf (%d/%d)" % (controller.program_count, controller.program_count)
    # Le texte complet est réparti sans perte (à l'espace de jonction près)
    joined = " ".join(s.text for s in controller._program_slides)
    for word in long_text.split():
        assert word in joined


def test_load_program_focus_lands_on_first_part_of_entry(tmp_path: Path) -> None:
    controller, slide_path = _make_controller(tmp_path)
    long_text = " ".join(f"phrase {i}." for i in range(60))
    short = "Court."

    controller.load_program(
        "bible", "Jean 3", [("Jean 3:16", long_text), ("Jean 3:17", short)],
        focus_entry=1,
    )

    # L'entrée 0 s'étale sur plusieurs slides, l'entrée 1 est projetée
    # juste après.
    payload = json.loads(slide_path.read_text(encoding="utf-8"))
    assert payload["reference"] == "Jean 3:17"
    assert payload["text"] == "Court."
    assert controller.current_row() >= 1


def test_navigation_walks_all_parts_and_stops_at_bounds(tmp_path: Path) -> None:
    controller, _ = _make_controller(tmp_path)
    entries = [("A", "un"), ("B", "deux"), ("C", "trois")]
    controller.load_program("custom", "Test", entries, focus_entry=0)

    assert controller.current_row() == 0
    controller.next_slide()
    assert controller.current_row() == 1
    controller.next_slide()
    assert controller.current_row() == 2
    controller.next_slide()
    assert controller.current_row() == 2  # borne haute

    controller.prev_slide()
    controller.prev_slide()
    controller.prev_slide()
    assert controller.current_row() == 0  # borne basse
    controller.prev_slide()
    assert controller.current_row() == 0


def test_peek_next_slide_mirrors_navigation(tmp_path: Path) -> None:
    controller, _ = _make_controller(tmp_path)
    controller.load_program("custom", "T", [("R1", "a"), ("R2", "b")], focus_entry=0)

    peeked = controller.peek_next_slide()
    assert peeked is not None and peeked.reference == "R2"
    controller.next_slide()
    assert controller.peek_next_slide() is None  # dernière slide


def test_empty_entries_do_not_load_program(tmp_path: Path) -> None:
    controller, _ = _make_controller(tmp_path)
    row = controller.load_program("custom", "Vide", [])
    assert row == -1
    assert controller.program_count == 0


def test_split_false_keeps_single_slide(tmp_path: Path) -> None:
    controller, _ = _make_controller(tmp_path)
    long_text = "mot " * 500

    controller.load_program(
        "custom", "Une seule diapo", [("Annonce", long_text)], split=False
    )
    assert controller.program_count == 1
    assert controller._program_slides[0].reference == "Annonce"


def test_hymn_reference_is_rebuilt_for_presentation(tmp_path: Path) -> None:
    controller, slide_path = _make_controller(tmp_path)

    controller.load_program(
        "hymn", "Cantique 12", [("12 - Titre - Strophe 1", "Couplet un")]
    )
    payload = json.loads(slide_path.read_text(encoding="utf-8"))
    # La référence passe sur deux lignes pour la projection des cantiques
    assert payload["reference"] == "12\nTitre - Strophe 1"


def test_add_custom_slides_projects_quick_text(tmp_path: Path) -> None:
    controller, slide_path = _make_controller(tmp_path)

    row = controller.add_custom_slides(
        "Annonce", ["Bienvenue à tous ce matin."], split=True
    )
    assert row == 0
    payload = json.loads(slide_path.read_text(encoding="utf-8"))
    assert payload["source"] == "custom"
    assert payload["text"] == "Bienvenue à tous ce matin."


def test_program_changed_signal_emits_title(tmp_path: Path) -> None:
    controller, _ = _make_controller(tmp_path)
    titles: list[str] = []
    controller.programChanged.connect(titles.append)

    controller.load_program("sermon", "Nouveau programme", [("R", "T")])
    assert titles == ["Nouveau programme"]


def test_reload_program_replaces_previous(tmp_path: Path) -> None:
    controller, slide_path = _make_controller(tmp_path)
    controller.load_program("sermon", "A", [("A1", "a1"), ("A2", "a2")])
    controller.load_program("bible", "B", [("B1", "b1")])

    assert controller.program_count == 1
    assert controller.program_title == "B"
    payload = json.loads(slide_path.read_text(encoding="utf-8"))
    assert payload["reference"] == "B1"
