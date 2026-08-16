from __future__ import annotations

import copy
import math
import re

from PyQt6.QtCore import QRect, QSize, Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.icons import app_icon
from app.ui.theme import Colors, Radius, Typography, get_scroll_area_style
from app.utils.fonts import get_available_fonts
from app.utils.settings import ObsScene, ObsOutputSettings, ObsSettings, scene_slug
from app.utils.translations import tr


class ObsPreviewWidget(QFrame):
    """A widget that renders a live preview of the OBS lower third."""

    def __init__(self, settings: ObsOutputSettings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self.setMinimumHeight(240)
        self.setStyleSheet(f"""
            ObsPreviewWidget {{
                background: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 12px;
            }}
        """)

    def update_settings(self, settings: ObsOutputSettings):
        self._settings = settings
        self.update()

    _RGBA_RE = re.compile(
        r"rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\s*\)"
    )

    def _parse_color(
        self, color_str: str, override_alpha: float | None = None
    ) -> QColor:
        try:
            match = self._RGBA_RE.match(color_str)
            if match:
                r, g, b = int(match.group(1)), int(match.group(2)), int(match.group(3))
                if override_alpha is not None:
                    a = override_alpha
                else:
                    a = float(match.group(4)) if match.group(4) else 1.0
                return QColor(r, g, b, int(a * 255))
        except (TypeError, ValueError):
            pass
        qc = QColor(color_str)
        if qc.isValid():
            if override_alpha is not None:
                qc.setAlpha(int(override_alpha * 255))
            return qc
        return QColor(255, 255, 255)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._settings.opacity)
        rect = self.contentsRect()
        W, H = rect.width(), rect.height()
        scale = max(0.12, min(W / 1920.0, H / 1080.0))
        safe = max(4, int(self._settings.edge_margin * scale)) + int(
            min(W, H) * self._settings.safe_area_percent / 100
        )
        mode = self._settings.layout_mode or "lower_third"
        width_ratio = max(0.40, min(1.0, self._settings.max_width / 100.0))

        if mode == "fullscreen":
            text_rect = QRect(safe, safe, W - (safe * 2), H - (safe * 2))
        elif mode == "side_panel":
            panel_w = min(
                max(120, W - (safe * 2)),
                max(120, int(W * width_ratio)),
            )
            x = W - safe - panel_w if self._settings.panel_side == "right" else safe
            text_rect = QRect(x, safe, panel_w, H - (safe * 2))
        elif mode == "subtitle":
            panel_h = max(64, int(H * 0.24))
            panel_w = min(W - (safe * 2), int(W * width_ratio))
            text_rect = QRect(
                (W - panel_w) // 2,
                H - safe - panel_h,
                panel_w,
                panel_h,
            )
        elif mode == "focus_card":
            panel_w = min(W - (safe * 2), int(W * width_ratio))
            panel_h = int(H * 0.56)
            text_rect = QRect(
                (W - panel_w) // 2, (H - panel_h) // 2, panel_w, panel_h
            )
        else:
            panel_w = min(W - (safe * 2), int(W * width_ratio))
            panel_h = max(80, int(H * 0.34))
            x = (
                safe
                if self._settings.band_align == "left"
                else W - safe - panel_w
                if self._settings.band_align == "right"
                else (W - panel_w) // 2
            )
            y = (
                safe
                if self._settings.position == "top"
                else (H - panel_h) // 2
                if self._settings.position == "center"
                else H - safe - panel_h
            )
            text_rect = QRect(x, y, panel_w, panel_h)

        text_rect.translate(
            int(self._settings.offset_x * scale),
            int(self._settings.offset_y * scale),
        )

        if self._settings.bg_enabled:
            radius = max(0, int(self._settings.border_radius * scale))
            bg_color = self._parse_color(
                self._settings.bg_color, self._settings.bg_opacity
            )
            if self._settings.bg_gradient_enabled:
                bg_color_2 = self._parse_color(
                    self._settings.bg_color_2, self._settings.bg_opacity
                )
                angle = self._settings.bg_gradient_angle
                rad = math.radians(angle)
                x1 = W / 2 - math.sin(rad) * 100
                y1 = H / 2 + math.cos(rad) * 100
                x2 = W / 2 + math.sin(rad) * 100
                y2 = H / 2 - math.cos(rad) * 100
                gradient = QLinearGradient(x1, y1, x2, y2)
                gradient.setColorAt(0, bg_color)
                gradient.setColorAt(1, bg_color_2)
                painter.setBrush(QBrush(gradient))
            else:
                painter.setBrush(QBrush(bg_color))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(text_rect, radius, radius)

        pad_h = max(0, int(self._settings.padding_horizontal * scale))
        pad_v = max(0, int(self._settings.padding_vertical * scale))
        inner = text_rect.adjusted(pad_h, pad_v, -pad_h, -pad_v)
        if self._settings.show_accent_bar and mode != "fullscreen":
            accent_color = (
                self._settings.accent_color
                if self._settings.accent_mode == "custom"
                else "#74a7f8"
            )
            painter.setBrush(QBrush(self._parse_color(accent_color)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(
                QRect(text_rect.x(), text_rect.y(), 5, text_rect.height()), 2, 2
            )

        text_color = self._parse_color(self._settings.text_color)
        painter.setPen(QPen(text_color))
        # Scale from the OBS reference canvas (1920×1080) without a hard cap:
        # changing the main text size must remain visible in the preview.
        font_size = max(4, int(round(self._settings.text_size * scale)))
        ref_font_size = max(4, int(round(self._settings.ref_size * scale)))
        self._last_effective_text_size = font_size
        font = QFont(self._settings.font_family or Typography.FAMILY)
        font.setPixelSize(font_size)
        font.setLetterSpacing(
            QFont.SpacingType.AbsoluteSpacing,
            float(self._settings.letter_spacing * scale),
        )
        if self._settings.font_weight == "bold":
            font.setBold(True)
        elif self._settings.font_weight == "light":
            font.setWeight(QFont.Weight.Light)
        painter.setFont(font)
        align = (
            Qt.AlignmentFlag.AlignLeft
            if self._settings.align == "left" or mode == "side_panel"
            else Qt.AlignmentFlag.AlignRight
            if self._settings.align == "right"
            else Qt.AlignmentFlag.AlignHCenter
        )
        ref_height = (
            max(8, int(ref_font_size * 1.75))
            if self._settings.show_reference
            else 0
        )
        body_rect = inner.adjusted(0, 0, 0, -(ref_height + 3))
        painter.drawText(
            body_rect,
            align | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap,
            "La foi transforme notre manière de voir et d'avancer.",
        )

        if self._settings.show_reference:
            ref_font = QFont(font)
            ref_font.setPixelSize(ref_font_size)
            ref_font.setBold(False)
            painter.setFont(ref_font)
            painter.setPen(QPen(self._parse_color(self._settings.ref_color)))
            ref_rect = QRect(
                inner.x(),
                inner.bottom() - ref_height + 1,
                inner.width(),
                ref_height,
            )
            painter.drawText(
                ref_rect,
                align | Qt.AlignmentFlag.AlignVCenter,
                "Hébreux 11:1",
            )


# Modern styles
DIALOG_STYLE = f"""
    QDialog {{
        background: {Colors.BG_PRIMARY};
    }}
    QLabel {{
        color: {Colors.TEXT_PRIMARY};
    }}
    QComboBox {{
        background: {Colors.BG_ELEVATED};
        border: 1px solid {Colors.BORDER_DEFAULT};
        border-radius: {Radius.MD}px;
        padding: 10px 14px;
        min-width: 160px;
        min-height: 20px;
        color: {Colors.TEXT_PRIMARY};
        font-size: {Typography.SIZE_FILTER}px;
    }}
    QComboBox:hover {{
        border: 1px solid {Colors.BORDER_FOCUS};
    }}
    QComboBox::drop-down {{
        border: none;
        padding-right: 10px;
    }}
    QComboBox QAbstractItemView {{
        background: {Colors.BG_ELEVATED};
        border: 1px solid {Colors.BORDER_DEFAULT};
        border-radius: {Radius.MD}px;
        outline: none;
        padding: 4px;
        color: {Colors.TEXT_PRIMARY};
        selection-background-color: {Colors.ACCENT_GLOW_STRONG};
        selection-color: {Colors.ACCENT_PRIMARY};
    }}
    QSpinBox, QDoubleSpinBox {{
        background: {Colors.BG_ELEVATED};
        border: 1px solid {Colors.BORDER_DEFAULT};
        border-radius: {Radius.MD}px;
        padding: 10px 14px;
        min-height: 20px;
        min-width: 80px;
        color: {Colors.TEXT_PRIMARY};
        font-size: {Typography.SIZE_CONTROL}px;
    }}
    QSpinBox:hover, QDoubleSpinBox:hover {{
        border: 1px solid {Colors.BORDER_HOVER};
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {Colors.BORDER_FOCUS};
    }}
    QCheckBox {{
        color: {Colors.TEXT_PRIMARY};
        spacing: 10px;
        font-size: {Typography.SIZE_BODY}px;
    }}
    QCheckBox::indicator {{
        width: 20px;
        height: 20px;
        border-radius: 5px;
        border: 1px solid {Colors.BORDER_DEFAULT};
        background: {Colors.BG_ELEVATED};
    }}
    QCheckBox::indicator:checked {{
        background: {Colors.ACCENT_PRIMARY};
        border: 1px solid {Colors.ACCENT_PRIMARY};
    }}
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
    }}
    QScrollBar::handle:vertical {{
        background: {Colors.BORDER_DEFAULT};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
"""


class ColorPickerButton(QPushButton):
    """Modern color picker button."""

    colorChanged = pyqtSignal(str)

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(48, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()
        self.clicked.connect(self._pick_color)

    def _parse_rgba(self, color_str: str) -> QColor:
        try:
            match = re.match(
                r"rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\s*\)",
                color_str,
            )
            if match:
                r, g, b = int(match.group(1)), int(match.group(2)), int(match.group(3))
                a = float(match.group(4)) if match.group(4) else 1.0
                return QColor(r, g, b, int(a * 255))
        except Exception:
            pass
        qc = QColor(color_str)
        return qc if qc.isValid() else QColor(0, 0, 0, 191)

    def _update_style(self) -> None:
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self._color};
                border: 2px solid {Colors.BORDER_DEFAULT};
                border-radius: 6px;
            }}
            QPushButton:hover {{
                border: 2px solid {Colors.BORDER_FOCUS};
            }}
        """)

    def _pick_color(self) -> None:
        initial = self._parse_rgba(self._color)
        color = QColorDialog.getColor(
            initial,
            self,
            "Choisir une couleur",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if color.isValid():
            self._color = f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha() / 255:.2f})"
            self._update_style()
            self.colorChanged.emit(self._color)

    def color(self) -> str:
        return self._color

    def set_color(self, color: str) -> None:
        self._color = color
        self._update_style()


class SettingRow(QFrame):
    """A single setting row with label and control."""

    def __init__(self, label: str, widget: QWidget, description: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: transparent;
                border-bottom: 1px solid {Colors.BORDER_DEFAULT};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 12, 4, 12)
        layout.setSpacing(20)

        # Label column
        label_col = QVBoxLayout()
        label_col.setSpacing(3)

        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"font-size: {Typography.SIZE_LABEL}px; font-weight: 500; color: {Colors.TEXT_PRIMARY}; border: none;"
        )
        label_col.addWidget(lbl)

        if description:
            desc = QLabel(description)
            desc.setStyleSheet(
                f"font-size: {Typography.SIZE_CONTROL}px; color: {Colors.TEXT_SECONDARY}; border: none;"
            )
            desc.setWordWrap(True)
            label_col.addWidget(desc)

        layout.addLayout(label_col, 1)
        layout.addWidget(widget)


class SettingSection(QFrame):
    """A section with title and settings."""

    def __init__(self, title: str, icon_name: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            SettingSection {{
                background: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 14px;
            }}
        """)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 18, 20, 14)
        self._layout.setSpacing(2)

        # Header
        header = QHBoxLayout()
        header.setSpacing(10)

        if icon_name:
            icon_label = QLabel()
            icon_label.setPixmap(app_icon(icon_name).pixmap(20, 20))
            icon_label.setStyleSheet("background: transparent; border: none;")
            header.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"font-size: {Typography.SIZE_SECTION}px; font-weight: 600; color: {Colors.ACCENT_LIGHT}; background: transparent; border: none;"
        )
        header.addWidget(title_label, 1)

        self._layout.addLayout(header)

        # Separator (optional, keeping minimal line)
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {Colors.BORDER_DEFAULT}; border: none;")
        self._layout.addWidget(sep)
        self._layout.addSpacing(4)

    def addRow(self, label: str, widget: QWidget, description: str = "") -> None:
        row = SettingRow(label, widget, description)
        self._layout.addWidget(row)

    def addWidget(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)


