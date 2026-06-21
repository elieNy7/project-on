"""Fixtures partagées pour les tests de Project-On."""

from __future__ import annotations

import pytest
from pathlib import Path

from app.database.connection import Database, DatabaseConfig


@pytest.fixture
def db(tmp_path: Path) -> Database:
    """Base de données SQLite temporaire initialisée avec le schéma complet."""
    db_path = tmp_path / "test_project_on.db"
    database = Database(DatabaseConfig(db_path=db_path))
    database.initialize()
    return database
