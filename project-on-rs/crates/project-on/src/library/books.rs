//! Exposé et Livres : un ouvrage, ses chapitres, les paragraphes du chapitre (page par page, comme
//! dans la 2.8), et la recherche dans l'ouvrage. L'Exposé des Sept Âges (VGR et SHP) a sa page ;
//! les biographies et les brochures sont dans « Livres ».

use egui::{Align, Layout, RichText, ScrollArea, Ui};
use po_db::{Book, BookChapter, BookHit, Database, Paragraph};
use po_design::SlideSource;
use po_program::{Cue, Entry, book_entries, book_reference};

use super::{
    Action, ENTRY_ROW, ITEM_ROW, Marks, Origin, Prepared, choice_action, entry_menu, entry_row, item_row, scroll_offset,
};
use crate::search::{Request, SearchThread};
use crate::theme::*;
use crate::widgets;

/// Les ouvrages de la page Exposé et de la page Livres.
pub const EXPOSE_KEYS: [&str; 2] = ["ages-vgr", "ages-shp"];
pub const BOOK_KEYS: [&str; 3] = ["sent", "pvsa", "brochures"];

/// La référence d'un paragraphe d'ouvrage dans une playlist (`_playlist_reference` de la 2.8) :
/// « titre du chapitre · Page 3 §2 ».
pub fn playlist_reference(chapter: &str, raw_ref: &str) -> String {
    let raw = raw_ref.trim();
    let page_par = raw.split_once('-').filter(|(a, b)| {
        !a.is_empty() && !b.is_empty() && a.chars().all(|c| c.is_ascii_digit()) && b.chars().all(|c| c.is_ascii_digit())
    });
    match (page_par, chapter.is_empty()) {
        (Some((page, n)), false) => format!("{chapter} · Page {page} §{n}"),
        (Some((page, n)), true) => format!("Page {page} §{n}"),
        (None, false) => chapter.to_string(),
        (None, true) => raw.to_string(),
    }
}

pub struct BooksView {
    keys: &'static [&'static str],
    books: Option<Vec<Book>>,
    pub key: String,
    chapters: Vec<BookChapter>,
    chapter: Option<BookChapter>,
    /// Les paragraphes du chapitre (toutes ses pages) et leur page.
    paragraphs: Vec<(u32, Paragraph)>,
    entries: Vec<Entry>,
    pub query: String,
    asked: String,
    hits: Vec<BookHit>,
    searching: bool,
    pub focus_search: bool,
    scroll_chapter: Option<usize>,
    scroll_entry: Option<usize>,
}

