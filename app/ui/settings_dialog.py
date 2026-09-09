from __future__ import annotations

import copy
from dataclasses import replace

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.ui.icons import app_icon
from app.ui.obs_output_settings_dialog import (
    DIALOG_STYLE,
    ColorPickerButton,
    SettingSection,
)
from app.ui.theme import Colors, Radius, Typography, get_scroll_area_style
from app.utils.fonts import get_available_fonts
from app.utils.settings import ProjectionSettings
from app.utils.translations import tr

_COMBO_POPUP_STYLE = f"""
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


def _style_combo(combo: QComboBox) -> None:
    """Force an opaque background on the combo popup (Windows workaround)."""
    view = combo.view()
    if view:
        view.setStyleSheet(_COMBO_POPUP_STYLE)
        view.window().setStyleSheet(
            f"background: {Colors.BG_ELEVATED}; border: 1px solid {Colors.BORDER_DEFAULT}; border-radius: 6px;"
        )


def _picker_button_style() -> str:
    return f"""
        QPushButton {{
            background: {Colors.SURFACE_HOVER};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.MD}px;
            padding: 8px 14px;
            color: {Colors.TEXT_PRIMARY};
            font-size: {Typography.SIZE_BODY}px;
        }}
        QPushButton:hover {{
            background: {Colors.SURFACE_ACTIVE};
            border-color: {Colors.BORDER_FOCUS};
        }}
        QPushButton:disabled {{
            color: {Colors.TEXT_DISABLED};
            border-color: {Colors.BORDER_SUBTLE};
        }}
    """


class ProjectionSettingsDialog(QDialog):
    """Réglages essentiels de la projection locale.

    Volontairement minimal : seuls les réglages réellement utiles en
    consultation sont exposés. Les champs avancés de :class:`ProjectionSettings`
    (voile, panneau, dégradé, ombre…) conservent la valeur du style édité —
    ``read_settings()`` ne les écrase jamais.
    """

    settingsChanged = pyqtSignal(ProjectionSettings)

    def __init__(self, settings: ProjectionSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("local_projection_title"))
        self.setMinimumSize(560, 520)
        self.resize(620, 640)
        self.setStyleSheet(DIALOG_STYLE)

        # Style de référence : les champs non exposés restent inchangés.
        self._base = copy.deepcopy(settings)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Header ──
        header = QFrame(self)
        header.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_SECONDARY};
                border-bottom: 1px solid {Colors.BORDER_DEFAULT};
            }}
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(24, 16, 24, 14)
        h_layout.setSpacing(14)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(app_icon("monitor.svg").pixmap(28, 28))
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        h_layout.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Projection locale")
        title.setStyleSheet(
            f"font-size: {Typography.SIZE_TITLE}px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;"
        )
        title_col.addWidget(title)
        subtitle = QLabel("L'essentiel pour projeter lisiblement")
        subtitle.setStyleSheet(
            f"font-size: {Typography.SIZE_CONTROL}px; color: {Colors.TEXT_SECONDARY}; background: transparent; border: none;"
        )
        title_col.addWidget(subtitle)
        h_layout.addLayout(title_col, 1)
        main_layout.addWidget(header)

        # ── Scrollable content ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(get_scroll_area_style())

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(16)
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)

        # ═══════ Section: Sortie ═══════
        output_section = SettingSection("Sortie", "monitor.svg")

        self._layout_mode = QComboBox()
        self._layout_mode.addItem("Plein écran", "fullscreen")
        self._layout_mode.addItem("Bandeau tiers inférieur", "lower_third")
        self._layout_mode.addItem("Sous-titre", "subtitle")
        self._layout_mode.addItem("Panneau latéral", "side_panel")
        self._layout_mode.addItem("Carte focus", "focus_card")
        idx = self._layout_mode.findData(settings.layout_mode or "fullscreen")
        self._layout_mode.setCurrentIndex(max(idx, 0))
        output_section.addRow("Mode d'affichage", self._layout_mode)
        _style_combo(self._layout_mode)

        self._display_screen = QComboBox()
        self._display_screen.addItem("Automatique (écran secondaire)", "auto")
        for index, screen in enumerate(QGuiApplication.screens(), start=1):
            geo = screen.geometry()
            screen_name = str(screen.name() or f"Écran {index}")
            self._display_screen.addItem(
                f"{screen_name} — {geo.width()}×{geo.height()}", screen_name
            )
        idx = self._display_screen.findData(settings.display_screen or "auto")
        self._display_screen.setCurrentIndex(max(idx, 0))
        output_section.addRow("Écran cible", self._display_screen)
        _style_combo(self._display_screen)

        self._slide_style = QComboBox()
        self._slide_style.addItem("Standard (centré)", "cinematic")
        self._slide_style.addItem("Épuré (sans voile)", "clean")
        self._slide_style.addItem("Split (texte à gauche)", "split")
        idx = self._slide_style.findData(settings.slide_style or "cinematic")
        self._slide_style.setCurrentIndex(max(idx, 0))
        output_section.addRow("Composition", self._slide_style)
        _style_combo(self._slide_style)

        self._position = QComboBox()
        self._position.addItem("En haut", "top")
        self._position.addItem("Au centre", "center")
        self._position.addItem("En bas", "bottom")
        idx = self._position.findData((settings.position or "center").lower())
        self._position.setCurrentIndex(max(idx, 1))
        output_section.addRow("Position du texte", self._position)
        _style_combo(self._position)

        layout.addWidget(output_section)

        # ═══════ Section: Texte & référence ═══════
        text_section = SettingSection("Texte & référence", "type.svg")

        self._font_combo = QComboBox()
        for display_name, css_name in get_available_fonts():
            self._font_combo.addItem(display_name, css_name)
        idx = self._font_combo.findData(settings.font_family)
        if idx < 0:
            idx = self._font_combo.findText(settings.font_family)
        if idx >= 0:
            self._font_combo.setCurrentIndex(idx)
        text_section.addRow("Police", self._font_combo)
        _style_combo(self._font_combo)

        self._text_size = QSpinBox()
        self._text_size.setRange(20, 240)
        self._text_size.setSuffix(" px")
        self._text_size.setValue(settings.text_size)
        text_section.addRow("Taille du texte", self._text_size)

        self._ref_size = QSpinBox()
        self._ref_size.setRange(10, 120)
        self._ref_size.setSuffix(" px")
        self._ref_size.setValue(settings.ref_size)
        text_section.addRow("Taille de la référence", self._ref_size)

        self._text_color_btn = ColorPickerButton(
            settings.text_color or "rgba(255,255,255,0.92)"
        )
        text_section.addRow("Couleur du texte", self._text_color_btn)

        self._show_reference = QCheckBox("Afficher la référence")
        self._show_reference.setChecked(bool(settings.show_reference))
        text_section.addWidget(self._show_reference)

        self._reference_position = QComboBox()
        self._reference_position.addItem("En bas du texte", "bottom")
        self._reference_position.addItem("En haut du texte", "top")
        idx = self._reference_position.findData(
            (settings.reference_position or "bottom").lower()
        )
        self._reference_position.setCurrentIndex(max(idx, 0))
        text_section.addRow("Position de la référence", self._reference_position)
        _style_combo(self._reference_position)

        self._uppercase = QCheckBox("Texte en MAJUSCULES")
        self._uppercase.setChecked(bool(settings.uppercase))
        text_section.addWidget(self._uppercase)

        def _update_reference_controls() -> None:
            enabled = self._show_reference.isChecked()
            self._reference_position.setEnabled(enabled)
            self._ref_size.setEnabled(enabled)

        self._show_reference.toggled.connect(_update_reference_controls)
        _update_reference_controls()

        layout.addWidget(text_section)

        # ═══════ Section: Arrière-plan ═══════
        bg_section = SettingSection("Arrière-plan", "palette.svg")

        self._bg_mode_combo = QComboBox()
        self._bg_mode_combo.addItem("Couleur", "color")
        self._bg_mode_combo.addItem("Image", "image")
        _mode = "image" if str(settings.bg_mode or "color") == "image" else "color"
        idx = self._bg_mode_combo.findData(_mode)
        self._bg_mode_combo.setCurrentIndex(max(idx, 0))
        bg_section.addRow("Type de fond", self._bg_mode_combo)
        _style_combo(self._bg_mode_combo)

        self._bg_color_btn = ColorPickerButton(settings.bg_color or "#0c0f14")
        bg_section.addRow("Couleur de fond", self._bg_color_btn)

        self._bg_image_path = str(settings.bg_image or "")
        bg_image_widget = QWidget()
        bg_image_layout = QHBoxLayout(bg_image_widget)
        bg_image_layout.setContentsMargins(0, 0, 0, 0)
        bg_image_layout.setSpacing(8)
        self._bg_image_label = QLabel(self._bg_image_name_text())
        self._bg_image_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; background: transparent; border: none;"
        )
        picker_style = _picker_button_style()
        self._bg_browse_btn = QPushButton("Parcourir")
        self._bg_browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bg_browse_btn.setStyleSheet(picker_style)
        self._bg_clear_btn = QPushButton("Aucune")
        self._bg_clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bg_clear_btn.setStyleSheet(picker_style)
        bg_image_layout.addWidget(self._bg_image_label, 1)
        bg_image_layout.addWidget(self._bg_browse_btn)
        bg_image_layout.addWidget(self._bg_clear_btn)
        self._bg_browse_btn.clicked.connect(self._on_browse_bg_image)
        self._bg_clear_btn.clicked.connect(self._on_clear_bg_image)
        bg_section.addRow("Image de fond", bg_image_widget)

        self._background_dimmer = QSpinBox()
        self._background_dimmer.setRange(0, 85)
        self._background_dimmer.setSuffix(" %")
        self._background_dimmer.setValue(
            int(round(float(settings.background_dimmer or 0.0) * 100))
        )
        bg_section.addRow(
            "Assombrir l'image",
            self._background_dimmer,
            "Améliore le contraste du texte sur une image.",
        )

        def _apply_bg_mode_ui() -> None:
            is_image = self._bg_mode_combo.currentData() == "image"
            self._bg_image_label.setEnabled(is_image)
            self._bg_browse_btn.setEnabled(is_image)
            self._bg_clear_btn.setEnabled(is_image)
            self._bg_color_btn.setEnabled(not is_image)
            self._background_dimmer.setEnabled(True)

        self._bg_mode_combo.currentIndexChanged.connect(
            lambda _i: (_apply_bg_mode_ui(), self._on_change())
        )
        _apply_bg_mode_ui()

        layout.addWidget(bg_section)

        # ═══════ Section: Transition ═══════
        anim_section = SettingSection("Transition", "sparkles.svg")

        self._anim_enabled = QCheckBox("Transition en fondu entre les slides")
        self._anim_enabled.setChecked(bool(settings.animation_enabled))
        anim_section.addWidget(self._anim_enabled)

        self._anim_duration = QSpinBox()
        self._anim_duration.setRange(0, 800)
        self._anim_duration.setSingleStep(50)
        self._anim_duration.setSuffix(" ms")
        self._anim_duration.setValue(
            int(
                settings.animation_duration
                if settings.animation_duration is not None
                else 400
            )
        )
        anim_section.addRow("Durée du fondu", self._anim_duration)
        self._anim_enabled.toggled.connect(self._anim_duration.setEnabled)
        self._anim_duration.setEnabled(self._anim_enabled.isChecked())

        layout.addWidget(anim_section)

        # ── Connect signals for live preview ──
        self._layout_mode.currentIndexChanged.connect(self._on_change)
        self._display_screen.currentIndexChanged.connect(self._on_change)
        self._slide_style.currentIndexChanged.connect(self._on_change)
        self._position.currentIndexChanged.connect(self._on_change)
        self._font_combo.currentIndexChanged.connect(self._on_change)
        self._text_size.valueChanged.connect(self._on_change)
        self._ref_size.valueChanged.connect(self._on_change)
        self._text_color_btn.colorChanged.connect(self._on_change)
        self._show_reference.toggled.connect(self._on_change)
        self._reference_position.currentIndexChanged.connect(self._on_change)
        self._uppercase.toggled.connect(self._on_change)
        self._bg_color_btn.colorChanged.connect(self._on_change)
        self._background_dimmer.valueChanged.connect(self._on_change)
        self._anim_enabled.toggled.connect(self._on_change)
        self._anim_duration.valueChanged.connect(self._on_change)

        layout.addStretch()
        scroll.setWidget(content)
        main_layout.addWidget(scroll, 1)

        # ── Footer buttons ──
        btn_frame = QFrame(self)
        btn_frame.setStyleSheet(
            f"background: {Colors.BG_SECONDARY}; border-top: 1px solid {Colors.BORDER_DEFAULT};"
        )
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(20, 12, 20, 12)
        btn_layout.setSpacing(10)

        reset_btn = QPushButton("Réinitialiser")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.SURFACE_HOVER};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
                padding: 8px 18px;
                color: {Colors.TEXT_SECONDARY};
                font-size: {Typography.SIZE_CONTROL}px;
            }}
            QPushButton:hover {{ background: {Colors.SURFACE_ACTIVE}; border-color: {Colors.BORDER_FOCUS}; }}
        """)
        reset_btn.clicked.connect(self._reset_defaults)
        btn_layout.addWidget(reset_btn)
        btn_layout.addStretch(1)

        cancel_btn = QPushButton(tr("cancel"))
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.SURFACE_HOVER};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
                padding: 8px 22px;
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_CONTROL}px;
            }}
            QPushButton:hover {{ background: {Colors.SURFACE_ACTIVE}; border-color: {Colors.BORDER_FOCUS}; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Enregistrer")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ACCENT_PRIMARY};
                border: none;
                border-radius: {Radius.MD}px;
                padding: 8px 22px;
                color: {Colors.PROJECT_BUTTON_TEXT};
                font-size: {Typography.SIZE_CONTROL}px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {Colors.ACCENT_LIGHT}; }}
        """)
        save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(save_btn)

        main_layout.addWidget(btn_frame)

    def _on_change(self, *_args) -> None:
        """Emit signal with current settings for live preview."""
        self.settingsChanged.emit(self.read_settings())

    def _bg_image_name_text(self) -> str:
        from pathlib import Path
        if self._bg_image_path:
            return Path(self._bg_image_path).name
        return "Aucune image"

    def _on_browse_bg_image(self) -> None:
        import shutil
        from pathlib import Path

        from PyQt6.QtWidgets import QFileDialog

        from app.utils.app_paths import backgrounds_dir
        from app.utils.media_utils import BACKGROUND_FILE_FILTER

        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir une image de fond", str(backgrounds_dir()), BACKGROUND_FILE_FILTER
        )
        if not path:
            return
        src = Path(path)
        dest = backgrounds_dir() / src.name
        if not dest.exists() or dest.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dest)
        self._bg_image_path = str(dest)
        self._bg_image_label.setText(self._bg_image_name_text())
        self._bg_mode_combo.setCurrentIndex(self._bg_mode_combo.findData("image"))
        self._on_change()

    def _on_clear_bg_image(self) -> None:
        self._bg_image_path = ""
        self._bg_image_label.setText(self._bg_image_name_text())
        self._on_change()

    def _reset_defaults(self) -> None:
        """Réinitialise les réglages exposés aux valeurs par défaut."""
        d = ProjectionSettings()
        for combo, value in (
            (self._layout_mode, d.layout_mode),
            (self._display_screen, d.display_screen),
            (self._slide_style, d.slide_style),
            (self._position, d.position),
            (self._reference_position, d.reference_position),
        ):
            idx = combo.findData(value)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        idx = self._font_combo.findData(d.font_family)
        if idx >= 0:
            self._font_combo.setCurrentIndex(idx)
        self._text_size.setValue(d.text_size)
        self._ref_size.setValue(d.ref_size)
        self._text_color_btn.set_color(d.text_color)
        self._show_reference.setChecked(d.show_reference)
        self._uppercase.setChecked(d.uppercase)
        self._bg_mode_combo.setCurrentIndex(self._bg_mode_combo.findData("color"))
        self._bg_color_btn.set_color(d.bg_color)
        self._bg_image_path = ""
        self._bg_image_label.setText(self._bg_image_name_text())
        self._background_dimmer.setValue(int(round(d.background_dimmer * 100)))
        self._anim_enabled.setChecked(d.animation_enabled)
        self._anim_duration.setValue(d.animation_duration)
        self._on_change()

    def read_settings(self) -> ProjectionSettings:
        """Style complet : réglages exposés + champs non exposés inchangés."""
        font = self._font_combo.currentData() or self._font_combo.currentText()
        return replace(
            self._base,
            layout_mode=str(self._layout_mode.currentData() or "fullscreen"),
            display_screen=str(self._display_screen.currentData() or "auto"),
            slide_style=str(self._slide_style.currentData() or "cinematic"),
            position=str(self._position.currentData() or "center"),
            font_family=str(font).strip() or "Poppins",
            text_size=self._text_size.value(),
            ref_size=self._ref_size.value(),
            text_color=self._text_color_btn.color(),
            show_reference=self._show_reference.isChecked(),
            reference_position=str(self._reference_position.currentData() or "bottom"),
            uppercase=self._uppercase.isChecked(),
            bg_mode=str(self._bg_mode_combo.currentData() or "color"),
            bg_color=self._bg_color_btn.color(),
            bg_image=self._bg_image_path,
            background_dimmer=self._background_dimmer.value() / 100.0,
            animation_enabled=self._anim_enabled.isChecked(),
            animation_duration=self._anim_duration.value(),
        )

    @staticmethod
    def edit(settings: ProjectionSettings, parent=None) -> ProjectionSettings | None:
        dlg = ProjectionSettingsDialog(settings=settings, parent=parent)
        if dlg.exec() == int(QDialog.DialogCode.Accepted):
            return dlg.read_settings()
        return None
