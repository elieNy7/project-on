//! Prédications : la liste des sermons (titre, traduction), les paragraphes du sermon choisi
//! (filtre « §12 » ou un mot), et la recherche dans les paragraphes de tous les sermons (Ctrl+G).

use egui::{Align, Layout, RichText, ScrollArea, Ui};
use po_db::{Database, ParagraphHit, Sermon, SermonFilter};
use po_design::SlideSource;
use po_program::{Cue, Entry, find_entry, program_title, sermon_entries};
use po_text::fold;

use super::{
    Action, ENTRY_ROW, ITEM_ROW, Marks, Origin, Prepared, choice_action, entry_menu, entry_row, item_row, scroll_offset,
};
use crate::search::{Request, SearchThread};
use crate::theme::*;
use crate::widgets;

/// Le filtre de traduction.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Translator {
    All,
    Vgr,
    Shp,
    Bss,
}

impl Translator {
    fn code(self) -> Option<&'static str> {
        match self {
            Translator::All => None,
            Translator::Vgr => Some("VGR"),
            Translator::Shp => Some("SHP"),
            Translator::Bss => Some("BSS"),
        }
    }
}

/// Le repère d'une entrée : le dernier morceau de sa référence (« ¶12 », « E-76 »).
pub fn marker_of(reference: &str) -> &str {
    reference.rsplit(" - ").next().unwrap_or(reference)
}

/// Le filtre des paragraphes : « §12 » ou « 12 » cherche le repère, sinon un mot du texte.
pub fn matches_filter(entry: &Entry, filter: &str) -> bool {
    let f = filter.trim();
    if f.is_empty() {
        return true;
    }
    let digits = f.trim_start_matches(['§', '¶', 'E', 'e', '-', ' ']);
    if !digits.is_empty() && digits.chars().all(|c| c.is_ascii_digit()) {
        let marker: String = marker_of(&entry.reference).chars().filter(char::is_ascii_digit).collect();
        return marker == digits;
    }
    fold(&entry.text).to_lowercase().contains(&fold(f).to_lowercase())
}

#[derive(Default)]
pub struct SermonsView {
    pub query: String,
    loaded: Option<(String, Option<&'static str>)>,
    translator: Option<Translator>,
    sermons: Vec<Sermon>,
    selected: Option<Sermon>,
    entries: Vec<Entry>,
    pub filter: String,
    /// La recherche dans les paragraphes de tous les sermons (Ctrl+G).
    pub search_mode: bool,
    pub paragraph_query: String,
    asked: String,
    hits: Vec<ParagraphHit>,
    searching: bool,
    pub focus_search: bool,
    scroll_list: Option<usize>,
    scroll_entry: Option<usize>,
}

impl SermonsView {
    fn translator(&self) -> Translator {
        self.translator.unwrap_or(Translator::All)
    }

    pub fn sermon_count(&self) -> usize {
        self.sermons.len()
    }

    pub fn entry_count(&self) -> usize {
        self.entries.len()
    }

    pub fn selected(&self) -> Option<&Sermon> {
        self.selected.as_ref()
    }

    fn refresh(&mut self, db: &Database) {
        let key = (self.query.trim().to_string(), self.translator().code());
        if self.loaded.as_ref() == Some(&key) {
            return;
        }
        let filter = SermonFilter {
            language: Some("fr"),
            title: (!key.0.is_empty()).then_some(key.0.as_str()),
            translator: key.1,
            ..Default::default()
        };
        self.sermons = db.list_sermons(&filter).unwrap_or_default();
        self.loaded = Some(key);
    }

    /// Choisit un sermon de la liste (par son rang).
    pub fn select(&mut self, db: &Database, index: usize) {
        self.refresh(db);
        if let Some(sermon) = self.sermons.get(index).cloned() {
            self.load(db, sermon);
        }
    }

    fn load(&mut self, db: &Database, sermon: Sermon) {
        let paragraphs = db.paragraphs(sermon.id).unwrap_or_default();
        self.entries = sermon_entries(&paragraphs, sermon.date.as_deref().unwrap_or(""), &sermon.title);
        self.filter.clear();
        self.scroll_entry = Some(0);
        self.selected = Some(sermon);
    }

    /// Le programme du sermon choisi, à partir de l'entrée `index`.
    pub fn prepare(&self, index: usize) -> Option<Prepared> {
        let sermon = self.selected.as_ref()?;
        let date = sermon.date.as_deref().unwrap_or("");
        let cue = Cue::new(
            SlideSource::of_sermon_date(date),
            program_title(date, &sermon.title),
            self.entries.clone(),
            index,
        );
        Some(Prepared { cue, origin: Origin::Sermon(sermon.id) })
    }

