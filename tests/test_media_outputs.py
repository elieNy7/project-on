"""Sorties média : mixeur HDMI et NDI projettent le média plein cadre."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy  # noqa: E402
from PIL import Image  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.ui.mixer_output_window import MixerOutputWindow  # noqa: E402
from app.utils.ndi_lower_third import NdiLowerThirdSender  # noqa: E402
from app.utils.obs_overlay_render import CHROMA_KEY_GREEN  # noqa: E402

FIELD = (32, 96, 168)


def _app() -> QApplication:
    """QApplication gardée par l'appelant (variable locale) — convention du dépôt."""
    return QApplication.instance() or QApplication([])


def _photo(tmp_path: Path, size: tuple[int, int] = (1600, 1200)) -> str:
    path = tmp_path / "photo.png"
    Image.new("RGB", size, FIELD).save(path)
    return str(path)


def _presentation(tmp_path: Path, slide: dict, config: dict | None = None) -> Path:
    work = tmp_path / "pres"
    work.mkdir(exist_ok=True)
    (work / "obs-config.json").write_text(
        json.dumps(config or {"bg_color": "#07111f", "media_backdrop_dim": 0.45}),
        encoding="utf-8",
    )
    (work / "slide.json").write_text(json.dumps(slide), encoding="utf-8")
    return work


def test_hdmi_shows_media_full_frame_without_key_color(tmp_path: Path) -> None:
    app = _app()  # noqa: F841
    photo = _photo(tmp_path)
    work = _presentation(
        tmp_path,
        {"reference": "Photo", "text": "", "image": photo, "hidden": False},
        {"bg_color": "#07111f", "media_fit": "contain", "media_backdrop": "blur"},
    )
    window = MixerOutputWindow(work, screen="auto")
    window.resize(1920, 1080)
    window._apply_slide(json.loads((work / "slide.json").read_text(encoding="utf-8")))

    assert window._frame_is_media is True
    frame = window.grab().toImage()
    assert frame.pixelColor(960, 540).getRgb()[:3] == FIELD      # image nette
    band = frame.pixelColor(60, 540).getRgb()[:3]
    assert band != tuple(CHROMA_KEY_GREEN), "aucune couleur de clé sur un média"
    assert band != (0, 0, 0)
    assert band[2] < FIELD[2]  # fond assombri


def test_hdmi_text_slide_keeps_chroma_key(tmp_path: Path) -> None:
    app = _app()  # noqa: F841
    work = _presentation(
        tmp_path, {"reference": "Jean 3:16", "text": "Car Dieu a tant aimé", "hidden": False}
    )
    window = MixerOutputWindow(work, screen="auto")
    window.resize(1920, 1080)
    window._apply_slide(json.loads((work / "slide.json").read_text(encoding="utf-8")))

    assert window._frame_is_media is False
    frame = window.grab().toImage()
    assert frame.pixelColor(10, 10).getRgb()[:3] == tuple(CHROMA_KEY_GREEN)


def test_hdmi_masks_media_when_hidden(tmp_path: Path) -> None:
    """« Masquer les écritures » : le média disparaît aussi du mixeur."""
    app = _app()  # noqa: F841
    photo = _photo(tmp_path)
    work = _presentation(tmp_path, {"reference": "", "text": "", "image": "", "hidden": True})
    window = MixerOutputWindow(work, screen="auto")
    window.resize(1920, 1080)
    window._apply_slide(json.loads((work / "slide.json").read_text(encoding="utf-8")))
    assert window._frame_is_media is False
    assert window.grab().toImage().pixelColor(10, 10).getRgb()[:3] == tuple(CHROMA_KEY_GREEN)


def test_ndi_media_frame_is_opaque_and_whole(tmp_path: Path) -> None:
    app = _app()  # noqa: F841
    photo = _photo(tmp_path)
    work = _presentation(tmp_path, {"reference": "Photo", "text": "", "image": photo})
    sender = NdiLowerThirdSender(work, source_name="Test")
    sender._np = numpy
    sender._last_cfg = json.loads((work / "obs-config.json").read_text(encoding="utf-8"))

    frame = sender._render(json.loads((work / "slide.json").read_text(encoding="utf-8")))
    assert frame.shape == (1080, 1920, 4)
    # Un média est opaque : sinon le receveur NDI le découperait comme du texte.
    assert int(frame[:, :, 3].min()) == 255
    # BGRA : le centre est l'image nette, la bande gauche le fond assombri.
    assert tuple(frame[540, 960][:3]) == (FIELD[2], FIELD[1], FIELD[0])
    band = frame[540, 60][:3]
    assert tuple(band) != (CHROMA_KEY_GREEN[2], CHROMA_KEY_GREEN[1], CHROMA_KEY_GREEN[0])
    assert int(band[0]) < FIELD[2]


def test_ndi_text_slide_still_transparent(tmp_path: Path) -> None:
    app = _app()  # noqa: F841
    work = _presentation(tmp_path, {"reference": "Jean 3:16", "text": "Car Dieu a tant aimé"})
    sender = NdiLowerThirdSender(work, source_name="Test")
    sender._np = numpy
    sender._last_cfg = json.loads((work / "obs-config.json").read_text(encoding="utf-8"))

    frame = sender._render(
        {"reference": "Jean 3:16", "text": "Car Dieu a tant aimé", "hidden": False}
    )
    assert frame.shape == (1080, 1920, 4)
    assert int(frame[:, :, 3].min()) == 0  # fond transparent conservé


def test_ndi_carries_video_frames_from_the_hub(tmp_path: Path) -> None:
    """Quand une vidéo joue, la trame NDI reprend les images du hub."""
    app = _app()  # noqa: F841
    work = _presentation(tmp_path, {"reference": "Clip", "text": "", "video": "C:/clip.mp4"})

    class _FakeHub:
        def __init__(self) -> None:
            self.enabled = False

        def set_numpy_enabled(self, enabled: bool) -> None:
            self.enabled = enabled

        def latest_bgra(self):
            frame = numpy.zeros((1080, 1920, 4), dtype=numpy.uint8)
            frame[:, :, 3] = 255
            frame[:, :, 0] = 9
            return frame

    hub = _FakeHub()
    sender = NdiLowerThirdSender(work, source_name="Test", hub=hub)
    sender._np = numpy

    # Vidéo en cours : la trame du hub est reprise telle quelle (copiée).
    video = sender._hub_video_frame({"reference": "Clip", "video": "C:/clip.mp4"})
    assert video is not None
    assert video.shape == (1080, 1920, 4)
    assert int(video[0, 0, 0]) == 9 and int(video[0, 0, 3]) == 255

    # Hors vidéo (ou masqué) : rien à copier, la composition texte reste.
    assert sender._hub_video_frame({"reference": "Jean 3:16", "text": "Car Dieu"}) is None
    assert sender._hub_video_frame({"video": "C:/clip.mp4", "hidden": True}) is None

    # Dimension inattendue : on refuse la copie plutôt que de casser la boucle.
    class _WrongSizeHub(_FakeHub):
        def latest_bgra(self):
            return numpy.zeros((10, 10, 4), dtype=numpy.uint8)

    sender.set_media_hub(_WrongSizeHub())
    assert sender._hub_video_frame({"video": "C:/clip.mp4"}) is None
