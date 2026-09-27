from __future__ import annotations

"""Éditeur du style propre à la sortie HDMI.

Mêmes familles de réglages que la page OBS (police, tailles, position,
arrière-plan, couleurs, effets, animation), appliquées à la seule sortie
HDMI. Les widgets sont décrits une fois (clé → widget) : lecture, écriture
et préréglages passent par la même table.
"""

from dataclasses import asdict, fields
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.ui.obs_output_settings_dialog import ColorPickerButton
from app.ui.setting_cards import SettingSection
from app.ui.settings_dialog import _style_combo
from app.utils.flow_layout import FlowLayout
from app.utils.fonts import get_available_fonts
from app.utils.settings import HdmiStyle

__all__ = ["HdmiStyleEditor", "HDMI_STYLE_PRESETS", "style_from_obs_config"]


# Préréglages pensés pour l'incrustation caméra (clé chroma).
HDMI_STYLE_PRESETS: tuple[tuple[str, str, dict[str, Any]], ...] = (
    (
        "Sous-titre TV",
        "Bandeau sombre sobre, texte blanc centré",
        {},  # valeurs par défaut de HdmiStyle
    ),
    (
        "Contour seul",
        "Sans bandeau : texte blanc cerné de noir, comme un sous-titre de film",
        {
            "bg_enabled": False,
            "show_accent_bar": False,
            "text_color": "rgba(255, 255, 255, 1.00)",
            "text_stroke": True,
            "stroke_color": "rgba(0, 0, 0, 1.00)",
            "stroke_width": 3,
            "text_shadow": True,
            "shadow_blur": 10,
            "reference_style": "plain",
            "text_size": 56,
        },
    ),
    (
        "Jaune cinéma",
        "Texte jaune cerné, lisible sur toutes les images",
        {
            "bg_enabled": False,
            "show_accent_bar": False,
            "text_color": "rgba(255, 221, 51, 1.00)",
            "ref_color": "rgba(255, 255, 255, 0.95)",
            "text_stroke": True,
            "stroke_color": "rgba(0, 0, 0, 1.00)",
            "stroke_width": 3,
            "reference_style": "plain",
            "text_size": 56,
        },
    ),
    (
        "Bandeau clair",
        "Panneau blanc, texte foncé : pour un décor sombre",
        {
            "bg_color": "rgba(248, 248, 244, 1.00)",
            "text_color": "rgba(18, 22, 30, 1.00)",
            "ref_color": "rgba(60, 66, 80, 1.00)",
            "text_shadow": False,
            "border_radius": 14,
        },
    ),
    (
        "Louange — Impact",
        "Majuscules, entrée mot à mot",
        {
            "bg_color": "rgba(24, 14, 44, 1.00)",
            "bg_gradient_enabled": True,
            "bg_color_2": "rgba(8, 5, 20, 1.00)",
            "text_transform": "uppercase",
            "text_size": 58,
            "animation_style": "words",
            "animation_type": "slide",
        },
    ),
)


def style_from_obs_config(cfg: dict[str, Any] | None) -> HdmiStyle:
    """Style HDMI initialisé depuis la configuration de la page OBS."""
    names = {f.name for f in fields(HdmiStyle)}
    payload = {k: v for k, v in (cfg or {}).items() if k in names}
    return HdmiStyle.from_payload(payload)


