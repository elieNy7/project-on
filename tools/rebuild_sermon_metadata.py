"""Maintenance de la base des sermons : métadonnées exactes + optimisation.

Recalcule les titres canoniques et les clés de recherche avec les règles de
l'application (la traduction SHP garde le titre exact imprimé dans le PDF),
puis optimise la base :

* ``ANALYZE`` — statistiques requêtes pour le planificateur SQLite ;
* ``PRAGMA optimize`` — ajustements automatiques d'index ;
* ``PRAGMA integrity_check`` — contrôle d'intégrité complet ;
* ``--vacuum`` — compactage physique (récupère l'espace des suppressions).

Usage : python tools/rebuild_sermon_metadata.py [--db chemin] [--vacuum]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_DB = ROOT / "data" / "project_on.db"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Recalcule les titres canoniques (SHP = titre PDF exact), "
            "reconstruit les clés de recherche et optimise la base."
        )
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--vacuum",
        action="store_true",
        help="Compacte physiquement la base (peut prendre plusieurs minutes).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db_path = args.db.resolve()
    if not db_path.exists():
        print(f"Base introuvable: {db_path}", file=sys.stderr)
        return 2

    from app.database.connection import Database, DatabaseConfig

    database = Database(DatabaseConfig(db_path=db_path))
    with database.connect() as conn:
        before = conn.execute(
            """
            SELECT COUNT(*) FROM sermon
            WHERE tradition = 'SHP' AND canonical_title <> title
            """
        ).fetchone()[0]
        total_shp = conn.execute(
            "SELECT COUNT(*) FROM sermon WHERE tradition = 'SHP'"
        ).fetchone()[0]
        print(f"Sermons SHP: {total_shp} — titres canoniques divergents: {before}")

        started = time.perf_counter()
        database._ensure_sermon_search_metadata(conn)
        conn.commit()
        print(f"Métadonnées recalculées en {time.perf_counter() - started:.1f}s")

        after = conn.execute(
            """
            SELECT COUNT(*) FROM sermon
            WHERE tradition = 'SHP' AND canonical_title <> title
            """
        ).fetchone()[0]
        print(f"Titres canoniques SHP divergents après recalcul: {after}")

        print("Échantillon (titre stocké = titre affiché) :")
        for title, canon, date, loc in conn.execute(
            """
            SELECT title, canonical_title, date, location FROM sermon
            WHERE tradition = 'SHP' ORDER BY date LIMIT 6
            """
        ):
            exact = "OK " if title == canon else "ECART"
            print(f"  [{exact}] {date:>10} | {title[:52]:<52} | {loc}")

        print("ANALYZE...")
        started = time.perf_counter()
        conn.execute("ANALYZE")
        conn.commit()
        print(f"ANALYZE terminé en {time.perf_counter() - started:.1f}s")

    integrity = str(
        sqlite3.connect(db_path).execute("PRAGMA integrity_check").fetchone()[0]
    )
    print(f"integrity_check: {integrity}")
    if integrity.lower() != "ok":
        return 1

    if args.vacuum:
        print("VACUUM (peut prendre plusieurs minutes)...")
        started = time.perf_counter()
        connection = sqlite3.connect(db_path, timeout=120.0)
        try:
            connection.execute("VACUUM")
            connection.execute("PRAGMA optimize")
        finally:
            connection.close()
        size_mb = db_path.stat().st_size / (1024 * 1024)
        print(f"VACUUM terminé en {time.perf_counter() - started:.1f}s — {size_mb:.1f} Mo")
    else:
        connection = sqlite3.connect(db_path, timeout=120.0)
        try:
            connection.execute("PRAGMA optimize")
        finally:
            connection.close()
        print("PRAGMA optimize appliqué.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
