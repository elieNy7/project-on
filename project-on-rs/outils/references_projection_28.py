"""Les références de mise en page de la projection 2.8 (phase 2, comparées par `po-parite`).

Le vrai `SlideCanvas` de la 2.8 met en page, en mémoire (le canevas n'est jamais affiché : aucune
fenêtre ne s'ouvre), de vrais paragraphes, strophes et versets d'une COPIE de la base, avec plusieurs réglages. Pour
chaque slide, il note la taille retenue, les lignes, et la place du texte, de la référence et du
filet. Quelques captures servent à comparer à l'œil.

    py -3.14 outils/references_projection_28.py <copie de project_on.db> <dossier de sortie>

Il faut le Python qui a PySide6 (`py -3.14` sur le poste de développement).
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

# La vraie plateforme Windows : ses polices passent par DirectWrite, comme la 2.8 installée. La
# plateforme « offscreen » mesurerait le texte avec FreeType, qui donne d'autres largeurs.
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QFont, QFontMetrics, QFontMetricsF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication([])

from app.ui.slide_canvas import SlideCanvas  # noqa: E402
from app.utils.font_loader import load_fonts  # noqa: E402
from app.utils.settings import AppSettings, ProjectionSettings  # noqa: E402

SHORT = [
    "Amen",
    "Bienvenue à tous",
    "Jésus-Christ est le même hier, aujourd'hui et éternellement",
    "Il a dit : « Amen ! » Et voilà… le Seigneur vient ; gloire !",
]


def user_projection() -> ProjectionSettings:
    path = Path(os.environ.get("APPDATA", "")) / "Project-On" / "data" / "settings.json"
    return AppSettings.load(path).projection if path.is_file() else ProjectionSettings()


def configs() -> dict[str, dict]:
    user = user_projection()
    base = user.to_presentation_config()
    # Les fonds viennent de la 3.0 elle-même (phase 2) : ici, seule la place du texte compte.
    base["bg_mode"] = "color"
    variants = {"utilisateur": base}
    variants["reference_bas_ombre"] = {**base, "reference_position": "bottom", "text_shadow": True, "shadow_blur": 18}
    variants["poppins_gauche"] = {
        **base, "font_family": "Poppins", "align": "left", "uppercase": False, "text_size": 56,
        "ref_size": 24, "line_height": 1.12, "safe_margin": 80, "font_weight": "bold",
    }
    # « show_reference: False » n'est pas mesurable : en plein écran, la 2.8 plante alors
    # (`available_height` jamais calculée dans `_apply_layout_metrics`).
    return variants


def slides(conn: sqlite3.Connection) -> list[dict]:
    out = []
    rows = conn.execute(
        "SELECT p.text, s.date, COALESCE(NULLIF(s.canonical_title, ''), s.title), p.marker "
        "FROM sermon_paragraph p JOIN sermon s ON s.id = p.sermon_id "
        "WHERE p.id % 2000 = 7 ORDER BY p.id").fetchall()
    for text, date, title, marker in rows:
        out.append({"kind": "sermon", "source": "sermon", "text": text, "reference": f"{date} - {title} - {marker}"})
    rows = conn.execute(
        "SELECT hs.text, h.number, COALESCE(NULLIF(h.canonical_title, ''), h.title) "
        "FROM hymn_stanza hs JOIN hymn h ON h.id = hs.hymn_id WHERE hs.id % 40 = 3 ORDER BY hs.id").fetchall()
    for text, number, title in rows:
        out.append({"kind": "hymn", "source": "hymn", "text": text, "reference": f"{number or ''} - {title}".strip(" -")})
    rows = conn.execute(
        "SELECT text, COALESCE(book_name, book), chapter, verse FROM bible_translation_verse "
        "WHERE id % 2000 = 11 ORDER BY id").fetchall()
    for text, book, chapter, verse in rows:
        out.append({"kind": "bible", "source": "bible", "text": text, "reference": f"{book} {chapter}:{verse}"})
    for index, text in enumerate(SHORT):
        out.append({"kind": "court", "source": "custom", "text": text, "reference": "" if index % 2 else "Annonce"})
    return out


def placed_lines(canvas: SlideCanvas, label) -> dict | None:
    """Les lignes posées par `ShadowTextLabel._draw_lines`, en coordonnées de l'écran."""
    text = label.text()
    if not text or not label.isVisibleTo(canvas):
        return None
    origin = label.mapTo(canvas, QPoint(0, 0))
    rect = label.contentsRect()
    metrics = QFontMetrics(label.font())
    step = metrics.lineSpacing() * label._line_height
    lines = text.split("\n")
    block = metrics.height() + step * (len(lines) - 1)
    align = label.alignment()
    if align & Qt.AlignmentFlag.AlignTop:
        top = rect.top()
    elif align & Qt.AlignmentFlag.AlignBottom:
        top = rect.bottom() - block
    else:
        top = rect.top() + (rect.height() - block) / 2
    return {
        "size": label.font().pixelSize(),
        "lines": lines,
        "baseline": origin.y() + top + metrics.ascent(),
        "step": step,
        "label": [origin.y(), label.height(), rect.top(), rect.height()],
        "left": origin.x() + rect.left(),
        "right": origin.x() + rect.left() + rect.width(),
    }


