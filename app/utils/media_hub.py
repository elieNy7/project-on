"""Lecteur vidéo partagé : un seul décodage pour toutes les sorties.

La projection plein écran garde son lecteur natif (fluide, matériel, avec le
son). Les autres sorties — aperçu opérateur, mixeur HDMI, NDI — reçoivent les
images de ce hub : la vidéo y est donc réellement lue, sans décoder plusieurs
fois le même fichier ni désynchroniser les écrans.

Chaque image est normalisée à la résolution de référence de l'application
(1920×1080, bandes noires autour si la vidéo a un autre format) : tous les
consommateurs n'ont plus qu'à la dessiner telle quelle.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)

__all__ = ["MediaPlaybackHub", "FRAME_WIDTH", "FRAME_HEIGHT", "shared_hub"]

FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080

_hub: "MediaPlaybackHub | None" = None


def shared_hub() -> "MediaPlaybackHub":
    """Hub unique du processus (créé au premier appel, thread GUI)."""
    global _hub
    if _hub is None:
        _hub = MediaPlaybackHub()
    return _hub


def _reset_shared_hub() -> None:
    """Pour les tests : oublie l'instance courante."""
    global _hub
    _hub = None


class MediaPlaybackHub(QObject):
    """Un ``QMediaPlayer`` sans son, dont les images servent toutes les sorties."""

    frameReady = Signal()
    endOfMedia = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player: Any = None
        self._sink: Any = None
        self._audio_output: Any = None
        self._audio_enabled = False
        self._available: bool | None = None
        self._active_path = ""
        self._loop = False
        self._playing = False
        self._image: Any = None  # QImage de la dernière image normalisée
        self._bgra: Any = None  # version numpy, seulement si demandée
        self._numpy_enabled = False
        self._lock = threading.Lock()

    # ── État ──────────────────────────────────────────────────────────────

    @property
    def active_path(self) -> str:
        return self._active_path

    @property
    def is_playing(self) -> bool:
        return self._playing

    def available(self) -> bool:
        """QtMultimedia présent ? (faux : le hub devient inerte, sans erreur)"""
        if self._available is None:
            self._available = self._ensure_player()
        return bool(self._available)

    # ── Commandes ─────────────────────────────────────────────────────────

    def load(self, path: str) -> None:
        """Charge une source ; ne fait rien si c'est déjà la source courante."""
        normalized = str(path or "").strip()
        if not normalized:
            self.stop()
            return
        if not self.available():
            return
        from PySide6.QtCore import QUrl

        if normalized == self._active_path:
            return
        self._active_path = normalized
        with self._lock:
            self._image = None
            self._bgra = None
        self._playing = False
        self._player.setSource(QUrl.fromLocalFile(str(Path(normalized))))
        self.frameReady.emit()

    def play(self) -> None:
        if not self.available() or not self._active_path:
            return
        from PySide6.QtMultimedia import QMediaPlayer

        self._playing = True
        if self._player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self._player.play()

    def pause(self) -> None:
        if not self.available() or not self._active_path:
            return
        from PySide6.QtMultimedia import QMediaPlayer

        self._playing = False
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()

    def restart(self) -> None:
        """Retour au début, en pause (bouton Stop de l'opérateur)."""
        if not self.available() or not self._active_path:
            return
        self._playing = False
        self._player.pause()
        self._player.setPosition(0)

    def set_loop(self, loop: bool) -> None:
        self._loop = bool(loop)

    def set_audio_enabled(self, enabled: bool) -> None:
        """Prend (ou rend) la bande son de la vidéo.

        Le son sort normalement par la fenêtre de projection, qui possède son
        propre lecteur. Si cette fenêtre est fermée — régie pour un mélangeur
        HDMI ou un envoi NDI, sans projecteur local — le hub devient la source
        audio pour que la vidéo ne soit jamais muette.
        """
        enabled = bool(enabled)
        if enabled == self._audio_enabled:
            return
        self._audio_enabled = enabled
        if not self.available():
            return
        try:
            if enabled:
                if self._audio_output is None:
                    from PySide6.QtMultimedia import QAudioOutput

                    self._audio_output = QAudioOutput(self)
                    self._audio_output.setVolume(1.0)
                self._player.setAudioOutput(self._audio_output)
            else:
                self._player.setAudioOutput(None)
        except Exception:  # pragma: no cover - dépend de l'installation
            log.exception("Sortie audio du lecteur partagé indisponible")

    def stop(self) -> None:
        """Quitte le mode vidéo : plus de source, plus d'image."""
        self._active_path = ""
        self._playing = False
        if self._player is not None:
            from PySide6.QtCore import QUrl

            self._player.stop()
            self._player.setSource(QUrl())
        with self._lock:
            self._image = None
            self._bgra = None
        self.frameReady.emit()

    def set_numpy_enabled(self, enabled: bool) -> None:
        """Active la copie numpy (utile seulement pour la sortie NDI)."""
        self._numpy_enabled = bool(enabled)
        if not enabled:
            with self._lock:
                self._bgra = None

    # ── Images ────────────────────────────────────────────────────────────

    def latest_image(self) -> Any:
        """Dernière image normalisée (QImage), ou ``None``."""
        with self._lock:
            return self._image

    def latest_bgra(self) -> Any:
        """Dernière image en numpy BGRA ``(1080, 1920, 4)``, ou ``None``."""
        with self._lock:
            return self._bgra

    # ── Interne ───────────────────────────────────────────────────────────

    def _ensure_player(self) -> bool:
        if self._player is not None:
            return True
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QVideoSink
        except Exception as exc:  # pragma: no cover - dépend de l'installation
            log.warning("QtMultimedia indisponible pour le partage vidéo : %s", exc)
            return False
        try:
            self._sink = QVideoSink(self)
            self._player = QMediaPlayer(self)
            # Le son n'est branché que si la régie n'a pas de fenêtre de
            # projection : sinon deux lecteurs joueraient la même bande son.
            self._player.setVideoSink(self._sink)
            if self._audio_enabled:
                from PySide6.QtMultimedia import QAudioOutput

                self._audio_output = QAudioOutput(self)
                self._audio_output.setVolume(1.0)
                self._player.setAudioOutput(self._audio_output)
            self._sink.videoFrameChanged.connect(self._on_frame)
            self._player.mediaStatusChanged.connect(self._on_status)
        except Exception as exc:  # pragma: no cover
            log.warning("Initialisation du lecteur vidéo partagé impossible : %s", exc)
            self._player = None
            self._sink = None
            return False
        return True

    def _on_frame(self, frame) -> None:
        if not self._active_path:
            # Images tardives après un arrêt : rien à projeter.
            return
        try:
            if not frame.isValid():
                return
            image = frame.toImage()
        except Exception:
            return
        if image.isNull():
            return
        image = self._normalize(image)
        bgra = self._to_bgra(image) if self._numpy_enabled else None
        with self._lock:
            self._image = image
            self._bgra = bgra
        self.frameReady.emit()

    @staticmethod
    def _normalize(image):
        """Ramène l'image au format de référence, bandes noires comprises."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage

        if image.width() == FRAME_WIDTH and image.height() == FRAME_HEIGHT:
            return image
        canvas = QImage(FRAME_WIDTH, FRAME_HEIGHT, QImage.Format.Format_RGB32)
        canvas.fill(Qt.GlobalColor.black)
        scaled = image.scaled(
            FRAME_WIDTH,
            FRAME_HEIGHT,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        from PySide6.QtGui import QPainter

        painter = QPainter(canvas)
        painter.drawImage(
            (FRAME_WIDTH - scaled.width()) // 2,
            (FRAME_HEIGHT - scaled.height()) // 2,
            scaled,
        )
        painter.end()
        return canvas

    @staticmethod
    def _to_bgra(image):
        """Copie numpy BGRA (format demandé par la sortie NDI)."""
        try:
            import numpy as np
            from PySide6.QtGui import QImage
        except Exception:  # pragma: no cover - numpy manquant
            return None
        converted = image.convertToFormat(QImage.Format.Format_ARGB32)
        width, height = converted.width(), converted.height()
        pointer = converted.constBits()
        if pointer is None:
            return None
        # bytes() COPIE les pixels : le tableau numpy ne dépend plus du
        # QImage, libéré dès la fin de cette fonction (un simple frombuffer
        # laisserait un pointeur vers une mémoire libérée).
        raw = np.frombuffer(
            bytes(pointer[: converted.sizeInBytes()]), dtype=np.uint8
        )
        stride = converted.bytesPerLine()
        rows = raw.reshape(height, stride // 4, 4)
        # ARGB32 est stocké BGRA en mémoire petit-boutiste : aucun échange.
        return rows[:, :width, :].copy()

    def _on_status(self, status) -> None:
        from PySide6.QtMultimedia import QMediaPlayer

        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        if self._loop:
            self._player.setPosition(0)
            self._player.play()
            return
        self._playing = False
        self._player.pause()
        self._player.setPosition(0)
        self.endOfMedia.emit()
