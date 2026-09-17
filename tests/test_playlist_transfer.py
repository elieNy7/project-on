import json
from pathlib import Path
from threading import Event

import pytest

from app.database.dao_playlist import PlaylistDao
from app.utils.playlist_transfer import export_playlist, import_playlist, read_playlist
from app.utils.import_worker import ImportWorker


def test_portable_roundtrip(tmp_path, db):
    media = tmp_path / 'movie.mp4'
    media.write_bytes(b'video-fixture')
    items = [{'source': 'custom', 'reference': 'A', 'text': 'Bienvenue'},
             {'source': 'media', 'reference': 'B', 'text': '', 'background': str(media)}]
    archive = tmp_path / 'service.projecton'
    assert export_playlist(archive, 'Service', items) == 2
    media.unlink()
    dao = PlaylistDao(db)
    folder = import_playlist(archive, dao, tmp_path / 'fresh-profile')
    rows = dao.list_items(folder)
    assert rows[0]['text'] == 'Bienvenue'
    assert rows[1]['source'] == 'media'
    assert Path(rows[1]['background']).read_bytes() == b'video-fixture'


def test_legacy_json(tmp_path):
    path = tmp_path / 'old.json'
    path.write_text(json.dumps({'format': 1, 'name': 'Old', 'items': [{'reference': 'R', 'text': 'T'}]}))
    name, items = read_playlist(path, tmp_path / 'media')
    assert name == 'Old' and items[0]['source'] == 'custom'


def test_missing_asset_does_not_replace_existing_export(tmp_path):
    path = tmp_path / 'keep.projecton'
    path.write_bytes(b'existing')
    with pytest.raises(ValueError, match='absent'):
        export_playlist(path, 'X', [{'source': 'media', 'background': str(tmp_path / 'missing.png')}])
    assert path.read_bytes() == b'existing'


def test_cancelled_transfer_creates_no_folder(tmp_path, db):
    path = tmp_path / 'old.json'
    path.write_text(json.dumps({'items': [{'text': 'T'}]}))
    cancel = Event()
    cancel.set()
    dao = PlaylistDao(db)
    with pytest.raises(InterruptedError):
        import_playlist(path, dao, tmp_path / 'media', cancel)
    assert dao.list_folders() == []


def test_move_atomic_rollback(tmp_path, db):
    dao = PlaylistDao(db)
    folder = dao.create_folder('F')
    first = dao.add_item('custom', 'A', 'A', folder)
    second = dao.add_item('custom', 'B', 'B', folder)
    with db.connect() as conn:
        # Déclencheur inconditionnel (aucune valeur interpolée en SQL) :
        # le premier move_item échoue et tout l'échange doit être annulé.
        conn.execute(
            "CREATE TRIGGER fail_move BEFORE UPDATE ON playlist_item "
            "BEGIN SELECT RAISE(ABORT, 'test rollback'); END"
        )
    with pytest.raises(Exception, match='test rollback'):
        dao.move_item(first, 1, folder)
    assert [r['id'] for r in dao.list_items(folder)] == [first, second]


def test_worker_report_and_cancellation():
    def process(item, cancel):
        if item == 1:
            return None
        if item == 2:
            raise ValueError('diagnostic détaillé')
        if item == 3:
            cancel.set()
        return item
    worker = ImportWorker(range(5), process)
    reports = []
    worker.signals.finished.connect(reports.append)
    worker.run()
    report = reports[0]
    assert report.succeeded == [0, 3]
    assert report.skipped == [1]
    assert report.errors == [('2', 'diagnostic détaillé')]
    assert report.cancelled and report.remaining == 1


def test_media_import_copies_renders_dest_and_inserts_in_worker(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import get_ident
    from types import SimpleNamespace
    from app.utils.library_controller import LibraryController
    from app.utils import app_paths, office_renderer
    from PyQt6.QtWidgets import QFileDialog
    source = tmp_path / 'source.pptx'
    dest = tmp_path / 'stored.pptx'
    source.write_bytes(b'fixture')
    dest.write_bytes(b'fixture')
    ui_thread = get_ident()
    calls = []
    def copy(path):
        calls.append(('copy', get_ident(), path))
        return dest
    def render(path):
        calls.append(('render', get_ident(), path))
        return [tmp_path / 'slide.png']
    def insert(*args):
        calls.append(('insert', get_ident(), args[1]))
        return 1
    obj = LibraryController.__new__(LibraryController)
    obj._media_tab = object()
    obj._media_dao = SimpleNamespace(add_media=insert)
    jobs = []
    obj._start_import = lambda title, paths, process, refresh: jobs.append(ImportWorker(paths, process))
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(source), ''))
    monkeypatch.setattr(app_paths, 'import_media_file', copy)
    monkeypatch.setattr(office_renderer, 'render_pptx_to_images', render)
    obj.on_media_import('pptx')
    assert not calls
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(jobs[0].run).result()
    assert [call[0] for call in calls] == ['copy', 'render', 'insert']
    assert all(call[1] != ui_thread for call in calls)
    assert calls[1][2] == str(dest) == calls[2][2]


def test_cancel_copy_cleans_temporary_and_preserves_existing(tmp_path):
    from app.utils.playlist_transfer import _store
    source = tmp_path / 'source.png'
    source.write_bytes(b'fixture')
    media = tmp_path / 'media'
    media.mkdir()
    existing = media / 'keep.png'
    existing.write_bytes(b'keep')
    event = Event()
    event.set()
    with pytest.raises(InterruptedError):
        _store(source, media, event)
    assert list(media.iterdir()) == [existing]
    assert existing.read_bytes() == b'keep'
