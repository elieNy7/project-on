from __future__ import annotations

from app.utils.app_paths import resource_root

# Cache for available fonts to avoid repeated filesystem scans
_fonts_cache: list[tuple[str, str]] | None = None


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

    # Scan font directories
    font_mappings = {
        "Bebas_Neue": ("Bebas Neue", "Bebas Neue"),
        "Google_Sans": ("Google Sans", "Google Sans"),
        "Montserrat": ("Montserrat", "Montserrat"),
        "Roboto": ("Roboto", "Roboto"),
        "Open Sans": ("Open Sans", "Open Sans"),
        "Poppins": ("Poppins", "Poppins"),
    }

    for folder_name, (display_name, css_name) in font_mappings.items():
        folder_path = fonts_dir / folder_name
        if folder_path.exists():
            fonts.append((display_name, css_name))

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
        "Montserrat": [
            ("Montserrat-Regular.ttf", "Montserrat", "normal", "400"),
            ("Montserrat-Medium.ttf", "Montserrat", "normal", "500"),
            ("Montserrat-SemiBold.ttf", "Montserrat", "normal", "600"),
            ("Montserrat-Bold.ttf", "Montserrat", "normal", "700"),
            ("Montserrat-Italic.ttf", "Montserrat", "italic", "400"),
        ],
        "Roboto": [
            ("Roboto-Regular.ttf", "Roboto", "normal", "400"),
            ("Roboto-Medium.ttf", "Roboto", "normal", "500"),
            ("Roboto-Bold.ttf", "Roboto", "normal", "700"),
            ("Roboto-Italic.ttf", "Roboto", "italic", "400"),
            ("Roboto-Light.ttf", "Roboto", "normal", "300"),
        ],
        "Open Sans": [
            ("OpenSans-Regular.ttf", "Open Sans", "normal", "400"),
            ("OpenSans-Medium.ttf", "Open Sans", "normal", "500"),
            ("OpenSans-SemiBold.ttf", "Open Sans", "normal", "600"),
            ("OpenSans-Bold.ttf", "Open Sans", "normal", "700"),
            ("OpenSans-Italic.ttf", "Open Sans", "italic", "400"),
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

    return "\n\n".join(css_rules)
