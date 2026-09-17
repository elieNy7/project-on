"""Cooperative import jobs; all processing happens off the UI thread."""
from dataclasses import dataclass, field
from threading import Event

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot


@dataclass
class ImportReport:
    succeeded: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    cancelled: bool = False
    remaining: int = 0

    def summary(self):
        return (f"{len(self.succeeded)} réussi(s), {len(self.skipped)} ignoré(s), "
                f"{len(self.errors)} erreur(s), {self.remaining} non traité(s)."
                + ("\nAnnulation demandée." if self.cancelled else "")
                + "".join(f"\n{label} : {error}" for label, error in self.errors))


class ImportWorker(QRunnable):
    class Signals(QObject):
        progress = pyqtSignal(int, int)
        finished = pyqtSignal(object)

    def __init__(self, items, process):
        super().__init__()
        self.items = list(items)
        self.process = process
        self.cancelled = Event()
        self.signals = self.Signals()

    def cancel(self):
        self.cancelled.set()

    @pyqtSlot()
    def run(self):
        report = ImportReport(remaining=len(self.items))
        for index, item in enumerate(self.items):
            if self.cancelled.is_set():
                break
            try:
                result = self.process(item, self.cancelled)
                (report.skipped if result is None else report.succeeded).append(result if result is not None else item)
            except InterruptedError:
                self.cancelled.set()
                break
            except Exception as exc:
                report.errors.append((str(item), str(exc)))
            report.remaining -= 1
            self.signals.progress.emit(index + 1, len(self.items))
        report.cancelled = self.cancelled.is_set()
        self.signals.finished.emit(report)
