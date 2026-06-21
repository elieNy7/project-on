from __future__ import annotations

import ctypes
import sys

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QToolTip

from app.database.connection import Database
from app.ui.icons import app_logo_icon
from app.ui.splash_screen import SplashScreen


def _exception_handler(exctype, value, traceback_obj):
    """Global exception handler — écrit un rapport de crash et notifie l'utilisateur."""
    import datetime
    import traceback
    from app.utils.app_paths import logs_dir
    from app.utils.logger import cleanup_old_crash_logs

    try:
        log_dir = logs_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"crash_{timestamp}.txt"

        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"Crash at {timestamp}\n")
            f.write(f"Exception Type: {exctype}\n")
            f.write(f"Value: {value}\n\n")
            traceback.print_exception(exctype, value, traceback_obj, file=f)

        cleanup_old_crash_logs(log_dir)

        import logging
        logging.getLogger(__name__).critical(
            "Crash fatal — rapport: %s | %s: %s", log_file, exctype.__name__, value
        )

        if QApplication.instance():
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.critical(
                None,
                "Project-On - Erreur Fatale",
                f"Une erreur inattendue est survenue et l'application doit fermer.\n\n"
                f"Détails de l'erreur enregistrés dans :\n{log_file}",
            )
    except Exception:
        traceback.print_exception(exctype, value, traceback_obj)

    sys.exit(1)


def _create_fallback_window() -> QMainWindow:
    window = QMainWindow()
    window.setWindowTitle("Project-On")
    window.setWindowIcon(app_logo_icon())

    label = QLabel(
        "Project-On is initialized.\n\n"
        "If you see this window, there was an error loading the main interface.\n"
        "Please check the logs for details.",
        parent=window,
    )
    label.setWordWrap(True)
    label.setMargin(16)
    window.setCentralWidget(label)
    window.resize(900, 600)
    return window


def _qt_message_handler(mode, context, message):
    """Filter out harmless but noisy internal PyQt6 warnings."""
    if "QFont::setPointSize" in message or "font-variant-numeric" in message:
        return
    # Pass through other messages
    if sys.stderr:
        sys.stderr.write(f"{message}\n")


class _TooltipBlocker(QObject):
    """Application-wide filter that disables every tooltip popup."""

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            QToolTip.hideText()
            return True
        return super().eventFilter(watched, event)


def main() -> int:
    # Enable High DPI scaling (must be called before creating QApplication)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create system-wide mutex for Inno Setup detection and single instance
    if sys.platform == "win32":
        kernel32 = ctypes.windll.kernel32
        mutex_name = "ProjectOnMutex"
        mutex = kernel32.CreateMutexW(None, False, mutex_name)
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            # If we want a strict single instance, we could exit here.
            # For now, we just keep the handle to let the installer detect it.
            pass
        # We need to keep a reference to 'mutex' or it will be garbage collected
        global _app_mutex
        _app_mutex = mutex

    from PyQt6.QtCore import qInstallMessageHandler

    qInstallMessageHandler(_qt_message_handler)
    sys.excepthook = _exception_handler

    # ── Initialiser le logging avant tout le reste ────────────────────────────
    from app.utils.app_paths import data_dir, ensure_data_initialized, logs_dir, settings_path
    from app.utils.logger import setup_logging
    setup_logging(logs_dir())

    import logging
    _log = logging.getLogger(__name__)
    _log.info("=== Project-On démarrage ===")

    app = QApplication(sys.argv)

    # Load and apply theme/language settings before showing the splash.
    from app.utils.app_paths import data_dir, ensure_data_initialized, settings_path
    from app.utils.settings import AppSettings

    data_dir().mkdir(parents=True, exist_ok=True)

    from app.ui.theme import build_app_stylesheet, set_theme
    from app.utils.translations import set_language

    settings = AppSettings.load(settings_path())
    set_theme(settings.appearance.theme)
    set_language(settings.appearance.language)

    app.setStyleSheet(build_app_stylesheet())
    palette = app.palette()
    if str(settings.appearance.theme or "").lower() == "light":
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#111827"))
    else:
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#1d2430"))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#f5f1e8"))
    app.setPalette(palette)
    QToolTip.setPalette(palette)
    tooltip_blocker = _TooltipBlocker(app)
    app.installEventFilter(tooltip_blocker)
    app._tooltip_blocker = tooltip_blocker  # keep the filter alive
    app.setWindowIcon(app_logo_icon())

    # Show splash screen
    splash = SplashScreen()
    splash.show()
    app.processEvents()

    splash.set_progress(10, "Chargement des polices...")

    from app.utils.font_loader import load_fonts

    load_fonts()

    splash.set_progress(20, "Initialisation des donnees...")
    ensure_data_initialized()

    from app.utils.app_paths import seed_default_backgrounds

    seed_default_backgrounds()

    # Initialize database
    splash.set_progress(35, "Connexion a la base de donnees...")
    db = Database.default()
    db.initialize()

    splash.set_progress(65, "Chargement des modules...")
    try:
        from app.ui.main_window import MainWindow  # type: ignore

        splash.set_progress(85, "Preparation de l'interface...")
        window = MainWindow(db=db)
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"Error: {e}")
        window = _create_fallback_window()

    # Finish splash and show main window
    splash.finish(window)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
