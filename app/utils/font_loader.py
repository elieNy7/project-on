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


def load_fonts() -> None:
    """Load only the Qt fonts needed by the application shell."""
    fonts_dir = assets_dir() / "fonts"
    if not fonts_dir.exists():
        logger.warning(f"Fonts directory not found: {fonts_dir}")
        return

    loaded_families = set()

    for relative_path in STARTUP_FONT_FILES:
        file_path = fonts_dir / relative_path
        if not file_path.exists():
            logger.warning(f"Font not found: {relative_path}")
            continue

        font_id = QFontDatabase.addApplicationFont(str(file_path))
        if font_id != -1:
            families = QFontDatabase.applicationFontFamilies(font_id)
            for family in families:
                loaded_families.add(family)
        else:
            logger.warning(f"Failed to load font: {relative_path}")

    if loaded_families:
        logger.info(f"Loaded custom fonts: {', '.join(sorted(loaded_families))}")
    else:
        logger.info("No custom fonts loaded.")
