from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSize
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    src = root / "assets" / "logo" / "project-on-mark.svg"
    png = root / "assets" / "logo" / "app icon.png"
    docs_png = root / "docs" / "app-icon.png"
    ico_asset = root / "assets" / "logo.ico"
    out_dir = root / "build"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "app.ico"

    app = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(src))
    if not renderer.isValid():
        raise RuntimeError(f"Invalid SVG logo: {src}")
    image = QImage(QSize(1024, 1024), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    if not image.save(str(png), "PNG") or not image.save(str(docs_png), "PNG"):
        raise RuntimeError("Could not write logo PNG files")

    # Common Windows icon sizes
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img = Image.open(png).convert("RGBA")
    img.save(out, format="ICO", sizes=sizes)
    img.save(ico_asset, format="ICO", sizes=sizes)

    print(f"Wrote: {png}, {docs_png}, {ico_asset}, {out}")
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
