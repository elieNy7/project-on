from types import SimpleNamespace

from PySide6.QtWidgets import QApplication
from app.utils.library_controller import LibraryController


def controller():
    app = QApplication.instance() or QApplication([])
    obj = LibraryController.__new__(LibraryController)
    obj._generations = {}
    jobs = []
    obj._pool = SimpleNamespace(start=jobs.append)
    return obj, jobs, app


def test_reversed_completions_only_publish_latest():
    obj, jobs, app = controller()
    output = []
    obj._submit_latest('search', lambda: 'old', output.append)
    obj._submit_latest('search', lambda: 'new', output.append)
    jobs[1].run()
    jobs[0].run()
    assert output == ['new']


def test_independent_tabs_and_invalidated_selection():
    obj, jobs, app = controller()
    output = []
    obj._submit_latest('sermons', lambda: 'sermon', output.append)
    obj._submit_latest('expose', lambda: 'expose', output.append)
    obj._invalidate('sermons')
    for job in jobs:
        job.run()
    assert output == ['expose']


def test_paragraph_search_captures_request_before_execution():
    obj, jobs, app = controller()
    output = []
    obj._current_sermon_language = 'fr'
    obj._sermons_tab = SimpleNamespace(set_search_results=output.append)
    obj._sermons_dao = SimpleNamespace(search_paragraphs=lambda query, **kw: [query])
    obj.on_paragraph_search('old')
    obj.on_paragraph_search('new')
    for job in jobs:
        job.run()
    assert output == [['new']]
