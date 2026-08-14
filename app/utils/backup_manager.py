from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BackupResult:
    path: Path
    size_bytes: int
    integrity_message: str


def verify_database(path: Path) -> tuple[bool, str]:
    """Run SQLite's quick integrity check on a database file."""
    database_path = Path(path)
    if not database_path.is_file():
        return False, "Fichier introuvable"

    try:
        with closing(
            sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
        ) as conn:
            row = conn.execute("PRAGMA quick_check").fetchone()
    except sqlite3.Error as exc:
        return False, str(exc)

    message = str(row[0]) if row else "Aucun résultat"
    return message.lower() == "ok", message


def create_database_backup(source: Path, destination: Path) -> BackupResult:
    """Create an atomic, transactionally consistent SQLite backup.

    Copying an active SQLite file with a regular filesystem copy can omit WAL
    transactions.  The SQLite backup API takes a coherent snapshot while the
    application remains open, then the result is verified before publication.
    """
    source_path = Path(source).resolve()
    destination_path = Path(destination).resolve()

    if not source_path.is_file():
        raise FileNotFoundError(f"Base de données introuvable : {source_path}")
    if source_path == destination_path:
        raise ValueError("La sauvegarde doit utiliser un fichier différent de la base active.")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination_path.with_suffix(destination_path.suffix + ".tmp")
    if temporary_path.exists():
        temporary_path.unlink()

    try:
        with closing(sqlite3.connect(str(source_path), timeout=30)) as source_conn:
            with closing(
                sqlite3.connect(str(temporary_path), timeout=30)
            ) as backup_conn:
                source_conn.backup(backup_conn, pages=2048, sleep=0.01)

        valid, integrity_message = verify_database(temporary_path)
        if not valid:
            raise sqlite3.DatabaseError(
                f"La copie a échoué au contrôle d'intégrité : {integrity_message}"
            )

        os.replace(temporary_path, destination_path)
        return BackupResult(
            path=destination_path,
            size_bytes=destination_path.stat().st_size,
            integrity_message=integrity_message,
        )
    except Exception:
        if temporary_path.exists():
            temporary_path.unlink()
        raise
