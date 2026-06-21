from __future__ import annotations

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
    QLabel,
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
from app.utils.settings import ObsOutputSettings
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

        # Apply global opacity
        painter.setOpacity(self._settings.opacity)

        # Scale factor (preview is smaller than actual 1080p)
        rect = self.contentsRect()
        W, H = rect.width(), rect.height()

        # 1. Background (if enabled)
        if self._settings.bg_enabled:
            # Layout
            p_h = self._settings.padding_horizontal // 2
            p_v = self._settings.padding_vertical // 2
            radius = self._settings.border_radius // 2

            # Text bounding box (simulated)
            text_rect = QRect(40, H - 100, W - 80, 60)  # Simulated position

            # Gradient or Solid - Use bg_opacity
            bg_color = self._parse_color(
                self._settings.bg_color, self._settings.bg_opacity
            )
            if self._settings.bg_gradient_enabled:
                bg_color_2 = self._parse_color(
                    self._settings.bg_color_2, self._settings.bg_opacity
                )
                # Quick approximation of angle
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
            painter.drawRoundedRect(
                text_rect.adjusted(-p_h, -p_v, p_h, p_v), radius, radius
            )

        # 2. Text (Simulated)
        text_color = self._parse_color(self._settings.text_color)
        painter.setPen(QPen(text_color))
        # Saturate font size to at least 1px to avoid QFont::setPointSize: Point size <= 0 (-1)
        font_size = max(4, int(self._settings.text_size // 4))
        font = QFont(self._settings.font_family or Typography.FAMILY)
        font.setPointSize(max(1, int(font_size * 0.75)))
        if self._settings.font_weight == "bold":
            font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            QRect(0, 0, W, H),
            Qt.AlignmentFlag.AlignCenter,
            "Ceci est un aperçu\n(Texte de démonstration)",
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
        font-size: 13px;
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
        font-size: 13px;
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
        font-size: 13px;
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
            f"font-size: 14px; font-weight: 500; color: {Colors.TEXT_PRIMARY}; border: none;"
        )
        label_col.addWidget(lbl)

        if description:
            desc = QLabel(description)
            desc.setStyleSheet(
                f"font-size: 12px; color: {Colors.TEXT_SECONDARY}; border: none;"
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
            f"font-size: 15px; font-weight: 600; color: {Colors.ACCENT_LIGHT}; background: transparent; border: none;"
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
                    font-size: 14px;
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
                    font-size: 14px;
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

    def __init__(
        self, settings: ObsOutputSettings, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("obs_lower_third_title"))
        self.setMinimumSize(820, 600)
        self.resize(900, 680)
        self.setStyleSheet(DIALOG_STYLE)
        
        self._initializing = True  # Block signals during creation
        self._settings = settings
        self._nav_buttons = []

        # Background type/image/fit are chosen in the Projection settings dialog
        # (and mirrored onto the OBS output). This dialog does not edit them, so
        # carry them through verbatim — otherwise editing any field here would
        # reset them to defaults and the OBS overlay would drop the background
        # image and revert to the coloured gradient.
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

        title = QLabel("OBS Settings")
        title.setStyleSheet(
            f"font-size: 17px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; background: transparent;"
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
                font-size: 12px;
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
            f"font-size: 14px; font-weight: 600; color: {Colors.ACCENT_LIGHT};"
        )
        preview_layout.addWidget(preview_hdr)

        self._preview_widget = ObsPreviewWidget(settings)
        preview_layout.addWidget(self._preview_widget)

        preview_help = QLabel(
            "L'aperçu simule l'apparence sur OBS. Certains effets (flou, ombres avancées) peuvent varier légèrement."
        )
        preview_help.setWordWrap(True)
        preview_help.setStyleSheet(f"font-size: 11px; color: {Colors.TEXT_MUTED};")
        preview_layout.addWidget(preview_help)

        # Presets section in preview
        preview_layout.addSpacing(20)
        preset_hdr = QLabel("Préréglages (Styles)")
        preset_hdr.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {Colors.TEXT_SECONDARY};"
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
                font-size: 13px;
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
                font-size: 13px;
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

    def _add_scroll_page(self, widget: QWidget) -> int:
        """Helper to wrap a page in a scroll area before adding to stack."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet(get_scroll_area_style())
        scroll.setWidget(widget)
        return self._stack.addWidget(scroll)

    def _on_change(self, *_args) -> None:
        """Trigger debounced settings changed signal."""
        if getattr(self, "_initializing", True):
            return
            
        try:
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
        idx = self._align_combo.findData(settings.align)
        if idx >= 0:
            self._align_combo.setCurrentIndex(idx)
        pos_section.addRow("Alignement horizontal", self._align_combo)

        layout.addWidget(pos_section)

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
        size_section.addRow("Taille du texte", self._text_size)

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
            f"font-size: 13px; color: {Colors.TEXT_SECONDARY}; border: none;"
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

        self._animation_enabled.toggled.connect(_update_transition_controls)
        self._animation_type.currentIndexChanged.connect(_update_transition_controls)
        _update_transition_controls()

        layout.addWidget(transition_section)
        layout.addStretch()

        self._add_scroll_page(page)

    def _reset_defaults(self) -> None:
        """Reset all fields to default values."""
        defaults = ObsOutputSettings()
        # Position & Layout
        self._position_combo.setCurrentIndex(
            self._position_combo.findData(defaults.position)
        )
        self._align_combo.setCurrentIndex(self._align_combo.findData(defaults.align))
        self._max_width.setValue(defaults.max_width)
        self._padding_h.setValue(defaults.padding_horizontal)
        self._padding_v.setValue(defaults.padding_vertical)
        self._border_radius.setValue(defaults.border_radius)
        # Text
        idx = self._font_combo.findData(defaults.font_family)
        if idx >= 0:
            self._font_combo.setCurrentIndex(idx)
        self._font_weight.setCurrentIndex(
            self._font_weight.findData(defaults.font_weight)
        )
        self._text_size.setValue(defaults.text_size)
        self._ref_size.setValue(defaults.ref_size)
        self._show_ref.setChecked(defaults.show_reference)
        self._letter_spacing.setValue(defaults.letter_spacing)
        self._line_height.setValue(defaults.line_height)
        # Colors & Background
        self._bg_enabled.setChecked(defaults.bg_enabled)
        self._bg_color_btn.set_color(defaults.bg_color)
        self._bg_gradient_enabled.setChecked(defaults.bg_gradient_enabled)
        self._bg_color_2_btn.set_color(defaults.bg_color_2)
        self._bg_gradient_angle.setValue(defaults.bg_gradient_angle)
        self._bg_opacity.setValue(int(defaults.bg_opacity * 100))
        self._bg_blur.setChecked(defaults.bg_blur)
        self._bg_blur_amount.setValue(defaults.bg_blur_amount)
        self._text_color_btn.set_color(defaults.text_color)
        self._ref_color_btn.set_color(defaults.ref_color)
        self._overall_opacity.setValue(int(defaults.opacity * 100))
        # Effects
        self._text_shadow.setChecked(defaults.text_shadow)
        self._shadow_color_btn.set_color(defaults.shadow_color)
        self._shadow_blur.setValue(defaults.shadow_blur)
        self._text_stroke.setChecked(defaults.text_stroke)
        self._stroke_color_btn.set_color(defaults.stroke_color)
        self._stroke_width.setValue(defaults.stroke_width)
        self._animation_enabled.setChecked(defaults.animation_enabled)
        self._animation_type.setCurrentIndex(
            self._animation_type.findData(defaults.animation_type)
        )
        self._animation_direction.setCurrentIndex(
            self._animation_direction.findData(defaults.animation_direction)
        )
        self._animation_duration.setValue(defaults.animation_duration)
        # Professional
        self._text_transform.setCurrentIndex(
            self._text_transform.findData(defaults.text_transform)
        )
        self._on_change()

    def get_settings(self) -> ObsOutputSettings:
        # Robust data retrieval with fallbacks
        try:
            font = self._font_combo.currentData() or self._font_combo.currentText()
        except Exception:
            font = "Google Sans"
        return ObsOutputSettings(
            font_family=str(font).strip() or "Google Sans",
            text_size=self._text_size.value(),
            ref_size=self._ref_size.value(),
            align=self._align_combo.currentData() or "center",
            show_reference=self._show_ref.isChecked(),
            position=self._position_combo.currentData() or "bottom",
            bg_enabled=self._bg_enabled.isChecked(),
            bg_color=self._bg_color_btn.color(),
            bg_gradient_enabled=self._bg_gradient_enabled.isChecked(),
            bg_color_2=self._bg_color_2_btn.color(),
            bg_gradient_angle=self._bg_gradient_angle.value(),
            bg_opacity=self._bg_opacity.value() / 100.0,
            text_color=self._text_color_btn.color(),
            ref_color=self._ref_color_btn.color(),
            opacity=self._overall_opacity.value() / 100.0,
            # Professional styling
            text_shadow=self._text_shadow.isChecked(),
            shadow_color=self._shadow_color_btn.color(),
            shadow_blur=self._shadow_blur.value(),
            text_stroke=self._text_stroke.isChecked(),
            stroke_color=self._stroke_color_btn.color(),
            stroke_width=self._stroke_width.value(),
            letter_spacing=self._letter_spacing.value(),
            line_height=self._line_height.value(),
            padding_horizontal=self._padding_h.value(),
            padding_vertical=self._padding_v.value(),
            max_width=self._max_width.value(),
            border_radius=self._border_radius.value(),
            animation_enabled=self._animation_enabled.isChecked(),
            animation_type=self._animation_type.currentData() or "blur",
            animation_direction=self._animation_direction.currentData() or "up",
            animation_duration=self._animation_duration.value(),
            font_weight=self._font_weight.currentData() or "normal",
            text_transform=self._text_transform.currentData() or "none",
            bg_blur=self._bg_blur.isChecked(),
            bg_blur_amount=self._bg_blur_amount.value(),
            # Preserved from the incoming settings (edited elsewhere)
            bg_mode=self._bg_mode,
            bg_image=self._bg_image,
            bg_image_fit=self._bg_image_fit,
        )

    def _create_preset_buttons(self, layout: QVBoxLayout):
        """Create a grid of preset style buttons."""
        presets = [
            (
                "Broadcast",
                {
                    "bg_color": "rgba(8, 15, 28, 0.82)",
                    "bg_color_2": "rgba(3, 8, 18, 0.90)",
                    "bg_gradient_enabled": True,
                    "text_color": "rgba(255, 255, 255, 0.96)",
                },
            ),
            (
                "Navy Pro",
                {
                    "bg_color": "rgba(10, 25, 47, 0.82)",
                    "bg_color_2": "rgba(2, 12, 27, 0.90)",
                    "bg_gradient_enabled": True,
                    "text_color": "#E6F1FF",
                },
            ),
            (
                "Or Doux",
                {
                    "bg_color": "rgba(38, 29, 14, 0.82)",
                    "bg_color_2": "rgba(10, 10, 14, 0.92)",
                    "bg_gradient_enabled": True,
                    "text_color": "#FFF3D4",
                },
            ),
            (
                "Gris Moderne",
                {
                    "bg_color": "rgba(34, 39, 49, 0.82)",
                    "bg_color_2": "rgba(16, 20, 28, 0.92)",
                    "bg_gradient_enabled": True,
                    "text_color": "#F4F1EA",
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
                    font-size: 11px;
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
        self._initializing = False
        self._on_change()

    @classmethod
    def edit(
        cls, settings: ObsOutputSettings, parent: QWidget | None = None
    ) -> ObsOutputSettings | None:
        dialog = cls(settings, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.get_settings()
        return None
