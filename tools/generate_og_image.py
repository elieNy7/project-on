"""Draw the website's link preview image (docs/assets/og-image.png, 1200x630).

Logo, wordmark and tagline on the left, the real operator screen on the
right (docs/screenshots/ui-main.png, from tools/capture_site.py).

Run:  py -3 tools/generate_og_image.py
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
MARK = ROOT / "assets" / "logo" / "project-on-mark.svg"
SHOT = ROOT / "docs" / "screenshots" / "ui-main.png"
OUT = ROOT / "docs" / "assets" / "og-image.png"
FONTS = ROOT / "assets" / "fonts" / "Poppins"

W, H = 1200, 630


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication([])
    family = "Segoe UI"
    for path in sorted(FONTS.glob("Poppins-*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            family = QFontDatabase.applicationFontFamilies(font_id)[0]

    img = QImage(W, H, QImage.Format.Format_RGB32)
    p = QPainter(img)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)

    bg = QLinearGradient(0, 0, 0, H)
    bg.setColorAt(0, QColor("#17243A"))
    bg.setColorAt(1, QColor("#0B1222"))
    p.fillRect(0, 0, W, H, bg)
    glow = QRadialGradient(QPointF(W * 0.9, 0), 520)
    glow.setColorAt(0, QColor(243, 182, 74, 50))
    glow.setColorAt(1, QColor(243, 182, 74, 0))
    p.fillRect(0, 0, W, H, glow)

    # Screenshot, tilted card bleeding off the right edge.
    shot = QImage(str(SHOT))
    card = QRectF(560, 120, 820, 820 * shot.height() / shot.width())
    p.save()
    p.translate(card.center())
    p.rotate(-4)
    p.translate(-card.center())
    clip = QPainterPath()
    clip.addRoundedRect(card, 18, 18)
    p.setClipPath(clip)
    p.drawImage(card, shot)
    p.setClipping(False)
    p.setPen(QPen(QColor(245, 247, 250, 40), 2))
    p.drawRoundedRect(card, 18, 18)
    p.restore()

    QSvgRenderer(str(MARK)).render(p, QRectF(72, 92, 96, 96))

    def font(px: int, weight: QFont.Weight) -> QFont:
        f = QFont(family)
        f.setPixelSize(px)
        f.setWeight(weight)
        return f

    p.setFont(font(58, QFont.Weight.DemiBold))
    p.setPen(QColor("#F5F7FA"))
    p.drawText(QPointF(72, 272), "Project")
    x = 72 + p.fontMetrics().horizontalAdvance("Project")
    p.setPen(QColor("#F3B64A"))
    p.drawText(QPointF(x, 272), "-On")

    p.setFont(font(30, QFont.Weight.Medium))
    p.setPen(QColor("#F5F7FA"))
    p.drawText(QPointF(72, 350), "Préparez dans l’Aperçu.")
    p.drawText(QPointF(72, 394), "Projetez en Direct.")
    beam = QPen(QColor("#F3B64A"), 6)
    beam.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(beam)
    # Underneath, running past the word like the stroke leaving the « P ».
    p.setFont(font(30, QFont.Weight.Medium))
    start = 72 + p.fontMetrics().horizontalAdvance("Projetez ")
    p.drawLine(QPointF(start + 2, 412), QPointF(start + p.fontMetrics().horizontalAdvance("en Direct.") + 40, 412))

    p.setFont(font(19, QFont.Weight.Normal))
    p.setPen(QColor("#AAB4C5"))
    p.drawText(QPointF(72, 480), "Projection gratuite pour églises · Windows")
    p.drawText(QPointF(72, 510), "Bible · Cantiques · Prédications · OBS · HDMI · NDI")
    p.end()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not img.save(str(OUT), "PNG"):
        raise RuntimeError(f"Could not write {OUT}")
    print(f"Wrote {OUT.relative_to(ROOT)}")
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
