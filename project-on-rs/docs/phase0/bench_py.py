"""Mesure de référence : la recherche de Project-On 2.8 (Python + module natif livré).

Lit une COPIE de la base (premier argument) avec le DAO de la 2.8, sans initialize() : aucune
maintenance, aucune écriture dans les vraies données. Écrit les temps en JSON (second argument).

    python bench_py.py <copie de project_on.db> <sortie.json> [dossier du module natif extrait]
"""

import json
import sys
import time
from pathlib import Path

# La racine du dépôt Project-On : docs/phase0 -> docs -> project-on-rs -> Project-On.
REPO = Path(__file__).resolve().parents[3]
# Le module natif de la 2.8 (unaccent en extension SQLite) : troisième argument, le dossier où le
# paquet build/native/project_on_core-*.whl a été extrait. Sans lui, la 2.8 retombe sur une
# fonction Python très lente et la comparaison n'a pas de sens : le JSON le dit (« native »).
if len(sys.argv) > 3:
    sys.path.insert(0, sys.argv[3])
sys.path.insert(0, str(REPO))

from app.database.connection import Database, DatabaseConfig  # noqa: E402
from app.database.dao_sermons import SermonsDao  # noqa: E402
from app.utils import text_utils  # noqa: E402

QUERIES = [
    ("liste_sermons", lambda d: d.list_sermons()),
    ("liste_titre_foi", lambda d: d.list_sermons(title_query="foi")),
    ("fts_grace", lambda d: d.search_paragraphs("grâce", language="fr", limit=100)),
    ("fts_ferme_assurance", lambda d: d.search_paragraphs("ferme assurance", language="fr", limit=100)),
    ("fts_expression", lambda d: d.search_paragraphs('"colonne de feu"', language="fr", limit=100)),
    ("sous_chaine_ernel_die", lambda d: d.search_paragraphs("ernel Die", language="fr", limit=100)),
    ("sous_chaine_absente", lambda d: d.search_paragraphs("zzqxw", language="fr", limit=100)),
]


def main() -> None:
    db_path, out = Path(sys.argv[1]), Path(sys.argv[2])
    dao = SermonsDao(Database(DatabaseConfig(db_path=db_path)))
    results = {"native": text_utils._NATIVE_SQLITE_EXTENSION is not None, "queries": {}}
    for name, run in QUERIES:
        times, rows = [], []
        for _ in range(3):
            start = time.perf_counter()
            rows = run(dao)
            times.append((time.perf_counter() - start) * 1000)
        first = rows[0] if rows else {}
        results["queries"][name] = {
            "ms_first": round(times[0], 1),
            "ms_best": round(min(times), 1),
            "count": len(rows),
            "first": first.get("reference") or first.get("title") or "",
        }
        print(f"{name:24} {min(times):9.1f} ms  ({len(rows)} résultats)")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
