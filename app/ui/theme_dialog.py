from __future__ import annotations

"""Gestionnaire de thèmes de projection (façon ProPresenter).

Liste de thèmes éditables + assignation par type de contenu. Le thème actif
est édité via une copie de ``AppSettings.projection`` (le miroir historique) ;
les autres thèmes éditent leur propre style. Toute modification émet
``themesLiveChanged`` pour un aperçu immédiat dans la projection.
"""

import copy
import logging

log = logging.getLogger(__name__)

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.icons import app_icon
from app.ui.obs_output_settings_dialog import DIALOG_STYLE
from app.ui.settings_dialog import ProjectionSettingsDialog
from app.ui.setting_cards import PageHeader, SettingRow, SettingSection, fit_combos
from app.ui.theme import Colors, Radius, Typography, get_list_style
from app.utils.flow_layout import FlowLayout
from app.utils.settings import ProjectionSettings
from app.utils.themes import (
    ASSIGNABLE_SOURCES,
    DEFAULT_THEME_ID,
    Theme,
    builtin_theme_presets,
    make_theme_id,
)
from app.utils.translations import tr

_SOURCE_LABELS = {
    "bible": "Bible",
    "hymn": "Cantiques",
    "sermon": "Prédications",
    "expose": "Exposé",
    "custom": "Textes libres",
    "image": "Images",
    "video": "Vidéos",
}


