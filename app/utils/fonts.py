from __future__ import annotations

import json

from app.utils.app_paths import resource_root

# Cache for available fonts to avoid repeated filesystem scans
_fonts_cache: list[tuple[str, str]] | None = None


def _manifest_families() -> list[tuple[str, str]]:
    """Familles listées par le manifeste des Google Fonts téléchargées.

    Le manifeste ``assets/fonts/fonts.json`` est généré par
    ``tools/download_google_fonts.py`` : [{family, folder, files}, …].
    """
    manifest_path = resource_root() / "assets" / "fonts" / "fonts.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    families: list[tuple[str, str]] = []
    if isinstance(payload, list):
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            family = str(entry.get("family") or "").strip()
            folder = str(entry.get("folder") or "").strip()
            if not family or not folder:
                continue
            # Le dossier doit exister (install partielle, ressource absente).
            if (resource_root() / "assets" / "fonts" / folder).is_dir():
                families.append((family, family))
    return families


def get_available_fonts() -> list[tuple[str, str]]:
    """Get list of available fonts from assets/fonts directory.
    Returns list of tuples: (display_name, font_family_css)
    Results are cached after first call for performance.
    """
    global _fonts_cache
    if _fonts_cache is not None:
        return _fonts_cache

    fonts_dir = resource_root() / "assets" / "fonts"

    fonts: list[tuple[str, str]] = [
        ("Système (défaut)", "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"),
    ]

    if not fonts_dir.exists():
        _fonts_cache = fonts
        return fonts

    # Familles historiques embarquées avant l'arrivée du manifeste.
    font_mappings = {
        "Bebas_Neue": ("Bebas Neue", "Bebas Neue"),
        "Google_Sans": ("Google Sans", "Google Sans"),
        "Noto_Sans": ("Noto Sans", "Noto Sans"),
        "Oswald": ("Oswald", "Oswald"),
        "Poppins": ("Poppins", "Poppins"),
    }
    for folder_name, (display_name, css_name) in font_mappings.items():
        if (fonts_dir / folder_name).exists():
            fonts.append((display_name, css_name))

    # Familles Google Fonts (manifeste), triées alphabétiquement.
    known = {css for _display, css in fonts}
    for display_name, css_name in sorted(_manifest_families()):
        if css_name not in known:
            fonts.append((display_name, css_name))
            known.add(css_name)

    _fonts_cache = fonts
    return fonts


def get_font_css_imports() -> str:
    """Generate CSS @font-face rules for all available fonts."""
    fonts_dir = resource_root() / "assets" / "fonts"
    css_rules = []

    font_files = {
        "Bebas_Neue": [
            ("BebasNeue-Regular.ttf", "Bebas Neue", "normal", "400"),
        ],
        "Google_Sans": [
            ("static/GoogleSans-Regular.ttf", "Google Sans", "normal", "400"),
            ("static/GoogleSans-Medium.ttf", "Google Sans", "normal", "500"),
            ("static/GoogleSans-SemiBold.ttf", "Google Sans", "normal", "600"),
            ("static/GoogleSans-Bold.ttf", "Google Sans", "normal", "700"),
            ("static/GoogleSans-Italic.ttf", "Google Sans", "italic", "400"),
        ],
        "Poppins": [
            ("Poppins-Regular.ttf", "Poppins", "normal", "400"),
            ("Poppins-Medium.ttf", "Poppins", "normal", "500"),
            ("Poppins-SemiBold.ttf", "Poppins", "normal", "600"),
            ("Poppins-Bold.ttf", "Poppins", "normal", "700"),
            ("Poppins-Italic.ttf", "Poppins", "italic", "400"),
            ("Poppins-Light.ttf", "Poppins", "normal", "300"),
        ],
    }

    for folder_name, files in font_files.items():
        folder_path = fonts_dir / folder_name
        if not folder_path.exists():
            continue

        for file_path, family, style, weight in files:
            full_path = folder_path / file_path
            if full_path.exists():
                # Use relative path from presentation folder
                rel_path = f"../assets/fonts/{folder_name}/{file_path}"
                css_rules.append(f"""@font-face {{
  font-family: '{family}';
  src: url('{rel_path}') format('truetype');
  font-weight: {weight};
  font-style: {style};
}}""")

    # Familles du manifeste : le premier .ttf non italique de chaque dossier
    # (statique Regular ou police variable — la variable couvre toutes les
    # graisses via la plage font-weight 100-900).
    try:
        manifest = json.loads((fonts_dir / "fonts.json").read_text(encoding="utf-8"))
    except Exception:
        manifest = []
    for entry in manifest if isinstance(manifest, list) else []:
        if not isinstance(entry, dict):
            continue
        family = str(entry.get("family") or "").strip()
        folder = str(entry.get("folder") or "").strip()
        files = entry.get("files") or []
        if not family or not folder:
            continue
        regular = next((f for f in files if "Italic" not in str(f)), None)
        italic = next((f for f in files if "Italic" in str(f)), None)
        if regular:
            rel_path = f"../assets/fonts/{folder}/{regular}"
            css_rules.append(f"""@font-face {{
  font-family: '{family}';
  src: url('{rel_path}') format('truetype');
  font-weight: 100 900;
  font-style: normal;
}}""")
        if italic:
            rel_path = f"../assets/fonts/{folder}/{italic}"
            css_rules.append(f"""@font-face {{
  font-family: '{family}';
  src: url('{rel_path}') format('truetype');
  font-weight: 100 900;
  font-style: italic;
}}""")

    return "\n\n".join(css_rules)
