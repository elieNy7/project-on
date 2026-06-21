import os
import sys

sys.path.append(os.getcwd())
from pathlib import Path

from app.utils.fonts import get_font_css_imports

print("Generating fonts.css...")
try:
    css = get_font_css_imports()
    if not css:
        print("Warning: CSS is empty! Check if fonts are found.")

    path = Path("presentation/fonts.css")
    with open(path, "w", encoding="utf-8") as f:
        f.write("/* Custom Fonts for Project-On */\n\n")
        f.write(css)
        f.write("\n")

    print(f"Updated {path}")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
