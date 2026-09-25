"""Film a short demo of the real Project-On window for the website.

The application runs hidden (WA_DontShowOnScreen) in the same throw-away
sandbox as tools/capture_site.py: nothing appears on screen and data/,
presentation/ and the user profile are never touched. Each step drives the
real widgets, the window is grabbed, then a cursor, click ripples and
captions are drawn on top and the frames are piped to ffmpeg.

Run:  py -3 tools/record_demo.py
Out:  docs/assets/demo.mp4 (1280x752, H.264, music from docs/music.wav)
      docs/assets/demo-poster.jpg
"""
from __future__ import annotations

import math
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import capture_site as cs  # noqa: E402  (isolates the app paths on import)

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QFont,
    QFontDatabase,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)
from PySide6.QtSvg import QSvgRenderer  # noqa: E402
from PySide6.QtWidgets import QApplication, QListWidget, QWidget  # noqa: E402

ROOT = cs.ROOT
OUT = ROOT / "docs" / "assets" / "demo.mp4"
POSTER = ROOT / "docs" / "assets" / "demo-poster.jpg"
MUSIC = ROOT / "docs" / "music.wav"
MARK = ROOT / "assets" / "logo" / "project-on-mark.svg"
FPS = 30
W, H = 1280, 752

NAVY = QColor("#0B1222")
GOLD = QColor("#F3B64A")
TEXT = QColor("#F5F7FA")
MUTED = QColor("#AAB4C5")


def ease(t: float) -> float:
    return 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, t)))


