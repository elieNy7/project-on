//! Bible : la traduction, les livres, la grille des chapitres, les versets ; la recherche accepte
//! une référence (« Jean 3:16 », « Ps 23 ») ou des mots (dans toute la traduction).

use egui::{Align, Layout, RichText, ScrollArea, Ui, vec2};
use po_db::{Database, Translation, TranslationBook};
use po_design::SlideSource;
use po_program::{Cue, Entry, bible_entries, bible_title};
use po_text::parse_reference;

use super::{Action, ENTRY_ROW, ITEM_ROW, Marks, Origin, Prepared, entry_row, item_row, scroll_offset};
use crate::search::{Hit, Request, SearchThread, Target};
use crate::theme::*;
use crate::widgets;

#[derive(Default)]
pub struct BibleView {
    translations: Vec<Translation>,
    pub translation: Option<i64>,
    books: Vec<TranslationBook>,
    book: Option<i64>,
    chapters: Vec<i64>,
    chapter: Option<i64>,
    entries: Vec<Entry>,
    pub query: String,
    asked: String,
    hits: Vec<Hit>,
    searching: bool,
    pub focus_search: bool,
    scroll_book: Option<usize>,
    scroll_verse: Option<usize>,
}

impl BibleView {
    /// Charge les traductions et choisit la première française (au démarrage : la recherche
    /// globale cherche dans cette traduction avant même d'ouvrir la page Bible).
    pub fn ensure_loaded(&mut self, db: &Database) {
        if !self.translations.is_empty() {
            return;
        }
        self.translations = db.list_translations().unwrap_or_default();
        // La première traduction française, sinon la première.
        let first = self
            .translations
            .iter()
            .find(|t| t.lang.as_deref() == Some("fr"))
            .or_else(|| self.translations.first())
            .map(|t| t.id);
        if let Some(id) = first {
            self.set_translation(db, id);
        }
    }

    pub fn set_translation(&mut self, db: &Database, id: i64) {
        self.translation = Some(id);
        let previous = self.book;
        self.books = db.list_translation_books(id).unwrap_or_default();
        let book =
            previous.filter(|b| self.books.iter().any(|x| x.id == *b)).or_else(|| self.books.first().map(|b| b.id));
        let chapter = self.chapter;
        if let Some(book) = book {
            self.set_book(db, book);
            if let Some(c) = chapter.filter(|c| self.chapters.contains(c)) {
                self.set_chapter(db, c);
            }
        }
    }

    fn set_book(&mut self, db: &Database, book: i64) {
        let Some(t) = self.translation else { return };
        self.book = Some(book);
        self.chapters = db.list_translation_chapters(t, book).unwrap_or_default();
        if let Some(first) = self.chapters.first().copied() {
            self.set_chapter(db, first);
        }
    }

    fn set_chapter(&mut self, db: &Database, chapter: i64) {
        let (Some(t), Some(book)) = (self.translation, self.book) else { return };
        self.chapter = Some(chapter);
        let verses = db.list_translation_verses(t, book, chapter).unwrap_or_default();
        self.entries = bible_entries(&verses, &self.book_name(), chapter);
        self.scroll_verse = Some(0);
    }

    fn book_name(&self) -> String {
        self.books.iter().find(|b| Some(b.id) == self.book).map(|b| b.name.clone()).unwrap_or_default()
    }

    pub fn entry_count(&self) -> usize {
        self.entries.len()
    }

    /// Le programme du chapitre montré, à partir du verset `index`.
    pub fn prepare(&self, index: usize) -> Option<Prepared> {
        let (t, book, chapter) = (self.translation?, self.book?, self.chapter?);
        let cue = Cue::new(SlideSource::Bible, bible_title(&self.book_name(), chapter), self.entries.clone(), index);
        Some(Prepared { cue, origin: Origin::Chapter { translation: t, book, chapter } })
    }

