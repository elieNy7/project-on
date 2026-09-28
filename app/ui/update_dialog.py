from __future__ import annotations

"""Réglages → Mise à jour : vérifier, télécharger et installer la nouvelle version."""

import logging
import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from app.ui.obs_output_settings_dialog import DIALOG_STYLE
from app.ui.setting_cards import PageHeader, SettingSection
from app.ui.theme import Colors, Typography
from app.utils import updater
from app.version import __version__

log = logging.getLogger(__name__)


class _Relay(QObject):
    checked = Signal(object, str)  # UpdateInfo | None, erreur
    progress = Signal(int, int)
    downloaded = Signal(str, str)  # chemin, erreur


class UpdateDialog(QDialog):
    """Version installée, dernière version publiée, installation guidée."""

    autoCheckChanged = Signal(bool)

    def __init__(self, auto_check: bool = True, parent=None, embedded: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Mise à jour")
        self.setStyleSheet(DIALOG_STYLE)
        self._info: updater.UpdateInfo | None = None
        self._cancel = False
        self._relay = _Relay(self)
        self._relay.checked.connect(self._on_checked)
        self._relay.progress.connect(self._on_progress)
        self._relay.downloaded.connect(self._on_downloaded)

        layout = QVBoxLayout(self)
        margin = (16, 16, 16, 16) if embedded else (24, 20, 24, 16)
        layout.setContentsMargins(*margin)
        layout.setSpacing(14)
        layout.addWidget(PageHeader(
            "Mise à jour", "Nouvelles versions de Project-On, installées sans perdre vos données.",
        ))

        section = SettingSection("Version", "download.svg")
        self.current = QLabel(f"Project-On {__version__}")
        section.addRow("Version installée", self.current)
        self.check_btn = QPushButton("Vérifier maintenant")
        self.check_btn.clicked.connect(self.check)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        section.addRow("Dernière version", self.check_btn, "Nécessite Internet")
        section.addWidget(self.status)
        self.install_btn = QPushButton("Télécharger et installer")
        self.install_btn.setObjectName("AccentButton")
        self.install_btn.setVisible(False)
        self.install_btn.clicked.connect(self.download_and_install)
        section.addWidget(self.install_btn)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        section.addWidget(self.progress)
        self.auto = QCheckBox("Vérifier au démarrage quand Internet est disponible")
        self.auto.setChecked(bool(auto_check))
        self.auto.toggled.connect(self.autoCheckChanged.emit)
        section.addWidget(self.auto)
        layout.addWidget(section)

        note = QLabel(
            "L'installeur conserve la base, les cantiques, les playlists et les "
            "réglages. Project-On se ferme pendant l'installation."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: {Typography.SIZE_META}px;"
            " background: transparent; border: none;"
        )
        layout.addWidget(note)
        layout.addStretch(1)

    # ── Vérification ─────────────────────────────────────────────────

    def check(self) -> None:
        self.check_btn.setEnabled(False)
        self.status.setText("Recherche de la dernière version…")

        def work() -> None:
            try:
                self._relay.checked.emit(updater.check_latest(), "")
            except Exception as exc:
                self._relay.checked.emit(None, str(exc) or exc.__class__.__name__)

        threading.Thread(target=work, name="update-check", daemon=True).start()

    def _on_checked(self, info, error: str) -> None:
        self.check_btn.setEnabled(True)
        self._info = info
        if error:
            self.status.setText("Impossible de joindre GitHub (pas d'Internet ?).")
            self.install_btn.setVisible(False)
            return
        if info is None:
            self.status.setText("Aucune version installable publiée pour le moment.")
            self.install_btn.setVisible(False)
            return
        if updater.is_newer(info.version):
            size = f"{info.size / 1_000_000:.0f} Mo" if info.size else ""
            self.status.setText(f"Nouvelle version {info.version} disponible · {size}")
            self.install_btn.setVisible(True)
        else:
            self.status.setText(f"Project-On est à jour (dernière version : {info.version}).")
            self.install_btn.setVisible(False)

    # ── Téléchargement ───────────────────────────────────────────────

    def download_and_install(self) -> None:
        info = self._info
        if info is None:
            return
        from app.utils.app_paths import data_dir

        self.install_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.status.setText(f"Téléchargement de la version {info.version}…")
        folder = data_dir() / "updates"

        def work() -> None:
            try:
                path = updater.download(
                    info, folder,
                    progress=lambda done, total: self._relay.progress.emit(done, total),
                    cancelled=lambda: self._cancel,
                )
                self._relay.downloaded.emit(str(path), "")
            except Exception as exc:
                log.exception("Téléchargement de la mise à jour impossible")
                self._relay.downloaded.emit("", str(exc) or exc.__class__.__name__)

        threading.Thread(target=work, name="update-download", daemon=True).start()

    def _on_progress(self, done: int, total: int) -> None:
        if total:
            self.progress.setValue(int(done * 100 / total))

    def _on_downloaded(self, path: str, error: str) -> None:
        self.install_btn.setEnabled(True)
        if error:
            self.progress.setVisible(False)
            self.status.setText(f"Téléchargement interrompu : {error}")
            return
        self.progress.setValue(100)
        answer = QMessageBox.question(
            self,
            "Installer la mise à jour",
            "La nouvelle version est prête. Project-On va se fermer et "
            "l'installation démarrer. Continuer ?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.status.setText(f"Installeur prêt : {path}")
            return
        from pathlib import Path

        updater.launch_installer(Path(path))
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:
        self._cancel = True
        super().closeEvent(event)
