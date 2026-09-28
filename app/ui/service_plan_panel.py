from __future__ import annotations

"""Panneau « Déroulé du culte » (onglet Playlists).

Sections de la playlist (Louange, Annonces, Prédication…), avec une durée
prévue et, au choix, le slide qui ouvre la section : quand ce slide passe
en direct, la section démarre toute seule. L'heure de début prévue donne
les heures de chaque section ; l'avance ou le retard s'affiche en direct.
"""

from datetime import datetime
from typing import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import Colors, Spacing, Typography, get_compact_button_style
from app.utils.service_plan import (
    PlanSection,
    ServiceTracker,
    describe_delay,
    format_duration,
    parse_start_time,
)

SECTION_SUGGESTIONS = (
    "Accueil", "Prière", "Louange", "Adoration", "Annonces", "Offrandes",
    "Lecture biblique", "Prédication", "Sainte cène", "Bénédiction",
)


class SectionDialog(QDialog):
    def __init__(self, parent=None, name: str = "", duration: int = 10,
                 can_link: bool = False, linked: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Section du déroulé")
        form = QFormLayout(self)
        self.name = QLineEdit(name)
        self.name.setPlaceholderText(" · ".join(SECTION_SUGGESTIONS[:4]) + "…")
        form.addRow("Nom", self.name)
        self.duration = QSpinBox()
        self.duration.setRange(0, 600)
        self.duration.setSuffix(" min")
        self.duration.setValue(int(duration))
        form.addRow("Durée prévue", self.duration)
        self.link = QCheckBox("Démarre avec le slide sélectionné")
        self.link.setEnabled(can_link or linked)
        self.link.setChecked(linked)
        form.addRow("", self.link)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class ServicePlanPanel(QFrame):
    """Déroulé du culte d'une playlist, avec suivi de l'avance ou du retard."""

    sectionEntered = Signal(str)  # nom de la section (historique du culte)

    def __init__(
        self,
        dao,
        selected_item: Callable[[], int | None] = lambda: None,
        now: Callable[[], datetime] = datetime.now,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._dao = dao
        self._selected_item = selected_item
        self._now = now
        self._folder_id: int | None = None
        self._sections: list[dict] = []
        self._tracker = ServiceTracker()
        self.setObjectName("ServicePlanPanel")
        self.setStyleSheet(f"""
            QFrame#ServicePlanPanel {{
                background: {Colors.BG_CARD};
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 8px;
            }}
        """)

        self.toggle = QPushButton("Déroulé du culte", self)
        self.toggle.setCheckable(True)
        self.toggle.setStyleSheet(get_compact_button_style())
        self.toggle.toggled.connect(self._on_toggled)
        self.status = QLabel("", self)
        self.status.setStyleSheet(
            f"font-size: {Typography.SIZE_META}px; color: {Colors.TEXT_SECONDARY};"
            " background: transparent; border: none;"
        )
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self.toggle)
        header.addWidget(self.status, 1)

        # ── Corps (repliable) ──
        self.body = QWidget(self)
        self.body.setStyleSheet("background: transparent;")
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(Spacing.SM)

        top = QHBoxLayout()
        top.addWidget(QLabel("Début prévu"))
        self.start_edit = QLineEdit(self)
        self.start_edit.setPlaceholderText("ex. 9:30")
        self.start_edit.setMaximumWidth(80)
        self.start_edit.editingFinished.connect(self._on_start_time_edited)
        top.addWidget(self.start_edit)
        self.total_label = QLabel("", self)
        self.total_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; border: none;")
        top.addWidget(self.total_label, 1)
        self.run_btn = QPushButton("Démarrer", self)
        self.run_btn.clicked.connect(self._on_run_clicked)
        self.next_btn = QPushButton("Section suivante", self)
        self.next_btn.clicked.connect(self.next_section)
        top.addWidget(self.run_btn)
        top.addWidget(self.next_btn)
        body.addLayout(top)

        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["Section", "Durée", "Prévu", "Réel"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.table.setMinimumHeight(120)
        self.table.setShowGrid(False)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background: transparent; border: none;
                color: {Colors.TEXT_PRIMARY};
                selection-background-color: {Colors.ACCENT_GLOW};
                selection-color: {Colors.TEXT_PRIMARY};
            }}
            QHeaderView::section {{
                background: transparent; color: {Colors.TEXT_SECONDARY};
                border: none; border-bottom: 1px solid {Colors.BORDER_SUBTLE};
                padding: 4px 6px; font-size: {Typography.SIZE_META}px;
            }}
        """)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        body.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.add_btn = QPushButton("Ajouter", self)
        self.add_btn.clicked.connect(self._add_section)
        self.edit_btn = QPushButton("Modifier", self)
        self.edit_btn.clicked.connect(self._edit_section)
        self.delete_btn = QPushButton("Supprimer", self)
        self.delete_btn.clicked.connect(self._delete_section)
        self.up_btn = QPushButton("▲", self)
        self.up_btn.clicked.connect(lambda: self._move(-1))
        self.down_btn = QPushButton("▼", self)
        self.down_btn.clicked.connect(lambda: self._move(1))
        for button in (self.add_btn, self.edit_btn, self.delete_btn, self.up_btn,
                       self.down_btn, self.run_btn, self.next_btn):
            button.setStyleSheet(get_compact_button_style())
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        for button in (self.add_btn, self.edit_btn, self.delete_btn, self.up_btn, self.down_btn):
            actions.addWidget(button)
        actions.addStretch(1)
        body.addLayout(actions)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(Spacing.SM)
        layout.addLayout(header)
        layout.addWidget(self.body, 1)
        self.body.setVisible(False)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh_status)
        self._timer.start()
        self._refresh()

    # ── API ──────────────────────────────────────────────────────────

    @property
    def tracker(self) -> ServiceTracker:
        return self._tracker

    def set_folder(self, folder_id: int | None) -> None:
        if folder_id == self._folder_id:
            return
        self._folder_id = folder_id
        self._tracker = ServiceTracker()
        self._reload()

    def on_item_live(self, item_id: int) -> None:
        """Un slide de la playlist passe en direct : suivi automatique."""
        if self._tracker.enter_item(int(item_id), self._now()):
            self._announce()
            self._refresh()

    def next_section(self) -> None:
        now = self._now()
        if self._tracker.started_at is None:
            self._tracker.start(now)
        elif not self._tracker.next(now):
            return
        self._announce()
        self._refresh()

    # ── Données ──────────────────────────────────────────────────────

    def _reload(self) -> None:
        if self._folder_id is None:
            self._sections = []
            self.start_edit.setText("")
        else:
            self._sections = self._dao.list_sections(self._folder_id)
            self.start_edit.setText(self._dao.get_start_time(self._folder_id))
        self._tracker.sections = [
            PlanSection(int(s["id"]), str(s["name"]), int(s["duration_min"]),
                        int(s["item_id"]) if s.get("item_id") is not None else None)
            for s in self._sections
        ]
        self._refresh()

    def _reference_start(self) -> datetime | None:
        parsed = parse_start_time(self.start_edit.text())
        base = self._tracker.started_at or self._now()
        if parsed is None:
            return self._tracker.started_at
        return base.replace(hour=parsed[0], minute=parsed[1], second=0, microsecond=0)

    def _refresh(self) -> None:
        has_folder = self._folder_id is not None
        for widget in (self.add_btn, self.start_edit):
            widget.setEnabled(has_folder)
        has_sections = bool(self._sections)
        for widget in (self.edit_btn, self.delete_btn, self.up_btn, self.down_btn,
                       self.run_btn, self.next_btn):
            widget.setEnabled(has_sections)
        self.run_btn.setText("Arrêter" if self._tracker.started_at else "Démarrer")

        base = self._reference_start()
        selected = self.table.currentRow()
        self.table.setRowCount(len(self._sections))
        for row, section in enumerate(self._sections):
            name = str(section["name"])
            if section.get("item_id") is not None:
                name += "  ⟲"
            planned = (
                self._tracker.planned_start(row, base).strftime("%H:%M") if base else
                f"+{self._tracker.planned_offset_min(row)} min"
            )
            actual = self._tracker.actual_starts.get(row)
            cells = [name, f"{int(section['duration_min'])} min", planned,
                     actual.strftime("%H:%M") if actual else ""]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if row == self._tracker.current and self._tracker.running:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.table.setItem(row, column, item)
        if 0 <= selected < len(self._sections):
            self.table.selectRow(selected)
        total = self._tracker.total_min
        end = (
            f" · fin prévue {self._tracker.planned_start(len(self._sections), base):%H:%M}"
            if base and self._sections else ""
        )
        self.total_label.setText(f"{len(self._sections)} section(s) · {total} min{end}")
        self._refresh_status()

    def _refresh_status(self) -> None:
        status = self._tracker.status(self._now(), self._reference_start())
        if not status.get("running"):
            self.status.setText(
                "" if not self._sections else f"{len(self._sections)} section(s) — non démarré"
            )
            self.status.setStyleSheet(
                f"font-size: {Typography.SIZE_META}px; color: {Colors.TEXT_SECONDARY};"
                " background: transparent; border: none;"
            )
            return
        remaining = status["remaining"]
        timing = (
            f"reste {format_duration(remaining)}" if remaining >= 0
            else f"dépasse de {format_duration(remaining)}"
        )
        delay = status["delay"]
        color = (
            Colors.TEXT_SECONDARY if abs(delay) < 60
            else (Colors.ACCENT_WARNING if delay > 0 else Colors.ACCENT_SUCCESS)
        )
        self.status.setText(
            f"● {status['name']} · {timing} · {describe_delay(delay)} · "
            f"fin ≈ {status['expected_end']:%H:%M}"
        )
        self.status.setStyleSheet(
            f"font-size: {Typography.SIZE_META}px; color: {color}; font-weight: 600;"
            " background: transparent; border: none;"
        )

    def _announce(self) -> None:
        if self._tracker.running:
            self.sectionEntered.emit(self._tracker.sections[self._tracker.current].name)

    # ── Actions ──────────────────────────────────────────────────────

    def _on_toggled(self, checked: bool) -> None:
        self.body.setVisible(bool(checked))

    def _on_start_time_edited(self) -> None:
        if self._folder_id is None:
            return
        text = self.start_edit.text().strip()
        parsed = parse_start_time(text)
        value = f"{parsed[0]}:{parsed[1]:02d}" if parsed else ""
        self.start_edit.setText(value)
        self._dao.set_start_time(self._folder_id, value)
        self._refresh()

    def _on_run_clicked(self) -> None:
        if self._tracker.started_at is None:
            self._tracker.start(self._now())
            self._announce()
        else:
            self._tracker.stop()
        self._refresh()

    def _current_section(self) -> dict | None:
        row = self.table.currentRow()
        return self._sections[row] if 0 <= row < len(self._sections) else None

    def _add_section(self) -> None:
        if self._folder_id is None:
            return
        item_id = self._selected_item()
        dialog = SectionDialog(self, can_link=item_id is not None)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.name.text().strip():
            return
        self._dao.add_section(
            self._folder_id, dialog.name.text().strip(), dialog.duration.value(),
            item_id if dialog.link.isChecked() else None,
        )
        self._reload()

    def _edit_section(self) -> None:
        section = self._current_section()
        if section is None:
            return
        item_id = self._selected_item()
        dialog = SectionDialog(
            self, str(section["name"]), int(section["duration_min"]),
            can_link=item_id is not None, linked=section.get("item_id") is not None,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.name.text().strip():
            return
        linked = section.get("item_id")
        if dialog.link.isChecked():
            linked = item_id if item_id is not None else linked
        else:
            linked = None
        self._dao.update_section(
            int(section["id"]), dialog.name.text().strip(), dialog.duration.value(), linked
        )
        self._reload()

    def _on_double_click(self, row: int, _column: int) -> None:
        # Double-clic : l'opérateur force la section en cours.
        if self._tracker.enter(row, self._now()):
            self._announce()
            self._refresh()

    def _delete_section(self) -> None:
        section = self._current_section()
        if section is None:
            return
        self._dao.delete_section(int(section["id"]))
        self._reload()

    def _move(self, delta: int) -> None:
        section = self._current_section()
        if section is None:
            return
        row = self.table.currentRow()
        if self._dao.move_section(int(section["id"]), delta):
            self._reload()
            self.table.selectRow(max(0, min(row + delta, len(self._sections) - 1)))
