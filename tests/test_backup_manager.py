from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.utils.backup_manager import create_database_backup, verify_database


def test_database_backup_includes_committed_wal_data(tmp_path: Path) -> None:
    source = tmp_path / "active.db"
    destination = tmp_path / "backup.db"

    with sqlite3.connect(source) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE service_item (id INTEGER PRIMARY KEY, title TEXT)")
        conn.execute("INSERT INTO service_item(title) VALUES (?)", ("Lecture biblique",))
        conn.commit()

        result = create_database_backup(source, destination)

    assert result.path == destination.resolve()
    assert result.size_bytes > 0
    assert result.integrity_message == "ok"
    assert verify_database(destination) == (True, "ok")
    with sqlite3.connect(destination) as backup:
        assert backup.execute("SELECT title FROM service_item").fetchone()[0] == "Lecture biblique"


def test_database_backup_rejects_active_database_as_destination(tmp_path: Path) -> None:
    source = tmp_path / "active.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE content (value TEXT)")

    with pytest.raises(ValueError):
        create_database_backup(source, source)


def test_verify_database_reports_missing_file(tmp_path: Path) -> None:
    assert verify_database(tmp_path / "missing.db") == (False, "Fichier introuvable")
