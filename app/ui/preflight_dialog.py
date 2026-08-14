from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, QSize, QThreadPool, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui.icons import app_icon
from app.ui.theme import Colors, Radius, Spacing, Typography, get_scroll_area_style
from app.utils.settings import AppSettings
from app.utils.system_health import HealthCheck, HealthReport, run_system_health


class _HealthSignals(QObject):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)


class _HealthWorker(QRunnable):
    def __init__(self, signals: _HealthSignals, kwargs: dict) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._signals = signals
        self._kwargs = kwargs

    @pyqtSlot()
    def run(self) -> None:
        try:
            self._signals.completed.emit(run_system_health(**self._kwargs))
        except Exception as exc:
            self._signals.failed.emit(str(exc))


class _CheckRow(QFrame):
    _STATUS_STYLE = {
        "success": ("check-circle.svg", Colors.ACCENT_SUCCESS, "PRÊT"),
        "warning": ("info.svg", Colors.ACCENT_WARNING, "À VÉRIFIER"),
        "error": ("x-circle.svg", Colors.ACCENT_DANGER, "BLOQUANT"),
    }

    def __init__(self, check: HealthCheck, parent=None) -> None:
        super().__init__(parent)
        icon_name, color, label = self._STATUS_STYLE[check.status]
        self.setObjectName("PreflightCheckRow")
        self.setAccessibleName(f"{check.title}, {label}")
        self.setAccessibleDescription(check.detail)
        self.setStyleSheet(f"""
            QFrame#PreflightCheckRow {{
                background: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.LG}px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        icon = QLabel(self)
        icon.setFixedSize(30, 30)
        icon.setPixmap(app_icon(icon_name, color).pixmap(QSize(22, 22)))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(icon)

        copy = QVBoxLayout()
        copy.setSpacing(3)
        title = QLabel(check.title, self)
        title.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY};
            font-size: {Typography.SIZE_MD}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            background: transparent;
        """)
        copy.addWidget(title)
        detail = QLabel(check.detail, self)
        detail.setWordWrap(True)
        detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED};
            font-size: {Typography.SIZE_SM}px;
            background: transparent;
        """)
        copy.addWidget(detail)
        layout.addLayout(copy, 1)

        badge = QLabel(label, self)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(f"""
            color: {color};
            background: {Colors.BG_ELEVATED};
            border: 1px solid {color};
            border-radius: 999px;
            padding: 4px 10px;
            font-size: 10px;
            font-weight: {Typography.WEIGHT_BOLD};
        """)
        layout.addWidget(badge)


class PreflightDialog(QDialog):
    """Professional operator preflight and support-report dialog."""

    def __init__(
        self,
        *,
        database_path: Path,
        data_directory: Path,
        presentation_directory: Path,
        ndi_runtime_path: Path | None,
        settings: AppSettings,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Contrôle avant service")
        self.setMinimumSize(720, 620)
        self.resize(780, 680)
        self.setModal(True)
        self.setStyleSheet(f"QDialog {{ background: {Colors.BG_PRIMARY}; }}")

        self._report: HealthReport | None = None
        self._worker_signals = _HealthSignals(self)
        self._worker_signals.completed.connect(self._on_completed)
        self._worker_signals.failed.connect(self._on_failed)
        self._health_kwargs = {
            "database_path": Path(database_path),
            "data_directory": Path(data_directory),
            "presentation_directory": Path(presentation_directory),
            "screen_count": len(QApplication.screens()),
            "obs_mode": settings.obs.mode,
            "obs_port": settings.obs.web_port,
            "ndi_runtime_path": Path(ndi_runtime_path) if ndi_runtime_path else None,
        }

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(14)
        icon = QLabel(self)
        icon.setFixedSize(46, 46)
        icon.setPixmap(app_icon("check-circle.svg", Colors.ACCENT_PRIMARY).pixmap(32, 32))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(f"""
            background: {Colors.ACCENT_GLOW};
            border: 1px solid {Colors.BORDER_ACCENT};
            border-radius: 14px;
        """)
        header.addWidget(icon)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Contrôle avant service", self)
        title.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY};
            font-size: {Typography.SIZE_2XL}px;
            font-weight: {Typography.WEIGHT_BOLD};
        """)
        titles.addWidget(title)
        subtitle = QLabel(
            "Vérifiez les données, le stockage, les écrans et la sortie OBS avant de passer en direct.",
            self,
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {Typography.SIZE_SM}px;"
        )
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        root.addLayout(header)

        self._summary = QLabel("Analyse en cours…", self)
        self._summary.setAccessibleName("Résumé du contrôle")
        self._summary.setStyleSheet(f"""
            color: {Colors.ACCENT_SECONDARY};
            background: {Colors.BG_TERTIARY};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {Radius.MD}px;
            padding: 10px 14px;
            font-size: {Typography.SIZE_SM}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
        """)
        root.addWidget(self._summary)

        self._progress = QProgressBar(self)
        self._progress.setRange(0, 0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(4)
        self._progress.setStyleSheet(f"""
            QProgressBar {{ background: {Colors.BG_ELEVATED}; border: none; border-radius: 2px; }}
            QProgressBar::chunk {{ background: {Colors.ACCENT_PRIMARY}; border-radius: 2px; }}
        """)
        root.addWidget(self._progress)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(get_scroll_area_style())
        self._checks_container = QWidget(scroll)
        self._checks_container.setStyleSheet("background: transparent;")
        self._checks_layout = QVBoxLayout(self._checks_container)
        self._checks_layout.setContentsMargins(0, 0, 0, 0)
        self._checks_layout.setSpacing(9)
        self._loading_label = QLabel("Contrôle de la base de données…", self._checks_container)
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; padding: 36px; font-size: {Typography.SIZE_MD}px;"
        )
        self._checks_layout.addWidget(self._loading_label)
        self._checks_layout.addStretch(1)
        scroll.setWidget(self._checks_container)
        root.addWidget(scroll, 1)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self._copy_button = self._button("Copier le rapport", secondary=True)
        self._copy_button.setAccessibleDescription("Copie le diagnostic dans le presse-papiers")
        self._copy_button.clicked.connect(self._copy_report)
        actions.addWidget(self._copy_button)
        self._export_button = self._button("Exporter…", secondary=True)
        self._export_button.setAccessibleDescription("Enregistre un rapport texte pour le support")
        self._export_button.clicked.connect(self._export_report)
        actions.addWidget(self._export_button)
        actions.addStretch(1)
        self._rerun_button = self._button("Relancer", secondary=True)
        self._rerun_button.clicked.connect(self._start_check)
        actions.addWidget(self._rerun_button)
        close_button = self._button("Fermer")
        close_button.clicked.connect(self.accept)
        actions.addWidget(close_button)
        root.addLayout(actions)

        self._set_report_actions_enabled(False)
        self._start_check()

    def _button(self, text: str, *, secondary: bool = False) -> QPushButton:
        button = QPushButton(text, self)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(38)
        background = Colors.BG_ELEVATED if secondary else Colors.ACCENT_PRIMARY
        foreground = Colors.TEXT_PRIMARY if secondary else Colors.PROJECT_BUTTON_TEXT
        hover = Colors.SURFACE_HOVER if secondary else Colors.ACCENT_LIGHT
        button.setStyleSheet(f"""
            QPushButton {{
                background: {background}; color: {foreground};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px; padding: 8px 16px;
                font-size: {Typography.SIZE_SM}px;
                font-weight: {Typography.WEIGHT_SEMIBOLD};
            }}
            QPushButton:hover {{ background: {hover}; border-color: {Colors.BORDER_HOVER}; }}
            QPushButton:focus {{ border: 2px solid {Colors.BORDER_FOCUS}; }}
            QPushButton:disabled {{ color: {Colors.TEXT_DISABLED}; background: {Colors.BG_TERTIARY}; }}
        """)
        return button

    def _set_report_actions_enabled(self, enabled: bool) -> None:
        self._copy_button.setEnabled(enabled)
        self._export_button.setEnabled(enabled)

    def _clear_checks(self) -> None:
        while self._checks_layout.count():
            item = self._checks_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _start_check(self) -> None:
        self._report = None
        self._copy_button.setText("Copier le rapport")
        self._set_report_actions_enabled(False)
        self._rerun_button.setEnabled(False)
        self._progress.show()
        self._summary.setText("Analyse en cours…")
        self._clear_checks()
        loading = QLabel("Contrôle de la base de données…", self._checks_container)
        loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; padding: 36px; font-size: {Typography.SIZE_MD}px;"
        )
        self._checks_layout.addWidget(loading)
        self._checks_layout.addStretch(1)
        QThreadPool.globalInstance().start(
            _HealthWorker(self._worker_signals, self._health_kwargs)
        )

    def _on_completed(self, report: HealthReport) -> None:
        self._report = report
        self._progress.hide()
        self._rerun_button.setEnabled(True)
        self._set_report_actions_enabled(True)
        self._clear_checks()
        for check in report.checks:
            self._checks_layout.addWidget(_CheckRow(check, self._checks_container))
        self._checks_layout.addStretch(1)

        if report.overall_status == "success":
            color = Colors.ACCENT_SUCCESS
            text = "Tous les contrôles sont prêts pour le service."
        elif report.overall_status == "warning":
            color = Colors.ACCENT_WARNING
            text = f"Prêt avec {report.warnings} point(s) à vérifier avant le direct."
        else:
            color = Colors.ACCENT_DANGER
            text = f"{report.errors} problème(s) bloquant(s) doivent être corrigés."
        self._summary.setText(text)
        self._summary.setStyleSheet(f"""
            color: {color}; background: {Colors.BG_TERTIARY};
            border: 1px solid {color}; border-radius: {Radius.MD}px;
            padding: 10px 14px; font-size: {Typography.SIZE_SM}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
        """)

    def _on_failed(self, message: str) -> None:
        self._progress.hide()
        self._rerun_button.setEnabled(True)
        self._summary.setText("Le contrôle n'a pas pu être terminé.")
        self._clear_checks()
        label = QLabel(message, self._checks_container)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {Colors.ACCENT_DANGER}; padding: 24px;")
        self._checks_layout.addWidget(label)
        self._checks_layout.addStretch(1)

    def _copy_report(self) -> None:
        if self._report is None:
            return
        QApplication.clipboard().setText(self._report.to_text())
        self._copy_button.setText("Rapport copié")

    def _export_report(self) -> None:
        if self._report is None:
            return
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        default = Path(self._health_kwargs["data_directory"]) / f"diagnostic-{timestamp}.txt"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter le rapport de diagnostic",
            str(default),
            "Rapport texte (*.txt);;Tous les fichiers (*.*)",
        )
        if not file_path:
            return
        try:
            Path(file_path).write_text(self._report.to_text(), encoding="utf-8")
            QMessageBox.information(self, "Rapport exporté", "Le rapport a été enregistré.")
        except OSError as exc:
            QMessageBox.warning(self, "Export impossible", str(exc))
