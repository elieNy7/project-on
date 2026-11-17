//! La page **Recherche** (Ctrl+K, le champ « Rechercher partout » de la barre du haut), comme
//! l'onglet Recherche de MEDITATION : une requête, cherchée dans les sources cochées (Bible,
//! Prédications, Exposé et livres), les résultats groupés par source, les mots trouvés surlignés
//! d'or. Un clic ouvre le passage dans sa bibliothèque et le prépare dans l'Aperçu ; un double-clic
//! l'envoie au direct.
//!
//! Elle tourne sur un fil à part, avec sa propre connexion en lecture seule : l'interface ne
//! l'attend jamais, et une nouvelle requête abandonne la précédente.

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::mpsc::{Receiver, Sender, TryRecvError, channel};
use std::time::{Duration, Instant};

use egui::text::{LayoutJob, TextFormat, TextWrapping};
use egui::{Align2, CornerRadius, Rect, ScrollArea, Sense, Stroke, Ui, pos2, vec2};
use po_db::{Database, Mode, ParagraphSearch};
use po_search::words::{around, highlights, in_text, occurrences};
use po_search::{MIN_QUERY, MIN_TEXT_QUERY, Searcher, Target};
use po_text::looks_like_reference;

use crate::icons::{self, Icon};
use crate::theme::*;
use crate::widgets;

/// Le plafond par source : sans limite en pratique (un mot très courant trouverait des centaines
/// de milliers de paragraphes ; le plafond protège la mémoire).
pub const CAP: usize = 10_000;
/// Le temps sans frappe avant de chercher (Entrée cherche tout de suite).
const DELAY: Duration = Duration::from_millis(300);

/// Où chercher.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Source {
    Bible,
    Sermons,
    Books,
}

impl Source {
    pub const ALL: [Source; 3] = [Source::Bible, Source::Sermons, Source::Books];

    pub fn label(self) -> &'static str {
        match self {
            Source::Bible => "Bible",
            Source::Sermons => "Prédications",
            Source::Books => "Exposé et livres",
        }
    }
}

/// Les sources cochées. Décochée, une source n'est pas cherchée.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Filters {
    pub bible: bool,
    pub sermons: bool,
    pub books: bool,
}

impl Default for Filters {
    fn default() -> Self {
        Filters { bible: true, sermons: true, books: true }
    }
}

impl Filters {
    pub fn keeps(&self, source: Source) -> bool {
        match source {
            Source::Bible => self.bible,
            Source::Sermons => self.sermons,
            Source::Books => self.books,
        }
    }

    pub fn set(&mut self, source: Source, on: bool) {
        match source {
            Source::Bible => self.bible = on,
            Source::Sermons => self.sermons = on,
            Source::Books => self.books = on,
        }
    }

    pub fn any(&self) -> bool {
        Source::ALL.iter().any(|s| self.keeps(*s))
    }
}

/// Un résultat.
#[derive(Debug, Clone, PartialEq)]
pub struct Found {
    pub source: Source,
    pub title: String,
    pub excerpt: String,
    pub target: Target,
}

