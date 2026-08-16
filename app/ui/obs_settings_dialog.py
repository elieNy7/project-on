from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
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


class SettingRow(QFrame):
    """A setting row with label and control."""

    def __init__(self, label: str, widget: QWidget, description: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 10)
        layout.setSpacing(16)

        label_col = QVBoxLayout()
        label_col.setSpacing(2)

        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"font-size: {Typography.SIZE_LABEL}px; font-weight: 500; color: {Colors.TEXT_PRIMARY}; border: none;"
        )
        label_col.addWidget(lbl)

        if description:
            desc = QLabel(description)
            desc.setStyleSheet(
                f"font-size: {Typography.SIZE_META}px; color: {Colors.TEXT_MUTED}; border: none;"
            )
            label_col.addWidget(desc)

        layout.addLayout(label_col, 1)
        layout.addWidget(widget)


class ObsSettingsDialog(QDialog):
    def __init__(
        self,
        settings: ObsSettings,
        obs_controller: ObsController | None = None,
        remote_client=None,
        parent: QWidget | None = None,
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
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QFrame()
        header.setStyleSheet("background: transparent;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(14)

        icon_frame = QFrame()
        icon_frame.setFixedSize(48, 48)
        icon_frame.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 12px;
            }}
        """)
        icon_layout = QVBoxLayout(icon_frame)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_label = QLabel()
        icon_label.setPixmap(app_icon("cast.svg").pixmap(24, 24))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("background: transparent;")
        icon_layout.addWidget(icon_label)
        header_layout.addWidget(icon_frame)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        title = QLabel(tr("obs"))
        title.setStyleSheet(
            f"font-size: {Typography.SIZE_DIALOG_TITLE}px; font-weight: 700; color: {Colors.TEXT_PRIMARY};"
        )
        title_col.addWidget(title)
        subtitle = QLabel(tr("connectivity_desc"))
        subtitle.setStyleSheet(f"font-size: {Typography.SIZE_CONTROL}px; color: {Colors.TEXT_MUTED};")
        title_col.addWidget(subtitle)
        header_layout.addLayout(title_col, 1)

        layout.addWidget(header)

        # ── Scrollable content ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        # Stylize scrollbar
        scroll.verticalScrollBar().setStyleSheet(f"""
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {Colors.BORDER_DEFAULT};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {Colors.ACCENT_PRIMARY};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 10, 0, 10)
        content_layout.setSpacing(16)

        scroll.setWidget(content_widget)
        layout.addWidget(scroll, 1)

        # Mode selection
        mode_label = QLabel(tr("connectivity"))
        mode_label.setStyleSheet(
            f"font-size: {Typography.SIZE_CONTROL}px; font-weight: 600; color: {Colors.TEXT_MUTED}; text-transform: uppercase; letter-spacing: 1px;"
        )
        content_layout.addWidget(mode_label)

        self._web_card = ModeCard(
            tr("web_server"),
            tr("web_server_desc"),
            "globe.svg",
            is_recommended=True,
        )
        self._ndi_card = ModeCard(
            "NDI",
            tr("ndi_desc"),
            "wifi.svg",
        )

        self._web_card.mousePressEvent = lambda e: self._select_mode("web")
        self._ndi_card.mousePressEvent = lambda e: self._select_mode("ndi")

        content_layout.addWidget(self._web_card)
        content_layout.addWidget(self._ndi_card)

        # Web Server Settings
        self._web_settings_frame = QFrame()
        self._web_settings_frame.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 12px;
            }}
        """)
        web_settings_layout = QVBoxLayout(self._web_settings_frame)
        web_settings_layout.setContentsMargins(0, 8, 0, 8)
        web_settings_layout.setSpacing(12)

        # Port setting
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1024, 65535)
        self._port_spin.setValue(settings.web_port)
        self._port_spin.setFixedWidth(100)
        web_settings_layout.addWidget(
            SettingRow(tr("port_label"), self._port_spin, tr("port_desc"))
        )

        # Server status and controls
        status_frame = QFrame()
        status_frame.setStyleSheet("background: transparent;")
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(0, 8, 0, 0)
        status_layout.setSpacing(12)

        self._status_indicator = QFrame()
        self._status_indicator.setFixedSize(10, 10)
        self._status_indicator.setStyleSheet(
            f"background: {Colors.ACCENT_DANGER}; border-radius: 5px;"
        )
        status_layout.addWidget(self._status_indicator)

        self._status_label = QLabel(tr("server_not_started"))
        self._status_label.setStyleSheet(
            f"font-size: {Typography.SIZE_BODY}px; color: {Colors.TEXT_SECONDARY};"
        )
        status_layout.addWidget(self._status_label, 1)

        web_settings_layout.addWidget(status_frame)

        # URL display
        url_frame = QFrame()
        url_frame.setStyleSheet(
            f"background: {Colors.BG_ELEVATED}; border-radius: 8px;"
        )
        url_layout = QHBoxLayout(url_frame)
        url_layout.setContentsMargins(12, 10, 12, 10)
        url_layout.setSpacing(12)

        url_icon = QLabel()
        url_icon.setPixmap(app_icon("link.svg").pixmap(16, 16))
        url_icon.setStyleSheet("background: transparent;")
        url_layout.addWidget(url_icon)

        self._web_url_label = QLabel()
        self._web_url_label.setStyleSheet(
            f"font-size: {Typography.SIZE_CONTROL}px; font-weight: 500; color: {Colors.ACCENT_PRIMARY}; background: transparent;"
        )
        url_layout.addWidget(self._web_url_label, 1)

        test_btn = QPushButton()
        test_btn.setIcon(app_icon("external-link.svg"))
        test_btn.setFixedSize(32, 32)
        test_btn.setToolTip(tr("open_browser"))
        test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.SURFACE_HOVER};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 6px;
            }}
            QPushButton:hover {{ background: {Colors.SURFACE_ACTIVE}; }}
        """)
        test_btn.clicked.connect(self._open_in_browser)
        url_layout.addWidget(test_btn)

        copy_btn = QPushButton(tr("copy_url"))
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {Colors.ACCENT_PRIMARY};
                border-radius: 6px;
                padding: 6px 12px;
                color: {Colors.ACCENT_PRIMARY};
                font-size: {Typography.SIZE_CONTROL}px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {Colors.ACCENT_PRIMARY};
                color: #000;
            }}
        """)
        copy_btn.clicked.connect(self._copy_url)
        url_layout.addWidget(copy_btn)

        web_settings_layout.addWidget(url_frame)

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
                self._url_mode_combo.addItem(
                    f"Scène : {scene.name}", f"scene:{scene.id}"
                )
        web_settings_layout.addWidget(
            SettingRow(
                "URL par scène OBS",
                self._url_mode_combo,
                "Créez plusieurs sources Navigateur avec des compositions ou styles différents.",
            )
        )

        obs_pro_tip = QLabel(
            "Réglage OBS recommandé : source Navigateur 1920 × 1080, 60 FPS, "
            "fond transparent. Dupliquez la source et affectez un mode à chaque scène."
        )
        obs_pro_tip.setWordWrap(True)
        obs_pro_tip.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                background: {Colors.BG_ELEVATED};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-left: 3px solid {Colors.ACCENT_PRIMARY};
                border-radius: 8px;
                padding: 10px 12px;
                font-size: {Typography.SIZE_CONTROL}px;
            }}
        """)
        web_settings_layout.addWidget(obs_pro_tip)

        self._web_settings_frame.setLayout(web_settings_layout)  # Ensure layout is set
        content_layout.addWidget(self._web_settings_frame)

        # NDI Settings
        self._ndi_settings_frame = QFrame()
        self._ndi_settings_frame.setStyleSheet(
            self._web_settings_frame.styleSheet()
        )  # Same style
        ndi_settings_layout = QVBoxLayout(self._ndi_settings_frame)
        ndi_settings_layout.setContentsMargins(16, 16, 16, 16)
        ndi_settings_layout.setSpacing(12)

        self._ndi_name_edit = QLineEdit()
        self._ndi_name_edit.setText(settings.ndi_source_name)
        self._ndi_name_edit.setPlaceholderText(tr("app_name"))
        self._ndi_name_edit.setFixedWidth(200)
        ndi_settings_layout.addWidget(
            SettingRow(
                tr("ndi_source_name"), self._ndi_name_edit, tr("ndi_source_desc")
            )
        )

        self._ndi_status_frame = QFrame()
        self._ndi_status_frame.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_ELEVATED};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 8px;
            }}
        """)
        ndi_status_layout = QHBoxLayout(self._ndi_status_frame)
        ndi_status_layout.setContentsMargins(12, 10, 12, 10)
        ndi_status_layout.setSpacing(10)

        self._ndi_status_indicator = QFrame()
        self._ndi_status_indicator.setFixedSize(10, 10)
        ndi_status_layout.addWidget(self._ndi_status_indicator)

        self._ndi_status_label = QLabel()
        self._ndi_status_label.setWordWrap(True)
        self._ndi_status_label.setStyleSheet(
            f"font-size: {Typography.SIZE_CONTROL}px; color: {Colors.TEXT_SECONDARY}; background: transparent; border: none;"
        )
        ndi_status_layout.addWidget(self._ndi_status_label, 1)

        refresh_ndi_btn = QPushButton()
        refresh_ndi_btn.setIcon(app_icon("refresh-cw.svg"))
        refresh_ndi_btn.setFixedSize(32, 32)
        refresh_ndi_btn.setToolTip("Reverifier NDI")
        refresh_ndi_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_ndi_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.SURFACE_HOVER};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 6px;
            }}
            QPushButton:hover {{ background: {Colors.SURFACE_ACTIVE}; }}
        """)
        refresh_ndi_btn.clicked.connect(self._refresh_ndi_status)
        ndi_status_layout.addWidget(refresh_ndi_btn)

        ndi_settings_layout.addWidget(self._ndi_status_frame)
        content_layout.addWidget(self._ndi_settings_frame)

        # Remote control of OBS via obs-websocket
        self._create_remote_section(content_layout)

        content_layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton(tr("cancel"))
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.SURFACE_HOVER};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 8px;
                padding: 10px 24px;
                color: {Colors.TEXT_SECONDARY};
                font-size: {Typography.SIZE_CONTROL}px;
            }}
            QPushButton:hover {{
                background: {Colors.SURFACE_ACTIVE};
            }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton(tr("save"))
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ACCENT_PRIMARY};
                border: 1px solid {Colors.ACCENT_PRIMARY};
                border-radius: 8px;
                padding: 10px 24px;
                color: white;
                font-size: {Typography.SIZE_CONTROL}px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {Colors.ACCENT_SECONDARY};
            }}
        """)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)

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

        if usable:
            color = Colors.ACCENT_SUCCESS
            label = "NDI detecte automatiquement et pret a diffuser."
        elif runtime_found:
            color = Colors.ACCENT_WARNING
            missing = []
            if not bridge_found:
                missing.append("NDIlib")
            if not numpy_found:
                missing.append("numpy")
            suffix = f" Dependance manquante: {', '.join(missing)}." if missing else ""
            label = f"Runtime NDI detecte, mais la sortie n'est pas encore prete.{suffix}"
        else:
            color = Colors.ACCENT_DANGER
            label = "NDI non detecte. Installez le NDI Runtime ou ajoutez le dossier runtime portable."

        detail = str(status.get("message") or label)
        if paths:
            detail += "\n" + "\n".join(str(p) for p in paths[:4])

        self._ndi_status_indicator.setStyleSheet(
            f"background: {color}; border-radius: 5px;"
        )
        self._ndi_status_label.setText(label)
        self._ndi_status_label.setToolTip(detail)

    # ── Remote OBS control (obs-websocket 5.x) ─────────────────────────

    def _create_remote_section(self, content_layout: QVBoxLayout) -> None:
        remote = getattr(self._settings, "remote", None)

        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 10px;
            }}
        """)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        title = QLabel("Contrôle OBS (WebSocket)")
        title.setStyleSheet(
            f"font-size: {Typography.SIZE_SECTION}px; font-weight: 600;"
            f" color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;"
        )
        lay.addWidget(title)

        self._remote_enabled = QCheckBox("Piloter OBS depuis Project-On")
        self._remote_enabled.setChecked(bool(remote and remote.enabled))
        self._remote_enabled.setStyleSheet(
            f"font-size: {Typography.SIZE_CONTROL}px; color: {Colors.TEXT_SECONDARY};"
            " background: transparent; border: none;"
        )
        lay.addWidget(self._remote_enabled)

        endpoint_row = QHBoxLayout()
        endpoint_row.setSpacing(10)
        host_label = QLabel("Hôte")
        host_label.setStyleSheet("background: transparent; border: none;")
        endpoint_row.addWidget(host_label)
        self._remote_host = QLineEdit(getattr(remote, "host", "127.0.0.1"))
        self._remote_host.setFixedWidth(120)
        endpoint_row.addWidget(self._remote_host)
        port_label = QLabel("Port")
        port_label.setStyleSheet("background: transparent; border: none;")
        endpoint_row.addWidget(port_label)
        self._remote_port = QSpinBox()
        self._remote_port.setRange(1024, 65535)
        self._remote_port.setValue(getattr(remote, "port", 4455))
        endpoint_row.addWidget(self._remote_port)
        pwd_label = QLabel("Mot de passe")
        pwd_label.setStyleSheet("background: transparent; border: none;")
        endpoint_row.addWidget(pwd_label)
        self._remote_password = QLineEdit(getattr(remote, "password", ""))
        self._remote_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._remote_password.setPlaceholderText("si défini dans OBS")
        endpoint_row.addWidget(self._remote_password, 1)
        lay.addLayout(endpoint_row)

        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self._remote_status_dot = QFrame()
        self._remote_status_dot.setFixedSize(10, 10)
        self._remote_status_dot.setStyleSheet(
            f"background: {Colors.ACCENT_DANGER}; border-radius: 5px;"
        )
        status_row.addWidget(self._remote_status_dot)
        self._remote_status_label = QLabel("Déconnecté")
        self._remote_status_label.setStyleSheet(
            f"font-size: {Typography.SIZE_CONTROL}px; color: {Colors.TEXT_SECONDARY};"
            " background: transparent; border: none;"
        )
        status_row.addWidget(self._remote_status_label, 1)

        self._remote_connect_btn = QPushButton("Connecter")
        self._remote_connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remote_connect_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ACCENT_PRIMARY};
                border: 1px solid {Colors.ACCENT_PRIMARY};
                border-radius: 6px;
                padding: 6px 14px;
                color: {Colors.PROJECT_BUTTON_TEXT};
                font-size: {Typography.SIZE_CONTROL}px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {Colors.ACCENT_SECONDARY}; }}
        """)
        self._remote_connect_btn.clicked.connect(self._connect_remote)
        status_row.addWidget(self._remote_connect_btn)

        load_scenes_btn = QPushButton("Charger les scènes OBS")
        load_scenes_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        load_scenes_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 6px;
                padding: 6px 14px;
                color: {Colors.TEXT_SECONDARY};
                font-size: {Typography.SIZE_CONTROL}px;
            }}
            QPushButton:hover {{
                border-color: {Colors.ACCENT_PRIMARY};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        load_scenes_btn.clicked.connect(self._load_obs_scenes)
        status_row.addWidget(load_scenes_btn)
        lay.addLayout(status_row)

        self._remote_live_combo = QComboBox()
        self._remote_live_combo.setEditable(True)
        self._remote_live_combo.setCurrentText(
            getattr(remote, "scene_on_live", "") or ""
        )
        lay.addWidget(
            SettingRow(
                "Scène OBS quand on projette",
                self._remote_live_combo,
                "Bascule OBS sur cette scène dès qu'une slide passe en direct.",
            )
        )

        self._remote_hide_combo = QComboBox()
        self._remote_hide_combo.setEditable(True)
        self._remote_hide_combo.setCurrentText(
            getattr(remote, "scene_on_hide", "") or ""
        )
        lay.addWidget(
            SettingRow(
                "Scène OBS quand on masque",
                self._remote_hide_combo,
                "Ex. une scène caméra seul ou un écran d'accueil.",
            )
        )

        source_row = QHBoxLayout()
        source_row.setSpacing(10)
        self._remote_target_scene = QComboBox()
        self._remote_target_scene.setEditable(True)
        source_row.addWidget(self._remote_target_scene, 1)
        create_source_btn = QPushButton("Créer la source Project-On")
        create_source_btn.setToolTip(
            "Ajoute une source Navigateur pointant vers la diffusion Project-On"
            " dans la scène choisie (1920 × 1080)."
        )
        create_source_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_source_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 6px;
                padding: 6px 14px;
                color: {Colors.TEXT_SECONDARY};
                font-size: {Typography.SIZE_CONTROL}px;
            }}
            QPushButton:hover {{
                border-color: {Colors.ACCENT_PRIMARY};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        create_source_btn.clicked.connect(self._create_remote_source)
        source_row.addWidget(create_source_btn)
        lay.addLayout(source_row)

        content_layout.addWidget(frame)

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

    @classmethod
    def edit(
        cls,
        settings: ObsSettings,
        obs_controller: ObsController | None = None,
        remote_client=None,
        parent: QWidget | None = None,
    ) -> ObsSettings | None:
        dialog = cls(settings, obs_controller, remote_client, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.get_settings()
        return None
