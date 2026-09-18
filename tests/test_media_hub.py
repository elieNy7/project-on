"""Lecteur vidéo partagé : normalisation des images et robustesse."""

from __future__ import annotations

import gc
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy  # noqa: E402
from PyQt6.QtGui import QImage  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from app.utils.media_hub import FRAME_HEIGHT, FRAME_WIDTH, MediaPlaybackHub  # noqa: E402


def _app() -> QApplication:
    """QApplication gardée par l'appelant (variable locale) — convention du dépôt."""
    return QApplication.instance() or QApplication([])


def test_normalize_letterboxes_any_video_into_the_reference_frame() -> None:
    app = _app()  # noqa: F841
    # 4:3 dans 16:9 : l'image occupe la hauteur, bandes noires latérales.
    source = QImage(640, 480, QImage.Format.Format_RGB32)
    source.fill(0xFF204060)
    frame = MediaPlaybackHub._normalize(source)
    assert frame.width() == FRAME_WIDTH and frame.height() == FRAME_HEIGHT
    assert frame.pixelColor(10, FRAME_HEIGHT // 2).getRgb()[:3] == (0, 0, 0)
    assert frame.pixelColor(FRAME_WIDTH // 2, FRAME_HEIGHT // 2).getRgb()[:3] == (0x20, 0x40, 0x60)

    # 21:9 dans 16:9 : cette fois les bandes sont en haut et en bas.
    wide = QImage(1280, 540, QImage.Format.Format_RGB32)
    wide.fill(0xFF102030)
    frame = MediaPlaybackHub._normalize(wide)
    assert frame.pixelColor(FRAME_WIDTH // 2, 5).getRgb()[:3] == (0, 0, 0)
    assert frame.pixelColor(FRAME_WIDTH // 2, FRAME_HEIGHT // 2).getRgb()[:3] == (0x10, 0x20, 0x30)


def test_normalize_keeps_a_reference_sized_frame_untouched() -> None:
    app = _app()  # noqa: F841
    source = QImage(FRAME_WIDTH, FRAME_HEIGHT, QImage.Format.Format_RGB32)
    source.fill(0xFF102030)
    assert MediaPlaybackHub._normalize(source) is source


def test_bgra_conversion_is_opaque_and_survives_the_source_image() -> None:
    """La copie numpy ne doit jamais pointer sur une image libérée."""
    app = _app()  # noqa: F841
    image = QImage(64, 32, QImage.Format.Format_RGB32)
    image.fill(0xFF203040)
    array = MediaPlaybackHub._to_bgra(image)
    assert array.shape == (32, 64, 4)
    assert int(array[0, 0, 3]) == 255
    # ARGB32 est stocké BGRA en mémoire : bleu puis vert puis rouge.
    assert tuple(int(v) for v in array[0, 0][:3]) == (0x40, 0x30, 0x20)

    del image
    gc.collect()
    assert int(array[5, 5, 2]) == 0x20  # toujours lisible après libération


def test_hub_is_inert_without_multimedia(monkeypatch) -> None:
    """Sans QtMultimedia, le hub ne fait rien et ne lève jamais."""
    app = _app()  # noqa: F841
    hub = MediaPlaybackHub()
    monkeypatch.setattr(hub, "_ensure_player", lambda: False)
    assert hub.available() is False
    hub.load("C:/clip.mp4")
    hub.play()
    hub.pause()
    hub.restart()
    hub.set_loop(True)
    hub.set_audio_enabled(True)  # sans lecteur : simple drapeau, aucun échec
    assert hub.active_path == ""
    assert hub.latest_image() is None
    assert hub.latest_bgra() is None
    hub.stop()


def test_hub_ignores_late_frames_after_stop() -> None:
    app = _app()  # noqa: F841
    hub = MediaPlaybackHub()
    hub._active_path = ""

    class _Frame:
        def isValid(self) -> bool:
            return True

        def toImage(self) -> QImage:
            image = QImage(4, 4, QImage.Format.Format_RGB32)
            image.fill(0xFFFFFFFF)
            return image

    hub._on_frame(_Frame())  # doit être ignoré : aucune source active
    assert hub.latest_image() is None


def test_hub_numpy_copy_can_be_disabled() -> None:
    app = _app()  # noqa: F841
    hub = MediaPlaybackHub()
    hub._active_path = "C:/clip.mp4"
    hub.set_numpy_enabled(True)
    assert hub._numpy_enabled is True
    hub.set_numpy_enabled(False)
    assert hub._numpy_enabled is False
    assert hub.latest_bgra() is None


def test_shared_hub_is_a_singleton(monkeypatch) -> None:
    from app.utils import media_hub

    app = _app()  # noqa: F841
    monkeypatch.setattr(media_hub, "_hub", None)
    first = media_hub.shared_hub()
    assert media_hub.shared_hub() is first
    monkeypatch.setattr(media_hub, "_hub", None)
