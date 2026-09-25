"""Captures réelles de Project-On pour le site (rendu Qt exact, données réelles).

Usage :
    py -3 tools/capture_site.py            # thème sombre : toutes les captures
    py -3 tools/capture_site.py --light    # thème clair : vue principale seule

Écrit dans docs/screenshots/. Rien n'apparaît à l'écran : les fenêtres sont
« affichées » avec WA_DontShowOnScreen (plateforme native, vraies polices),
puis grab(). L'application tourne dans un bac à sable temporaire (copie de
la base et des réglages) : data/, presentation/ et le profil utilisateur du
poste ne sont jamais modifiés.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LIGHT = "--light" in sys.argv
SHOTS = ROOT / "docs" / "screenshots"
SIZE = (1600, 940)

# ── Bac à sable : les six fonctions inscriptibles de app_paths ───────────────

SANDBOX = Path(tempfile.mkdtemp(prefix="projecton-capture-"))


def _isolate() -> None:
    user, data, pres = SANDBOX / "user", SANDBOX / "data", SANDBOX / "presentation"
    for d in (user, data, pres):
        d.mkdir(parents=True)
    shutil.copy2(ROOT / "data" / "project_on.db", data / "project_on.db")
    settings = json.loads((ROOT / "data" / "settings.json").read_text(encoding="utf-8"))
    appearance = settings.setdefault("appearance", {})
    appearance["theme"] = "light" if LIGHT else "dark"
    appearance["language"] = "fr"
    appearance["mica"] = False  # grab() ne capture pas le fond Mica
    (data / "settings.json").write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8")
    os.environ["APPDATA"] = os.environ["LOCALAPPDATA"] = str(SANDBOX)

    from app.utils import app_paths

    def ensure(path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path

    replacements = {
        "user_data_dir": lambda: user,
        "data_dir": lambda: data,
        "ensure_presentation_workdir": lambda: pres,
        "ensure_data_initialized": lambda: None,
        "backgrounds_dir": lambda: ensure(user / "backgrounds"),
        "media_dir": lambda: ensure(user / "media"),
    }
    originals = {id(getattr(app_paths, name)): fn for name, fn in replacements.items()}
    for name, fn in replacements.items():
        setattr(app_paths, name, fn)
    for module in list(sys.modules.values()):
        namespace = getattr(module, "__dict__", None)
        if not namespace or module is app_paths:
            continue
        for attr, value in list(namespace.items()):
            if id(value) in originals:
                setattr(module, attr, originals[id(value)])


_isolate()

from PySide6.QtCore import QEvent, QThreadPool, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication, QListWidget  # noqa: E402


def drain(seconds: float = 1.2) -> None:
    """Laisse les workers asynchrones se terminer (event loop manuelle)."""
    app = QApplication.instance()
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        # Without a running event loop, deleteLater() never happens: stale
        # widgets (old chapter buttons) would be painted over the new ones.
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        time.sleep(0.02)


def grab(widget, name: str) -> None:
    pixmap = widget.grab()
    pixmap.save(str(SHOTS / name))
    print(f"[OK] {name} ({pixmap.width()}x{pixmap.height()})")


def click_row(lst: QListWidget, row: int, double: bool = False) -> None:
    row = min(row, lst.count() - 1)
    if row < 0:
        return
    item = lst.item(row)
    lst.setCurrentItem(item)
    lst.scrollToItem(item)
    (lst.itemDoubleClicked if double else lst.itemClicked).emit(item)


def seed_demo(db) -> None:
    """Playlists et médias de démonstration (dans le bac à sable seulement)."""
    from app.database.dao_media import MediaDao
    from app.database.dao_playlist import PlaylistDao
    from app.utils.app_paths import media_dir

    dao = PlaylistDao(db)
    folder = dao.create_folder("Culte du dimanche")
    for ref, text in (
        ("Jean 3:16", "Car Dieu a tant aimé le monde qu'il a donné son Fils unique, "
                      "afin que quiconque croit en lui ne périsse point."),
        ("Psaume 23:1", "L'Éternel est mon berger : je ne manquerai de rien."),
        ("Chœur", "Jésus, Roi des rois, nous t'adorons, remplis nos cœurs de ta joie !"),
        ("Annonce", "Repas d'amour partagé après le culte — venez nombreux !"),
        ("Hébreux 13:8", "Jésus-Christ est le même hier, aujourd'hui, et éternellement."),
    ):
        dao.add_item("custom", ref, text, folder_id=folder)
    dao.create_folder("Louange")

    media = MediaDao(db)
    for name, c1, c2 in (
        ("Bienvenue", "#17243A", "#F3B64A"),
        ("Sainte Cène", "#3b1f0f", "#fdba74"),
        ("Baptême", "#0c4a6e", "#bae6fd"),
        ("Annonce repas", "#14532d", "#bbf7d0"),
    ):
        pm = QPixmap(960, 540)
        pm.fill(QColor(c1))
        painter = QPainter(pm)
        painter.setPen(QColor(c2))
        painter.setFont(QFont("Segoe UI", 44, QFont.Weight.DemiBold))
        painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, name)
        painter.end()
        path = media_dir() / f"demo-{name.lower().replace(' ', '-')}.png"
        pm.save(str(path), "PNG")
        media.add_media(name, str(path), "image")


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication.instance() or QApplication([])

    from app.database.connection import Database
    from app.ui.theme import build_app_stylesheet, set_theme, set_window_backdrop
    from app.ui.window_effects import apply_color_scheme
    from app.utils.font_loader import load_fonts
    from app.utils.translations import set_language

    theme = "light" if LIGHT else "dark"
    set_theme(theme)
    set_language("fr")
    apply_color_scheme(app, theme)
    set_window_backdrop(False)
    load_fonts()
    app.setStyleSheet(build_app_stylesheet())

    from app.ui.main_window import MainWindow

    # Aucune fenêtre ni serveur hors de la capture : pas de projection plein
    # écran, pas de sortie OBS, pas de boîte de dialogue.
    MainWindow._open_local_projection = lambda self: None
    MainWindow._start_obs_output = lambda self: None
    MainWindow._poll_obs_status = lambda self: None
    MainWindow._show_operator_warning = lambda self, title, message: print("[warn]", title)

    db = Database.default()
    db.initialize()
    if not LIGHT:
        seed_demo(db)

    win = MainWindow(db=db)
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    win.resize(*SIZE)
    win.show()
    drain(2.0)

    rail, panel, ctl = win.rail, win.library_panel, win._library_controller

    # Bible : Jean 3:16 en direct, le verset suivant préparé dans l'Aperçu.
    rail.setCurrentIndex(0)
    panel.bible_tab.select_book(43)
    drain(1.5)
    panel.bible_tab._chapter_buttons[3].click()
    drain(1.5)
    verses = panel.bible_tab.verses_list
    click_row(verses, 15, double=True)
    drain(0.8)
    click_row(verses, 16)
    drain(1.2)
    grab(win, "app-light.png" if LIGHT else "ui-main.png")

    if not LIGHT:
        # Recherche globale (Ctrl+K)
        field = win.command_bar.search_edit
        field.setFocus()
        field.setText("Jean 3:16")
        field.textEdited.emit("Jean 3:16")
        drain(3.0)
        grab(win, "ui-search.png")
        win._search_popup.dismiss()
        field.clear()
        drain(0.3)

        # Cantiques : un cantique ouvert, une strophe en Aperçu
        rail.setCurrentIndex(1)
        drain(2.0)
        hymns = panel.hymns_tab
        lists = [w for w in hymns.findChildren(QListWidget) if w.isVisible()]
        if lists:
            click_row(lists[0], 3)
            drain(1.5)
            lists = [w for w in hymns.findChildren(QListWidget) if w.isVisible() and w.count()]
            if len(lists) > 1:
                click_row(lists[-1], 0)
                drain(1.0)
        grab(win, "ui-hymns.png")

        # Prédications : un sermon, un paragraphe en Aperçu
        rail.setCurrentIndex(2)
        drain(2.5)
        sermons = panel.sermons_tab
        click_row(sermons.sermons_list, 8)
        drain(2.5)
        click_row(sermons.paragraphs_list, 4)
        drain(1.2)
        grab(win, "ui-sermons.png")

        # Livres
        rail.setCurrentIndex(3)
        drain(2.5)
        books = panel.expose_tab
        combo = books.book_combo
        for i in range(combo.count()):
            if "envoyé" in combo.itemText(i).lower():
                combo.setCurrentIndex(i)
                break
        drain(2.5)
        click_row(books.chapters_list, 1)
        drain(2.5)
        click_row(books.paragraphs_list, 2)
        drain(1.2)
        grab(win, "ui-books.png")

        # Médias et playlists (données de démonstration du bac à sable)
        rail.setCurrentIndex(4)
        ctl.refresh_media()
        drain(2.0)
        grab(win, "ui-media.png")

        rail.setCurrentIndex(5)
        ctl.refresh_playlists()
        drain(2.0)
        playlist = panel.playlist_tab
        folders = playlist.folders_list
        for row in range(folders.count()):
            if folders.item(row).text().startswith("Culte"):
                click_row(folders, row)
        drain(1.5)
        click_row(playlist.items_list, 1)
        drain(1.0)
        grab(win, "ui-playlists.png")

        # Page Réglages : projection locale et bandeau OBS
        win._show_settings_section("projection")
        drain(1.2)
        grab(win, "ui-settings-projection.png")
        win._show_settings_section("obs_output")
        drain(1.5)
        grab(win, "ui-settings-obs.png")

    win.close()
    drain(0.5)
    QThreadPool.globalInstance().waitForDone(5000)
    return 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(SANDBOX, ignore_errors=True)
    raise SystemExit(code)
