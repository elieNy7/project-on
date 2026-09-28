"""Éditeur de cantiques et répétition du refrain."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.database.connection import Database, DatabaseConfig
from app.database.dao_hymns import HymnsDao
from app.ui.hymn_editor_dialog import compose_text, parse_stanzas
from app.utils.library_controller import expand_hymn_chorus


def _db(tmp_path: Path) -> Database:
    db = Database(DatabaseConfig(db_path=tmp_path / "h.db"))
    db.initialize()
    return db


def test_parse_and_compose_stanzas() -> None:
    text = "Ligne A\nLigne B\n\nRefrain\nGloire !\nAlléluia\n\n  \nLigne C\n\nChœur : Amen"
    stanzas = parse_stanzas(text)
    assert stanzas == [
        ("Ligne A\nLigne B", False),
        ("Gloire !\nAlléluia", True),
        ("Ligne C", False),
        ("Amen", True),
    ]
    assert parse_stanzas(compose_text(stanzas)) == stanzas


def test_save_create_then_edit_hymn(tmp_path: Path) -> None:
    dao = HymnsDao(_db(tmp_path))
    hymn_id = dao.save_hymn(
        None, "À toi la gloire",
        [("À toi la gloire\nÔ Ressuscité", False), ("Gloire à toi", True), ("Vois-le paraître", False)],
        number="42",
    )
    stanzas = dao.list_stanzas(hymn_id)
    assert [(s["label"], s["is_chorus"]) for s in stanzas] == [
        ("Strophe 1", False), ("Refrain", True), ("Strophe 2", False)
    ]
    # Le refrain garde la convention « Refrain » en tête (maintenance de la base).
    assert stanzas[1]["text"].startswith("Refrain")
    assert dao.get_hymn(hymn_id)["number"] == "42"

    same = dao.save_hymn(hymn_id, "À toi la gloire (révisé)", [("Nouvelle strophe", False)])
    assert same == hymn_id
    assert [s["text"] for s in dao.list_stanzas(hymn_id)] == ["Nouvelle strophe"]
    assert dao.get_hymn(hymn_id)["original_title"] == "À toi la gloire (révisé)"
    # Recherche plein texte à jour.
    assert any(r.get("hymn_id") == hymn_id for r in dao.search_stanzas("Nouvelle"))


def test_expand_chorus_after_each_verse() -> None:
    def stanza(label, chorus=False):
        return {"reference": label, "text": label, "is_chorus": chorus}

    s1, r, s2, s3 = stanza("S1"), stanza("R", True), stanza("S2"), stanza("S3")
    assert [p["reference"] for p in expand_hymn_chorus([s1, r, s2, s3])] == [
        "S1", "R", "S2", "R", "S3", "R"
    ]
    # Refrain en tête : il ouvre aussi le chant.
    assert [p["reference"] for p in expand_hymn_chorus([r, s1, s2])] == [
        "R", "S1", "R", "S2", "R"
    ]
    # Deux refrains différents, ou une seule strophe : inchangé.
    r2 = stanza("R2", True)
    assert expand_hymn_chorus([s1, r, s2, r2]) == [s1, r, s2, r2]
    assert expand_hymn_chorus([s1, r]) == [s1, r]


def test_editor_dialog_toggle_chorus() -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from app.ui.hymn_editor_dialog import HymnEditorDialog

    dialog = HymnEditorDialog(title="Test", stanzas=[("Ligne 1", False), ("Ligne 2", False)])
    try:
        cursor = dialog.editor.textCursor()
        cursor.setPosition(len("Ligne 1\n\nLig"))
        dialog.editor.setTextCursor(cursor)
        dialog.toggle_chorus_at_cursor()
        assert dialog.stanzas() == [("Ligne 1", False), ("Ligne 2", True)]
        dialog.toggle_chorus_at_cursor()
        assert dialog.stanzas() == [("Ligne 1", False), ("Ligne 2", False)]
        assert dialog.preview.count() == 2
        assert dialog.values()["title"] == "Test"
    finally:
        dialog.close()
