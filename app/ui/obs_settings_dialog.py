from __future__ import annotations

from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.ui.icons import app_icon
from app.ui.setting_cards import PageHeader, SettingRow, SettingSection, fit_combos
from app.ui.theme import Colors, Radius, Typography
from app.utils.obs_controller import ObsController
from app.utils.settings import ObsSettings
from app.utils.translations import tr

# Modern styles
DIALOG_STYLE = f"""
    QDialog {{
        background: {Colors.BG_SECONDARY};
    }}
    QLabel {{
        color: {Colors.TEXT_PRIMARY};
    }}
    QSpinBox, QLineEdit {{
        background: {Colors.BG_PRIMARY};
        border: 1px solid {Colors.BORDER_DEFAULT};
        border-radius: {Radius.MD}px;
        padding: 10px 14px;
        color: {Colors.TEXT_PRIMARY};
        font-size: {Typography.SIZE_FILTER}px;
    }}
    QSpinBox:hover, QLineEdit:hover {{
        border: 1px solid {Colors.BORDER_FOCUS};
    }}
"""


class ModeCard(QFrame):
    """A selectable mode card."""

    def __init__(
        self,
        title: str,
        description: str,
        icon_name: str,
        is_recommended: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        # Icon
        icon_frame = QFrame()
        icon_frame.setFixedSize(44, 44)
        icon_frame.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 10px;
            }}
        """)
        icon_layout = QVBoxLayout(icon_frame)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_label = QLabel()
        icon_label.setPixmap(app_icon(icon_name).pixmap(22, 22))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("background: transparent; border: none;")
        icon_layout.addWidget(icon_label)
        layout.addWidget(icon_frame)

        # Text
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"font-size: {Typography.SIZE_SECTION}px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;"
        )
        title_row.addWidget(title_label)

        if is_recommended:
            badge = QLabel(tr("recommended"))
            badge.setStyleSheet(f"""
                background: {Colors.ACCENT_SUCCESS};
                color: #000;
                font-size: {Typography.SIZE_NUMBER}px;
                font-weight: 700;
                padding: 3px 8px;
                border-radius: 4px;
                border: none;
            """)
            title_row.addWidget(badge)

        title_row.addStretch()
        text_layout.addLayout(title_row)

        desc_label = QLabel(description)
        desc_label.setStyleSheet(
            f"font-size: {Typography.SIZE_CONTROL}px; color: {Colors.TEXT_MUTED}; background: transparent; border: none;"
        )
        desc_label.setWordWrap(True)
        text_layout.addWidget(desc_label)

        layout.addLayout(text_layout, 1)

        # Selection indicator
        self._check = QLabel()
        self._check.setFixedSize(24, 24)
        self._check.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self._check)

    def _update_style(self) -> None:
        if self._selected:
            self.setStyleSheet(f"""
                ModeCard {{
                    background: {Colors.SURFACE_ACTIVE};
                    border: 1px solid {Colors.ACCENT_PRIMARY};
                    border-radius: 12px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                ModeCard {{
                    background: {Colors.BG_PRIMARY};
                    border: 1px solid {Colors.BORDER_DEFAULT};
                    border-radius: 12px;
                }}
                ModeCard:hover {{
                    background: {Colors.SURFACE_HOVER};
                    border-color: {Colors.BORDER_FOCUS};
                }}
            """)

    def setSelected(self, selected: bool) -> None:
        self._selected = selected
        self._update_style()
        if selected:
            self._check.setPixmap(app_icon("check-circle.svg").pixmap(20, 20))
        else:
            self._check.clear()

    def isSelected(self) -> bool:
        return self._selected

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setSelected(True)
        super().mousePressEvent(event)


def _status_dot() -> QFrame:
    dot = QFrame()
    dot.setFixedSize(10, 10)
    dot.setStyleSheet(f"background: {Colors.TEXT_DISABLED}; border-radius: 5px;")
    return dot


def _row_of(*widgets: QWidget) -> QWidget:
    """Several controls side by side on the right of a setting card."""
    box = QWidget()
    box.setStyleSheet("QWidget#ControlGroup { background: transparent; }")
    box.setObjectName("ControlGroup")
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    for w in widgets:
        row.addWidget(w, 0, Qt.AlignmentFlag.AlignVCenter)
    return box


class ObsSettingsDialog(QDialog):
    settingsChanged = Signal()  # output mode picked (fields are watched by the page)

    def __init__(
        self,
        settings: ObsSettings,
        obs_controller: ObsController | None = None,
        remote_client=None,
        parent: QWidget | None = None,
        embedded: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("obs"))
        self.setMinimumSize(550, 580)
        self.resize(580, 700)
        self.setStyleSheet(DIALOG_STYLE)

        self._settings = settings
        self._obs_controller = obs_controller
        self._remote_client = remote_client

        layout = QVBoxLayout(self)
        layout.setSpacing(0)

        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(16)
        content_layout.addWidget(
            PageHeader(
                "Connectivité OBS & NDI",
                "Comment le texte arrive dans OBS : page Web locale ou flux NDI, "
                "et pilotage d'OBS depuis Project-On.",
            )
        )
        if embedded:
            # Inside the settings page, which scrolls as a whole.
            layout.setContentsMargins(16, 16, 16, 16)
            layout.addWidget(content_widget)
        else:
            layout.setContentsMargins(24, 20, 24, 16)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setStyleSheet("background: transparent; border: none;")
            scroll.setWidget(content_widget)
            layout.addWidget(scroll, 1)

        # ── Mode de sortie ──
        mode_section = SettingSection("Mode de sortie", "cast.svg")
        self._web_card = ModeCard(
            tr("web_server"), tr("web_server_desc"), "globe.svg", is_recommended=True
        )
        self._ndi_card = ModeCard("NDI", tr("ndi_desc"), "wifi.svg")
        self._web_card.mousePressEvent = lambda e: self._select_mode("web")
        self._ndi_card.mousePressEvent = lambda e: self._select_mode("ndi")
        mode_section.addWidget(self._web_card)
        mode_section.addWidget(self._ndi_card)
        content_layout.addWidget(mode_section)

        # ── Serveur Web ──
        self._web_settings_frame = SettingSection("Serveur Web", "globe.svg")
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1024, 65535)
        self._port_spin.setValue(settings.web_port)
        self._port_spin.setFixedWidth(110)
        self._web_settings_frame.addRow(tr("port_label"), self._port_spin, tr("port_desc"))

        self._status_indicator = _status_dot()
        server_row = SettingRow("État du serveur", self._status_indicator, tr("server_not_started"))
        self._status_label = server_row.description_label
        self._web_settings_frame.addWidget(server_row)

        test_btn = QPushButton()
        test_btn.setIcon(app_icon("external-link.svg", Colors.TEXT_PRIMARY))
        test_btn.setToolTip(tr("open_browser"))
        test_btn.clicked.connect(self._open_in_browser)
        copy_btn = QPushButton(tr("copy_url"))
        copy_btn.setIcon(app_icon("copy.svg", Colors.TEXT_PRIMARY))
        copy_btn.clicked.connect(self._copy_url)
        url_row = SettingRow("Adresse à coller dans OBS", _row_of(test_btn, copy_btn), "…")
        self._web_url_label = url_row.description_label
        self._web_url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._web_url_label.setStyleSheet(
            f"font-size: {Typography.SIZE_FILTER}px; color: {Colors.ACCENT_PRIMARY};"
            " border: none; background: transparent;"
        )
        self._web_settings_frame.addWidget(url_row)

        self._url_mode_combo = QComboBox()
        for label, data in (
            ("Mode configuré", ""),
            ("Lower Third", "lower_third"),
            ("Plein écran", "fullscreen"),
            ("Panneau latéral", "side_panel"),
            ("Sous-titre", "subtitle"),
            ("Carte focus", "focus_card"),
        ):
            self._url_mode_combo.addItem(label, data)
        for scene in getattr(settings, "scenes", []) or []:
            if scene.id:
                self._url_mode_combo.addItem(f"Scène : {scene.name}", f"scene:{scene.id}")
        self._web_settings_frame.addRow(
            "URL par scène OBS",
            self._url_mode_combo,
            "Plusieurs sources Navigateur, chacune avec sa composition ou son style.",
        )
        obs_pro_tip = QLabel(
            "Réglage OBS recommandé : source Navigateur 1920 × 1080, 60 FPS, "
            "fond transparent. Dupliquez la source et affectez un mode à chaque scène."
        )
        obs_pro_tip.setWordWrap(True)
        obs_pro_tip.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                background: {Colors.ACCENT_SECONDARY_GLOW};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.SM}px;
                padding: 10px 12px;
                font-size: {Typography.SIZE_FILTER}px;
            }}
        """)
        self._web_settings_frame.addWidget(obs_pro_tip)
        content_layout.addWidget(self._web_settings_frame)

        # ── NDI ──
        self._ndi_settings_frame = SettingSection("NDI", "wifi.svg")
        self._ndi_name_edit = QLineEdit()
        self._ndi_name_edit.setText(settings.ndi_source_name)
        self._ndi_name_edit.setPlaceholderText(tr("app_name"))
        self._ndi_name_edit.setFixedWidth(180)
        self._ndi_settings_frame.addRow(
            tr("ndi_source_name"), self._ndi_name_edit, tr("ndi_source_desc")
        )
        self._ndi_status_indicator = _status_dot()
        self._ndi_test_btn = QPushButton("Tester")
        self._ndi_test_btn.setToolTip(
            "Démarre l'envoi NDI avec les réglages enregistrés ; recliquez pour arrêter."
        )
        self._ndi_test_btn.clicked.connect(self._toggle_ndi_test)
        refresh_ndi_btn = QPushButton()
        refresh_ndi_btn.setIcon(app_icon("refresh-cw.svg", Colors.TEXT_PRIMARY))
        refresh_ndi_btn.setToolTip("Revérifier NDI")
        refresh_ndi_btn.clicked.connect(self._refresh_ndi_status)
        ndi_row = SettingRow(
            "État NDI",
            _row_of(self._ndi_status_indicator, self._ndi_test_btn, refresh_ndi_btn),
            "…",
        )
        self._ndi_status_label = ndi_row.description_label
        self._ndi_settings_frame.addWidget(ndi_row)
        content_layout.addWidget(self._ndi_settings_frame)

        # ── Contrôle OBS (WebSocket) ──
        self._create_remote_section(content_layout)
        content_layout.addStretch()
        fit_combos(content_widget)

        # Standalone dialog only: the settings page applies at once.
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton(tr("cancel"))
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        ok_btn = QPushButton(tr("save"))
        ok_btn.setObjectName("AccentButton")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        if embedded:
            cancel_btn.hide()
            ok_btn.hide()
        layout.addLayout(btn_layout)

        # Set initial state
        self._current_mode = settings.mode if settings.mode in ("web", "ndi") else "web"
        self._select_mode(self._current_mode)
        self._update_url()
        self._update_server_status()
        self._refresh_ndi_status()

        self._port_spin.valueChanged.connect(self._update_url)
        self._url_mode_combo.currentIndexChanged.connect(self._update_url)

        # Status update timer
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_server_status)
        self._status_timer.start(1000)

    def _stop_status_timer(self) -> None:
        """Arrête le polling d'état (appelé à la fermeture du dialogue)."""
        timer = getattr(self, "_status_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()

    def closeEvent(self, event) -> None:
        self._stop_status_timer()
        super().closeEvent(event)

    def reject(self) -> None:
        self._stop_status_timer()
        super().reject()

    def accept(self) -> None:
        self._stop_status_timer()
        super().accept()

    def _copy_url(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._web_url_label.text())

    def _update_url(self) -> None:
        port = int(self._port_spin.value())
        url = f"http://localhost:{port}/obs"
        data = str(self._url_mode_combo.currentData() or "")
        if data.startswith("scene:"):
            scene_id = data.split(":", 1)[1]
            url = f"{url}?scene={scene_id}"
            if (
                self._obs_controller is not None
                and self._obs_controller.is_web_server_running()
            ):
                running_url = self._obs_controller.get_scene_urls().get(scene_id)
                if running_url:
                    url = running_url
        else:
            layout_mode = data
            if (
                self._obs_controller is not None
                and self._obs_controller.is_web_server_running()
            ):
                running_url = self._obs_controller.get_web_server_url(
                    layout_mode or None
                )
                if running_url:
                    url = running_url
            elif layout_mode:
                url = f"{url}?layout={layout_mode}"
        self._web_url_label.setText(url)
        self._web_url_label.setToolTip(url)

    def _open_in_browser(self) -> None:
        if not self._obs_controller:
            return
        data = str(self._url_mode_combo.currentData() or "")
        if data.startswith("scene:"):
            self._obs_controller.open_scene_in_browser(data.split(":", 1)[1])
            return
        self._obs_controller.open_in_browser(data or None)

    def _select_mode(self, mode: str) -> None:
        self._current_mode = mode
        self._web_card.setSelected(mode == "web")
        self._ndi_card.setSelected(mode == "ndi")
        self.settingsChanged.emit()

        # Show/hide relevant settings
        self._web_settings_frame.setVisible(mode == "web")
        self._ndi_settings_frame.setVisible(mode == "ndi")
        if mode == "ndi":
            self._refresh_ndi_status()

    def _refresh_ndi_status(self, *args) -> None:
        if self._obs_controller is None:
            status = {
                "usable": False,
                "runtime_found": False,
                "python_bridge_found": False,
                "numpy_found": False,
                "runtime_paths": [],
                "message": tr("ndi_unavailable"),
            }
        else:
            status = self._obs_controller.get_ndi_availability()

        usable = bool(status.get("usable"))
        runtime_found = bool(status.get("runtime_found"))
        bridge_found = bool(status.get("python_bridge_found"))
        numpy_found = bool(status.get("numpy_found"))
        paths = status.get("runtime_paths") or []
        running = (
            self._obs_controller is not None
            and self._obs_controller.is_ndi_running()
        )

        if running:
            color = Colors.ACCENT_SUCCESS
            source = self._obs_controller.settings.ndi_source_name
            label = f"En direct sur le réseau NDI : source « {source} »."
            self._ndi_test_btn.setText("Arrêter")
        else:
            self._ndi_test_btn.setText("Tester")
            if usable:
                color = Colors.ACCENT_WARNING
                label = "NDI prêt. Cliquez sur Tester (ou Enregistrer) pour diffuser."
            elif runtime_found:
                color = Colors.ACCENT_WARNING
                missing = []
                if not bridge_found:
                    missing.append("NDIlib")
                if not numpy_found:
                    missing.append("numpy")
                suffix = (
                    f" Dépendance manquante : {', '.join(missing)}." if missing else ""
                )
                label = f"Runtime NDI détecté, mais la sortie n'est pas prête.{suffix}"
            else:
                color = Colors.ACCENT_DANGER
                label = (
                    "NDI non détecté. Installez le NDI Runtime (ndi.video) "
                    "puis cliquez sur ⟳."
                )

        detail = str(status.get("message") or label)
        if paths:
            detail += "\n" + "\n".join(str(p) for p in paths[:4])

        self._ndi_status_indicator.setStyleSheet(
            f"background: {color}; border-radius: 5px;"
        )
        self._ndi_status_label.setText(label)
        self._ndi_status_label.setToolTip(detail)

    def _toggle_ndi_test(self) -> None:
        """Démarre/arrête un envoi NDI réel sans quitter le dialogue."""
        if self._obs_controller is None:
            return
        if self._obs_controller.is_ndi_running():
            self._obs_controller.stop_ndi()
        else:
            if not self._obs_controller.start_ndi():
                self._refresh_ndi_status()
                self._ndi_status_label.setText(
                    "Démarrage NDI impossible — vérifiez le NDI Runtime."
                )
        self._refresh_ndi_status()

    # ── Remote OBS control (obs-websocket 5.x) ─────────────────────────

    def _create_remote_section(self, content_layout: QVBoxLayout) -> None:
        remote = getattr(self._settings, "remote", None)
        section = SettingSection("Contrôle OBS (WebSocket)", "zap.svg")

        self._remote_enabled = QCheckBox("Piloter OBS depuis Project-On")
        self._remote_enabled.setToolTip(
            "Change de scène OBS quand on projette ou masque (obs-websocket 5)."
        )
        self._remote_enabled.setChecked(bool(remote and remote.enabled))
        section.addWidget(self._remote_enabled)

        self._remote_host = QLineEdit(getattr(remote, "host", "127.0.0.1"))
        self._remote_host.setFixedWidth(180)
        section.addRow("Hôte", self._remote_host, "Adresse de l'ordinateur qui fait tourner OBS")
        self._remote_port = QSpinBox()
        self._remote_port.setRange(1024, 65535)
        self._remote_port.setValue(getattr(remote, "port", 4455))
        self._remote_port.setFixedWidth(110)
        section.addRow("Port", self._remote_port, "4455 par défaut dans OBS")
        self._remote_password = QLineEdit(getattr(remote, "password", ""))
        self._remote_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._remote_password.setPlaceholderText("si défini dans OBS")
        self._remote_password.setFixedWidth(180)
        section.addRow("Mot de passe", self._remote_password)

        self._remote_status_dot = _status_dot()
        self._remote_connect_btn = QPushButton("Connecter")
        self._remote_connect_btn.setObjectName("AccentButton")
        self._remote_connect_btn.clicked.connect(self._connect_remote)
        load_scenes_btn = QPushButton("Charger les scènes")
        load_scenes_btn.clicked.connect(self._load_obs_scenes)
        status_row = SettingRow(
            "Connexion",
            _row_of(self._remote_status_dot, self._remote_connect_btn),
            "Déconnecté",
        )
        self._remote_status_label = status_row.description_label
        section.addWidget(status_row)
        section.addRow(
            "Scènes OBS",
            load_scenes_btn,
            "Remplit les listes ci-dessous avec les scènes d'OBS.",
        )

        self._remote_live_combo = QComboBox()
        self._remote_live_combo.setEditable(True)
        self._remote_live_combo.setCurrentText(getattr(remote, "scene_on_live", "") or "")
        section.addRow(
            "Scène quand on projette",
            self._remote_live_combo,
            "OBS bascule sur cette scène dès qu'une slide passe en direct.",
        )
        self._remote_hide_combo = QComboBox()
        self._remote_hide_combo.setEditable(True)
        self._remote_hide_combo.setCurrentText(getattr(remote, "scene_on_hide", "") or "")
        section.addRow(
            "Scène quand on masque",
            self._remote_hide_combo,
            "Par exemple une scène caméra seule ou un écran d'accueil.",
        )

        self._remote_target_scene = QComboBox()
        self._remote_target_scene.setEditable(True)
        create_source_btn = QPushButton("Créer la source")
        create_source_btn.setToolTip(
            "Ajoute une source Navigateur pointant vers la diffusion Project-On"
            " dans la scène choisie (1920 × 1080)."
        )
        create_source_btn.clicked.connect(self._create_remote_source)
        section.addRow(
            "Scène de la source Project-On",
            self._remote_target_scene,
            "Scène OBS qui recevra la source Navigateur.",
        )
        section.addRow(
            "Source Navigateur",
            create_source_btn,
            "Crée en un clic la source Project-On (1920 × 1080) dans la scène choisie.",
        )
        content_layout.addWidget(section)

        self._remote_enabled.toggled.connect(self._update_remote_controls)
        self._update_remote_controls()
        self._update_remote_status()

        if self._remote_client is not None:
            self._remote_client.scenesLoaded.connect(self._on_scenes_loaded)
            self._remote_client.connected.connect(self._update_remote_status)
            self._remote_client.disconnected.connect(self._update_remote_status)
            self._remote_client.errorOccurred.connect(self._on_remote_error)

    def _update_remote_controls(self, *_args) -> None:
        enabled = self._remote_enabled.isChecked()
        for w in (
            self._remote_host,
            self._remote_port,
            self._remote_password,
            self._remote_connect_btn,
            self._remote_live_combo,
            self._remote_hide_combo,
            self._remote_target_scene,
        ):
            w.setEnabled(enabled)

    def _remote_from_widgets(self, enabled: bool | None = None):
        from app.utils.settings import ObsRemoteSettings

        return ObsRemoteSettings(
            enabled=self._remote_enabled.isChecked()
            if enabled is None
            else enabled,
            host=self._remote_host.text().strip() or "127.0.0.1",
            port=self._remote_port.value(),
            password=self._remote_password.text(),
            scene_on_live=self._remote_live_combo.currentText().strip(),
            scene_on_hide=self._remote_hide_combo.currentText().strip(),
        )

    def _connect_remote(self) -> None:
        if self._remote_client is None:
            return
        if self._remote_client.is_connected():
            self._remote_client.disconnect_from_obs()
            self._update_remote_status()
            return
        self._remote_client.apply_settings(
            self._remote_from_widgets(enabled=True)
        )
        self._remote_client.connect_to_obs()
        self._remote_status_label.setText("Connexion…")
        self._remote_status_dot.setStyleSheet(
            f"background: {Colors.ACCENT_WARNING}; border-radius: 5px;"
        )

    def _load_obs_scenes(self) -> None:
        if self._remote_client is None:
            return
        if not self._remote_client.is_connected():
            self._remote_status_label.setText(
                "Connectez-vous d'abord pour charger les scènes."
            )
            return
        self._remote_client.get_scenes()

    def _on_scenes_loaded(self, scene_names: list) -> None:
        for combo in (
            self._remote_live_combo,
            self._remote_hide_combo,
            self._remote_target_scene,
        ):
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("")
            combo.addItems([str(n) for n in scene_names])
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.setCurrentText(current)
            combo.blockSignals(False)
        self._remote_status_label.setText(
            f"{len(scene_names)} scènes OBS chargées."
        )

    def _on_remote_error(self, message: str) -> None:
        self._remote_status_label.setText(f"Erreur : {message}")

    def _create_remote_source(self) -> None:
        if self._remote_client is None:
            return
        scene = self._remote_target_scene.currentText().strip()
        if not scene:
            self._remote_status_label.setText(
                "Choisissez la scène OBS cible d'abord."
            )
            return
        if not self._remote_client.is_connected():
            self._remote_status_label.setText(
                "Connectez-vous d'abord pour créer la source."
            )
            return
        if self._obs_controller is not None:
            url = self._obs_controller.get_web_server_url()
        else:
            url = f"http://localhost:{self._settings.web_port}/obs"
        self._remote_client.create_browser_source(scene, url)
        self._remote_status_label.setText(
            f"Source Project-On ajoutée à « {scene} »."
        )

    def _update_remote_status(self, *_args) -> None:
        if self._remote_client is None:
            return
        if self._remote_client.is_connected():
            self._remote_status_dot.setStyleSheet(
                f"background: {Colors.ACCENT_SUCCESS}; border-radius: 5px;"
            )
            self._remote_status_label.setText("OBS connecté (WebSocket)")
            self._remote_connect_btn.setText("Déconnecter")
        else:
            self._remote_status_dot.setStyleSheet(
                f"background: {Colors.ACCENT_DANGER}; border-radius: 5px;"
            )
            self._remote_status_label.setText("Déconnecté")
            self._remote_connect_btn.setText("Connecter")

    def _update_server_status(self) -> None:
        """Update the server status display."""
        self._update_remote_status()
        if self._obs_controller is None:
            return

        # Volet NDI visible : l'état (détection + envoi en cours) suit en direct.
        if self._current_mode == "ndi":
            self._refresh_ndi_status()

        running = self._obs_controller.is_web_server_running()

        if running:
            self._status_indicator.setStyleSheet(
                f"background: {Colors.ACCENT_SUCCESS}; border-radius: 5px;"
            )
            self._status_label.setText(tr("obs_server_started"))
        else:
            self._status_indicator.setStyleSheet(
                f"background: {Colors.ACCENT_DANGER}; border-radius: 5px;"
            )
            self._status_label.setText(tr("server_not_started"))

    def get_settings(self) -> ObsSettings:
        try:
            remote = self._remote_from_widgets()
        except Exception:
            remote = getattr(self._settings, "remote", None)
        return ObsSettings(
            mode=self._current_mode,
            web_port=self._port_spin.value(),
            ndi_source_name=self._ndi_name_edit.text().strip() or tr("app_name"),
            output=self._settings.output,
            scenes=self._settings.scenes,
            remote=remote,
        )
