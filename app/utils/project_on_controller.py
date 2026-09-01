from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from app.database.connection import Database
from app.utils.models import Slide, SourceType
from app.utils.slide_writer import SlideWriter
from app.utils.text_utils import strip_hymn_projection_label


class ProjectOnController(QObject):
    """Pilote la projection depuis un « programme live » en mémoire.

    Le programme est alimenté directement par la bibliothèque (versets,
    strophes, paragraphes de sermon/exposé, textes rapides). Chaque entrée
    est découpée en slides lisibles — les textes longs deviennent plusieurs
    parties « réf (i/n) » navigables avec next/prev pendant la projection.
    La sortie passe par ``SlideWriter`` (slide.json), lue par la fenêtre de
    projection locale, le serveur OBS et l'envoi NDI.
    """

    currentSlideChanged = pyqtSignal(object)
    currentRowChanged = pyqtSignal(int)
    programChanged = pyqtSignal(str)

    _MAX_CHARS_PER_SLIDE = 280
    _MIN_CHARS = 60

    def __init__(self, db: Database, presentation_dir: Path) -> None:
        super().__init__()
        self._db = db
        self._slide_writer = SlideWriter(presentation_dir=presentation_dir)
        self._program_slides: list[Slide] = []
        self._program_title: str = ""
        self._current_row = -1
        self._entry_start_rows: list[int | None] = []

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def db(self) -> Database:
        return self._db

    @property
    def slide_writer(self) -> SlideWriter:
        return self._slide_writer

    @property
    def program_title(self) -> str:
        """Titre lisible du programme en cours (sermon, chapitre, cantique…)."""
        return self._program_title

    @property
    def program_count(self) -> int:
        return len(self._program_slides)

    def current_slide(self) -> Slide | None:
        if 0 <= self._current_row < len(self._program_slides):
            return self._program_slides[self._current_row]
        return None

    # ── Program loading ────────────────────────────────────────────────────

    def load_program(
        self,
        source: SourceType,
        title: str,
        entries: list[tuple[str, str]],
        focus_entry: int = 0,
        split: bool = True,
        entry_visuals: list[str] | None = None,
    ) -> int:
        """Charge un programme de projection et projette l'entrée demandée.

        Chaque entrée (référence, texte) devient une ou plusieurs slides ;
        les textes longs sont découpés en parties « réf (i/n) ». Le programme
        précédent est remplacé, puis la première partie de ``focus_entry``
        passe en direct.

        ``entry_visuals`` (optionnel, même longueur que ``entries``) associe
        à chaque entrée un média : image ou vidéo (décision par extension).
        Une entrée à visuel produit une slide unique sans découpage —
        ``source`` bascule sur ``image``/``video``.
        """
        slides: list[Slide] = []
        entry_start_rows: list[int | None] = []
        for index, (reference, text) in enumerate(entries):
            ref_clean = self._clean_text(reference)
            text_clean = self._clean_text(text)
            visual = ""
            if entry_visuals is not None and index < len(entry_visuals):
                visual = str(entry_visuals[index] or "").strip()
            if source == "hymn" and not visual:
                text_clean = strip_hymn_projection_label(text_clean)

            if visual:
                # Média : une slide unique, jamais découpée.
                from app.utils.media_utils import is_video_file

                slides.append(
                    Slide(
                        source="video" if is_video_file(visual) else "image",
                        reference=ref_clean,
                        text="",
                        image_path=None if is_video_file(visual) else visual,
                        video_path=visual if is_video_file(visual) else None,
                    )
                )
                entry_start_rows.append(len(slides) - 1)
                continue

            if split:
                chunks = self._split_text(text_clean)
            else:
                chunks = [text_clean] if text_clean else []
            total = len(chunks)

            start: int | None = None
            for i, chunk in enumerate(chunks, start=1):
                ref = ref_clean
                if total > 1:
                    ref = f"{ref_clean} ({i}/{total})"
                chunk_clean = self._clean_text(chunk)
                if chunk_clean:
                    if start is None:
                        start = len(slides)
                    slides.append(
                        Slide(source=source, reference=ref, text=chunk_clean)
                    )
            entry_start_rows.append(start)

        if not slides:
            return -1

        self._program_slides = slides
        self._program_title = self._clean_text(title)
        self._entry_start_rows = entry_start_rows

        focus = entry_start_rows[focus_entry] if 0 <= focus_entry < len(entry_start_rows) else None
        if focus is None:
            focus = next((row for row in entry_start_rows if row is not None), 0)

        self._current_row = -1
        self.programChanged.emit(self._program_title)
        self.set_current_row(focus)
        return focus

    def add_custom_slides(self, title: str, texts: list[str], split: bool = True) -> int:
        """Projette immédiatement un texte rapide (annonce, texte libre).

        ``split`` découpe les blocs longs à la limite de 280 caractères ;
        False conserve chaque texte en une seule slide.
        """
        entries = [(title, text) for text in texts if str(text).strip()]
        if not entries:
            return -1
        return self.load_program("custom", title, entries, split=split)

    def load_media(self, path: str, name: str = "") -> int:
        """Projette immédiatement un média (image ou vidéo) plein écran."""
        from app.utils.media_utils import is_media_file

        if not is_media_file(path):
            return -1
        from app.utils.media_utils import media_kind

        label = name or Path(path).stem
        return self.load_program(
            "image" if media_kind(path) == "image" else "video",
            label,
            [(label, "")],
            entry_visuals=[path],
        )

    def set_video_playing(self, playing: bool) -> None:
        """Play/pause de la vidéo en direct (contrôle manuel opérateur)."""
        slide = self.current_slide()
        if slide is None or not slide.video_path:
            return
        self.slide_writer.set_video_playing(bool(playing))
        # Re-émettre la slide : l'aperçu et l'OBS suivent l'état de lecture.
        self.currentSlideChanged.emit(slide)

    def restart_video(self) -> None:
        """Stop : remet la vidéo en direct au début, en pause."""
        slide = self.current_slide()
        if slide is None or not slide.video_path:
            return
        self.slide_writer.set_video_reset()
        self.currentSlideChanged.emit(slide)

    @staticmethod
    def _clean_text(value: object) -> str:
        from app.utils.text_utils import clean_text

        return clean_text(value)

    def _split_text(self, text: str) -> list[str]:
        """Split text into balanced, readable slides (see text_utils)."""
        from app.utils.text_utils import split_text_into_slides

        return split_text_into_slides(text, self._MAX_CHARS_PER_SLIDE, self._MIN_CHARS)

    # ── Navigation ─────────────────────────────────────────────────────────

    def set_current_row(self, row: int) -> None:
        if not self._program_slides:
            self._current_row = -1
            return
        row = max(0, min(int(row), len(self._program_slides) - 1))
        slide = self._program_slides[row]
        self._current_row = row

        presentation_slide = slide
        if slide.source == "hymn" and " - " in slide.reference:
            presentation_slide = Slide(
                source=slide.source,
                reference=slide.reference.replace(" - ", "\n", 1),
                text=strip_hymn_projection_label(slide.text),
                background=slide.background,
                image_path=slide.image_path,
                video_path=slide.video_path,
            )
        elif slide.source == "hymn":
            presentation_slide = Slide(
                source=slide.source,
                reference=slide.reference,
                text=strip_hymn_projection_label(slide.text),
                background=slide.background,
                image_path=slide.image_path,
                video_path=slide.video_path,
            )

        self._slide_writer.write(presentation_slide)
        self.currentRowChanged.emit(row)
        self.currentSlideChanged.emit(presentation_slide)

    def current_row(self) -> int:
        return self._current_row

    def entry_index_for_row(self, row: int) -> int | None:
        """Index de l'entrée d'origine qui produit la slide ``row``.

        Permet à l'interface de retrouver l'élément de bibliothèque
        (paragraphe de sermon/exposé, strophe…) correspondant à la slide
        affichée. ``None`` si la slide ne correspond à aucune entrée.
        """
        if not 0 <= row < len(self._program_slides):
            return None
        entry = None
        for i, start in enumerate(self._entry_start_rows):
            if start is not None and start <= row:
                entry = i
            elif start is not None and start > row:
                break
        return entry

    def next_slide(self) -> None:
        if not self._program_slides:
            return
        if self._current_row == -1:
            self.set_current_row(0)
            return
        if self._current_row + 1 < len(self._program_slides):
            self.set_current_row(self._current_row + 1)

    def peek_next_slide(self) -> Slide | None:
        """Return the slide next_slide() would move to, without changing state."""
        if not self._program_slides:
            return None
        if self._current_row == -1:
            return self._program_slides[0]
        if self._current_row + 1 < len(self._program_slides):
            return self._program_slides[self._current_row + 1]
        return None

    def prev_slide(self) -> None:
        if not self._program_slides:
            return
        if self._current_row == -1:
            self.set_current_row(0)
            return
        if self._current_row - 1 >= 0:
            self.set_current_row(self._current_row - 1)

    # ── Live editing ───────────────────────────────────────────────────────

    def update_live_slide(self, reference: str, text: str) -> None:
        """Update the currently displayed slide (Quick Edit).

        Does not alter the stored program — only the live projection and
        the preview.
        """
        current_slide = self.current_slide()
        if current_slide is None:
            return
        text_clean = self._clean_text(text)
        if current_slide.source == "hymn":
            text_clean = strip_hymn_projection_label(text_clean)
        edited = Slide(
            source=current_slide.source,
            reference=self._clean_text(reference),
            text=text_clean,
            image_path=current_slide.image_path,
            background=current_slide.background,
            video_path=current_slide.video_path,
        )
        self._slide_writer.write(edited)
        self.currentSlideChanged.emit(edited)

    def show_logo(self) -> None:
        """Clear the current slide to show the logo/black screen."""
        self._current_row = -1
        self._slide_writer.write(None)
        self.currentRowChanged.emit(-1)
        self.currentSlideChanged.emit(None)
