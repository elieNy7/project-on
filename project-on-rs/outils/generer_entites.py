"""Génère crates/po-text/src/entities.rs depuis html.entities.html5 de Python.

La 2.8 décode le HTML avec html.unescape ; la 3.0 doit rendre exactement le même texte. La table
vient donc de Python lui-même (2 231 noms, dont ceux admis sans point-virgule).

    python outils/generer_entites.py
"""

from html.entities import html5
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "crates" / "po-text" / "src" / "entities.rs"
BACKSLASH = chr(92)


def rust_str(value: str) -> str:
    out = []
    for c in value:
        if c in ('"', BACKSLASH):
            out.append(BACKSLASH + c)
        elif 0x20 <= ord(c) < 0x7F:
            out.append(c)
        else:
            out.append(BACKSLASH + "u{%x}" % ord(c))
    return '"' + "".join(out) + '"'


def main() -> None:
    # Tri par octets : celui de la recherche dichotomique côté Rust.
    names = sorted(html5, key=lambda name: name.encode("utf-8"))
    lines = [
        "//! Les noms d'entités HTML5 et leur texte, tirés de `html.entities.html5` (Python).",
        "//!",
        "//! Fichier généré par `outils/generer_entites.py` : ne pas le modifier à la main.",
        "",
        "/// (nom, texte), triés par nom (recherche dichotomique). Un nom finit par `;` ou non, comme",
        "/// dans la table de Python.",
        "#[rustfmt::skip]",
        f"pub(crate) static ENTITIES: [(&str, &str); {len(names)}] = [",
    ]
    lines += [f"    ({rust_str(n)}, {rust_str(html5[n])})," for n in names]
    lines.append("];")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(names)} entités : {OUT}")


if __name__ == "__main__":
    main()
