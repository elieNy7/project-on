from __future__ import annotations

import logging

from PyQt6.QtGui import QFontDatabase

from app.utils.app_paths import assets_dir

logger = logging.getLogger(__name__)

STARTUP_FONT_FILES = (
    "Poppins/Poppins-Regular.ttf",
    "Poppins/Poppins-Medium.ttf",
    "Poppins/Poppins-SemiBold.ttf",
    "Poppins/Poppins-Bold.ttf",
    "Poppins/Poppins-Italic.ttf",
    "Poppins/Poppins-Light.ttf",
)


def load_fonts(core_only: bool = False) -> None:
    """Enregistre dans Qt les polices embarquées (assets/fonts).

    ``core_only`` ne charge que Poppins (police de l'interface) : c'est la
    passe synchrone du démarrage. Les ~40 familles Google Fonts sont ensuite
    complétées juste après l'affichage de la fenêtre (voir main.py) — la
    liste des polices, elle, vient du manifeste et est complète aussitôt.
    ``QFontDatabase`` déduplique par famille : charger deux fois un fichier
    est sans effet.
    """
    fonts_dir = assets_dir() / "fonts"
    if not fonts_dir.exists():
        logger.warning(f"Fonts directory not found: {fonts_dir}")
        return

    loaded_families: set[str] = set()
    font_files = sorted(fonts_dir.rglob("*.ttf"))
    font_files.sort(
        key=lambda path: (0 if path.parent.name == "Poppins" else 1, str(path))
    )
    if core_only:
        font_files = [path for path in font_files if path.parent.name == "Poppins"]

    for file_path in font_files:
        font_id = QFontDatabase.addApplicationFont(str(file_path))
        if font_id != -1:
            loaded_families.update(QFontDatabase.applicationFontFamilies(font_id))
        else:
            logger.warning(f"Failed to load font: {file_path}")

    if loaded_families:
        logger.info(
            f"Loaded custom fonts ({len(font_files)} fichiers) : "
            f"{', '.join(sorted(loaded_families))}"
        )
    else:
        logger.info("No custom fonts loaded.")
