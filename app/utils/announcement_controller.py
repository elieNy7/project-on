from __future__ import annotations

"""Boucle d'annonces (façon ProPresenter).

Prend en charge une playlist d'annonces et l'affiche en boucle sur la
projection avec avance automatique. Tout contenu live en cours est mis en
instantané et **restauré à l'identique** à l'arrêt ; toute action manuelle
de navigation interrompt la boucle et restitue le live.
"""

import logging

log = logging.getLogger(__name__)

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class AnnouncementController(QObject):
    activeChanged = pyqtSignal(bool)

    def __init__(self, project_controller, playlist_dao, parent=None) -> None:
        super().__init__(parent)
        self._controller = project_controller
        self._playlist_dao = playlist_dao
        self._folder_id: int | None = None
        self._seconds_per_slide: int = 8
        self._active = False
        # Instantané du live avant la prise en charge des annonces.
        self._snapshot: tuple | None = None
        self._announce_slides: list[tuple[str, str]] = []
        self._index = 0

        self._timer = QTimer(self)
        self._timer.setInterval(max(2, self._seconds_per_slide) * 1000)
        self._timer.timeout.connect(self._advance)

    # ── État ───────────────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def folder_id(self) -> int | None:
        return self._folder_id

    def set_folder(self, folder_id: int | None) -> None:
        """Désigne la playlist utilisée comme boucle d'annonces."""
        if self._active:
            self.stop()
        self._folder_id = folder_id

    def set_seconds_per_slide(self, seconds: int) -> None:
        self._seconds_per_slide = max(2, min(120, int(seconds or 8)))
        self._timer.setInterval(self._seconds_per_slide * 1000)

    # ── Démarrage / arrêt ──────────────────────────────────────────────

    def start(self) -> bool:
        """Prend la main sur la sortie avec la playlist d'annonces."""
        if self._active or self._folder_id is None:
            return False
        entries = self._load_entries(self._folder_id)
        if not entries:
            return False

        controller = self._controller
        # Instantané du live (slides, titre, rangée courante) pour restauration.
        self._snapshot = (
            list(controller._program_slides),
            controller._program_title,
            list(controller._entry_start_rows),
            controller.current_row(),
        )

        self._announce_slides = entries
        self._index = 0
        self._active = True
        controller.load_program("custom", "Annonces", entries, split=False)
        self._timer.start()
        self.activeChanged.emit(True)
        return True

    def stop(self) -> None:
        """Arrête la boucle et restitue le live instantané."""
        if not self._active:
            return
        self._timer.stop()
        self._active = False
        snapshot = self._snapshot
        self._snapshot = None
        if snapshot is None:
            self.activeChanged.emit(False)
            return
        slides, title, entry_rows, current = snapshot
        controller = self._controller
        controller._program_slides = list(slides)
        controller._program_title = str(title or "")
        controller._entry_start_rows = list(entry_rows)
        controller.programChanged.emit(controller._program_title)
        if 0 <= current < len(controller._program_slides):
            controller.set_current_row(current)
        else:
            controller.show_logo()
        self.activeChanged.emit(False)

    def toggle(self) -> bool:
        if self._active:
            self.stop()
            return False
        return self.start()

    # ── Avance automatique ─────────────────────────────────────────────

    def _advance(self) -> None:
        if not self._active or not self._announce_slides:
            return
        self._index = (self._index + 1) % len(self._announce_slides)
        self._controller.set_current_row(self._index)

    # ── Chargement des items de la playlist ────────────────────────────

    def _load_entries(self, folder_id: int) -> list[tuple[str, str]]:
        try:
            items = self._playlist_dao.list_items(folder_id)
        except Exception:
            log.exception("Échec du chargement de la playlist d'annonces")
            return []
        entries: list[tuple[str, str]] = []
        title = "Annonces"
        try:
            folder = self._playlist_dao.get_folder(folder_id)
            title = str((folder or {}).get("name") or title)
        except Exception:
            pass
        for item in items or []:
            reference = str(item.get("reference") or "").strip() or title
            text = str(item.get("text") or "").strip()
            background = str(item.get("background") or "").strip()
            is_media = str(item.get("source") or "") == "media" and background
            if is_media or text:
                entries.append((reference, text if not is_media else ""))
        return entries