class NavButton(QPushButton):
    """Navigation button for sidebar."""

    def __init__(self, text: str, icon_name: str, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setIcon(app_icon(icon_name))
        self.setIconSize(QSize(20, 20))
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(46)
        self._update_style(False)

    def _update_style(self, checked: bool) -> None:
        if checked:
            self.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ACCENT_GLOW_STRONG};
                border: 1px solid {Colors.BORDER_FOCUS};
                border-left: 3px solid {Colors.ACCENT_PRIMARY};
                    border-radius: 8px;
                    padding: 10px 14px;
                    text-align: left;
                    font-size: {Typography.SIZE_LABEL}px;
                    font-weight: 600;
                color: {Colors.ACCENT_PRIMARY};
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    border-radius: 8px;
                    padding: 10px 14px;
                    text-align: left;
                    font-size: {Typography.SIZE_LABEL}px;
                    color: {Colors.TEXT_MUTED};
                }}
                QPushButton:hover {{
                    background: {Colors.SURFACE_HOVER};
                    color: {Colors.TEXT_SECONDARY};
                }}
            """)

    def setChecked(self, checked: bool) -> None:
        super().setChecked(checked)
        self._update_style(checked)


class ObsOutputSettingsDialog(QDialog):
    settingsChanged = pyqtSignal(ObsOutputSettings)
    # Full OBS settings (base style + named scenes) — used for live updates.
    obsSettingsChanged = pyqtSignal(object)

    def __init__(
        self, obs_settings: ObsSettings, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Paramètres de diffusion OBS")
        self.setMinimumSize(820, 600)
        self.resize(980, 700)
        self.setStyleSheet(DIALOG_STYLE)

        self._initializing = True  # Block signals during creation
        # Work on a private copy: live updates broadcast it, cancel restores
        # the caller's object untouched.
        self._obs_settings = copy.deepcopy(obs_settings)
        self._scene_index = -1  # -1 = base style, otherwise index in scenes
        self._nav_buttons = []

        # Background type/image/fit are chosen in the Projection settings dialog
        # (and mirrored onto the OBS output). This dialog does not edit them, so
        # carry them through verbatim — otherwise editing any field here would
        # reset them to defaults and the OBS overlay would drop the background
        # image and revert to the coloured gradient.
        settings = self._active_output()
        self._bg_mode = settings.bg_mode
        self._bg_image = settings.bg_image
        self._bg_image_fit = settings.bg_image_fit
        
        # Debounce timer for live updates
        self._change_timer = QTimer(self)
        self._change_timer.setSingleShot(True)
        self._change_timer.timeout.connect(self._emit_settings_changed)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ===== SIDEBAR =====
        sidebar = QFrame()
        sidebar.setMinimumWidth(160)
        sidebar.setMaximumWidth(220)
        sidebar.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_SECONDARY};
                border-right: 1px solid {Colors.BORDER_DEFAULT};
            }}
        """)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 18, 14, 18)
        sidebar_layout.setSpacing(4)

        # Logo/Title
        title_frame = QFrame()
        title_frame.setStyleSheet("background: transparent;")
        title_layout = QHBoxLayout(title_frame)
        title_layout.setContentsMargins(8, 8, 8, 16)
        title_layout.setSpacing(10)

        logo = QLabel()
        logo.setPixmap(app_icon("monitor.svg").pixmap(24, 24))
        logo.setStyleSheet("background: transparent;")
        title_layout.addWidget(logo)

        title = QLabel("Projection OBS")
        title.setStyleSheet(
            f"font-size: {Typography.SIZE_TITLE}px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; background: transparent;"
        )
        title_layout.addWidget(title, 1)
        sidebar_layout.addWidget(title_frame)

        # Navigation buttons
        nav_items = [
            ("Disposition", "layout.svg"),
            ("Texte", "type.svg"),
            ("Couleurs", "palette.svg"),
            ("Effets", "sparkles.svg"),
        ]

        for i, (text, icon) in enumerate(nav_items):
            btn = NavButton(text, icon)
            btn.clicked.connect(lambda checked, idx=i: self._on_nav_clicked(idx))
            self._nav_buttons.append(btn)
            sidebar_layout.addWidget(btn)

        sidebar_layout.addStretch()

        # Reset button at bottom
        reset_btn = QPushButton("Réinitialiser")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.GLASS_MEDIUM};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 8px;
                padding: 10px;
                color: {Colors.ACCENT_DANGER};
                font-size: {Typography.SIZE_CONTROL}px;
            }}
            QPushButton:hover {{
                background: {Colors.GLASS_HEAVY};
                border-color: {Colors.ACCENT_DANGER};
            }}
        """)
        reset_btn.clicked.connect(self._reset_defaults)
        sidebar_layout.addWidget(reset_btn)

        main_layout.addWidget(sidebar)

        # ===== CONTENT AREA =====
        content_wrapper = QHBoxLayout()  # Horizontal split for preview

        content = QWidget()
        content.setStyleSheet(f"background: {Colors.BG_PRIMARY};")
        content.setObjectName("SettingsContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 24, 28, 20)
        content_layout.setSpacing(20)

        # Stacked widget for pages
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")

        # Scene selector bar (base style vs per-OBS-scene styles)
        self._create_scene_bar(content_layout)

        # Create all pages
        self._create_layout_page(settings)
        self._create_text_page(settings)
        self._create_colors_page(settings)
        self._create_effects_page(settings)

        content_layout.addWidget(self._stack, 1)

        # Preview Panel (Right Side)
        preview_panel = QFrame()
        preview_panel.setMinimumWidth(240)
        preview_panel.setMaximumWidth(360)
        preview_panel.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_SECONDARY};
                border-left: 1px solid {Colors.BORDER_DEFAULT};
            }}
        """)
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(16, 24, 16, 24)
        preview_layout.setSpacing(16)

        preview_hdr = QLabel("Aperçu en direct")
        preview_hdr.setStyleSheet(
            f"font-size: {Typography.SIZE_SECTION}px; font-weight: 600; color: {Colors.ACCENT_LIGHT};"
        )
        preview_layout.addWidget(preview_hdr)

        self._preview_widget = ObsPreviewWidget(settings)
        preview_layout.addWidget(self._preview_widget)

        preview_help = QLabel(
            "L'aperçu simule l'apparence sur OBS. Certains effets (flou, ombres avancées) peuvent varier légèrement."
        )
        preview_help.setWordWrap(True)
        preview_help.setStyleSheet(f"font-size: {Typography.SIZE_META}px; color: {Colors.TEXT_MUTED};")
        preview_layout.addWidget(preview_help)

        # Presets section in preview
        preview_layout.addSpacing(20)
        preset_hdr = QLabel("Préréglages (Styles)")
        preset_hdr.setStyleSheet(
            f"font-size: {Typography.SIZE_LABEL}px; font-weight: 600; color: {Colors.TEXT_SECONDARY};"
        )
        preview_layout.addWidget(preset_hdr)

        self._create_preset_buttons(preview_layout)

        preview_layout.addStretch()

        content_wrapper.addWidget(content, 1)
        content_wrapper.addWidget(preview_panel)

        # Bottom controls wrapper
        final_layout = QVBoxLayout()
        final_layout.addLayout(content_wrapper, 1)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(28, 0, 28, 20)
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

        ok_btn = QPushButton("Appliquer")
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ACCENT_PRIMARY};
                border: 1px solid {Colors.ACCENT_PRIMARY};
                border-radius: 8px;
                padding: 10px 24px;
                color: {Colors.PROJECT_BUTTON_TEXT};
                font-size: {Typography.SIZE_CONTROL}px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {Colors.ACCENT_SECONDARY};
            }}
        """)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)

        final_layout.addLayout(btn_layout)
        main_layout.addLayout(final_layout, 1)

        # Select first nav button
        self._nav_buttons[0].setChecked(True)

        # Connect signals for live updates
        self._connect_signals()

        # Force opaque background on all combo popups (Windows workaround)
        try:
            _popup_qss = f"""
                QAbstractItemView {{
                    background-color: {Colors.BG_ELEVATED};
                    border: 1px solid {Colors.BORDER_DEFAULT};
                    border-radius: 6px;
                    padding: 4px;
                    color: {Colors.TEXT_PRIMARY};
                    selection-background-color: {Colors.ACCENT_GLOW_STRONG};
                    selection-color: {Colors.ACCENT_PRIMARY};
                    outline: none;
                }}
            """
            for combo in self.findChildren(QComboBox):
                v = combo.view()
                if v:
                    v.setStyleSheet(_popup_qss)
                    v.window().setStyleSheet(
                        f"background: {Colors.BG_ELEVATED}; border: 1px solid {Colors.BORDER_DEFAULT}; border-radius: 6px;"
                    )
        except Exception:
            pass

        # Construction complete — allow signals
        self._initializing = False
        self._on_change()

    def _add_scroll_page(self, widget: QWidget) -> int:
        """Helper to wrap a page in a scroll area before adding to stack."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet(get_scroll_area_style())
        scroll.setWidget(widget)
        return self._stack.addWidget(scroll)

    # ── Scene management ───────────────────────────────────────────────

    def _active_output(self) -> ObsOutputSettings:
        """The output style currently being edited (base or a named scene)."""
        if 0 <= self._scene_index < len(self._obs_settings.scenes):
            return self._obs_settings.scenes[self._scene_index].output
        return self._obs_settings.output

    def _create_scene_bar(self, layout: QVBoxLayout) -> None:
        bar = QFrame()
        bar.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 10px;
            }}
        """)
        bar_layout = QVBoxLayout(bar)
        bar_layout.setContentsMargins(14, 10, 14, 10)
        bar_layout.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        label = QLabel("Style édité :")
        label.setStyleSheet(
            f"font-size: {Typography.SIZE_CONTROL}px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        top_row.addWidget(label)

        self._scene_combo = QComboBox()
        self._scene_combo.setMinimumWidth(220)
        self._refresh_scene_combo()
        top_row.addWidget(self._scene_combo, 1)

        btn_style = f"""
            QPushButton {{
                background: {Colors.BG_ELEVATED};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 6px;
                padding: 6px 10px;
                color: {Colors.TEXT_SECONDARY};
                font-size: {Typography.SIZE_CONTROL}px;
            }}
            QPushButton:hover {{
                background: {Colors.SURFACE_HOVER};
                border-color: {Colors.ACCENT_PRIMARY};
                color: {Colors.TEXT_PRIMARY};
            }}
        """
        add_btn = QPushButton("＋ Scène")
        add_btn.setToolTip("Créer un style indépendant pour une scène OBS")
        add_btn.setStyleSheet(btn_style)
        add_btn.clicked.connect(self._add_scene)
        top_row.addWidget(add_btn)

        self._rename_btn = QPushButton("Renommer")
        self._rename_btn.setStyleSheet(btn_style)
        self._rename_btn.clicked.connect(self._rename_scene)
        top_row.addWidget(self._rename_btn)

        self._dup_btn = QPushButton("Dupliquer")
        self._dup_btn.setStyleSheet(btn_style)
        self._dup_btn.clicked.connect(self._duplicate_scene)
        top_row.addWidget(self._dup_btn)

        self._del_btn = QPushButton("Supprimer")
        self._del_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_ELEVATED};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 6px;
                padding: 6px 10px;
                color: {Colors.ACCENT_DANGER};
                font-size: {Typography.SIZE_CONTROL}px;
            }}
            QPushButton:hover {{
                background: {Colors.SURFACE_HOVER};
                border-color: {Colors.ACCENT_DANGER};
            }}
        """)
        self._del_btn.clicked.connect(self._delete_scene)
        top_row.addWidget(self._del_btn)

        bar_layout.addLayout(top_row)

        self._scene_url_label = QLabel("")
        self._scene_url_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._scene_url_label.setStyleSheet(
            f"font-size: {Typography.SIZE_META}px; color: {Colors.TEXT_MUTED}; background: transparent;"
        )
        bar_layout.addWidget(self._scene_url_label)

        copy_btn = QPushButton("Copier l'URL de la scène")
        copy_btn.setStyleSheet(btn_style)
        copy_btn.clicked.connect(self._copy_scene_url)
        self._scene_copy_btn = copy_btn
        bar_layout.addWidget(copy_btn)

        self._scene_combo.currentIndexChanged.connect(self._on_scene_selected)
        self._update_scene_bar_state()
        layout.addWidget(bar)

    def _refresh_scene_combo(self) -> None:
        self._scene_combo.blockSignals(True)
        self._scene_combo.clear()
        self._scene_combo.addItem("Style de base (toutes scènes)", -1)
        for i, scene in enumerate(self._obs_settings.scenes):
            self._scene_combo.addItem(f"Scène : {scene.name}", i)
        idx = self._scene_combo.findData(self._scene_index)
        if idx >= 0:
            self._scene_combo.setCurrentIndex(idx)
        self._scene_combo.blockSignals(False)

    def _update_scene_bar_state(self) -> None:
        scene_selected = 0 <= self._scene_index < len(self._obs_settings.scenes)
        for btn in (self._rename_btn, self._dup_btn, self._del_btn):
            btn.setEnabled(scene_selected)
        self._scene_copy_btn.setVisible(scene_selected)
        if scene_selected:
            scene = self._obs_settings.scenes[self._scene_index]
            self._scene_url_label.setText(
                f"URL OBS : http://127.0.0.1:{self._obs_settings.web_port}"
                f"/obs?scene={scene.id}"
            )
            self._scene_url_label.setVisible(True)
        else:
            self._scene_url_label.setText(
                "Le style de base s'applique aux sources sans paramètre ?scene=."
            )
            self._scene_url_label.setVisible(True)

    def _on_scene_selected(self, combo_index: int) -> None:
        data = self._scene_combo.itemData(combo_index)
        new_index = int(data) if isinstance(data, int) else -1
        if new_index == self._scene_index:
            return
        # Commit the widgets onto the previously edited output before switching.
        self.get_settings()
        self._scene_index = new_index
        out = self._active_output()
        self._bg_mode = out.bg_mode
        self._bg_image = out.bg_image
        self._bg_image_fit = out.bg_image_fit
        self._apply_settings_to_widgets(out)
        self._update_scene_bar_state()

    def _add_scene(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Nouvelle scène", "Nom de la scène OBS (ex. Louange, Prédication) :"
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        existing_ids = [s.id for s in self._obs_settings.scenes]
        scene = ObsScene(
            id=scene_slug(name, existing_ids),
            name=name,
            output=copy.deepcopy(self._obs_settings.output),
        )
        self.get_settings()  # commit current edits first
        self._obs_settings.scenes.append(scene)
        self._scene_index = len(self._obs_settings.scenes) - 1
        self._refresh_scene_combo()
        self._update_scene_bar_state()
        self._on_change()

    def _rename_scene(self) -> None:
        if not 0 <= self._scene_index < len(self._obs_settings.scenes):
            return
        scene = self._obs_settings.scenes[self._scene_index]
        name, ok = QInputDialog.getText(
            self, "Renommer la scène", "Nouveau nom :", text=scene.name
        )
        if not ok or not name.strip():
            return
        scene.name = name.strip()
        self._refresh_scene_combo()
        self._update_scene_bar_state()

    def _duplicate_scene(self) -> None:
        if not 0 <= self._scene_index < len(self._obs_settings.scenes):
            return
        self.get_settings()  # commit current edits first
        src = self._obs_settings.scenes[self._scene_index]
        existing_ids = [s.id for s in self._obs_settings.scenes]
        clone = ObsScene(
            id=scene_slug(src.id, existing_ids),
            name=f"{src.name} (copie)",
            output=copy.deepcopy(src.output),
        )
        self._obs_settings.scenes.append(clone)
        self._scene_index = len(self._obs_settings.scenes) - 1
        self._refresh_scene_combo()
        self._update_scene_bar_state()
        self._on_change()

    def _delete_scene(self) -> None:
        if not 0 <= self._scene_index < len(self._obs_settings.scenes):
            return
        scene = self._obs_settings.scenes[self._scene_index]
        confirm = QMessageBox.question(
            self,
            "Supprimer la scène",
            f"Supprimer le style « {scene.name} » ?\n"
            "Les sources OBS qui utilisent son URL reviendront au style de base.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._obs_settings.scenes.pop(self._scene_index)
        self._scene_index = -1
        out = self._active_output()
        self._bg_mode = out.bg_mode
        self._bg_image = out.bg_image
        self._bg_image_fit = out.bg_image_fit
        self._apply_settings_to_widgets(out)
        self._refresh_scene_combo()
        self._update_scene_bar_state()
        self._on_change()

    def _copy_scene_url(self) -> None:
        if not 0 <= self._scene_index < len(self._obs_settings.scenes):
            return
        scene = self._obs_settings.scenes[self._scene_index]
        url = (
            f"http://127.0.0.1:{self._obs_settings.web_port}"
            f"/obs?scene={scene.id}"
        )
        from PyQt6.QtWidgets import QApplication

        QApplication.clipboard().setText(url)

    def _on_change(self, *_args) -> None:
        """Trigger debounced settings changed signal."""
        if getattr(self, "_initializing", True):
            return

        try:
            if hasattr(self, "_text_size") and hasattr(self, "_min_text_size"):
                self._min_text_size.setMaximum(
                    max(12, self._text_size.value())
                )
                if self._min_text_size.value() > self._text_size.value():
                    self._min_text_size.setValue(self._text_size.value())
                uniform = self._uniform_text_size.isChecked()
                self._auto_fit.setEnabled(not uniform)
                auto_fit = not uniform and self._auto_fit.isChecked()
                self._min_text_size.setEnabled(auto_fit)
                self._max_lines.setEnabled(auto_fit)

            # Immediate UI feedback for preview widget
            settings = self.get_settings()
            if hasattr(self, "_preview_widget"):
                self._preview_widget.update_settings(settings)
                
            # Debounce the network-heavy signal emission (e.g. while dragging sliders)
            self._change_timer.start(50)  # 50ms delay for smoothness
        except Exception:
            pass

    def _emit_settings_changed(self) -> None:
        """Safely emit the settingsChanged signal."""
        if getattr(self, "_initializing", True):
            return
        try:
            settings = self.get_settings()
            self.settingsChanged.emit(settings)
            self.obsSettingsChanged.emit(self._obs_settings)
        except Exception:
            pass

    def _connect_signals(self) -> None:
        """Connect all input widgets to the change handler."""
        # Robust discovery of all input widgets in the dialog
        from PyQt6.QtWidgets import (
            QCheckBox,
            QComboBox,
            QDoubleSpinBox,
            QSlider,
            QSpinBox,
        )

        for w in self.findChildren(QComboBox):
            try:
                w.currentIndexChanged.disconnect(self._on_change)
            except (TypeError, RuntimeError):
                pass
            w.currentIndexChanged.connect(self._on_change)

        for w in self.findChildren(QSpinBox):
            try:
                w.valueChanged.disconnect(self._on_change)
            except (TypeError, RuntimeError):
                pass
            w.valueChanged.connect(self._on_change)

        for w in self.findChildren(QDoubleSpinBox):
            try:
                w.valueChanged.disconnect(self._on_change)
            except (TypeError, RuntimeError):
                pass
            w.valueChanged.connect(self._on_change)

        for w in self.findChildren(QSlider):
            try:
                w.valueChanged.disconnect(self._on_change)
            except (TypeError, RuntimeError):
                pass
            w.valueChanged.connect(self._on_change)

        for w in self.findChildren(QCheckBox):
            try:
                w.toggled.disconnect(self._on_change)
            except (TypeError, RuntimeError):
                pass
            w.toggled.connect(self._on_change)

        # Connect custom buttons
        for w in self.findChildren(ColorPickerButton):
            try:
                w.colorChanged.disconnect(self._on_change)
            except Exception:
                pass
            w.colorChanged.connect(self._on_change)

    def _on_nav_clicked(self, index: int) -> None:
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)
        self._stack.setCurrentIndex(index)

    def _create_layout_page(self, settings: ObsOutputSettings) -> None:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        mode_section = SettingSection("Mode de composition", "monitor.svg")

        self._layout_mode = QComboBox()
        for label, data in (
            ("Lower Third", "lower_third"),
            ("Plein écran", "fullscreen"),
            ("Panneau latéral", "side_panel"),
            ("Sous-titre", "subtitle"),
            ("Carte focus", "focus_card"),
        ):
            self._layout_mode.addItem(label, data)
        idx = self._layout_mode.findData(settings.layout_mode or "lower_third")
        self._layout_mode.setCurrentIndex(max(idx, 0))
        mode_section.addRow(
            "Composition",
            self._layout_mode,
            "Chaque mode peut aussi être forcé dans l'URL OBS avec ?layout=nom_du_mode.",
        )

        self._panel_side = QComboBox()
        self._panel_side.addItem("Gauche", "left")
        self._panel_side.addItem("Droite", "right")
        idx = self._panel_side.findData(settings.panel_side or "left")
        self._panel_side.setCurrentIndex(max(idx, 0))
        mode_section.addRow("Côté du panneau", self._panel_side)

        self._safe_area = QSpinBox()
        self._safe_area.setRange(0, 15)
        self._safe_area.setSuffix(" %")
        self._safe_area.setValue(int(settings.safe_area_percent or 0))
        mode_section.addRow(
            "Zone de sécurité",
            self._safe_area,
            "Inset broadcast protégé, indépendant de la résolution OBS.",
        )

        self._background_dimmer = QSpinBox()
        self._background_dimmer.setRange(0, 85)
        self._background_dimmer.setSuffix(" %")
        self._background_dimmer.setValue(
            int(round(float(settings.background_dimmer or 0.0) * 100))
        )
        mode_section.addRow(
            "Assombrissement",
            self._background_dimmer,
            "Contraste du fond pour les compositions plein écran.",
        )

        layout.addWidget(mode_section)

        # Position section
        pos_section = SettingSection("Position", "move.svg")

        self._position_combo = QComboBox()
        self._position_combo.addItem("Bas de l'écran", "bottom")
        self._position_combo.addItem("Haut de l'écran", "top")
        self._position_combo.addItem("Centre", "center")
        idx = self._position_combo.findData(settings.position)
        if idx >= 0:
            self._position_combo.setCurrentIndex(idx)
        pos_section.addRow(
            "Position verticale", self._position_combo, "Où afficher le lower third"
        )

        self._align_combo = QComboBox()
        self._align_combo.addItem("Centré", "center")
        self._align_combo.addItem("Aligné à gauche", "left")
        self._align_combo.addItem("Aligné à droite", "right")
        idx = self._align_combo.findData(settings.align)
        if idx >= 0:
            self._align_combo.setCurrentIndex(idx)
        pos_section.addRow("Alignement du texte", self._align_combo)

        self._band_align_combo = QComboBox()
        self._band_align_combo.addItem("Centré", "center")
        self._band_align_combo.addItem("À gauche", "left")
        self._band_align_combo.addItem("À droite", "right")
        idx = self._band_align_combo.findData(settings.band_align)
        if idx >= 0:
            self._band_align_combo.setCurrentIndex(idx)
        pos_section.addRow(
            "Placement du bandeau",
            self._band_align_combo,
            "Position horizontale du bloc sur l'écran",
        )

        layout.addWidget(pos_section)

        # Fine position section (fully adjustable)
        fine_section = SettingSection("Position fine", "move.svg")

        self._offset_x = QSpinBox()
        self._offset_x.setRange(-960, 960)
        self._offset_x.setSuffix(" px")
        self._offset_x.setValue(settings.offset_x)
        fine_section.addRow(
            "Décalage horizontal", self._offset_x, "Négatif = vers la gauche"
        )

        self._offset_y = QSpinBox()
        self._offset_y.setRange(-540, 540)
        self._offset_y.setSuffix(" px")
        self._offset_y.setValue(settings.offset_y)
        fine_section.addRow(
            "Décalage vertical", self._offset_y, "Négatif = vers le haut"
        )

        self._edge_margin = QSpinBox()
        self._edge_margin.setRange(0, 300)
        self._edge_margin.setSuffix(" px")
        self._edge_margin.setValue(settings.edge_margin)
        fine_section.addRow(
            "Marge des bords", self._edge_margin, "Distance minimale avec les bords de l'écran"
        )

        layout.addWidget(fine_section)

        # Dimensions section
        dim_section = SettingSection("Dimensions", "maximize.svg")

        self._max_width = QSpinBox()
        self._max_width.setRange(50, 100)
        self._max_width.setSuffix(" %")
        self._max_width.setValue(settings.max_width)
        dim_section.addRow(
            "Largeur maximale", self._max_width, "Pourcentage de la largeur d'écran"
        )

        self._padding_h = QSpinBox()
        self._padding_h.setRange(0, 100)
        self._padding_h.setSuffix(" px")
        self._padding_h.setValue(settings.padding_horizontal)
        dim_section.addRow("Marge horizontale", self._padding_h)

        self._padding_v = QSpinBox()
        self._padding_v.setRange(0, 60)
        self._padding_v.setSuffix(" px")
        self._padding_v.setValue(settings.padding_vertical)
        dim_section.addRow("Marge verticale", self._padding_v)

        self._border_radius = QSpinBox()
        self._border_radius.setRange(0, 30)
        self._border_radius.setSuffix(" px")
        self._border_radius.setValue(settings.border_radius)
        dim_section.addRow("Coins arrondis", self._border_radius)

        self._uniform_text_size = QCheckBox(
            "Conserver la même taille de texte sur toutes les slides"
        )
        self._uniform_text_size.setChecked(bool(settings.uniform_text_size))
        dim_section.addWidget(self._uniform_text_size)

        self._auto_fit = QCheckBox(
            "Ajuster automatiquement seulement si le texte déborde"
        )
        self._auto_fit.setChecked(bool(settings.auto_fit))
        dim_section.addWidget(self._auto_fit)

        self._min_text_size = QSpinBox()
        self._min_text_size.setRange(12, 72)
        self._min_text_size.setSuffix(" px")
        self._min_text_size.setValue(int(settings.min_text_size or 24))
        dim_section.addRow("Taille minimale", self._min_text_size)

        self._max_lines = QSpinBox()
        self._max_lines.setRange(1, 12)
        self._max_lines.setValue(int(settings.max_lines or 6))
        dim_section.addRow(
            "Nombre de lignes max.",
            self._max_lines,
            "Le moteur réduit la police avant d'atteindre cette limite.",
        )

        self._reference_style = QComboBox()
        self._reference_style.addItem("Badge", "badge")
        self._reference_style.addItem("Texte simple", "plain")
        self._reference_style.addItem("En ligne", "inline")
        idx = self._reference_style.findData(settings.reference_style or "badge")
        self._reference_style.setCurrentIndex(max(idx, 0))
        dim_section.addRow("Style de référence", self._reference_style)

        layout.addWidget(dim_section)
        layout.addStretch()

        self._add_scroll_page(page)

    def _create_text_page(self, settings: ObsOutputSettings) -> None:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # Font section
        font_section = SettingSection("Police", "type.svg")

        self._font_combo = QComboBox()
        for display_name, css_name in get_available_fonts():
            self._font_combo.addItem(display_name, css_name)
        idx = self._font_combo.findData(settings.font_family)
        if idx < 0:
            idx = self._font_combo.findText(settings.font_family)
        if idx >= 0:
            self._font_combo.setCurrentIndex(idx)
        font_section.addRow("Famille de police", self._font_combo)

        self._font_weight = QComboBox()
        self._font_weight.addItem("Normal", "normal")
        self._font_weight.addItem("Gras", "bold")
        self._font_weight.addItem("Léger", "light")
        idx = self._font_weight.findData(settings.font_weight)
        if idx >= 0:
            self._font_weight.setCurrentIndex(idx)
        font_section.addRow("Épaisseur", self._font_weight)

        self._text_transform = QComboBox()
        self._text_transform.addItem("Normal", "none")
        self._text_transform.addItem("MAJUSCULES", "uppercase")
        self._text_transform.addItem("Capitalize", "capitalize")
        idx = self._text_transform.findData(settings.text_transform)
        if idx >= 0:
            self._text_transform.setCurrentIndex(idx)
        font_section.addRow(
            "Transformation", self._text_transform, "Modifier la casse du texte"
        )

        layout.addWidget(font_section)

        # Size section
        size_section = SettingSection("Tailles", "text.svg")

        self._text_size = QSpinBox()
        self._text_size.setRange(16, 120)
        self._text_size.setSuffix(" px")
        self._text_size.setValue(settings.text_size)
        size_section.addRow(
            "Taille du texte principal",
            self._text_size,
            "Taille appliquée directement; avec Auto-fit, elle devient la taille maximale.",
        )

        self._ref_size = QSpinBox()
        self._ref_size.setRange(10, 60)
        self._ref_size.setSuffix(" px")
        self._ref_size.setValue(settings.ref_size)
        size_section.addRow("Taille de la référence", self._ref_size)

        self._show_ref = QCheckBox(tr("show_bible_ref"))
        self._show_ref.setChecked(settings.show_reference)
        size_section.addWidget(self._show_ref)

        layout.addWidget(size_section)

        # Advanced section
        adv_section = SettingSection("Options avancées", "sliders.svg")

        self._letter_spacing = QSpinBox()
        self._letter_spacing.setRange(-5, 20)
        self._letter_spacing.setSuffix(" px")
        self._letter_spacing.setValue(settings.letter_spacing)
        adv_section.addRow("Espacement des lettres", self._letter_spacing)

        self._line_height = QDoubleSpinBox()
        self._line_height.setRange(1.0, 3.0)
        self._line_height.setSingleStep(0.1)
        self._line_height.setValue(settings.line_height)
        adv_section.addRow("Hauteur de ligne", self._line_height)

        layout.addWidget(adv_section)
        layout.addStretch()

        self._add_scroll_page(page)

    def _create_colors_page(self, settings: ObsOutputSettings) -> None:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # ── Background section ──────────────────────────────────────────
        bg_section = SettingSection("Arrière-plan", "monitor.svg")

        self._bg_enabled = QCheckBox(tr("show_background"))
        self._bg_enabled.setChecked(settings.bg_enabled)
        bg_section.addWidget(self._bg_enabled)

        self._bg_color_btn = ColorPickerButton(settings.bg_color)
        bg_section.addRow(
            "Couleur principale",
            self._bg_color_btn,
            "Couleur de fond (ou première couleur du dégradé)",
        )

        # Gradient controls
        self._bg_gradient_enabled = QCheckBox("Activer le dégradé (Gradient)")
        self._bg_gradient_enabled.setChecked(settings.bg_gradient_enabled)
        bg_section.addWidget(self._bg_gradient_enabled)

        self._bg_color_2_btn = ColorPickerButton(settings.bg_color_2)
        bg_section.addRow(
            "Couleur secondaire", self._bg_color_2_btn, "Deuxième couleur du dégradé"
        )

        self._bg_gradient_angle = QSpinBox()
        self._bg_gradient_angle.setRange(0, 360)
        self._bg_gradient_angle.setSuffix(" °")
        self._bg_gradient_angle.setValue(settings.bg_gradient_angle)
        bg_section.addRow("Angle du dégradé", self._bg_gradient_angle)

        self._bg_opacity = QSlider(Qt.Orientation.Horizontal)
        self._bg_opacity.setRange(0, 100)
        self._bg_opacity.setValue(int(settings.bg_opacity * 100))
        self._bg_opacity.setMinimumWidth(240)
        self._bg_opacity.setStyleSheet(f"""
            QSlider {{
                min-height: 24px;
            }}
            QSlider::groove:horizontal {{
                height: 6px;
                background: {Colors.BG_ELEVATED};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                width: 20px; height: 20px;
                margin: -7px 0;
                background: {Colors.ACCENT_PRIMARY};
                border: 2px solid #fff;
                border-radius: 10px;
            }}
            QSlider::sub-page:horizontal {{
                background: {Colors.ACCENT_PRIMARY};
                border-radius: 3px;
            }}
        """)
        self._bg_opacity_label = QLabel(f"{int(settings.bg_opacity * 100)} %")
        self._bg_opacity_label.setFixedWidth(44)
        self._bg_opacity_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._bg_opacity_label.setStyleSheet(
            f"font-size: {Typography.SIZE_NUMBER}px; color: {Colors.TEXT_SECONDARY}; border: none;"
        )
        opacity_row = QWidget()
        opacity_row.setStyleSheet("background: transparent;")
        opacity_hl = QHBoxLayout(opacity_row)
        opacity_hl.setContentsMargins(0, 0, 0, 0)
        opacity_hl.setSpacing(8)
        opacity_hl.addWidget(self._bg_opacity)
        opacity_hl.addWidget(self._bg_opacity_label)
        self._bg_opacity.valueChanged.connect(
            lambda v: self._bg_opacity_label.setText(f"{v} %")
        )
        bg_section.addRow("Opacité", opacity_row, "Transparence de l'arrière-plan")

        self._bg_blur = QCheckBox("Effet verre (Glass / Blur)")
        self._bg_blur.setChecked(settings.bg_blur)
        bg_section.addWidget(self._bg_blur)

        self._bg_blur_amount = QSpinBox()
        self._bg_blur_amount.setRange(2, 30)
        self._bg_blur_amount.setSuffix(" px")
        self._bg_blur_amount.setValue(settings.bg_blur_amount)
        bg_section.addRow("Intensité du flou", self._bg_blur_amount)

        # Wire toggle: disable controls when background is off
        def _on_bg_toggled(checked: bool) -> None:
            self._bg_color_btn.setEnabled(checked)
            self._bg_gradient_enabled.setEnabled(checked)
            self._bg_color_2_btn.setEnabled(
                checked and self._bg_gradient_enabled.isChecked()
            )
            self._bg_gradient_angle.setEnabled(
                checked and self._bg_gradient_enabled.isChecked()
            )
            self._bg_opacity.setEnabled(checked)
            self._bg_blur.setEnabled(checked)
            self._bg_blur_amount.setEnabled(checked)

        self._bg_enabled.toggled.connect(_on_bg_toggled)
        self._bg_gradient_enabled.toggled.connect(
            lambda: _on_bg_toggled(self._bg_enabled.isChecked())
        )
        _on_bg_toggled(settings.bg_enabled)

        layout.addWidget(bg_section)

        # ── Text colors section ─────────────────────────────────────────
        color_section = SettingSection("Couleurs du texte", "palette.svg")

        self._text_color_btn = ColorPickerButton(settings.text_color)
        color_section.addRow("Texte principal", self._text_color_btn)

        self._ref_color_btn = ColorPickerButton(settings.ref_color)
        color_section.addRow("Référence biblique", self._ref_color_btn)

        # Overall Opacity
        self._overall_opacity = QSlider(Qt.Orientation.Horizontal)
        self._overall_opacity.setRange(0, 100)
        self._overall_opacity.setValue(int(settings.opacity * 100))
        self._overall_opacity.setMinimumWidth(240)
        self._overall_opacity.setStyleSheet(
            self._bg_opacity.styleSheet()
        )  # Reuse style

        self._overall_opacity_label = QLabel(f"{int(settings.opacity * 100)} %")
        self._overall_opacity_label.setFixedWidth(44)
        self._overall_opacity_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._overall_opacity_label.setStyleSheet(self._bg_opacity_label.styleSheet())

        opacity_row = QWidget()
        opacity_row.setStyleSheet("background: transparent;")
        opacity_hl = QHBoxLayout(opacity_row)
        opacity_hl.setContentsMargins(0, 0, 0, 0)
        opacity_hl.setSpacing(8)
        opacity_hl.addWidget(self._overall_opacity)
        opacity_hl.addWidget(self._overall_opacity_label)
        self._overall_opacity.valueChanged.connect(
            lambda v: self._overall_opacity_label.setText(f"{v} %")
        )

        color_section.addRow(
            "Opacité globale", opacity_row, "Transparence totale de la projection"
        )

        layout.addWidget(color_section)

        # ── Branding / decorations ──────────────────────────────────────
        deco_section = SettingSection("Habillage", "sparkles.svg")

        self._show_kicker = QCheckBox("Afficher le badge de source (Bible, Cantique…)")
        self._show_kicker.setChecked(settings.show_kicker)
        deco_section.addWidget(self._show_kicker)

        self._show_accent_bar = QCheckBox("Afficher la barre d'accent colorée")
        self._show_accent_bar.setChecked(settings.show_accent_bar)
        deco_section.addWidget(self._show_accent_bar)

        self._accent_mode = QComboBox()
        self._accent_mode.addItem("Automatique (couleur par source)", "auto")
        self._accent_mode.addItem("Personnalisée", "custom")
        idx = self._accent_mode.findData(settings.accent_mode)
        if idx >= 0:
            self._accent_mode.setCurrentIndex(idx)
        deco_section.addRow(
            "Couleur d'accent",
            self._accent_mode,
            "Automatique : vert Bible, violet Cantique, or Prédication…",
        )

        self._accent_color_btn = ColorPickerButton(settings.accent_color)
        deco_section.addRow("Accent personnalisé", self._accent_color_btn)

        def _on_accent_mode_changed(*_args) -> None:
            self._accent_color_btn.setEnabled(
                str(self._accent_mode.currentData() or "auto") == "custom"
            )

        self._accent_mode.currentIndexChanged.connect(_on_accent_mode_changed)
        _on_accent_mode_changed()

        layout.addWidget(deco_section)
        layout.addStretch()

        self._add_scroll_page(page)

    def _create_effects_page(self, settings: ObsOutputSettings) -> None:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # Shadow section
        shadow_section = SettingSection("Ombre du texte", "sun.svg")

        self._text_shadow = QCheckBox("Activer l'ombre portée")
        self._text_shadow.setChecked(settings.text_shadow)
        shadow_section.addWidget(self._text_shadow)

        self._shadow_color_btn = ColorPickerButton(settings.shadow_color)
        shadow_section.addRow("Couleur de l'ombre", self._shadow_color_btn)

        self._shadow_blur = QSpinBox()
        self._shadow_blur.setRange(0, 20)
        self._shadow_blur.setSuffix(" px")
        self._shadow_blur.setValue(settings.shadow_blur)
        shadow_section.addRow("Flou de l'ombre", self._shadow_blur)

        layout.addWidget(shadow_section)

        # Stroke section
        stroke_section = SettingSection("Contour du texte", "circle.svg")

        self._text_stroke = QCheckBox("Activer le contour")
        self._text_stroke.setChecked(settings.text_stroke)
        stroke_section.addWidget(self._text_stroke)

        self._stroke_color_btn = ColorPickerButton(settings.stroke_color)
        stroke_section.addRow("Couleur du contour", self._stroke_color_btn)

        self._stroke_width = QSpinBox()
        self._stroke_width.setRange(1, 5)
        self._stroke_width.setSuffix(" px")
        self._stroke_width.setValue(settings.stroke_width)
        stroke_section.addRow("Épaisseur du contour", self._stroke_width)

        layout.addWidget(stroke_section)

        transition_section = SettingSection("Transitions de slide", "sparkles.svg")

        self._animation_enabled = QCheckBox("Activer les transitions")
        self._animation_enabled.setChecked(settings.animation_enabled)
        transition_section.addWidget(self._animation_enabled)

        self._animation_type = QComboBox()
        self._animation_type.addItem("Auto par source", "auto")
        self._animation_type.addItem("Aucune", "none")
        self._animation_type.addItem("Fondu", "fade")
        self._animation_type.addItem("Glissement", "slide")
        self._animation_type.addItem("Zoom doux", "scale")
        self._animation_type.addItem("Blur broadcast", "blur")
        self._animation_type.addItem("Reveal cinématique", "reveal")
        idx = self._animation_type.findData(settings.animation_type)
        if idx >= 0:
            self._animation_type.setCurrentIndex(idx)
        transition_section.addRow(
            "Style de transition",
            self._animation_type,
            "Animation appliquée lors du changement de slide",
        )

        self._animation_style = QComboBox()
        self._animation_style.addItem("Bloc (tout le texte)", "block")
        self._animation_style.addItem("Mot à mot (broadcast)", "words")
        idx = self._animation_style.findData(settings.animation_style)
        if idx >= 0:
            self._animation_style.setCurrentIndex(idx)
        transition_section.addRow(
            "Révélation du texte",
            self._animation_style,
            "Mot à mot : les mots apparaissent en cascade, style habillage TV",
        )

        self._animation_direction = QComboBox()
        self._animation_direction.addItem("Vers le haut", "up")
        self._animation_direction.addItem("Vers le bas", "down")
        self._animation_direction.addItem("Vers la gauche", "left")
        self._animation_direction.addItem("Vers la droite", "right")
        idx = self._animation_direction.findData(settings.animation_direction)
        if idx >= 0:
            self._animation_direction.setCurrentIndex(idx)
        transition_section.addRow(
            "Direction",
            self._animation_direction,
            "Utilisé pour les transitions de glissement et reveal",
        )

        self._animation_duration = QSpinBox()
        self._animation_duration.setRange(0, 2000)
        self._animation_duration.setSingleStep(50)
        self._animation_duration.setSuffix(" ms")
        self._animation_duration.setValue(settings.animation_duration)
        transition_section.addRow(
            "Durée",
            self._animation_duration,
            "520 ms donne un rendu fluide et professionnel",
        )

        def _update_transition_controls(*_args) -> None:
            enabled = self._animation_enabled.isChecked()
            anim_type = str(self._animation_type.currentData() or "fade")
            allow_direction = enabled and anim_type in ("slide", "reveal")
            self._animation_type.setEnabled(enabled)
            self._animation_duration.setEnabled(enabled)
            self._animation_direction.setEnabled(allow_direction)
            self._animation_style.setEnabled(enabled)

        self._animation_enabled.toggled.connect(_update_transition_controls)
        self._animation_type.currentIndexChanged.connect(_update_transition_controls)
        _update_transition_controls()

        layout.addWidget(transition_section)
        layout.addStretch()

        self._add_scroll_page(page)

    def _reset_defaults(self) -> None:
        """Reset all fields to default values."""
        self._apply_settings_to_widgets(ObsOutputSettings())

    def _apply_settings_to_widgets(self, values: ObsOutputSettings) -> None:
        """Populate every widget from an output style (base or scene)."""
        self._initializing = True  # Block signals during repopulation
        # Position & Layout
        self._layout_mode.setCurrentIndex(
            self._layout_mode.findData(values.layout_mode)
        )
        self._panel_side.setCurrentIndex(
            self._panel_side.findData(values.panel_side)
        )
        self._safe_area.setValue(values.safe_area_percent)
        self._background_dimmer.setValue(
            int(round(values.background_dimmer * 100))
        )
        self._position_combo.setCurrentIndex(
            self._position_combo.findData(values.position)
        )
        self._align_combo.setCurrentIndex(self._align_combo.findData(values.align))
        self._band_align_combo.setCurrentIndex(
            self._band_align_combo.findData(values.band_align)
        )
        self._offset_x.setValue(values.offset_x)
        self._offset_y.setValue(values.offset_y)
        self._edge_margin.setValue(values.edge_margin)
        self._show_kicker.setChecked(values.show_kicker)
        self._show_accent_bar.setChecked(values.show_accent_bar)
        self._accent_mode.setCurrentIndex(
            self._accent_mode.findData(values.accent_mode)
        )
        self._accent_color_btn.set_color(values.accent_color)
        self._max_width.setValue(values.max_width)
        self._padding_h.setValue(values.padding_horizontal)
        self._padding_v.setValue(values.padding_vertical)
        self._border_radius.setValue(values.border_radius)
        self._uniform_text_size.setChecked(values.uniform_text_size)
        self._auto_fit.setChecked(values.auto_fit)
        self._min_text_size.setValue(values.min_text_size)
        self._max_lines.setValue(values.max_lines)
        self._reference_style.setCurrentIndex(
            self._reference_style.findData(values.reference_style)
        )
        # Text
        idx = self._font_combo.findData(values.font_family)
        if idx >= 0:
            self._font_combo.setCurrentIndex(idx)
        self._font_weight.setCurrentIndex(
            self._font_weight.findData(values.font_weight)
        )
        self._text_size.setValue(values.text_size)
        self._ref_size.setValue(values.ref_size)
        self._show_ref.setChecked(values.show_reference)
        self._letter_spacing.setValue(values.letter_spacing)
        self._line_height.setValue(values.line_height)
        # Colors & Background
        self._bg_enabled.setChecked(values.bg_enabled)
        self._bg_color_btn.set_color(values.bg_color)
        self._bg_gradient_enabled.setChecked(values.bg_gradient_enabled)
        self._bg_color_2_btn.set_color(values.bg_color_2)
        self._bg_gradient_angle.setValue(values.bg_gradient_angle)
        self._bg_opacity.setValue(int(values.bg_opacity * 100))
        self._bg_blur.setChecked(values.bg_blur)
        self._bg_blur_amount.setValue(values.bg_blur_amount)
        self._text_color_btn.set_color(values.text_color)
        self._ref_color_btn.set_color(values.ref_color)
        self._overall_opacity.setValue(int(values.opacity * 100))
        # Effects
        self._text_shadow.setChecked(values.text_shadow)
        self._shadow_color_btn.set_color(values.shadow_color)
        self._shadow_blur.setValue(values.shadow_blur)
        self._text_stroke.setChecked(values.text_stroke)
        self._stroke_color_btn.set_color(values.stroke_color)
        self._stroke_width.setValue(values.stroke_width)
        self._animation_enabled.setChecked(values.animation_enabled)
        self._animation_type.setCurrentIndex(
            self._animation_type.findData(values.animation_type)
        )
        self._animation_style.setCurrentIndex(
            self._animation_style.findData(values.animation_style)
        )
        self._animation_direction.setCurrentIndex(
            self._animation_direction.findData(values.animation_direction)
        )
        self._animation_duration.setValue(values.animation_duration)
        # Professional
        self._text_transform.setCurrentIndex(
            self._text_transform.findData(values.text_transform)
        )
        # Refresh dependent enablement (mirrors _update_transition_controls)
        anim_enabled = self._animation_enabled.isChecked()
        anim_type = str(self._animation_type.currentData() or "fade")
        self._animation_type.setEnabled(anim_enabled)
        self._animation_duration.setEnabled(anim_enabled)
        self._animation_style.setEnabled(anim_enabled)
        self._animation_direction.setEnabled(
            anim_enabled and anim_type in ("slide", "reveal")
        )
        self._initializing = False
        self._on_change()

    def get_settings(self) -> ObsOutputSettings:
        # Robust data retrieval with fallbacks
        try:
            font = self._font_combo.currentData() or self._font_combo.currentText()
        except Exception:
            font = "Google Sans"
        out = self._active_output()
        out.layout_mode = self._layout_mode.currentData() or "lower_third"
        out.font_family = str(font).strip() or "Google Sans"
        out.text_size = self._text_size.value()
        out.ref_size = self._ref_size.value()
        out.align = self._align_combo.currentData() or "center"
        out.show_reference = self._show_ref.isChecked()
        out.position = self._position_combo.currentData() or "bottom"
        out.band_align = self._band_align_combo.currentData() or "center"
        out.offset_x = self._offset_x.value()
        out.offset_y = self._offset_y.value()
        out.edge_margin = self._edge_margin.value()
        out.safe_area_percent = self._safe_area.value()
        out.panel_side = self._panel_side.currentData() or "left"
        out.show_kicker = self._show_kicker.isChecked()
        out.show_accent_bar = self._show_accent_bar.isChecked()
        out.accent_mode = self._accent_mode.currentData() or "auto"
        out.accent_color = self._accent_color_btn.color()
        out.bg_enabled = self._bg_enabled.isChecked()
        out.bg_color = self._bg_color_btn.color()
        out.bg_gradient_enabled = self._bg_gradient_enabled.isChecked()
        out.bg_color_2 = self._bg_color_2_btn.color()
        out.bg_gradient_angle = self._bg_gradient_angle.value()
        out.bg_opacity = self._bg_opacity.value() / 100.0
        out.text_color = self._text_color_btn.color()
        out.ref_color = self._ref_color_btn.color()
        out.opacity = self._overall_opacity.value() / 100.0
        # Professional styling
        out.text_shadow = self._text_shadow.isChecked()
        out.shadow_color = self._shadow_color_btn.color()
        out.shadow_blur = self._shadow_blur.value()
        out.text_stroke = self._text_stroke.isChecked()
        out.stroke_color = self._stroke_color_btn.color()
        out.stroke_width = self._stroke_width.value()
        out.letter_spacing = self._letter_spacing.value()
        out.line_height = self._line_height.value()
        out.padding_horizontal = self._padding_h.value()
        out.padding_vertical = self._padding_v.value()
        out.max_width = self._max_width.value()
        out.auto_fit = self._auto_fit.isChecked()
        out.uniform_text_size = self._uniform_text_size.isChecked()
        out.min_text_size = self._min_text_size.value()
        out.max_lines = self._max_lines.value()
        out.reference_style = self._reference_style.currentData() or "badge"
        out.background_dimmer = self._background_dimmer.value() / 100.0
        out.border_radius = self._border_radius.value()
        out.animation_enabled = self._animation_enabled.isChecked()
        out.animation_type = self._animation_type.currentData() or "blur"
        out.animation_direction = self._animation_direction.currentData() or "up"
        out.animation_style = self._animation_style.currentData() or "block"
        out.animation_duration = self._animation_duration.value()
        out.font_weight = self._font_weight.currentData() or "normal"
        out.text_transform = self._text_transform.currentData() or "none"
        out.bg_blur = self._bg_blur.isChecked()
        out.bg_blur_amount = self._bg_blur_amount.value()
        # Preserved from the incoming settings (edited elsewhere)
        out.bg_mode = self._bg_mode
        out.bg_image = self._bg_image
        out.bg_image_fit = self._bg_image_fit
        return out

    def get_obs_settings(self) -> ObsSettings:
        """Full OBS settings including any edits made to the active style."""
        self.get_settings()  # commit widget values
        return self._obs_settings

    def _create_preset_buttons(self, layout: QVBoxLayout):
        """Create a grid of preset style buttons."""
        presets = [
            (
                "Lower Third TV",
                {
                    "layout_mode": "lower_third",
                    "safe_area_percent": 5,
                    "position": "bottom",
                    "band_align": "center",
                    "align": "center",
                    "max_width": 78,
                    "text_size": 46,
                    "ref_size": 18,
                    "padding_horizontal": 48,
                    "padding_vertical": 24,
                    "max_lines": 4,
                    "reference_style": "badge",
                    "border_radius": 22,
                    "show_kicker": True,
                    "show_accent_bar": True,
                    "bg_color": "rgba(7, 12, 22, 0.90)",
                    "bg_color_2": "rgba(2, 6, 14, 0.92)",
                    "bg_gradient_enabled": True,
                    "text_color": "rgba(255, 255, 255, 0.97)",
                    "text_transform": "none",
                    "animation_type": "auto",
                    "animation_style": "words",
                },
            ),
            (
                "Verset plein écran",
                {
                    "layout_mode": "fullscreen",
                    "safe_area_percent": 7,
                    "position": "center",
                    "band_align": "center",
                    "align": "center",
                    "max_width": 100,
                    "text_size": 64,
                    "ref_size": 22,
                    "padding_horizontal": 92,
                    "padding_vertical": 54,
                    "min_text_size": 30,
                    "max_lines": 7,
                    "reference_style": "plain",
                    "background_dimmer": 0.44,
                    "border_radius": 0,
                    "show_kicker": True,
                    "show_accent_bar": True,
                    "bg_color": "rgba(5, 12, 24, 0.78)",
                    "bg_color_2": "rgba(2, 7, 16, 0.92)",
                    "bg_gradient_enabled": True,
                    "text_color": "rgba(255, 255, 255, 0.98)",
                    "text_transform": "none",
                    "animation_type": "reveal",
                },
            ),
            (
                "Panneau sermon",
                {
                    "layout_mode": "side_panel",
                    "panel_side": "left",
                    "safe_area_percent": 5,
                    "position": "center",
                    "band_align": "left",
                    "align": "left",
                    "max_width": 44,
                    "text_size": 40,
                    "ref_size": 18,
                    "padding_horizontal": 44,
                    "padding_vertical": 38,
                    "min_text_size": 22,
                    "max_lines": 9,
                    "reference_style": "badge",
                    "border_radius": 26,
                    "show_kicker": True,
                    "show_accent_bar": True,
                    "bg_color": "rgba(8, 18, 34, 0.88)",
                    "bg_color_2": "rgba(3, 8, 18, 0.94)",
                    "bg_gradient_enabled": True,
                    "text_color": "rgba(255, 255, 255, 0.97)",
                    "text_transform": "none",
                    "animation_type": "slide",
                },
            ),
            (
                "Sous-titres live",
                {
                    "layout_mode": "subtitle",
                    "safe_area_percent": 4,
                    "position": "bottom",
                    "band_align": "center",
                    "align": "center",
                    "max_width": 92,
                    "text_size": 34,
                    "ref_size": 15,
                    "padding_horizontal": 42,
                    "padding_vertical": 18,
                    "min_text_size": 22,
                    "max_lines": 3,
                    "reference_style": "inline",
                    "border_radius": 18,
                    "show_kicker": False,
                    "show_accent_bar": True,
                    "bg_color": "rgba(5, 9, 16, 0.88)",
                    "bg_color_2": "rgba(12, 20, 34, 0.88)",
                    "bg_gradient_enabled": True,
                    "text_color": "rgba(255, 255, 255, 0.98)",
                    "text_transform": "none",
                    "animation_type": "fade",
                },
            ),
            (
                "Carte focus",
                {
                    "layout_mode": "focus_card",
                    "safe_area_percent": 6,
                    "position": "center",
                    "band_align": "center",
                    "align": "center",
                    "max_width": 68,
                    "text_size": 52,
                    "ref_size": 19,
                    "padding_horizontal": 64,
                    "padding_vertical": 46,
                    "min_text_size": 26,
                    "max_lines": 7,
                    "reference_style": "badge",
                    "background_dimmer": 0.38,
                    "border_radius": 28,
                    "show_kicker": True,
                    "show_accent_bar": True,
                    "bg_color": "rgba(11, 18, 31, 0.86)",
                    "bg_color_2": "rgba(3, 8, 18, 0.94)",
                    "bg_gradient_enabled": True,
                    "text_color": "rgba(255, 255, 255, 0.98)",
                    "text_transform": "none",
                    "animation_type": "scale",
                },
            ),
            (
                "Sans fond",
                {
                    "bg_enabled": False,
                    "text_shadow": True,
                    "shadow_blur": 14,
                    "text_color": "rgba(255, 255, 255, 0.96)",
                },
            ),
            (
                "Église — Culte",
                {
                    "bg_enabled": True,
                    "bg_color": "rgba(8, 14, 26, 0.88)",
                    "bg_color_2": "rgba(3, 7, 15, 0.92)",
                    "bg_gradient_enabled": True,
                    "text_color": "rgba(255, 255, 255, 0.97)",
                    "text_shadow": True,
                    "shadow_blur": 12,
                    "show_kicker": True,
                    "show_accent_bar": True,
                    "accent_mode": "auto",
                    "position": "bottom",
                    "band_align": "center",
                    "max_width": 78,
                    "font_weight": "bold",
                    "text_transform": "none",
                },
            ),
            (
                "Sainte-Cène — Discret",
                {
                    "bg_enabled": True,
                    "bg_color": "rgba(26, 16, 12, 0.55)",
                    "bg_color_2": "rgba(12, 8, 6, 0.65)",
                    "bg_gradient_enabled": True,
                    "bg_opacity": 0.55,
                    "bg_blur": True,
                    "text_color": "rgba(255, 246, 232, 0.94)",
                    "text_shadow": True,
                    "shadow_blur": 10,
                    "show_kicker": False,
                    "show_accent_bar": False,
                    "accent_mode": "custom",
                    "accent_color": "rgba(201, 168, 76, 1.00)",
                    "position": "bottom",
                    "band_align": "center",
                    "max_width": 60,
                    "text_size": 40,
                    "font_weight": "normal",
                    "text_transform": "none",
                },
            ),
            (
                "Louange — Impact",
                {
                    "bg_enabled": True,
                    "bg_color": "rgba(24, 14, 44, 0.82)",
                    "bg_color_2": "rgba(8, 5, 20, 0.92)",
                    "bg_gradient_enabled": True,
                    "bg_opacity": 0.85,
                    "text_color": "rgba(255, 255, 255, 0.98)",
                    "text_shadow": True,
                    "shadow_blur": 16,
                    "show_kicker": True,
                    "show_accent_bar": True,
                    "accent_mode": "auto",
                    "position": "bottom",
                    "band_align": "center",
                    "max_width": 88,
                    "text_size": 56,
                    "font_weight": "bold",
                    "text_transform": "uppercase",
                    "animation_style": "words",
                },
            ),
        ]

        grid = QVBoxLayout()
        grid.setSpacing(6)

        for name, params in presets:
            btn = QPushButton(name)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {Colors.BG_ELEVATED};
                    border: 1px solid {Colors.BORDER_DEFAULT};
                    border-radius: 6px;
                    padding: 8px;
                    color: {Colors.TEXT_SECONDARY};
                    font-size: {Typography.SIZE_CONTROL}px;
                }}
                QPushButton:hover {{
                    background: {Colors.SURFACE_HOVER};
                    border: 1px solid {Colors.ACCENT_PRIMARY};
                    color: {Colors.TEXT_PRIMARY};
                }}
            """)
            btn.clicked.connect(lambda checked, p=params: self._apply_preset(p))
            grid.addWidget(btn)

        layout.addLayout(grid)

    def _apply_preset(self, params: dict):
        """Apply a set of parameters to the UI."""
        self._initializing = True  # Block signals temporarily
        for key, combo in (
            ("layout_mode", self._layout_mode),
            ("panel_side", self._panel_side),
            ("position", self._position_combo),
            ("band_align", self._band_align_combo),
            ("align", self._align_combo),
            ("reference_style", self._reference_style),
            ("animation_type", self._animation_type),
            ("animation_style", self._animation_style),
        ):
            if key in params:
                idx = combo.findData(params[key])
                if idx >= 0:
                    combo.setCurrentIndex(idx)
        for key, spin in (
            ("safe_area_percent", self._safe_area),
            ("max_width", self._max_width),
            ("text_size", self._text_size),
            ("ref_size", self._ref_size),
            ("padding_horizontal", self._padding_h),
            ("padding_vertical", self._padding_v),
            ("min_text_size", self._min_text_size),
            ("max_lines", self._max_lines),
            ("border_radius", self._border_radius),
        ):
            if key in params:
                spin.setValue(int(params[key]))
        if "background_dimmer" in params:
            self._background_dimmer.setValue(
                int(round(float(params["background_dimmer"]) * 100))
            )
        if "bg_enabled" in params:
            self._bg_enabled.setChecked(bool(params["bg_enabled"]))
        if "bg_color" in params:
            self._bg_color_btn.set_color(params["bg_color"])
        if "bg_color_2" in params:
            self._bg_color_2_btn.set_color(params["bg_color_2"])
        if "bg_gradient_enabled" in params:
            self._bg_gradient_enabled.setChecked(params["bg_gradient_enabled"])
        if "text_color" in params:
            self._text_color_btn.set_color(params["text_color"])
        if "text_shadow" in params:
            self._text_shadow.setChecked(bool(params["text_shadow"]))
        if "shadow_blur" in params:
            self._shadow_blur.setValue(int(params["shadow_blur"]))
        if "bg_opacity" in params:
            self._bg_opacity.setValue(int(float(params["bg_opacity"]) * 100))
        if "bg_blur" in params:
            self._bg_blur.setChecked(bool(params["bg_blur"]))
        if "show_kicker" in params:
            self._show_kicker.setChecked(bool(params["show_kicker"]))
        if "show_accent_bar" in params:
            self._show_accent_bar.setChecked(bool(params["show_accent_bar"]))
        if "accent_mode" in params:
            idx = self._accent_mode.findData(params["accent_mode"])
            if idx >= 0:
                self._accent_mode.setCurrentIndex(idx)
        if "accent_color" in params:
            self._accent_color_btn.set_color(params["accent_color"])
        if "font_weight" in params:
            idx = self._font_weight.findData(params["font_weight"])
            if idx >= 0:
                self._font_weight.setCurrentIndex(idx)
        if "text_transform" in params:
            idx = self._text_transform.findData(params["text_transform"])
            if idx >= 0:
                self._text_transform.setCurrentIndex(idx)
        self._initializing = False
        self._on_change()

    @classmethod
    def edit(
        cls, obs_settings: ObsSettings, parent: QWidget | None = None
    ) -> ObsSettings | None:
        dialog = cls(obs_settings, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.get_obs_settings()
        return None
