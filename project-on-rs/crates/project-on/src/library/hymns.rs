//! Cantiques : la liste (numéro ou titre), les strophes du cantique choisi, et la recherche dans
//! les paroles. Le programme suit les réglages de la 2.x (refrain répété après chaque strophe).

use egui::{Align, Layout, RichText, ScrollArea, Ui};
use po_db::{Database, Hymn, HymnHit};
use po_design::SlideSource;
use po_program::{Cue, PreparedStanza, hymn_entries, prepare_stanzas, program_title};

use super::{
    Action, ENTRY_ROW, ITEM_ROW, Marks, Origin, Prepared, choice_action, entry_menu, entry_row, item_row, scroll_offset,
};
use crate::hymn_editor::{Draft, LANGUAGES, parse_stanzas, preview, toggle_chorus_at};
use crate::search::{Request, SearchThread};
use crate::theme::*;
use crate::widgets::{self, Tone};

/// Ce que l'éditeur demande à la régie (qui écrit dans la base).
#[derive(Debug, Clone, PartialEq)]
pub enum HymnRequest {
    Save(Draft),
    Delete(i64),
}

#[derive(Default)]
pub struct HymnsView {
    /// « Importer un PDF… » demandé.
    pub import_pdf: bool,
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
    /// Le cantique en cours d'édition, et la place du curseur dans ses paroles.
    pub editor: Option<Draft>,
    editor_cursor: usize,
    pub editor_error: Option<String>,
    /// Le cantique dont la suppression attend une confirmation.
    confirm_delete: Option<(i64, String)>,
    pub request: Option<HymnRequest>,
    /// « Modifier » cliqué (la colonne des strophes n'a pas la base sous la main).
    edit_selected: bool,
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

    /// Après un enregistrement : la liste est relue et le cantique choisi.
    pub fn saved(&mut self, db: &Database, id: i64) {
        self.loaded = None;
        self.refresh(db);
        if let Some(index) = self.hymns.iter().position(|h| h.id == id) {
            self.scroll_list = Some(index);
        }
        if let Ok(Some(hymn)) = db.hymn(id) {
            self.load(db, hymn);
        }
        self.editor = None;
        self.editor_error = None;
    }

    /// Après un import : la liste est relue.
    pub fn reload(&mut self, db: &Database) {
        self.loaded = None;
        self.refresh(db);
    }

    /// Après une suppression.
    pub fn deleted(&mut self, db: &Database) {
        self.loaded = None;
        self.selected = None;
        self.stanzas.clear();
        self.refresh(db);
    }

    pub fn selected_id(&self) -> Option<i64> {
        self.selected.as_ref().map(|h| h.id)
    }

    /// Ouvre l'éditeur : un nouveau cantique, ou celui choisi.
    pub fn edit(&mut self, db: &Database, id: Option<i64>) {
        let draft = match id.and_then(|id| db.hymn(id).ok().flatten()) {
            Some(hymn) => Draft::of(&hymn, &db.stanzas(hymn.id).unwrap_or_default()),
            None => Draft::default(),
        };
        self.editor_cursor = draft.text.chars().count();
        self.editor = Some(draft);
        self.editor_error = None;
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
        self.editor_window(ui);
        self.delete_window(ui);
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
        if std::mem::take(&mut self.edit_selected) {
            let id = self.selected_id();
            self.edit(db, id);
        }
        action
    }

