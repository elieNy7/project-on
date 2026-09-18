"""Projection locale : transitions des médias et fin de vidéo signalée."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from app.ui.projection_window import ProjectionWindow  # noqa: E402

FIELD = (32, 96, 168)


def _app() -> QApplication:
    """QApplication gardée par l'appelant (variable locale) — convention du dépôt."""
    return QApplication.instance() or QApplication([])


def _photo(tmp_path: Path, name: str, color: tuple[int, int, int]) -> str:
    path = tmp_path / f"{name}.png"
    Image.new("RGB", (1600, 1200), color).save(path)
    return str(path)


def _window(tmp_path: Path, **config) -> ProjectionWindow:
    window = ProjectionWindow(tmp_path)
    window.resize(1920, 1080)
    window._apply_config(
        {
            "layout_mode": "fullscreen",
            "bg_color": "#000000",
            "animation_enabled": True,
            "animation_type": "fade",
            "animation_duration": 220,
            **config,
        }
    )
    assert window._config["layout_mode"] == "fullscreen"
    return window


def test_media_slides_animate_like_text(tmp_path: Path) -> None:
    """Deux images enchaînées s'animent (la scène texte est vide pour un média)."""
    app = _app()  # noqa: F841
    window = _window(tmp_path)
    window.set_slide({"source": "image", "text": "", "image": _photo(tmp_path, "a", FIELD)})

    window._apply_slide(
        {"source": "image", "text": "", "image": _photo(tmp_path, "b", (200, 40, 40))}
    )
    assert window._trans is not None, "les médias ne sont pas animés"
    assert window._trans["out_media"] is not None
    assert window._trans["in_media"] is not None
    assert window._trans["out_media"].width() == 1920
    window._on_trans_finished()


def test_media_to_text_still_animates(tmp_path: Path) -> None:
    app = _app()  # noqa: F841
    window = _window(tmp_path)
    window.set_slide({"source": "image", "text": "", "image": _photo(tmp_path, "a", FIELD)})
    window._apply_slide({"source": "custom", "reference": "Jean 3:16", "text": "Car Dieu…"})
    assert window._trans is not None
    assert window._trans["out_media"] is not None
    assert window._trans["in_media"] is None
    window._on_trans_finished()


def test_animation_can_be_disabled_for_media(tmp_path: Path) -> None:
    app = _app()  # noqa: F841
    window = _window(tmp_path, animation_enabled=False)
    window.set_slide({"source": "image", "text": "", "image": _photo(tmp_path, "a", FIELD)})
    window._apply_slide(
        {"source": "image", "text": "", "image": _photo(tmp_path, "b", (200, 40, 40))}
    )
    assert window._trans is None
    assert window._current_slide["_media_key"].endswith("b.png")


def test_ken_burns_never_runs_on_a_media(tmp_path: Path) -> None:
    """Le zoom lent reste réservé aux fonds d'ambiance."""
    app = _app()  # noqa: F841
    window = _window(tmp_path, ken_burns=True)
    window.set_slide({"source": "image", "text": "", "image": _photo(tmp_path, "a", FIELD)})
    window._update_ken_burns_state()
    assert window.media_layer_active() is True
    assert window._kb_anim.state() != window._kb_anim.State.Running

    # Un fond d'ambiance, lui, anime toujours.
    window.set_slide(
        {"source": "custom", "reference": "Psaume 23", "text": "L'Éternel…",
         "background": _photo(tmp_path, "fond", (10, 40, 90))}
    )
    window._update_ken_burns_state()
    assert window._kb_anim.state() == window._kb_anim.State.Running
    window._kb_anim.stop()


def test_video_end_is_signalled_when_not_looping(tmp_path: Path) -> None:
    """La régie peut enchaîner : fin de vidéo signalée une fois, hors boucle."""
    app = _app()  # noqa: F841
    window = _window(tmp_path)
    received: list[int] = []
    window.videoFinished.connect(lambda: received.append(1))

    calls: list[str] = []

    class _Player:
        def pause(self) -> None:
            calls.append("pause")

        def setPosition(self, value: int) -> None:
            calls.append(f"pos{value}")

        def play(self) -> None:
            calls.append("play")

    window._media_player = _Player()

    from PyQt6.QtMultimedia import QMediaPlayer

    window._video_loop = True
    window._on_media_status(QMediaPlayer.MediaStatus.EndOfMedia)
    assert calls == ["pos0", "play"]
    assert received == []  # en boucle : pas de fin

    calls.clear()
    window._video_loop = False
    window._on_media_status(QMediaPlayer.MediaStatus.EndOfMedia)
    assert calls == ["pause", "pos0"]
    assert received == [1]

    # Un autre statut ne déclenche rien.
    window._on_media_status(QMediaPlayer.MediaStatus.LoadedMedia)
    assert received == [1]