class Recorder:
    def __init__(self, win: QWidget, family: str) -> None:
        self.win = win
        self.family = family
        self.frames = 0
        self.base: QImage | None = None
        self.prev: QImage | None = None
        self.fade = 0
        self.cursor = QPointF(W * 0.6, H * 0.55)
        self.cursor_visible = True
        self.ripples: list[list[float]] = []  # [x, y, age]
        self.caption = ""
        self.step = ""
        self.caption_age = 0
        self.poster: QImage | None = None
        ffmpeg = shutil.which("ffmpeg") or _imageio_ffmpeg()
        self.silent = OUT.with_suffix(".silent.mp4")
        self.proc = subprocess.Popen(
            [
                ffmpeg, "-y", "-loglevel", "error",
                "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                "-c:v", "libx264", "-preset", "slow", "-crf", "24", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(self.silent),
            ],
            stdin=subprocess.PIPE,
        )
        self.ffmpeg = ffmpeg

    # ── Window ──

    def refresh(self, fade: bool = True) -> None:
        pix = self.win.grab()
        img = pix.toImage().scaled(
            W, H, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
        ).convertToFormat(QImage.Format.Format_RGB32)
        if fade and self.base is not None:
            self.prev, self.fade = self.base, 8
        self.base = img

    def pos(self, widget: QWidget, local: QPointF | None = None) -> QPointF:
        """Position of a widget point in video coordinates."""
        point = widget.rect().center() if local is None else local.toPoint()
        mapped = widget.mapTo(self.win, point)
        return QPointF(mapped.x() * W / self.win.width(), mapped.y() * H / self.win.height())

    def row_pos(self, lst: QListWidget, row: int) -> QPointF:
        row = min(row, lst.count() - 1)
        item = lst.item(row)
        lst.scrollToItem(item)
        rect = lst.visualItemRect(item)
        center = QPointF(rect.left() + min(rect.width() * 0.35, 220), rect.center().y())
        return self.pos(lst.viewport(), center)

    # ── Timeline ──

    def say(self, step: str, text: str) -> None:
        self.step, self.caption, self.caption_age = step, text, 0

    def hold(self, seconds: float) -> None:
        for _ in range(max(1, round(seconds * FPS))):
            self._emit()

    def move(self, target: QPointF, seconds: float = 0.7) -> None:
        start = QPointF(self.cursor)
        n = max(1, round(seconds * FPS))
        for i in range(1, n + 1):
            t = ease(i / n)
            self.cursor = start + (target - start) * t
            self._emit()

    def click(self, action=None, settle: float = 0.8, fade: bool = True) -> None:
        self.ripples.append([self.cursor.x(), self.cursor.y(), 0])
        self.hold(0.12)
        if action is not None:
            action()
            cs.drain(settle)
            self.refresh(fade)

    def card(self, title: str, lines: list[str], seconds: float, fade_in: bool, fade_out: bool) -> None:
        n = round(seconds * FPS)
        for i in range(n):
            img = QImage(W, H, QImage.Format.Format_RGB32)
            p = QPainter(img)
            p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
            bg = QLinearGradient(0, 0, 0, H)
            bg.setColorAt(0, QColor("#17243A"))
            bg.setColorAt(1, NAVY)
            p.fillRect(0, 0, W, H, bg)
            glow = QRadialGradient(QPointF(W / 2, H * 0.9), W * 0.6)
            glow.setColorAt(0, QColor(243, 182, 74, 40))
            glow.setColorAt(1, QColor(243, 182, 74, 0))
            p.fillRect(0, 0, W, H, glow)
            QSvgRenderer(str(MARK)).render(p, QRectF(W / 2 - 56, H * 0.24, 112, 112))
            p.setFont(self._font(54, QFont.Weight.DemiBold))
            fm = p.fontMetrics()
            x = (W - fm.horizontalAdvance(title + "-On")) / 2
            p.setPen(TEXT)
            p.drawText(QPointF(x, H * 0.24 + 190), title)
            p.setPen(GOLD)
            p.drawText(QPointF(x + fm.horizontalAdvance(title), H * 0.24 + 190), "-On")
            p.setFont(self._font(22, QFont.Weight.Medium))
            p.setPen(MUTED)
            for k, line in enumerate(lines):
                p.drawText(QRectF(0, H * 0.24 + 220 + k * 36, W, 34), Qt.AlignmentFlag.AlignHCenter, line)
            # the logo's beam, drawn in
            grow = ease(min(1.0, i / (0.6 * FPS)))
            pen = QPen(GOLD, 5)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(W / 2 - 70 * grow, H * 0.24 + 214), QPointF(W / 2 + 70 * grow, H * 0.24 + 214))
            alpha = 1.0
            if fade_in:
                alpha = min(alpha, i / 12)
            if fade_out:
                alpha = min(alpha, (n - 1 - i) / 12)
            if alpha < 1:
                p.fillRect(0, 0, W, H, QColor(0, 0, 0, round(255 * (1 - max(0.0, alpha)))))
            p.end()
            self._write(img)

    # ── Drawing ──

    def _font(self, px: int, weight: QFont.Weight) -> QFont:
        f = QFont(self.family)
        f.setPixelSize(px)
        f.setWeight(weight)
        return f

    def _emit(self) -> None:
        frame = self.base.copy()
        p = QPainter(frame)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        if self.fade > 0 and self.prev is not None:
            p.setOpacity(self.fade / 9)
            p.drawImage(0, 0, self.prev)
            p.setOpacity(1)
            self.fade -= 1
        for r in self.ripples:
            t = r[2] / 14
            p.setPen(QPen(QColor(243, 182, 74, round(230 * (1 - t))), 3))
            p.setBrush(QColor(243, 182, 74, round(70 * (1 - t))))
            radius = 6 + 26 * t
            p.drawEllipse(QPointF(r[0], r[1]), radius, radius)
            r[2] += 1
        self.ripples = [r for r in self.ripples if r[2] <= 14]
        if self.caption:
            self._draw_caption(p)
        if self.cursor_visible:
            self._draw_cursor(p)
        p.end()
        self._write(frame)

    def _draw_caption(self, p: QPainter) -> None:
        a = min(1.0, self.caption_age / 8)
        self.caption_age += 1
        p.setFont(self._font(22, QFont.Weight.DemiBold))
        fm = p.fontMetrics()
        text_w = fm.horizontalAdvance(self.caption)
        box_w = text_w + 96
        box = QRectF((W - box_w) / 2, H - 92 + 10 * (1 - a), box_w, 56)
        p.setOpacity(a)
        path = QPainterPath()
        path.addRoundedRect(box, 28, 28)
        p.fillPath(path, QColor(11, 18, 34, 235))
        p.setPen(QPen(QColor(245, 247, 250, 36), 1))
        p.drawPath(path)
        badge = QRectF(box.left() + 12, box.top() + 12, 32, 32)
        p.setBrush(GOLD)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(badge)
        p.setPen(NAVY)
        p.setFont(self._font(17, QFont.Weight.Bold))
        p.drawText(badge, Qt.AlignmentFlag.AlignCenter, self.step)
        p.setPen(TEXT)
        p.setFont(self._font(22, QFont.Weight.DemiBold))
        p.drawText(QRectF(box.left() + 60, box.top(), text_w + 10, box.height()),
                   Qt.AlignmentFlag.AlignVCenter, self.caption)
        p.setOpacity(1)

    def _draw_cursor(self, p: QPainter) -> None:
        x, y = self.cursor.x(), self.cursor.y()
        s = 1.25
        pts = [(0, 0), (0, 17), (4.5, 13), (7.5, 20), (10, 19), (7, 12), (13, 12)]
        poly = QPolygonF([QPointF(x + px * s, y + py * s) for px, py in pts])
        p.setPen(QPen(QColor(0, 0, 0, 90), 4))
        p.drawPolygon(poly.translated(1.5, 2))
        p.setPen(QPen(QColor("#111A2E"), 1.6))
        p.setBrush(QColor("white"))
        p.drawPolygon(poly)

    def _write(self, img: QImage) -> None:
        # Poster: just after « F2 », Aperçu and Direct both filled.
        if self.poster is None and self.step == "3" and self.caption_age == 75:
            self.poster = img.copy()
        self.proc.stdin.write(bytes(img.constBits()))
        self.frames += 1

    def finish(self) -> None:
        self.proc.stdin.close()
        self.proc.wait()
        if self.proc.returncode:
            raise RuntimeError("ffmpeg failed while encoding the frames")
        duration = self.frames / FPS
        if MUSIC.exists():
            subprocess.run(
                [
                    self.ffmpeg, "-y", "-loglevel", "error", "-i", str(self.silent), "-i", str(MUSIC),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                    "-af", f"volume=0.55,afade=t=in:d=1.2,afade=t=out:st={duration - 2.5:.2f}:d=2.5",
                    "-t", f"{duration:.2f}", "-movflags", "+faststart", str(OUT),
                ],
                check=True,
            )
            self.silent.unlink()
        else:
            self.silent.replace(OUT)
        if self.poster is not None:
            self.poster.save(str(POSTER), "JPG", 88)
        print(f"Wrote {OUT.relative_to(ROOT)} ({duration:.1f} s, {OUT.stat().st_size / 1e6:.1f} Mo)")


