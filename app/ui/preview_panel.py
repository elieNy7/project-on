from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSignalBlocker, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from app.ui.icons import app_icon
from app.ui.theme import Colors, get_theme
from app.utils.translations import tr


# ═══════════════════════════════════════════════════════════════════
#  Navigation arrow (circle button)
# ═══════════════════════════════════════════════════════════════════
class _NavArrowButton(QPushButton):
    def __init__(self, icon_name: str, tooltip: str, parent=None) -> None:
        super().__init__(parent)
        self.setIcon(app_icon(icon_name, Colors.TEXT_PRIMARY))
        self.setIconSize(QSize(18, 18))
        self.setToolTip(tooltip)
        self.setFixedSize(40, 40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_TERTIARY};
                border: none;
                border-radius: 20px;
                color: {Colors.TEXT_PRIMARY};
            }}
            QPushButton:hover {{
                background: {Colors.ACCENT_GLOW};
                color: {Colors.ACCENT_LIGHT};
            }}
            QPushButton:pressed {{
                background: rgba(216,170,90,0.22);
            }}
        """)


# ═══════════════════════════════════════════════════════════════════
#  Pill control button
# ═══════════════════════════════════════════════════════════════════
class PreviewControlButton(QPushButton):
    """Premium action button used in the presenter preview toolbar."""

    def __init__(
        self, icon_name: str, tooltip: str, parent=None, text: str = ""
    ) -> None:
        super().__init__(text, parent)
        self._icon_name = icon_name
        self.setIcon(app_icon(icon_name, Colors.TEXT_PRIMARY))
        self.setIconSize(QSize(16, 16))
        self.setToolTip(tooltip)
        if text:
            self.setMinimumWidth(132)
            self.setFixedHeight(40)
            padding = "padding: 0 16px;"
        else:
            self.setFixedSize(40, 40)
            padding = ""

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._padding = padding
        self.setStyleSheet(self._build_style())

    def _build_style(
        self,
        *,
        checked_bg: str = "rgba(216,170,90,0.18)",
        checked_border: str = "rgba(216,170,90,0.42)",
        checked_text: str = Colors.ACCENT_LIGHT,
    ) -> str:
        return f"""
            QPushButton {{
                background: {Colors.BG_TERTIARY};
                border: none;
                border-radius: 20px;
                color: {Colors.TEXT_PRIMARY};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0;
                text-transform: uppercase;
                {self._padding}
            }}
            QPushButton:hover {{
                background: {Colors.SURFACE_HOVER};
                color: {Colors.TEXT_PRIMARY};
            }}
            QPushButton:pressed {{
                background: {Colors.SURFACE_ACTIVE};
            }}
            QPushButton:checked {{
                background: {checked_bg};
                border: none;
                color: {checked_text};
            }}
        """


# ═══════════════════════════════════════════════════════════════════
#  Preview Panel
# ═══════════════════════════════════════════════════════════════════
class PreviewPanel(QFrame):
    hideToggled = pyqtSignal(bool)
    prevRequested = pyqtSignal()
    nextRequested = pyqtSignal()
    logoRequested = pyqtSignal()
    projectToggled = pyqtSignal(bool)

    def __init__(self, parent=None, settings=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setObjectName("PreviewPanel")
        self._is_hidden = False
        self._has_content = False
        self._current_row = -1
        self._total_slides = 0
        self._current_reference = ""
        self._current_image_path = ""
        self._project_active = False
        self._is_light_theme = get_theme() == "light"
        if self._is_light_theme:
            self._stage_text_rgb = (23, 32, 51)
            self._stage_ref_rgb = (183, 121, 31)
            self._stage_empty_color = "rgba(100, 116, 139, 0.38)"
            self._stage_meta_color = "rgba(71, 85, 105, 0.62)"
            self._stage_chip_bg = "rgba(20, 28, 42, 0.07)"
            self._stage_counter_bg = "rgba(255, 255, 255, 0.72)"
            self._stage_border = f"1px solid {Colors.BORDER_DEFAULT}"
        else:
            self._stage_text_rgb = (245, 241, 232)
            self._stage_ref_rgb = (216, 170, 90)
            self._stage_empty_color = "rgba(120, 120, 138, 0.30)"
            self._stage_meta_color = "rgba(245, 241, 232, 0.38)"
            self._stage_chip_bg = "rgba(245, 241, 232, 0.07)"
            self._stage_counter_bg = "rgba(0, 0, 0, 0.24)"
            self._stage_border = "none"

        self.setStyleSheet("")

        # ── Header ────────────────────────────────────────────────
        self.header = QFrame(self)
        self.header.setObjectName("TopBar")
        self.header.setFixedHeight(58)
        self.header.setStyleSheet(f"""
            QFrame#TopBar {{
                background: {Colors.BG_TERTIARY};
                border: none;
                border-radius: 14px;
            }}
        """)

        header_lay = QHBoxLayout(self.header)
        header_lay.setContentsMargins(16, 0, 16, 0)
        header_lay.setSpacing(10)
        header_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        icon_chip = QFrame(self.header)
        icon_chip.setFixedSize(30, 30)
        icon_chip.setStyleSheet(f"""
            background: {Colors.ACCENT_GLOW};
            border: none;
            border-radius: 11px;
        """)
        icon_chip_layout = QHBoxLayout(icon_chip)
        icon_chip_layout.setContentsMargins(7, 7, 7, 7)
        icon_chip_layout.setSpacing(0)

        icon_label = QLabel(icon_chip)
        icon_label.setPixmap(app_icon("monitor.svg", Colors.ACCENT_LIGHT).pixmap(15, 15))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_chip_layout.addWidget(icon_label)
        header_lay.addWidget(icon_chip, 0, Qt.AlignmentFlag.AlignVCenter)

        title_wrap = QVBoxLayout()
        title_wrap.setContentsMargins(0, 0, 0, 0)
        title_wrap.setSpacing(1)

        title = QLabel(tr("preview"), self.header)
        title.setStyleSheet(
            f"font-size: 12px; font-weight: 800; color: {Colors.TEXT_PRIMARY};"
            f"text-transform: uppercase; letter-spacing: 0;"
        )
        title_wrap.addWidget(title)

        subtitle = QLabel(tr("projection"), self.header)
        subtitle.setStyleSheet(
            f"font-size: 10px; color: {Colors.TEXT_MUTED};"
            "letter-spacing: 0;"
        )
        title_wrap.addWidget(subtitle)
        header_lay.addLayout(title_wrap, 1)
        header_lay.addStretch()

        self._mode_badge = QLabel("PREVIEW", self.header)
        self._mode_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mode_badge.setFixedHeight(24)
        self._mode_badge.setMinimumWidth(72)
        self._mode_badge.setStyleSheet(
            f"""
            QLabel {{
                background: rgba(116,167,248,0.14);
                border: none;
                border-radius: 10px;
                padding: 4px 10px;
                min-width: 56px;
                color: {Colors.ACCENT_PRIMARY};
                font-size: 9px;
                font-weight: 800;
                letter-spacing: 0;
            }}
            """
        )
        header_lay.addWidget(self._mode_badge, 0, Qt.AlignmentFlag.AlignVCenter)

        # ── Slide screen ──────────────────────────────────────────
        self._bg_live = (
            "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 #ffffff, stop:0.48 #f2f5fa, stop:1 #e6edf6)"
            if self._is_light_theme
            else "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 #101521, stop:0.45 #0b0d12, stop:1 #06070a)"
        )
        self._bg_hidden = (
            "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 #fff1f2, stop:1 #f8d7da)"
            if self._is_light_theme
            else "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #221a1c, stop:1 #100d10)"
        )

        self._slide_frame = QFrame()
        self._slide_frame.setObjectName("SlideScreen")
        self._slide_frame.setStyleSheet(self._slide_screen_style(self._bg_live))

        frame_layout = QVBoxLayout(self._slide_frame)
        frame_layout.setContentsMargins(18, 18, 18, 16)
        frame_layout.setSpacing(10)

        self._stage_top = QFrame(self._slide_frame)
        self._stage_top.setStyleSheet("background: transparent;")
        stage_top_layout = QHBoxLayout(self._stage_top)
        stage_top_layout.setContentsMargins(0, 0, 0, 0)
        stage_top_layout.setSpacing(8)

        self._live_badge = QLabel(tr("live").upper(), self._stage_top)
        self._live_badge.setStyleSheet(
            f"""
            background: rgba(86,214,129,0.18);
            border: none;
            color: #dfffe9;
            padding: 4px 10px;
            border-radius: 11px;
            font-size: 8px;
            font-weight: 800;
            letter-spacing: 0;
            """,
        )
        self._live_badge.hide()
        stage_top_layout.addWidget(self._live_badge, 0, Qt.AlignmentFlag.AlignLeft)

        self._status_chip = QLabel(tr("waiting"), self._stage_top)
        self._status_chip.setStyleSheet(
            f"""
            background: {self._stage_chip_bg};
            border: none;
            color: {Colors.TEXT_SECONDARY};
            padding: 4px 10px;
            border-radius: 11px;
            font-size: 8px;
            font-weight: 700;
            letter-spacing: 0;
            """
        )
        stage_top_layout.addWidget(self._status_chip, 0, Qt.AlignmentFlag.AlignLeft)
        stage_top_layout.addStretch()
        frame_layout.addWidget(self._stage_top, 0)

        # Main text
        self.slide_view = QLabel("", self._slide_frame)
        self.slide_view.setObjectName("SlideText")
        self.slide_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.slide_view.setWordWrap(True)
        frame_layout.addWidget(self.slide_view, 1)

        # Image display (shown instead of text for image slides)
        self._image_label = QLabel("", self._slide_frame)
        self._image_label.setObjectName("SlideImage")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._image_label.setStyleSheet("background: transparent; border: none;")
        self._image_label.setVisible(False)
        frame_layout.addWidget(self._image_label, 1)

        # Reference
        self._ref_label = QLabel("", self._slide_frame)
        self._ref_label.setObjectName("SlideRef")
        self._ref_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ref_label.setWordWrap(True)
        frame_layout.addWidget(self._ref_label, 0)

        self._stage_footer = QFrame(self._slide_frame)
        self._stage_footer.setStyleSheet("background: transparent;")
        stage_footer_layout = QHBoxLayout(self._stage_footer)
        stage_footer_layout.setContentsMargins(0, 0, 0, 0)
        stage_footer_layout.setSpacing(10)

        self._scene_label = QLabel("SCENE 00", self._stage_footer)
        self._scene_label.setStyleSheet(
            f"""
            color: {self._stage_meta_color};
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 0;
            """
        )
        stage_footer_layout.addWidget(self._scene_label)
        stage_footer_layout.addStretch()

        self._counter_label = QLabel("", self._stage_footer)
        self._counter_label.setStyleSheet(
            f"""
            color: {Colors.TEXT_SECONDARY};
            font-size: 9px;
            font-weight: 800;
            letter-spacing: 0.7px;
            background: {self._stage_counter_bg};
            border: none;
            border-radius: 11px;
            padding: 4px 10px;
            """
        )
        stage_footer_layout.addWidget(self._counter_label, 0, Qt.AlignmentFlag.AlignRight)
        frame_layout.addWidget(self._stage_footer, 0)

        # Subtle text shadows
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setOffset(0, 1)
        shadow.setBlurRadius(10)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.slide_view.setGraphicsEffect(shadow)

        ref_shadow = QGraphicsDropShadowEffect(self)
        ref_shadow.setOffset(0, 1)
        ref_shadow.setBlurRadius(6)
        ref_shadow.setColor(QColor(0, 0, 0, 160))
        self._ref_label.setGraphicsEffect(ref_shadow)

        self._slide_frame.resizeEvent = self._on_slide_resize

        # ── Controls bar ──────────────────────────────────────────
        self.controls = QFrame(self)
        self.controls.setStyleSheet(f"""
            background: {Colors.BG_TERTIARY};
            border: none;
            border-radius: 14px;
        """)
        controls_layout = QHBoxLayout(self.controls)
        controls_layout.setContentsMargins(12, 10, 12, 10)
        controls_layout.setSpacing(6)

        self._prev_button = _NavArrowButton(
            "chevron-left.svg", tr("previous"), self.controls
        )
        self._next_button = _NavArrowButton(
            "chevron-right.svg", tr("next"), self.controls
        )

        # Console capsule
        self.console_frame = QFrame(self.controls)
        self.console_frame.setStyleSheet(f"""
            background: {Colors.BG_SECONDARY};
            border: none;
            border-radius: 22px;
        """)
        console_layout = QHBoxLayout(self.console_frame)
        console_layout.setContentsMargins(6, 6, 6, 6)
        console_layout.setSpacing(6)

        self._project_button = PreviewControlButton(
            "cast.svg", tr("project"), self.console_frame, text=tr("project")
        )
        self._project_button.setCheckable(True)
        self._project_button.setObjectName("ProjectButton")

        self._hide_button = PreviewControlButton(
            "eye.svg", tr("hide"), self.console_frame, text=tr("hide")
        )
        self._hide_button.setCheckable(True)
        self._hide_button.setObjectName("HideButton")
        self._hide_button_base_style = self._hide_button.styleSheet()
        self._hide_button_hidden_style = self._hide_button._build_style(
            checked_bg="rgba(229,83,75,0.18)",
            checked_border="rgba(229,83,75,0.38)",
            checked_text="#ffb4ae",
        )
        self._hide_button.setStyleSheet(
            (
                self._hide_button_hidden_style
                if self._is_hidden
                else self._hide_button_base_style
            ),
        )

        console_layout.addWidget(self._project_button)
        console_layout.addWidget(self._hide_button)

        controls_layout.addStretch(1)
        controls_layout.addWidget(self._prev_button, 0, Qt.AlignmentFlag.AlignVCenter)
        controls_layout.addWidget(self.console_frame, 0, Qt.AlignmentFlag.AlignVCenter)
        controls_layout.addWidget(self._next_button, 0, Qt.AlignmentFlag.AlignVCenter)
        controls_layout.addStretch(1)

        # Connections
        self._prev_button.clicked.connect(self.prevRequested.emit)
        self._next_button.clicked.connect(self.nextRequested.emit)
        self._hide_button.clicked.connect(self._on_hide_clicked)
        self._project_button.toggled.connect(self.projectToggled.emit)

        # Shortcut
        self._hide_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self._hide_shortcut.activated.connect(self._toggle_hide)

        # Main Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.header)
        layout.addWidget(self._slide_frame, 1)
        layout.addWidget(self.controls)

    # ──────────────────────────────────────────────────────────────
    def _slide_screen_style(self, background: str) -> str:
        return f"""
            QFrame#SlideScreen {{
                background: {background};
                border-radius: 18px;
                border: {self._stage_border};
            }}
        """

    @staticmethod
    def _rgba(rgb: tuple[int, int, int], alpha: float) -> str:
        r, g, b = rgb
        return f"rgba({r}, {g}, {b}, {max(0.0, min(1.0, alpha)):.2f})"

    def _on_slide_resize(self, event) -> None:
        if event:
            QFrame.resizeEvent(self._slide_frame, event)
        self._refresh_image_pixmap()

    def set_project_active(self, active: bool) -> None:
        self._project_active = active
        with QSignalBlocker(self._project_button):
            self._project_button.setChecked(active)
        self._live_badge.setVisible(self._project_active and not self._is_hidden)
        self._update_mode_badge()
        self._update_stage_meta()

    def set_slide(self, reference: str, text: str, image_path: str = "") -> None:
        ref = str(reference or "").strip()
        body = str(text or "").strip()
        img = str(image_path or "").strip()
        self._current_reference = ref
        self._current_image_path = img
        self._has_content = bool(ref or body or img)

        if img and Path(img).is_file():
            self._image_label.setVisible(True)
            self.slide_view.setVisible(False)
            self._refresh_image_pixmap()
        else:
            self._current_image_path = ""
            self._image_label.setVisible(False)
            self._image_label.clear()
            self.slide_view.setVisible(True)
            self.slide_view.setText(body)
            self._ref_label.setText(ref)

        self._update_stage_meta()
        self._apply_slide_text_style()

    def _refresh_image_pixmap(self) -> None:
        if not self._current_image_path or not self._image_label.isVisible():
            return
        pixmap = QPixmap(self._current_image_path)
        if pixmap.isNull():
            self._image_label.setText("⚠ Image introuvable")
            return
        size = self._image_label.size()
        if size.width() < 10 or size.height() < 10:
            size = QSize(400, 280)
        self._image_label.setPixmap(
            pixmap.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )

    def set_slide_counter(self, current: int, total: int) -> None:
        self._current_row = current
        self._total_slides = total
        if total > 0 and current >= 0:
            self._counter_label.setText(f"{current + 1} / {total}")
            self._scene_label.setText(f"SCENE {current + 1:02d}")
        else:
            self._counter_label.setText("")
            self._scene_label.setText("SCENE 00")

    def _on_hide_clicked(self) -> None:
        self._is_hidden = self._hide_button.isChecked()
        self._update_hide_button()
        self.hideToggled.emit(self._is_hidden)

    def _update_mode_badge(self) -> None:
        if self._project_active:
            self._mode_badge.setText("LIVE")
            self._mode_badge.setStyleSheet(
                """
                QLabel {
                    background: rgba(62,207,115,0.18);
                    border: none;
                    border-radius: 10px;
                    padding: 4px 10px;
                    min-width: 56px;
                    color: #dfffe9;
                    font-size: 9px;
                    font-weight: 800;
                    letter-spacing: 0;
                }
                """
            )
        else:
            self._mode_badge.setText("PREVIEW")
            self._mode_badge.setStyleSheet(
                f"""
                QLabel {{
                    background: rgba(116,167,248,0.14);
                    border: none;
                    border-radius: 10px;
                    padding: 4px 10px;
                    min-width: 56px;
                    color: {Colors.TEXT_PRIMARY};
                    font-size: 9px;
                    font-weight: 800;
                    letter-spacing: 0;
                }}
                """
            )

    def _update_stage_meta(self) -> None:
        if self._is_hidden:
            self._status_chip.setText(tr("output_hidden"))
        elif self._project_active and self._has_content:
            self._status_chip.setText(tr("projection_active"))
        elif self._has_content:
            self._status_chip.setText(tr("ready_to_project"))
        else:
            self._status_chip.setText(tr("waiting"))

    def _update_hide_button(self) -> None:
        if self._is_hidden:
            self._hide_button.setIcon(app_icon("eye-off.svg", "#ffb4ae"))
            self._hide_button.setText(tr("show"))
            self._hide_button.setStyleSheet(self._hide_button_hidden_style)
            self._slide_frame.setStyleSheet(self._slide_screen_style(self._bg_hidden))
        else:
            self._hide_button.setIcon(app_icon("eye.svg", Colors.TEXT_PRIMARY))
            self._hide_button.setText(tr("hide"))
            self._hide_button.setStyleSheet(self._hide_button_base_style)
            self._slide_frame.setStyleSheet(self._slide_screen_style(self._bg_live))

        self._live_badge.setVisible(self._project_active and not self._is_hidden)
        self._update_stage_meta()
        self._apply_slide_text_style()

    def set_hidden(self, hidden: bool) -> None:
        self._is_hidden = hidden
        self._hide_button.setChecked(hidden)
        self._update_hide_button()

    def _toggle_hide(self) -> None:
        self._hide_button.setChecked(not self._hide_button.isChecked())
        self._on_hide_clicked()

    def _apply_slide_text_style(self) -> None:
        text_len = len(self.slide_view.text().strip())

        base_size = 22
        line_height = 1.3
        font_weight = "600"
        transform = "none"

        if self._settings and hasattr(self._settings, "obs"):
            obs_output = self._settings.obs.output
            base_size = max(16, int(obs_output.text_size * 0.60))
            line_height = obs_output.line_height
            font_weight = (
                "800"
                if obs_output.font_weight == "bold"
                else "300" if obs_output.font_weight == "light" else "500"
            )
            transform = obs_output.text_transform

        # Progressive scale
        if text_len > 400:
            font_size = base_size * 0.58
        elif text_len > 280:
            font_size = base_size * 0.70
        elif text_len > 180:
            font_size = base_size * 0.82
        else:
            font_size = base_size

        font_size = max(10, int(font_size))

        alpha = 0.18 if self._is_hidden else 1.0
        color = (
            self._rgba(self._stage_text_rgb, alpha)
            if self._has_content
            else self._stage_empty_color
        )
        ref_color = (
            self._rgba(self._stage_ref_rgb, alpha * 0.8)
            if self._has_content
            else "transparent"
        )

        self.slide_view.setStyleSheet(f"""
            QLabel {{
                font-size: {font_size}px;
                font-weight: {font_weight};
                color: {color};
                background: transparent;
                line-height: {line_height};
                text-transform: {transform};
                padding: 10px 10px 4px 10px;
            }}
        """)

        ref_size = max(9, font_size - 5)
        self._ref_label.setStyleSheet(f"""
            QLabel {{
                font-size: {ref_size}px;
                font-weight: 700;
                color: {ref_color};
                background: transparent;
                letter-spacing: 0;
                padding-top: 6px;
            }}
        """)

    def get_current_reference(self) -> str:
        return self._current_reference
