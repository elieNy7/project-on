"""Convertit les logos des réseaux (SVG) en masques PNG blancs 256×256.

Sources dans ``assets/social/svg`` :
- logos des marques : Simple Icons (https://simpleicons.org), licence CC0 ;
- site web, e-mail, téléphone : Lucide (https://lucide.dev), licence ISC.

Les masques ``assets/social/<réseau>.png`` sont recolorés au rendu par
``app/utils/church_graphics.py`` (pastilles aux couleurs officielles).

Usage : py -3 tools/build_social_icons.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
SIZE = 256


def main() -> int:
    from PySide6.QtCore import QByteArray, QRectF, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    QGuiApplication.instance() or QGuiApplication(sys.argv)
    folder = ROOT / "assets" / "social"
    for svg in sorted((folder / "svg").glob("*.svg")):
        data = svg.read_text(encoding="utf-8")
        # Tout en blanc : le rendu recolore le masque (couleur de la marque).
        data = data.replace("currentColor", "#ffffff")
        if 'fill="none"' not in data:
            data = data.replace("<svg ", '<svg fill="#ffffff" ', 1)
        renderer = QSvgRenderer(QByteArray(data.encode("utf-8")))
        image = QImage(SIZE, SIZE, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF(0, 0, SIZE, SIZE))
        painter.end()
        target = folder / f"{svg.stem}.png"
        image.save(str(target))
        print(f"[OK] {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
