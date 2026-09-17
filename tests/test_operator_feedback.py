"""Retours opérateur : widgets isolés, sans application ni profil réels."""
import os
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QDialog

from app.ui.preflight_dialog import PreflightDialog
from app.utils.settings import AppSettings
from app.utils.system_health import HealthCheck, HealthReport


def test_startup_warning_is_deferred_and_only_shown_once(monkeypatch):
    from PyQt6.QtWidgets import QMainWindow
    from app.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])

    class Window(MainWindow):
        def __init__(self):
            QMainWindow.__init__(self)
            self._settings = AppSettings(load_warning="Paramètres récupérés")

        def closeEvent(self, event):
            event.accept()

    messages = []
    monkeypatch.setattr(MainWindow, "_show_operator_warning", lambda self, title, text: messages.append(text))
    window = Window()
    assert messages == []
    window.show()
    assert messages == []
    app.processEvents()
    assert messages == ["Paramètres récupérés"]
    window.hide()
    window.show()
    app.processEvents()
    assert len(messages) == 1
    window.close()
    window.deleteLater()


def test_preflight_accepts_injected_report(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(PreflightDialog, "_start_check", lambda self: None)
    dialog = PreflightDialog(
        database_path=tmp_path / "test.db",
        data_directory=tmp_path / "data",
        presentation_directory=tmp_path / "presentation",
        ndi_runtime_path=None,
        settings=AppSettings(),
    )
    report = HealthReport((HealthCheck("media", "Médias", "warning", "Image manquante"),), datetime.now())
    dialog._on_completed(report)
    assert dialog._report is report
    assert "1 point(s)" in dialog._summary.text()
    assert dialog._copy_button.isEnabled()
    accepted = []
    dialog.accepted.connect(lambda: accepted.append(True))
    dialog.accept()
    assert accepted == [True]
    assert dialog.result() == QDialog.DialogCode.Accepted
    dialog.deleteLater()
    app.processEvents()
