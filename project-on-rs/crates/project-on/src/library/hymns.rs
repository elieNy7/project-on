//! Cantiques : la liste (numéro ou titre), les strophes du cantique choisi, et la recherche dans
//! les paroles. Le programme suit les réglages de la 2.x (refrain répété après chaque strophe).

use egui::{Align, Layout, RichText, ScrollArea, Ui};
use po_db::{Database, Hymn, HymnHit};
use po_design::SlideSource;
use po_program::{Cue, PreparedStanza, hymn_entries, prepare_stanzas, program_title};

use super::{
    Action, ENTRY_ROW, ITEM_ROW, Marks, Origin, Prepared, choice_action, entry_menu, entry_row, item_row, scroll_offset,
};
use crate::search::{Request, SearchThread};
use crate::theme::*;
use crate::widgets;

#[derive(Default)]
pub struct HymnsView {
    pub query: String,
    loaded: Option<String>,
    hymns: Vec<Hymn>,
    selected: Option<Hymn>,
    stanzas: Vec<PreparedStanza>,
    /// Chercher dans les paroles plutôt que dans les titres.
    pub in_lyrics: bool,
    asked: String,
    hits: Vec<HymnHit>,
    searching: bool,
    pub focus_search: bool,
    scroll_list: Option<usize>,
}

impl HymnsView {
    fn refresh(&mut self, db: &Database) {
        let q = self.query.trim().to_string();
        if self.in_lyrics || self.loaded.as_deref() == Some(q.as_str()) {
            return;
        }
        self.hymns = crate::search::hymns(db, &q);
        self.loaded = Some(q);
    }

    pub fn hymn_count(&self) -> usize {
        self.hymns.len()
    }

    pub fn select(&mut self, db: &Database, index: usize) {
        self.refresh(db);
        if let Some(h) = self.hymns.get(index).cloned() {
            self.load(db, h);
        }
    }

    fn load(&mut self, db: &Database, hymn: Hymn) {
        let stanzas = db.stanzas(hymn.id).unwrap_or_default();
        self.stanzas = prepare_stanzas(&stanzas, hymn.number.as_deref().unwrap_or(""), &hymn.title);
        self.selected = Some(hymn);
    }

    /// Le programme du cantique, à partir de la strophe `index` (refrain répété selon les réglages).
    pub fn prepare(&self, index: usize, repeat_chorus: bool) -> Option<Prepared> {
        let hymn = self.selected.as_ref()?;
        let entries = hymn_entries(&self.stanzas, repeat_chorus);
        // La strophe cliquée dans le programme (le refrain répété : sa première place).
        let clicked = &self.stanzas.get(index)?.reference;
        let focus = entries.iter().position(|e| &e.reference == clicked).unwrap_or(0);
        let title = program_title(hymn.number.as_deref().unwrap_or(""), &hymn.title);
        let cue = Cue::new(SlideSource::Hymn, if title.is_empty() { "Cantique".into() } else { title }, entries, focus);
        Some(Prepared { cue, origin: Origin::Hymn(hymn.id) })
    }

    pub fn receive(&mut self, query: String, hits: Vec<HymnHit>) {
        if query == self.asked {
            self.hits = hits;
            self.searching = false;
        }
    }

    pub fn ui(
        &mut self,
        ui: &mut Ui,
        db: &Database,
        marks: &Marks,
        search: Option<&SearchThread>,
        repeat_chorus: bool,
    ) -> Option<Action> {
        self.refresh(db);
        let mut action = None;
        let left = (ui.available_width() * 0.40).clamp(240.0, 360.0);
        ui.horizontal_top(|ui| {
            ui.allocate_ui_with_layout(egui::vec2(left, ui.available_height()), Layout::top_down(Align::Min), |ui| {
                ui.set_width(left);
                self.list_column(ui, db, search);
            });
            ui.add_space(10.0);
            ui.allocate_ui_with_layout(ui.available_size(), Layout::top_down(Align::Min), |ui| {
                action = self.stanza_column(ui, marks, repeat_chorus);
            });
        });
        action
    }