/// Cherche `query` dans `source` ; `translation` : la Bible où chercher.
pub fn find(searcher: &mut Searcher, source: Source, query: &str, translation: Option<i64>) -> Vec<Found> {
    let q = query.trim();
    if q.chars().count() < MIN_QUERY {
        return Vec::new();
    }
    let words = highlights(q);
    let text_search = q.chars().count() >= MIN_TEXT_QUERY && !looks_like_reference(q);
    match source {
        Source::Bible => {
            let hits = searcher.bible_hits(q, translation, CAP);
            // L'extrait vient du verset entier (la recherche le coupe à 140 lettres, parfois avant
            // le mot trouvé) ; les versets sont lus chapitre par chapitre.
            let mut chapters: HashMap<(i64, i64, i64), Vec<po_db::Verse>> = HashMap::new();
            let db = searcher.database();
            hits.into_iter()
                .map(|h| {
                    let excerpt = match &h.target {
                        Target::Verse { translation, book, chapter, verse: Some(n) } => {
                            let verses = chapters.entry((*translation, *book, *chapter)).or_insert_with(|| {
                                db.list_translation_verses(*translation, *book, *chapter).unwrap_or_default()
                            });
                            verses.iter().find(|v| v.verse == *n).map(|v| po_text::clean_text(&v.text))
                        }
                        _ => None,
                    };
                    let excerpt = excerpt.map_or(h.subtitle, |t| around(&t, &words, 240));
                    Found { source, title: h.title, excerpt, target: h.target }
                })
                .collect()
        }
        Source::Sermons => {
            // Le texte seulement, jamais le titre (il se cherche dans la page Prédications).
            if !text_search {
                return Vec::new();
            }
            let search = ParagraphSearch {
                query: q,
                language: Some("fr"),
                translator: None,
                limit: CAP,
                substring_fallback: true,
            };
            searcher
                .database()
                .search_paragraphs(&search)
                .unwrap_or_default()
                .into_iter()
                .filter(|p| in_text(&p.text, q))
                .map(|p| Found {
                    source,
                    title: [p.sermon_date.unwrap_or_default(), p.sermon_title, p.marker]
                        .into_iter()
                        .filter(|t| !t.is_empty())
                        .collect::<Vec<_>>()
                        .join(" · "),
                    excerpt: around(&p.text, &words, 320),
                    target: Target::Sermon { sermon_id: p.sermon_id, reference: Some(p.reference) },
                })
                .collect()
        }
        Source::Books => {
            if !text_search {
                return Vec::new();
            }
            let db = searcher.database();
            let mut out = Vec::new();
            // Tous les ouvrages de la base, dans son ordre : les Exposés, puis les livres.
            for book in db.list_books().unwrap_or_default() {
                for p in db.search_book(q, &book.key, CAP).unwrap_or_default() {
                    let title = [p.title.as_str(), p.marker.as_str()]
                        .into_iter()
                        .filter(|s| !s.is_empty())
                        .collect::<Vec<_>>()
                        .join(" · ");
                    out.push(Found {
                        source,
                        title: if title.is_empty() { p.reference.clone() } else { title },
                        excerpt: around(&p.text, &words, 240),
                        target: Target::Book { chapter_id: p.sermon_id, raw_ref: p.raw_ref },
                    });
                }
            }
            out
        }
    }
}

/// Une recherche demandée au fil (`n` : son numéro ; seule la dernière compte).
#[derive(Debug, Clone)]
struct Ask {
    n: u64,
    query: String,
    filters: Filters,
    translation: Option<i64>,
}

/// Ce que rend le fil : les résultats d'une source, puis la fin de la recherche.
enum Message {
    Found { n: u64, found: Vec<Found> },
    Done { n: u64 },
}

/// Le fil de recherche, avec sa propre connexion (en lecture seule).
struct Worker {
    asks: Sender<Ask>,
    messages: Receiver<Message>,
}

impl Worker {
    fn spawn(db_path: PathBuf, wake: impl Fn() + Send + 'static) -> Worker {
        let (asks, inbox) = channel::<Ask>();
        let (outbox, messages) = channel::<Message>();
        let spawned = std::thread::Builder::new().name("recherche-globale".into()).spawn(move || {
            let Ok(db) = Database::open(&db_path, Mode::ReadOnly) else { return };
            let mut searcher = Searcher::new(db);
            let mut next: Option<Ask> = None;
            loop {
                let mut ask = match next.take() {
                    Some(a) => a,
                    None => match inbox.recv() {
                        Ok(a) => a,
                        Err(_) => return,
                    },
                };
                while let Ok(newer) = inbox.try_recv() {
                    ask = newer;
                }
                for source in Source::ALL.into_iter().filter(|s| ask.filters.keeps(*s)) {
                    let found = find(&mut searcher, source, &ask.query, ask.translation);
                    if outbox.send(Message::Found { n: ask.n, found }).is_err() {
                        return;
                    }
                    wake();
                    // Une nouvelle demande : celle-ci est abandonnée.
                    match inbox.try_recv() {
                        Ok(newer) => {
                            next = Some(newer);
                            break;
                        }
                        Err(TryRecvError::Disconnected) => return,
                        Err(TryRecvError::Empty) => {}
                    }
                }
                if next.is_none() {
                    if outbox.send(Message::Done { n: ask.n }).is_err() {
                        return;
                    }
                    wake();
                }
            }
        });
        if let Err(e) = spawned {
            po_core::journal::line(&format!("fil de recherche globale impossible : {e}"));
        }
        Worker { asks, messages }
    }
}