def _imageio_ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication([])

    from app.database.connection import Database
    from app.ui.setting_cards import SettingRow
    from app.ui.theme import build_app_stylesheet, set_theme, set_window_backdrop
    from app.ui.window_effects import apply_color_scheme
    from app.utils.font_loader import load_fonts
    from app.utils.translations import set_language

    set_theme("dark")
    set_language("fr")
    apply_color_scheme(app, "dark")
    set_window_backdrop(False)
    load_fonts()
    app.setStyleSheet(build_app_stylesheet())
    family = "Segoe UI"
    for path in sorted((ROOT / "assets" / "fonts" / "Poppins").glob("Poppins-*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            family = QFontDatabase.applicationFontFamilies(font_id)[0]

    from app.ui.main_window import MainWindow

    MainWindow._open_local_projection = lambda self: None
    MainWindow._start_obs_output = lambda self: None
    MainWindow._poll_obs_status = lambda self: None
    MainWindow._show_operator_warning = lambda self, title, message: print("[warn]", title)

    db = Database.default()
    db.initialize()
    cs.seed_demo(db)

    win = MainWindow(db=db)
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    win.resize(1600, 940)
    win.show()
    cs.drain(2.0)

    rail, panel = win.rail, win.library_panel
    bible = panel.bible_tab
    rail.setCurrentIndex(0)
    bible.select_book(43)
    cs.drain(1.5)

    rec = Recorder(win, family)
    rec.card("Project", ["Préparez dans l’Aperçu. Projetez en Direct.", "Démo de la version 2.6"], 3.0, True, True)
    rec.refresh(fade=False)
    rec.hold(0.6)

    # 1. Chapter
    rec.say("1", "Choisissez un chapitre")
    rec.move(rec.pos(bible._chapter_buttons[3]), 0.9)
    rec.click(bible._chapter_buttons[3].click, 1.5)
    rec.hold(0.9)

    # 2. One click prepares
    verses = bible.verses_list
    rec.say("2", "Un clic prépare le verset dans l’Aperçu")
    target = rec.row_pos(verses, 15)
    cs.drain(0.3)
    rec.refresh(fade=False)
    rec.move(target, 0.9)
    rec.click(lambda: cs.click_row(verses, 15), 1.0)
    rec.hold(1.8)

    # 3. F2 sends it live
    take = win.cue_monitor._take_button
    rec.say("3", "F2 (ou ce bouton) l’envoie au Direct")
    rec.move(rec.pos(take), 0.9)
    rec.click(take.click, 1.0)
    rec.hold(2.0)

    # 4. Prepare the next one while live
    rec.say("4", "Préparez la suite pendant le direct")
    rec.move(rec.row_pos(verses, 16), 0.8)
    rec.click(lambda: cs.click_row(verses, 16), 1.0)
    rec.hold(2.2)

    # 5. Global search
    field = win.command_bar.search_edit
    rec.say("5", "Ctrl+K : cherchez une référence ou des mots")
    rec.move(rec.pos(field, QPointF(140, field.height() / 2)), 0.9)
    rec.click(field.setFocus, 0.2, fade=False)
    typed = ""
    for ch in "Ps 23:1":
        typed += ch
        field.setText(typed)
        field.textEdited.emit(typed)
        cs.drain(0.06)
        rec.refresh(fade=False)
        rec.hold(0.11)
    cs.drain(2.0)
    rec.refresh()
    rec.hold(1.0)
    hits = win._search_popup._list
    hit_row = next(
        (r for r in range(hits.count()) if hits.item(r).flags() & Qt.ItemFlag.ItemIsSelectable),
        0,
    )
    rec.move(rec.row_pos(hits, hit_row), 0.6)
    rec.click(win._search_popup._activate_current, 1.5)
    field.clear()
    cs.drain(0.3)
    rec.refresh()
    rec.hold(2.0)

    # 6. Libraries
    rec.say("6", "Cantiques, prédications, livres, médias…")
    items = rail._items
    rec.move(rec.pos(items[1]), 0.8)
    rec.click(lambda: rail._on_clicked(1), 1.8)
    hymn_lists = [w for w in panel.hymns_tab.findChildren(QListWidget) if w.isVisible()]
    if hymn_lists:
        rec.move(rec.row_pos(hymn_lists[0], 2), 0.6)
        rec.click(lambda: cs.click_row(hymn_lists[0], 2), 1.2)
    rec.hold(1.2)

    sermons = panel.sermons_tab
    rec.move(rec.pos(items[2]), 0.6)
    rec.click(lambda: rail._on_clicked(2), 2.2)
    rec.move(rec.row_pos(sermons.sermons_list, 8), 0.6)
    rec.click(lambda: cs.click_row(sermons.sermons_list, 8), 2.2)
    rec.move(rec.row_pos(sermons.paragraphs_list, 4), 0.6)
    rec.click(lambda: cs.click_row(sermons.paragraphs_list, 4), 1.0)
    rec.hold(1.4)

    books = panel.expose_tab
    rec.move(rec.pos(items[3]), 0.6)

    def open_book() -> None:
        rail._on_clicked(3)
        cs.drain(1.5)
        combo = books.book_combo
        for i in range(combo.count()):
            if "envoyé" in combo.itemText(i).lower():
                combo.setCurrentIndex(i)
                break
        cs.drain(2.0)
        cs.click_row(books.chapters_list, 1)

    rec.click(open_book, 2.2)
    rec.hold(1.6)

    rec.move(rec.pos(items[4]), 0.6)
    rec.click(lambda: (rail._on_clicked(4), win._library_controller.refresh_media()), 1.6)
    rec.hold(1.4)

    # 7. Settings, applied at once
    rec.say("7", "Réglages appliqués aussitôt, sous vos yeux")
    rec.move(rec.pos(items[6]), 0.8)
    rec.click(lambda: rail._on_clicked(6), 1.0)
    page = panel.settings_page
    nav = page._sections["projection"].item
    rec.move(rec.pos(nav), 0.7)
    rec.click(lambda: page.show_section("projection"), 1.2)
    row = next(
        (r for r in page.current_widget().findChildren(SettingRow)
         if "MAJUSCULES" in r.title_label.text().upper() and r._toggle is not None),
        None,
    )
    if row is not None:
        page._host.ensureWidgetVisible(row, 0, 120)
        cs.drain(0.4)
        rec.refresh()
        rec.hold(0.6)
        rec.move(rec.pos(row._toggle), 0.9)
        rec.click(row._toggle.toggle, 1.0)
        rec.hold(2.4)

    rec.caption = ""
    rec.hold(0.4)
    rec.cursor_visible = False
    rec.card("Project", ["Gratuit · Hors-ligne · Windows 10 / 11", "elieny7.github.io/project-on"], 3.6, True, True)
    rec.finish()

    win.close()
    cs.drain(0.5)
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(5000)
    return 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(cs.SANDBOX, ignore_errors=True)
    raise SystemExit(code)