def font_metrics() -> list[dict]:
    """Les mesures de Qt pour les polices des réglages : la 3.0 compare les siennes."""
    out = []
    for family in ("Passion One", "Poppins"):
        for weight, qt_weight in ((700, QFont.Weight.Bold), (600, QFont.Weight.DemiBold)):
            for size in (21, 24, 40, 100, 180):
                font = QFont(family)
                font.setWeight(qt_weight)
                font.setPixelSize(size)
                m, mf = QFontMetrics(font), QFontMetricsF(font)
                out.append({
                    "family": family, "weight": weight, "size": size, "ascent": m.ascent(),
                    "descent": m.descent(), "height": m.height(), "line_spacing": m.lineSpacing(),
                    "leading": m.leading(), "ascent_f": mf.ascent(), "descent_f": mf.descent(),
                    "line_spacing_f": mf.lineSpacing(),
                    "advances": {w: m.horizontalAdvance(w) for w in ("AMEN", "ET CETTE SEMAINE", "Jean 3:16", " ")},
                    "advances_f": {w: mf.horizontalAdvance(w) for w in ("AMEN", "ET CETTE SEMAINE", "Jean 3:16", " ")},
                })
    return out


def main() -> None:
    source, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    (out / "captures").mkdir(parents=True, exist_ok=True)
    load_fonts()
    conn = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    cases = slides(conn)
    results = []
    for name, cfg in configs().items():
        canvas = SlideCanvas()
        canvas.resize(1920, 1080)
        canvas.apply_config(cfg)

        shots = 0
        for index, slide in enumerate(cases):
            canvas.set_slide(slide)
            # `grab()` rend le canevas en mémoire, sans l'afficher : Qt applique alors toute la mise
            # en page (un widget jamais affiché garde sinon des positions par défaut).
            image = canvas.render_pixmap(slide)
            accent = canvas._accent_line
            accent_rect = None
            if accent.isVisibleTo(canvas) and canvas._ref_zone.isVisibleTo(canvas):
                p = accent.mapTo(canvas, QPoint(0, 0))
                accent_rect = [p.x(), p.y(), accent.width(), accent.height()]
            results.append({
                "config": name, "index": index, "kind": slide["kind"], "source": slide["source"],
                "text": slide["text"], "reference": slide["reference"],
                "texte": placed_lines(canvas, canvas.text_label),
                "reference_posee": placed_lines(canvas, canvas.ref_label),
                "filet": accent_rect,
            })
            if name == "utilisateur" and index % 60 == 0 and shots < 12:
                image.save(str(out / "captures" / f"28-{index:04d}.png"))
                shots += 1
    (out / "projection.json").write_text(
        json.dumps({"configs": configs(), "polices": font_metrics(), "cas": results}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"{len(results)} mises en page de la 2.8 : {out}")


if __name__ == "__main__":
    main()
