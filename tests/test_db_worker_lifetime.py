"""Workers finishing together must not dispatch from destroyed signal carriers.

Regression: the thread pool deletes a finished runnable in its worker thread.
The carrier QObject used to die with it while its queued "finished" signal was
still pending, so the main thread crashed (access violation) when several
searches completed at the same time.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QElapsedTimer, QThreadPool
from PySide6.QtWidgets import QApplication

from app.utils import library_controller
from app.utils.library_controller import _DbWorker


def test_concurrent_workers_deliver_every_result_and_release_carriers() -> None:
    app = QApplication.instance() or QApplication([])
    pool = QThreadPool.globalInstance()
    results: list[int] = []

    def slow(i: int) -> int:
        time.sleep(0.002)  # overlap completions across pool threads
        return i

    total = 400
    for i in range(total):
        pool.start(_DbWorker(lambda i=i: slow(i), results.append))

    timer = QElapsedTimer()
    timer.start()
    while len(results) < total and timer.elapsed() < 20000:
        app.processEvents()
    pool.waitForDone(5000)
    app.processEvents()

    assert sorted(results) == list(range(total))
    assert not library_controller._in_flight
