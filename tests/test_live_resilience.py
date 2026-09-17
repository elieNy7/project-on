"""Live state regressions; no database or user profile access."""
import json
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QCoreApplication

from app.utils.project_on_controller import ProjectOnController
from app.utils.announcement_controller import AnnouncementController


@pytest.fixture
def live(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    controller = ProjectOnController(None, tmp_path / 'presentation')
    return controller, app


def announcements(controller, items):
    dao = SimpleNamespace(list_items=lambda _: items, get_folder=lambda _: {'name': 'Annonces'})
    loop = AnnouncementController(controller, dao)
    loop.set_folder(1)
    return loop


def test_edited_live_restored(live):
    controller, _ = live
    controller.load_program('custom', 'Live', [('A', 'Original')])
    controller.update_live_slide('Edited', 'Correction')
    loop = announcements(controller, [{'text': 'Annonce'}])
    assert loop.start()
    loop.stop()
    payload = json.loads(controller.slide_writer.slide_path.read_text(encoding='utf-8'))
    assert payload['text'] == 'Correction'
    assert payload['reference'] == 'Edited'
    assert controller.current_slide().text == 'Original'


def test_snapshot_restores_mask_video_and_discards_loop_edits(live):
    controller, _ = live
    controller.load_program('video', 'Film', [('Film', '')], entry_visuals=['film.mp4'])
    controller.set_video_playing(True)
    controller.set_video_loop(True)
    controller.slide_writer.set_hidden(True)
    before = controller.capture_live_state()
    loop = announcements(controller, [{'text': 'Annonce'}, {'source': 'media', 'background': 'image.png'}])
    assert loop.start()
    controller.slide_writer.set_hidden(False)
    controller.update_live_slide('Changed', 'Only the announcement')
    loop._advance()
    assert controller.current_slide().image_path == 'image.png'
    loop.stop()
    assert controller.capture_live_state() == before


def test_empty_program_does_not_activate(live):
    controller, _ = live
    controller.load_program('custom', 'Original', [('R', 'T')])
    before = controller.capture_live_state()
    loop = announcements(controller, [{'text': '   '}])
    assert not loop.start()
    assert not loop.is_active
    assert controller.capture_live_state() == before


def test_restoration_signal_contains_edited_slide(live):
    controller, _ = live
    controller.load_program('custom', 'Original', [('R', 'T')])
    controller.update_live_slide('R', 'Edited')
    received = []
    controller.currentSlideChanged.connect(received.append)
    loop = announcements(controller, [{'text': 'Announcement'}])
    loop.start()
    loop.stop()
    assert received[-1].text == 'Edited'


def test_abandon_keeps_new_library_program(live):
    controller, _ = live
    controller.load_program('custom', 'First', [('R', 'T')])
    loop = announcements(controller, [{'text': 'Announcement'}])
    loop.start()
    # UI flow: stop without restoring, then load the requested program.
    loop.abandon()
    assert not loop.is_active
    controller.load_program('bible', 'Library', [('Lib', 'Program')])
    loop.stop()
    assert controller.program_title == 'Library'
    assert controller.current_slide().text == 'Program'


def test_manual_load_hook_fires_for_operator_and_not_for_loop(live):
    controller, _ = live
    calls = []
    controller.set_before_manual_load(lambda: calls.append(1))

    controller.load_program('custom', 'Manual', [('R', 'T')])
    assert calls == [1]

    loop = announcements(controller, [{'text': 'Announcement'}])
    assert loop.start()
    assert calls == [1]  # le démarrage de la boucle ne déclenche PAS le crochet

    loop.abandon()
    controller.load_program('bible', 'Library', [('Lib', 'Program')])
    assert calls == [1, 1]
    loop.stop()
