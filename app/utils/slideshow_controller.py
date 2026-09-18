from __future__ import annotations

"""Diaporama de médias (images, vidéos, présentations) avec durée par média.

Prend la main sur la sortie live et enchaîne les médias choisis : chaque image
s'affiche sa durée, chaque vidéo passe au suivant dès qu'elle se termine (sauf
boucle activée). Le live en cours est mis en instantané et **restauré à
l'identique** à l'arrêt ; toute action manuelle rend la main à l'opérateur.
"""

import logging
from typing import Any

log = logging.getLogger(__name__)

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class SlideshowController(QObject):
    """Enchaînement automatique de médias, avec durée propre à chacun."""

    activeChanged = pyqtSignal(bool)

    def __init__(self, project_controller, parent=None) -> None:
        super().__init__(parent)
        self._controller = project_controller
        self._active = False
        self._snapshot: Any = None
        self._rows: list[int] = []  # rangées du programme, dans l'ordre
        self._durations: dict[int, int] = {}  # rangée -> secondes (0 = manuel)
        self._index = 0
        self._default_duration = 0
        self._video_row: int | None = None  # rangée qui attend la fin d'une vidéo

        # Minuterie à un seul tir : réarmée à chaque média avec SA durée.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._advance)

    # ── État ──────────────────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        return self._active

    def set_default_duration(self, seconds: int) -> None:
        """Durée appliquée aux médias qui n'en ont pas (0 = avance manuelle)."""
        try:
            value = max(0, min(3600, int(seconds)))
        except (TypeError, ValueError):
            value = 0
        if value == self._default_duration:
            return
        self._default_duration = value
        if self._active:
            self._arm_current_row()

    # ── Démarrage / arrêt ─────────────────────────────────────────────────

    def start(self, entries: list[dict[str, Any]]) -> bool:
        """Lance le diaporama sur une liste de médias (bibliothèque/playlist).

        Chaque entrée porte au minimum ``name`` et ``path`` (et ``duration_seconds``
        quand l'opérateur l'a réglée). Les présentations PowerPoint sont
        développées en autant de diapositives que de pages rendues.
        """
        medias = [m for m in (entries or []) if str(m.get("path") or "").strip()]
        if not medias:
            return False

        program_entries: list[tuple[str, str]] = []
        visuals: list[str] = []
        durations: list[int] = []
        for media in medias:
            path = str(media.get("path") or "")
            name = str(media.get("name") or "") or "Média"
            try:
                seconds = max(0, int(media.get("duration_seconds") or 0))
            except (TypeError, ValueError):
                seconds = 0
            if str(media.get("kind") or "") == "powerpoint":
                pages = self._pptx_pages(path)
                if not pages:
                    continue
                total = len(pages)
                for index, page in enumerate(pages, start=1):
                    program_entries.append((f"{name} ({index}/{total})", ""))
                    visuals.append(page)
                    durations.append(seconds)
                continue
            program_entries.append((name, ""))
            visuals.append(path)
            durations.append(seconds)

        if not program_entries:
            return False

        controller = self._controller
        # Instantané complet du live (slides, titre, rangée, état writer) pour
        # une restauration à l'identique, édition comprise.
        self._snapshot = controller.capture_live_state()

        if controller.load_program(
            "image",
            medias[0].get("slideshow_title") or "Diaporama",
            program_entries,
            split=False,
            entry_visuals=visuals,
            manual=False,
        ) < 0:
            self._snapshot = None
            return False

        self._build_row_map(durations)
        self._index = 0
        self._active = True
        self.activeChanged.emit(True)
        self._arm_current_row()
        return True

    def stop(self) -> None:
        """Arrête le diaporama et restitue le live instantané."""
        if not self._active:
            return
        self._timer.stop()
        self._active = False
        self._video_row = None
        self._rows = []
        self._durations = {}
        snapshot = self._snapshot
        self._snapshot = None
        self.activeChanged.emit(False)
        if snapshot is not None:
            self._controller.restore_live_state(snapshot)

    def abandon(self) -> None:
        """Clos le diaporama sans restauration (une autre source prend le live)."""
        if not self._active:
            return
        self._timer.stop()
        self._active = False
        self._video_row = None
        self._rows = []
        self._durations = {}
        self._snapshot = None
        self.activeChanged.emit(False)

    def toggle(self, entries: list[dict[str, Any]]) -> bool:
        if self._active:
            self.stop()
            return False
        return self.start(entries)

    # ── Enchaînement ──────────────────────────────────────────────────────

    def on_video_finished(self, video_path: str = "") -> None:
        """Fin de lecture d'une vidéo : on passe au média suivant.

        Appelé par la régie quand la projection signale la fin d'un média
        (hors boucle). Ignoré si la vidéo terminée n'est pas celle attendue.
        """
        if not self._active or self._video_row is None:
            return
        if self._video_row != self._current_row():
            self._video_row = None
            return
        self._video_row = None
        self._advance()

    def _advance(self) -> None:
        if not self._active or not self._rows:
            return
        self._index = (self._index + 1) % len(self._rows)
        self._controller.set_current_row(self._rows[self._index])
        self._arm_current_row()

    def _current_row(self) -> int:
        if not self._rows:
            return -1
        return self._rows[self._index % len(self._rows)]

    def _arm_current_row(self) -> None:
        """Arme la minuterie du média courant (ou attend la fin de la vidéo)."""
        self._timer.stop()
        self._video_row = None
        row = self._current_row()
        if row < 0:
            return
        slide = self._slide_at(row)
        video_path = str(getattr(slide, "video_path", "") or "") if slide else ""
        if video_path:
            loop = bool(self._controller.video_loop)
            if loop:
                # Vidéo en boucle : elle ne se termine jamais, pas d'avance.
                return
            # La vidéo donne le tempo : on avancera à sa fin de lecture.
            self._video_row = row
            return
        seconds = self._durations.get(row, 0) or self._default_duration
        if seconds <= 0:
            return
        self._timer.start(max(1, int(seconds)) * 1000)

    # ── Programme ─────────────────────────────────────────────────────────

    def _build_row_map(self, durations: list[int]) -> None:
        """Rangées réellement projetées → durée de chaque média d'origine.

        Une présentation PowerPoint produit plusieurs rangées pour une seule
        entrée : chaque page hérite de la durée du média.
        """
        self._rows = []
        self._durations = {}
        rows_total = max(0, int(getattr(self._controller, "program_count", 0) or 0))
        for row in range(rows_total):
            index = self._entry_index_for_row(row)
            if index is None or index >= len(durations):
                continue
            self._rows.append(row)
            self._durations[row] = int(durations[index])

    def _entry_index_for_row(self, row: int):
        mapper = getattr(self._controller, "entry_index_for_row", None)
        if mapper is None:
            return row
        try:
            return mapper(row)
        except Exception:
            return None

    def _slide_at(self, row: int):
        reader = getattr(self._controller, "slide_at_row", None)
        if reader is None:
            return None
        try:
            return reader(row)
        except Exception:
            return None

    @staticmethod
    def _pptx_pages(path: str) -> list[str]:
        """Pages rendues d'une présentation (cache disque, rendu si besoin)."""
        try:
            from app.utils.office_renderer import render_pptx_to_images

            return [str(p) for p in (render_pptx_to_images(path) or [])]
        except Exception:
            log.exception("Rendu PowerPoint impossible pour le diaporama : %s", path)
            return []
