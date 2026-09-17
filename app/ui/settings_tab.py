from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

from PyQt6.QtCore import (
    QObject,
    QRunnable,
    Qt,
    QThreadPool,
    QUrl,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import (
    QColor,
    QDesktopServices,
    QGuiApplication,
    QLinearGradient,
    QPainter,
)
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui.icons import app_icon
from app.ui.theme import Colors, Radius, Typography, get_scroll_area_style
from app.utils.app_paths import app_db_path, data_dir, settings_path
from app.utils.backup_manager import create_database_backup
from app.utils.settings import AppSettings
from app.utils.translations import tr
from app.version import __version__


# ─── Thread-safe worker pattern ──────────────────────────────────────────────

class _WorkerSignals(QObject):
    """Signaux pour les workers de fond (thread-safe via Qt signal/slot)."""
    optimize_done  = pyqtSignal(bool, int, int)  # (success, saved_bytes, new_size)
    backup_done = pyqtSignal(bool, str, int, str)
    bundle_done = pyqtSignal(bool, str, int, str)


class _OptimizeWorker(QRunnable):
    """Exécute VACUUM + REINDEX dans un thread de fond."""

    def __init__(self, db_path, signals: _WorkerSignals) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._db_path = db_path
        self._signals = signals

    @pyqtSlot()
    def run(self) -> None:
        conn = None
        try:
            size_before = os.path.getsize(str(self._db_path))
            conn = sqlite3.connect(str(self._db_path))
            # Laisser VACUUM attendre posément un verrou détenu par l'application
            # plutôt qu'échouer immédiatement avec « database is locked ».
            conn.execute("PRAGMA busy_timeout = 10000;")
            conn.execute("VACUUM")
            conn.execute("REINDEX")
            conn.close()
            conn = None
            size_after = os.path.getsize(str(self._db_path))
            self._signals.optimize_done.emit(True, size_before - size_after, size_after)
        except Exception:
            log.exception("Échec de l'optimisation de la base")
            self._signals.optimize_done.emit(False, 0, 0)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass


class _BackupWorker(QRunnable):
    """Crée une sauvegarde SQLite cohérente sans bloquer l'interface."""

    def __init__(self, source: Path, destination: Path, signals: _WorkerSignals) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._source = source
        self._destination = destination
        self._signals = signals

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = create_database_backup(self._source, self._destination)
            self._signals.backup_done.emit(
                True,
                str(result.path),
                result.size_bytes,
                result.integrity_message,
            )
        except Exception as exc:
            self._signals.backup_done.emit(False, str(self._destination), 0, str(exc))


class _BundleWorker(QRunnable):
    """Archive complète (base + médias + fonds + paramètres) en arrière-plan."""

    def __init__(self, source: Path, destination: Path, signals: _WorkerSignals) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._source = source
        self._destination = destination
        self._signals = signals

    @pyqtSlot()
    def run(self) -> None:
        from app.utils.app_paths import backgrounds_dir, media_dir
        from app.utils.backup_manager import create_backup_bundle

        try:
            result = create_backup_bundle(
                self._source,
                self._destination,
                media_root=media_dir(),
                backgrounds_root=backgrounds_dir(),
                settings_file=settings_path(),
            )
            self._signals.bundle_done.emit(
                True, str(result.path), result.size_bytes, ""
            )
        except Exception as exc:
            self._signals.bundle_done.emit(False, str(self._destination), 0, str(exc))


# ─── Composants visuels ───────────────────────────────────────────────────────

class SettingsCard(QFrame):
    """Conteneur de section avec titre et style carte."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            SettingsCard {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {Colors.BG_TERTIARY},
                    stop:1 {Colors.BG_SECONDARY});
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.XL}px;
            }}
        """)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 18, 0, 10)
        self.main_layout.setSpacing(0)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(20, 0, 20, 10)
        lbl = QLabel(title, self)
        lbl.setStyleSheet(f"""
            font-size: {Typography.SIZE_CONTROL}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            color: {Colors.ACCENT_LIGHT};
            letter-spacing: 1.2px;
            background: transparent; border: none;
        """)
        hdr.addWidget(lbl)
        hdr.addStretch()
        self.main_layout.addLayout(hdr)

    def add_item(self, item: QWidget) -> None:
        self.main_layout.addWidget(item)