    /// Ouvre un sermon (résultat de recherche) sur le paragraphe `reference`.
    pub fn open(&mut self, db: &Database, sermon_id: i64, reference: Option<&str>) -> Option<Prepared> {
        let sermon = db.sermon(sermon_id).ok().flatten()?;
        self.load(db, sermon);
        if let Some(i) = self.sermons.iter().position(|s| s.id == sermon_id) {
            self.scroll_list = Some(i);
        }
        let index = reference.map_or(0, |r| find_entry(&self.entries, r));
        self.scroll_entry = Some(index);
        self.prepare(index)
    }

    /// Les résultats de Ctrl+G arrivés du fil de recherche.
    pub fn receive(&mut self, query: String, hits: Vec<ParagraphHit>) {
        if query == self.asked {
            self.hits = hits;
            self.searching = false;
        }
    }

    pub fn ui(&mut self, ui: &mut Ui, db: &Database, marks: &Marks, search: Option<&SearchThread>) -> Option<Action> {
        self.refresh(db);
        let mut action = None;
        let width = ui.available_width();
        let left = (width * 0.40).clamp(260.0, 380.0);
        ui.horizontal_top(|ui| {
            ui.allocate_ui_with_layout(egui::vec2(left, ui.available_height()), Layout::top_down(Align::Min), |ui| {
                ui.set_width(left);
                if self.search_mode {
                    action = self.search_column(ui, db, search);
                } else {
                    self.list_column(ui, db);
                }
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

    fn list_column(&mut self, ui: &mut Ui, db: &Database) {
        ui.horizontal(|ui| {
            let r = widgets::search_field(ui, &mut self.query, "Rechercher un sermon…", ui.available_width() - 108.0);
            if std::mem::take(&mut self.focus_search) {
                r.request_focus();
            }
            if widgets::button(ui, None, "Paragraphes", widgets::Tone::Secondary)
                .on_hover_text("Chercher dans les paragraphes de tous les sermons (Ctrl+G)")
                .clicked()
            {
                self.search_mode = true;
                self.focus_search = true;
            }
        });
        ui.add_space(6.0);
        let mut t = self.translator();
        if widgets::segmented(
            ui,
            &mut t,
            &[
                (Translator::All, "Toutes"),
                (Translator::Vgr, "VGR"),
                (Translator::Shp, "SHP"),
                (Translator::Bss, "BSS"),
            ],
        ) {
            self.translator = Some(t);
            self.refresh(db);
        }
        ui.add_space(4.0);
        ui.label(RichText::new(format!("{} sermons", self.sermons.len())).font(regular(11.5)).color(FAINT));
        ui.add_space(4.0);
        let mut chosen = None;
        let selected_id = self.selected.as_ref().map(|s| s.id);
        let mut area = ScrollArea::vertical().id_salt("liste-sermons").auto_shrink([false, false]);
        if let Some(row) = self.scroll_list.take() {
            area = area.vertical_scroll_offset(scroll_offset(ui, row, ITEM_ROW));
        }
        area.show_rows(ui, ITEM_ROW, self.sermons.len(), |ui, range| {
            for i in range {
                let s = &self.sermons[i];
                let date = s.date.as_deref().unwrap_or("");
                let subtitle =
                    if s.location.is_empty() { date.to_string() } else { format!("{date} · {}", s.location) };
                if item_row(ui, selected_id == Some(s.id), &s.title, &subtitle, Some(&s.tradition)).clicked() {
                    chosen = Some(s.clone());
                }
            }
        });
        if let Some(sermon) = chosen {
            self.load(db, sermon);
        }
    }

    fn search_column(&mut self, ui: &mut Ui, db: &Database, search: Option<&SearchThread>) -> Option<Action> {
        ui.horizontal(|ui| {
            let r = widgets::search_field(
                ui,
                &mut self.paragraph_query,
                "Mots d'un paragraphe…",
                ui.available_width() - 80.0,
            );
            if std::mem::take(&mut self.focus_search) {
                r.request_focus();
            }
            if widgets::button(ui, None, "Sermons", widgets::Tone::Secondary).clicked() {
                self.search_mode = false;
            }
        });
        let q = self.paragraph_query.trim().to_string();
        if q != self.asked {
            self.asked = q.clone();
            self.hits.clear();
            if q.chars().count() >= crate::search::MIN_TEXT_QUERY
                && let Some(search) = search
            {
                search.ask(Request::Paragraphs { query: q, translator: self.translator().code().map(str::to_string) });
                self.searching = true;
            } else {
                self.searching = false;
            }
        }
        ui.add_space(6.0);
        let status = if self.searching {
            "Recherche…".to_string()
        } else if self.asked.chars().count() < crate::search::MIN_TEXT_QUERY {
            "Au moins trois lettres".to_string()
        } else {
            format!("{} paragraphes", self.hits.len())
        };
        ui.label(RichText::new(status).font(regular(11.5)).color(FAINT));
        ui.add_space(4.0);
        let mut opened = None;
        ScrollArea::vertical().id_salt("resultats-paragraphes").auto_shrink([false, false]).show_rows(
            ui,
            ITEM_ROW,
            self.hits.len(),
            |ui, range| {
                for i in range {
                    let hit = &self.hits[i];
                    let title = format!("{} {}", hit.sermon_title, hit.marker);
                    let r = item_row(ui, false, &title, &hit.text.replace('\n', " "), Some(&hit.sermon_tradition));
                    if r.clicked() || r.double_clicked() {
                        opened = Some((hit.sermon_id, hit.reference.clone(), r.double_clicked()));
                    }
                }
            },
        );
        let (id, reference, take) = opened?;
        let prepared = self.open(db, id, Some(&reference))?;
        Some(if take { Action::Take(prepared) } else { Action::Cue(prepared) })
    }

    fn paragraph_column(&mut self, ui: &mut Ui, marks: &Marks) -> Option<Action> {
        let Some(sermon) = self.selected.clone() else {
            super::empty(ui, "Choisissez un sermon dans la liste.");
            return None;
        };
        ui.horizontal(|ui| {
            ui.vertical(|ui| {
                ui.label(RichText::new(&sermon.title).font(semibold(16.0)).color(TEXT));
                let date = sermon.date.as_deref().unwrap_or("");
                let info = [date, sermon.location.as_str(), sermon.tradition.as_str()]
                    .into_iter()
                    .filter(|s| !s.is_empty())
                    .collect::<Vec<_>>()
                    .join(" · ");
                ui.label(RichText::new(info).font(regular(12.0)).color(MUTED));
            });
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                widgets::search_field(ui, &mut self.filter, "Filtrer (§12 ou mot)…", 200.0);
            });
        });
        ui.add_space(8.0);
        let origin = Origin::Sermon(sermon.id);
        let visible: Vec<usize> =
            (0..self.entries.len()).filter(|&i| matches_filter(&self.entries[i], &self.filter)).collect();
        let mut clicked = None;
        let mut menu = None;
        let mut area = ScrollArea::vertical().id_salt(("paragraphes", sermon.id)).auto_shrink([false, false]);
        if let Some(entry) = self.scroll_entry.take()
            && let Some(row) = visible.iter().position(|&i| i == entry)
        {
            area = area.vertical_scroll_offset(scroll_offset(ui, row, ENTRY_ROW));
        }
        area.show_rows(ui, ENTRY_ROW, visible.len(), |ui, range| {
            for row in range {
                let i = visible[row];
                let entry = &self.entries[i];
                let (preview, live) = marks.of(&origin, i);
                let r = entry_row(ui, marker_of(&entry.reference), &entry.text, preview, live);
                // « Ajouter à la playlist » prend le paragraphe entier (ses alinéas, un par ligne).
                if let Some(c) = entry_menu(&r, i, || entry.clone(), "", "Ajouter une plage de paragraphes…") {
                    menu = Some(c);
                }
                if r.clicked() || r.double_clicked() {
                    clicked = Some((i, r));
                }
            }
        });
        if let Some(choice) = menu {
            return choice_action(choice, |i| self.prepare(i), || self.entries.clone(), "sermon");
        }
        let (index, response) = clicked?;
        Action::from_click(&response, || self.prepare(index).unwrap_or_else(|| unreachable_prepared(&origin)))
    }
}

/// Un sermon est toujours choisi quand ses paragraphes sont montrés.
fn unreachable_prepared(origin: &Origin) -> Prepared {
    Prepared { cue: Cue::new(SlideSource::Sermon, "", Vec::new(), 0), origin: origin.clone() }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn paragraph_filter() {
        let e = Entry::new("63-0317M - Titre - ¶12", "La grâce de Dieu.");
        assert!(matches_filter(&e, "§12"));
        assert!(matches_filter(&e, "12"));
        assert!(!matches_filter(&e, "§1"));
        assert!(matches_filter(&e, "grace"));
        assert!(matches_filter(&e, "GRÂCE"));
        assert!(!matches_filter(&e, "colère"));
        let shp = Entry::new("47-1123 - Titre - E-76", "Texte");
        assert!(matches_filter(&shp, "E-76") && matches_filter(&shp, "76"));
    }
}
