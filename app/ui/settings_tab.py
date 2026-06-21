from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
import os
import sqlite3

log = logging.getLogger(__name__)

from PyQt6.QtCore import (
    QObject,
    QRunnable,
    QSize,
    QThreadPool,
    Qt,
    QUrl,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QColor, QDesktopServices, QLinearGradient, QPainter
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui.icons import app_icon
from app.ui.theme import Colors, Radius, Spacing, Typography, get_scroll_area_style
from app.utils.app_paths import app_db_path, data_dir, settings_path
from app.utils.settings import AppSettings
from app.utils.translations import tr
from app.version import __version__


# ─── Thread-safe worker pattern ──────────────────────────────────────────────

class _WorkerSignals(QObject):
    """Signaux pour les workers de fond (thread-safe via Qt signal/slot)."""
    optimize_done  = pyqtSignal(bool, int, int)  # (success, saved_bytes, new_size)


class _OptimizeWorker(QRunnable):
    """Exécute VACUUM + REINDEX dans un thread de fond."""

    def __init__(self, db_path, signals: _WorkerSignals) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._db_path = db_path
        self._signals = signals

    @pyqtSlot()
    def run(self) -> None:
        try:
            size_before = os.path.getsize(str(self._db_path))
            conn = sqlite3.connect(str(self._db_path))
            conn.execute("VACUUM")
            conn.execute("REINDEX")
            conn.close()
            size_after  = os.path.getsize(str(self._db_path))
            self._signals.optimize_done.emit(True, size_before - size_after, size_after)
        except Exception:
            self._signals.optimize_done.emit(False, 0, 0)


# ─── Composants visuels ───────────────────────────────────────────────────────

class SettingsCard(QFrame):
    """Conteneur de section avec titre et style carte."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            SettingsCard {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {Colors.BG_SECONDARY},
                    stop:1 {Colors.BG_TERTIARY});
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
            font-size: 11px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            color: {Colors.ACCENT_LIGHT};
            letter-spacing: 1.2px;
            background: transparent; border: none;
        """)
        hdr.addWidget(lbl)
        hdr.addStretch()
        self.main_layout.addLayout(hdr)
        self._title_label = lbl
        self._hdr_layout  = hdr

    def add_item(self, item: QWidget) -> None:
        self.main_layout.addWidget(item)

    def add_header_widget(self, widget: QWidget) -> None:
        """Ajoute un widget (ex: bouton) à droite du titre de la carte."""
        self._hdr_layout.addWidget(widget)


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
            border: none;
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
                font-size: {Typography.SIZE_SM}px;
                color: {Colors.TEXT_MUTED};
                background: transparent; border: none;
            """)
            tl.addWidget(desc_lbl)
        layout.addLayout(tl, 1)

        # Pill détail
        self._detail_label = QLabel("", self)
        self._detail_label.setStyleSheet(f"""
            font-size: 11px;
            font-weight: {Typography.WEIGHT_MEDIUM};
            color: {Colors.TEXT_SECONDARY};
            background: {Colors.GLASS_MEDIUM};
            padding: 4px 12px;
            border-radius: 99px; border: none;
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
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class SettingsInfoItem(QWidget):
    """Ligne d'information non-cliquable (stats, valeurs)."""

    def __init__(
        self,
        title: str,
        value: str,
        icon_name: str,
        accent_color: str = Colors.TEXT_SECONDARY,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsInfoItem")
        self.setMinimumHeight(50)
        self.setStyleSheet("""
            QWidget#SettingsInfoItem {
                background: transparent;
                margin: 0 8px;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 16, 6)
        layout.setSpacing(14)

        # Icône
        icon_frame = QFrame()
        icon_frame.setFixedSize(34, 34)
        icon_frame.setStyleSheet(f"""
            background: {Colors.BG_ELEVATED};
            border-radius: 8px;
            border: none;
        """)
        il = QVBoxLayout(icon_frame)
        il.setContentsMargins(0, 0, 0, 0)
        il.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(app_icon(icon_name, accent_color).pixmap(16, 16))
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        il.addWidget(icon_lbl)
        layout.addWidget(icon_frame)

        # Titre
        title_lbl = QLabel(title, self)
        title_lbl.setStyleSheet(f"""
            font-size: {Typography.SIZE_SM}px;
            font-weight: {Typography.WEIGHT_MEDIUM};
            color: {Colors.TEXT_SECONDARY};
            background: transparent; border: none;
        """)
        layout.addWidget(title_lbl, 1)

        # Valeur pill
        self._value_label = QLabel(value, self)
        self._value_label.setStyleSheet(f"""
            font-size: 11px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            color: {Colors.TEXT_PRIMARY};
            background: {Colors.GLASS_MEDIUM};
            padding: 3px 10px;
            border-radius: 99px; border: none;
        """)
        layout.addWidget(self._value_label)

    def set_value(self, text: str) -> None:
        self._value_label.setText(text)


class _ShortcutRow(QWidget):
    """Ligne raccourci: description à gauche, touche badge à droite."""

    def __init__(self, shortcut: str, description: str, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(38)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 4, 20, 4)
        layout.setSpacing(12)

        desc_lbl = QLabel(description, self)
        desc_lbl.setStyleSheet(f"""
            font-size: {Typography.SIZE_SM}px;
            color: {Colors.TEXT_SECONDARY};
            background: transparent; border: none;
        """)
        layout.addWidget(desc_lbl, 1)

        key_lbl = QLabel(shortcut, self)
        key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        key_lbl.setStyleSheet(f"""
            font-size: 11px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            color: {Colors.TEXT_PRIMARY};
            background: {Colors.BG_ELEVATED};
            border: none;
            padding: 2px 10px;
            border-radius: 6px;
            font-family: 'Consolas', monospace;
        """)
        layout.addWidget(key_lbl)


class SettingsHeader(QFrame):
    """En-tête de l'onglet paramètres avec dégradé."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(90)
        self.setMaximumHeight(120)
        self.setObjectName("SettingsHeader")
        self.setStyleSheet("#SettingsHeader { background: transparent; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 22, 34, 16)
        layout.setSpacing(8)

        badge = QLabel("Onzième Heure Tab", self)
        badge.setStyleSheet(f"""
            font-size: 10px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            color: {Colors.ACCENT_LIGHT};
            background: rgba(230, 180, 76, 0.10);
            border: 1px solid rgba(230, 180, 76, 0.16);
            border-radius: 999px;
            padding: 5px 12px;
        """)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setMaximumWidth(160)
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)

        title = QLabel("Paramètres", self)
        title.setStyleSheet(f"""
            font-size: 24px;
            font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_PRIMARY};
            background: transparent;
        """)
        title.setText(tr("settings_title"))
        layout.addWidget(title)

        subtitle = QLabel("Préférences de diffusion et d'affichage", self)
        subtitle.setStyleSheet(f"""
            font-size: {Typography.SIZE_MD}px;
            color: {Colors.TEXT_MUTED};
            background: transparent;
        """)
        subtitle.setText("Gérez la projection, OBS, l'apparence et les outils de Project-On")
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
    obsSettingsRequested         = pyqtSignal()
    obsOutputSettingsRequested   = pyqtSignal()
    appearanceSettingsRequested  = pyqtSignal()
    shortcutsRequested           = pyqtSignal()
    aboutRequested               = pyqtSignal()
    settingsApplied              = pyqtSignal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background: {Colors.BG_PRIMARY};")

        # Signaux partagés par les workers (thread-safe)
        self._worker_signals = _WorkerSignals()
        self._worker_signals.optimize_done.connect(self._on_optimize_done)

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

        # ── AFFICHAGE ────────────────────────────────────────────────
        display_card = SettingsCard("AFFICHAGE", content)
        self._projection_item = SettingsItem(
            tr("local_projection"), tr("local_projection_desc"),
            "monitor.svg", "#a78bfa", display_card,
        )
        display_card.add_item(self._projection_item)
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

        config_card = SettingsCard("CONFIGURATION", content)
        self._export_settings_item = SettingsItem(
            "Exporter les paramètres",
            "Créer une copie JSON réutilisable de tous les réglages de l'application",
            "file-plus.svg", "#38bdf8", config_card,
        )
        config_card.add_item(self._export_settings_item)
        self._import_settings_item = SettingsItem(
            "Importer des paramètres",
            "Restaurer une configuration exportée et l'appliquer immédiatement",
            "folder-open.svg", "#818cf8", config_card,
        )
        config_card.add_item(self._import_settings_item)
        self._reset_settings_item = SettingsItem(
            "Réinitialiser les paramètres",
            "Revenir aux réglages professionnels par défaut sans toucher aux données",
            "settings.svg", "#fb7185", config_card,
        )
        config_card.add_item(self._reset_settings_item)
        self._settings_file_info = SettingsInfoItem(
            "Fichier paramètres", "—", "settings.svg", "#94a3b8", config_card
        )
        config_card.add_item(self._settings_file_info)
        cl.addWidget(config_card)

        # ── DONNÉES & STOCKAGE ───────────────────────────────────────
        data_card = SettingsCard("DONNÉES & STOCKAGE", content)

        self._backup_db_item = SettingsItem(
            "Sauvegarder la base",
            "Créer une copie de sécurité du fichier de données principal",
            "database.svg", "#22c55e", data_card,
        )
        data_card.add_item(self._backup_db_item)
        self._open_data_folder_item = SettingsItem(
            "Ouvrir le dossier des données",
            "Accéder aux paramètres, sauvegardes et fichiers de travail",
            "folder-open.svg", "#eab308", data_card,
        )
        data_card.add_item(self._open_data_folder_item)
        cl.addWidget(data_card)

        # ── PERFORMANCE ──────────────────────────────────────────────
        perf_card = SettingsCard("MAINTENANCE", content)
        self._optimize_item = SettingsItem(
            "Optimiser la base de données",
            "Compacte la base et rafraîchit les index pour accélérer les recherches",
            "zap.svg", "#f59e0b", perf_card,
        )
        perf_card.add_item(self._optimize_item)
        cl.addWidget(perf_card)

        # ── RACCOURCIS CLAVIER ───────────────────────────────────────
        shortcuts_card = SettingsCard("RACCOURCIS ESSENTIELS", content)
        shortcuts = [
            ("Ctrl+F",    "Recherche dans l'onglet actif"),
            ("Ctrl+G",    "Recherche globale paragraphes"),
            ("Ctrl+1..5", "Changer d'onglet"),
            ("Ctrl+Z",    "Annuler (playlist)"),
            ("F1",        "Aide raccourcis"),
            ("F5",        "Projeter / Arrêter"),
            ("Haut / Bas", "Naviguer dans la playlist"),
            ("B",         "Masquer / Afficher l'écran"),
            ("Suppr",     "Supprimer de la playlist"),
            ("Entrée",    "Ajouter à la playlist"),
        ]
        for key, desc in shortcuts:
            shortcuts_card.add_item(_ShortcutRow(key, desc))
        cl.addWidget(shortcuts_card)

        cl.addStretch(1)

        # Footer version
        footer = QLabel(f"Project-On v{__version__}\nOnzième Heure Tab", content)
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(f"""
            font-size: 11px;
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
        self._obs_connect_item.clicked.connect(self.obsSettingsRequested.emit)
        self._obs_style_item.clicked.connect(self.obsOutputSettingsRequested.emit)
        self._appearance_item.clicked.connect(self.appearanceSettingsRequested.emit)
        self._shortcuts_item.clicked.connect(self.shortcutsRequested.emit)
        self._about_item.clicked.connect(self.aboutRequested.emit)
        self._export_settings_item.clicked.connect(self._on_export_settings)
        self._import_settings_item.clicked.connect(self._on_import_settings)
        self._reset_settings_item.clicked.connect(self._on_reset_settings)
        self._backup_db_item.clicked.connect(self._on_backup_db)
        self._open_data_folder_item.clicked.connect(self._on_open_data_folder)
        self._optimize_item.clicked.connect(self._on_optimize_db)

        # Chargement initial
        self.load_settings()

    # ─── API publique ────────────────────────────────────────────────

    def load_settings(self) -> None:
        """Recharge les paramètres et met à jour les détails affichés."""
        try:
            path     = settings_path()          # chemin correct (dev + prod)
            settings = AppSettings.load(path)

            p = settings.projection
            style = str(getattr(p, "slide_style", "cinematic") or "cinematic").title()
            self._projection_item.set_detail(
                f"{style} · {p.font_family} · {p.text_size}px"
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
            lang_label = "Francais" if a.language == "fr" else "English"
            self._appearance_item.set_detail(f"{theme_label} - {lang_label}")
            self._shortcuts_item.set_detail("F1")
            self._about_item.set_detail(f"v{__version__}")
            self._export_settings_item.set_detail("JSON")
            self._import_settings_item.set_detail("Appliquer")
            self._reset_settings_item.set_detail("Défauts")
            self._backup_db_item.set_detail("Copie .db")
            self._open_data_folder_item.set_detail("Dossier")
            self._settings_file_info.set_value(str(path.name))

        except Exception as e:
            log.error("Erreur chargement paramètres: %s", e)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.load_settings()

    @staticmethod
    def _timestamp() -> str:
        return datetime.now().strftime("%Y%m%d-%H%M%S")

    def _backup_current_settings_file(self) -> Path | None:
        path = settings_path()
        if not path.exists():
            return None
        backup = path.with_name(f"{path.stem}.backup-{self._timestamp()}{path.suffix}")
        shutil.copy2(path, backup)
        return backup

    def _read_external_settings(self, file_path: str) -> AppSettings | None:
        path = Path(file_path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Import impossible",
                f"Le fichier sélectionné n'est pas un JSON valide.\n\n{exc}",
            )
            return None

        if not isinstance(payload, dict) or not any(
            key in payload for key in ("projection", "obs", "appearance")
        ):
            QMessageBox.warning(
                self,
                "Import impossible",
                "Ce fichier ne ressemble pas à une configuration Project-On.",
            )
            return None
        return AppSettings.load(path)

    def _on_export_settings(self) -> None:
        default = data_dir() / f"project-on-settings-{self._timestamp()}.json"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter les paramètres",
            str(default),
            "Paramètres Project-On (*.json);;Tous les fichiers (*.*)",
        )
        if not file_path:
            return

        try:
            settings = AppSettings.load(settings_path())
            settings.save(Path(file_path))
            QMessageBox.information(
                self,
                "Export terminé",
                "Les paramètres ont été exportés avec succès.",
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Erreur export",
                f"Impossible d'exporter les paramètres.\n\n{exc}",
            )

    def _on_import_settings(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Importer des paramètres",
            str(data_dir()),
            "Paramètres Project-On (*.json);;Tous les fichiers (*.*)",
        )
        if not file_path:
            return

        imported = self._read_external_settings(file_path)
        if imported is None:
            return

        reply = QMessageBox.question(
            self,
            "Importer les paramètres",
            "Les paramètres actuels seront sauvegardés puis remplacés.\n"
            "La projection et OBS seront mis à jour immédiatement.\n\nContinuer ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            backup = self._backup_current_settings_file()
            imported.save(settings_path())
            self.settingsApplied.emit(imported)
            self.load_settings()
            msg = "Paramètres importés avec succès."
            if backup is not None:
                msg += f"\n\nSauvegarde créée : {backup.name}"
            QMessageBox.information(self, "Import terminé", msg)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Erreur import",
                f"Impossible d'importer les paramètres.\n\n{exc}",
            )

    def _on_reset_settings(self) -> None:
        reply = QMessageBox.warning(
            self,
            "Réinitialiser les paramètres",
            "Tous les réglages seront remis aux valeurs par défaut.\n"
            "Les sermons, cantiques, playlists et données ne seront pas supprimés.\n\n"
            "Continuer ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            backup = self._backup_current_settings_file()
            defaults = AppSettings()
            defaults.save(settings_path())
            self.settingsApplied.emit(defaults)
            self.load_settings()
            msg = "Paramètres réinitialisés."
            if backup is not None:
                msg += f"\n\nSauvegarde créée : {backup.name}"
            QMessageBox.information(self, "Réinitialisation terminée", msg)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Erreur",
                f"Impossible de réinitialiser les paramètres.\n\n{exc}",
            )

    def _on_backup_db(self) -> None:
        db_path = app_db_path()
        if not db_path.exists():
            QMessageBox.warning(self, "Sauvegarde impossible", "La base de données est introuvable.")
            return

        default = data_dir() / f"project-on-db-{self._timestamp()}.db"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Sauvegarder la base",
            str(default),
            "Base Project-On (*.db);;Tous les fichiers (*.*)",
        )
        if not file_path:
            return

        try:
            shutil.copy2(db_path, Path(file_path))
            QMessageBox.information(
                self,
                "Sauvegarde terminée",
                f"Base sauvegardée :\n{Path(file_path).name}",
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Erreur sauvegarde",
                f"Impossible de sauvegarder la base.\n\n{exc}",
            )

    def _on_open_data_folder(self) -> None:
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

        self._optimize_item.set_detail("⏳ En cours…")
        self._optimize_item.setEnabled(False)

        worker = _OptimizeWorker(db_path, self._worker_signals)
        QThreadPool.globalInstance().start(worker)

    def _on_optimize_done(self, success: bool, saved_bytes: int, new_size: int) -> None:
        """Appelé sur le thread principal via signal Qt (thread-safe)."""
        self._optimize_item.setEnabled(True)

        if success:
            if saved_bytes > 1024:
                detail = f"✓  {self._fmt_size(saved_bytes)} libérés"
            else:
                detail = "✓  Déjà optimisé"
            self._optimize_item.set_detail(detail)
            QMessageBox.information(
                self, "Optimisation terminée",
                f"Base optimisée avec succès.\n{detail.replace('✓  ', '')}"
            )
        else:
            self._optimize_item.set_detail("✗  Erreur")
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