class ThemeDialog(QDialog):
    themesLiveChanged = Signal(list, dict, str, object)
    # (themes, theme_assignments, active_theme_id, active_style)

    def __init__(self, settings, parent=None, embedded: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("themes_title"))
        self.setModal(True)
        self.setMinimumSize(820, 560)
        self.setStyleSheet(DIALOG_STYLE)

        # État éditable (copie profonde — annulable).
        self._themes: list[Theme] = copy.deepcopy(
            settings.themes
        ) or [Theme(id=DEFAULT_THEME_ID, name="Par défaut", style=copy.deepcopy(settings.projection))]
        self._assignments: dict[str, str] = dict(settings.theme_assignments)
        self._active_id: str = settings.active_theme_id
        if not any(t.id == self._active_id for t in self._themes):
            self._active_id = self._themes[0].id
        # Miroir du style du thème actif (deviendra settings.projection).
        self._active_style: ProjectionSettings = copy.deepcopy(settings.projection)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)
        root.addWidget(PageHeader(tr("themes_title"), tr("themes_intro")))

        # ── Thèmes ──
        themes_section = SettingSection("Thèmes", "palette.svg")
        self._theme_list = QListWidget(self)
        self._theme_list.setStyleSheet(get_list_style())
        self._theme_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._theme_list.currentRowChanged.connect(self._on_row_changed)
        themes_section.addWidget(self._theme_list)

        def _btn(text: str, tip: str, cb, icon: str = "") -> QPushButton:
            b = QPushButton(text, self)
            b.setToolTip(tip)
            if icon:
                b.setIcon(app_icon(icon, Colors.TEXT_PRIMARY))
            b.clicked.connect(cb)
            return b

        self._btn_activate = _btn(tr("themes_activate"), tr("themes_activate_tip"), self._on_activate, "check-circle.svg")
        self._btn_new = _btn(tr("themes_new"), tr("themes_new_tip"), self._on_new, "plus.svg")
        self._btn_duplicate = _btn(tr("themes_duplicate"), tr("themes_duplicate_tip"), self._on_duplicate, "copy.svg")
        self._btn_rename = _btn(tr("themes_rename"), tr("themes_rename_tip"), self._on_rename)
        self._btn_delete = _btn(tr("themes_delete"), tr("themes_delete_tip"), self._on_delete)
        self._btn_delete.setStyleSheet(f"QPushButton {{ color: {Colors.ACCENT_DANGER}; }}")
        self._btn_preset = _btn(tr("themes_presets"), tr("themes_presets_tip"), self._on_add_preset, "sparkles.svg")
        actions = QWidget(self)
        actions.setStyleSheet("background: transparent;")
        flow = FlowLayout(actions, margin=0, hSpacing=6, vSpacing=6)
        for b in (
            self._btn_activate,
            self._btn_new,
            self._btn_duplicate,
            self._btn_rename,
            self._btn_delete,
            self._btn_preset,
        ):
            flow.addWidget(b)
        themes_section.addWidget(actions)
        root.addWidget(themes_section)

        # ── Thème sélectionné ──
        selected_section = SettingSection("Thème sélectionné", "sparkles.svg")
        self._btn_edit_style = QPushButton(tr("themes_edit_style"), self)
        self._btn_edit_style.setIcon(app_icon("palette.svg", Colors.TEXT_PRIMARY))
        self._btn_edit_style.clicked.connect(self._on_edit_style)
        self._active_badge = QLabel(tr("themes_active_badge"), self)
        self._active_badge.setStyleSheet(
            f"color: {Colors.ACCENT_SUCCESS}; background: {Colors.ACCENT_SUCCESS_GLOW};"
            f" border-radius: {Radius.SM}px; padding: 3px 8px;"
            f" font-size: {Typography.SIZE_META}px; font-weight: {Typography.WEIGHT_SEMIBOLD};"
        )
        controls = QWidget(self)
        controls.setStyleSheet("background: transparent;")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)
        controls_layout.addWidget(self._active_badge)
        controls_layout.addWidget(self._btn_edit_style)
        selected_row = SettingRow("", controls)
        # The card title is the selected theme's name (see _refresh_detail).
        self._detail_label = selected_row.title_label
        selected_section.addWidget(selected_row)
        root.addWidget(selected_section)

        # ── Attribution par type de contenu ──
        assign_section = SettingSection(tr("themes_assign_title"), "layout.svg")
        self._assign_combos: dict[str, QComboBox] = {}
        for source in ASSIGNABLE_SOURCES:
            combo = QComboBox(self)
            _style_combo_popup(combo)
            assign_section.addRow(_SOURCE_LABELS.get(source, source), combo)
            self._assign_combos[source] = combo
            combo.currentIndexChanged.connect(
                lambda _ix, s=source: self._on_assignment_changed(s)
            )
        root.addWidget(assign_section)
        root.addStretch(1)

        # ── Pied : annuler / enregistrer ─────────────────────────────
        foot = QHBoxLayout()
        foot.addStretch()
        self._btn_cancel = QPushButton(tr("cancel"), self)
        self._btn_ok = QPushButton(tr("save"), self)
        self._btn_ok.setDefault(True)
        for b in (self._btn_cancel, self._btn_ok):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton {{ background: {Colors.BG_TERTIARY};"
                f" border: 1px solid {Colors.BORDER_DEFAULT}; border-radius: 8px;"
                f" padding: 8px 18px; color: {Colors.TEXT_PRIMARY};"
                f" font-size: {Typography.SIZE_CONTROL}px; font-weight: 600; }}"
                f"QPushButton:hover {{ border-color: {Colors.BORDER_HOVER}; }}"
                f"QPushButton#ok {{ background: {Colors.ACCENT_GLOW_STRONG};"
                f" border-color: {Colors.ACCENT_PRIMARY};"
                f" color: {Colors.ACCENT_LIGHT}; }}"
            )
        self._btn_ok.setObjectName("ok")
        foot.addWidget(self._btn_cancel)
        foot.addWidget(self._btn_ok)
        root.addLayout(foot)
        self._btn_cancel.clicked.connect(self.reject)
        self._btn_ok.clicked.connect(self.accept)
        if embedded:  # settings page: every change applies immediately
            self._btn_cancel.hide()
            self._btn_ok.hide()

        self._reload_list()
        self._reload_assignments()
        fit_combos(self)

    # ── État interne ──────────────────────────────────────────────────

    def _current_theme(self) -> Theme | None:
        row = self._theme_list.currentRow()
        if 0 <= row < len(self._themes):
            return self._themes[row]
        return None

    def _style_of(self, theme: Theme) -> ProjectionSettings:
        if theme.id == self._active_id:
            return self._active_style
        return theme.style

    def _reload_list(self, keep_id: str | None = None) -> None:
        target = keep_id or (self._current_theme().id if self._current_theme() else None)
        self._theme_list.blockSignals(True)
        self._theme_list.clear()
        for theme in self._themes:
            mark = "  ●" if theme.id == self._active_id else ""
            item = QListWidgetItem(f"{theme.name}{mark}")
            self._theme_list.addItem(item)
        if target:
            for row, theme in enumerate(self._themes):
                if theme.id == target:
                    self._theme_list.setCurrentRow(row)
                    break
        else:
            self._theme_list.setCurrentRow(0)
        self._theme_list.blockSignals(False)
        self._refresh_detail()
        self._reload_assignments()
        self._fit_list_height()

    def _fit_list_height(self) -> None:
        rows = max(1, min(self._theme_list.count(), 6))
        row_h = self._theme_list.sizeHintForRow(0) if self._theme_list.count() else 40
        frame = 2 * self._theme_list.frameWidth() + 12
        self._theme_list.setFixedHeight(rows * max(row_h, 36) + frame)

    def _refresh_detail(self) -> None:
        theme = self._current_theme()
        if theme is None:
            self._detail_label.setText("")
            return
        style = self._style_of(theme)
        self._detail_label.setText(
            f"{theme.name}  ·  {style.font_family} · {style.text_size}px ·"
            f" {style.slide_style}"
        )
        self._active_badge.setVisible(theme.id == self._active_id)
        self._btn_activate.setEnabled(theme.id != self._active_id)
        can_delete = len(self._themes) > 1 and theme.id != self._active_id
        self._btn_delete.setEnabled(can_delete)

    def _reload_assignments(self) -> None:
        names = [t.name for t in self._themes]
        ids = [t.id for t in self._themes]
        none_label = tr("themes_assign_none")
        for source, combo in self._assign_combos.items():
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(none_label, "")
            for theme_id, name in zip(ids, names):
                combo.addItem(name, theme_id)
            assigned = self._assignments.get(source, "")
            index = combo.findData(assigned)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)

    def _emit_live(self) -> None:
        self.themesLiveChanged.emit(
            copy.deepcopy(self._themes),
            dict(self._assignments),
            self._active_id,
            copy.deepcopy(self._active_style),
        )

    # ── Actions ───────────────────────────────────────────────────────

    def _on_row_changed(self, _row: int) -> None:
        self._refresh_detail()

    def _on_activate(self) -> None:
        theme = self._current_theme()
        if theme is None or theme.id == self._active_id:
            return
        previous = next((t for t in self._themes if t.id == self._active_id), None)
        if previous is not None:
            # Le style de l'ancien actif est déjà son miroir : rien à recopier.
            pass
        self._active_id = theme.id
        self._reload_list(keep_id=theme.id)
        self._emit_live()

    def _on_new(self) -> None:
        base = self._current_theme()
        style = copy.deepcopy(self._style_of(base)) if base else ProjectionSettings()
        name = self._unique_name(tr("themes_default_new_name"))
        theme_id = make_theme_id(name, [t.id for t in self._themes])
        theme = Theme(id=theme_id, name=name, style=style)
        self._themes.append(theme)
        self._reload_list(keep_id=theme_id)
        self._emit_live()

    def _on_duplicate(self) -> None:
        theme = self._current_theme()
        if theme is None:
            return
        name = self._unique_name(f"{theme.name} (copie)")
        theme_id = make_theme_id(name, [t.id for t in self._themes])
        copy_theme = Theme(
            id=theme_id, name=name, style=copy.deepcopy(self._style_of(theme))
        )
        self._themes.append(copy_theme)
        self._reload_list(keep_id=theme_id)
        self._emit_live()

    def _unique_name(self, base: str) -> str:
        names = {t.name for t in self._themes}
        if base not in names:
            return base
        n = 2
        while f"{base} {n}" in names:
            n += 1
        return f"{base} {n}"

    def _on_rename(self) -> None:
        theme = self._current_theme()
        if theme is None:
            return
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(
            self, tr("themes_rename"), tr("themes_name_label"), text=theme.name
        )
        name = str(name or "").strip()
        if not ok or not name:
            return
        theme.name = name
        self._reload_list(keep_id=theme.id)
        self._emit_live()

    def _on_delete(self) -> None:
        theme = self._current_theme()
        if (
            theme is None
            or theme.id == self._active_id
            or len(self._themes) <= 1
        ):
            return
        ret = QMessageBox.question(
            self,
            tr("themes_delete"),
            tr("themes_delete_confirm").format(name=theme.name),
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        self._themes = [t for t in self._themes if t.id != theme.id]
        self._assignments = {
            s: t for s, t in self._assignments.items() if t != theme.id
        }
        self._reload_list()
        self._emit_live()

    def _on_add_preset(self) -> None:
        existing_ids = [t.id for t in self._themes]
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        for preset in builtin_theme_presets():
            already = preset.id in existing_ids
            label = f"{preset.name}  (déjà présent)" if already else preset.name
            action = menu.addAction(label)
            action.setEnabled(not already)
            action.setData(preset.id)
        chosen = menu.exec(self._btn_preset.mapToGlobal(self._btn_preset.rect().bottomLeft()))
        if chosen is None:
            return
        preset = next(
            (p for p in builtin_theme_presets() if p.id == str(chosen.data())), None
        )
        if preset is None:
            return
        theme = Theme(
            id=make_theme_id(preset.id, existing_ids),
            name=preset.name,
            style=copy.deepcopy(preset.style),
        )
        self._themes.append(theme)
        self._reload_list(keep_id=theme.id)
        self._emit_live()

    def _on_edit_style(self) -> None:
        theme = self._current_theme()
        if theme is None:
            return
        # État sauvegardé AVANT ouverture (restauré si le sous-dialogue est annulé).
        self._saved_active_style = copy.deepcopy(self._active_style)
        self._saved_theme_style = copy.deepcopy(theme.style)
        working_copy = copy.deepcopy(self._style_of(theme))
        dlg = ProjectionSettingsDialog(working_copy, parent=self)

        def on_live(updated: ProjectionSettings) -> None:
            if theme.id == self._active_id:
                self._active_style = updated
            else:
                theme.style = updated
            self._refresh_detail()
            self._emit_live()

        dlg.settingsChanged.connect(on_live)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            on_live(dlg.read_settings())
            self._reload_list(keep_id=theme.id)
        else:
            # Annulation : restaurer le style d'avant l'édition.
            if theme.id == self._active_id:
                self._active_style = copy.deepcopy(self._saved_active_style)
            else:
                theme.style = copy.deepcopy(self._saved_theme_style)
            self._refresh_detail()
            self._emit_live()

    def _on_assignment_changed(self, source: str) -> None:
        combo = self._assign_combos.get(source)
        if combo is None:
            return
        theme_id = str(combo.currentData() or "")
        if theme_id:
            self._assignments[source] = theme_id
        else:
            self._assignments.pop(source, None)
        self._emit_live()

    # ── Résultat ──────────────────────────────────────────────────────

    def result_state(self) -> tuple[list[Theme], dict[str, str], str, ProjectionSettings]:
        """(thèmes, assignations, id actif, style actif → settings.projection)."""
        return (
            copy.deepcopy(self._themes),
            dict(self._assignments),
            self._active_id,
            copy.deepcopy(self._active_style),
        )


def _style_combo_popup(combo: QComboBox) -> None:
    from app.ui.settings_dialog import _style_combo

    _style_combo(combo)
