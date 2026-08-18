from __future__ import annotations

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
    ) -> None:
        super().__init__()
        self._db = db
        self._project = project_controller

        self._bible_dao = BibleDao(db)
        self._hymns_dao = HymnsDao(db)
        self._sermons_dao = SermonsDao(db)

        self._bible_tab = bible_tab
        self._hymns_tab = hymns_tab
        self._sermons_tab = sermons_tab
        self._expose_tab = expose_tab

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
            self._expose_tab.searchRequested.connect(self.on_expose_search)
            self._expose_tab.translatorChanged.connect(self.refresh_expose)

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

    def on_expose_paragraph_activated(
        self, reference: str, text: str, title: str = ""
    ) -> None:
        """Projette tout le chapitre exposé courant depuis le paragraphe cliqué.

        Les paragraphes de toutes les pages du chapitre sont rechargés en
        arrière-plan (dans l'ordre des pages) pour former le programme live.
        """
        ref = self._clean_text(reference)
        chapter_title = self._clean_text(title) or ref

        ch_id = self._current_expose_chapter_id
        pages = list(self._current_expose_pages)

        def _fetch():
            all_rows: list[dict[str, Any]] = []
            for page in pages:
                rows = self._sermons_dao.list_expose_page_paragraphs(ch_id, page)
                all_rows.extend(rows or [])
            return all_rows

        def _on_done(rows):
            entries: list[tuple[str, str]] = []
            raw_refs: list[str] = []
            for p in rows or []:
                raw_ref = str(p.get("ref", ""))
                marker = str(p.get("marker") or p.get("para_id") or raw_ref)
                m = re.search(r"(\d+)-(\d+)", raw_ref)
                if m:
                    enriched = f"{chapter_title} - Page {m.group(1)}-¶{m.group(2)}"
                elif marker:
                    enriched = f"{chapter_title} - {marker}"
                else:
                    enriched = chapter_title
                entries.append((enriched, self._clean_text(p.get("text", ""))))
                raw_refs.append(raw_ref)

            if not entries and text:
                entries = [(ref, text)]
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
        entries = [
            (self._clean_text(ref), self._clean_text(text)) for ref, text in stanzas
        ]
        if entries:
            self._project.load_program(
                "hymn", self._current_hymn_program_title or "Cantique", entries
            )

    def on_hymn_activated(self, hymn_id: int) -> None:
        """Projette tout le cantique sélectionné."""
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
