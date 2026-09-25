"""Draw the Inno Setup wizard images from the Project-On logo.

Writes installer/wizard/wizard-<scale>.bmp (side panel of the Welcome and
Finish pages) and installer/wizard/small-<scale>.bmp (page header), at the
100 / 150 / 200 % sizes Inno Setup picks from for the screen's DPI.

Run:  py -3 tools/generate_installer_images.py
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
MARK = ROOT / "assets" / "logo" / "project-on-mark.svg"
OUT = ROOT / "installer" / "wizard"

NAVY_TOP = QColor("#17243A")
NAVY_BOTTOM = QColor("#0B1222")
GOLD = QColor("#F3B64A")
TEXT = QColor("#F5F7FA")
MUTED = QColor("#9AA6BA")

LARGE = (164, 314)  # 100 % size of the modern wizard side panel
SMALL = (55, 55)
SCALES = (100, 150, 200)


def _font(px: float, weight: QFont.Weight) -> QFont:
    font = QFont("Segoe UI Variable Display")
    font.setPixelSize(max(1, round(px)))
    font.setWeight(weight)
    return font


def draw_large(scale: float, logo: QSvgRenderer) -> QImage:
    w, h = round(LARGE[0] * scale), round(LARGE[1] * scale)
    img = QImage(w, h, QImage.Format.Format_RGB32)
    p = QPainter(img)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
    grad = QLinearGradient(0, 0, 0, h)
    grad.setColorAt(0, NAVY_TOP)
    grad.setColorAt(1, NAVY_BOTTOM)
    p.fillRect(0, 0, w, h, grad)

    size = 84 * scale
    logo.render(p, QRectF((w - size) / 2, h * 0.2, size, size))

    p.setPen(TEXT)
    p.setFont(_font(19 * scale, QFont.Weight.DemiBold))
    title_top = h * 0.2 + size + 16 * scale
    p.drawText(QRectF(0, title_top, w, 28 * scale), Qt.AlignmentFlag.AlignHCenter, "Project-On")
    p.setPen(MUTED)
    p.setFont(_font(8.5 * scale, QFont.Weight.Medium))
    p.drawText(
        QRectF(8 * scale, title_top + 30 * scale, w - 16 * scale, 40 * scale),
        Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap,
        "Projection pour églises",
    )

    # A soft golden beam across the panel, echoing the mark's stroke.
    beam = QLinearGradient(0, 0, w, 0)
    beam.setColorAt(0, QColor(243, 182, 74, 0))
    beam.setColorAt(0.5, QColor(243, 182, 74, 90))
    beam.setColorAt(1, QColor(243, 182, 74, 0))
    p.fillRect(QRectF(0, title_top + 58 * scale, w, 2 * scale), beam)

    pen = QPen(GOLD, 2 * scale)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    y = h - 30 * scale
    p.drawLine(QPointF(w / 2 - 14 * scale, y), QPointF(w / 2 + 14 * scale, y))
    p.end()
    return img


def draw_small(scale: float, logo: QSvgRenderer) -> QImage:
    w, h = round(SMALL[0] * scale), round(SMALL[1] * scale)
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    inset = 4 * scale
    logo.render(p, QRectF(inset, inset, w - 2 * inset, h - 2 * inset))
    p.end()
    return img


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication([])
    logo = QSvgRenderer(str(MARK))
    if not logo.isValid():
        raise RuntimeError(f"Invalid SVG logo: {MARK}")
    OUT.mkdir(parents=True, exist_ok=True)
    for pct in SCALES:
        for name, draw in (("wizard", draw_large), ("small", draw_small)):
            path = OUT / f"{name}-{pct}.bmp"
            if not draw(pct / 100, logo).save(str(path), "BMP"):
                raise RuntimeError(f"Could not write {path}")
            print(f"Wrote {path.relative_to(ROOT)}")
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
