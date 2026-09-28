"""Télécharge les Bibles libres « fournies » et les prépare pour l'installeur.

Chaque Bible marquée ``bundled`` dans ``app/utils/bible_catalog.py`` est
téléchargée depuis scrollmapper/bible_databases, convertie au format
Project-On puis enregistrée compressée dans ``bibles/<module>.json.gz``.
PyInstaller embarque ce dossier ; au démarrage, l'application installe les
Bibles qui manquent (voir ``install_bundled_bibles``).

Usage :
    py -3 tools/download_bibles.py            # Bibles fournies manquantes
    py -3 tools/download_bibles.py --all      # tout le catalogue
    py -3 tools/download_bibles.py --force    # retélécharger
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.utils.bible_catalog import CATALOG, download, save_payload  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="tout le catalogue")
    parser.add_argument("--force", action="store_true", help="retélécharger")
    parser.add_argument("--out", default=str(ROOT / "bibles"))
    args = parser.parse_args()

    out = Path(args.out)
    failures = 0
    for entry in CATALOG:
        if not (args.all or entry.bundled):
            continue
        target = out / f"{entry.module}.json.gz"
        if target.exists() and not args.force:
            print(f"[OK]   {entry.shortname} (déjà présente)")
            continue
        try:
            payload = download(entry)
            path = save_payload(payload, out)
            size = path.stat().st_size / 1_000_000
            print(f"[NEW]  {entry.shortname} : {len(payload['verses'])} versets, {size:.1f} Mo")
        except Exception as exc:  # réseau, format
            failures += 1
            print(f"[ERR]  {entry.shortname} : {exc}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
