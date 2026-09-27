"""Découpage des textes longs et des strophes de cantiques."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.utils.settings import AppSettings, SplitSettings
from app.utils.text_utils import split_hymn_stanza, split_text_into_slides


def _words(text: str) -> list[str]:
    return text.split()


def test_short_text_is_never_split() -> None:
    assert split_text_into_slides("Jésus pleura.") == ["Jésus pleura."]
    assert split_text_into_slides("") == []


def test_long_text_parts_are_balanced_and_lossless() -> None:
    text = " ".join(f"Phrase numéro {i} du texte long." for i in range(40))
    parts = split_text_into_slides(text, 280, 60)
    assert len(parts) == 5  # minimum de parties pour ~1 270 caractères
    assert all(len(p) <= 280 for p in parts)
    lengths = [len(p) for p in parts]
    assert max(lengths) - min(lengths) < 60  # parties de longueur proche
    assert _words(" ".join(parts)) == _words(text)


def test_no_tiny_orphan_part_at_the_end() -> None:
    text = "A" * 10 + " " + " ".join(["mot"] * 70) + ". Fin."
    parts = split_text_into_slides(text, 280, 60)
    assert min(len(p) for p in parts) >= 60


def test_line_breaks_are_kept_and_preferred_as_cut_points() -> None:
    first = "Premier alinéa, qui parle de la foi et de la grâce de Dieu envers nous. " * 2
    second = "Deuxième alinéa, qui parle de l'espérance et de la patience des saints. " * 2
    text = first.strip() + "\n" + second.strip()
    parts = split_text_into_slides(text, 200, 60)
    assert parts == [first.strip(), second.strip()]

    kept = split_text_into_slides(text + "\nCourt.", 400, 60)
    assert "\n" in kept[0]
    flat = split_text_into_slides(text + "\nCourt.", 400, 60, keep_line_breaks=False)
    assert all("\n" not in part for part in flat)


def test_sentences_are_not_cut_after_abbreviations_or_verse_numbers() -> None:
    text = (
        "Alors M. Branham a dit que Jean 3.16 est le cœur de l'Évangile, et que "
        "St. Paul l'a répété aux Romains avec beaucoup de force et de conviction. "
    ) * 4
    parts = split_text_into_slides(text.strip(), 200, 40)
    for part in parts:
        assert not part.endswith(" M.")
        assert not part.endswith(" St.")
        assert not part.startswith("Branham")


def test_prefers_sentence_end_over_mid_sentence_cut() -> None:
    sentence = "Dieu est amour et Il ne change jamais, hier aujourd'hui et éternellement."
    text = " ".join([sentence] * 6)
    for part in split_text_into_slides(text, 160, 40):
        assert part.endswith(".")


def test_single_giant_word_is_still_split() -> None:
    parts = split_text_into_slides("x" * 700, 280, 60)
    assert all(len(p) <= 280 for p in parts)
    assert "".join(parts) == "x" * 700


# ── Cantiques ──────────────────────────────────────────────────────────


STANZA_8 = "\n".join(f"Vers numéro {i} du cantique" for i in range(1, 9))


def test_short_stanza_stays_whole() -> None:
    four = "\n".join(STANZA_8.split("\n")[:4])
    assert split_hymn_stanza(four, 4) == [four]


def test_long_stanza_split_by_verses_never_mid_verse() -> None:
    parts = split_hymn_stanza(STANZA_8, 4)
    assert [p.count("\n") + 1 for p in parts] == [4, 4]
    assert "\n".join(parts) == STANZA_8


def test_couplets_stay_together() -> None:
    six = "\n".join(STANZA_8.split("\n")[:6])
    assert [p.count("\n") + 1 for p in split_hymn_stanza(six, 4)] == [4, 2]
    assert [
        p.count("\n") + 1 for p in split_hymn_stanza(six, 4, keep_couplets=False)
    ] == [3, 3]
    # Parties de 3 vers : les couplets imposent 2 + 2 + 2.
    assert [p.count("\n") + 1 for p in split_hymn_stanza(six, 3)] == [2, 2, 2]


def test_flat_stanza_without_line_breaks_is_split_like_text() -> None:
    flat = " ".join(["Gloire à Dieu, gloire à l'Agneau, qui règne à jamais."] * 8)
    parts = split_hymn_stanza(flat, 4, 200)
    assert len(parts) > 1 and all(len(p) <= 200 for p in parts)


# ── Contrôleur et réglages ─────────────────────────────────────────────


def _controller(tmp_path: Path):
    from app.database.connection import Database, DatabaseConfig
    from app.utils.project_on_controller import ProjectOnController

    db = Database(DatabaseConfig(db_path=tmp_path / "t.db"))
    db.initialize()
    return ProjectOnController(db=db, presentation_dir=tmp_path / "pres")


def test_hymn_stanzas_are_split_into_parts(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    controller.load_program("hymn", "Cantique 1", [("1 - Strophe 1", "Refrain\n" + STANZA_8)])
    refs = [s.reference for s in controller._program_slides]
    assert refs == ["1 - Strophe 1 (1/2)", "1 - Strophe 1 (2/2)"]
    assert controller._program_slides[0].text.count("\n") == 3  # 4 vers
    assert not controller._program_slides[0].text.startswith("Refrain")

    controller.set_split_settings(SplitSettings(hymn_enabled=False))
    controller.load_program("hymn", "Cantique 1", [("1 - Strophe 1", STANZA_8)])
    assert controller.program_count == 1

    controller.set_split_settings(SplitSettings(hymn_max_lines=2))
    controller.load_program("hymn", "Cantique 1", [("1 - Strophe 1", STANZA_8)])
    assert controller.program_count == 4


def test_sermon_paragraph_keeps_alineas_on_their_own_lines(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    alinea = "Un alinéa assez long pour compter dans la longueur du paragraphe entier."
    text = "\n".join([alinea] * 6)
    controller.load_program("sermon", "Sermon", [("§12", text)])
    assert controller.program_count > 1
    for slide in controller._program_slides:
        assert all(line == alinea for line in slide.text.split("\n"))


def test_split_settings_limits_and_counter(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    text = " ".join(f"Phrase {i} du paragraphe." for i in range(30))
    controller.set_split_settings(SplitSettings(max_chars=150, show_part_counter=False))
    controller.load_program("sermon", "S", [("§1", text)])
    assert all(len(s.text) <= 150 for s in controller._program_slides)
    assert all(s.reference == "§1" for s in controller._program_slides)

    controller.set_split_settings(SplitSettings(text_enabled=False))
    controller.load_program("sermon", "S", [("§1", text)])
    assert controller.program_count == 1


def test_split_settings_round_trip_and_sanitized(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settings = AppSettings()
    settings.split = SplitSettings(max_chars=360, hymn_max_lines=6, hymn_keep_couplets=False)
    settings.save(path)
    loaded = AppSettings.load(path).split
    assert (loaded.max_chars, loaded.hymn_max_lines, loaded.hymn_keep_couplets) == (360, 6, False)

    wild = SplitSettings.from_payload({"max_chars": 5, "hymn_max_lines": 99})
    assert wild.max_chars == 120 and wild.hymn_max_lines == 12
    assert AppSettings().split == SplitSettings()


def test_split_settings_dialog_reads_back_and_previews() -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from app.ui.split_settings_dialog import SplitSettingsDialog

    dialog = SplitSettingsDialog(SplitSettings(max_chars=200, hymn_max_lines=3))
    try:
        read = dialog.read_settings()
        assert read.max_chars == 200 and read.hymn_max_lines == 3
        assert "Strophe de 6 vers — 3 parties" in dialog._preview.text()
        dialog._hymn_enabled.setChecked(False)
        assert "Strophe de 6 vers — 1 partie" in dialog._preview.text()
        assert not dialog._hymn_max_lines.isEnabled()
    finally:
        dialog.close()