    fn list_column(&mut self, ui: &mut Ui, db: &Database, search: Option<&SearchThread>) {
        let hint = if self.in_lyrics { "Mots des paroles…" } else { "Numéro ou titre…" };
        let r = widgets::search_field(ui, &mut self.query, hint, ui.available_width());
        if std::mem::take(&mut self.focus_search) {
            r.request_focus();
        }
        ui.add_space(6.0);
        let mut lyrics = self.in_lyrics;
        if widgets::segmented(ui, &mut lyrics, &[(false, "Titres"), (true, "Paroles")]) {
            self.in_lyrics = lyrics;
            self.loaded = None;
            self.asked.clear();
        }
        ui.add_space(4.0);
        let mut chosen: Option<Hymn> = None;
        if self.in_lyrics {
            let q = self.query.trim().to_string();
            if q != self.asked {
                self.asked = q.clone();
                self.hits.clear();
                self.searching = false;
                if q.chars().count() >= crate::search::MIN_TEXT_QUERY
                    && let Some(search) = search
                {
                    search.ask(Request::Stanzas { query: q });
                    self.searching = true;
                }
            }
            let status =
                if self.searching { "Recherche…".to_string() } else { format!("{} strophes", self.hits.len()) };
            ui.label(RichText::new(status).font(regular(11.5)).color(FAINT));
            ScrollArea::vertical().id_salt("paroles").auto_shrink([false, false]).show_rows(
                ui,
                ITEM_ROW,
                self.hits.len(),
                |ui, range| {
                    for i in range {
                        let h = &self.hits[i];
                        let number = h.hymn_number.as_deref().unwrap_or("");
                        let title = if number.is_empty() {
                            h.hymn_title.clone()
                        } else {
                            format!("{number} · {}", h.hymn_title)
                        };
                        if item_row(ui, false, &title, &h.text.replace('\n', " / "), None).clicked() {
                            chosen = db.hymn(h.hymn_id).ok().flatten();
                        }
                    }
                },
            );
        } else {
            ui.label(RichText::new(format!("{} cantiques", self.hymns.len())).font(regular(11.5)).color(FAINT));
            ui.add_space(4.0);
            let selected_id = self.selected.as_ref().map(|h| h.id);
            let mut area = ScrollArea::vertical().id_salt("liste-cantiques").auto_shrink([false, false]);
            if let Some(row) = self.scroll_list.take() {
                area = area.vertical_scroll_offset(scroll_offset(ui, row, ITEM_ROW));
            }
            area.show_rows(ui, ITEM_ROW, self.hymns.len(), |ui, range| {
                for i in range {
                    let h = &self.hymns[i];
                    let number = h.number.as_deref().unwrap_or("");
                    let subtitle = h.language.as_deref().map(str::to_uppercase).unwrap_or_default();
                    let title = if number.is_empty() { h.title.clone() } else { format!("{number} · {}", h.title) };
                    if item_row(ui, selected_id == Some(h.id), &title, &subtitle, None).clicked() {
                        chosen = Some(h.clone());
                    }
                }
            });
        }
        if let Some(h) = chosen {
            self.load(db, h);
        }
    }

    fn stanza_column(&mut self, ui: &mut Ui, marks: &Marks, repeat_chorus: bool) -> Option<Action> {
        let Some(hymn) = self.selected.clone() else {
            super::empty(ui, "Choisissez un cantique.");
            return None;
        };
        let number = hymn.number.as_deref().unwrap_or("");
        let title = if number.is_empty() { hymn.title.clone() } else { format!("{number} · {}", hymn.title) };
        ui.label(RichText::new(title).font(semibold(16.0)).color(TEXT));
        ui.label(RichText::new(format!("{} strophes", self.stanzas.len())).font(regular(12.0)).color(MUTED));
        ui.add_space(8.0);
        let origin = Origin::Hymn(hymn.id);
        // Les marques portent sur les entrées du programme (refrain répété) : on les ramène aux strophes.
        let entries = hymn_entries(&self.stanzas, repeat_chorus);
        let mut clicked = None;
        let mut menu = None;
        ScrollArea::vertical().id_salt(("strophes", hymn.id)).auto_shrink([false, false]).show_rows(
            ui,
            ENTRY_ROW,
            self.stanzas.len(),
            |ui, range| {
                for i in range {
                    let s = &self.stanzas[i];
                    let marked = |m: &Option<(Origin, usize)>| {
                        m.as_ref().is_some_and(|(o, e)| {
                            *o == origin && entries.get(*e).is_some_and(|x| x.reference == s.reference)
                        })
                    };
                    let r = entry_row(ui, &s.label, &s.text, marked(&marks.preview), marked(&marks.live));
                    let entry = || po_program::Entry::new(s.reference.clone(), s.text.clone());
                    if let Some(c) = entry_menu(&r, i, entry, "Ajouter tout le cantique", "") {
                        menu = Some(c);
                    }
                    if r.clicked() || r.double_clicked() {
                        clicked = Some((i, r));
                    }
                }
            },
        );
        if let Some(choice) = menu {
            let all =
                || self.stanzas.iter().map(|s| po_program::Entry::new(s.reference.clone(), s.text.clone())).collect();
            return choice_action(choice, |i| self.prepare(i, repeat_chorus), all, "hymn");
        }
        let (index, response) = clicked?;
        Action::from_click(&response, || {
            self.prepare(index, repeat_chorus)
                .unwrap_or(Prepared { cue: Cue::new(SlideSource::Hymn, "", Vec::new(), 0), origin: origin.clone() })
        })
    }
}