    /// Ouvre un chapitre (référence tapée ou résultat de recherche), sur le verset demandé.
    pub fn open(
        &mut self,
        db: &Database,
        translation: i64,
        book: i64,
        chapter: i64,
        verse: Option<i64>,
    ) -> Option<Prepared> {
        self.ensure_loaded(db);
        if self.translation != Some(translation) {
            self.set_translation(db, translation);
        }
        self.set_book(db, book);
        if let Some(i) = self.books.iter().position(|b| b.id == book) {
            self.scroll_book = Some(i);
        }
        self.set_chapter(db, chapter);
        let index =
            verse.and_then(|v| self.entries.iter().position(|e| e.reference.ends_with(&format!(":{v}")))).unwrap_or(0);
        self.scroll_verse = Some(index);
        self.prepare(index)
    }

    pub fn receive(&mut self, query: String, hits: Vec<Hit>) {
        if query == self.asked {
            self.hits = hits;
            self.searching = false;
        }
    }

    /// Entrée dans le champ de recherche : une référence ouvre son chapitre et le prépare.
    fn submit(&mut self, db: &Database) -> Option<Prepared> {
        let t = self.translation?;
        let books: Vec<po_text::Book> =
            self.books.iter().map(|b| po_text::Book { id: b.id, name: b.name.clone() }).collect();
        let r = parse_reference(&self.query, &books)?;
        self.query.clear();
        self.open(db, t, r.book_id, i64::from(r.chapter), r.verse.map(i64::from))
    }

    pub fn ui(&mut self, ui: &mut Ui, db: &Database, marks: &Marks, search: Option<&SearchThread>) -> Option<Action> {
        self.ensure_loaded(db);
        let mut action = None;
        let books_w = 200.0;
        ui.horizontal_top(|ui| {
            ui.allocate_ui_with_layout(vec2(books_w, ui.available_height()), Layout::top_down(Align::Min), |ui| {
                ui.set_width(books_w);
                self.translation_picker(ui, db);
                ui.add_space(6.0);
                let mut chosen = None;
                let mut area = ScrollArea::vertical().id_salt("livres-bible").auto_shrink([false, false]);
                if let Some(row) = self.scroll_book.take() {
                    area = area.vertical_scroll_offset(scroll_offset(ui, row, 34.0));
                }
                area.show_rows(ui, 34.0, self.books.len(), |ui, range| {
                    for i in range {
                        let b = &self.books[i];
                        let (rect, r) = widgets::list_row(ui, Some(b.id) == self.book, 32.0, &b.name);
                        ui.add_space(2.0);
                        widgets::paint_text(
                            ui,
                            egui::pos2(rect.min.x + 12.0, rect.center().y),
                            egui::Align2::LEFT_CENTER,
                            &b.name,
                            medium(13.0),
                            TEXT,
                            rect.width() - 20.0,
                        );
                        if r.clicked() {
                            chosen = Some(b.id);
                        }
                    }
                });
                if let Some(b) = chosen {
                    self.set_book(db, b);
                }
            });
            ui.add_space(10.0);
            ui.allocate_ui_with_layout(ui.available_size(), Layout::top_down(Align::Min), |ui| {
                action = self.chapter_column(ui, db, marks, search);
            });
        });
        action
    }

    fn translation_picker(&mut self, ui: &mut Ui, db: &Database) {
        let current = self
            .translations
            .iter()
            .find(|t| Some(t.id) == self.translation)
            .map(|t| t.shortname.clone().or(t.name.clone()).unwrap_or_else(|| t.module.clone()))
            .unwrap_or_default();
        let mut chosen = None;
        egui::ComboBox::from_id_salt("traduction").width(ui.available_width()).selected_text(current).show_ui(
            ui,
            |ui| {
                for t in &self.translations {
                    let label = t.name.clone().unwrap_or_else(|| t.module.clone());
                    if ui.selectable_label(Some(t.id) == self.translation, label).clicked() {
                        chosen = Some(t.id);
                    }
                }
            },
        );
        if let Some(id) = chosen {
            self.set_translation(db, id);
        }
    }

