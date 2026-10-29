"""Aperçus d'images dessinés hors du fil de l'interface.

Une citation ou une miniature demande 30 à 400 ms de dessin. Dessinées à
chaque frappe dans le fil de l'interface, elles figeaient la fenêtre ; ici
elles partent dans un fil de travail, une à la fois, et seule la plus
récente demande est affichée (les frappes intermédiaires sont sautées).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtGui import QImage

log = logging.getLogger(__name__)


def pil_to_qimage(image: Any) -> QImage:
    """Image PIL → QImage RGB indépendante (utilisable hors du fil de l'interface)."""
    rgb = image.convert("RGB")
    data = rgb.tobytes()
    return QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888).copy()


class _RenderSignals(QObject):
    done = Signal(int, object)  # numéro de demande, QImage ou None


class _RenderJob(QRunnable):
    def __init__(self, signals: _RenderSignals, generation: int, build: Callable[[], Any]):
        super().__init__()
        self.setAutoDelete(True)
        self._signals = signals
        self._generation = generation
        self._build = build

    @Slot()
    def run(self) -> None:
        try:
            image = pil_to_qimage(self._build())
        except Exception:
            log.exception("Aperçu : échec du dessin")
            image = None
        self._signals.done.emit(self._generation, image)


class PreviewRenderer(QObject):
    """Dessine ``build()`` (qui rend une image PIL) en arrière-plan.

    ``build`` ne doit pas toucher aux widgets : lire les champs avant, dans
    le fil de l'interface, et les capturer dans la fonction.
    """

    ready = Signal(QImage)

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        # Créé avant les signaux : à la destruction, Qt détruit les enfants
        # dans l'ordre, donc le pool attend la fin du dessin en cours avant
        # que l'objet de signalisation ne disparaisse.
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._signals = _RenderSignals(self)
        self._signals.done.connect(self._on_done)
        self._generation = 0
        self._busy = False
        self._pending: tuple[int, Callable[[], Any]] | None = None

    def request(self, build: Callable[[], Any]) -> None:
        self._generation += 1
        self._pending = (self._generation, build)
        self._start_next()

    def wait_idle(self) -> None:
        """Attend le dessin en cours : à appeler avant un rendu dans le fil de
        l'interface (export, copie), les polices n'étant pas partageables
        entre deux fils à la fois."""
        self._pool.waitForDone()

    def _start_next(self) -> None:
        if self._busy or self._pending is None:
            return
        generation, build = self._pending
        self._pending = None
        self._busy = True
        self._pool.start(_RenderJob(self._signals, generation, build))

    def _on_done(self, generation: int, image: QImage | None) -> None:
        self._busy = False
        if generation == self._generation and image is not None:
            self.ready.emit(image)
        self._start_next()
