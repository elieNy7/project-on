"""Aperçus dessinés hors du fil de l'interface (app.ui.preview_renderer)."""

from __future__ import annotations

import threading
import time

from PIL import Image
from PySide6.QtCore import QCoreApplication, QElapsedTimer, QEvent, QObject
from PySide6.QtWidgets import QApplication

from app.ui.preview_renderer import PreviewRenderer


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pump(app, until, timeout_ms: int = 10000) -> None:
    timer = QElapsedTimer()
    timer.start()
    while not until() and timer.elapsed() < timeout_ms:
        app.processEvents()
        time.sleep(0.001)


def test_only_latest_request_is_shown_and_ui_thread_is_free() -> None:
    app = _app()
    owner = QObject()
    renderer = PreviewRenderer(owner)
    shown = []
    renderer.ready.connect(shown.append)
    threads = set()

    def build(width: int):
        threads.add(threading.get_ident())
        time.sleep(0.05)
        return Image.new("RGB", (width, 10), (200, 30, 30))

    for width in (11, 12, 13, 14):  # frappes rapides
        renderer.request(lambda w=width: build(w))
    _pump(app, lambda: bool(shown) and not renderer._busy)

    # La 1re demande était déjà partie ; les intermédiaires sont sautées.
    assert [image.width() for image in shown] == [14]
    assert shown[0].pixelColor(0, 0).red() == 200
    assert threading.get_ident() not in threads
    renderer.wait_idle()


def test_failed_render_shows_nothing_and_next_one_works() -> None:
    app = _app()
    owner = QObject()
    renderer = PreviewRenderer(owner)
    shown = []
    renderer.ready.connect(shown.append)

    def broken():
        raise ValueError("photo illisible")

    renderer.request(broken)
    _pump(app, lambda: not renderer._busy, 3000)
    assert shown == []
    renderer.request(lambda: Image.new("RGB", (5, 5)))
    _pump(app, lambda: bool(shown))
    assert shown[0].width() == 5


def test_owner_destroyed_during_render_does_not_crash() -> None:
    app = _app()
    owner = QObject()
    renderer = PreviewRenderer(owner)
    started = threading.Event()

    def slow():
        started.set()
        time.sleep(0.2)
        return Image.new("RGB", (4, 4))

    renderer.request(slow)
    assert started.wait(5)
    owner.deleteLater()  # fenêtre fermée pendant le dessin
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    for _ in range(50):
        app.processEvents()
        time.sleep(0.005)
