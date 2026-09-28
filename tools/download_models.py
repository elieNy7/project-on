"""Télécharge le modèle de détourage (photo du pasteur) pour l'installeur.

Place ``models/silueta.onnx`` (44 Mo, U²-Net réduit, projet rembg, MIT) à
la racine du projet ; PyInstaller l'embarque pour que le détourage marche
sans Internet. L'empreinte SHA-256 est vérifiée. Sans ce fichier,
l'application le télécharge une fois, à la première utilisation.

Usage : py -3 tools/download_models.py
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.utils import background_removal as br  # noqa: E402


def main() -> int:
    target = ROOT / "models" / br.MODEL_NAME
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == br.MODEL_SHA256:
        print(f"[OK]  {target.relative_to(ROOT)} déjà présent")
        return 0
    try:
        downloaded = br.download_model(
            lambda done, total: print(f"\r      {done * 100 // max(1, total)} %", end="")
        )
    except Exception as exc:
        print(f"\n[ERR] Téléchargement du modèle impossible : {exc}")
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(downloaded, target)
    print(f"\n[NEW] {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
