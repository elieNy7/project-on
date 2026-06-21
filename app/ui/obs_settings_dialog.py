from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
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
from app.ui.theme import Colors, Radius
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
        font-size: 13px;
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
            f"font-size: 14px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;"
        )
        title_row.addWidget(title_label)

        if is_recommended:
            badge = QLabel(tr("recommended"))
            badge.setStyleSheet(f"""
                background: {Colors.ACCENT_SUCCESS};
                color: #000;
                font-size: 10px;
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
            f"font-size: 12px; color: {Colors.TEXT_MUTED}; background: transparent; border: none;"
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
            f"font-size: 13px; font-weight: 500; color: {Colors.TEXT_PRIMARY}; border: none;"
        )
        label_col.addWidget(lbl)

        if description:
            desc = QLabel(description)
            desc.setStyleSheet(
                f"font-size: 11px; color: {Colors.TEXT_MUTED}; border: none;"
            )
            label_col.addWidget(desc)

        layout.addLayout(label_col, 1)
        layout.addWidget(widget)


class ObsSettingsDialog(QDialog):
    def __init__(
        self,
        settings: ObsSettings,
        obs_controller: ObsController | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("obs"))
        self.setMinimumSize(550, 580)
        self.resize(580, 620)
        self.setStyleSheet(DIALOG_STYLE)

        self._settings = settings
        self._obs_controller = obs_controller

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
            f"font-size: 20px; font-weight: 700; color: {Colors.TEXT_PRIMARY};"
        )
        title_col.addWidget(title)
        subtitle = QLabel(tr("connectivity_desc"))
        subtitle.setStyleSheet(f"font-size: 13px; color: {Colors.TEXT_MUTED};")
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
            f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_MUTED}; text-transform: uppercase; letter-spacing: 1px;"
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
            f"font-size: 13px; color: {Colors.TEXT_SECONDARY};"
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
            f"font-size: 13px; font-weight: 500; color: {Colors.ACCENT_PRIMARY}; background: transparent;"
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
                font-size: 11px;
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
            f"font-size: 12px; color: {Colors.TEXT_SECONDARY}; background: transparent; border: none;"
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
                font-size: 13px;
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
                font-size: 13px;
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
        if (
            self._obs_controller is not None
            and self._obs_controller.is_web_server_running()
        ):
            running_url = self._obs_controller.get_web_server_url()
            if running_url:
                url = running_url
        self._web_url_label.setText(url)
        self._web_url_label.setToolTip(url)

    def _open_in_browser(self) -> None:
        if self._obs_controller:
            self._obs_controller.open_in_browser()

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

    def _update_server_status(self) -> None:
        """Update the server status display."""
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
        return ObsSettings(
            mode=self._current_mode,
            web_port=self._port_spin.value(),
            ndi_source_name=self._ndi_name_edit.text().strip() or tr("app_name"),
            output=self._settings.output,
        )

    @classmethod
    def edit(
        cls,
        settings: ObsSettings,
        obs_controller: ObsController | None = None,
        parent: QWidget | None = None,
    ) -> ObsSettings | None:
        dialog = cls(settings, obs_controller, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.get_settings()
        return None
