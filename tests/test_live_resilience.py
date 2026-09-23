"""Résilience du direct : instantané et restauration à l'identique.

Le diaporama prend la main sur le live (comme toute prise en charge
automatique) : ces tests verrouillent la restauration exacte — texte édité,
masquage, lecture et boucle vidéo — ainsi que le crochet de chargement manuel.
"""
import json

import pytest
from PySide6.QtCore import QCoreApplication

from app.utils.project_on_controller import ProjectOnController
from app.utils.slideshow_controller import SlideshowController


@pytest.fixture
def live(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    controller = ProjectOnController(None, tmp_path / "presentation")
    return controller, app


def slideshow(controller, medias):
    return SlideshowController(controller)


def test_edited_live_restored(live):
    controller, _ = live
    controller.load_program("custom", "Live", [("A", "Original")])
    controller.update_live_slide("Edited", "Correction")
    loop = slideshow(controller, [{"text": "Annonce"}])
    assert loop.start([{"name": "Photo", "path": "photo.png"}])
    loop.stop()
    payload = json.loads(controller.slide_writer.slide_path.read_text(encoding="utf-8"))
    assert payload["text"] == "Correction"
    assert payload["reference"] == "Edited"
    assert controller.current_slide().text == "Original"


def test_snapshot_restores_mask_video_and_discards_slideshow_edits(live):
    controller, _ = live
    controller.load_program("video", "Film", [("Film", "")], entry_visuals=["film.mp4"])
    controller.set_video_playing(True)
    controller.set_video_loop(True)
    controller.slide_writer.set_hidden(True)
    before = controller.capture_live_state()
    loop = slideshow(controller, [])
    assert loop.start([{"name": "Photo", "path": "image.png"}])
    controller.slide_writer.set_hidden(False)
    controller.update_live_slide("Changed", "Only the slideshow")
    loop._advance()
    assert controller.current_slide().image_path == "image.png"
    loop.stop()
    assert controller.capture_live_state() == before


def test_empty_slideshow_does_not_activate(live):
    controller, _ = live
    controller.load_program("custom", "Original", [("R", "T")])
    before = controller.capture_live_state()
    loop = slideshow(controller, [])
    assert not loop.start([{"name": "Vide", "path": "   "}])
    assert not loop.is_active
    assert controller.capture_live_state() == before


def test_start_without_media_does_not_activate(live):
    controller, _ = live
    controller.load_program("custom", "Original", [("R", "T")])
    before = controller.capture_live_state()
    loop = slideshow(controller, [])
    assert not loop.start([])
    assert not loop.is_active
    assert controller.capture_live_state() == before


def test_restoration_signal_contains_edited_slide(live):
    controller, _ = live
    controller.load_program("custom", "Original", [("R", "T")])
    controller.update_live_slide("R", "Edited")
    received = []
    controller.currentSlideChanged.connect(received.append)
    loop = slideshow(controller, [])
    loop.start([{"name": "Photo", "path": "photo.png"}])
    loop.stop()
    assert received[-1].text == "Edited"


def test_abandon_keeps_new_library_program(live):
    controller, _ = live
    controller.load_program("custom", "First", [("R", "T")])
    loop = slideshow(controller, [])
    loop.start([{"name": "Photo", "path": "photo.png"}])
    # Parcours interface : on clos sans restaurer, puis on charge le programme
    # demandé — celui-ci doit rester le live.
    loop.abandon()
    assert not loop.is_active
    controller.load_program("bible", "Library", [("Lib", "Program")])
    loop.stop()
    assert controller.program_title == "Library"
    assert controller.current_slide().text == "Program"


def test_manual_load_hook_fires_for_operator_and_not_for_slideshow(live):
    controller, _ = live
    calls = []
    controller.set_before_manual_load(lambda: calls.append(1))

    controller.load_program("custom", "Manual", [("R", "T")])
    assert calls == [1]

    loop = slideshow(controller, [])
    assert loop.start([{"name": "Photo", "path": "photo.png"}])
    assert calls == [1]  # le démarrage du diaporama ne déclenche PAS le crochet

    loop.abandon()
    controller.load_program("bible", "Library", [("Lib", "Program")])
    assert calls == [1, 1]
    loop.stop()
