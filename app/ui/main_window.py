from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.database.connection import Database
from app.ui.command_bar import CommandBar
from app.ui.cue_monitor import CueMonitor
from app.ui.settings_page import embed_dialog, watch_inputs
from app.ui.global_search_popup import GlobalSearchPopup
from app.ui.icons import app_logo_icon
from app.ui.library_panel import LibraryPanel
from app.ui.preview_panel import PreviewPanel
from app.ui.projection_window import ProjectionWindow
from app.ui.theme import (
    Spacing,
    build_app_stylesheet,
    get_main_window_style,
    get_splitter_style,
    set_theme,
    set_window_backdrop,
    window_backdrop_enabled,
)
from app.ui.window_effects import apply_mica, prepare_for_mica
from app.utils.app_paths import (
    app_db_path,
    data_dir,
    ensure_presentation_workdir,
    resource_root,
    settings_path,
)
from app.utils.library_controller import LibraryController
from app.utils.obs_controller import ObsController
from app.utils.project_on_controller import ProjectOnController
from app.utils.settings import AppSettings
from app.utils.translations import set_language, tr
from app.version import __version__

log = logging.getLogger(__name__)


def _is_text_entry(widget: QWidget | None) -> bool:
    """Widgets where the operator types (Escape must stay local to them)."""
    if isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
        return not getattr(widget, "isReadOnly", lambda: False)()
    return isinstance(widget, QComboBox) and widget.isEditable()


