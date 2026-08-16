import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.utils.fonts import get_font_css_imports

print("Generating fonts.css...")
try:
    css = get_font_css_imports()
    if not css:
        print("Warning: CSS is empty! Check if fonts are found.")

    # Chemin ancré à la racine du dépôt, indépendant du répertoire courant,
    # puis confiné à cette racine.
    path = (ROOT / "presentation" / "fonts.css").resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError("Chemin de sortie hors du dépôt")
    path.write_text(
        "/* Custom Fonts for Project-On */\n\n" + css + "\n",
        encoding="utf-8",
    )

    print(f"Updated {path}")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