class HdmiStyleEditor(QWidget):
    """Réglages du style HDMI, groupés comme la page OBS."""

    changed = Signal()

    def __init__(self, style: HdmiStyle, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._loading = False
        self._widgets: dict[str, QWidget] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        # ── Police ──
        font = SettingSection("Police", "type.svg")
        fonts = QComboBox()
        for display_name, css_name in get_available_fonts():
            fonts.addItem(display_name, css_name)
        self._add_combo_widget(font, "font_family", "Famille de police", fonts)
        self._combo(font, "font_weight", "Épaisseur",
                    [("Gras", "bold"), ("Normal", "normal"), ("Léger", "light")])
        self._combo(font, "text_transform", "Casse",
                    [("Normale", "none"), ("MAJUSCULES", "uppercase"),
                     ("Capitales Initiales", "capitalize")])
        self._spin(font, "letter_spacing", "Espacement des lettres", -5, 20, " px")
        self._dspin(font, "line_height", "Hauteur de ligne", 1.0, 2.0, 0.05)
        layout.addWidget(font)

        # ── Tailles et référence ──
        sizes = SettingSection("Tailles et référence", "text.svg")
        self._spin(sizes, "text_size", "Taille du texte", 16, 120, " px",
                   "Taille à 1920×1080, avant le curseur « Taille du texte »")
        self._spin(sizes, "ref_size", "Taille de la référence", 10, 60, " px")
        self._check(sizes, "show_reference", "Afficher la référence (Jean 3:16…)")
        self._combo(sizes, "reference_style", "Style de référence",
                    [("Badge", "badge"), ("Simple", "plain"), ("Dans le texte", "inline")])
        self._check(sizes, "auto_fit", "Réduire le texte trop long (ajustement automatique)")
        self._spin(sizes, "max_lines", "Lignes au maximum", 1, 8, "",
                   "Au-delà, le texte rétrécit (ajustement automatique actif)")
        layout.addWidget(sizes)

        # ── Position ──
        position = SettingSection("Position", "move.svg")
        self._combo(position, "position", "Emplacement",
                    [("En bas", "bottom"), ("En haut", "top"), ("Au centre", "center")])
        self._combo(position, "align", "Alignement du texte",
                    [("Centré", "center"), ("À gauche", "left"), ("À droite", "right")])
        self._spin(position, "edge_margin", "Marge des bords", 0, 300, " px",
                   "Distance entre le texte et le bord de l'image")
        self._spin(position, "max_width", "Largeur maximale", 30, 100, " %")
        layout.addWidget(position)

        # ── Arrière-plan ──
        background = SettingSection("Arrière-plan du texte", "monitor.svg")
        self._check(background, "bg_enabled", "Afficher un bandeau derrière le texte")
        self._color(background, "bg_color", "Couleur du bandeau",
                    "Toujours opaque sur la sortie HDMI (clé chroma)")
        self._check(background, "bg_gradient_enabled", "Dégradé")
        self._color(background, "bg_color_2", "Seconde couleur du dégradé")
        self._spin(background, "border_radius", "Coins arrondis", 0, 60, " px")
        layout.addWidget(background)

        # ── Couleurs et habillage ──
        colors = SettingSection("Couleurs et habillage", "palette.svg")
        self._color(colors, "text_color", "Texte")
        self._color(colors, "ref_color", "Référence")
        self._check(colors, "show_accent_bar", "Barre d'accent sous le bandeau")
        self._check(colors, "show_kicker", "Pastille de source (Bible, Cantique…)")
        self._combo(colors, "accent_mode", "Couleur d'accent",
                    [("Selon la source", "auto"), ("Personnalisée", "custom")])
        self._color(colors, "accent_color", "Accent personnalisé")
        layout.addWidget(colors)

        # ── Effets ──
        effects = SettingSection("Effets du texte", "sun.svg")
        self._check(effects, "text_shadow", "Ombre portée")
        self._color(effects, "shadow_color", "Couleur de l'ombre")
        self._spin(effects, "shadow_blur", "Flou de l'ombre", 0, 30, " px")
        self._check(effects, "text_stroke", "Contour des lettres")
        self._color(effects, "stroke_color", "Couleur du contour")
        self._spin(effects, "stroke_width", "Épaisseur du contour", 1, 8, " px")
        layout.addWidget(effects)

        # ── Animation ──
        animation = SettingSection("Animation d'entrée", "sparkles.svg")
        self._check(animation, "animation_enabled", "Animer l'arrivée du texte")
        self._combo(animation, "animation_type", "Style",
                    [("Fondu", "fade"), ("Glissement", "slide"), ("Zoom doux", "scale"),
                     ("Flou", "blur"), ("Reveal", "reveal"), ("Auto par source", "auto"),
                     ("Aucune", "none")])
        self._combo(animation, "animation_style", "Révélation",
                    [("Tout le texte", "block"), ("Mot à mot", "words")])
        self._combo(animation, "animation_direction", "Direction",
                    [("Vers le haut", "up"), ("Vers le bas", "down"),
                     ("Vers la gauche", "left"), ("Vers la droite", "right")])
        self._spin(animation, "animation_duration", "Durée", 0, 2000, " ms", step=50)
        layout.addWidget(animation)

        self.set_style(style)
        self._connect_dependencies()

    # ── Construction des lignes ───────────────────────────────────────

    def _register(self, key: str, widget: QWidget) -> None:
        self._widgets[key] = widget

    def _add_combo_widget(self, section, key, label, combo, description="") -> None:
        combo.currentIndexChanged.connect(self._emit)
        section.addRow(label, combo, description)
        _style_combo(combo)
        self._register(key, combo)

    def _combo(self, section, key, label, items, description="") -> None:
        combo = QComboBox()
        for text, value in items:
            combo.addItem(text, value)
        self._add_combo_widget(section, key, label, combo, description)

    def _spin(self, section, key, label, low, high, suffix, description="", step=1) -> None:
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setSingleStep(step)
        spin.setSuffix(suffix)
        spin.valueChanged.connect(self._emit)
        section.addRow(label, spin, description)
        self._register(key, spin)

    def _dspin(self, section, key, label, low, high, step) -> None:
        spin = QDoubleSpinBox()
        spin.setRange(low, high)
        spin.setSingleStep(step)
        spin.setDecimals(2)
        spin.valueChanged.connect(self._emit)
        section.addRow(label, spin)
        self._register(key, spin)

    def _check(self, section, key, text) -> None:
        box = QCheckBox(text)
        box.toggled.connect(self._emit)
        section.addWidget(box)
        self._register(key, box)

    def _color(self, section, key, label, description="") -> None:
        button = ColorPickerButton("rgba(0, 0, 0, 1.00)")
        button.colorChanged.connect(self._emit)
        section.addRow(label, button, description)
        self._register(key, button)

    def _connect_dependencies(self) -> None:
        """Grise les réglages sans effet (ex. couleur d'ombre sans ombre)."""
        rules = (
            ("bg_enabled", ("bg_color", "bg_gradient_enabled", "bg_color_2", "border_radius")),
            ("bg_gradient_enabled", ("bg_color_2",)),
            ("show_reference", ("ref_size", "reference_style", "ref_color")),
            ("auto_fit", ("max_lines",)),
            ("text_shadow", ("shadow_color", "shadow_blur")),
            ("text_stroke", ("stroke_color", "stroke_width")),
            ("animation_enabled", ("animation_type", "animation_style",
                                   "animation_direction", "animation_duration")),
        )
        self._rules = rules
        for key, _deps in rules:
            self._widgets[key].toggled.connect(self._refresh_dependencies)
        self._widgets["accent_mode"].currentIndexChanged.connect(self._refresh_dependencies)
        self._refresh_dependencies()

    def _refresh_dependencies(self, *_args) -> None:
        for key, deps in self._rules:
            on = self._widgets[key].isChecked() and self._widgets[key].isEnabled()
            for dep in deps:
                self._widgets[dep].setEnabled(on)
        # Le dégradé dépend aussi du bandeau (règle en cascade).
        if not self._widgets["bg_enabled"].isChecked():
            self._widgets["bg_color_2"].setEnabled(False)
        self._widgets["accent_color"].setEnabled(
            self._widgets["accent_mode"].currentData() == "custom"
        )

    # ── Lecture / écriture ────────────────────────────────────────────

    def _emit(self, *_args) -> None:
        if not self._loading:
            self.changed.emit()

    def style(self) -> HdmiStyle:
        values: dict[str, Any] = {}
        for key, widget in self._widgets.items():
            if isinstance(widget, QComboBox):
                values[key] = widget.currentData()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                values[key] = widget.value()
            elif isinstance(widget, QCheckBox):
                values[key] = widget.isChecked()
            elif isinstance(widget, ColorPickerButton):
                values[key] = widget.color()
        return HdmiStyle.from_payload(values)

    def set_style(self, style: HdmiStyle) -> None:
        values = asdict(style.sanitized())
        self._loading = True
        try:
            for key, widget in self._widgets.items():
                value = values.get(key)
                if isinstance(widget, QComboBox):
                    idx = widget.findData(value)
                    if idx < 0 and key == "font_family":
                        # Police absente de la liste : on l'ajoute plutôt que
                        # de la remplacer en silence.
                        widget.addItem(str(value), value)
                        idx = widget.count() - 1
                    widget.setCurrentIndex(max(idx, 0))
                elif isinstance(widget, QSpinBox):
                    widget.setValue(int(value))
                elif isinstance(widget, QDoubleSpinBox):
                    widget.setValue(float(value))
                elif isinstance(widget, QCheckBox):
                    widget.setChecked(bool(value))
                elif isinstance(widget, ColorPickerButton):
                    widget.set_color(str(value))
        finally:
            self._loading = False
        if hasattr(self, "_rules"):
            self._refresh_dependencies()
        self.changed.emit()

    def apply_preset(self, params: dict[str, Any]) -> None:
        """Préréglage : valeurs par défaut + paramètres du préréglage.

        La police choisie est conservée : un préréglage change l'allure,
        pas l'identité typographique de l'église.
        """
        payload = asdict(HdmiStyle())
        payload.update(params)
        payload["font_family"] = self.style().font_family
        self.set_style(HdmiStyle.from_payload(payload))


def build_preset_bar(on_preset, on_copy_obs) -> QWidget:
    """Rangée de boutons de préréglages (+ « Partir du style OBS »)."""
    chips = QWidget()
    chips.setStyleSheet("background: transparent;")
    flow = FlowLayout(chips, margin=0, hSpacing=6, vSpacing=6)
    for name, hint, params in HDMI_STYLE_PRESETS:
        button = QPushButton(name)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip(hint)
        button.clicked.connect(lambda _checked=False, p=params: on_preset(p))
        flow.addWidget(button)
    copy_button = QPushButton("Partir du style OBS")
    copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
    copy_button.setToolTip("Recopie le style actuel de la page OBS, pour l'ajuster ici")
    copy_button.clicked.connect(lambda _checked=False: on_copy_obs())
    flow.addWidget(copy_button)
    return chips
