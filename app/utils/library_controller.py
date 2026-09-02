from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from app.database.connection import Database


class _DbWorker(QRunnable):
    """Run a DB function in the thread pool, then call back on the main thread."""

    class _Signals(QObject):
        finished = pyqtSignal(object)

    def __init__(self, fn: Callable[[], Any], callback: Callable[[Any], None]) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._fn = fn
        self._signals = self._Signals()
        self._signals.finished.connect(callback)

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self._fn()
        except Exception:
            result = None
        self._signals.finished.emit(result)


from app.database.dao_bible import BibleDao
from app.database.dao_hymns import HymnsDao
from app.database.dao_media import MediaDao
from app.database.dao_playlist import PlaylistDao
from app.database.dao_sermons import SermonsDao
from app.ui.pdf_import_dialog import PdfImportDialog
from app.utils.pdf_parser import HAS_FITZ, parse_hymns_from_pdf
from app.utils.pptx_parser import parse_pptx_as_hymn, parse_pptx_folder
from app.utils.project_on_controller import ProjectOnController


class LibraryController(QObject):
    def __init__(
        self,
        db: Database,
        project_controller: ProjectOnController,
        bible_tab: QObject,
        hymns_tab: QObject,
        sermons_tab: QObject,
        expose_tab: QObject | None = None,
        playlist_tab: QObject | None = None,
        media_tab: QObject | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project = project_controller

        self._bible_dao = BibleDao(db)
        self._hymns_dao = HymnsDao(db)
        self._sermons_dao = SermonsDao(db)
        self._playlist_dao = PlaylistDao(db)
        self._media_dao = MediaDao(db)

        self._bible_tab = bible_tab
        self._hymns_tab = hymns_tab
        self._sermons_tab = sermons_tab
        self._expose_tab = expose_tab
        self._playlist_tab = playlist_tab
        self._media_tab = media_tab

        self._current_translation_id: int | None = None
        self._current_book_id: int | None = None
        self._current_chapter: int | None = None
        self._current_sermon_id: int | None = None
        self._current_sermon_language: str = "en"
        self._current_hymn_id: int | None = None
        self._current_expose_chapter_id: int | None = None
        self._current_expose_page: int | None = None
        self._sermons_loaded = False
        self._expose_loaded = False
        self._pool = QThreadPool.globalInstance()

        # Caches du programme de projection : la liste affichée dans chaque
        # onglet devient directement le programme live (découpage conservé).
        self._current_verses: list[dict[str, Any]] = []
        self._current_verses_title: str = ""
        self._current_sermon_paragraphs: list[dict[str, Any]] = []
        self._current_sermon_program_title: str = ""
        self._current_stanzas: list[dict[str, Any]] = []
        self._current_hymn_program_title: str = ""
        self._current_expose_pages: list[int] = []
        # Programme live en cours = chapitre d'Exposé ? Sert au suivi du
        # paragraphe projeté dans l'onglet Exposé (None sinon).
        self._live_expose_chapter_id: int | None = None
        self._current_playlist_folder_id: int | None = None

        self._wire()
        self.refresh_all()

    @staticmethod
    def _clean_text(value: Any) -> str:
        from app.utils.text_utils import clean_text

        return clean_text(value)

    @staticmethod
    def _format_sermon_reference(date_code: Any, title: Any, marker: Any) -> str:
        parts = [
            str(date_code or "").strip(),
            str(title or "").strip(),
            str(marker or "").strip(),
        ]
        return " - ".join(p for p in parts if p)

    @staticmethod
    def _format_hymn_reference(number: Any, title: Any, label: Any) -> str:
        parts = [
            str(number or "").strip(),
            str(title or "").strip(),
            str(label or "").strip(),
        ]
        return " - ".join(p for p in parts if p)

    def _wire(self) -> None:
        if hasattr(self._bible_tab, "translationSelected"):
            self._bible_tab.translationSelected.connect(
                self.on_bible_translation_selected
            )
        self._bible_tab.bookSelected.connect(self.on_bible_book_selected)
        self._bible_tab.chapterSelected.connect(self.on_bible_chapter_selected)
        self._bible_tab.verseActivated.connect(self.on_bible_verse_activated)
        if hasattr(self._bible_tab, "versesActivated"):
            self._bible_tab.versesActivated.connect(self.on_bible_verses_activated)

        self._sermons_tab.sermonSelected.connect(self.on_sermon_selected)
        self._sermons_tab.paragraphActivated.connect(self.on_sermon_paragraph_activated)
        if hasattr(self._sermons_tab, "filtersChanged"):
            self._sermons_tab.filtersChanged.connect(self.refresh_sermons)
        if hasattr(self._sermons_tab, "paragraphSearchRequested"):
            self._sermons_tab.paragraphSearchRequested.connect(self.on_paragraph_search)

        if self._expose_tab is not None:
            self._expose_tab.chapterSelected.connect(self.on_expose_chapter_selected)
            self._expose_tab.pageSelected.connect(self.on_expose_page_selected)
            self._expose_tab.paragraphActivated.connect(
                self.on_expose_paragraph_activated
            )
            if hasattr(self._expose_tab, "paragraphSoloRequested"):
                self._expose_tab.paragraphSoloRequested.connect(
                    self.on_expose_paragraph_solo
                )
            self._expose_tab.searchRequested.connect(self.on_expose_search)
            self._expose_tab.translatorChanged.connect(self.refresh_expose)

        if self._playlist_tab is not None:
            self._playlist_tab.folderSelected.connect(self.on_playlist_folder_selected)
            self._playlist_tab.itemActivated.connect(self.on_playlist_play)
            self._playlist_tab.playRequested.connect(self.on_playlist_play)
            self._playlist_tab.folderCreateRequested.connect(
                self.on_playlist_folder_create
            )
            self._playlist_tab.folderRenameRequested.connect(
                self.on_playlist_folder_rename
            )
            self._playlist_tab.folderDeleteRequested.connect(
                self.on_playlist_folder_delete
            )
            self._playlist_tab.itemCreateRequested.connect(self.on_playlist_item_create)
            self._playlist_tab.itemUpdateRequested.connect(self.on_playlist_item_update)
            self._playlist_tab.itemDeleteRequested.connect(self.on_playlist_item_delete)
            self._playlist_tab.itemMoveRequested.connect(self.on_playlist_item_move)
            self._playlist_tab.folderExportRequested.connect(
                self.on_playlist_folder_export
            )
            self._playlist_tab.importRequested.connect(self.on_playlist_import)

        if self._media_tab is not None:
            self._media_tab.importRequested.connect(self.on_media_import)
            self._media_tab.webAddRequested.connect(self.on_media_add_web)
            self._media_tab.itemActivated.connect(self.on_media_item_activated)
            self._media_tab.itemDeleteRequested.connect(self.on_media_delete)
            self._media_tab.itemRenameRequested.connect(self.on_media_rename)
            self._media_tab.refreshRequested.connect(self.refresh_media)
            self._media_tab.mediaAddToPlaylistRequested.connect(
                self.on_media_add_to_playlist
            )

        # « Ajouter à la playlist » depuis Bible / Cantiques / Sermons / Exposé.
        for tab in (self._bible_tab, self._hymns_tab, self._sermons_tab, self._expose_tab):
            if tab is not None and hasattr(tab, "addToPlaylistRequested"):
                tab.addToPlaylistRequested.connect(self.on_add_to_playlist)

        self._hymns_tab.hymnSelected.connect(self.on_hymn_selected)
        self._hymns_tab.stanzaActivated.connect(self.on_hymn_stanza_activated)
        if hasattr(self._hymns_tab, "stanzasActivated"):
            self._hymns_tab.stanzasActivated.connect(self.on_hymn_stanzas_activated)
        if hasattr(self._hymns_tab, "hymnActivated"):
            self._hymns_tab.hymnActivated.connect(self.on_hymn_activated)
        if hasattr(self._hymns_tab, "importScanRequested"):
            self._hymns_tab.importScanRequested.connect(self.on_scan_hymns_folder)
        if hasattr(self._hymns_tab, "deleteRequested"):
            self._hymns_tab.deleteRequested.connect(self.on_delete_hymn)
        if hasattr(self._hymns_tab, "deleteAllRequested"):
            self._hymns_tab.deleteAllRequested.connect(self.on_delete_all_hymns)
        if hasattr(self._hymns_tab, "importPptxFileRequested"):
            self._hymns_tab.importPptxFileRequested.connect(self.on_import_pptx_file)
        if hasattr(self._hymns_tab, "importPptxFolderRequested"):
            self._hymns_tab.importPptxFolderRequested.connect(
                self.on_import_pptx_folder
            )
        if hasattr(self._hymns_tab, "clearAllHymnsRequested"):
            self._hymns_tab.clearAllHymnsRequested.connect(self.on_clear_all_hymns)
        if hasattr(self._hymns_tab, "importPdfFileRequested"):
            self._hymns_tab.importPdfFileRequested.connect(self.on_import_pdf_file)

    def refresh_all(self) -> None:
        self.refresh_bible_books()
        self.refresh_hymns()
        self.refresh_sermons()
        self.refresh_expose()
        self.refresh_playlists()
        self.refresh_media()
        self._sermons_loaded = True
        self._expose_loaded = True

    def on_tab_shown(self, index: int) -> None:
        """Called when a library tab becomes visible. Triggers lazy loading."""

    def refresh_bible_books(self) -> None:
        translations = []
        try:
            translations = self._bible_dao.list_translations()
        except Exception:
            translations = []

        if translations and hasattr(self._bible_tab, "set_translations"):
            self._bible_tab.set_translations(translations)
            if self._current_translation_id is None:
                self._current_translation_id = int(translations[0]["id"])
            books = self._bible_dao.list_translation_books(self._current_translation_id)
        else:
            books = self._bible_dao.list_books()

        self._bible_tab.set_books(books)
        if books:
            self.on_bible_book_selected(int(books[0]["id"]))

    def on_bible_translation_selected(self, translation_id: int) -> None:
        self._current_translation_id = int(translation_id)
        self._current_book_id = None
        self._current_chapter = None
        books = self._bible_dao.list_translation_books(self._current_translation_id)
        self._bible_tab.set_books(books)
        if books:
            self.on_bible_book_selected(int(books[0]["id"]))
        else:
            self._bible_tab.set_chapters([])
            self._bible_tab.set_verses([])

    def on_bible_book_selected(self, book_id: int) -> None:
        self._current_book_id = int(book_id)
        if self._current_translation_id is not None:
            chapters = self._bible_dao.list_translation_chapters(
                self._current_translation_id, self._current_book_id
            )
        else:
            chapters = self._bible_dao.list_chapters(self._current_book_id)
        self._bible_tab.set_chapters(chapters)
        if chapters:
            self.on_bible_chapter_selected(int(chapters[0]))
        else:
            self._bible_tab.set_verses([])

    def on_bible_chapter_selected(self, chapter: int) -> None:
        if self._current_book_id is None:
            return
        self._current_chapter = int(chapter)
        self._bible_tab.set_current_chapter(self._current_chapter)
        if self._current_translation_id is not None:
            verses = self._bible_dao.list_translation_verses(
                self._current_translation_id,
                self._current_book_id,
                self._current_chapter,
            )
        else:
            verses = self._bible_dao.list_verses(
                self._current_book_id, self._current_chapter
            )

        book_name = self._bible_tab.current_book_name() or ""
        prepared: list[dict[str, Any]] = []
        for v in verses:
            ref = f"{book_name} {self._current_chapter}:{int(v['verse'])}".strip()
            prepared.append(
                {
                    "reference": ref,
                    "text": self._clean_text(v["text"]),
                    "verse": int(v["verse"]),
                }
            )

        self._current_verses = prepared
        self._current_verses_title = f"{book_name} {self._current_chapter}".strip()
        self._bible_tab.set_verses(prepared)

    def on_bible_verse_activated(self, reference: str, text: str) -> None:
        """Projette le chapitre courant depuis le verset cliqué."""
        self._live_expose_chapter_id = None
        ref = self._clean_text(reference)
        entries = [(p["reference"], p["text"]) for p in self._current_verses]
        focus = next(
            (i for i, (entry_ref, _t) in enumerate(entries) if entry_ref == ref), 0
        )
        if not entries:
            entries = [(ref, self._clean_text(text))]
        self._project.load_program(
            "bible", self._current_verses_title or ref, entries, focus_entry=focus
        )

    def on_bible_verses_activated(self, verses: list) -> None:
        """Projette la sélection multiple de versets."""
        self._live_expose_chapter_id = None
        entries = [
            (self._clean_text(ref), self._clean_text(text)) for ref, text in verses
        ]
        if entries:
            self._project.load_program(
                "bible", self._current_verses_title or "Bible", entries
            )

    def refresh_sermons(self) -> None:
        language = None
        tradition = None
        title_query = None
        translator = None
        date_from = None
        date_to = None

        # Static overrides for removed filters
        location_query = None
        sort_by = "date"
        limit = 5000

        if hasattr(self._sermons_tab, "current_language"):
            language = self._sermons_tab.current_language()
        if hasattr(self._sermons_tab, "current_query"):
            title_query = self._sermons_tab.current_query() or None
        if hasattr(self._sermons_tab, "current_translator"):
            translator = self._sermons_tab.current_translator()
        if hasattr(self._sermons_tab, "current_date_from"):
            date_from = self._sermons_tab.current_date_from()
        if hasattr(self._sermons_tab, "current_date_to"):
            date_to = self._sermons_tab.current_date_to()

        searching = title_query is not None
        self._current_sermon_language = language or "en"

        def _fetch():
            res = {}
            lang_str = str(language).lower() if language is not None else "fr"
            res["translators"] = self._sermons_dao.list_branham_translators(lang_str)
            res["years"] = self._sermons_dao.list_sermon_years(
                tradition=tradition,
                language=language,
                title_query=title_query if not searching else None,
                translator=translator,
            )
            res["sermons"] = self._sermons_dao.list_sermons(
                tradition=tradition,
                language=language,
                title_query=title_query,
                translator=translator,
                date_from=date_from,
                date_to=date_to,
                location_query=location_query,
                sort_by=sort_by,
                limit=limit,
            )
            return res

        def _on_done(result):
            if result is None:
                return
            if hasattr(self._sermons_tab, "set_translators"):
                self._sermons_tab.set_translators(result["translators"])
            if hasattr(self._sermons_tab, "set_years"):
                self._sermons_tab.set_years(result["years"])
            self._sermons_tab.set_sermons(result["sermons"])

        self._pool.start(_DbWorker(_fetch, _on_done))

    def on_sermon_selected(self, sermon_id: Any) -> None:
        self._current_sermon_id = sermon_id
        sermon_title = self._sermons_tab.current_sermon_title() or ""
        sermon_date = ""
        if hasattr(self._sermons_tab, "current_sermon_date"):
            sermon_date = self._sermons_tab.current_sermon_date() or ""

        lang = self._current_sermon_language

        # Run heavy list_paragraphs in background
        def _fetch():
            return self._sermons_dao.list_paragraphs(sermon_id, lang)

        def _on_done(paragraphs):
            prepared = self._prepare_sermon_entries(paragraphs, sermon_title, sermon_date)
            self._current_sermon_paragraphs = prepared
            self._current_sermon_program_title = self._format_sermon_reference(
                sermon_date, sermon_title, ""
            ).strip(" -")
            self._sermons_tab.set_paragraphs(prepared)

        self._pool.start(_DbWorker(_fetch, _on_done))

    def _prepare_sermon_entries(
        self, paragraphs: list[dict[str, Any]], sermon_title: str, sermon_date: str
    ) -> list[dict[str, Any]]:
        """Met en forme les paragraphes d'un sermon pour l'affichage/projection."""
        prepared: list[dict[str, Any]] = []
        for p in paragraphs or []:
            no = int(p["paragraph_no"])
            marker = str(p.get("marker") or p.get("para_id") or f"¶{no}").strip()
            ref = self._format_sermon_reference(sermon_date, sermon_title, marker)

            prepared.append(
                {
                    "reference": ref,
                    "ref": ref,
                    "text": self._clean_text(p["text"]),
                    "paragraph_no": no,
                    "para_id": marker,
                    "marker": marker,
                },
            )
        return prepared

    @staticmethod
    def _find_entry_index(
        entries: list[tuple[str, str]], reference: str
    ) -> int:
        """Index de l'entrée correspondant à la référence cliquée.

        Retombe sur le marqueur seul (dernier segment après « - ») lorsque la
        référence complète diffère (ex. résultat de recherche global).
        """
        for i, (ref, _text) in enumerate(entries):
            if ref == reference:
                return i
        marker = reference.rsplit(" - ", 1)[-1].strip()
        for i, (ref, _text) in enumerate(entries):
            if ref.rsplit(" - ", 1)[-1].strip() == marker:
                return i
        return 0

    def on_sermon_paragraph_activated(self, payload: dict) -> None:
        """Projette tout le sermon courant depuis le paragraphe cliqué.

        Fonctionne aussi depuis un résultat de recherche globale : le sermon
        d'origine est alors rechargé en arrière-plan avant projection.
        """
        self._live_expose_chapter_id = None
        ref = self._clean_text(payload.get("reference", ""))
        text = self._clean_text(payload.get("text", ""))
        sermon_id = payload.get("sermon_id")

        same_sermon = (
            sermon_id is not None
            and self._current_sermon_paragraphs
            and str(sermon_id) == str(self._current_sermon_id)
        )
        if same_sermon or (sermon_id is None and self._current_sermon_paragraphs):
            entries = [
                (p["reference"], p["text"]) for p in self._current_sermon_paragraphs
            ]
            focus = self._find_entry_index(entries, ref)
            self._project.load_program(
                "sermon",
                self._current_sermon_program_title or ref,
                entries,
                focus_entry=focus,
            )
            return

        if sermon_id is None:
            if text:
                self._project.load_program("sermon", ref, [(ref, text)])
            return

        # Résultat de recherche : recharger le sermon complet en arrière-plan
        sermon_title = self._clean_text(payload.get("sermon_title", ""))
        sermon_date = self._clean_text(payload.get("sermon_date", ""))
        lang = self._current_sermon_language

        def _fetch():
            return self._sermons_dao.list_paragraphs(sermon_id, lang)

        def _on_done(paragraphs):
            prepared = self._prepare_sermon_entries(paragraphs, sermon_title, sermon_date)
            self._current_sermon_id = sermon_id
            self._current_sermon_paragraphs = prepared
            self._current_sermon_program_title = self._format_sermon_reference(
                sermon_date, sermon_title, ""
            ).strip(" -")
            entries = [(p["reference"], p["text"]) for p in prepared]
            if not entries and text:
                entries = [(ref, text)]
            focus = self._find_entry_index(entries, ref)
            self._project.load_program(
                "sermon",
                self._current_sermon_program_title or sermon_title or ref,
                entries,
                focus_entry=focus,
            )

        self._pool.start(_DbWorker(_fetch, _on_done))

    def on_paragraph_search(self, query: str) -> None:
        """Search across all paragraphs in background thread."""
        lang = self._current_sermon_language
        translator = None
        if hasattr(self._sermons_tab, "current_translator"):
            translator = self._sermons_tab.current_translator()

        def _fetch():
            return self._sermons_dao.search_paragraphs(
                query,
                language=lang,
                translator=translator,
                limit=200,
            )

        def _on_done(results):
            if results is None:
                results = []
            if hasattr(self._sermons_tab, "set_search_results"):
                self._sermons_tab.set_search_results(results)

        self._pool.start(_DbWorker(_fetch, _on_done))

    # ── Exposé ────────────────────────────────────────────────────────────

    def refresh_expose(self) -> None:
        if self._expose_tab is None:
            return

        translator = "VGR"
        if hasattr(self._expose_tab, "current_translator"):
            translator = self._expose_tab.current_translator()

        def _fetch():
            return self._sermons_dao.list_expose_chapters(translator=translator)

        def _on_done(chapters):
            if chapters is None:
                chapters = []
            self._expose_tab.set_chapters(chapters)

        self._pool.start(_DbWorker(_fetch, _on_done))

    def on_expose_chapter_selected(self, chapter_id: Any) -> None:
        if self._expose_tab is None:
            return

        # Remove 'int_' prefix if present
        if isinstance(chapter_id, str) and chapter_id.startswith("int_"):
            self._current_expose_chapter_id = int(chapter_id.replace("int_", ""))
        else:
            self._current_expose_chapter_id = int(chapter_id)

        def _fetch():
            return self._sermons_dao.list_expose_pages(self._current_expose_chapter_id)

        def _on_done(pages):
            if pages is None:
                pages = []
            self._expose_tab.set_pages(pages)
            self._current_expose_pages = [int(p) for p in pages]
            if pages:
                self.on_expose_page_selected(pages[0])
            else:
                self._expose_tab.set_paragraphs([])

        self._pool.start(_DbWorker(_fetch, _on_done))

    def on_expose_page_selected(self, page_num: int) -> None:
        if self._expose_tab is None or self._current_expose_chapter_id is None:
            return

        if page_num == -1:
            # Restore view when search is cleared
            if self._current_expose_page is not None:
                p = self._current_expose_page
            else:
                # Need to refresh from beginning of chapter
                self.on_expose_chapter_selected(self._current_expose_chapter_id)
                return
        else:
            p = page_num
            self._current_expose_page = p

        self._expose_tab.set_current_page(p)

        ch_id = self._current_expose_chapter_id

        def _fetch():
            return self._sermons_dao.list_expose_page_paragraphs(ch_id, p)

        def _on_done(paragraphs):
            if paragraphs is None:
                paragraphs = []
            self._expose_tab.set_paragraphs(paragraphs)

        self._pool.start(_DbWorker(_fetch, _on_done))

    def on_expose_search(self, query: str) -> None:
        """Search across entire Exposé book in background."""
        translator = "VGR"
        if hasattr(self._expose_tab, "current_translator"):
            translator = self._expose_tab.current_translator()

        def _fetch():
            return self._sermons_dao.search_expose(query, translator=translator)

        def _on_done(results):
            if results is None:
                results = []
            if hasattr(self._expose_tab, "set_search_results"):
                self._expose_tab.set_search_results(results)

        self._pool.start(_DbWorker(_fetch, _on_done))

    def _expose_book_prefix(self, ch_id: int | None) -> str:
        """Titre de l'ouvrage d'Exposé selon la tradition du chapitre."""
        tradition = "VGR"
        if ch_id is not None:
            try:
                with self._db.connect() as conn:
                    row = conn.execute(
                        "SELECT tradition FROM sermon WHERE id = ?", (int(ch_id),)
                    ).fetchone()
                if row is not None and str(row["tradition"] or "").strip():
                    tradition = str(row["tradition"]).strip().upper()
            except Exception:
                pass
        if tradition == "SHP":
            return "Exposé SHP"
        return "Exposé des Sept Âges"

    def _expose_full_reference(self, ch_id: int | None, chapter_title: str) -> str:
        """Référence projetée d'un exposé : « <ouvrage> — <chapitre> »."""
        prefix = self._expose_book_prefix(ch_id)
        chapter = (chapter_title or "").strip()
        return f"{prefix} — {chapter}" if chapter else prefix

    def on_expose_paragraph_activated(
        self, reference: str, text: str, title: str = ""
    ) -> None:
        """Projette tout le chapitre exposé courant depuis le paragraphe cliqué.

        Les paragraphes de toutes les pages du chapitre sont rechargés en
        arrière-plan (dans l'ordre des pages) pour former le programme live.
        La référence projetée porte le titre de l'ouvrage et du chapitre —
        la position « Page/¶ » n'a d'intérêt que pour l'opérateur.
        """
        ref = self._clean_text(reference)
        chapter_title = self._clean_text(title) or ref
        full_reference = self._expose_full_reference(
            self._current_expose_chapter_id, chapter_title
        )

        ch_id = self._current_expose_chapter_id
        pages = list(self._current_expose_pages)

        def _fetch():
            all_rows: list[dict[str, Any]] = []
            for page in pages:
                rows = self._sermons_dao.list_expose_page_paragraphs(ch_id, page)
                all_rows.extend(rows or [])
            return all_rows

        def _on_done(rows):
            self._live_expose_chapter_id = ch_id
            entries: list[tuple[str, str]] = []
            raw_refs: list[str] = []
            for p in rows or []:
                raw_ref = str(p.get("ref", ""))
                entry_reference = full_reference
                m = re.search(r"(\d+)-(\d+)", raw_ref)
                if m:
                    # « ¶ » est filtré par clean_text → utiliser « § ».
                    entry_reference = (
                        f"{full_reference} · Page {m.group(1)} §{m.group(2)}"
                    )
                entries.append((entry_reference, self._clean_text(p.get("text", ""))))
                raw_refs.append(raw_ref)

            if not entries and text:
                entries = [(full_reference, text)]
                raw_refs = [ref]

            focus = 0
            for i, raw in enumerate(raw_refs):
                if raw == ref:
                    focus = i
                    break

            self._project.load_program(
                "sermon", chapter_title, entries, focus_entry=focus
            )

        self._pool.start(_DbWorker(_fetch, _on_done))

    def on_expose_paragraph_solo(
        self, reference: str, text: str, title: str = ""
    ) -> None:
        """Projette uniquement le paragraphe sélectionné de l'Exposé."""
        body = self._clean_text(text)
        if not body:
            return
        chapter_title = self._clean_text(title)
        full_reference = self._expose_full_reference(
            self._current_expose_chapter_id, chapter_title
        )
        # Position page/§ si le marqueur brut la porte (« 45-3 »).
        m = re.search(r"(\d+)-(\d+)", self._clean_text(reference))
        if m:
            full_reference += f" · Page {m.group(1)} §{m.group(2)}"
        self._live_expose_chapter_id = self._current_expose_chapter_id
        self._project.load_program(
            "sermon", chapter_title or full_reference, [(full_reference, body)]
        )

    def live_expose_chapter_id(self) -> int | None:
        """Chapitre d'Exposé actuellement en projection (None si autre programme)."""
        return self._live_expose_chapter_id

    def refresh_hymns(self) -> None:
        def _fetch():
            return self._hymns_dao.list_hymns()

        def _on_done(hymns):
            if hymns is None:
                hymns = []
            self._hymns_tab.set_hymns(hymns)
            if hymns:
                self.on_hymn_selected(int(hymns[0]["id"]))

        self._pool.start(_DbWorker(_fetch, _on_done))

    @staticmethod
    def _detect_chorus(text: str) -> tuple[bool, str, str]:
        """Detect if stanza text is a chorus.
        Returns (is_chorus, label, original_text).
        """
        import re

        stripped = text.strip()
        m = re.match(
            r"^(?:Dernier\s+)?(Chœur|Choeur|Refrain|Chorus)\s*[:.\-–—]?\s*",
            stripped,
            re.IGNORECASE,
        )
        if m:
            word = m.group(1)
            label = "Refrain" if word.lower().startswith("ref") else "Chœur"
            # Return True, the detected label, but keep the ORIGINAL text
            return True, label, text
        return False, "", text

    def on_hymn_selected(self, hymn_id: int) -> None:
        self._current_hymn_id = int(hymn_id)
        stanzas = self._hymns_dao.list_stanzas(self._current_hymn_id)
        hymn = self._hymns_dao.get_hymn(self._current_hymn_id)

        hymn_title = (hymn or {}).get("title") or self._hymns_tab.current_hymn_title() or ""
        hymn_number = (hymn or {}).get("number") or ""
        prepared = self._prepare_hymn_stanzas(stanzas, hymn_number, hymn_title)

        self._current_stanzas = prepared
        self._current_hymn_program_title = self._format_hymn_reference(
            hymn_number, hymn_title, ""
        ).strip(" -")
        self._hymns_tab.set_stanzas(prepared)

    def _prepare_hymn_stanzas(
        self, stanzas: list[dict[str, Any]], hymn_number: str, hymn_title: str
    ) -> list[dict[str, Any]]:
        """Met en forme les strophes pour l'affichage/projection."""
        prepared: list[dict[str, Any]] = []
        verse_no = 0
        chorus_no = 0
        for s in stanzas or []:
            full_text = s["text"]
            label = str(s.get("label") or "")
            is_chorus = bool(s.get("is_chorus"))
            if not label:
                if is_chorus:
                    chorus_no += 1
                    label = "Refrain" if chorus_no == 1 else f"Refrain {chorus_no}"
                else:
                    verse_no += 1
                    label = f"Strophe {verse_no}"
            else:
                if is_chorus:
                    chorus_no += 1
                else:
                    verse_no += 1
            ref = self._format_hymn_reference(hymn_number, hymn_title, label)
            prepared.append(
                {
                    "reference": ref,
                    "label": label,
                    "is_chorus": is_chorus,
                    "text": full_text,
                    "stanza_no": int(s["stanza_no"]),
                }
            )
        return prepared

    def on_hymn_stanza_activated(self, reference: str, text: str) -> None:
        """Projette tout le cantique courant depuis la strophe cliquée."""
        self._live_expose_chapter_id = None
        ref = self._clean_text(reference)
        entries = [(p["reference"], p["text"]) for p in self._current_stanzas]
        focus = self._find_entry_index(entries, ref)
        if not entries:
            entries = [(ref, self._clean_text(text))]
        self._project.load_program(
            "hymn", self._current_hymn_program_title or ref, entries, focus_entry=focus
        )

    def on_hymn_stanzas_activated(self, stanzas: list[tuple[str, str]]) -> None:
        """Projette la sélection multiple de strophes."""
        self._live_expose_chapter_id = None
        entries = [
            (self._clean_text(ref), self._clean_text(text)) for ref, text in stanzas
        ]
        if entries:
            self._project.load_program(
                "hymn", self._current_hymn_program_title or "Cantique", entries
            )

    def on_hymn_activated(self, hymn_id: int) -> None:
        """Projette tout le cantique sélectionné."""
        self._live_expose_chapter_id = None
        stanzas = self._hymns_dao.list_stanzas(hymn_id)
        hymn = self._hymns_dao.get_hymn(hymn_id)
        hymn_title = hymn["title"] if hymn else ""
        hymn_number = hymn.get("number", "") if hymn else ""
        program_title = self._format_hymn_reference(hymn_number, hymn_title, "").strip(" -")

        self._current_hymn_id = int(hymn_id)
        self._current_stanzas = self._prepare_hymn_stanzas(stanzas, hymn_number, hymn_title)
        self._current_hymn_program_title = program_title

        entries = [
            (p["reference"], self._clean_text(p["text"]))
            for p in self._current_stanzas
        ]
        if entries:
            self._project.load_program("hymn", program_title or "Cantique", entries)

    def on_import_pptx_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Importer un fichier PowerPoint",
            "",
            "Fichiers PowerPoint (*.pptx *.ppsx);;Tous les fichiers (*)",
        )
        if not file_path:
            return

        hymn_data = parse_pptx_as_hymn(Path(file_path))
        if hymn_data is None:
            QMessageBox.warning(
                None,
                "Import échoué",
                f"Aucune slide trouvée dans le fichier:\n{file_path}",
            )
            return

        title = hymn_data["title"]
        if self._hymns_dao.hymn_exists(title):
            reply = QMessageBox.question(
                None,
                "Cantique existant",
                f'Un cantique avec le titre "{title}" existe déjà.\nVoulez-vous l\'importer quand même ?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._hymns_dao.import_hymn(title, hymn_data["stanzas"])
        self.refresh_hymns()
        QMessageBox.information(
            None,
            "Import réussi",
            f'Cantique "{title}" importé avec {len(hymn_data["stanzas"])} strophe(s).',
        )

    def on_import_pptx_folder(self) -> None:
        folder_path = QFileDialog.getExistingDirectory(
            None,
            "Importer un dossier de fichiers PowerPoint",
            "",
        )
        if not folder_path:
            return

        hymns_data = parse_pptx_folder(Path(folder_path))
        if not hymns_data:
            QMessageBox.warning(
                None,
                "Import échoué",
                f"Aucun fichier PPTX/PPSX valide trouvé dans:\n{folder_path}",
            )
            return

        imported = 0
        skipped = 0
        for hymn_data in hymns_data:
            title = hymn_data["title"]
            if self._hymns_dao.hymn_exists(title):
                skipped += 1
                continue
            self._hymns_dao.import_hymn(title, hymn_data["stanzas"])
            imported += 1

        self.refresh_hymns()
        msg = f"{imported} cantique(s) importé(s)."
        if skipped > 0:
            msg += f"\n{skipped} cantique(s) ignoré(s) (déjà existants)."
        QMessageBox.information(None, "Import terminé", msg)

    def on_delete_hymn(self, hymn_id: int) -> None:
        """Delete a hymn after user confirmation."""
        hymn = self._hymns_dao.get_hymn(hymn_id)
        if hymn is None:
            return

        title = hymn.get("title", "")
        reply = QMessageBox.question(
            None,
            "Supprimer le cantique",
            f'Voulez-vous vraiment supprimer le cantique "{title}" ?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._hymns_dao.delete_hymn(hymn_id)
        self.refresh_hymns()

    def on_delete_all_hymns(self) -> None:
        """Delete all hymns from the database."""
        # Assuming self._main_window and tr() are available or replaced with None and string literals
        # For this context, I'll use None for parent and string literals for messages.
        reply = QMessageBox.question(
            None,  # self._main_window,
            "Confirmer la suppression",  # tr("confirm_delete"),
            "Êtes-vous sûr de vouloir supprimer TOUS les cantiques ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            count = self._hymns_dao.delete_all_hymns()
            self.refresh_hymns()  # Assuming _load_hymns is equivalent to refresh_hymns
            QMessageBox.information(None, "Succès", f"{count} cantiques supprimés.")

    def on_scan_hymns_folder(self) -> None:
        """Scan the 'cantiques' folder for PDFs and import them sequentially with dialog."""
        folder = os.path.join(os.getcwd(), "cantiques")
        if not os.path.exists(folder):
            QMessageBox.warning(
                None, "Erreur", f"Le dossier 'cantiques' n'existe pas:\n{folder}"
            )
            return

        pdf_files = [f for f in os.listdir(folder) if f.lower().endswith(".pdf")]
        if not pdf_files:
            QMessageBox.information(
                None, "Info", "Aucun fichier PDF trouvé dans le dossier 'cantiques'."
            )
            return

        # Process sequentially to avoid overlapping dialogs
        self._sequential_pdfs = [os.path.join(folder, f) for f in pdf_files]
        self._sequential_import_count = 0
        self._process_next_pdf_in_queue()

    def _process_next_pdf_in_queue(self) -> None:
        if not hasattr(self, "_sequential_pdfs") or not self._sequential_pdfs:
            if (
                hasattr(self, "_sequential_import_count")
                and self._sequential_import_count > 0
            ):
                self.refresh_hymns()
                QMessageBox.information(
                    None,
                    "Scan terminé",
                    f"{self._sequential_import_count} cantique(s) importé(s).",
                )
            return

        pdf_path = Path(self._sequential_pdfs.pop(0))
        prefix = pdf_path.name[:2].upper()

        def _parse():
            from app.utils.hymn_pdf_parser import parse_hymns_for_import

            hymns = parse_hymns_for_import(pdf_path)
            if len(hymns) >= 5:
                return hymns
            legacy = parse_hymns_from_pdf(pdf_path, prefix)
            return legacy if len(legacy) > len(hymns) else hymns

        def _on_done(hymns):
            if hymns:
                imported = self._show_import_dialog_for_hymns(hymns, pdf_path)
                self._sequential_import_count += imported
            # Always try next one
            self._process_next_pdf_in_queue()

        self._pool.start(_DbWorker(_parse, _on_done))

    def on_clear_all_hymns(self) -> None:
        """Clear all hymns after user confirmation."""
        reply = QMessageBox.question(
            None,
            "Vider tous les cantiques",
            "Voulez-vous vraiment supprimer TOUS les cantiques ?\n\n"
            "Cette action est irréversible.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._hymns_dao.delete_all_hymns()
        self.refresh_hymns()
        QMessageBox.information(
            None, "Cantiques supprimés", "Tous les cantiques ont été supprimés."
        )

    def on_import_pdf_file(self) -> None:
        """Import hymns from a PDF file with professional dialog."""
        if not HAS_FITZ:
            QMessageBox.warning(
                None,
                "Module manquant",
                "Le module PyMuPDF est requis pour l'importation de PDF.\n\n"
                "Installez-le avec: pip install pymupdf",
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Importer un fichier PDF",
            "",
            "Fichiers PDF (*.pdf)",
        )
        if not file_path:
            return

        path = Path(file_path)

        def _parse():
            # Primary: column-aware, gap-based parser that separates stanzas
            # exactly as the PDF does (handles two-column hymnals and single
            # "Choeur" markers — the logic validated on the cantique PDFs).
            from app.utils.hymn_pdf_parser import parse_hymns_for_import

            hymns = parse_hymns_for_import(path)
            if len(hymns) >= 5:
                return hymns
            # Fallback: legacy multi-format parser for title-only layouts,
            # numbered-verse books and scanned (OCR) PDFs.
            legacy = parse_hymns_from_pdf(path, "TEMP")
            return legacy if len(legacy) > len(hymns) else hymns

        def _on_parsed(hymns):
            if hymns is None:
                QMessageBox.critical(
                    None, "Erreur", "Une erreur est survenue lors de la lecture du PDF."
                )
                return

            if not hymns:
                from app.utils.pdf_parser import HAS_OCR

                msg = "Aucun cantique n'a été trouvé dans ce PDF."
                if not HAS_OCR:
                    msg += "\n\nAstuce: Installez 'pytesseract' pour supporter les PDF scannés."
                QMessageBox.warning(None, "Aucun cantique", msg)
                return

            self._show_import_dialog_for_hymns(hymns, path)
            self.refresh_hymns()

        self._pool.start(_DbWorker(_parse, _on_parsed))

    def _show_import_dialog_for_hymns(self, hymns: list[dict], path: Path) -> int:
        """Helper to show the import dialog and perform the DB import. Returns count of imported hymns."""
        dialog = PdfImportDialog(hymns, path.name, dao=self._hymns_dao)

        if dialog.exec() != dialog.DialogCode.Accepted:
            return 0

        selected_hymns = dialog.get_selected_hymns()
        prefix = dialog.get_prefix()

        if not selected_hymns:
            return 0

        imported = 0
        skipped = 0

        for hymn in selected_hymns:
            title = hymn.get("title", "")
            stanzas = hymn.get("stanzas", [])

            if self._hymns_dao.hymn_exists(title):
                skipped += 1
                continue

            self._hymns_dao.import_hymn(title, stanzas)
            imported += 1

        self._update_sort_keys_for_prefix(prefix)
        return imported

    def _update_sort_keys_for_prefix(self, prefix: str) -> None:
        """Update sort_key for hymns with given prefix."""
        # Map prefix to sort letter
        sort_letters = {"CI": "A", "CV": "B", "PN": "C", "AD": "D"}
        sort_letter = sort_letters.get(prefix, chr(ord("E") + len(sort_letters)))

        with self._db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, title FROM hymn WHERE title LIKE ?",
                (f"{prefix}-%",),
            )
            for hymn_id, title in cursor.fetchall():
                match = re.match(rf"^{prefix}-(\d+)\.", title)
                if match:
                    num = int(match.group(1))
                    sort_key = f"{sort_letter}{num:04d}"
                    cursor.execute(
                        "UPDATE hymn SET sort_key = ? WHERE id = ?",
                        (sort_key, hymn_id),
                    )
            conn.commit()

    # ── Playlists ─────────────────────────────────────────────────────────

    def refresh_playlists(self, select_id: int | None = None) -> None:
        """Recharge la liste des playlists (dossiers) en arrière-plan."""
        if self._playlist_tab is None:
            return

        def _fetch():
            return self._playlist_dao.list_folders()

        def _on_done(folders):
            if folders is None:
                folders = []
            if hasattr(self._playlist_tab, "set_folders"):
                self._playlist_tab.set_folders(folders, select_id=select_id)

        self._pool.start(_DbWorker(_fetch, _on_done))

    def _refresh_playlist_items(self) -> None:
        """Recharge les slides du dossier de playlist courant."""
        folder_id = self._current_playlist_folder_id
        if self._playlist_tab is None:
            return

        def _fetch():
            if folder_id is None:
                return []
            return self._playlist_dao.list_items(folder_id)

        def _on_done(items):
            if items is None:
                items = []
            if hasattr(self._playlist_tab, "set_items"):
                self._playlist_tab.set_items(items)

        self._pool.start(_DbWorker(_fetch, _on_done))

    def on_playlist_folder_selected(self, folder_id: Any) -> None:
        self._current_playlist_folder_id = (
            int(folder_id) if folder_id is not None else None
        )
        self._refresh_playlist_items()

    def on_playlist_folder_create(self, name: str) -> None:
        clean = self._clean_text(name)
        if not clean:
            return
        new_id = self._playlist_dao.create_folder(clean)
        self.refresh_playlists(select_id=new_id)

    def on_playlist_folder_rename(self, folder_id: int, new_name: str) -> None:
        clean = self._clean_text(new_name)
        if not clean:
            return
        self._playlist_dao.rename_folder(int(folder_id), clean)
        self.refresh_playlists(select_id=int(folder_id))

    def on_playlist_folder_delete(self, folder_id: int) -> None:
        # Les items du dossier partent avec lui (FK ON DELETE CASCADE).
        self._playlist_dao.delete_folder(int(folder_id))
        if self._current_playlist_folder_id == int(folder_id):
            self._current_playlist_folder_id = None
        self.refresh_playlists()

    def on_playlist_item_create(self, folder_id: int, reference: str, text: str) -> None:
        self._playlist_dao.add_item(
            "custom", self._clean_text(reference), self._clean_text(text),
            folder_id=int(folder_id),
        )
        self._refresh_playlist_items()

    def on_playlist_item_update(self, item_id: int, reference: str, text: str) -> None:
        self._playlist_dao.update_item(
            int(item_id), self._clean_text(reference), self._clean_text(text)
        )
        self._refresh_playlist_items()

    def on_playlist_item_delete(self, item_id: int) -> None:
        self._playlist_dao.delete_item(int(item_id))
        self._refresh_playlist_items()

    def on_playlist_item_move(self, item_id: int, delta: int) -> None:
        """Échange l'ordre du slide avec son voisin (haut/bas)."""
        folder_id = self._current_playlist_folder_id
        if folder_id is None:
            return
        items = self._playlist_dao.list_items(folder_id)
        index = next(
            (i for i, it in enumerate(items) if int(it["id"]) == int(item_id)), None
        )
        target = index + int(delta) if index is not None else None
        if index is None or not 0 <= target < len(items):
            return
        self._playlist_dao.update_item_sort_order(
            int(items[index]["id"]), int(items[target]["sort_order"]), folder_id
        )
        self._playlist_dao.update_item_sort_order(
            int(items[target]["id"]), int(items[index]["sort_order"]), folder_id
        )
        self._refresh_playlist_items()

    def _show_add_to_playlist_dialog(self, folders: list, count: int):
        """Ouvre le dialogue de destination (couture de test : sous-classer)."""
        from app.ui.playlist_tab import AddToPlaylistDialog

        return AddToPlaylistDialog(folders, count, parent=self._playlist_tab)

    def on_add_to_playlist(self, entries: list) -> None:
        """Ajoute des éléments (référence, texte) à une playlist choisie.

        Appelé depuis les menus « Ajouter à la playlist » de la Bible, des
        cantiques, des sermons et de l'Exposé. Un dialogue permet de choisir
        la playlist de destination ou d'en créer une à la volée.
        """
        if self._playlist_tab is None:
            return
        cleaned = [
            (self._clean_text(ref), self._clean_text(text))
            for ref, text in entries or []
            if self._clean_text(ref) or self._clean_text(text)
        ]
        if not cleaned:
            return

        from PyQt6.QtWidgets import QDialog

        dialog = self._show_add_to_playlist_dialog(
            self._playlist_dao.list_folders(), len(cleaned)
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        folder_id, new_name = dialog.selected_folder()
        self._commit_to_playlist(folder_id, new_name, cleaned)

    def _commit_to_playlist(
        self, folder_id: int | None, new_name: str, entries: list[tuple[str, str]]
    ) -> None:
        """Écrit les entrées (référence, texte) dans la playlist visée.

        ``folder_id=None`` crée une playlist nommée ``new_name``.
        """
        if folder_id is None:
            if not new_name:
                return
            folder_id = self._playlist_dao.create_folder(new_name)
        self._playlist_dao.add_items(
            [("custom", ref, text) for ref, text in entries], folder_id=int(folder_id)
        )
        if self._current_playlist_folder_id == int(folder_id):
            self._refresh_playlist_items()
        self.refresh_playlists(select_id=int(folder_id))

    def _build_playlist_export(self, folder_id: int) -> dict[str, Any] | None:
        """Construit le dictionnaire d'export JSON (None si playlist vide)."""
        from app.version import __version__

        folder = self._playlist_dao.get_folder(int(folder_id))
        if folder is None:
            return None
        items = self._playlist_dao.list_items(int(folder_id))
        if not items:
            return None
        return {
            "app": "Project-On",
            "format": 1,
            "app_version": __version__,
            "name": str(folder.get("name") or "Playlist"),
            "items": [
                {
                    "reference": self._clean_text(it.get("reference") or ""),
                    "text": str(it.get("text") or ""),
                }
                for it in items
            ],
        }

    @staticmethod
    def _read_playlist_file(path: str) -> tuple[str, list[tuple[str, str]]]:
        """Lit un fichier d'export .json → (nom de playlist, entrées).

        Lève ``ValueError`` si le format est invalide.
        """
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError("format de playlist invalide")
        entries = [
            (str(it.get("reference") or ""), str(it.get("text") or ""))
            for it in payload["items"]
            if isinstance(it, dict) and str(it.get("text") or "").strip()
        ]
        return str(payload.get("name") or Path(path).stem), entries

    def on_playlist_folder_export(self, folder_id: int) -> None:
        """Exporte une playlist en .json (partage entre ordinateurs)."""
        payload = self._build_playlist_export(int(folder_id))
        if payload is None:
            name = str((self._playlist_dao.get_folder(int(folder_id)) or {}).get("name") or "Playlist")
            QMessageBox.information(
                self._playlist_tab,
                "Export de la playlist",
                f"La playlist « {name} » est vide : rien à exporter.",
            )
            return
        target, _filter = QFileDialog.getSaveFileName(
            self._playlist_tab,
            "Exporter la playlist",
            f"{payload['name']}.json",
            "Playlist Project-On (*.json)",
        )
        if not target:
            return
        try:
            Path(target).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            QMessageBox.warning(
                self._playlist_tab,
                "Export de la playlist",
                f"Impossible d'écrire le fichier :\n{exc}",
            )
            return
        QMessageBox.information(
            self._playlist_tab,
            "Export de la playlist",
            f"{len(payload['items'])} slide(s) exporté(s) vers :\n{target}",
        )

    def on_playlist_import(self) -> None:
        """Importe une playlist depuis un fichier .json exporté."""
        source, _filter = QFileDialog.getOpenFileName(
            self._playlist_tab,
            "Importer une playlist",
            "",
            "Playlist Project-On (*.json);;Tous les fichiers (*)",
        )
        if not source:
            return
        try:
            name, entries = self._read_playlist_file(source)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(
                self._playlist_tab,
                "Import de playlist",
                f"Fichier illisible ou invalide :\n{exc}",
            )
            return
        if not entries:
            QMessageBox.information(
                self._playlist_tab,
                "Import de playlist",
                "La playlist ne contient aucun slide exploitable.",
            )
            return
        name = self._clean_text(name) or "Playlist importée"
        self._commit_to_playlist(None, name, entries)
        QMessageBox.information(
            self._playlist_tab,
            "Import de playlist",
            f"{len(entries)} slide(s) importé(s) dans « {name} ».",
        )

    def on_playlist_play(self, item_id: Any) -> None:
        """Projette la playlist du dossier courant, depuis le slide demandé.

        ``item_id=None`` (ou id introuvable) démarre au premier slide. Chaque
        slide peut être découpé en plusieurs parties ; la navigation
        suivant/précédent enchaîne naturellement les slides suivants.
        """
        folder_id = self._current_playlist_folder_id
        if folder_id is None:
            return
        folder = self._playlist_dao.get_folder(folder_id)
        title = str((folder or {}).get("name") or "Playlist")

        def _fetch():
            return self._playlist_dao.list_items(folder_id)

        def _fetch():
            from app.utils.media_utils import media_kind

            all_rows: list[dict[str, Any]] = []
            for item in self._playlist_dao.list_items(folder_id):
                row = dict(item)
                # Un item PowerPoint développe toutes ses slides rendues.
                if (
                    str(item.get("source") or "") == "media"
                    and media_kind(str(item.get("background") or "")) == "powerpoint"
                ):
                    try:
                        from app.utils.office_renderer import render_pptx_to_images

                        row["_pptx_images"] = [
                            str(p) for p in render_pptx_to_images(
                                str(item.get("background"))
                            )
                        ]
                    except Exception:
                        row["_pptx_images"] = []
                all_rows.append(row)
            return all_rows

        def _on_done(items):
            self._live_expose_chapter_id = None
            entries: list[tuple[str, str]] = []
            visuals: list[str] = []
            for it in items or []:
                is_media = str(it.get("source") or "") == "media" and str(
                    it.get("background") or ""
                ).strip()
                reference = self._clean_text(it.get("reference") or title)
                pptx_images = it.get("_pptx_images") or []
                if pptx_images:
                    for image in pptx_images:
                        entries.append((reference, ""))
                        visuals.append(image)
                    continue
                body = "" if is_media else self._clean_text(it.get("text") or "")
                if is_media or body:
                    entries.append((reference, body))
                    visuals.append(str(it.get("background") or "") if is_media else "")
            if not entries:
                return
            focus = 0
            if item_id is not None:
                position = 0
                for it in items or []:
                    pptx_images = it.get("_pptx_images") or []
                    if pptx_images:
                        spans = len(pptx_images)
                        if int(it["id"]) == int(item_id):
                            break
                        position += spans
                        continue
                    if not (
                        self._clean_text(it.get("text") or "")
                        or (
                            str(it.get("source") or "") == "media"
                            and str(it.get("background") or "").strip()
                        )
                    ):
                        continue
                    if int(it["id"]) == int(item_id):
                        focus = position
                        break
                    position += 1
            self._project.load_program(
                "custom", title, entries, focus_entry=focus, entry_visuals=visuals
            )

        self._pool.start(_DbWorker(_fetch, _on_done))

    # ── Médias (images + vidéos) ──────────────────────────────────────────

    def refresh_media(self) -> None:
        """Recharge la galerie de médias en arrière-plan."""
        if self._media_tab is None:
            return

        def _fetch():
            return self._media_dao.list_media()

        def _on_done(items):
            if items is None:
                items = []
            if hasattr(self._media_tab, "set_media"):
                self._media_tab.set_media(items)

        self._pool.start(_DbWorker(_fetch, _on_done))

    def on_media_import(self, kind: str = "image") -> None:
        """Importe des fichiers média (copie dans la bibliothèque utilisateur)."""
        from PyQt6.QtWidgets import QFileDialog

        from app.utils.app_paths import import_media_file
        from app.utils.media_utils import (
            IMAGE_FILE_FILTER,
            MEDIA_FILE_FILTER,
            POWERPOINT_FILE_FILTER,
            VIDEO_FILE_FILTER,
            media_kind,
        )

        if self._media_tab is None:
            return
        title = (
            "Importer des images"
            if kind == "image"
            else "Importer des vidéos"
            if kind == "video"
            else "Importer une présentation PowerPoint"
        )
        file_filter = (
            IMAGE_FILE_FILTER
            if kind == "image"
            else VIDEO_FILE_FILTER
            if kind == "video"
            else POWERPOINT_FILE_FILTER
        )
        if kind == "pptx":
            # Une présentation à la fois : le rendu fidèle est coûteux.
            path, _filter = QFileDialog.getOpenFileName(
                self._media_tab, title, "", file_filter
            )
            paths = [path] if path else []
        else:
            paths, _filter = QFileDialog.getOpenFileNames(
                self._media_tab, title, "", file_filter
            )
        if not paths:
            return
        imported = 0
        for path in paths:
            dest = import_media_file(path)
            if dest is None:
                continue
            self._media_dao.add_media(
                dest.stem, str(dest), media_kind(str(dest))
            )
            imported += 1
        if not imported:
            return
        if kind == "pptx":
            self._render_pptx_in_background(paths[0])
        else:
            self.refresh_media()

    def _render_pptx_in_background(self, pptx_path: str) -> None:
        """Rend les slides d'un .pptx en arrière-plan puis rafraîchit la galerie."""
        if self._media_tab is None:
            return

        def _fetch():
            from app.utils.office_renderer import (
                OfficeRenderError,
                render_pptx_to_images,
            )

            try:
                return True, render_pptx_to_images(pptx_path), ""
            except OfficeRenderError as exc:
                return False, None, str(exc)
            except Exception as exc:  # erreurs COM/LibreOffice variées
                return False, None, str(exc)

        def _on_done(result):
            from PyQt6.QtWidgets import QMessageBox

            ok, images, detail = result or (False, None, "")
            self.refresh_media()
            if not ok:
                QMessageBox.warning(
                    self._media_tab,
                    "Import PowerPoint",
                    "Le rendu de la présentation a échoué.\n\n"
                    f"{detail}\n\nVérifiez que Microsoft PowerPoint ou "
                    "LibreOffice est installé.",
                )
            elif images:
                QMessageBox.information(
                    self._media_tab,
                    "Import PowerPoint",
                    f"{len(images)} slides rendues et ajoutées aux Médias.",
                )

        self._pool.start(_DbWorker(_fetch, _on_done))

    def on_media_item_activated(self, media_id: int) -> None:
        """Projette immédiatement le média double-cliqué."""
        from app.utils.media_utils import is_powerpoint_file

        media = self._media_dao.get_media(int(media_id))
        if media is None:
            return
        path = str(media["path"] or "")
        name = str(media["name"] or "")
        kind = str(media.get("kind") or "")
        self._live_expose_chapter_id = None

        if kind == "powerpoint" or is_powerpoint_file(path):
            # Rendu en arrière-plan (cache) puis programme des slides.
            def _fetch():
                from app.utils.office_renderer import (
                    OfficeRenderError,
                    render_pptx_to_images,
                )

                try:
                    return True, render_pptx_to_images(path), ""
                except OfficeRenderError as exc:
                    return False, None, str(exc)
                except Exception as exc:
                    return False, None, str(exc)

            def _on_done(result):
                from PyQt6.QtWidgets import QMessageBox

                ok, images, detail = result or (False, None, "")
                if not ok:
                    QMessageBox.warning(
                        self._media_tab,
                        "Projection PowerPoint",
                        f"Rendu impossible :\n{detail}",
                    )
                    return
                visuals = [str(p) for p in images or []]
                entries = [
                    (f"{name or 'Présentation'} ({i}/{len(visuals)})", "")
                    for i in range(1, len(visuals) + 1)
                ]
                self._project.load_program(
                    "image", name or "Présentation", entries, entry_visuals=visuals
                )

            self._pool.start(_DbWorker(_fetch, _on_done))
            return

        self._project.load_media(path, name)

    def on_media_add_web(self, url: str, name: str = "") -> None:
        """Ajoute une page web (URL) comme média projetable."""
        clean_url = str(url or "").strip()
        if not clean_url:
            return
        if not clean_url.startswith(("http://", "https://")):
            clean_url = "https://" + clean_url
        display = self._clean_text(name) or clean_url
        self._media_dao.add_media(display, clean_url, "web")
        self.refresh_media()

    def on_media_delete(self, media_id: int) -> None:
        """Retire le média de la bibliothèque (le fichier reste sur disque)."""
        self._media_dao.delete_media(int(media_id))
        self.refresh_media()

    def on_media_rename(self, media_id: int, new_name: str) -> None:
        clean = self._clean_text(new_name)
        if not clean:
            return
        self._media_dao.rename_media(int(media_id), clean)
        self.refresh_media()

    def on_media_add_to_playlist(self, payload: dict) -> None:
        """Ajoute un média (image/vidéo) à une playlist choisie."""
        path = str((payload or {}).get("path") or "").strip()
        name = self._clean_text((payload or {}).get("name") or "")
        if not path or self._playlist_tab is None:
            return
        cleaned = [(name or "Média", "")]  # texte vide : entrée purement visuelle

        dialog = self._show_add_to_playlist_dialog(
            self._playlist_dao.list_folders(), len(cleaned)
        )
        from PyQt6.QtWidgets import QDialog

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        folder_id, new_name = dialog.selected_folder()
        if folder_id is None:
            if not new_name:
                return
            folder_id = self._playlist_dao.create_folder(new_name)
        self._playlist_dao.add_item(
            "media", name or "Média", "", folder_id=int(folder_id), background=path
        )
        if self._current_playlist_folder_id == int(folder_id):
            self._refresh_playlist_items()
        self.refresh_playlists(select_id=int(folder_id))