/// La page Recherche : la requête (tapée dans la barre du haut), les filtres, les résultats.
#[derive(Default)]
pub struct GlobalSearch {
    pub query: String,
    pub filters: Filters,
    worker: Option<Worker>,
    n: u64,
    received: u64,
    asked: Option<(String, Filters, Option<i64>)>,
    typed: Option<Instant>,
    now: bool,
    words: Vec<String>,
    pub results: Vec<Found>,
    pub searching: bool,
    /// Donner le clavier au champ (Ctrl+K).
    pub focus: bool,
    selected: Option<usize>,
}

impl GlobalSearch {
    /// Une frappe dans le champ : la recherche part après un temps sans frappe.
    pub fn typed(&mut self) {
        self.typed = Some(Instant::now());
    }

    /// Entrée : chercher sans attendre.
    pub fn search_now(&mut self) {
        self.now = true;
    }

    /// Range les réponses du fil, puis demande la recherche si la requête, les filtres ou la Bible
    /// ont changé (après un temps sans frappe, ou tout de suite après Entrée).
    pub fn advance(&mut self, ctx: &egui::Context, db_path: Option<&PathBuf>, translation: Option<i64>) {
        let messages: Vec<Message> = self.worker.as_ref().map(|w| w.messages.try_iter().collect()).unwrap_or_default();
        for m in messages {
            match m {
                Message::Found { n, found } if n == self.n => {
                    self.receive(n);
                    self.results.extend(found);
                }
                Message::Done { n } if n == self.n => {
                    self.receive(n);
                    self.searching = false;
                }
                _ => {}
            }
        }
        let wanted = (self.query.trim().to_string(), self.filters, translation);
        if self.asked.as_ref() == Some(&wanted) {
            return;
        }
        if !self.now
            && let Some(t) = self.typed
            && t.elapsed() < DELAY
        {
            ctx.request_repaint_after(DELAY - t.elapsed());
            return;
        }
        self.typed = None;
        self.now = false;
        self.n += 1;
        self.selected = None;
        let query = wanted.0.clone();
        if query.chars().count() < MIN_QUERY || !self.filters.any() || db_path.is_none() {
            self.asked = Some(wanted);
            self.receive(self.n);
            self.searching = false;
            return;
        }
        if self.worker.is_none()
            && let Some(path) = db_path
        {
            let ctx = ctx.clone();
            self.worker = Some(Worker::spawn(path.clone(), move || ctx.request_repaint()));
        }
        self.searching = true;
        if let Some(w) = &self.worker {
            let _ = w.asks.send(Ask { n: self.n, query, filters: self.filters, translation });
        }
        self.asked = Some(wanted);
    }

    /// Les premiers résultats d'une nouvelle recherche remplacent ceux montrés.
    fn receive(&mut self, n: u64) {
        if self.received != n {
            self.received = n;
            self.results.clear();
            self.words = self.asked.as_ref().map(|(q, _, _)| highlights(q)).unwrap_or_default();
        }
    }