class SettingsItem(QWidget):
    """Item cliquable avec icône, titre, description et détail."""

    clicked = pyqtSignal()

    def __init__(
        self,
        title: str,
        description: str,
        icon_name: str,
        accent_color: str = Colors.TEXT_SECONDARY,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)
        self.setMinimumHeight(60)
        self.setStyleSheet(f"""
            QWidget#SettingsItem {{
                background: transparent;
                border-radius: {Radius.LG}px;
                margin: 0 8px;
            }}
            QWidget#SettingsItem:hover {{
                background: {Colors.GLASS_MEDIUM};
            }}
            QWidget#SettingsItem:focus {{
                border: 2px solid {Colors.BORDER_FOCUS};
                background: {Colors.GLASS_MEDIUM};
            }}
            QWidget#SettingsItem:disabled {{
                color: {Colors.TEXT_DISABLED};
                background: transparent;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 16, 10)
        layout.setSpacing(14)

        # Icône
        icon_frame = QFrame()
        icon_frame.setFixedSize(42, 42)
        icon_frame.setStyleSheet(f"""
            background: {Colors.BG_ELEVATED};
            border-radius: 12px;
            border: 1px solid {Colors.BORDER_SUBTLE};
        """)
        il = QVBoxLayout(icon_frame)
        il.setContentsMargins(0, 0, 0, 0)
        il.setAlignment(Qt.AlignmentFlag.AlignCenter)
        il.addWidget(self._make_icon_label(icon_name, accent_color))
        layout.addWidget(icon_frame)

        # Texte
        tl = QVBoxLayout()
        tl.setSpacing(2)
        tl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        title_lbl = QLabel(title, self)
        title_lbl.setStyleSheet(f"""
            font-size: {Typography.SIZE_MD}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            color: {Colors.TEXT_PRIMARY};
            background: transparent; border: none;
        """)
        tl.addWidget(title_lbl)
        if description:
            desc_lbl = QLabel(description, self)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet(f"""
                font-size: {Typography.SIZE_CONTROL}px;
                color: {Colors.TEXT_MUTED};
                background: transparent; border: none;
            """)
            tl.addWidget(desc_lbl)
        layout.addLayout(tl, 1)

        # Pill détail
        self._detail_label = QLabel("", self)
        self._detail_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_META}px;
            font-weight: {Typography.WEIGHT_MEDIUM};
            color: {Colors.TEXT_SECONDARY};
            background: {Colors.GLASS_MEDIUM};
            padding: 4px 12px;
            border-radius: 99px; border: 1px solid {Colors.BORDER_SUBTLE};
        """)
        self._detail_label.hide()
        layout.addWidget(self._detail_label)

        # Chevron
        arrow = QLabel(self)
        arrow.setPixmap(app_icon("chevron-right.svg", Colors.TEXT_DISABLED).pixmap(16, 16))
        arrow.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(arrow)

    @staticmethod
    def _make_icon_label(icon_name: str, color: str) -> QLabel:
        lbl = QLabel()
        lbl.setPixmap(app_icon(icon_name, color).pixmap(18, 18))
        lbl.setStyleSheet("background: transparent; border: none;")
        return lbl

    def set_detail(self, text: str) -> None:
        if text:
            self._detail_label.setText(text)
            self._detail_label.show()
        else:
            self._detail_label.hide()

    def mousePressEvent(self, event) -> None:
        if self.isEnabled() and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if self.isEnabled() and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class SettingsHeader(QFrame):
    """En-tête sobre de l'onglet paramètres."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(78)
        self.setMaximumHeight(100)
        self.setObjectName("SettingsHeader")
        self.setStyleSheet("#SettingsHeader { background: transparent; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 18, 34, 14)
        layout.setSpacing(6)

        title = QLabel(tr("settings_title"), self)
        title.setStyleSheet(f"""
            font-size: 24px;
            font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_PRIMARY};
            background: transparent;
        """)
        layout.addWidget(title)

        subtitle = QLabel(
            "Projection, diffusion OBS/NDI, apparence et outils",
            self,
        )
        subtitle.setStyleSheet(f"""
            font-size: {Typography.SIZE_MD}px;
            color: {Colors.TEXT_MUTED};
            background: transparent;
        """)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        g = QLinearGradient(0, 0, 0, r.height())
        g.setColorAt(0.0, QColor(Colors.BG_TERTIARY))
        g.setColorAt(0.55, QColor(Colors.BG_SECONDARY))
        g.setColorAt(1.0, QColor(Colors.BG_PRIMARY))
        painter.fillRect(r, g)
        painter.setPen(Qt.PenStyle.NoPen)
        accent = QColor(Colors.ACCENT_PRIMARY)
        accent.setAlpha(30)
        painter.setBrush(accent)
        painter.drawRect(0, r.height() - 1, r.width(), 1)


# ─── Onglet principal ─────────────────────────────────────────────────────────

class SettingsTab(QWidget):
    projectionSettingsRequested  = pyqtSignal()
    themesRequested              = pyqtSignal()
    stageSettingsRequested       = pyqtSignal()
    hdmiSettingsRequested        = pyqtSignal()
    tickerSettingsRequested      = pyqtSignal()
    obsSettingsRequested         = pyqtSignal()
    obsOutputSettingsRequested   = pyqtSignal()
    appearanceSettingsRequested  = pyqtSignal()
    shortcutsRequested           = pyqtSignal()
    aboutRequested               = pyqtSignal()
    preflightRequested           = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background: {Colors.BG_PRIMARY};")

        # Signaux partagés par les workers (thread-safe)
        self._worker_signals = _WorkerSignals()
        self._worker_signals.optimize_done.connect(self._on_optimize_done)
        self._worker_signals.backup_done.connect(self._on_backup_done)
        self._worker_signals.bundle_done.connect(self._on_bundle_done)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # En-tête
        self.header = SettingsHeader(self)
        layout.addWidget(self.header)

        # Zone scrollable
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(get_scroll_area_style())

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(32, 20, 32, 40)
        cl.setSpacing(16)

        # ── PROJECTION ───────────────────────────────────────────────
        display_card = SettingsCard("PROJECTION", content)
        self._projection_item = SettingsItem(
            tr("local_projection"), tr("local_projection_desc"),
            "monitor.svg", "#a78bfa", display_card,
        )
        display_card.add_item(self._projection_item)
        self._themes_item = SettingsItem(
            tr("themes_manager"), tr("themes_manager_desc"),
            "palette.svg", "#34d399", display_card,
        )
        display_card.add_item(self._themes_item)
        self._stage_item = SettingsItem(
            tr("stage_display"), tr("stage_display_desc"),
            "users.svg", "#60a5fa", display_card,
        )
        display_card.add_item(self._stage_item)
        self._hdmi_item = SettingsItem(
            "Sortie HDMI / mixeur",
            "Source d'incrustation verte pour ATEM, Roland V/AV et autres mélangeurs",
            "cast.svg", "#4ade80", display_card,
        )
        display_card.add_item(self._hdmi_item)
        self._ticker_item = SettingsItem(
            tr("ticker_settings"), tr("ticker_settings_desc"),
            "megaphone.svg", "#fbbf24", display_card,
        )
        display_card.add_item(self._ticker_item)
        cl.addWidget(display_card)

        # ── DIFFUSION ────────────────────────────────────────────────
        streaming_card = SettingsCard("DIFFUSION & OBS", content)
        self._obs_connect_item = SettingsItem(
            tr("connectivity"), tr("connectivity_desc"),
            "wifi.svg", "#60a5fa", streaming_card,
        )
        streaming_card.add_item(self._obs_connect_item)
        self._obs_style_item = SettingsItem(
            tr("lower_third_style"), tr("lower_third_style_desc"),
            "palette.svg", "#f472b6", streaming_card,
        )
        streaming_card.add_item(self._obs_style_item)
        cl.addWidget(streaming_card)

        # ── APPLICATION ──────────────────────────────────────────────
        app_card = SettingsCard("APPLICATION", content)
        self._appearance_item = SettingsItem(
            tr("appearance"), tr("appearance_desc"),
            "eye.svg", "#34d399", app_card,
        )
        app_card.add_item(self._appearance_item)
        self._shortcuts_item = SettingsItem(
            "Raccourcis clavier", "Consulter les commandes utiles pour piloter rapidement l'application",
            "zap.svg", "#facc15", app_card,
        )
        app_card.add_item(self._shortcuts_item)
        self._about_item = SettingsItem(
            tr("about"), tr("about_desc"),
            "info.svg", Colors.TEXT_MUTED, app_card,
        )
        app_card.add_item(self._about_item)
        cl.addWidget(app_card)

        # ── DONNÉES & MAINTENANCE ────────────────────────────────────
        data_card = SettingsCard("DONNÉES & MAINTENANCE", content)
        self._backup_db_item = SettingsItem(
            "Sauvegarder la base",
            "Créer une copie de sécurité du fichier de données principal",
            "database.svg", "#22c55e", data_card,
        )
        data_card.add_item(self._backup_db_item)
        self._backup_bundle_item = SettingsItem(
            "Sauvegarde complète (archive)",
            "Base + médias + fonds + paramètres dans un ZIP transportable, restaurable sur un autre poste",
            "database.svg", "#38bdf8", data_card,
        )
        data_card.add_item(self._backup_bundle_item)
        self._restore_bundle_item = SettingsItem(
            "Restaurer une archive",
            "Reconstruit un profil complet depuis un ZIP — toujours vers un NOUVEAU dossier, jamais le profil actif",
            "folder-open.svg", "#f472b6", data_card,
        )
        data_card.add_item(self._restore_bundle_item)
        self._optimize_item = SettingsItem(
            "Optimiser la base de données",
            "Compacte la base et rafraîchit les index pour accélérer les recherches",
            "zap.svg", "#f59e0b", data_card,
        )
        data_card.add_item(self._optimize_item)
        self._preflight_item = SettingsItem(
            "Contrôle avant service",
            "Vérifier les données, les écrans, le stockage et la sortie OBS avant le direct",
            "check-circle.svg", "#4ade80", data_card,
        )
        data_card.add_item(self._preflight_item)
        self._open_data_folder_item = SettingsItem(
            "Ouvrir le dossier des données",
            "Paramètres (settings.json), sauvegardes et fichiers de travail",
            "folder-open.svg", "#eab308", data_card,
        )
        data_card.add_item(self._open_data_folder_item)
        cl.addWidget(data_card)

        cl.addStretch(1)

        # Footer version
        footer = QLabel(f"Project-On v{__version__} · Onzième Heure Tab", content)
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(f"""
            font-size: {Typography.SIZE_META}px;
            font-weight: {Typography.WEIGHT_MEDIUM};
            color: {Colors.TEXT_DISABLED};
            letter-spacing: 0.4px;
            padding-top: 18px;
        """)
        cl.addWidget(footer)

        scroll.setWidget(content)
        layout.addWidget(scroll)

        # ── Connexions ────────────────────────────────────────────────
        self._projection_item.clicked.connect(self.projectionSettingsRequested.emit)
        self._themes_item.clicked.connect(self.themesRequested.emit)
        self._stage_item.clicked.connect(self.stageSettingsRequested.emit)
        self._hdmi_item.clicked.connect(self.hdmiSettingsRequested.emit)
        self._ticker_item.clicked.connect(self.tickerSettingsRequested.emit)
        self._obs_connect_item.clicked.connect(self.obsSettingsRequested.emit)
        self._obs_style_item.clicked.connect(self.obsOutputSettingsRequested.emit)
        self._appearance_item.clicked.connect(self.appearanceSettingsRequested.emit)
        self._shortcuts_item.clicked.connect(self.shortcutsRequested.emit)
        self._about_item.clicked.connect(self.aboutRequested.emit)
        self._backup_db_item.clicked.connect(self._on_backup_db)
        self._backup_bundle_item.clicked.connect(self._on_backup_bundle)
        self._restore_bundle_item.clicked.connect(self._on_restore_bundle)
        self._optimize_item.clicked.connect(self._on_optimize_db)
        self._preflight_item.clicked.connect(self.preflightRequested.emit)
        self._open_data_folder_item.clicked.connect(self._on_open_data_folder)

        # Chargement initial
        self.load_settings()

    # ─── API publique ────────────────────────────────────────────────

    def load_settings(self) -> None:
        """Recharge les paramètres et met à jour les détails affichés."""
        try:
            settings = AppSettings.load(settings_path())

            p = settings.projection
            style = str(getattr(p, "slide_style", "cinematic") or "cinematic").title()
            self._projection_item.set_detail(
                f"{style} · {p.font_family} · {p.text_size}px"
            )
            n_themes = len(getattr(settings, "themes", []) or [])
            n_assign = len(getattr(settings, "theme_assignments", {}) or {})
            self._themes_item.set_detail(f"{max(1, n_themes)} · {n_assign} assign.")
            self._stage_item.set_detail("F6")
            hdmi = getattr(settings, "hdmi", None)
            self._hdmi_item.set_detail(self._hdmi_detail(hdmi))
            self._ticker_item.set_detail(
                "Actif" if getattr(getattr(settings, "ticker", None), "enabled", False) else "Inactif"
            )

            o = settings.obs
            if o.mode == "web":
                self._obs_connect_item.set_detail(f"Web · port {o.web_port}")
            else:
                self._obs_connect_item.set_detail(f"NDI · {o.ndi_source_name}")

            self._obs_style_item.set_detail(
                "Style personnalisé" if o.output.bg_enabled else "Fond transparent"
            )

            a = settings.appearance
            theme_label = "Clair" if a.theme == "light" else "Sombre"
            self._appearance_item.set_detail(theme_label)
            self._shortcuts_item.set_detail("F1")
            self._about_item.set_detail(f"v{__version__}")
            self._backup_db_item.set_detail("Copie .db")
            self._optimize_item.set_detail("VACUUM")
            self._preflight_item.set_detail("Diagnostic")
            self._open_data_folder_item.set_detail("Dossier")

        except Exception as e:
            log.error("Erreur chargement paramètres: %s", e)

    @staticmethod
    def _hdmi_detail(hdmi) -> str:
        if hdmi is None or not getattr(hdmi, "enabled", False):
            return "Désactivée"
        key_names = {"green": "vert", "magenta": "magenta", "blue": "bleu"}
        key = key_names.get(str(getattr(hdmi, "key_color", "green")), "vert")
        name = str(getattr(hdmi, "screen", "auto") or "auto")
        if name == "auto":
            return f"Auto · chroma {key}"
        screen = next(
            (s for s in QGuiApplication.screens() if str(s.name() or "") == name),
            None,
        )
        if screen is None:
            return f"{name} · introuvable"
        geo = screen.geometry()
        return f"{name} · {geo.width()}×{geo.height()} · chroma {key}"

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.load_settings()

    @staticmethod
    def _timestamp() -> str:
        return datetime.now().strftime("%Y%m%d-%H%M%S")

    def _on_backup_db(self) -> None:
        db_path = app_db_path()
        if not db_path.exists():
            QMessageBox.warning(self, "Sauvegarde impossible", "La base de données est introuvable.")
            return

        from PyQt6.QtWidgets import QFileDialog

        default = data_dir() / f"project-on-db-{self._timestamp()}.db"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Sauvegarder la base",
            str(default),
            "Base Project-On (*.db);;Tous les fichiers (*.*)",
        )
        if not file_path:
            return

        self._backup_db_item.set_detail("Sauvegarde en cours...")
        self._backup_db_item.setEnabled(False)
        worker = _BackupWorker(db_path, Path(file_path), self._worker_signals)
        QThreadPool.globalInstance().start(worker)

    def _on_backup_done(
        self, success: bool, file_path: str, size_bytes: int, message: str
    ) -> None:
        self._backup_db_item.setEnabled(True)
        if success:
            self._backup_db_item.set_detail("Sauvegarde vérifiée")
            QMessageBox.information(
                self,
                "Sauvegarde terminée",
                f"Base sauvegardée et vérifiée :\n{Path(file_path).name}\n\n"
                f"Taille : {self._fmt_size(size_bytes)} · Intégrité SQLite : {message}",
            )
        else:
            self._backup_db_item.set_detail("Erreur")
            QMessageBox.warning(
                self,
                "Erreur sauvegarde",
                f"Impossible de sauvegarder la base.\n\n{message}",
            )

    def _on_backup_bundle(self) -> None:
        db_path = app_db_path()
        if not db_path.exists():
            QMessageBox.warning(self, "Sauvegarde impossible", "La base de données est introuvable.")
            return

        from PyQt6.QtWidgets import QFileDialog

        default = data_dir() / f"project-on-complet-{self._timestamp()}.zip"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Sauvegarde complète (archive)",
            str(default),
            "Archive Project-On (*.zip);;Tous les fichiers (*.*)",
        )
        if not file_path:
            return

        self._backup_bundle_item.set_detail("Archive en cours...")
        self._backup_bundle_item.setEnabled(False)
        worker = _BundleWorker(db_path, Path(file_path), self._worker_signals)
        QThreadPool.globalInstance().start(worker)

    def _on_bundle_done(
        self, success: bool, file_path: str, size_bytes: int, message: str
    ) -> None:
        self._backup_bundle_item.setEnabled(True)
        if success:
            self._backup_bundle_item.set_detail("Archive vérifiée")
            QMessageBox.information(
                self,
                "Sauvegarde complète terminée",
                f"Archive transportable créée :\n{Path(file_path).name}\n\n"
                f"Taille : {self._fmt_size(size_bytes)}\n\n"
                "Restauration : Réglages → « Restaurer une archive » sur le poste "
                "cible, dans un NOUVEAU dossier de profil.",
            )
        else:
            self._backup_bundle_item.set_detail("Erreur")
            QMessageBox.warning(
                self,
                "Erreur sauvegarde complète",
                f"Impossible de créer l'archive.\n\n{message}",
            )

    def _on_restore_bundle(self) -> None:
        from PyQt6.QtWidgets import QFileDialog

        archive, _ = QFileDialog.getOpenFileName(
            self,
            "Restaurer une archive Project-On",
            str(data_dir()),
            "Archive Project-On (*.zip);;Tous les fichiers (*.*)",
        )
        if not archive:
            return
        target = QFileDialog.getExistingDirectory(
            self, "Dossier PARENT du nouveau profil (le profil sera créé dedans)"
        )
        if not target:
            return
        profile_dir = Path(target) / "Project-On-restauré"
        if profile_dir.exists():
            QMessageBox.warning(
                self,
                "Restauration impossible",
                f"Le dossier cible existe déjà :\n{profile_dir}\n\n"
                "Choisissez un emplacement vierge.",
            )
            return
        confirm = QMessageBox.question(
            self,
            "Confirmer la restauration",
            "Le profil sera reconstruit dans :\n"
            f"{profile_dir}\n\n"
            "Le profil ACTIF n'est pas touché. Pour utiliser le profil restauré, "
            "fermez Project-On puis relancez-le avec ce dossier de données.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        from app.utils.backup_manager import restore_backup_bundle

        try:
            restored = restore_backup_bundle(Path(archive), profile_dir)
        except Exception as exc:
            self._restore_bundle_item.set_detail("Erreur")
            QMessageBox.warning(
                self, "Erreur de restauration", f"Restauration impossible.\n\n{exc}"
            )
            return
        self._restore_bundle_item.set_detail("Profil reconstruit")
        QMessageBox.information(
            self,
            "Restauration terminée",
            f"Profil reconstruit et vérifié :\n{restored}",
        )

    def _on_open_data_folder(self) -> None:
        from app.utils.app_paths import data_dir

        folder = data_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ─── Optimisation DB ─────────────────────────────────────────────

    def _on_optimize_db(self) -> None:
        """Lance VACUUM + REINDEX en arrière-plan."""
        db_path = app_db_path()
        if not db_path.exists():
            return

        # Confirmation
        reply = QMessageBox.question(
            self,
            "Optimiser la base",
            "Cette opération va compacter et réindexer la base de données.\n"
            "Durée estimée : quelques secondes.\n\nContinuer ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._optimize_item.set_detail("En cours...")
        self._optimize_item.setEnabled(False)

        worker = _OptimizeWorker(db_path, self._worker_signals)
        QThreadPool.globalInstance().start(worker)

    def _on_optimize_done(self, success: bool, saved_bytes: int, new_size: int) -> None:
        """Appelé sur le thread principal via signal Qt (thread-safe)."""
        self._optimize_item.setEnabled(True)

        if success:
            if saved_bytes > 1024:
                detail = f"{self._fmt_size(saved_bytes)} libérés"
            else:
                detail = "Déjà optimisé"
            self._optimize_item.set_detail(detail)
            QMessageBox.information(
                self, "Optimisation terminée",
                f"Base optimisée avec succès.\n{detail}"
            )
        else:
            self._optimize_item.set_detail("Erreur")
            QMessageBox.warning(
                self, "Erreur",
                "L'optimisation a échoué.\n"
                "Vérifiez que l'application n'est pas utilisée par un autre processus."
            )

    # ─── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _fmt_size(size_bytes: int) -> str:
        if size_bytes >= 1_073_741_824:
            return f"{size_bytes / 1_073_741_824:.1f} Go"
        if size_bytes >= 1_048_576:
            return f"{size_bytes / 1_048_576:.1f} Mo"
        return f"{size_bytes / 1024:.0f} Ko"

    # ─── Propriétés de compatibilité (utilisées dans main_window.py) ─

    @property
    def projection_btn(self):
        return self._projection_item

    @property
    def obs_btn(self):
        return self._obs_connect_item

    @property
    def obs_output_btn(self):
        return self._obs_style_item

    @property
    def about_btn(self):
        return self._about_item