    fn list_column(&mut self, ui: &mut Ui, db: &Database, search: Option<&SearchThread>) {
        let hint = if self.in_lyrics { "Mots des paroles…" } else { "Numéro ou titre…" };
        let r = widgets::search_field(ui, &mut self.query, hint, ui.available_width() - 96.0);
        ui.horizontal(|ui| {
            if widgets::button(ui, Some(crate::icons::Icon::Plus), "Nouveau cantique", Tone::Secondary).clicked() {
                self.edit(db, None);
            }
            if widgets::button(ui, None, "Importer un PDF…", Tone::Secondary)
                .on_hover_text("Les cantiques d'un recueil en PDF (numéros, titres, strophes, refrains)")
                .clicked()
            {
                self.import_pdf = true;
            }
        });
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

    /// La fenêtre de l'éditeur : à gauche les paroles, à droite le découpage reconnu.
    fn editor_window(&mut self, ui: &mut Ui) {
        let Some(mut draft) = self.editor.take() else { return };
        let mut open = true;
        let mut save = false;
        let title = if draft.id.is_some() { "Modifier le cantique" } else { "Nouveau cantique" };
        egui::Window::new(title)
            .open(&mut open)
            .collapsible(false)
            .default_size([760.0, 560.0])
            .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
            .show(ui.ctx(), |ui| {
                ui.horizontal(|ui| {
                    ui.label("Titre");
                    let r = ui.add(
                        egui::TextEdit::singleline(&mut draft.title).hint_text("À toi la gloire").desired_width(280.0),
                    );
                    ui.ctx().accesskit_node_builder(r.id, |n| n.set_label("Titre du cantique"));
                    ui.label("Numéro");
                    let r =
                        ui.add(egui::TextEdit::singleline(&mut draft.number).hint_text("ex. 42").desired_width(70.0));
                    ui.ctx().accesskit_node_builder(r.id, |n| n.set_label("Numéro du cantique"));
                    let shown = LANGUAGES
                        .iter()
                        .find(|(_, c)| *c == draft.language)
                        .map_or(draft.language.clone(), |(l, _)| (*l).to_string());
                    egui::ComboBox::from_id_salt("langue-cantique").selected_text(shown).show_ui(ui, |ui| {
                        for (label, code) in LANGUAGES {
                            ui.selectable_value(&mut draft.language, code.to_string(), label);
                        }
                    });
                });
                ui.add_space(6.0);
                ui.horizontal(|ui| {
                    if widgets::button(ui, None, "Refrain", Tone::Secondary)
                        .on_hover_text("Marquer / démarquer comme refrain la strophe du curseur")
                        .clicked()
                    {
                        let (text, cursor) = toggle_chorus_at(&draft.text, self.editor_cursor);
                        draft.text = text;
                        self.editor_cursor = cursor;
                    }
                    ui.label(RichText::new("Une ligne vide sépare les strophes.").font(regular(12.0)).color(MUTED));
                });
                let stanzas = parse_stanzas(&draft.text);
                ui.horizontal_top(|ui| {
                    let width = ui.available_width() * 0.62;
                    let output = egui::TextEdit::multiline(&mut draft.text)
                        .hint_text("Strophe 1, ligne 1\nStrophe 1, ligne 2\n\nRefrain\nLigne du refrain\n\nStrophe 2…")
                        .desired_width(width)
                        .desired_rows(18)
                        .show(ui);
                    ui.ctx().accesskit_node_builder(output.response.id, |n| n.set_label("Paroles du cantique"));
                    if let Some(range) = output.cursor_range {
                        self.editor_cursor = range.primary.index.0;
                    }
                    ui.vertical(|ui| {
                        ui.label(RichText::new("DÉCOUPAGE RECONNU").font(semibold(10.5)).color(FAINT));
                        egui::ScrollArea::vertical().id_salt("decoupage").max_height(380.0).show(ui, |ui| {
                            for (label, first) in preview(&stanzas) {
                                ui.label(RichText::new(label).font(semibold(12.0)).color(TEXT));
                                ui.label(RichText::new(first).font(regular(11.5)).color(MUTED));
                                ui.add_space(4.0);
                            }
                        });
                    });
                });
                if let Some(error) = &self.editor_error {
                    ui.label(RichText::new(error).font(medium(12.0)).color(WARN));
                }
                ui.horizontal(|ui| {
                    if widgets::button(ui, None, "Enregistrer", Tone::Primary(ACCENT)).clicked() {
                        save = true;
                    }
                });
            });
        if save {
            match draft.check() {
                Ok(_) => {
                    self.request = Some(HymnRequest::Save(draft.clone()));
                    self.editor = Some(draft);
                }
                Err(message) => {
                    self.editor_error = Some(message.into());
                    self.editor = Some(draft);
                }
            }
        } else if open {
            self.editor = Some(draft);
        }
    }

    /// La confirmation de suppression (comme la 2.8).
    fn delete_window(&mut self, ui: &mut Ui) {
        let Some((id, title)) = self.confirm_delete.clone() else { return };
        let mut answer = None;
        egui::Window::new("Supprimer le cantique")
            .collapsible(false)
            .resizable(false)
            .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
            .show(ui.ctx(), |ui| {
                ui.label(format!("Voulez-vous vraiment supprimer le cantique « {title} » ?"));
                ui.horizontal(|ui| {
                    if widgets::button(ui, None, "Supprimer définitivement", Tone::Danger).clicked() {
                        answer = Some(true);
                    }
                    if widgets::button(ui, None, "Annuler", Tone::Secondary).clicked() {
                        answer = Some(false);
                    }
                });
            });
        match answer {
            Some(true) => {
                self.request = Some(HymnRequest::Delete(id));
                self.confirm_delete = None;
            }
            Some(false) => self.confirm_delete = None,
            None => {}
        }
    }

    fn stanza_column(&mut self, ui: &mut Ui, marks: &Marks, repeat_chorus: bool) -> Option<Action> {
        let Some(hymn) = self.selected.clone() else {
            super::empty(ui, "Choisissez un cantique.");
            return None;
        };
        let number = hymn.number.as_deref().unwrap_or("");
        let title = if number.is_empty() { hymn.title.clone() } else { format!("{number} · {}", hymn.title) };
        ui.horizontal(|ui| {
            ui.label(RichText::new(title).font(semibold(16.0)).color(TEXT));
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                if widgets::button(ui, None, "Supprimer", Tone::Danger).clicked() {
                    self.confirm_delete = Some((hymn.id, hymn.title.clone()));
                }
                if widgets::button(ui, None, "Modifier", Tone::Secondary).clicked() {
                    self.edit_selected = true;
                }
            });
        });
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