    /// La page ; rend le résultat ouvert et s'il va au direct (double-clic).
    pub fn ui(&mut self, ui: &mut Ui) -> Option<(Target, bool)> {
        widgets::section(ui, "Recherche");
        ui.horizontal_wrapped(|ui| {
            ui.spacing_mut().item_spacing = vec2(6.0, 6.0);
            for source in Source::ALL {
                filter_pill(ui, source, &mut self.filters);
            }
        });
        ui.add_space(6.0);
        let status = if self.query.trim().chars().count() < MIN_QUERY {
            "Tapez au moins deux lettres dans le champ du haut (Ctrl+K) : des mots, une « expression » \
             entre guillemets ou une référence (Jean 3:16)."
                .to_string()
        } else if !self.filters.any() {
            "Cochez au moins une source.".to_string()
        } else if self.searching && self.results.is_empty() {
            "Recherche…".to_string()
        } else {
            let n = self.results.len();
            let text = match n {
                0 => "Aucun résultat".to_string(),
                1 => "1 résultat".to_string(),
                n => format!("{n} résultats"),
            };
            let capped = Source::ALL.iter().any(|s| self.results.iter().filter(|r| r.source == *s).count() >= CAP);
            let text = if capped { format!("{text} (10 000 au plus par source : précisez)") } else { text };
            let text = if self.searching { format!("{text} · recherche…") } else { text };
            format!("{text} · clic : aperçu ; double-clic : direct")
        };
        ui.label(egui::RichText::new(status).font(regular(11.5)).color(FAINT));
        ui.add_space(4.0);
        // Les lignes (en-têtes de source, résultats) : seules celles à l'écran sont dessinées.
        let mut rows: Vec<(Option<usize>, Source, f32)> = Vec::with_capacity(self.results.len() + 3);
        for (i, r) in self.results.iter().enumerate() {
            if i == 0 || self.results[i - 1].source != r.source {
                rows.push((None, r.source, HEADER));
            }
            rows.push((Some(i), r.source, row_height(r)));
        }
        let total: f32 = rows.iter().map(|l| l.2).sum();
        let mut opened = None;
        ScrollArea::vertical().id_salt("resultats-globaux").auto_shrink([false, false]).show_viewport(
            ui,
            |ui, view| {
                ui.set_height(total);
                let top = ui.max_rect().min;
                let width = ui.available_width();
                let mut y = 0.0;
                for &(i, source, h) in &rows {
                    if y + h >= view.min.y && y <= view.max.y {
                        let rect = Rect::from_min_size(top + vec2(0.0, y), vec2(width, h));
                        match i {
                            None => {
                                let n = self.results.iter().filter(|x| x.source == source).count();
                                header(ui, rect, source, n);
                            }
                            Some(i) => {
                                let r = &self.results[i];
                                let response = result_row(ui, rect, r, &self.words, self.selected == Some(i));
                                if response.clicked() || response.double_clicked() {
                                    self.selected = Some(i);
                                    opened = Some((r.target.clone(), response.double_clicked()));
                                }
                            }
                        }
                    }
                    y += h;
                }
            },
        );
        opened
    }
}

/// Une case à cocher en pastille (une source de la recherche).
fn filter_pill(ui: &mut Ui, source: Source, filters: &mut Filters) {
    let on = filters.keeps(source);
    let g = ui.painter().layout_no_wrap(source.label().to_string(), medium(12.0), TEXT);
    let size = vec2(g.size().x + 34.0, 26.0);
    let (rect, r) = ui.allocate_exact_size(size, Sense::click());
    r.widget_info(|| egui::WidgetInfo::selected(egui::Role::CheckBox, true, on, source.label()));
    if r.clicked() {
        filters.set(source, !on);
    }
    let t = widgets::hover_t(ui, &r, r.hovered());
    let painter = ui.painter();
    let (fill, stroke, ink) = if on {
        (ACCENT.gamma_multiply(0.16 + 0.06 * t), ACCENT.gamma_multiply(0.55), TEXT)
    } else {
        (SURFACE.gamma_multiply(0.5 + 0.5 * t), BORDER_STRONG, MUTED)
    };
    painter.rect(rect, CornerRadius::same(13), fill, Stroke::new(1.0, stroke), egui::StrokeKind::Inside);
    let check = Rect::from_center_size(pos2(rect.min.x + 14.0, rect.center().y), vec2(12.0, 12.0));
    if on {
        icons::paint(painter, check, Icon::Check, ACCENT);
    } else {
        painter.circle_stroke(check.center(), 4.5, Stroke::new(1.2, ink.gamma_multiply(0.8)));
    }
    painter.galley(pos2(rect.min.x + 25.0, rect.center().y - g.size().y / 2.0), g, ink);
}

