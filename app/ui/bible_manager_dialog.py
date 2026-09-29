from __future__ import annotations

"""Gestion des Bibles : versions installées, catalogue libre, import de fichier."""

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui.obs_output_settings_dialog import DIALOG_STYLE
from app.ui.setting_cards import PageHeader, SettingRow, SettingSection
from app.ui.theme import Colors, Typography
from app.utils import bible_catalog as bc

log = logging.getLogger(__name__)


class _Relay(QObject):
    """Ramène les résultats des threads de téléchargement dans le thread UI."""

    progress = Signal(str, int)  # code, pourcentage
    finished = Signal(str, str)  # code, message d'erreur ("" = succès)


class BibleManagerDialog(QDialog):
    """Bibles : installer depuis le catalogue libre, importer un fichier, retirer."""

    biblesChanged = Signal()

    def __init__(self, db, parent=None, embedded: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bibles")
        self.setMinimumSize(560, 560)
        self.resize(640, 800)
        self.setStyleSheet(DIALOG_STYLE)
        self._db = db
        self._busy: set[str] = set()
        self._relay = _Relay(self)
        self._relay.progress.connect(self._on_progress)
        self._relay.finished.connect(self._on_finished)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        header = PageHeader(
            "Bibles",
            "Versions installées, Bibles libres de droits à télécharger, import de fichier.",
        )
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(content)
        self._layout.setSpacing(14)
        self._layout.addWidget(header)
        if embedded:
            self._layout.setContentsMargins(16, 16, 16, 16)
            main_layout.addWidget(content)
        else:
            self._layout.setContentsMargins(24, 20, 24, 16)
            scroll = QScrollArea(self)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidget(content)
            main_layout.addWidget(scroll, 1)

        self._installed_section = SettingSection("Bibles installées", "book.svg")
        self._layout.addWidget(self._installed_section)

        # ── Import d'un fichier ──
        import_section = SettingSection("Importer une Bible (fichier)", "upload.svg")
        import_btn = QPushButton("Choisir un fichier…")
        import_btn.clicked.connect(self._import_file)
        import_section.addRow(
            "Zefania XML, XML « Beblia » ou JSON",
            import_btn,
            "Pour une version dont l'église a les droits (lingala, swahili, tshiluba…)",
        )
        self._layout.addWidget(import_section)

        # ── Catalogue ──
        self._catalog_section = SettingSection("Bibles libres à télécharger", "download.svg")
        self._lang_filter = QComboBox()
        self._lang_filter.addItem("Toutes les langues", "")
        for lang in sorted({e.lang for e in bc.CATALOG}):
            self._lang_filter.addItem(bc.LANG_LABELS.get(lang, lang), lang)
        # Changer de langue ne relit pas la base (comptage des versets).
        self._lang_filter.currentIndexChanged.connect(lambda _i: self._rebuild(reload=False))
        self._catalog_section.addRow("Langue", self._lang_filter)
        self._layout.addWidget(self._catalog_section)

        note = QLabel(
            "Textes du domaine public publiés par le projet libre "
            "scrollmapper/bible_databases (GitHub). Le téléchargement demande "
            "une connexion Internet ; ensuite la Bible fonctionne hors-ligne."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; background: transparent; "
            f"border: none; font-size: {Typography.SIZE_META}px;"
        )
        self._layout.addWidget(note)
        self._layout.addStretch(1)

        self._installed_cache: dict[str, dict] | None = None
        self._dynamic_rows: list[QWidget] = []
        self._buttons: dict[str, QPushButton] = {}
        self._rebuild()

    # ── Construction des listes ──────────────────────────────────────

    def _installed(self) -> dict[str, dict]:
        try:
            with self._db.connect() as conn:
                return bc.installed_translations(conn)
        except Exception:
            log.exception("Lecture des Bibles installées impossible")
            return {}

    def _clear_rows(self) -> None:
        for row in self._dynamic_rows:
            row.setParent(None)
            row.deleteLater()
        self._dynamic_rows.clear()
        self._buttons.clear()

    def _add_row(self, section: SettingSection, label: str, widget: QWidget, desc: str) -> None:
        row = SettingRow(label, widget, desc)
        section._layout.addWidget(row)
        self._dynamic_rows.append(row)

    def _rebuild(self, *_args, reload: bool = True) -> None:
        self._clear_rows()
        if reload or self._installed_cache is None:
            self._installed_cache = self._installed()
        installed = self._installed_cache

        for module, info in sorted(
            installed.items(), key=lambda kv: str(kv[1].get("shortname") or kv[0]).lower()
        ):
            button = QPushButton("Retirer")
            button.clicked.connect(lambda _c=False, m=module: self._remove(m))
            lang = bc.LANG_LABELS.get(str(info.get("lang") or ""), info.get("lang") or "")
            desc = f"{info.get('name') or module} · {lang} · {info['verses']:,} versets".replace(",", " ")
            self._add_row(
                self._installed_section,
                str(info.get("shortname") or info.get("name") or module),
                button,
                desc,
            )
        if not installed:
            label = QLabel("Aucune Bible installée.")
            self._installed_section._layout.addWidget(label)
            self._dynamic_rows.append(label)

        wanted = str(self._lang_filter.currentData() or "")
        for entry in bc.CATALOG:
            if wanted and entry.lang != wanted:
                continue
            present = entry.module in installed
            button = QPushButton("Installée" if present else "Télécharger")
            button.setEnabled(not present and entry.code not in self._busy)
            if entry.code in self._busy:
                button.setText("…")
            button.clicked.connect(lambda _c=False, e=entry: self._download(e))
            self._buttons[entry.code] = button
            parts = [entry.name, bc.LANG_LABELS.get(entry.lang, entry.lang), entry.license]
            if entry.bundled:
                parts.append("fournie avec l'application")
            if entry.note:
                parts.append(entry.note)
            self._add_row(self._catalog_section, entry.shortname, button, " · ".join(parts))

    # ── Actions ──────────────────────────────────────────────────────

    def _download(self, entry: bc.BibleEntry) -> None:
        if entry.code in self._busy:
            return
        self._busy.add(entry.code)
        button = self._buttons.get(entry.code)
        if button is not None:
            button.setEnabled(False)
            button.setText("0 %")
        db_path = self._db.db_path

        def work() -> None:
            import sqlite3

            try:
                def progress(done: int, total: int) -> None:
                    if total:
                        self._relay.progress.emit(entry.code, int(done * 100 / total))

                payload = bc.download(entry, progress)
                try:
                    bc.save_payload(payload, bc.user_bibles_dir())
                except OSError:
                    log.warning("Copie locale de la Bible %s impossible", entry.code)
                conn = sqlite3.connect(db_path, timeout=30.0)
                try:
                    bc.install_payload(conn, payload)
                    bc.mark_removed(conn, entry.module, removed=False)
                    conn.commit()
                finally:
                    conn.close()
                self._relay.finished.emit(entry.code, "")
            except Exception as exc:  # réseau coupé, format…
                log.exception("Téléchargement de la Bible %s impossible", entry.code)
                self._relay.finished.emit(entry.code, str(exc) or exc.__class__.__name__)

        threading.Thread(target=work, name=f"bible-{entry.code}", daemon=True).start()

    def _on_progress(self, code: str, percent: int) -> None:
        button = self._buttons.get(code)
        if button is not None:
            button.setText(f"{percent} %")

    def _on_finished(self, code: str, error: str) -> None:
        self._busy.discard(code)
        if error:
            QMessageBox.warning(
                self,
                "Bible non téléchargée",
                "Le téléchargement a échoué. Vérifiez la connexion Internet puis "
                f"réessayez.\n\nDétail : {error}",
            )
        self._rebuild()
        if not error:
            self.biblesChanged.emit()

    def _remove(self, module: str) -> None:
        answer = QMessageBox.question(
            self,
            "Retirer la Bible",
            "Retirer cette Bible de l'application ? Elle pourra être "
            "réinstallée depuis le catalogue ou un fichier.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        with self._db.connect() as conn:
            bc.remove_translation(conn, module)
            bc.mark_removed(conn, module, removed=True)
            conn.commit()
        self._rebuild()
        self.biblesChanged.emit()

    def _import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importer une Bible",
            "",
            "Bibles (*.xml *.json *.gz);;Tous les fichiers (*)",
        )
        if not path:
            return
        languages = [f"{label} ({code})" for code, label in bc.LANG_LABELS.items()]
        choice, ok = QInputDialog.getItem(
            self, "Langue de la Bible", "Langue (noms des livres affichés) :",
            languages, 0, False,
        )
        if not ok:
            return
        lang = choice.rsplit("(", 1)[-1].rstrip(")")
        self.import_path(Path(path), lang=lang)

    def import_path(self, path: Path, *, lang: str = "fr", shortname: str = "") -> bool:
        try:
            payload = bc.load_bible_file(path, shortname=shortname, lang=lang)
            if len(payload.get("verses") or []) < 10:
                raise ValueError("aucun verset reconnu dans ce fichier")
            with self._db.connect() as conn:
                bc.install_payload(conn, payload)
                bc.mark_removed(conn, payload["metadata"]["module"], removed=False)
                conn.commit()
        except Exception as exc:
            log.exception("Import de Bible impossible : %s", path)
            QMessageBox.warning(self, "Import impossible", f"{path.name} : {exc}")
            return False
        self._rebuild()
        self.biblesChanged.emit()
        return True
