"""Les résultats de la 2.8 sur les recueils du dépôt, pour l'essai de parité de po-pdf.

    py -3.14 project-on-rs/crates/po-pdf/references.py

(à lancer depuis la racine du dépôt, avec PyMuPDF). Écrit target/pdf-ref/<recueil>.json : les
lignes lues par la 2.8 et ses cantiques. Rien d'autre n'est modifié.
"""

import json
import pathlib
import sys

root = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root))
from app.utils.hymn_pdf_parser import ordered_pdf_lines, parse_hymns_for_import  # noqa: E402

out = root / "project-on-rs" / "target" / "pdf-ref"
out.mkdir(parents=True, exist_ok=True)
for pdf in sorted((root / "cantiques").glob("*.pdf")):
    hymns = parse_hymns_for_import(pdf)
    lines = ordered_pdf_lines(pdf, column_break=True)
    (out / f"{pdf.stem}.json").write_text(json.dumps({"hymns": hymns, "lines": lines}, ensure_ascii=False), encoding="utf-8")
    print(f"{pdf.name} : {len(hymns)} cantiques")