impl BooksView {
    pub fn new(keys: &'static [&'static str]) -> Self {
        BooksView {
            keys,
            books: None,
            key: keys.first().copied().unwrap_or("ages-vgr").to_string(),
            chapters: Vec::new(),
            chapter: None,
            paragraphs: Vec::new(),
            entries: Vec::new(),
            query: String::new(),
            asked: String::new(),
            hits: Vec::new(),
            searching: false,
            focus_search: false,
            scroll_chapter: None,
            scroll_entry: None,
        }
    }

    /// L'ouvrage d'une clé gérée par cette page.
    pub fn handles(&self, key: &str) -> bool {
        self.keys.contains(&key)
    }

    fn ensure_loaded(&mut self, db: &Database) {
        if self.books.is_some() {
            return;
        }
        let books: Vec<Book> =
            db.list_books().unwrap_or_default().into_iter().filter(|b| self.keys.contains(&b.key.as_str())).collect();
        if !books.iter().any(|b| b.key == self.key)
            && let Some(first) = books.first()
        {
            self.key = first.key.clone();
        }
        self.books = Some(books);
        let key = self.key.clone();
        self.set_book(db, &key);
    }

    fn set_book(&mut self, db: &Database, key: &str) {
        self.key = key.to_string();
        self.chapters = db.list_book_chapters(key).unwrap_or_default();
        self.chapter = None;
        self.paragraphs.clear();
        self.entries.clear();
        self.asked.clear();
    }

    fn book(&self) -> Option<&Book> {
        self.books.as_ref()?.iter().find(|b| b.key == self.key)
    }

    pub fn chapter_count(&self) -> usize {
        self.chapters.len()
    }

    pub fn select(&mut self, db: &Database, index: usize) {
        self.ensure_loaded(db);
        if let Some(c) = self.chapters.get(index).cloned() {
            self.load(db, c);
        }
    }

    fn load(&mut self, db: &Database, chapter: BookChapter) {
        self.paragraphs.clear();
        for page in db.list_expose_pages(chapter.id).unwrap_or_default() {
            for p in db.list_expose_page_paragraphs(chapter.id, page).unwrap_or_default() {
                self.paragraphs.push((page, p));
            }
        }
        let rows: Vec<Paragraph> = self.paragraphs.iter().map(|(_, p)| p.clone()).collect();
        let book = db.book_of_chapter(chapter.id).ok().flatten();
        self.entries = book_entries(&rows, &book_reference(book.as_ref(), &chapter.title));
        self.scroll_entry = Some(0);
        self.chapter = Some(chapter);
    }

    /// Le genre des slides de l'ouvrage (pour l'identification de Branham).
    fn source(&self) -> SlideSource {
        let date = self.chapter.as_ref().and_then(|c| c.date_code.as_deref()).unwrap_or("");
        SlideSource::of_sermon_date(date)
    }

    pub fn prepare(&self, index: usize) -> Option<Prepared> {
        let chapter = self.chapter.as_ref()?;
        let cue = Cue::new(self.source(), chapter.title.clone(), self.entries.clone(), index);
        Some(Prepared { cue, origin: Origin::BookChapter(chapter.id) })
    }

    /// Ouvre un chapitre (résultat de recherche) sur le paragraphe de référence brute `raw_ref`.
    pub fn open(&mut self, db: &Database, chapter_id: i64, raw_ref: Option<&str>) -> Option<Prepared> {
        self.ensure_loaded(db);
        if !self.chapters.iter().any(|c| c.id == chapter_id) {
            let key = db.book_of_chapter(chapter_id).ok().flatten()?.key;
            self.set_book(db, &key);
        }
        let position = self.chapters.iter().position(|c| c.id == chapter_id)?;
        self.scroll_chapter = Some(position);
        self.load(db, self.chapters[position].clone());
        let index = raw_ref
            .and_then(|r| self.paragraphs.iter().position(|(_, p)| p.raw_ref.as_deref() == Some(r)))
            .unwrap_or(0);
        self.scroll_entry = Some(index);
        self.prepare(index)
    }

    pub fn receive(&mut self, query: String, key: String, hits: Vec<BookHit>) {
        if query == self.asked && key == self.key {
            self.hits = hits;
            self.searching = false;
        }
    }

    pub fn ui(&mut self, ui: &mut Ui, db: &Database, marks: &Marks, search: Option<&SearchThread>) -> Option<Action> {
        self.ensure_loaded(db);
        let mut action = None;
        let left = (ui.available_width() * 0.36).clamp(240.0, 340.0);
        ui.horizontal_top(|ui| {
            ui.allocate_ui_with_layout(egui::vec2(left, ui.available_height()), Layout::top_down(Align::Min), |ui| {
                ui.set_width(left);
                action = self.chapter_column(ui, db, search);
            });
            ui.add_space(10.0);
            ui.allocate_ui_with_layout(ui.available_size(), Layout::top_down(Align::Min), |ui| {
                if let Some(a) = self.paragraph_column(ui, marks) {
                    action = Some(a);
                }
            });
        });
        action
    }

    fn chapter_column(&mut self, ui: &mut Ui, db: &Database, search: Option<&SearchThread>) -> Option<Action> {
        let books = self.books.clone().unwrap_or_default();
        if books.len() > 1 {
            let current = self.book().map(|b| b.title.clone()).unwrap_or_default();
            let mut chosen = None;
            egui::ComboBox::from_id_salt(("ouvrage", self.keys[0]))
                .width(ui.available_width())
                .selected_text(current)
                .show_ui(ui, |ui| {
                    for b in &books {
                        if ui.selectable_label(b.key == self.key, &b.title).clicked() {
                            chosen = Some(b.key.clone());
                        }
                    }
                });
            if let Some(key) = chosen {
                self.set_book(db, &key);
            }
            ui.add_space(6.0);
        }
        let r = widgets::search_field(ui, &mut self.query, "Rechercher dans l'ouvrage…", ui.available_width());
        if std::mem::take(&mut self.focus_search) {
            r.request_focus();
        }
        ui.add_space(6.0);
        let q = self.query.trim().to_string();
        if q.chars().count() >= crate::search::MIN_TEXT_QUERY {
            if q != self.asked {
                self.asked = q.clone();
                self.hits.clear();
                if let Some(search) = search {
                    search.ask(Request::Book { query: q, key: self.key.clone() });
                    self.searching = true;
                }
            }
            let status =
                if self.searching { "Recherche…".to_string() } else { format!("{} paragraphes", self.hits.len()) };
            ui.label(RichText::new(status).font(regular(11.5)).color(FAINT));
            let mut opened = None;
            ScrollArea::vertical().id_salt(("recherche-ouvrage", self.keys[0])).auto_shrink([false, false]).show_rows(
                ui,
                ITEM_ROW,
                self.hits.len(),
                |ui, range| {
                    for i in range {
                        let h = &self.hits[i];
                        let title = [h.title.as_str(), h.marker.as_str()]
                            .into_iter()
                            .filter(|s| !s.is_empty())
                            .collect::<Vec<_>>()
                            .join(" · ");
                        let r = item_row(ui, false, &title, &h.text.replace('\n', " "), None);
                        if r.clicked() || r.double_clicked() {
                            opened = Some((h.sermon_id, h.raw_ref.clone(), r.double_clicked()));
                        }
                    }
                },
            );
            let (id, raw, take) = opened?;
            let p = self.open(db, id, raw.as_deref())?;
            return Some(if take { Action::Take(p) } else { Action::Cue(p) });
        }
        self.asked.clear();
        let mut chosen = None;
        let selected = self.chapter.as_ref().map(|c| c.id);
        let mut area = ScrollArea::vertical().id_salt(("chapitres-ouvrage", self.keys[0])).auto_shrink([false, false]);
        if let Some(row) = self.scroll_chapter.take() {
            area = area.vertical_scroll_offset(scroll_offset(ui, row, ITEM_ROW));
        }
        area.show_rows(ui, ITEM_ROW, self.chapters.len(), |ui, range| {
            for i in range {
                let c = &self.chapters[i];
                let number =
                    if c.chapter_num == 0 { "Introduction".to_string() } else { format!("Chapitre {}", c.chapter_num) };
                if item_row(ui, selected == Some(c.id), &c.title, &number, None).clicked() {
                    chosen = Some(c.clone());
                }
            }
        });
        if let Some(c) = chosen {
            self.load(db, c);
        }
        None
    }

    fn paragraph_column(&mut self, ui: &mut Ui, marks: &Marks) -> Option<Action> {
        let Some(chapter) = self.chapter.clone() else {
            super::empty(ui, "Choisissez un chapitre.");
            return None;
        };
        ui.label(RichText::new(&chapter.title).font(semibold(16.0)).color(TEXT));
        let pages = self.paragraphs.iter().map(|(p, _)| *p).collect::<std::collections::BTreeSet<_>>();
        ui.label(
            RichText::new(format!("{} paragraphes · {} pages", self.entries.len(), pages.len()))
                .font(regular(12.0))
                .color(MUTED),
        );
        ui.add_space(8.0);
        let origin = Origin::BookChapter(chapter.id);
        let mut clicked = None;
        let mut menu = None;
        let mut area = ScrollArea::vertical().id_salt(("paragraphes-ouvrage", chapter.id)).auto_shrink([false, false]);
        if let Some(row) = self.scroll_entry.take() {
            area = area.vertical_scroll_offset(scroll_offset(ui, row, ENTRY_ROW));
        }
        area.show_rows(ui, ENTRY_ROW, self.entries.len(), |ui, range| {
            for i in range {
                let (page, p) = &self.paragraphs[i];
                let marker = p
                    .raw_ref
                    .as_deref()
                    .and_then(|r| r.split_whitespace().last())
                    .map_or_else(|| format!("p. {page}"), str::to_string);
                let (preview, live) = marks.of(&origin, i);
                let r = entry_row(ui, &marker, &self.entries[i].text, preview, live);
                let entry = || {
                    Entry::new(playlist_reference(&chapter.title, p.raw_ref.as_deref().unwrap_or("")), p.text.clone())
                };
                if let Some(c) = entry_menu(&r, i, entry, "", "Ajouter une plage de paragraphes…") {
                    menu = Some(c);
                }
                if r.clicked() || r.double_clicked() {
                    clicked = Some((i, r));
                }
            }
        });
        if let Some(choice) = menu {
            let all = || {
                self.paragraphs
                    .iter()
                    .map(|(_, p)| {
                        Entry::new(
                            playlist_reference(&chapter.title, p.raw_ref.as_deref().unwrap_or("")),
                            p.text.clone(),
                        )
                    })
                    .collect()
            };
            return choice_action(choice, |i| self.prepare(i), all, "expose");
        }
        let (index, response) = clicked?;
        Action::from_click(&response, || {
            self.prepare(index)
                .unwrap_or(Prepared { cue: Cue::new(SlideSource::Expose, "", Vec::new(), 0), origin: origin.clone() })
        })
    }
}

#[cfg(test)]
mod tests {
    use super::playlist_reference;

    #[test]
    fn playlist_references_like_the_2x() {
        assert_eq!(playlist_reference("L'Âge d'Éphèse", "40-3"), "L'Âge d'Éphèse · Page 40 §3");
        assert_eq!(playlist_reference("", " 40-3 "), "Page 40 §3");
        assert_eq!(playlist_reference("Le Signe", "BK 40-3"), "Le Signe");
        assert_eq!(playlist_reference("", "E-12"), "E-12");
    }
}
