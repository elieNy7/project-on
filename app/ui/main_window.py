from __future__ import annotations

import copy
import json
import time
from pathlib import Path

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QGraphicsDropShadowEffect,
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
from app.ui.icons import app_logo_icon
from app.ui.library_panel import LibraryPanel
from app.ui.playlist_panel import PlaylistPanel
from app.ui.preview_panel import PreviewPanel
from app.ui.projection_window import ProjectionWindow
from app.ui.status_bar import StatusBar
from app.ui.theme import (
    Colors,
    Spacing,
    get_main_window_style,
    get_theme,
    get_splitter_style,
    set_theme,
)
from app.utils.app_paths import ensure_presentation_workdir, settings_path
from app.utils.library_controller import LibraryController
from app.utils.obs_controller import ObsController
from app.utils.project_on_controller import ProjectOnController
from app.utils.settings import AppSettings
from app.utils.translations import set_language, tr
from app.version import __version__


class MainWindow(QMainWindow):
    def __init__(self, db: Database) -> None:
        super().__init__()

        # Load settings first to apply theme and language
        self._settings_path = settings_path()
        self._settings = AppSettings.load(self._settings_path)

        # Apply theme and language from settings
        set_theme(self._settings.appearance.theme)
        set_language(self._settings.appearance.language)

        self.setWindowTitle(f"Project-On v{__version__}")

        self.setWindowIcon(app_logo_icon())
        self.setStyleSheet(get_main_window_style())

        presentation_dir = ensure_presentation_workdir()

        self._projection_window: ProjectionWindow | None = None
        self._presentation_dir = presentation_dir
        self._write_presentation_config()
        self._write_obs_config()

        self._project_controller = ProjectOnController(
            db=db, presentation_dir=presentation_dir
        )
        self._obs = ObsController(settings=self._settings.obs)

        # Connect slide changes to OBS controller
        self._project_controller.currentSlideChanged.connect(
            self._on_slide_changed_for_obs
        )

        root = QWidget(self)
        self.setCentralWidget(root)

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.MD)
        root_layout.setSpacing(Spacing.SM)

        splitter = QSplitter(root)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(Spacing.XS)
        splitter.setStyleSheet(get_splitter_style())

        self.library_panel = LibraryPanel(splitter)
        self.playlist_panel = PlaylistPanel(splitter)
        self.preview_panel = PreviewPanel(splitter, self._settings)

        # Apply subtle shadows to panels for depth
        is_light_theme = get_theme() == "light"
        for panel in (self.library_panel, self.playlist_panel, self.preview_panel):
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(22 if is_light_theme else 28)
            shadow.setXOffset(0)
            shadow.setYOffset(3 if is_light_theme else 4)
            shadow.setColor(
                QColor(15, 23, 42, 42) if is_light_theme else QColor(0, 0, 0, 110)
            )
            panel.setGraphicsEffect(shadow)

        splitter.addWidget(self.library_panel)
        splitter.addWidget(self.playlist_panel)
        splitter.addWidget(self.preview_panel)

        # Balance: Playlist (45%), Library (20%), Preview (35%)
        splitter.setStretchFactor(0, 20)
        splitter.setStretchFactor(1, 45)
        splitter.setStretchFactor(2, 35)

        # Proportional initial sizes
        width = self.width() if self.width() > 800 else 1400
        splitter.setSizes([int(width * 0.20), int(width * 0.45), int(width * 0.35)])

        root_layout.addWidget(splitter, 1)

        # Status bar
        self.status_bar = StatusBar(root)
        self.status_bar.setContentsMargins(Spacing.SM, 0, Spacing.SM, 0)
        self.status_bar.setStyleSheet(
            f"""
            QFrame#StatusBar {{
                background: {Colors.BG_SECONDARY};
                border: none;
                border-radius: 10px;
                color: {Colors.TEXT_SECONDARY};
                min-height: 26px;
            }}
            """
        )
        root_layout.addWidget(self.status_bar)

        self.playlist_panel.set_model(self._project_controller.playlist_model)

        self._library_controller = LibraryController(
            db=db,
            project_controller=self._project_controller,
            bible_tab=self.library_panel.bible_tab,
            hymns_tab=self.library_panel.hymns_tab,
            sermons_tab=self.library_panel.sermons_tab,
            playlist_panel=self.playlist_panel,
            expose_tab=self.library_panel.expose_tab,
        )

        # Lazy-load sermons & expose when their tab is first shown
        self.library_panel.tab_bar.currentChanged.connect(
            self._library_controller.on_tab_shown,
        )

        if hasattr(self.library_panel, "settings_tab"):
            self.library_panel.settings_tab.projectionSettingsRequested.connect(
                self._open_projection_settings
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
            if hasattr(self.library_panel.settings_tab, "settingsApplied"):
                self.library_panel.settings_tab.settingsApplied.connect(
                    self._apply_settings_from_settings_tab
                )
            self._refresh_settings_details()

        # Connect playlist panel signals
        self.playlist_panel.moveRequested.connect(self._project_controller.move_index)
        self.playlist_panel.duplicateRequested.connect(
            self._project_controller.duplicate_item
        )

        self.playlist_panel.slideSelected.connect(
            self._project_controller.set_current_row
        )
        if hasattr(self.playlist_panel, "removeRequested"):
            self.playlist_panel.removeRequested.connect(
                self._project_controller.remove_row
            )
        if hasattr(self.playlist_panel, "removeIndexRequested"):
            self.playlist_panel.removeIndexRequested.connect(
                self._project_controller.remove_index
            )
        if hasattr(self.playlist_panel, "clearRequested"):
            self.playlist_panel.clearRequested.connect(
                self._project_controller.clear_playlist
            )
        if hasattr(self.playlist_panel, "folderCreateRequested"):
            self.playlist_panel.folderCreateRequested.connect(
                self._on_folder_create_requested
            )
        if hasattr(self.playlist_panel, "folderDeleteRequested"):
            self.playlist_panel.folderDeleteRequested.connect(
                self._project_controller.delete_folder
            )
        if hasattr(self.playlist_panel, "customSlideRequested"):
            self.playlist_panel.customSlideRequested.connect(
                self._on_custom_slide_requested
            )
        if hasattr(self.playlist_panel, "customSlidesRequested"):
            self.playlist_panel.customSlidesRequested.connect(
                self._on_custom_slides_requested
            )
        if hasattr(self.playlist_panel, "folderRenameRequested"):
            self.playlist_panel.folderRenameRequested.connect(
                self._project_controller.rename_folder
            )
        self._project_controller.currentSlideChanged.connect(
            self._on_current_slide_changed
        )
        if hasattr(self.playlist_panel, "set_current_row"):
            self._project_controller.currentRowChanged.connect(
                self.playlist_panel.set_current_row
            )
        if hasattr(self.playlist_panel, "editRequested"):
            self.playlist_panel.editRequested.connect(
                self._on_playlist_edit_requested
            )
        if hasattr(self.playlist_panel, "undoRequested"):
            self.playlist_panel.undoRequested.connect(self._undo_playlist)

        self.preview_panel.projectToggled.connect(self._toggle_local_projection)
        self.preview_panel.nextRequested.connect(lambda: self._handle_navigation(1))
        self.preview_panel.prevRequested.connect(lambda: self._handle_navigation(-1))
        self.preview_panel.hideToggled.connect(self._on_hide_toggled)

        class _GlobalArrowNavFilter(QObject):
            def __init__(self, owner: MainWindow) -> None:
                super().__init__(owner)
                self._owner = owner

            def eventFilter(self, obj: QObject, event: QEvent) -> bool:
                if event.type() != QEvent.Type.KeyPress:
                    return False

                key = event.key()
                if key not in (
                    int(Qt.Key.Key_Up),
                    int(Qt.Key.Key_Down),
                    int(Qt.Key.Key_Left),
                    int(Qt.Key.Key_Right),
                ):
                    return False

                # Don't steal arrows when editing text / numbers
                fw = QApplication.focusWidget()
                if isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox)):
                    return False

                if key in (int(Qt.Key.Key_Up), int(Qt.Key.Key_Left)):
                    self._owner._handle_navigation(-1)
                    return True

                self._owner._handle_navigation(1)
                return True

        self._global_arrow_nav_filter = _GlobalArrowNavFilter(self)
        QApplication.instance().installEventFilter(self._global_arrow_nav_filter)

        sc = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
        sc.activated.connect(self._delete_current_playlist_item)

        sc = QShortcut(QKeySequence(Qt.Key.Key_B), self)
        sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
        sc.activated.connect(self._toggle_hide)

        # ── New shortcuts ──
        # F1 → Shortcuts help dialog
        sc_f1 = QShortcut(QKeySequence(Qt.Key.Key_F1), self)
        sc_f1.setContext(Qt.ShortcutContext.ApplicationShortcut)
        sc_f1.activated.connect(self._show_shortcuts_dialog)

        # Ctrl+Z → Undo
        sc_undo = QShortcut(QKeySequence("Ctrl+Z"), self)
        sc_undo.setContext(Qt.ShortcutContext.ApplicationShortcut)
        sc_undo.activated.connect(self._undo_playlist)

        # Ctrl+1..5 → Switch library tabs
        for i in range(5):
            sc_tab = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
            sc_tab.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc_tab.activated.connect(
                lambda idx=i: self.library_panel.tab_bar.setCurrentIndex(idx)
            )

        # F5 → Toggle local projection
        sc_f5 = QShortcut(QKeySequence(Qt.Key.Key_F5), self)
        sc_f5.setContext(Qt.ShortcutContext.ApplicationShortcut)
        sc_f5.activated.connect(self._toggle_local_projection)

        # Ctrl+F → Focus recherche dans l'onglet actif
        sc_search = QShortcut(QKeySequence("Ctrl+F"), self)
        sc_search.setContext(Qt.ShortcutContext.ApplicationShortcut)
        sc_search.activated.connect(self._focus_active_search)

        # Ctrl+G → Focus recherche paragraphe global
        sc_para = QShortcut(QKeySequence("Ctrl+G"), self)
        sc_para.setContext(Qt.ShortcutContext.ApplicationShortcut)
        sc_para.activated.connect(self._focus_paragraph_search)

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
        QTimer.singleShot(0, self._start_obs_output)

        # Responsive: allow window to shrink on small screens
        self.setMinimumSize(900, 550)

        # Adapt initial size to screen resolution
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            w = min(1400, int(avail.width() * 0.85))
            h = min(820, int(avail.height() * 0.85))
            self.resize(w, h)
        else:
            self.resize(1400, 820)

    def _poll_obs_status(self) -> None:
        """Vérifie le statut OBS et met à jour la barre de statut."""
        try:
            connected = self._obs.is_web_server_running() or self._obs.is_ndi_running()
        except Exception:
            connected = False
        self.status_bar.set_obs_connected(connected)

    def _start_obs_output(self) -> None:
        """Start OBS output automatically with the application."""
        try:
            self._obs.start()
        except Exception as exc:
            print(f"Unable to start OBS output automatically: {exc}")
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
            # Chercher le premier QLineEdit nommé 'search'
            search_widget = getattr(tab, "search", None)
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
        - Otherwise, they navigate the playlist slides.
        """
        fw = QApplication.focusWidget()
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

    def _switch_library_tab(self, delta: int) -> None:
        tabs = getattr(self.library_panel, "tabs", None)
        if tabs is None:
            return
        count = int(tabs.count())
        if count <= 0:
            return
        idx = int(tabs.currentIndex())
        tabs.setCurrentIndex((idx + int(delta)) % count)

    def _set_library_tab(self, index: int) -> None:
        tabs = getattr(self.library_panel, "tabs", None)
        if tabs is None:
            return
        if 0 <= int(index) < int(tabs.count()):
            tabs.setCurrentIndex(int(index))

    def _focus_library(self) -> None:
        tabs = getattr(self.library_panel, "tabs", None)
        if tabs is None:
            return
        tabs.setFocus()
        self._focus_search()

    def _focus_playlist(self) -> None:
        if hasattr(self.playlist_panel, "list_view"):
            self.playlist_panel.list_view.setFocus()

    def _focus_preview(self) -> None:
        if hasattr(self.preview_panel, "slide_view"):
            self.preview_panel.slide_view.setFocus()

    def _focus_search(self) -> None:
        tabs = getattr(self.library_panel, "tabs", None)
        if tabs is None:
            return
        current = tabs.currentWidget()
        if current is None:
            return
        # Bible
        if hasattr(current, "search"):
            try:
                current.search.setFocus()
                if hasattr(current.search, "selectAll"):
                    current.search.selectAll()
                return
            except Exception:
                pass

    def _activate_current(self) -> None:
        tabs = getattr(self.library_panel, "tabs", None)
        if tabs is None:
            return
        current = tabs.currentWidget()
        if current is None:
            return

        # Bible: add selected verse
        if hasattr(current, "verses_list") and hasattr(
            current, "_on_add_verse_clicked"
        ):
            try:
                if current.verses_list.hasFocus():
                    current._on_add_verse_clicked()
                    return
            except Exception:
                pass

        # Sermons: add selected paragraph
        if hasattr(current, "paragraphs_list") and hasattr(
            current, "_on_add_paragraph_clicked"
        ):
            try:
                if current.paragraphs_list.hasFocus():
                    current._on_add_paragraph_clicked()
                    return
            except Exception:
                pass

        # Hymns: add all stanzas of selected hymn or selected stanza
        if hasattr(current, "stanzas_list") and hasattr(
            current, "_on_add_stanza_clicked"
        ):
            try:
                if current.stanzas_list.hasFocus() or current.hymns_list.hasFocus():
                    current._on_add_stanza_clicked()
                    return
            except Exception:
                pass

    def _delete_current_playlist_item(self) -> None:
        row = self._project_controller.current_row()
        if row >= 0:
            self._project_controller.remove_row(row)

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
            print(f"Error saving config to {path}: {e}")

    def _write_presentation_config(self) -> None:
        cfg = self._settings.projection.to_presentation_config()
        out = self._presentation_dir / "config.json"
        self._safe_write_json(out, cfg)

    def _write_obs_config(self) -> None:
        cfg = self._settings.obs.output.to_obs_config()
        out = self._presentation_dir / "obs-config.json"
        self._safe_write_json(out, cfg)

    def _refresh_settings_details(self) -> None:
        """Update detail labels on settings items to show current values."""
        if hasattr(self.library_panel, "settings_tab"):
            self.library_panel.settings_tab.load_settings()

    def _apply_settings_from_settings_tab(self, settings) -> None:
        """Apply settings imported or reset from the Settings hub."""
        self._settings = settings
        self._settings.save(self._settings_path)
        self._write_presentation_config()
        self._write_obs_config()
        self._obs.update_settings(self._settings.obs)
        if self._projection_window is not None and self._projection_window.isVisible():
            try:
                self._projection_window._apply_config(
                    self._settings.projection.to_presentation_config()
                )
            except Exception:
                pass
        self._refresh_settings_details()

    def _sync_obs_background(
        self, mode: str, image_path: str, fit: str = "cover"
    ) -> None:
        """Mirror the background type + image + fit onto the OBS output so both
        projection layers share the same background."""
        out = self._settings.obs.output
        if (
            out.bg_mode == mode
            and out.bg_image == image_path
            and out.bg_image_fit == fit
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

    def _open_projection_settings(self) -> None:
        from app.ui.settings_dialog import ProjectionSettingsDialog

        # Deep copy original for robust revert
        original_projection = copy.deepcopy(self._settings.projection)
        original_obs_mode = self._settings.obs.output.bg_mode
        original_obs_bg = self._settings.obs.output.bg_image
        original_obs_fit = self._settings.obs.output.bg_image_fit
        dlg = ProjectionSettingsDialog(self._settings.projection, parent=self)

        def on_live_update(new_settings):
            # Apply to temp state and write config for immediate visual effect
            self._settings.projection = new_settings
            cfg = new_settings.to_presentation_config()
            self._safe_write_json(self._presentation_dir / "config.json", cfg)
            if self._projection_window is not None and self._projection_window.isVisible():
                try:
                    self._projection_window._apply_config(cfg)
                except Exception:
                    pass
            # Keep the OBS output background in sync with the global setting
            self._sync_obs_background(
                new_settings.bg_mode,
                new_settings.bg_image,
                new_settings.bg_image_fit,
            )

        dlg.settingsChanged.connect(on_live_update)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Committed
            self._sync_obs_background(
                self._settings.projection.bg_mode,
                self._settings.projection.bg_image,
                self._settings.projection.bg_image_fit,
            )
            self._settings.save(self._settings_path)
            self._refresh_settings_details()
        else:
            # Revert to deep copy
            self._settings.projection = original_projection
            self._write_presentation_config()
            self._sync_obs_background(
                original_obs_mode, original_obs_bg, original_obs_fit
            )
            if self._projection_window is not None and self._projection_window.isVisible():
                try:
                    self._projection_window._apply_config(
                        original_projection.to_presentation_config()
                    )
                except Exception:
                    pass

    def _open_obs_settings(self) -> None:
        from app.ui.obs_settings_dialog import ObsSettingsDialog

        updated = ObsSettingsDialog.edit(
            self._settings.obs, obs_controller=self._obs, parent=self
        )
        if updated is None:
            return
        self._settings.obs = updated
        self._settings.save(self._settings_path)
        self._obs.update_settings(updated)
        self._refresh_settings_details()

    def _open_obs_output_settings(self) -> None:
        from app.ui.obs_output_settings_dialog import ObsOutputSettingsDialog

        # Create dialog instance instead of using static edit() to connect signals for live preview
        dlg = ObsOutputSettingsDialog(self._settings.obs.output, parent=self)

        # Connect live updates
        def on_live_update(new_settings):
            self._obs.update_output_settings(new_settings)

        dlg.settingsChanged.connect(on_live_update)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            updated = dlg.get_settings()
            self._settings.obs.output = updated
            self._settings.save(self._settings_path)
            self._write_obs_config()
            # Final update
            self._obs.update_output_settings(updated)
            self._refresh_settings_details()
        else:
            # Revert to original settings if cancelled
            self._obs.update_output_settings(self._settings.obs.output)

    def _open_appearance_settings(self) -> None:
        from app.ui.appearance_settings_dialog import AppearanceSettingsDialog
        from app.utils.translations import tr

        result = AppearanceSettingsDialog.edit(
            self._settings.appearance.theme,
            self._settings.appearance.language,
            parent=self,
        )
        if result is None:
            return
        theme, language = result
        self._settings.appearance.theme = theme
        self._settings.appearance.language = language
        self._settings.save(self._settings_path)

        self._refresh_settings_details()

        # Notify user that restart is needed for theme/language changes.
        QMessageBox.information(
            self,
            tr("settings_saved"),
            tr("settings_saved_msg"),
        )

    def _show_about(self) -> None:
        from app.ui.about_dialog import AboutDialog

        AboutDialog.show_about(self)

    def _show_obs_url(self) -> None:
        mode = str(self._settings.obs.mode or "web").lower()
        if mode not in ("web", "ndi"):
            mode = "web"

        if mode == "web":
            if not self._obs.is_web_server_running():
                ok = self._obs.start_web_server()
                if not ok:
                    QMessageBox.warning(
                        self,
                        tr("server_error"),
                        tr("server_error_detail"),
                    )
                    return

            obs_url = self._obs.get_web_server_url()

            msg = QMessageBox(self)
            msg.setWindowTitle(tr("obs_server_title"))
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setText(tr("obs_server_started"))
            msg.setInformativeText(f"{tr('obs_url_info')}\n{obs_url}")
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)

            copy_btn = msg.addButton(tr("copy_url"), QMessageBox.ButtonRole.ActionRole)
            open_btn = msg.addButton(
                tr("open_browser"), QMessageBox.ButtonRole.ActionRole
            )
            msg.exec()

            if msg.clickedButton() == copy_btn:
                clipboard = QApplication.clipboard()
                if clipboard:
                    clipboard.setText(obs_url)
            elif msg.clickedButton() == open_btn:
                self._obs.open_in_browser()
        else:
            ok = self._obs.start_ndi()
            if not ok:
                ndi_status = self._obs.get_ndi_availability()
                detail = str(
                    ndi_status.get("message")
                    or tr("ndi_runtime_missing")
                )
                QMessageBox.warning(
                    self,
                    tr("ndi_unavailable_title"),
                    tr("ndi_unavailable_detail") + "\n\n" + detail,
                )
                return

            ndi_name = self._settings.obs.ndi_source_name or "Project-On"
            QMessageBox.information(
                self,
                tr("ndi_active"),
                tr("ndi_active_detail").format(name=ndi_name),
            )

    def _on_current_slide_changed(self, slide) -> None:
        if slide is None:
            self.preview_panel.set_slide("", "")
            self.preview_panel.set_slide_counter(-1, 0)
            self.status_bar.clear_slide()
            return
        image_path = slide.image_path or slide.background or ""
        self.preview_panel.set_slide(slide.reference, slide.text, image_path=image_path)
        # Update slide counter
        row = self._project_controller.current_row()
        total = self._project_controller.playlist_model.flat_row_count()
        self.preview_panel.set_slide_counter(row, total)
        self.status_bar.update_slide(slide.source, slide.reference, row, total)

    def _on_quick_edit_requested(self) -> None:
        """Open a dialog to quickly edit the current displayed slide."""
        from app.ui.quick_edit_dialog import QuickEditDialog

        ref = self.preview_panel.get_current_reference()
        text = self.preview_panel.slide_view.text()

        result = QuickEditDialog.edit(ref, text, parent=self)
        if result:
            new_ref, new_text = result
            self._project_controller.update_live_slide(new_ref, new_text)

    def _on_playlist_edit_requested(self, index) -> None:
        """Edit a playlist item persistently via QuickEditDialog."""
        from app.ui.quick_edit_dialog import QuickEditDialog

        if not index.isValid():
            return
            
        from app.utils.playlist_model import PlaylistRoles
        slide = index.data(PlaylistRoles.SlideDataRole)
        is_folder = index.data(PlaylistRoles.IsFolderRole)
        
        if slide is None or is_folder:
            return
            
        result = QuickEditDialog.edit(slide.reference, slide.text, parent=self)
        if result:
            new_ref, new_text = result
            # Persist via controller
            self._project_controller.update_item_content(index, new_ref, new_text)

    def _on_folder_create_requested(self, name: str) -> None:
        """Crée un nouveau dossier dans la playlist (toujours à la racine)."""
        folder_index = self._project_controller.create_folder(name, None)
        # Select and expand the new folder in the playlist view
        self.playlist_panel.select_and_expand_folder(folder_index)

    def _on_custom_slide_requested(self, title: str, text: str) -> None:
        """Ajoute une slide personnalisée à la playlist."""
        parent = self.playlist_panel.get_selected_folder_index()
        self._project_controller.add_custom_slide(title, text, parent)

    def _on_custom_slides_requested(
        self, title: str, texts: list, split: bool
    ) -> None:
        """Ajoute une ou plusieurs slides de texte selon le mode de découpage."""
        parent = self.playlist_panel.get_selected_folder_index()
        self._project_controller.add_custom_slides(
            title, list(texts), parent, split=split
        )

    def _on_hide_toggled(self, hidden: bool) -> None:
        """Toggle visibility of text on projection and OBS."""
        self._project_controller.slide_writer.set_hidden(hidden)
        self.status_bar.set_hidden(hidden)
        # Also update OBS
        slide = self._project_controller.playlist_model.slide_at(
            self._project_controller.current_row()
        )
        if slide:
            img = slide.image_path or slide.background or ""
            self._obs.update_slide(slide.text, slide.reference, slide.source, hidden, img)
        else:
            self._obs.update_slide("", "", "custom", True, "")

    def _toggle_hide(self) -> None:
        """Toggle hide state via keyboard shortcut."""
        hidden = self._project_controller.slide_writer.toggle_hidden()
        self.preview_panel.set_hidden(hidden)
        self.status_bar.set_hidden(hidden)
        # Also update OBS
        slide = self._project_controller.playlist_model.slide_at(
            self._project_controller.current_row()
        )
        if slide:
            img = slide.image_path or slide.background or ""
            self._obs.update_slide(slide.text, slide.reference, slide.source, hidden, img)
        else:
            self._obs.update_slide("", "", "custom", True, "")

    def _on_slide_changed_for_obs(self, slide) -> None:
        """Update OBS when the current slide changes."""
        hidden = self._project_controller.slide_writer.is_hidden
        if slide is None:
            self._obs.update_slide("", "", "custom", True, "")
        else:
            img = slide.image_path or slide.background or ""
            self._obs.update_slide(slide.text, slide.reference, slide.source, hidden, img)

    # ── New feature handlers ───────────────────────────────────────────────

    def _show_shortcuts_dialog(self) -> None:
        from app.ui.shortcuts_dialog import ShortcutsDialog

        dlg = ShortcutsDialog(self)
        dlg.exec()

    def _undo_playlist(self) -> None:
        if not self._project_controller.undo():
            QMessageBox.information(self, "Project-On", tr("nothing_to_undo"))

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
        self.preview_panel.set_project_active(False)

    def _open_local_projection(self) -> None:
        if self._projection_window is None:
            self._projection_window = ProjectionWindow(self._presentation_dir)
            self._projection_window.destroyed.connect(
                lambda: setattr(self, "_projection_window", None)
            )
            # Also sync button state when closed externally
            self._projection_window.destroyed.connect(
                lambda: self.preview_panel.set_project_active(False)
            )

        self._projection_window.show()
        self._projection_window.raise_()
        self._projection_window.activateWindow()
        self.preview_panel.set_project_active(True)

    def closeEvent(self, event) -> None:
        """Handle application shutdown gracefully."""
        app = QApplication.instance()
        if app is not None and hasattr(self, "_global_arrow_nav_filter"):
            try:
                app.removeEventFilter(self._global_arrow_nav_filter)
            except Exception:
                pass
        # Stop OBS server threads so Python can exit completely
        if hasattr(self, "_obs") and self._obs:
            self._obs.stop()
        event.accept()