    fn chapter_column(
        &mut self,
        ui: &mut Ui,
        db: &Database,
        marks: &Marks,
        search: Option<&SearchThread>,
    ) -> Option<Action> {
        // La grille des chapitres.
        let mut chosen = None;
        ScrollArea::vertical().id_salt("chapitres").max_height(112.0).show(ui, |ui| {
            ui.horizontal_wrapped(|ui| {
                ui.spacing_mut().item_spacing = vec2(4.0, 4.0);
                for c in &self.chapters {
                    let selected = Some(*c) == self.chapter;
                    let tone = if selected { widgets::Tone::Primary(ACCENT) } else { widgets::Tone::Secondary };
                    if widgets::button_sized(ui, 38.0, widgets::Size::Normal, None, &c.to_string(), tone, true)
                        .clicked()
                    {
                        chosen = Some(*c);
                    }
                }
            });
        });
        if let Some(c) = chosen {
            self.set_chapter(db, c);
        }
        ui.add_space(8.0);
        let mut action = None;
        let r = widgets::search_field(ui, &mut self.query, "Référence (Jean 3:16) ou mots…", ui.available_width());
        if std::mem::take(&mut self.focus_search) {
            r.request_focus();
        }
        if r.lost_focus()
            && ui.input(|i| i.key_pressed(egui::Key::Enter))
            && let Some(p) = self.submit(db)
        {
            action = Some(Action::Cue(p));
        }
        ui.add_space(8.0);
        // Des mots (pas une référence) : la recherche dans la traduction.
        let q = self.query.trim().to_string();
        let words = q.chars().count() >= crate::search::MIN_TEXT_QUERY && !po_text::looks_like_reference(&q);
        if q != self.asked {
            self.asked = q.clone();
            self.hits.clear();
            self.searching = false;
            if words && let (Some(search), Some(t)) = (search, self.translation) {
                search.ask(Request::Verses { query: q, translation: t });
                self.searching = true;
            }
        }
        if words {
            let status =
                if self.searching { "Recherche…".to_string() } else { format!("{} versets", self.hits.len()) };
            ui.label(RichText::new(status).font(regular(11.5)).color(FAINT));
            let mut opened = None;
            ScrollArea::vertical().id_salt("resultats-bible").auto_shrink([false, false]).show_rows(
                ui,
                ITEM_ROW,
                self.hits.len(),
                |ui, range| {
                    for i in range {
                        let h = &self.hits[i];
                        let r = item_row(ui, false, &h.title, &h.subtitle, None);
                        if r.clicked() || r.double_clicked() {
                            opened = Some((h.target.clone(), r.double_clicked()));
                        }
                    }
                },
            );
            if let Some((Target::Verse { translation, book, chapter, verse }, take)) = opened {
                self.query.clear();
                let p = self.open(db, translation, book, chapter, verse)?;
                return Some(if take { Action::Take(p) } else { Action::Cue(p) });
            }
            return action;
        }
        let (Some(t), Some(book), Some(chapter)) = (self.translation, self.book, self.chapter) else {
            super::empty(ui, "Aucune Bible installée.");
            return action;
        };
        ui.label(RichText::new(bible_title(&self.book_name(), chapter)).font(semibold(15.0)).color(TEXT));
        ui.add_space(4.0);
        let origin = Origin::Chapter { translation: t, book, chapter };
        let mut clicked = None;
        let mut area = ScrollArea::vertical().id_salt(("versets", t, book, chapter)).auto_shrink([false, false]);
        if let Some(row) = self.scroll_verse.take() {
            area = area.vertical_scroll_offset(scroll_offset(ui, row, ENTRY_ROW));
        }
        area.show_rows(ui, ENTRY_ROW, self.entries.len(), |ui, range| {
            for i in range {
                let e = &self.entries[i];
                let verse = e.reference.rsplit(':').next().unwrap_or("");
                let (preview, live) = marks.of(&origin, i);
                let r = entry_row(ui, verse, &e.text, preview, live);
                if r.clicked() || r.double_clicked() {
                    clicked = Some((i, r));
                }
            }
        });
        if let Some((index, response)) = clicked
            && let Some(a) = Action::from_click(&response, || {
                self.prepare(index).unwrap_or(Prepared {
                    cue: Cue::new(SlideSource::Bible, "", Vec::new(), 0),
                    origin: origin.clone(),
                })
            })
        {
            action = Some(a);
        }
        action
    }
}