/// La hauteur d'un en-tête de source.
const HEADER: f32 = 30.0;

/// La hauteur d'une ligne : le titre, puis trois lignes d'extrait pour une prédication, deux pour
/// les autres.
fn row_height(r: &Found) -> f32 {
    if r.source == Source::Sermons { 88.0 } else { 70.0 }
}

/// L'en-tête d'une source (« BIBLE · 12 »).
fn header(ui: &Ui, rect: Rect, source: Source, n: usize) {
    widgets::paint_text(
        ui,
        pos2(rect.min.x + 4.0, rect.max.y - 11.0),
        Align2::LEFT_CENTER,
        &format!("{} · {n}", source.label().to_uppercase()),
        semibold(10.5),
        ACCENT,
        rect.width() - 8.0,
    );
}

/// Une ligne de résultat : le titre et l'extrait, les mots trouvés surlignés d'or.
fn result_row(ui: &mut Ui, rect: Rect, r: &Found, words: &[String], selected: bool) -> egui::Response {
    let line = Rect::from_min_size(rect.min, vec2(rect.width(), rect.height() - 4.0));
    let response = ui
        .scope_builder(egui::UiBuilder::new().max_rect(line), |ui| {
            widgets::list_row(ui, selected, line.height(), &r.title).1
        })
        .inner;
    let w = line.width() - 22.0;
    let x = line.min.x + 12.0;
    widgets::paint_text(ui, pos2(x, line.min.y + 7.0), Align2::LEFT_TOP, &r.title, semibold(12.5), TEXT, w);
    let lines = if r.source == Source::Sermons { 3 } else { 2 };
    let g = ui.painter().layout_job(excerpt(&r.excerpt, words, w, lines, TEXT.gamma_multiply(0.85)));
    ui.painter().galley(pos2(x, line.min.y + 27.0), g, MUTED);
    response
}

/// L'extrait mis en page : `lines` lignes au plus, les mots cherchés surlignés d'or.
fn excerpt(text: &str, words: &[String], width: f32, lines: usize, ink: egui::Color32) -> LayoutJob {
    let mut job = LayoutJob {
        wrap: TextWrapping {
            max_width: width.max(10.0),
            max_rows: lines,
            break_anywhere: false,
            overflow_character: Some('…'),
        },
        ..Default::default()
    };
    let normal = TextFormat::simple(regular(12.0), ink);
    let strong = TextFormat { font_id: semibold(12.0), color: BG, background: ACCENT, ..Default::default() };
    let bytes: Vec<usize> = text.char_indices().map(|(b, _)| b).chain(std::iter::once(text.len())).collect();
    let mut at = 0;
    for (a, b) in occurrences(text, words) {
        let (ba, bb) = (bytes[a], bytes[b]);
        if ba > at {
            job.append(&text[at..ba], 0.0, normal.clone());
        }
        job.append(&text[ba..bb], 0.0, strong.clone());
        at = bb;
    }
    if at < text.len() {
        job.append(&text[at..], 0.0, normal);
    }
    job
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn filters_switch_sources() {
        let mut f = Filters::default();
        assert!(f.keeps(Source::Bible) && f.any());
        for s in Source::ALL {
            f.set(s, false);
        }
        assert!(!f.any());
        f.set(Source::Books, true);
        assert!(f.any() && !f.keeps(Source::Bible));
    }
}
