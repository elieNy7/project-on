from __future__ import annotations

"""Historique du culte : consultation et exports (rapport, CSV, SRT, images)."""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.ui.obs_output_settings_dialog import DIALOG_STYLE
from app.utils.montage_export import export_montage, load_obs_config
from app.utils.service_log import EVENT_LABELS, ServiceLog, to_csv, to_report, to_srt


class HistoryDialog(QDialog):
    def __init__(self, log: ServiceLog, presentation_dir: Path | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Historique du culte")
        self.setStyleSheet(DIALOG_STYLE)
        self.resize(900, 620)
        self._log = log
        self._presentation_dir = presentation_dir

        self.day = QComboBox()
        for day in log.days():
            self.day.addItem(day.strftime("%A %d/%m/%Y"), day)
        self.day.currentIndexChanged.connect(self._reload)
        self.summary = QLabel("")
        top = QHBoxLayout()
        top.addWidget(QLabel("Jour"))
        top.addWidget(self.day)
        top.addWidget(self.summary, 1)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Heure", "Type", "Référence", "Texte"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        actions = QHBoxLayout()
        for label, slot, tip in (
            ("Rapport (.txt)", self._export_report, "Déroulé lisible pour le rapport de culte"),
            ("Tableur (.csv)", self._export_csv, "Tout l'historique, ouvrable dans Excel"),
            ("Sous-titres (.srt)", self._export_srt, "Pour YouTube ou le montage vidéo"),
            ("Images transparentes…", self._export_montage,
             "PNG à fond transparent + SRT + minutage, pour le montage"),
        ):
            button = QPushButton(label)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addStretch(1)
        close = QPushButton("Fermer")
        close.clicked.connect(self.accept)
        actions.addWidget(close)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addLayout(actions)
        self._reload()

    def events(self):
        day = self.day.currentData()
        return self._log.events(day) if day is not None else []

    def _reload(self, *_args) -> None:
        events = self.events()
        self.table.setRowCount(len(events))
        for row, e in enumerate(events):
            for column, text in enumerate((
                e.time.strftime("%H:%M:%S"), EVENT_LABELS.get(e.event, e.event),
                e.reference.replace("\n", " — "), e.text.replace("\n", " / "),
            )):
                self.table.setItem(row, column, QTableWidgetItem(text))
        slides = sum(1 for e in events if e.event == "slide")
        if events:
            self.summary.setText(
                f"{slides} slide(s) · {events[0].time:%H:%M} → {events[-1].time:%H:%M}"
            )
        else:
            self.summary.setText("Aucun historique pour l'instant.")

    def _day_stem(self) -> str:
        day = self.day.currentData()
        return f"culte-{day.isoformat()}" if day is not None else "culte"

    def _save_text(self, title: str, suffix: str, content: str, filt: str) -> None:
        if not content.strip():
            QMessageBox.information(self, title, "Rien à exporter pour ce jour.")
            return
        path, _ = QFileDialog.getSaveFileName(self, title, f"{self._day_stem()}{suffix}", filt)
        if path:
            Path(path).write_text(content, encoding="utf-8-sig" if suffix == ".csv" else "utf-8")

    def _export_report(self) -> None:
        self._save_text("Exporter le rapport", ".txt", to_report(self.events()), "Texte (*.txt)")

    def _export_csv(self) -> None:
        self._save_text("Exporter le tableur", ".csv", to_csv(self.events()), "CSV (*.csv)")

    def _ask_origin(self) -> datetime | None:
        events = self.events()
        if not events:
            return None
        first = events[0].time
        text, ok = QInputDialog.getText(
            self, "Début de l'enregistrement",
            "Heure de début de la vidéo (HH:MM:SS) — les sous-titres sont calés dessus :",
            text=first.strftime("%H:%M:%S"),
        )
        if not ok:
            return None
        parsed = QTime.fromString(text.strip(), "HH:mm:ss")
        if not parsed.isValid():
            parsed = QTime.fromString(text.strip(), "H:mm")
        if not parsed.isValid():
            return first
        return first.replace(hour=parsed.hour(), minute=parsed.minute(),
                             second=parsed.second(), microsecond=0)

    def _export_srt(self) -> None:
        origin = self._ask_origin()
        if origin is None:
            return
        self._save_text("Exporter les sous-titres", ".srt",
                        to_srt(self.events(), origin), "Sous-titres (*.srt)")

    def _export_montage(self) -> None:
        origin = self._ask_origin()
        if origin is None:
            return
        folder = QFileDialog.getExistingDirectory(self, "Dossier des images de montage")
        if not folder:
            return
        target = Path(folder) / self._day_stem()
        report = export_montage(
            self.events(), target, load_obs_config(self._presentation_dir), origin=origin
        )
        QMessageBox.information(
            self, "Montage",
            f"{report['images']} image(s) transparente(s), sous-titres et minutage "
            f"enregistrés dans :\n{report['folder']}",
        )
