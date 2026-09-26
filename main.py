from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QToolTip

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
        # Nom construit depuis un horodatage local (chiffres/underscore),
        # puis confiné au répertoire de journaux géré par l'application.
        log_file = (log_dir / ("crash_" + timestamp + ".txt")).resolve()
        if not log_file.is_relative_to(log_dir.resolve()):
            raise ValueError("Chemin de rapport de crash hors du dossier de journaux")

        report = (
            f"Crash at {timestamp}\n"
            f"Exception Type: {exctype}\n"
            f"Value: {value}\n\n"
            + "".join(traceback.format_exception(exctype, value, traceback_obj))
        )
        log_file.write_text(report, encoding="utf-8")

        cleanup_old_crash_logs(log_dir)

        import logging
        logging.getLogger(__name__).critical(
            "Crash fatal — rapport: %s | %s: %s", log_file, exctype.__name__, value
        )

        if QApplication.instance():
            from PySide6.QtWidgets import QMessageBox

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
    """Filter out harmless but noisy internal PySide6 warnings."""
    if "QFont::setPointSize" in message or "font-variant-numeric" in message:
        return
    # Pass through other messages
    if sys.stderr:
        sys.stderr.write(f"{message}\n")


def _run_responsive(app: QApplication, work):
    """Exécute ``work()`` dans un fil de travail en gardant l'interface vivante.

    Les tâches lourdes du démarrage (migration de la base, pack de contenu,
    reconstruction de l'index de recherche) peuvent durer une minute sur une
    grosse base. Exécutées dans le fil de l'interface, elles figeaient l'écran
    de démarrage : Windows affichait « Ne répond pas » et l'utilisateur fermait
    l'application en pleine migration, qui recommençait au lancement suivant.
    L'exception éventuelle est relancée dans le fil appelant.
    """
    import threading
    import time

    outcome: dict = {}

    def _target() -> None:
        try:
            outcome["value"] = work()
        except BaseException as error:  # relancée plus bas
            outcome["error"] = error

    worker = threading.Thread(target=_target, name="project-on-startup", daemon=True)
    worker.start()
    while worker.is_alive():
        app.processEvents()
        worker.join(0.015)
        time.sleep(0)
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")


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

    from PySide6.QtCore import qInstallMessageHandler

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

    from app.ui.theme import Colors, build_app_stylesheet, set_theme, set_window_backdrop
    from app.ui.window_effects import apply_color_scheme, mica_supported
    from app.utils.translations import set_language, tr

    settings = AppSettings.load(settings_path())
    set_theme(settings.appearance.theme)
    set_language(settings.appearance.language)
    apply_color_scheme(app, settings.appearance.theme)
    set_window_backdrop(settings.appearance.mica and mica_supported())

    app.setStyleSheet(build_app_stylesheet())
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(Colors.BG_TOOLTIP))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(Colors.TEXT_PRIMARY))
    app.setPalette(palette)
    QToolTip.setPalette(palette)
    app.setWindowIcon(app_logo_icon())

    # Show splash screen
    splash = SplashScreen()
    splash.show()
    app.processEvents()

    splash.set_progress(10, tr("splash_fonts"))

    from app.utils.font_loader import load_fonts

    # Poppins (interface) en synchrone ; les ~40 familles Google Fonts sont
    # enregistrées juste après l'affichage de la fenêtre, sans ralentir
    # le démarrage (la liste des polices vient du manifeste, elle est
    # complète immédiatement).
    load_fonts(core_only=True)

    splash.set_progress(20, tr("splash_data"))
    ensure_data_initialized()

    from app.utils.app_paths import seed_default_backgrounds

    seed_default_backgrounds()

    # Initialize database
    splash.set_progress(35, tr("splash_database"))
    db = Database.default()
    _run_responsive(app, db.initialize)

    # Appliquer le pack de données éditorial (Exposé corrigé) aux bases
    # existantes, puis resynchroniser titres/index — une seule fois par pack.
    try:
        from app.utils.app_paths import is_frozen as _is_frozen

        if _is_frozen():
            from app.utils.app_paths import app_db_path as _app_db_path
            from app.utils.app_paths import data_pack_pending as _pack_pending
            from app.utils.app_paths import resource_root as _resource_root
            from app.utils.app_paths import upgrade_data_pack as _upgrade_pack

            _pack = _resource_root() / "data" / "project_on.db"
            if _pack_pending(_app_db_path(), _pack):
                splash.set_progress(40, tr("splash_content_update"))

                def _apply_pack() -> None:
                    if _upgrade_pack(_app_db_path(), _pack):
                        with db.connect() as _conn:
                            db._ensure_sermon_search_metadata(_conn)
                            _conn.commit()

                _run_responsive(app, _apply_pack)
    except Exception:
        import logging

        logging.getLogger(__name__).exception("Data pack upgrade failed")

    splash.set_progress(65, tr("splash_modules"))
    try:
        from app.ui.main_window import MainWindow  # type: ignore

        splash.set_progress(85, tr("splash_interface"))
        window = MainWindow(db=db)
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"Error: {e}")
        window = _create_fallback_window()

    # Finish splash and show main window
    splash.finish(window)

    # Compléter la bibliothèque de polices une fois l'interface affichée.
    from PySide6.QtCore import QTimer

    QTimer.singleShot(0, load_fonts)

    exit_code = app.exec()

    # Laisser finir les tâches d'arrière-plan (recherche, contrôle avant
    # service, sauvegarde) avant l'arrêt de l'interpréteur : PySide6 signale
    # sinon une erreur dans QRunnable::run() pendant la finalisation.
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(5000)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
