from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
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
from app.ui.theme import Colors, Radius, get_scroll_area_style
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


class ProjectionSettingsDialog(QDialog):
    settingsChanged = pyqtSignal(ProjectionSettings)

    def __init__(self, settings: ProjectionSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("local_projection_title"))
        self.setMinimumSize(620, 580)
        self.resize(680, 720)
        self.setStyleSheet(DIALOG_STYLE)

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
            f"font-size: 17px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;"
        )
        title_col.addWidget(title)
        subtitle = QLabel("Personnaliser l'affichage du texte projeté")
        subtitle.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_SECONDARY}; background: transparent; border: none;"
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

        # ═══════ Section: Police & Typographie ═══════
        font_section = SettingSection("Police & Typographie", "type.svg")

        self._font_combo = QComboBox()
        # Add available fonts
        for display_name, css_name in get_available_fonts():
            self._font_combo.addItem(display_name, css_name)

        # Select current
        idx = self._font_combo.findData(settings.font_family)
        if idx < 0:
            idx = self._font_combo.findText(settings.font_family)
        if idx >= 0:
            self._font_combo.setCurrentIndex(idx)
        font_section.addRow("Famille de police", self._font_combo)
        _style_combo(self._font_combo)

        self._font_weight = QComboBox()
        self._font_weight.addItem("Normal", "normal")
        self._font_weight.addItem("Gras", "bold")
        self._font_weight.addItem("Léger", "light")
        fw_idx = self._font_weight.findData(settings.font_weight or "normal")
        self._font_weight.setCurrentIndex(max(fw_idx, 0))
        font_section.addRow("Épaisseur", self._font_weight)
        _style_combo(self._font_weight)

        self._line_height = QDoubleSpinBox()
        self._line_height.setRange(0.8, 3.0)
        self._line_height.setSingleStep(0.05)
        self._line_height.setDecimals(2)
        self._line_height.setValue(settings.line_height or 1.15)
        font_section.addRow("Interligne", self._line_height)

        self._letter_spacing = QSpinBox()
        self._letter_spacing.setRange(-5, 20)
        self._letter_spacing.setSuffix(" px")
        self._letter_spacing.setValue(settings.letter_spacing)
        font_section.addRow("Espacement des lettres", self._letter_spacing)

        layout.addWidget(font_section)

        # ═══════ Section: Dimensions ═══════
        size_section = SettingSection("Dimensions", "text.svg")

        self._text_size = QSpinBox()
        self._text_size.setRange(16, 800)
        self._text_size.setSuffix(" px")
        self._text_size.setValue(settings.text_size)
        size_section.addRow("Taille du texte", self._text_size)

        self._ref_size = QSpinBox()
        self._ref_size.setRange(10, 400)
        self._ref_size.setSuffix(" px")
        self._ref_size.setValue(settings.ref_size)
        size_section.addRow("Taille de la référence", self._ref_size)

        self._padding = QSpinBox()
        self._padding.setRange(0, 500)
        self._padding.setSuffix(" px")
        self._padding.setValue(settings.padding)
        size_section.addRow("Marges intérieures", self._padding)

        self._max_width = QSpinBox()
        self._max_width.setRange(40, 100)
        self._max_width.setSuffix(" %")
        self._max_width.setValue(settings.max_width)
        size_section.addRow("Largeur max.", self._max_width, "Pourcentage de l'écran")

        layout.addWidget(size_section)

        # â•â•â•â•â•â•â• Section: Composition de slide â•â•â•â•â•â•â•
        composition_section = SettingSection("Composition de slide", "monitor.svg")

        self._slide_style = QComboBox()
        self._slide_style.addItem("Standard (centré)", "cinematic")
        self._slide_style.addItem("Split (texte à gauche)", "split")
        idx = self._slide_style.findData(settings.slide_style or "cinematic")
        self._slide_style.setCurrentIndex(max(idx, 0))
        composition_section.addRow("Style visuel", self._slide_style)
        _style_combo(self._slide_style)

        self._content_width = QSpinBox()
        self._content_width.setRange(40, 100)
        self._content_width.setSuffix(" %")
        self._content_width.setValue(settings.content_width)
        composition_section.addRow("Largeur du texte", self._content_width)

        self._content_height = QSpinBox()
        self._content_height.setRange(35, 100)
        self._content_height.setSuffix(" %")
        self._content_height.setValue(settings.content_height)
        composition_section.addRow("Hauteur du texte", self._content_height)

        layout.addWidget(composition_section)

        # ═══════ Section: Couleurs ═══════
        color_section = SettingSection("Couleurs", "palette.svg")

        self._text_color_btn = ColorPickerButton(
            settings.text_color or "rgba(255,255,255,0.92)"
        )
        color_section.addRow("Texte principal", self._text_color_btn)

        self._ref_color_btn = ColorPickerButton(
            settings.ref_color or "rgba(255,255,255,0.78)"
        )
        color_section.addRow("Référence", self._ref_color_btn)

        # ── Background type: color OR image (mutually exclusive) ──
        self._bg_mode_combo = QComboBox()
        self._bg_mode_combo.addItem("Couleur", "color")
        self._bg_mode_combo.addItem("Image", "image")
        _mode = "image" if str(settings.bg_mode or "color") == "image" else "color"
        idx = self._bg_mode_combo.findData(_mode)
        self._bg_mode_combo.setCurrentIndex(max(idx, 0))
        color_section.addRow(
            "Type d'arrière-plan", self._bg_mode_combo,
            "Choisissez une couleur OU une image (pas les deux)",
        )
        _style_combo(self._bg_mode_combo)

        self._bg_color_btn = ColorPickerButton(settings.bg_color or "#0c0f14")
        color_section.addRow("Couleur de fond", self._bg_color_btn)

        # Background image (used only when type = Image)
        self._bg_image_path = str(settings.bg_image or "")
        bg_image_widget = QWidget()
        bg_image_layout = QHBoxLayout(bg_image_widget)
        bg_image_layout.setContentsMargins(0, 0, 0, 0)
        bg_image_layout.setSpacing(8)
        self._bg_image_label = QLabel(self._bg_image_name_text())
        self._bg_image_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; background: transparent; border: none;"
        )
        _picker_btn_style = f"""
            QPushButton {{
                background: {Colors.SURFACE_HOVER};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
                padding: 8px 14px;
                color: {Colors.TEXT_PRIMARY};
                font-size: 13px;
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
        self._bg_browse_btn = QPushButton("Parcourir")
        self._bg_browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bg_browse_btn.setStyleSheet(_picker_btn_style)
        self._bg_clear_btn = QPushButton("Aucune")
        self._bg_clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bg_clear_btn.setStyleSheet(_picker_btn_style)
        bg_image_layout.addWidget(self._bg_image_label, 1)
        bg_image_layout.addWidget(self._bg_browse_btn)
        bg_image_layout.addWidget(self._bg_clear_btn)
        self._bg_browse_btn.clicked.connect(self._on_browse_bg_image)
        self._bg_clear_btn.clicked.connect(self._on_clear_bg_image)
        color_section.addRow(
            "Image de fond", bg_image_widget,
            "Image appliquée à toute la projection (plein écran en local, bandeau en OBS)",
        )

        # Image fit (used only when type = Image)
        self._bg_image_fit_combo = QComboBox()
        self._bg_image_fit_combo.addItem("Remplir", "cover")
        self._bg_image_fit_combo.addItem("Contenir", "contain")
        _fit = "contain" if str(settings.bg_image_fit or "cover") == "contain" else "cover"
        idx = self._bg_image_fit_combo.findData(_fit)
        self._bg_image_fit_combo.setCurrentIndex(max(idx, 0))
        color_section.addRow(
            "Cadrage de l'image", self._bg_image_fit_combo,
            "Remplir : couvre tout le cadre. Contenir : image entière visible.",
        )
        _style_combo(self._bg_image_fit_combo)

        self._bg_gradient_enabled = QCheckBox("Activer le dégradé")
        self._bg_gradient_enabled.setChecked(settings.bg_gradient_enabled)
        color_section.addWidget(self._bg_gradient_enabled)

        self._bg_color_2_btn = ColorPickerButton(settings.bg_color_2 or "#031228")
        color_section.addRow("Couleur de fin", self._bg_color_2_btn)

        self._bg_gradient_angle = QSpinBox()
        self._bg_gradient_angle.setRange(0, 360)
        self._bg_gradient_angle.setSuffix(" °")
        self._bg_gradient_angle.setValue(settings.bg_gradient_angle)
        color_section.addRow("Angle du dégradé", self._bg_gradient_angle)

        def _on_gradient_toggled(checked: bool) -> None:
            color_mode = self._bg_mode_combo.currentData() == "color"
            self._bg_color_2_btn.setEnabled(checked and color_mode)
            self._bg_gradient_angle.setEnabled(checked and color_mode)

        self._bg_gradient_enabled.toggled.connect(_on_gradient_toggled)

        def _apply_bg_mode_ui() -> None:
            is_image = self._bg_mode_combo.currentData() == "image"
            self._bg_image_label.setEnabled(is_image)
            self._bg_browse_btn.setEnabled(is_image)
            self._bg_clear_btn.setEnabled(is_image)
            self._bg_image_fit_combo.setEnabled(is_image)
            self._bg_color_btn.setEnabled(not is_image)
            self._bg_gradient_enabled.setEnabled(not is_image)
            _on_gradient_toggled(self._bg_gradient_enabled.isChecked())

        self._bg_mode_combo.currentIndexChanged.connect(
            lambda _i: (_apply_bg_mode_ui(), self._on_change())
        )
        _apply_bg_mode_ui()

        layout.addWidget(color_section)

        # ═══════ Section: Ombre du texte ═══════
        shadow_section = SettingSection("Ombre du texte", "sun.svg")

        self._text_shadow = QCheckBox("Activer l'ombre")
        self._text_shadow.setChecked(settings.text_shadow)
        shadow_section.addWidget(self._text_shadow)

        self._shadow_color_btn = ColorPickerButton(
            settings.shadow_color or "rgba(0,0,0,0.6)"
        )
        shadow_section.addRow("Couleur de l'ombre", self._shadow_color_btn)

        self._shadow_blur = QSpinBox()
        self._shadow_blur.setRange(0, 30)
        self._shadow_blur.setSuffix(" px")
        self._shadow_blur.setValue(settings.shadow_blur)
        shadow_section.addRow("Flou de l'ombre", self._shadow_blur)

        # Wire toggle
        def _on_shadow_toggled(checked: bool) -> None:
            self._shadow_color_btn.setEnabled(checked)
            self._shadow_blur.setEnabled(checked)

        self._text_shadow.toggled.connect(_on_shadow_toggled)
        _on_shadow_toggled(settings.text_shadow)

        layout.addWidget(shadow_section)

        # ═══════ Section: Affichage ═══════
        display_section = SettingSection("Affichage", "monitor.svg")

        self._align = QComboBox()
        self._align.addItem("Centré", "center")
        self._align.addItem("Gauche", "left")
        current_align = (settings.align or "center").lower()
        idx = self._align.findData(current_align)
        self._align.setCurrentIndex(max(idx, 0))
        display_section.addRow("Alignement", self._align)
        _style_combo(self._align)

        self._position = QComboBox()
        self._position.addItem("En haut", "top")
        self._position.addItem("Au centre", "center")
        self._position.addItem("En bas", "bottom")
        position = (settings.position or "center").lower()
        idx = self._position.findData(position)
        self._position.setCurrentIndex(max(idx, 1))
        display_section.addRow("Placement du bloc", self._position)
        _style_combo(self._position)

        self._show_reference = QCheckBox(tr("show_reference"))
        self._show_reference.setChecked(bool(settings.show_reference))
        display_section.addWidget(self._show_reference)

        self._reference_position = QComboBox()
        self._reference_position.addItem("En bas du texte", "bottom")
        self._reference_position.addItem("En haut du texte", "top")
        ref_pos = (settings.reference_position or "bottom").lower()
        idx = self._reference_position.findData(ref_pos)
        self._reference_position.setCurrentIndex(max(idx, 0))
        display_section.addRow("Position de la référence", self._reference_position)
        _style_combo(self._reference_position)

        self._uppercase = QCheckBox("Texte en MAJUSCULES")
        self._uppercase.setChecked(bool(settings.uppercase))
        display_section.addWidget(self._uppercase)

        layout.addWidget(display_section)

        # ═══════ Section: Transitions & Effets ═══════
        anim_section = SettingSection("Transitions & Effets", "sparkles.svg")

        self._anim_enabled = QCheckBox("Activer les transitions entre slides")
        self._anim_enabled.setChecked(bool(settings.animation_enabled))
        anim_section.addWidget(self._anim_enabled)

        self._anim_type = QComboBox()
        for label, data in (
            ("Aucune", "none"),
            ("Fondu", "fade"),
            ("Glissement", "slide"),
            ("Zoom doux", "scale"),
            ("Flou", "blur"),
            ("Reveal cinématique", "reveal"),
        ):
            self._anim_type.addItem(label, data)
        idx = self._anim_type.findData(settings.animation_type or "fade")
        self._anim_type.setCurrentIndex(max(idx, 0))
        anim_section.addRow("Style de transition", self._anim_type)
        _style_combo(self._anim_type)

        self._anim_direction = QComboBox()
        for label, data in (
            ("Vers le haut", "up"),
            ("Vers le bas", "down"),
            ("Vers la gauche", "left"),
            ("Vers la droite", "right"),
        ):
            self._anim_direction.addItem(label, data)
        idx = self._anim_direction.findData(settings.animation_direction or "up")
        self._anim_direction.setCurrentIndex(max(idx, 0))
        anim_section.addRow(
            "Direction", self._anim_direction,
            "Utilisée pour Glissement et Reveal",
        )
        _style_combo(self._anim_direction)

        self._anim_duration = QSpinBox()
        self._anim_duration.setRange(0, 2000)
        self._anim_duration.setSingleStep(50)
        self._anim_duration.setSuffix(" ms")
        self._anim_duration.setValue(int(settings.animation_duration or 420))
        anim_section.addRow(
            "Durée", self._anim_duration, "420 ms donne un rendu fluide"
        )

        self._ken_burns = QCheckBox("Zoom lent sur les images de fond (Ken Burns)")
        self._ken_burns.setChecked(bool(settings.ken_burns))
        anim_section.addWidget(self._ken_burns)

        def _update_anim_controls() -> None:
            on = self._anim_enabled.isChecked()
            anim_type = str(self._anim_type.currentData() or "fade")
            self._anim_type.setEnabled(on)
            self._anim_duration.setEnabled(on and anim_type != "none")
            self._anim_direction.setEnabled(
                on and anim_type in ("slide", "reveal")
            )

        self._anim_enabled.toggled.connect(_update_anim_controls)
        self._anim_type.currentIndexChanged.connect(_update_anim_controls)
        _update_anim_controls()

        layout.addWidget(anim_section)

        # ── Connect signals for live preview ──
        self._font_combo.currentIndexChanged.connect(self._on_change)
        self._font_weight.currentIndexChanged.connect(self._on_change)
        self._line_height.valueChanged.connect(self._on_change)
        self._letter_spacing.valueChanged.connect(self._on_change)
        self._text_size.valueChanged.connect(self._on_change)
        self._ref_size.valueChanged.connect(self._on_change)
        self._padding.valueChanged.connect(self._on_change)
        self._max_width.valueChanged.connect(self._on_change)
        self._slide_style.currentIndexChanged.connect(self._on_change)
        self._content_width.valueChanged.connect(self._on_change)
        self._content_height.valueChanged.connect(self._on_change)
        self._text_color_btn.colorChanged.connect(self._on_change)
        self._ref_color_btn.colorChanged.connect(self._on_change)
        self._bg_color_btn.colorChanged.connect(self._on_change)
        self._bg_image_fit_combo.currentIndexChanged.connect(self._on_change)
        self._bg_gradient_enabled.toggled.connect(self._on_change)
        self._bg_color_2_btn.colorChanged.connect(self._on_change)
        self._bg_gradient_angle.valueChanged.connect(self._on_change)
        self._text_shadow.toggled.connect(self._on_change)
        self._shadow_color_btn.colorChanged.connect(self._on_change)
        self._shadow_blur.valueChanged.connect(self._on_change)
        self._align.currentIndexChanged.connect(self._on_change)
        self._position.currentIndexChanged.connect(self._on_change)
        self._show_reference.toggled.connect(self._on_change)
        self._reference_position.currentIndexChanged.connect(self._on_change)
        self._uppercase.toggled.connect(self._on_change)
        self._anim_enabled.toggled.connect(self._on_change)
        self._anim_type.currentIndexChanged.connect(self._on_change)
        self._anim_direction.currentIndexChanged.connect(self._on_change)
        self._anim_duration.valueChanged.connect(self._on_change)
        self._ken_burns.toggled.connect(self._on_change)

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
                font-size: 13px;
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
                font-size: 13px;
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
                font-size: 13px;
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
        self._on_change()

    def _on_clear_bg_image(self) -> None:
        self._bg_image_path = ""
        self._bg_image_label.setText(self._bg_image_name_text())
        self._on_change()

    def _reset_defaults(self) -> None:
        d = ProjectionSettings()
        # Font
        idx = self._font_combo.findData(d.font_family)
        if idx >= 0:
            self._font_combo.setCurrentIndex(idx)
        fw_idx = self._font_weight.findData(d.font_weight)
        if fw_idx >= 0:
            self._font_weight.setCurrentIndex(fw_idx)
        self._line_height.setValue(d.line_height)
        self._letter_spacing.setValue(d.letter_spacing)
        # Sizes
        self._text_size.setValue(d.text_size)
        self._ref_size.setValue(d.ref_size)
        self._padding.setValue(d.padding)
        self._max_width.setValue(d.max_width)
        idx = self._slide_style.findData(d.slide_style)
        if idx >= 0:
            self._slide_style.setCurrentIndex(idx)
        self._content_width.setValue(d.content_width)
        self._content_height.setValue(d.content_height)
        # Colors
        self._text_color_btn.set_color(d.text_color)
        self._ref_color_btn.set_color(d.ref_color)
        self._bg_color_btn.set_color(d.bg_color)
        self._bg_image_path = str(d.bg_image or "")
        self._bg_image_label.setText(self._bg_image_name_text())
        mode_idx = self._bg_mode_combo.findData(d.bg_mode or "color")
        self._bg_mode_combo.setCurrentIndex(max(mode_idx, 0))
        fit_idx = self._bg_image_fit_combo.findData(d.bg_image_fit or "cover")
        self._bg_image_fit_combo.setCurrentIndex(max(fit_idx, 0))
        self._bg_gradient_enabled.setChecked(d.bg_gradient_enabled)
        self._bg_color_2_btn.set_color(d.bg_color_2)
        self._bg_gradient_angle.setValue(d.bg_gradient_angle)
        # Shadow
        self._text_shadow.setChecked(d.text_shadow)
        self._shadow_color_btn.set_color(d.shadow_color)
        self._shadow_blur.setValue(d.shadow_blur)
        # Display
        idx = self._align.findData(d.align)
        if idx >= 0:
            self._align.setCurrentIndex(idx)
        idx = self._position.findData(d.position)
        if idx >= 0:
            self._position.setCurrentIndex(idx)
        self._show_reference.setChecked(d.show_reference)
        idx = self._reference_position.findData(d.reference_position)
        if idx >= 0:
            self._reference_position.setCurrentIndex(idx)
        self._uppercase.setChecked(d.uppercase)
        # Transitions & effects
        self._anim_enabled.setChecked(d.animation_enabled)
        idx = self._anim_type.findData(d.animation_type)
        if idx >= 0:
            self._anim_type.setCurrentIndex(idx)
        idx = self._anim_direction.findData(d.animation_direction)
        if idx >= 0:
            self._anim_direction.setCurrentIndex(idx)
        self._anim_duration.setValue(d.animation_duration)
        self._ken_burns.setChecked(d.ken_burns)
        self._on_change()

    def read_settings(self) -> ProjectionSettings:
        font = self._font_combo.currentData() or self._font_combo.currentText()
        return ProjectionSettings(
            font_family=str(font).strip() or "Google Sans",
            text_size=self._text_size.value(),
            ref_size=self._ref_size.value(),
            padding=self._padding.value(),
            align=str(self._align.currentData() or "center"),
            position=str(self._position.currentData() or "center"),
            slide_style=str(self._slide_style.currentData() or "cinematic"),
            content_width=self._content_width.value(),
            content_height=self._content_height.value(),
            show_reference=self._show_reference.isChecked(),
            reference_position=str(
                self._reference_position.currentData() or "bottom"
            ),
            uppercase=self._uppercase.isChecked(),
            text_color=self._text_color_btn.color(),
            ref_color=self._ref_color_btn.color(),
            bg_color=self._bg_color_btn.color(),
            bg_gradient_enabled=self._bg_gradient_enabled.isChecked(),
            bg_color_2=self._bg_color_2_btn.color(),
            bg_gradient_angle=self._bg_gradient_angle.value(),
            bg_mode=str(self._bg_mode_combo.currentData() or "color"),
            bg_image=self._bg_image_path,
            bg_image_fit=str(self._bg_image_fit_combo.currentData() or "cover"),
            font_weight=str(self._font_weight.currentData() or "normal"),
            line_height=self._line_height.value(),
            letter_spacing=self._letter_spacing.value(),
            text_shadow=self._text_shadow.isChecked(),
            shadow_color=self._shadow_color_btn.color(),
            shadow_blur=self._shadow_blur.value(),
            max_width=self._max_width.value(),
            animation_enabled=self._anim_enabled.isChecked(),
            animation_type=str(self._anim_type.currentData() or "fade"),
            animation_direction=str(self._anim_direction.currentData() or "up"),
            animation_duration=self._anim_duration.value(),
            ken_burns=self._ken_burns.isChecked(),
        )

    @staticmethod
    def edit(settings: ProjectionSettings, parent=None) -> ProjectionSettings | None:
        dlg = ProjectionSettingsDialog(settings=settings, parent=parent)
        if dlg.exec() == int(QDialog.DialogCode.Accepted):
            return dlg.read_settings()
        return None