class MainWindow(QMainWindow):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db

        # Load settings first to apply theme and language
        self._settings_path = settings_path()
        self._settings = AppSettings.load(self._settings_path)

        # Apply theme and language from settings
        set_theme(self._settings.appearance.theme)
        set_language(self._settings.appearance.language)

        self.setWindowTitle(f"Project-On v{__version__}")
        if window_backdrop_enabled():
            prepare_for_mica(self)

        self.setWindowIcon(app_logo_icon())
        self.setStyleSheet(get_main_window_style())

        presentation_dir = ensure_presentation_workdir()

        self._projection_window: ProjectionWindow | None = None
        self._mixer_window = None  # MixerOutputWindow | None
        self._presentation_dir = presentation_dir
        self._write_presentation_config()
        self._write_obs_config()

        self._project_controller = ProjectOnController(
            db=db, presentation_dir=presentation_dir
        )
        self._project_controller.set_split_settings(self._settings.split)
        self._obs = ObsController(settings=self._settings.obs)
        if self._settings.appearance.low_power:
            self._obs.set_low_power(True)
        # Lecteur vidéo partagé : l'aperçu, le mixeur HDMI et le NDI lisent les
        # mêmes images — un seul décodage, aucune dérive entre les sorties.
        # La projection plein écran garde son lecteur natif (son + matériel).
        from app.utils.media_hub import shared_hub

        self._media_hub = shared_hub()
        self._obs.set_media_hub(self._media_hub)
        # Aucune fenêtre de projection au démarrage : le lecteur partagé porte
        # le son de la vidéo jusqu'à ce que la projection prenne la main.
        self._set_hub_audio(enabled=True)

        # Diaporama de médias : durée par média, avance automatique et
        # restauration du live à l'arrêt.
        from app.utils.slideshow_controller import SlideshowController

        self._slideshow = SlideshowController(self._project_controller, parent=self)
        self._slideshow.set_default_duration(
            self._settings.projection.media_default_duration
        )
        # Toute activation manuelle (bible, cantique, sermon, exposé, média)
        # remplace le live : le diaporama en cours est clos sans restauration —
        # le nouveau programme devient le live, sans écrasement au tick suivant.
        self._project_controller.set_before_manual_load(
            self._abandon_slideshow_for_manual_load
        )

        # Remote OBS control (obs-websocket 5.x) — scene switching on live/hide
        from app.utils.obs_websocket import ObsRemoteClient

        self._obs_remote = ObsRemoteClient(self._settings.obs.remote, parent=self)
        if self._settings.obs.remote.enabled:
            self._obs_remote.connect_to_obs()

        # Connect slide changes to OBS controller
        self._project_controller.currentSlideChanged.connect(
            self._on_slide_changed_for_obs
        )

        # Historique du culte : tout ce qui passe en direct est horodaté.
        from app.utils.service_log import ServiceLog

        self._service_log = ServiceLog(data_dir() / "history")
        self._project_controller.currentSlideChanged.connect(self._log_live_slide)

        # Reprise après coupure : le direct est sauvegardé en continu ; un
        # fichier encore présent au démarrage signale un arrêt brutal.
        from app.utils import live_recovery

        self._recovery_path = data_dir() / "live-recovery.json"
        self._pending_recovery = live_recovery.load(self._recovery_path)
        self._recovery_timer = QTimer(self)
        self._recovery_timer.setSingleShot(True)
        self._recovery_timer.setInterval(400)
        self._recovery_timer.timeout.connect(self._save_recovery)
        self._project_controller.currentSlideChanged.connect(
            lambda _slide: self._recovery_timer.start()
        )
        if self._pending_recovery is not None:
            QTimer.singleShot(900, self._offer_recovery)

        # Fluent shell: navigation rail on the window edge, command bar on
        # top, then the library and preview layers. Rail and bar sit on the
        # window backdrop (Mica); the layers are opaque cards.
        root = QWidget(self)
        root.setObjectName("ShellRoot")
        root.setStyleSheet("QWidget#ShellRoot { background: transparent; }")
        self.setCentralWidget(root)

        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        splitter = QSplitter(root)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(Spacing.SM)
        splitter.setStyleSheet(get_splitter_style())

        self.library_panel = LibraryPanel(splitter)
        self.preview_panel = PreviewPanel(splitter, self._settings)
        self.preview_panel.set_presentation_dir(presentation_dir)
        self.preview_panel.set_media_hub(self._media_hub)

        self.rail = self.library_panel.rail
        self.rail.setParent(root)
        self.rail.set_compact(self._settings.appearance.rail_compact, animate=False)
        self.rail.compactChanged.connect(self._on_rail_compact_changed)
        shell.addWidget(self.rail)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, Spacing.MD, Spacing.MD)
        column.setSpacing(Spacing.XS)
        shell.addLayout(column, 1)

        self.command_bar = CommandBar(root)
        self.command_bar.outputClicked.connect(self._on_output_chip_clicked)
        column.addWidget(self.command_bar)

        # Right column: the preview ("Aperçu", prepared, not live) above the
        # live monitor ("Direct", what the audience sees).
        self.cue_monitor = CueMonitor()
        self.cue_monitor.set_renderer(self.preview_panel.render_slide_pixmap)
        self.preview_panel.renderStyleChanged.connect(self.cue_monitor.refresh)
        monitors = QSplitter(Qt.Orientation.Vertical)
        monitors.setChildrenCollapsible(False)
        monitors.setHandleWidth(Spacing.SM)
        monitors.setStyleSheet(get_splitter_style())
        monitors.addWidget(self.cue_monitor)
        monitors.addWidget(self.preview_panel)
        monitors.setStretchFactor(0, 40)
        monitors.setStretchFactor(1, 60)

        splitter.addWidget(self.library_panel)
        splitter.addWidget(monitors)

        # Balance: Library (55%), Preview (45%)
        splitter.setStretchFactor(0, 55)
        splitter.setStretchFactor(1, 45)

        # Proportional initial sizes (window not yet shown: use the screen)
        screen = QApplication.primaryScreen()
        width = screen.availableGeometry().width() if screen else 1400
        splitter.setSizes([int(width * 0.55), int(width * 0.45)])

        column.addWidget(splitter, 1)

        self._library_controller = LibraryController(
            db=db,
            project_controller=self._project_controller,
            bible_tab=self.library_panel.bible_tab,
            hymns_tab=self.library_panel.hymns_tab,
            sermons_tab=self.library_panel.sermons_tab,
            expose_tab=self.library_panel.expose_tab,
            playlist_tab=self.library_panel.playlist_tab,
            media_tab=self.library_panel.media_tab,
        )

        self._setup_global_search(root)
        self._setup_settings_page()
        self._library_controller.programCued.connect(self._on_program_cued)
        self.cue_monitor.takeRequested.connect(self._take_cue)

        # Diaporama lancé depuis la galerie des médias (sélection ou
        # bibliothèque entière) ou depuis une playlist de médias.
        media_tab = self.library_panel.media_tab
        if media_tab is not None and hasattr(media_tab, "slideshowRequested"):
            media_tab.slideshowRequested.connect(self._start_slideshow)
        playlist_tab = self.library_panel.playlist_tab
        if playlist_tab is not None and hasattr(playlist_tab, "slideshowRequested"):
            playlist_tab.slideshowRequested.connect(self._start_slideshow)
        if playlist_tab is not None:
            self._setup_service_plan(playlist_tab)
        for tab in (self.library_panel.bible_tab, self.library_panel.sermons_tab):
            signal = getattr(tab, "quoteImageRequested", None)
            if hasattr(signal, "connect"):
                signal.connect(self.open_quote_dialog)

        if hasattr(self.library_panel, "settings_tab"):
            self.library_panel.settings_tab.projectionSettingsRequested.connect(
                self._open_projection_settings
            )
            if hasattr(self.library_panel.settings_tab, "hdmiSettingsRequested"):
                self.library_panel.settings_tab.hdmiSettingsRequested.connect(
                    self._open_hdmi_settings
                )
            if hasattr(self.library_panel.settings_tab, "obsSettingsRequested"):
                self.library_panel.settings_tab.obsSettingsRequested.connect(
                    self._open_obs_settings
                )
            if hasattr(self.library_panel.settings_tab, "obsOutputSettingsRequested"):
                self.library_panel.settings_tab.obsOutputSettingsRequested.connect(
                    self._open_obs_output_settings
                )
            if hasattr(self.library_panel.settings_tab, "appearanceSettingsRequested"):
                self.library_panel.settings_tab.appearanceSettingsRequested.connect(
                    self._open_appearance_settings
                )
            if hasattr(self.library_panel.settings_tab, "shortcutsRequested"):
                self.library_panel.settings_tab.shortcutsRequested.connect(
                    self._show_shortcuts_dialog
                )
            if hasattr(self.library_panel.settings_tab, "aboutRequested"):
                self.library_panel.settings_tab.aboutRequested.connect(self._show_about)
            if hasattr(self.library_panel.settings_tab, "preflightRequested"):
                self.library_panel.settings_tab.preflightRequested.connect(
                    self._show_preflight_dialog
                )
            self._refresh_settings_details()

        # Projection directe : le programme live alimente l'aperçu et la barre d'état
        self._project_controller.currentSlideChanged.connect(
            self._on_current_slide_changed
        )
        self._project_controller.programChanged.connect(
            self.preview_panel.set_program_title
        )
        self.preview_panel.projectToggled.connect(self._toggle_local_projection)
        self.preview_panel.nextRequested.connect(lambda: self._handle_navigation(1))
        self.preview_panel.prevRequested.connect(lambda: self._handle_navigation(-1))
        self.preview_panel.hideToggled.connect(self._on_hide_toggled)
        self.preview_panel.quickTextRequested.connect(self._on_quick_text_requested)
        self.preview_panel.quickEditRequested.connect(self._on_quick_edit_requested)
        self.preview_panel.referencePositionToggled.connect(
            self._on_reference_position_toggled
        )
        self.preview_panel.videoControlRequested.connect(self._on_video_control)
        self.preview_panel.videoLoopToggled.connect(
            self._project_controller.set_video_loop
        )

        class _GlobalArrowNavFilter(QObject):
            def __init__(self, owner: MainWindow) -> None:
                super().__init__(owner)
                self._owner = owner

            def eventFilter(self, obj: QObject, event: QEvent) -> bool:
                if (
                    event.type() == QEvent.Type.ShortcutOverride
                    and event.key() == Qt.Key.Key_Escape
                    and _is_text_entry(QApplication.focusWidget())
                ):
                    # Escape while typing belongs to the field: it must never
                    # reach the "close projection" shortcut.
                    event.accept()
                    return False
                if event.type() != QEvent.Type.KeyPress:
                    return False

                key = event.key()

                # Don't steal arrows when editing text / numbers
                fw = QApplication.focusWidget()
                if isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox)):
                    pass
                elif key in (
                    int(Qt.Key.Key_Up),
                    int(Qt.Key.Key_Down),
                    int(Qt.Key.Key_Left),
                    int(Qt.Key.Key_Right),
                ):
                    if key in (int(Qt.Key.Key_Up), int(Qt.Key.Key_Left)):
                        self._owner._handle_navigation(-1)
                    else:
                        self._owner._handle_navigation(1)
                    return True
                elif key == int(Qt.Key.Key_Home):
                    if not self._owner._is_text_or_list_focus():
                        self._owner._jump_live_to_edge(to_start=True)
                        return True
                elif key == int(Qt.Key.Key_End):
                    if not self._owner._is_text_or_list_focus():
                        self._owner._jump_live_to_edge(to_start=False)
                        return True

                return False

        self._global_arrow_nav_filter = _GlobalArrowNavFilter(self)
        QApplication.instance().installEventFilter(self._global_arrow_nav_filter)

        # Raccourcis configurables (Réglages → Raccourcis) : télécommande de
        # présentation (Page suivante/précédente) et Stream Deck compris.
        self._shortcuts: dict[str, QShortcut] = {}
        self._install_shortcuts()

        # Ctrl+1..7 → Switch library tabs (Bible, Cantiques, Prédications,
        # Livres, Médias, Playlists, Paramètres)
        for i in range(7):
            sc_tab = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
            sc_tab.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc_tab.activated.connect(
                lambda idx=i: self.library_panel.tab_bar.setCurrentIndex(idx)
            )

        # Escape → Close projection (Only when MainWindow is active)
        sc_esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        sc_esc.setContext(Qt.ShortcutContext.WindowShortcut)
        sc_esc.activated.connect(self._close_projection)

        # ── Polling OBS toutes les 5 secondes ──────────────────────────
        self._obs_poll_timer = QTimer(self)
        self._obs_poll_timer.setInterval(5000)
        self._obs_poll_timer.timeout.connect(self._poll_obs_status)
        self._obs_poll_timer.start()
        # Premier check immédiat
        QTimer.singleShot(500, self._poll_obs_status)
        # Contrôle avant culte en arrière-plan, une fois l'interface affichée.
        if self._settings.appearance.startup_check:
            QTimer.singleShot(4000, self._run_startup_check)
        if self._settings.appearance.check_updates:
            QTimer.singleShot(12000, self._run_update_check)
        QTimer.singleShot(0, self._start_obs_output)
        # La sortie HDMI ne s'ouvre JAMAIS au démarrage : elle s'active à la
        # demande (Réglages → Sortie HDMI) et se quitte par Échap.

        # Responsive: allow window to shrink on small screens
        self.setMinimumSize(900, 550)        # Adapt initial size to screen resolution
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            w = min(1400, int(avail.width() * 0.85))
            h = min(820, int(avail.height() * 0.85))
            self.resize(w, h)
        else:
            self.resize(1400, 820)

    def event(self, event) -> bool:
        # Changing window flags recreates the native window, which drops the
        # DWM backdrop: re-apply it to the new handle.
        if event.type() == QEvent.Type.WinIdChange and window_backdrop_enabled():
            QTimer.singleShot(0, self._apply_backdrop)
        return super().event(event)

    def _apply_backdrop(self) -> None:
        if not window_backdrop_enabled() or apply_mica(self):
            return
        # No backdrop after all: fall back to the opaque window base.
        set_window_backdrop(False)
        self.setStyleSheet(get_main_window_style())
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_app_stylesheet())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_backdrop()
        if not getattr(self, "_startup_feedback_scheduled", False):
            self._startup_feedback_scheduled = True
            QTimer.singleShot(0, self._show_startup_warning)
        if not getattr(self, "_search_warmed", True):
            # Build search indexes once startup loading has settled.
            QTimer.singleShot(5000, self._warm_up_search)

    def _warm_up_search(self) -> None:
        if not self._search_warmed:
            self._search_warmed = True
            self._library_controller.warm_up_search()

    def _show_startup_warning(self) -> None:
        warning = self._settings.load_warning
        if warning:
            self._show_operator_warning("Paramètres à vérifier", warning)

    def _show_operator_warning(self, title: str, message: str) -> None:
        """Retour non bloquant : la régie reste utilisable, texte sans HTML."""
        box = QMessageBox(QMessageBox.Icon.Warning, title, message,
                          QMessageBox.StandardButton.Ok, self)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setWindowModality(Qt.WindowModality.NonModal)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.show()

    def _save_settings(self) -> bool:
        try:
            self._settings.save(self._settings_path)
        except Exception:
            log.exception("Impossible d'enregistrer les paramètres")
            self._show_operator_warning(
                "Paramètres non enregistrés",
                "Les réglages restent actifs pour cette session mais leur sauvegarde a échoué. "
                "Vérifiez l'espace disque, les droits d'accès et le profil Windows, "
                "puis réessayez avant de quitter.",
            )
            return False
        return True

    # ── Aperçu → Direct ───────────────────────────────────────────────────

    def _on_program_cued(self, cue) -> None:
        # Le premier programme préparé après un clic sur un slide de playlist
        # est celui de ce slide : le déroulé le reconnaîtra au passage au direct.
        pending = getattr(self, "_cued_playlist_item", None)
        self._cue_playlist_item = (cue, pending) if pending is not None else None
        self._cued_playlist_item = None
        self.cue_monitor.set_cue(cue, self._project_controller.cue_slide(cue))

    def _take_cue(self) -> None:
        """Send the prepared preview live (button or F2)."""
        cue = self.cue_monitor.cue()
        if cue is not None:
            self._library_controller.take(cue)
            linked = getattr(self, "_cue_playlist_item", None)
            if linked is not None and linked[0] is cue and hasattr(self, "service_plan"):
                self.service_plan.on_item_live(int(linked[1]))

    # ── Recherche globale ─────────────────────────────────────────────────

    def _setup_global_search(self, root: QWidget) -> None:
        field = self.command_bar.search_edit
        self._search_popup = GlobalSearchPopup(root)
        self._search_popup.attach(field)
        self._search_popup.hitActivated.connect(self._open_search_hit)

        self._global_search_timer = QTimer(self)
        self._global_search_timer.setSingleShot(True)
        self._global_search_timer.setInterval(220)
        self._global_search_timer.timeout.connect(self._run_global_search)
        field.textEdited.connect(self._on_global_search_edited)
        field.returnPressed.connect(self._run_global_search_now)
        self._search_warmed = False
        field.installEventFilter(self)

    def _focus_global_search(self) -> None:
        field = self.command_bar.search_edit
        field.setFocus(Qt.FocusReason.ShortcutFocusReason)
        field.selectAll()

    def _on_global_search_edited(self, text: str) -> None:
        if len(text.strip()) < 2:
            self._global_search_timer.stop()
            self._library_controller.cancel_global_search()
            self._search_popup.dismiss()
            return
        self._global_search_timer.start()

    def _run_global_search_now(self) -> None:
        # Enter with no visible results yet: search immediately.
        if not self._search_popup.isVisible():
            self._global_search_timer.stop()
            self._run_global_search()

    def _run_global_search(self) -> None:
        query = self.command_bar.search_edit.text().strip()
        if len(query) < 2:
            return
        self._search_popup.begin()
        self._library_controller.global_search(query, self._search_popup.add_group)

    def _open_search_hit(self, hit: dict) -> None:
        self._global_search_timer.stop()
        self._library_controller.cancel_global_search()
        index = self._library_controller.reveal_search_hit(hit)
        self.rail.setCurrentIndex(index)
        self.command_bar.search_edit.clearFocus()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if (
            obj is self.command_bar.search_edit
            and event.type() == QEvent.Type.FocusIn
        ):
            self._warm_up_search()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        popup = getattr(self, "_search_popup", None)
        if popup is not None and popup.isVisible():
            popup.reposition()

    def _on_rail_compact_changed(self, compact: bool) -> None:
        self._settings.appearance.rail_compact = compact
        self._save_settings()

    def _on_output_chip_clicked(self, key: str) -> None:
        """Output chips open the matching settings; they never go live."""
        if key == "projection":
            self._open_projection_settings()
        elif key == "hdmi":
            self._open_hdmi_settings()
        else:  # obs, ndi
            self._open_obs_settings()

    def _poll_obs_status(self) -> None:
        """Vérifie le statut OBS et met à jour la barre de statut.

        En mode NDI, un envoi tombé (runtime arrêté, thread en échec) est
        relancé silencieusement : le direct ne doit pas rester noir.
        """
        try:
            self._obs.ensure_ndi_running()
            web = self._obs.is_web_server_running()
            ndi = self._obs.is_ndi_running()
        except Exception:
            web = ndi = False
        self.command_bar.set_obs_connected(web)
        self.command_bar.set_ndi_active(ndi)

    def _start_obs_output(self) -> None:
        """Start OBS output automatically with the application."""
        try:
            self._obs.start()
        except Exception as exc:
            log.exception("Impossible de démarrer la sortie OBS automatiquement")
        self._poll_obs_status()

    def _focus_active_search(self) -> None:
        """Ctrl+F : donne le focus à la zone de recherche de l'onglet actif."""
        idx = self.library_panel.sidebar.currentIndex()
        tab_widgets = [
            self.library_panel.bible_tab,
            self.library_panel.hymns_tab,
            self.library_panel.sermons_tab,
            self.library_panel.expose_tab,
        ]
        if 0 <= idx < len(tab_widgets):
            tab = tab_widgets[idx]
            # Les onglets nomment leur champ de recherche différemment
            # («search» ou «search_input») : prendre le premier disponible.
            search_widget = getattr(tab, "search", None) or getattr(
                tab, "search_input", None
            )
            if search_widget is not None:
                search_widget.setFocus()
                search_widget.selectAll()

    def _focus_paragraph_search(self) -> None:
        """Ctrl+G : active la recherche globale de paragraphes dans l'onglet sermons."""
        # Basculer vers l'onglet sermons si nécessaire
        sermons_idx = 2
        self.library_panel.sidebar.setCurrentIndex(sermons_idx)
        # Activer le mode recherche paragraphes
        tab = self.library_panel.sermons_tab
        btn = getattr(tab, "_para_search_btn", None)
        search = getattr(tab, "_para_search", None)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)
            btn.clicked.emit()
        if search is not None:
            search.setFocus()
            search.selectAll()

    def _handle_navigation(self, delta: int) -> None:
        """Contextual navigation.

        - When focus is in the Library panel, arrows/prev-next scroll the relevant list
          (Bible books, Hymns titles, Sermons titles).
        - Otherwise, they navigate the live program slides.
        """
        fw = QApplication.focusWidget()
        # Les annonces en boucle cèdent immédiatement à toute action manuelle.
        # La boucle s'arrête ET la touche agit d'emblée sur le live restauré —
        # l'opérateur n'a pas besoin d'un second appui pour naviguer.
        # Le diaporama cède lui aussi : la flèche agit sur le live restauré.
        if getattr(self, "_slideshow", None) is not None and self._slideshow.is_active:
            self._slideshow.stop()
        if fw is not None and self.library_panel.isAncestorOf(fw):
            tabs = getattr(self.library_panel, "tabs", None)
            current = tabs.currentWidget() if tabs is not None else None

            target_list = None
            if current is not None:
                if hasattr(current, "books_list"):
                    target_list = getattr(current, "books_list", None)
                elif hasattr(current, "hymns_list"):
                    target_list = getattr(current, "hymns_list", None)
                elif hasattr(current, "sermons_list"):
                    target_list = getattr(current, "sermons_list", None)

            if (
                target_list is not None
                and hasattr(target_list, "count")
                and hasattr(target_list, "setCurrentRow")
            ):
                count = int(target_list.count())
                if count <= 0:
                    return
                row = int(target_list.currentRow())
                row = max(row, 0)
                new_row = max(0, min(count - 1, row + int(delta)))
                target_list.setFocus()
                target_list.setCurrentRow(new_row)

                try:
                    item = target_list.currentItem()
                    if item is not None and current is not None:
                        # Force-refresh dependent panels when navigation is driven by our global handler.
                        if (
                            hasattr(current, "sermonSelected")
                            and hasattr(current, "sermons_list")
                            and target_list is getattr(current, "sermons_list", None)
                        ):
                            sid = item.data(256)
                            if sid is not None:
                                current.sermonSelected.emit(sid)
                        elif (
                            hasattr(current, "hymnSelected")
                            and hasattr(current, "hymns_list")
                            and target_list is getattr(current, "hymns_list", None)
                        ):
                            hid = item.data(256)
                            if hid is not None:
                                current.hymnSelected.emit(int(hid))
                        elif (
                            hasattr(current, "bookSelected")
                            and hasattr(current, "books_list")
                            and target_list is getattr(current, "books_list", None)
                        ):
                            bid = item.data(256)
                            if bid is not None:
                                current.bookSelected.emit(int(bid))
                except Exception:
                    pass
                return

        if int(delta) < 0:
            self._project_controller.prev_slide()
        else:
            self._project_controller.next_slide()

    @staticmethod
    def _is_text_or_list_focus() -> bool:
        """Home/End restent natifs dans les champs et les listes."""
        from PySide6.QtWidgets import QAbstractItemView, QComboBox

        fw = QApplication.focusWidget()
        return isinstance(
            fw,
            (
                QLineEdit,
                QTextEdit,
                QPlainTextEdit,
                QSpinBox,
                QComboBox,
                QAbstractItemView,
            ),
        )

    def _jump_live_to_edge(self, to_start: bool) -> None:
        """Home / End : aller au premier ou au dernier slide du programme live."""
        count = self._project_controller.program_count
        if count <= 0:
            return
        self._project_controller.set_current_row(0 if to_start else count - 1)

    def _safe_write_json(self, path: Path, data: dict) -> None:
        """Safely write JSON to a file, handling rapid consecutive accesses on Windows."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            # Retry loop for Windows file locking
            for i in range(5):
                try:
                    tmp.replace(path)
                    return
                except PermissionError:
                    if i == 4:
                        raise
                    time.sleep(0.05)
        except Exception as e:
            log.exception("Échec d'écriture de la configuration %s", path)

    def _write_presentation_config(self) -> None:
        cfg = self._build_projection_config()
        out = self._presentation_dir / "config.json"
        self._safe_write_json(out, cfg)

    def _build_projection_config(self) -> dict:
        """Config de projection (config.json) : le style de projection."""
        cfg = self._settings.projection.to_presentation_config()
        from app.utils.church_graphics import speaker_slide_badge

        cfg["speaker_badge"] = speaker_slide_badge(self._settings.church)
        if self._settings.appearance.low_power:
            cfg.update(low_power_projection_overrides(cfg))
        return cfg

    def _hdmi_style_overrides(self):
        """Style HDMI propre, sans animation en mode PC modeste."""
        style = self._settings.hdmi.style_overrides()
        if style is not None and self._settings.appearance.low_power:
            style = {**style, **low_power_obs_overrides()}
        return style

    def _apply_low_power(self) -> None:
        """Mode PC modeste appliqué à chaud à toutes les sorties."""
        self._apply_projection_config()
        self._write_obs_config()
        window = self._projection_window
        if window is not None:
            window._low_power = self._settings.appearance.low_power
        if self._mixer_window is not None:
            self._mixer_window.set_style(self._hdmi_style_overrides())
        try:
            self._obs.set_low_power(self._settings.appearance.low_power)
        except Exception:
            log.exception("Mode PC modeste : sortie OBS non mise à jour")

    def _write_obs_config(self) -> None:
        # Les médias se projettent avec les mêmes règles partout : la sortie
        # OBS (page Navigateur, NDI) reprend le cadrage et l'habillage réglés
        # pour la projection locale — une seule vérité dans les Réglages.
        projection = self._settings.projection
        out = self._settings.obs.output
        out.media_fit = projection.media_fit
        out.media_backdrop = projection.media_backdrop
        out.media_backdrop_dim = projection.media_backdrop_dim
        cfg = self._settings.obs.to_full_obs_config()
        if self._settings.appearance.low_power:
            cfg.update(low_power_obs_overrides())
            for scene in (cfg.get("scenes") or {}).values():
                scene.update(low_power_obs_overrides())
        target = self._presentation_dir / "obs-config.json"
        self._safe_write_json(target, cfg)

    def _refresh_settings_details(self) -> None:
        """Update detail labels on settings items to show current values."""
        if hasattr(self.library_panel, "settings_tab"):
            self.library_panel.settings_tab.load_settings()

    def _sync_obs_background(
        self, mode: str, image_path: str, fit: str = "cover"
    ) -> None:
        """Mirror the background type + image + fit onto the OBS output so both
        projection layers share the same background.

        Les réglages média (cadrage, habillage) suivent le même chemin : ils
        sont réglés une fois et s'appliquent à la page OBS et au NDI.
        """
        out = self._settings.obs.output
        projection = self._settings.projection
        media_changed = (
            out.media_fit != projection.media_fit
            or out.media_backdrop != projection.media_backdrop
            or abs(
                float(out.media_backdrop_dim or 0.0)
                - float(projection.media_backdrop_dim or 0.0)
            )
            > 1e-6
        )
        if media_changed:
            out.media_fit = projection.media_fit
            out.media_backdrop = projection.media_backdrop
            out.media_backdrop_dim = projection.media_backdrop_dim
        if (
            out.bg_mode == mode
            and out.bg_image == image_path
            and out.bg_image_fit == fit
            and not media_changed
        ):
            return
        out.bg_mode = mode
        out.bg_image = image_path
        out.bg_image_fit = fit
        self._write_obs_config()
        try:
            self._obs.update_output_settings(out)
        except Exception:
            pass

    # ── Réglages : page unique, application immédiate ─────────────────────
    # Each section hosts an existing settings screen in embedded mode. Every
    # change is applied at once to the outputs and saved shortly after (the
    # save is coalesced so a slider does not rewrite settings.json per step).

    _SETTINGS_TAB = 6

    def _setup_settings_page(self) -> None:
        page = self.library_panel.settings_page
        page.register("projection", tr("local_projection"), "monitor.svg", self._build_projection_section)
        page.register("hdmi", "Sortie HDMI", "cast.svg", self._build_hdmi_section)
        page.register("split", "Découpage des textes", "file-text.svg", self._build_split_section)
        page.register("bibles", "Bibles", "book.svg", self._build_bibles_section)
        page.register("shortcuts", "Raccourcis", "zap.svg", self._build_shortcuts_section)
        page.register("update", "Mise à jour", "download.svg", self._build_update_section)
        page.register("church", "Profil de l'église", "church.svg", self._build_church_section)
        page.register("obs", tr("connectivity"), "wifi.svg", self._build_obs_section)
        page.register("obs_output", tr("lower_third_style"), "layout.svg", self._build_obs_output_section)
        page.register("appearance", tr("appearance"), "eye.svg", self._build_appearance_section)

        self._settings_save_timer = QTimer(self)
        self._settings_save_timer.setSingleShot(True)
        self._settings_save_timer.setInterval(500)
        self._settings_save_timer.timeout.connect(self._save_settings)

    def _show_settings_section(self, key: str) -> None:
        self.rail.setCurrentIndex(self._SETTINGS_TAB)
        self.library_panel.settings_page.show_section(key)

    def _settings_changed(self) -> None:
        """A setting was applied: save soon, refresh the overview texts."""
        self._settings_save_timer.start()
        self._refresh_settings_details()

    def _flush_settings_save(self) -> None:
        timer = getattr(self, "_settings_save_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()
            self._save_settings()

    # Historical entry points (settings overview cards, output chips, menus).
    def _open_projection_settings(self) -> None:
        self._show_settings_section("projection")

    def _open_obs_settings(self) -> None:
        self._show_settings_section("obs")

    def _open_obs_output_settings(self) -> None:
        self._show_settings_section("obs_output")

    def _open_appearance_settings(self) -> None:
        self._show_settings_section("appearance")

    def _open_hdmi_settings(self) -> None:
        self._show_settings_section("hdmi")

    # ── Sections ──

    def _apply_projection_config(self) -> None:
        """Write config.json and restyle every output from current settings."""
        cfg = self._build_projection_config()
        self._safe_write_json(self._presentation_dir / "config.json", cfg)
        if self._projection_window is not None and self._projection_window.isVisible():
            try:
                self._projection_window._apply_config(cfg)
            except Exception:
                log.exception("Style de projection non appliqué à la fenêtre")
        self.preview_panel.set_settings(self._settings)

    def _build_projection_section(self) -> QWidget:
        from app.ui.settings_dialog import ProjectionSettingsDialog

        dlg = embed_dialog(ProjectionSettingsDialog, self._settings.projection)
        dlg.settingsChanged.connect(self._apply_projection_settings)
        return dlg

    def _apply_projection_settings(self, projection) -> None:
        self._settings.projection = projection
        self._apply_projection_config()
        # Fond vidéo : propre à la projection locale (OBS garde sa couleur).
        obs_mode = "color" if projection.bg_mode == "video" else projection.bg_mode
        self._sync_obs_background(obs_mode, projection.bg_image, projection.bg_image_fit)
        # Media framing is shared with the OBS page / NDI output.
        self._write_obs_config()
        self._settings_changed()

    def _setup_service_plan(self, playlist_tab) -> None:
        """Déroulé du culte sous les slides de la playlist, suivi automatique."""
        from app.database.dao_service_plan import ServicePlanDao
        from app.ui.service_plan_panel import ServicePlanPanel

        self.service_plan = ServicePlanPanel(
            ServicePlanDao(self._db), selected_item=playlist_tab.selected_item_id
        )
        playlist_tab.attach_service_panel(self.service_plan)
        self.service_plan.sectionEntered.connect(
            lambda name: self._service_log.record("section", reference=name)
        )
        self.service_plan.historyRequested.connect(self._show_history_dialog)
        playlist_tab.folderSelected.connect(self.service_plan.set_folder)
        playlist_tab.itemActivated.connect(self.service_plan.on_item_live)
        playlist_tab.playRequested.connect(
            lambda item_id: item_id is not None and self.service_plan.on_item_live(item_id)
        )
        # Clic simple puis F2 : la section démarre quand le slide passe au direct.
        self._cued_playlist_item: int | None = None
        playlist_tab.itemCued.connect(lambda item_id: setattr(self, "_cued_playlist_item", item_id))

    def _build_church_section(self) -> QWidget:
        from app.ui.church_profile_dialog import ChurchProfileDialog

        dlg = embed_dialog(
            ChurchProfileDialog, self._settings.church, logo_folder=data_dir() / "church"
        )

        def on_change(profile) -> None:
            self._settings.church = profile
            # L'orateur du jour s'affiche sur les slides : mise à jour immédiate.
            self._apply_projection_config()
            self._settings_changed()

        dlg.profileChanged.connect(on_change)
        dlg.welcomeRequested.connect(self._project_welcome_screen)
        dlg.socialsRequested.connect(self._project_socials_screen)
        dlg.pastorRequested.connect(self._project_pastor_screen)
        dlg.quoteRequested.connect(self._quote_from_live)
        return dlg

    def _project_church_visual(self, filename: str, label: str, render) -> None:
        """Projette un visuel de l'église (image 1920×1080 régénérée)."""
        folder = data_dir() / "church"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / filename
        render(self._settings.church).convert("RGB").save(path)
        self._project_controller.load_program(
            "image", label, [(label, "")], entry_visuals=[str(path)]
        )

    def _project_welcome_screen(self) -> None:
        """Écran d'accueil (logo, nom, devise, horaires, réseaux)."""
        from app.utils.church_graphics import render_welcome

        self._project_church_visual(
            "accueil.png", self._settings.church.name or "Accueil", render_welcome
        )

    def _project_pastor_screen(self) -> None:
        """Écran de l'orateur du jour (le pasteur, ou l'invité du jour)."""
        from app.utils.church_graphics import render_speaker, speaker_label

        church = self._settings.church
        self._project_church_visual(
            "orateur-du-jour.png", speaker_label(church) or "Orateur du jour", render_speaker,
        )

    def _project_socials_screen(self) -> None:
        """Écran « Réseaux sociaux » de fin de culte, avec QR code."""
        from app.utils.church_graphics import render_socials

        self._project_church_visual("reseaux-sociaux.png", "Réseaux sociaux", render_socials)

    def open_quote_dialog(self, reference: str = "", text: str = "") -> None:
        from app.ui.church_profile_dialog import QuoteImageDialog

        QuoteImageDialog(self._settings.church, reference, text, self).exec()

    def _quote_from_live(self) -> None:
        slide = self._project_controller.current_slide()
        if slide is not None and slide.text:
            self.open_quote_dialog(slide.reference.replace("\n", " — "), slide.text)
        else:
            self.open_quote_dialog()

    def _build_update_section(self) -> QWidget:
        from app.ui.update_dialog import UpdateDialog

        dlg = embed_dialog(UpdateDialog, self._settings.appearance.check_updates)

        def on_auto(enabled: bool) -> None:
            self._settings.appearance.check_updates = bool(enabled)
            self._settings_changed()

        dlg.autoCheckChanged.connect(on_auto)
        return dlg

    def _run_update_check(self) -> None:
        """Nouvelle version ? Vérification discrète, en arrière-plan."""
        import threading

        from PySide6.QtCore import QObject, Signal

        from app.utils import updater

        class _Relay(QObject):
            found = Signal(object)

        self._update_relay = _Relay(self)
        self._update_relay.found.connect(self._on_update_found)

        def work() -> None:
            try:
                info = updater.check_latest()
            except Exception:
                return  # pas d'Internet : rien à signaler
            if info is not None and updater.is_newer(info.version):
                self._update_relay.found.emit(info)

        threading.Thread(target=work, name="update-check", daemon=True).start()

    def _on_update_found(self, info) -> None:
        box = QMessageBox(
            QMessageBox.Icon.Information,
            "Mise à jour disponible",
            f"Project-On {info.version} est disponible. L'installation garde "
            "vos cantiques, playlists et réglages.",
            QMessageBox.StandardButton.Close,
            self,
        )
        see = box.addButton("Voir", QMessageBox.ButtonRole.AcceptRole)
        box.buttonClicked.connect(
            lambda button: self._show_settings_section("update") if button is see else None
        )
        box.setWindowModality(Qt.WindowModality.NonModal)
        self._update_box = box
        box.show()

    def _build_shortcuts_section(self) -> QWidget:
        from app.ui.shortcut_settings_dialog import ShortcutSettingsDialog

        dlg = embed_dialog(ShortcutSettingsDialog, self._settings.shortcuts)

        def on_change(shortcuts) -> None:
            self._settings.shortcuts = shortcuts
            self._install_shortcuts()
            self._settings_changed()

        dlg.shortcutsChanged.connect(on_change)
        return dlg

    def _build_bibles_section(self) -> QWidget:
        from app.ui.bible_manager_dialog import BibleManagerDialog

        dlg = embed_dialog(BibleManagerDialog, self._db)
        dlg.biblesChanged.connect(self._library_controller.refresh_bible_books)
        return dlg

    def _build_split_section(self) -> QWidget:
        from app.ui.split_settings_dialog import SplitSettingsDialog

        dlg = embed_dialog(SplitSettingsDialog, self._settings.split)
        dlg.splitChanged.connect(self._apply_split_settings)
        return dlg

    def _apply_split_settings(self, split) -> None:
        self._settings.split = split.sanitized()
        self._project_controller.set_split_settings(self._settings.split)
        self._settings_changed()

    def _build_hdmi_section(self) -> QWidget:
        from app.ui.hdmi_settings_dialog import HdmiSettingsDialog

        dlg = embed_dialog(
            HdmiSettingsDialog, self._settings.hdmi, presentation_dir=self._presentation_dir
        )

        def on_change(new_settings) -> None:
            self._apply_hdmi_settings(new_settings)
            dlg.set_live_status(self._hdmi_live_status())
            self._settings_changed()

        dlg.hdmiChanged.connect(on_change)
        dlg.mireToggled.connect(self._toggle_hdmi_mire)
        return dlg

    def _build_obs_section(self) -> QWidget:
        from app.ui.obs_settings_dialog import ObsSettingsDialog

        dlg = embed_dialog(
            ObsSettingsDialog,
            self._settings.obs,
            obs_controller=self._obs,
            remote_client=self._obs_remote,
        )

        def commit() -> None:
            updated = dlg.get_settings()
            if updated == self._settings.obs:
                return
            # Keep the lower-third style edited elsewhere in the meantime.
            updated.output = self._settings.obs.output
            updated.scenes = self._settings.obs.scenes
            self._settings.obs = updated
            self._obs.update_settings(updated)
            self._obs_remote.apply_settings(updated.remote)
            self._settings_changed()

        # Ports and addresses are applied once typing pauses: a web server
        # restart per keystroke would drop OBS mid-service.
        dlg._change_watch = watch_inputs(dlg, commit)
        dlg.settingsChanged.connect(dlg._change_watch.start)
        return dlg

    def _build_obs_output_section(self) -> QWidget:
        from app.ui.obs_output_settings_dialog import ObsOutputSettingsDialog

        dlg = embed_dialog(ObsOutputSettingsDialog, self._settings.obs)

        def on_change(new_obs_settings) -> None:
            self._settings.obs = new_obs_settings
            self._obs.update_settings(new_obs_settings)
            self._write_obs_config()
            self._settings_changed()

        dlg.obsSettingsChanged.connect(on_change)
        return dlg

    def _build_appearance_section(self) -> QWidget:
        from app.ui.appearance_settings_dialog import AppearanceSettingsDialog

        from app.ui.window_effects import mica_supported

        appearance = self._settings.appearance
        dlg = embed_dialog(
            AppearanceSettingsDialog,
            appearance.theme,
            appearance.language,
            mica=appearance.mica if mica_supported() else None,
            low_power=appearance.low_power,
            startup_check=appearance.startup_check,
        )

        def on_change() -> None:
            theme, language = dlg.get_settings()
            mica = dlg.mica_enabled()
            low_power = dlg.low_power_enabled()
            appearance.startup_check = dlg.startup_check_enabled()
            if low_power != appearance.low_power:
                appearance.low_power = low_power
                self._apply_low_power()
            state = (theme, language, appearance.mica if mica is None else mica)
            if state == (appearance.theme, appearance.language, appearance.mica):
                self._settings_changed()
                return
            appearance.theme, appearance.language = theme, language
            if mica is not None:
                appearance.mica = mica
            self._settings_changed()
            self.library_panel.settings_page.info_bar.show_message(tr("settings_saved_msg"))

        dlg.settingsChanged.connect(on_change)
        return dlg

    def _show_about(self) -> None:
        from app.ui.about_dialog import AboutDialog

        AboutDialog.show_about(self)

    def _sync_media_hub(self, slide) -> None:
        """Aligne le lecteur vidéo partagé sur la slide courante.

        L'aperçu, le mixeur HDMI et le NDI lisent ce lecteur : ils jouent donc
        réellement la vidéo, sans décoder le fichier une fois de plus, et
        restent d'accord sur l'état lecture/pause/boucle de l'opérateur.
        """
        hub = getattr(self, "_media_hub", None)
        if hub is None:
            return
        writer = self._project_controller.slide_writer
        hub.set_loop(self._project_controller.video_loop)
        video = ""
        if slide is not None and not writer.is_hidden:
            video = str(getattr(slide, "video_path", "") or "").strip()
        if not video:
            hub.stop()
            return
        hub.load(video)
        if writer.video_playing:
            hub.play()
        else:
            hub.pause()

    def _on_current_slide_changed(self, slide) -> None:
        self._sync_media_hub(slide)
        if slide is None:
            self.preview_panel.set_slide("", "")
            self.preview_panel.set_slide_counter(-1, 0)
            self.command_bar.clear_slide()
            return
        image_path = slide.image_path or slide.background or ""
        self.preview_panel.set_slide(
            slide.reference,
            slide.text,
            image_path=image_path,
            video_path=slide.video_path or "",
            video_playing=self._project_controller.slide_writer.video_playing,
            source=slide.source,
            hidden=self._project_controller.slide_writer.is_hidden,
            video_loop=self._project_controller.video_loop,
        )
        # Bandeau « Suivant » : le slide à venir, sans changer l'écran.
        peek = self._project_controller.peek_next_slide()
        if peek is not None:
            self.preview_panel.set_next_slide(peek.reference, peek.text)
        else:
            self.preview_panel.set_next_slide("", "")
        # Update slide counter
        row = self._project_controller.current_row()
        total = self._project_controller.program_count
        self.preview_panel.set_slide_counter(row, total)
        self.command_bar.update_slide(slide.source, slide.reference, row, total)
        self._sync_expose_highlight(row)

    def _sync_expose_highlight(self, row: int) -> None:
        """Suit la projection dans l'onglet Exposé quand un chapitre est en direct.

        Pendant un diaporama le live n'affiche pas le programme chargé :
        le surlignage reprend à son arrêt (voir SlideshowController).
        """
        if getattr(self, "_slideshow", None) is not None and self._slideshow.is_active:
            return
        try:
            chapter_id = self._library_controller.live_expose_chapter_id()
        except AttributeError:
            return
        if chapter_id is None:
            return
        entry = self._project_controller.entry_index_for_row(row)
        expose_tab = getattr(self.library_panel, "expose_tab", None)
        if expose_tab is not None and hasattr(expose_tab, "highlight_live_entry"):
            expose_tab.highlight_live_entry(entry)

    def _on_reference_position_toggled(self, top: bool) -> None:
        """Bouton rapide Réf haut/bas : persiste et applique immédiatement."""
        self._settings.projection.reference_position = "top" if top else "bottom"
        self._save_settings()
        self._write_presentation_config()
        cfg = self._settings.projection.to_presentation_config()
        if self._projection_window is not None and self._projection_window.isVisible():
            try:
                self._projection_window._apply_config(cfg)
            except Exception:
                pass
        # L'aperçu fidèle reflète le nouveau placement tout de suite.
        self.preview_panel.set_settings(self._settings)

    def _on_video_control(self, command: str) -> None:
        """Boutons Lecture / Pause / Stop : projection ET aperçu synchronisés."""
        if command == "play":
            self._project_controller.set_video_playing(True)
            self.preview_panel.play_video()
        elif command == "pause":
            self._project_controller.set_video_playing(False)
            self.preview_panel.pause_video()
        elif command == "stop":
            self._project_controller.restart_video()
            self.preview_panel.stop_video()

    def _on_quick_edit_requested(self) -> None:
        """Éditer rapidement la slide affichée en direct (référence + texte)."""
        from app.ui.quick_edit_dialog import QuickEditDialog

        slide = self._project_controller.current_slide()
        ref = slide.reference if slide else ""
        text = slide.text if slide else ""

        result = QuickEditDialog.edit(ref, text, parent=self)
        if result:
            new_ref, new_text = result
            self._project_controller.update_live_slide(new_ref, new_text)

    def _on_quick_text_requested(
        self, title: str, texts: list, split: bool
    ) -> None:
        """Projette immédiatement un texte rapide (annonce, texte libre)."""
        self._project_controller.add_custom_slides(
            title, list(texts), split=split
        )

    def _log_live_slide(self, slide) -> None:
        if slide is None:
            return
        reference = slide.reference or ""
        if not reference and (slide.image_path or slide.video_path):
            reference = Path(slide.image_path or slide.video_path).stem
        self._service_log.record(
            "slide", reference=reference, text=slide.text or "",
            source=str(slide.source or ""), program=self._project_controller.program_title,
        )

    def _log_hidden(self, hidden: bool) -> None:
        self._service_log.record("hide" if hidden else "show")
        timer = getattr(self, "_recovery_timer", None)
        if timer is not None:
            timer.start()

    def _save_recovery(self) -> None:
        from app.utils import live_recovery

        live_recovery.save(
            self._recovery_path,
            live_recovery.snapshot(
                self._project_controller,
                hidden=self._project_controller.slide_writer.is_hidden,
            ),
        )

    def _offer_recovery(self) -> None:
        """Propose de reprendre le direct interrompu par un arrêt brutal."""
        from app.utils import live_recovery

        data, self._pending_recovery = self._pending_recovery, None
        if data is None or self._project_controller.program_count:
            return
        title = data.get("title") or "le programme"
        answer = QMessageBox.question(
            self,
            "Reprendre la projection ?",
            f"Project-On s'est arrêté brutalement à {data['saved_at']:%H:%M} "
            f"(coupure de courant ?) pendant « {title} ».\n\n"
            "Reprendre exactement là où vous étiez ?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            live_recovery.clear(self._recovery_path)
            return
        live_recovery.restore(self._project_controller, data)
        if data.get("hidden"):
            self._on_hide_toggled(True)
            self.preview_panel.set_hidden(True)

    def _show_history_dialog(self) -> None:
        from app.ui.history_dialog import HistoryDialog

        HistoryDialog(self._service_log, self._presentation_dir, self).exec()

    def _on_hide_toggled(self, hidden: bool) -> None:
        """Toggle visibility of text on projection and OBS."""
        self._log_hidden(bool(hidden))
        self._project_controller.slide_writer.set_hidden(hidden)
        self.command_bar.set_hidden(hidden)
        # Masquer les écritures coupe aussi la vidéo des sorties secondaires.
        self._sync_media_hub(self._project_controller.current_slide())
        # Also update OBS
        slide = self._project_controller.current_slide()
        if slide:
            img = slide.image_path or slide.background or ""
            self._obs.update_slide(
                slide.text,
                slide.reference,
                slide.source,
                hidden,
                img,
                video_path=slide.video_path or "",
                video_playing=self._project_controller.slide_writer.video_playing,
            )
        else:
            self._obs.update_slide("", "", "custom", True, "")
        self._obs_remote.notify_live(hidden)

    def _toggle_hide(self) -> None:
        """Toggle hide state via keyboard shortcut."""
        hidden = self._project_controller.slide_writer.toggle_hidden()
        self._log_hidden(hidden)
        self.preview_panel.set_hidden(hidden)
        self.command_bar.set_hidden(hidden)
        # Masquer les écritures coupe aussi la vidéo des sorties secondaires.
        self._sync_media_hub(self._project_controller.current_slide())
        # Also update OBS
        slide = self._project_controller.current_slide()
        if slide:
            img = slide.image_path or slide.background or ""
            self._obs.update_slide(
                slide.text,
                slide.reference,
                slide.source,
                hidden,
                img,
                video_path=slide.video_path or "",
                video_playing=self._project_controller.slide_writer.video_playing,
            )
        else:
            self._obs.update_slide("", "", "custom", True, "")
        self._obs_remote.notify_live(hidden)

    def _on_slide_changed_for_obs(self, slide) -> None:
        """Update OBS when the current slide changes."""
        hidden = self._project_controller.slide_writer.is_hidden
        if slide is None:
            self._obs.update_slide("", "", "custom", True, "")
        else:
            img = slide.image_path or slide.background or ""
            self._obs.update_slide(
                slide.text,
                slide.reference,
                slide.source,
                hidden,
                img,
                video_path=slide.video_path or "",
                video_playing=self._project_controller.slide_writer.video_playing,
            )
        self._obs_remote.notify_live(hidden)

    # ── New feature handlers ───────────────────────────────────────────────

    def _shortcut_handlers(self) -> dict:
        return {
            "take": self._take_cue,
            "next_slide": lambda: self._handle_navigation(1),
            "prev_slide": lambda: self._handle_navigation(-1),
            "hide": self._toggle_hide,
            "projection": self._toggle_local_projection,
            "hdmi_mire": self._toggle_hdmi_mire,
            "next_section": lambda: getattr(self, "service_plan", None)
            and self.service_plan.next_section(),
            "global_search": self._focus_global_search,
            "search": self._focus_active_search,
            "paragraph_search": self._focus_paragraph_search,
            "preflight": self._show_preflight_dialog,
            "history": lambda: getattr(self, "_show_history_dialog", lambda: None)(),
            "welcome": self._project_welcome_screen,
            "socials": self._project_socials_screen,
            "pastor": self._project_pastor_screen,
            "quote": self._quote_from_live,
            "help": self._show_shortcuts_dialog,
        }

    def _install_shortcuts(self) -> None:
        """(Re)crée les raccourcis de la régie depuis les réglages."""
        for shortcut in self._shortcuts.values():
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self._shortcuts = {}
        keys = self._settings.shortcuts.effective()
        for action_id, handler in self._shortcut_handlers().items():
            key = keys.get(action_id, "")
            if not key:
                continue
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(handler)
            self._shortcuts[action_id] = shortcut

    def _show_shortcuts_dialog(self) -> None:
        from app.ui.shortcuts_dialog import ShortcutsDialog

        dlg = ShortcutsDialog(self, keys=self._settings.shortcuts.effective())
        dlg.exec()

    def _preflight_kwargs(self) -> dict:
        from app.ui.preflight_dialog import PreflightDialog

        ndi_arch = "x64" if sys.maxsize > 2**32 else "x86"
        return {
            "database_path": app_db_path(),
            "data_directory": data_dir(),
            "presentation_directory": self._presentation_dir,
            "screen_count": len(QApplication.screens()),
            "obs_mode": self._settings.obs.mode,
            "obs_port": self._settings.obs.web_port,
            "ndi_runtime_path": resource_root() / "ndi" / "bin"
            / f"Processing.NDI.Lib.{ndi_arch}.dll",
            "hdmi_info": PreflightDialog._build_hdmi_info(self._settings),
        }

    def _run_startup_check(self) -> None:
        """Contrôle avant culte silencieux : on ne prévient qu'en cas de souci."""
        from PySide6.QtCore import QThreadPool

        from app.ui.preflight_dialog import _HealthSignals, _HealthWorker

        self._startup_check_signals = _HealthSignals(self)
        self._startup_check_signals.completed.connect(self._on_startup_check_done)
        QThreadPool.globalInstance().start(
            _HealthWorker(self._startup_check_signals, self._preflight_kwargs())
        )

    def _on_startup_check_done(self, report) -> None:
        problems = [c for c in report.checks if c.status != "success"]
        if not problems:
            return
        lines = "\n".join(
            f"• {'✖' if c.status == 'error' else '⚠'} {c.title} : {c.detail}"
            for c in problems[:6]
        )
        box = QMessageBox(
            QMessageBox.Icon.Warning if report.errors else QMessageBox.Icon.Information,
            "Contrôle avant culte",
            f"{report.errors} erreur(s), {report.warnings} avertissement(s) :\n\n{lines}",
            QMessageBox.StandardButton.Ignore,
            self,
        )
        details = box.addButton("Voir le détail", QMessageBox.ButtonRole.AcceptRole)
        box.buttonClicked.connect(
            lambda button: self._show_preflight_dialog() if button is details else None
        )
        # Non modal : la régie reste utilisable pendant la lecture du message.
        box.setWindowModality(Qt.WindowModality.NonModal)
        self._startup_check_box = box
        box.show()

    def _show_preflight_dialog(self) -> None:
        from app.ui.preflight_dialog import PreflightDialog

        ndi_arch = "x64" if sys.maxsize > 2**32 else "x86"
        ndi_runtime = (
            resource_root() / "ndi" / "bin" / f"Processing.NDI.Lib.{ndi_arch}.dll"
        )
        dialog = PreflightDialog(
            database_path=app_db_path(),
            data_directory=data_dir(),
            presentation_directory=self._presentation_dir,
            ndi_runtime_path=ndi_runtime,
            settings=self._settings,
            parent=self,
        )
        dialog.exec()

    def _toggle_local_projection(self, checked: bool | None = None) -> None:
        """Toggle the local projection window."""
        should_show = checked
        if should_show is None:
            # If toggle via shortcut, invert current state
            should_show = not (
                self._projection_window is not None
                and self._projection_window.isVisible()
            )

        if should_show:
            self._open_local_projection()
        else:
            self._close_projection()

    def _close_projection(self) -> None:
        if self._projection_window is not None:
            self._projection_window.close()
            self._projection_window = None
        # Sans fenêtre de projection, la bande son de la vidéo revient au
        # lecteur partagé : les sorties HDMI/NDI ne restent jamais muettes.
        self._set_hub_audio(enabled=True)
        self.preview_panel.set_project_active(False)
        self.command_bar.set_project_active(False)

    def _set_hub_audio(self, enabled: bool) -> None:
        hub = getattr(self, "_media_hub", None)
        if hub is None:
            return
        try:
            hub.set_audio_enabled(bool(enabled))
        except Exception:
            pass

    def _abandon_slideshow_for_manual_load(self) -> None:
        """Crochet « chargement manuel » : clos le diaporama sans restauration.

        Appelé par ProjectOnController avant tout load_program demandé par
        l'opérateur. Sans ceci, le diaporama actif continuerait d'écraser le
        nouveau programme au tick suivant.
        """
        if getattr(self, "_slideshow", None) is not None and self._slideshow.is_active:
            self._slideshow.abandon()

    def _start_slideshow(self, medias: list) -> None:
        """Lance un diaporama (galerie, bibliothèque entière ou playlist)."""
        slideshow = getattr(self, "_slideshow", None)
        if slideshow is None:
            return
        slideshow.set_default_duration(
            self._settings.projection.media_default_duration
        )
        entries = self._library_controller.slideshow_entries(medias)
        slideshow.start(entries)
        self._refresh_settings_details()

    def _open_local_projection(self) -> None:
        if self._projection_window is None:
            self._projection_window = ProjectionWindow(self._presentation_dir)
            self._projection_window._low_power = self._settings.appearance.low_power
            # Fin de vidéo : le diaporama enchaîne sur le média suivant.
            self._projection_window.videoFinished.connect(
                lambda: self._slideshow.on_video_finished()
                if getattr(self, "_slideshow", None) is not None
                else None
            )
            self._projection_window.destroyed.connect(
                lambda: setattr(self, "_projection_window", None)
            )
            # Also sync button state when closed externally
            self._projection_window.destroyed.connect(
                lambda: self.preview_panel.set_project_active(False)
            )
            self._projection_window.destroyed.connect(
                lambda: self.command_bar.set_project_active(False)
            )

        self._projection_window.show()
        self._projection_window.raise_()
        self._projection_window.activateWindow()
        # Le son repart par la projection : le lecteur partagé (aperçu, HDMI,
        # NDI) redevient muet pour éviter deux bandes son en décalé.
        self._set_hub_audio(enabled=False)
        self.preview_panel.set_project_active(True)
        self.command_bar.set_project_active(True)

    # ── Sortie HDMI / mixeur vidéo ─────────────────────────────────────

    def _apply_hdmi_settings(self, hdmi) -> None:
        self._settings.hdmi = hdmi.sanitized()
        if self._settings.hdmi.enabled:
            self._open_mixer_window()
        else:
            self._close_mixer()

    def _mixer_exclude_screen(self) -> str:
        """Écran à éviter en choix auto : celui de la projection locale."""
        window = self._projection_window
        if window is not None and getattr(window, "_active_display_screen", ""):
            return str(window._active_display_screen)
        return str(self._settings.projection.display_screen or "")

    def _open_mixer_window(self) -> None:
        from app.ui.mixer_output_window import MixerOutputWindow

        if self._mixer_window is None:
            hdmi = self._settings.hdmi
            self._mixer_window = MixerOutputWindow(
                self._presentation_dir,
                screen=hdmi.screen,
                letterbox=hdmi.letterbox,
                exclude_screen=self._mixer_exclude_screen(),
                key_color=hdmi.key_color,
                text_scale=hdmi.text_scale,
                offset_y=hdmi.offset_y,
                layout=hdmi.layout,
                style=self._hdmi_style_overrides(),
            )
            self._mixer_window.destroyed.connect(
                lambda: setattr(self, "_mixer_window", None)
            )
            self._mixer_window.destroyed.connect(
                lambda: self.command_bar.set_hdmi_active(False)
            )
            # Vidéo réellement lue sur la sortie mixeur, via le lecteur partagé.
            self._mixer_window.set_media_hub(self._media_hub)
            # Échap : quitter la sortie désactive le réglage (sinon la régie
            # afficherait « active » alors que rien n'est projeté).
            self._mixer_window.escapeRequested.connect(self._leave_hdmi_mode)
        else:
            hdmi = self._settings.hdmi
            self._mixer_window.set_screen(hdmi.screen)
            self._mixer_window.set_letterbox(hdmi.letterbox)
            self._mixer_window.set_key_color(hdmi.key_color)
            self._mixer_window.set_text_scale(hdmi.text_scale)
            self._mixer_window.set_offset_y(hdmi.offset_y)
            self._mixer_window.set_layout(hdmi.layout)
            self._mixer_window.set_style(self._hdmi_style_overrides())
            self._mixer_window.show()
        self._update_hdmi_status()

    def _leave_hdmi_mode(self) -> None:
        """Échap sur la sortie HDMI : on éteint la sortie, pas juste la fenêtre."""
        window = self._mixer_window
        if window is not None:
            window.close()
            self._mixer_window = None
        if self._settings.hdmi.enabled:
            self._settings.hdmi.enabled = False
            self._save_settings()
        self.command_bar.set_hdmi_active(False)
        self._refresh_settings_details()

    def _close_mixer(self) -> None:
        window = self._mixer_window
        if window is not None:
            window.close()
            self._mixer_window = None
        self.command_bar.set_hdmi_active(False)

    def _hdmi_live_status(self) -> str:
        window = self._mixer_window
        if window is None or not window.isVisible():
            return "Inactive"
        key_names = {"green": "verte", "magenta": "magenta", "blue": "bleue"}
        key = key_names.get(self._settings.hdmi.key_color, "verte")
        return f"En direct vers {window.active_screen or '?'} · clé {key}"

    def _update_hdmi_status(self) -> None:
        window = self._mixer_window
        active = window is not None and window.isVisible()
        self.command_bar.set_hdmi_active(
            active, window.active_screen if active else ""
        )

    def _toggle_hdmi_mire(self) -> None:
        window = self._mixer_window
        if window is not None:
            window.toggle_mire()

    def closeEvent(self, event) -> None:
        """Handle application shutdown gracefully."""
        self._flush_settings_save()
        # Fermeture normale : rien à reprendre au prochain démarrage.
        if hasattr(self, "_recovery_timer"):
            self._recovery_timer.stop()
            from app.utils import live_recovery

            live_recovery.clear(self._recovery_path)
        app = QApplication.instance()
        if app is not None and hasattr(self, "_global_arrow_nav_filter"):
            try:
                app.removeEventFilter(self._global_arrow_nav_filter)
            except Exception:
                log.exception("Échec du retrait du filtre global de navigation")
        # Fermer la fenêtre de projection pour ne pas laisser un écran
        # plein écran zombie après la fermeture de la régie.
        if getattr(self, "_projection_window", None) is not None:
            try:
                self._projection_window.close()
            except Exception:
                log.exception("Échec de fermeture de la fenêtre de projection")
        if getattr(self, "_mixer_window", None) is not None:
            try:
                self._mixer_window.close()
            except Exception:
                log.exception("Échec de fermeture de la sortie HDMI")
        # Stop OBS server threads so Python can exit completely
        if hasattr(self, "_obs") and self._obs:
            self._obs.stop()
        if hasattr(self, "_obs_remote") and self._obs_remote:
            self._obs_remote.disconnect_from_obs()
        event.accept()


def low_power_projection_overrides(cfg: dict) -> dict:
    """Projection allégée : ni transition, ni zoom lent, ni fond vidéo."""
    out = {"animation_enabled": False, "animation_type": "none", "ken_burns": False}
    if cfg.get("bg_mode") == "video":
        out["bg_mode"] = "color"
    return out


def low_power_obs_overrides() -> dict:
    """Page OBS, NDI et HDMI allégés : sans animation ni flou."""
    return {"animation_enabled": False, "animation_type": "none", "bg_blur": False}
