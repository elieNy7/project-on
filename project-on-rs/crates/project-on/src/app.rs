//! L'application : le rail, la bibliothèque, l'Aperçu et le Direct, la projection, la recherche
//! globale et les raccourcis. Une seule structure, `App`, dessinée par eframe (la vraie fenêtre) ou
//! par egui_kittest (les essais, sans fenêtre).

use std::collections::HashMap;
use std::path::PathBuf;
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use egui::{
    Align, Align2, Color32, CornerRadius, Key, Layout, Margin, RichText, ScrollArea, Sense, Stroke, Ui, pos2, vec2,
};
use po_db::{Database, Mode};
use po_design::{AnimationKind, RoomDesign};
use po_layout::Slide;
use po_layout::transition::blur_radius;
use po_program::Program;
use po_settings::{Settings, SplitSettings};

use crate::data::{CopyReport, Locations};
use crate::icons::{self, Icon};
use crate::library::books::{BOOK_KEYS, BooksView, EXPOSE_KEYS};
use crate::library::{Action, Marks, Origin, Page, Prepared, bible::BibleView, hymns::HymnsView, sermons::SermonsView};
use crate::projector::Projector;
use crate::search::{self, Hit, Kind, Request, Response, SearchThread};
use crate::shortcuts::{self, Action as Key2, Shortcuts};
use crate::stage::{Frame, Stage};
use crate::theme::*;
use crate::widgets::{self, Size, Tone};
use crate::worker::{Job, Target, Worker};

/// Un programme montré (Aperçu ou Direct) et d'où il vient.
#[derive(Debug, Clone)]
pub struct Shown {
    pub program: Program,
    pub origin: Origin,
}

/// Le démarrage : la copie des données de la 2.x au premier lancement.
enum Startup {
    Ready,
    Copying { handle: JoinHandle<Result<CopyReport, String>>, since: Instant },
    Failed(String),
}

/// Ce qu'il faut pour démarrer.
pub struct Config {
    pub fonts_dir: PathBuf,
    pub locations: Option<Locations>,
    /// Une base déjà prête (essais, mesures) : pas de copie.
    pub database: Option<PathBuf>,
    pub settings: Settings,
    /// La projection s'ouvre dans une fenêtre, jamais en plein écran (essais).
    pub windowed_projection: bool,
}

#[derive(Default)]
struct GlobalSearch {
    query: String,
    asked: String,
    hits: Vec<Hit>,
    searching: bool,
    selected: usize,
    open: bool,
    focus: bool,
    anchor_rect: Option<egui::Rect>,
}

pub struct App {
    ctx: egui::Context,
    locations: Option<Locations>,
    startup: Startup,
    db: Option<Database>,
    db_path: Option<PathBuf>,
    pub design: RoomDesign,
    split: SplitSettings,
    display_screen: String,
    pub shortcuts: Shortcuts,
    windowed_projection: bool,
    pub page: Page,
    pub sermons: SermonsView,
    pub bible: BibleView,
    pub hymns: HymnsView,
    pub expose: BooksView,
    pub books: BooksView,
    pub preview: Option<Shown>,
    pub live: Option<Shown>,
    preview_stage: Stage,
    live_stage: Stage,
    worker: Worker,
    next_job: u64,
    pending: HashMap<Target, u64>,
    search: Option<SearchThread>,
    global: GlobalSearch,
    /// Les fenêtres de projection ouvertes (une par écran).
    projectors: Vec<Projector>,
    /// Ce qui vient de passer au direct, à diffuser aux écrans Web.
    pub taken: Option<Slide>,
    pub web_screens: usize,
    help: bool,
    status: String,
    warm_up: Option<JoinHandle<(u64, Duration)>>,
    /// Durée du dernier rendu d'un slide (ms).
    pub last_render_ms: f64,
    /// La liste du programme au direct doit montrer le slide courant.
    follow_live: bool,
}

fn animation_off() -> po_design::Animation {
    po_design::Animation { kind: AnimationKind::None, duration_ms: 0, direction: po_design::Direction::Up }
}

impl App {
    pub fn new(ctx: &egui::Context, config: Config) -> Self {
        crate::theme::install(ctx, &config.fonts_dir);
        icons::load(ctx);
        let settings = &config.settings;
        let wake = ctx.clone();
        let worker = Worker::spawn(config.fonts_dir.clone(), move || wake.request_repaint());
        let mut app = App {
            ctx: ctx.clone(),
            locations: config.locations.clone(),
            startup: Startup::Ready,
            db: None,
            db_path: None,
            design: RoomDesign::from_projection(&settings.projection),
            split: settings.split.clone(),
            display_screen: settings.projection.display_screen.clone(),
            shortcuts: Shortcuts::from_settings(settings.other.get("shortcuts")),
            windowed_projection: config.windowed_projection,
            page: Page::Sermons,
            sermons: SermonsView::default(),
            bible: BibleView::default(),
            hymns: HymnsView::default(),
            expose: BooksView::new(&EXPOSE_KEYS),
            books: BooksView::new(&BOOK_KEYS),
            preview: None,
            live: None,
            preview_stage: Stage::default(),
            live_stage: Stage::default(),
            worker,
            next_job: 0,
            pending: HashMap::new(),
            search: None,
            global: GlobalSearch::default(),
            projectors: Vec::new(),
            taken: None,
            web_screens: 0,
            help: false,
            status: "Prêt".into(),
            warm_up: None,
            last_render_ms: 0.0,
            follow_live: false,
        };
        match (config.database, config.locations) {
            (Some(path), _) => app.open_database(path),
            (None, Some(locations)) => {
                if crate::data::needs_copy(&locations.beta) {
                    if let Some(legacy) = locations.legacy.clone() {
                        let beta = locations.beta.clone();
                        let handle = std::thread::spawn(move || crate::data::copy_from_legacy(&legacy, &beta));
                        app.startup = Startup::Copying { handle, since: Instant::now() };
                    } else {
                        app.startup = Startup::Failed(
                            "Aucune donnée de Project-On 2.x sur ce poste : installez et lancez d'abord la 2.8.".into(),
                        );
                    }
                } else {
                    app.open_database(locations.beta.database());
                }
            }
            (None, None) => app.startup = Startup::Failed("Dossier des données introuvable.".into()),
        }
        app
    }

    /// Les réglages de la copie de la bêta (lus après la copie).
    fn reload_settings(&mut self) {
        let Some(locations) = &self.locations else { return };
        let loaded = Settings::load(&locations.beta.settings()).settings;
        self.design = RoomDesign::from_projection(&loaded.projection);
        self.split = loaded.split.clone();
        self.display_screen = loaded.projection.display_screen.clone();
        self.shortcuts = Shortcuts::from_settings(loaded.other.get("shortcuts"));
    }

    fn open_database(&mut self, path: PathBuf) {
        match Database::open(&path, Mode::ReadOnly) {
            Ok(db) => {
                self.bible.ensure_loaded(&db);
                self.db = Some(db);
                let wake = self.ctx.clone();
                self.search = Some(SearchThread::spawn(path.clone(), move || wake.request_repaint()));
                self.warm_up = Some(crate::data::warm_up(path.clone()));
                self.db_path = Some(path);
                self.startup = Startup::Ready;
            }
            Err(e) => self.startup = Startup::Failed(format!("Base illisible : {e}")),
        }
    }

    pub fn database(&self) -> Option<&Database> {
        self.db.as_ref()
    }

    // ── Programmes ──────────────────────────────────────────────────────────────────────────────

    /// La taille de rendu : celle du plus grand écran de projection ouvert, sinon 1920 × 1080.
    fn render_size(&self) -> (u32, u32) {
        self.projectors.iter().map(Projector::render_size).max_by_key(|(w, h)| w * h).unwrap_or((1920, 1080))
    }

    fn render(&mut self, target: Target) {
        let shown = match target {
            Target::Preview => self.preview.as_ref(),
            Target::Live => self.live.as_ref(),
        };
        let Some(shown) = shown else { return };
        let slide = shown.program.slide();
        let (width, height) = self.render_size();
        self.next_job += 1;
        let id = self.next_job;
        self.pending.insert(target, id);
        let blur = (target == Target::Live && self.design.animation.kind == AnimationKind::Blur)
            .then(|| blur_radius(&self.design.animation));
        if target == Target::Live {
            self.taken = Some(slide.clone());
            self.follow_live = true;
        }
        self.worker.submit(Job { target, id, slide, design: self.design.clone(), width, height, blur });
    }

    /// Prépare un programme dans l'Aperçu.
    pub fn cue(&mut self, prepared: Prepared) {
        match Program::from_cue(&prepared.cue, &self.split) {
            Some(program) => {
                self.preview = Some(Shown { program, origin: prepared.origin });
                self.render(Target::Preview);
            }
            None => self.status = "Rien à projeter : texte vide.".into(),
        }
    }

    /// Envoie l'Aperçu au direct (F2).
    pub fn take(&mut self) {
        if let Some(preview) = self.preview.clone() {
            self.live = Some(preview);
            self.render(Target::Live);
            self.status = "Au direct".into();
        }
    }

    /// Slide suivant (`+1`) ou précédent (`-1`) au direct.
    pub fn step(&mut self, delta: i32) {
        let Some(live) = self.live.as_mut() else { return };
        let moved = if delta > 0 { live.program.next_slide() } else { live.program.prev_slide() };
        if moved {
            self.render(Target::Live);
        }
    }

    pub fn jump(&mut self, row: usize) {
        if let Some(live) = self.live.as_mut()
            && live.program.set(row)
        {
            self.render(Target::Live);
        }
    }

    fn edge(&mut self, to_start: bool) {
        if let Some(live) = self.live.as_mut()
            && live.program.edge(to_start)
        {
            self.render(Target::Live);
        }
    }

    pub fn toggle_hidden(&mut self) {
        let now = self.ctx.input(|i| i.time);
        let hidden = !self.live_stage.hidden();
        self.live_stage.set_hidden(hidden, now);
        self.status = if hidden { "Texte masqué".into() } else { "Texte affiché".into() };
    }

    pub fn hidden(&self) -> bool {
        self.live_stage.hidden()
    }

    /// F5 : ouvre la projection sur l'écran des réglages, ou ferme toutes les projections.
    pub fn toggle_projection(&mut self) {
        if self.projectors.is_empty() {
            let projector =
                if self.windowed_projection { Projector::windowed() } else { Projector::open(&self.display_screen) };
            self.open_projector(projector);
        } else {
            self.projectors.clear();
            self.status = "Projection fermée".into();
            self.render(Target::Live);
            self.render(Target::Preview);
        }
    }

    /// Ouvre (ou ferme, s'il projette déjà) une projection sur un écran précis.
    pub fn toggle_projector(&mut self, projector: Projector) {
        if let Some(i) = self.projectors.iter().position(|p| *p == projector) {
            self.projectors.remove(i);
            self.status = format!("Projection fermée : {}", projector.label());
            self.render(Target::Live);
            self.render(Target::Preview);
        } else {
            self.open_projector(projector);
        }
    }

    fn open_projector(&mut self, projector: Projector) {
        self.status = format!("Projection : {}", projector.label());
        self.projectors.push(projector);
        // La taille de rendu suit l'écran de projection.
        self.render(Target::Live);
        self.render(Target::Preview);
    }

    pub fn projecting(&self) -> bool {
        !self.projectors.is_empty()
    }

    /// Les écrans qui projettent, et la taille de rendu qui en découle.
    pub fn projection(&self) -> (usize, (u32, u32)) {
        (self.projectors.len(), self.render_size())
    }

    /// Le menu des écrans (clic droit sur « Projection ») : un écran coché projette.
    fn screens_menu(&mut self, response: &egui::Response) {
        response.context_menu(|ui| {
            ui.set_min_width(260.0);
            ui.label(RichText::new("PROJETER SUR").font(semibold(10.5)).color(FAINT));
            for screen in crate::screens::list() {
                let projector = Projector::on(screen.clone());
                let on = self.projectors.contains(&projector);
                if ui.add(egui::Button::selectable(on, &screen.label)).clicked() {
                    self.toggle_projector(projector);
                    ui.close();
                }
            }
            let window = Projector::windowed();
            let on = self.projectors.contains(&window);
            if ui.add(egui::Button::selectable(on, "Dans une fenêtre")).clicked() {
                self.toggle_projector(window);
                ui.close();
            }
            if !self.projectors.is_empty() {
                ui.separator();
                if ui.button("Fermer toutes les projections").clicked() {
                    self.toggle_projection();
                    ui.close();
                }
            }
        });
    }

    /// Le slide montré au direct et celui de l'Aperçu, une fois dessinés.
    pub fn live_frame(&self) -> Option<&Frame> {
        self.live_stage.current()
    }

    pub fn preview_frame(&self) -> Option<&Frame> {
        self.preview_stage.current()
    }

    /// Des rendus attendus (essais).
    pub fn rendering(&self) -> bool {
        !self.pending.is_empty()
    }

    // ── Pour les essais et les mesures (sans souris) ────────────────────────────────────────────

    /// Choisit le sermon de rang `index` dans la liste.
    pub fn select_sermon(&mut self, index: usize) {
        if let Some(db) = &self.db {
            self.page = Page::Sermons;
            self.sermons.select(db, index);
        }
    }

    /// Prépare dans l'Aperçu le sermon choisi, à partir de son entrée `index`.
    pub fn cue_sermon_entry(&mut self, index: usize) {
        if let Some(p) = self.sermons.prepare(index) {
            self.cue(p);
        }
    }

    /// Lance la recherche globale (comme si l'opérateur tapait `query` après Ctrl+K).
    pub fn search_everywhere(&mut self, query: &str) {
        self.global.query = query.to_string();
        self.global.open = true;
    }

    /// Les résultats de la recherche globale, et si elle tourne encore.
    pub fn global_results_now(&self) -> (&[Hit], bool) {
        (&self.global.hits, self.global.searching)
    }

    /// Ouvre le résultat `index` de la recherche globale.
    pub fn open_global(&mut self, index: usize) {
        if let Some(hit) = self.global.hits.get(index).cloned() {
            self.open_hit(&hit);
        }
    }

    fn apply(&mut self, action: Action) {
        match action {
            Action::Cue(p) => self.cue(p),
            Action::Take(p) => {
                self.cue(p);
                self.take();
            }
        }
    }

    fn marks(&self) -> Marks {
        let mark = |s: &Option<Shown>| s.as_ref().map(|s| (s.origin.clone(), s.program.current_entry()));
        Marks { preview: mark(&self.preview), live: mark(&self.live) }
    }

    // ── Fils de rendu et de recherche ───────────────────────────────────────────────────────────

    fn poll(&mut self, now: f64) {
        if let Startup::Copying { handle, .. } = &self.startup
            && handle.is_finished()
            && let Startup::Copying { handle, .. } = std::mem::replace(&mut self.startup, Startup::Ready)
        {
            match handle.join() {
                Ok(Ok(report)) => {
                    po_core::journal::line(&format!(
                        "bêta : copie de la 2.x ({} Mo) en {:.1} s",
                        report.database_bytes / 1_000_000,
                        report.elapsed.as_secs_f64()
                    ));
                    self.reload_settings();
                    if let Some(l) = &self.locations {
                        let path = l.beta.database();
                        self.open_database(path);
                    }
                    self.status = "Données de la 2.8 copiées".into();
                }
                Ok(Err(e)) => self.startup = Startup::Failed(e),
                Err(_) => self.startup = Startup::Failed("la copie s'est arrêtée".into()),
            }
        }
        if let Some(handle) = self.warm_up.take_if(|h| h.is_finished())
            && let Ok((bytes, elapsed)) = handle.join()
        {
            po_core::journal::line(&format!(
                "base lue en arrière-plan : {} Mo en {:.1} s",
                bytes / 1_000_000,
                elapsed.as_secs_f64()
            ));
        }
        for done in self.worker.finished() {
            if self.pending.get(&done.target) != Some(&done.id) {
                continue;
            }
            self.pending.remove(&done.target);
            self.last_render_ms = done.ms;
            let target = done.target;
            let slide = match target {
                Target::Live => self.live.as_ref(),
                Target::Preview => self.preview.as_ref(),
            }
            .map(|s| s.program.slide())
            .unwrap_or_else(|| Slide::new("", "", po_design::SlideSource::Custom));
            let name = if target == Target::Live { "direct" } else { "apercu" };
            let frame = Frame::upload(&self.ctx, name, slide, done);
            match target {
                Target::Live => self.live_stage.show(frame, self.design.animation, now),
                Target::Preview => self.preview_stage.show(frame, animation_off(), now),
            }
        }
        let answers = self.search.as_ref().map(SearchThread::answers).unwrap_or_default();
        for answer in answers {
            match answer {
                Response::Global { query, hits } => {
                    if query == self.global.asked {
                        self.global.hits = hits;
                        self.global.searching = false;
                        self.global.selected = 0;
                    }
                }
                Response::Paragraphs { query, hits } => self.sermons.receive(query, hits),
                Response::Verses { query, hits } => self.bible.receive(query, hits),
                Response::Stanzas { query, hits } => self.hymns.receive(query, hits),
                Response::Book { query, key, hits } => {
                    if self.expose.handles(&key) {
                        self.expose.receive(query, key, hits);
                    } else {
                        self.books.receive(query, key, hits);
                    }
                }
            }
        }
        self.live_stage.tick(now);
        self.preview_stage.tick(now);
    }

    // ── Clavier ─────────────────────────────────────────────────────────────────────────────────

    fn keyboard(&mut self) {
        for action in self.shortcuts.pressed(&self.ctx) {
            match action {
                Key2::Take => self.take(),
                Key2::NextSlide => self.step(1),
                Key2::PrevSlide => self.step(-1),
                Key2::Hide => self.toggle_hidden(),
                Key2::Projection => self.toggle_projection(),
                Key2::GlobalSearch => self.global.focus = true,
                Key2::Search => self.focus_page_search(),
                Key2::ParagraphSearch => {
                    self.page = Page::Sermons;
                    self.sermons.search_mode = true;
                    self.sermons.focus_search = true;
                }
                Key2::Help => self.help = !self.help,
            }
        }
        let typing = self.ctx.egui_wants_keyboard_input();
        // Ctrl+1 … Ctrl+5 : les pages du rail.
        let pages = [Key::Num1, Key::Num2, Key::Num3, Key::Num4, Key::Num5];
        for (key, page) in pages.into_iter().zip(Page::ALL) {
            if self.ctx.input_mut(|i| i.consume_key(egui::Modifiers::COMMAND, key)) {
                self.page = page;
            }
        }
        if typing {
            return;
        }
        // Les flèches, Début et Fin pilotent le direct (comme une télécommande de présentation).
        let ctx = self.ctx.clone();
        let pressed = |k: Key| ctx.input_mut(|i| i.consume_key(egui::Modifiers::NONE, k));
        if pressed(Key::ArrowRight) || pressed(Key::ArrowDown) {
            self.step(1);
        }
        if pressed(Key::ArrowLeft) || pressed(Key::ArrowUp) {
            self.step(-1);
        }
        if pressed(Key::Home) {
            self.edge(true);
        }
        if pressed(Key::End) {
            self.edge(false);
        }
    }

    fn focus_page_search(&mut self) {
        match self.page {
            Page::Bible => self.bible.focus_search = true,
            Page::Hymns => self.hymns.focus_search = true,
            Page::Sermons => self.sermons.focus_search = true,
            Page::Expose => self.expose.focus_search = true,
            Page::Books => self.books.focus_search = true,
        }
    }

    // ── Interface ───────────────────────────────────────────────────────────────────────────────

    pub fn ui(&mut self, ui: &mut Ui) {
        let now = ui.input(|i| i.time);
        self.poll(now);
        match &self.startup {
            Startup::Copying { since, .. } => {
                let seconds = since.elapsed().as_secs();
                waiting(
                    ui,
                    "Préparation de la bêta",
                    &format!(
                        "Copie de vos données de Project-On 2.8 (une seule fois)… {seconds} s\nLa 2.8 et ses données ne sont pas modifiées."
                    ),
                );
                ui.ctx().request_repaint_after(Duration::from_millis(250));
                return;
            }
            Startup::Failed(message) => {
                waiting(ui, "Project-On 3 ne peut pas démarrer", message);
                return;
            }
            Startup::Ready => {}
        }
        self.keyboard();
        egui::Panel::top("barre").exact_size(50.0).frame(bar_frame()).show(ui, |ui| self.command_bar(ui));
        egui::Panel::bottom("etat").exact_size(26.0).frame(bar_frame()).show(ui, |ui| self.status_bar(ui));
        egui::Panel::left("rail").exact_size(176.0).resizable(false).frame(bar_frame()).show(ui, |ui| self.rail(ui));
        egui::Panel::right("moniteurs")
            .exact_size(480.0)
            .resizable(false)
            .frame(panel_frame())
            .show(ui, |ui| self.monitors(ui, now));
        egui::CentralPanel::no_frame().frame(panel_frame().fill(BG)).show(ui, |ui| self.library(ui));
        self.global_results(ui);
        if self.help {
            self.help_window(ui);
        }
        let before = self.projectors.len();
        let (ctx, stage) = (self.ctx.clone(), &self.live_stage);
        self.projectors.retain_mut(|p| p.show(&ctx, stage, now));
        if self.projectors.len() < before {
            self.status = "Projection fermée".into();
        }
        if self.live_stage.animating(now) || self.preview_stage.animating(now) {
            ui.ctx().request_repaint();
        }
        // L'horloge de la barre.
        ui.ctx().request_repaint_after(Duration::from_secs(1));
    }

    fn library(&mut self, ui: &mut Ui) {
        let Some(db) = self.db.as_ref() else { return };
        let marks = self.marks();
        let search = self.search.as_ref();
        let action = match self.page {
            Page::Sermons => self.sermons.ui(ui, db, &marks, search),
            Page::Bible => self.bible.ui(ui, db, &marks, search),
            Page::Hymns => self.hymns.ui(ui, db, &marks, search, self.split.hymn_repeat_chorus),
            Page::Expose => self.expose.ui(ui, db, &marks, search),
            Page::Books => self.books.ui(ui, db, &marks, search),
        };
        if let Some(action) = action {
            self.apply(action);
        }
    }

    fn command_bar(&mut self, ui: &mut Ui) {
        ui.horizontal_centered(|ui| {
            ui.label(RichText::new("Project-On").font(bold(17.0)).color(TEXT));
            widgets::chip(ui, "3.0 bêta", ACCENT);
            ui.add_space(24.0);
            let r = widgets::search_field(ui, &mut self.global.query, "Rechercher partout…  Ctrl+K", 440.0);
            if std::mem::take(&mut self.global.focus) {
                r.request_focus();
            }
            if r.has_focus() || r.changed() {
                self.global.open = !self.global.query.trim().is_empty();
            }
            let q = self.global.query.trim().to_string();
            if q != self.global.asked {
                self.global.asked = q.clone();
                self.global.hits.clear();
                self.global.searching = false;
                if q.chars().count() >= search::MIN_QUERY
                    && let Some(s) = &self.search
                {
                    s.ask(Request::Global { query: q, translation: self.bible.translation });
                    self.global.searching = true;
                }
            }
            if r.has_focus() {
                let (down, up, enter, escape) = ui.input(|i| {
                    (
                        i.key_pressed(Key::ArrowDown),
                        i.key_pressed(Key::ArrowUp),
                        i.key_pressed(Key::Enter),
                        i.key_pressed(Key::Escape),
                    )
                });
                if down {
                    self.global.selected = (self.global.selected + 1).min(self.global.hits.len().saturating_sub(1));
                }
                if up {
                    self.global.selected = self.global.selected.saturating_sub(1);
                }
                if escape {
                    self.global.open = false;
                    r.surrender_focus();
                }
                if enter && let Some(hit) = self.global.hits.get(self.global.selected).cloned() {
                    self.open_hit(&hit);
                }
            } else if r.lost_focus()
                && ui.input(|i| i.key_pressed(Key::Enter))
                && let Some(hit) = self.global.hits.get(self.global.selected).cloned()
            {
                // Entrée fait perdre le clavier au champ : le résultat choisi s'ouvre quand même.
                self.open_hit(&hit);
            }
            self.global.anchor(r.rect);
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                let clock = chrono_now();
                ui.label(RichText::new(clock).font(medium(12.5)).color(MUTED));
                ui.add_space(8.0);
                widgets::chip(
                    ui,
                    &format!("Web · {}", self.web_screens),
                    if self.web_screens > 0 { PREVIEW } else { FAINT },
                );
                ui.add_space(4.0);
                let label = match self.projectors.as_slice() {
                    [] => "Projection fermée".to_string(),
                    [p] => format!("Projection · {}", p.label()),
                    many => format!("Projection · {} écrans", many.len()),
                };
                let tip = format!(
                    "Ouvrir ou fermer la projection ({}) ; clic droit : choisir les écrans",
                    self.shortcuts.text(Key2::Projection)
                );
                let tone = if self.projecting() { Tone::Primary(LIVE) } else { Tone::Secondary };
                let r = widgets::button(ui, Some(Icon::Cast), &label, tone).on_hover_text(tip);
                if r.clicked() {
                    self.toggle_projection();
                }
                self.screens_menu(&r);
            });
        });
    }

    fn open_hit(&mut self, hit: &Hit) {
        let Some(db) = self.db.as_ref() else { return };
        let prepared = match &hit.target {
            search::Target::Verse { translation, book, chapter, verse } => {
                self.page = Page::Bible;
                self.bible.open(db, *translation, *book, *chapter, *verse)
            }
            search::Target::Sermon { sermon_id, reference } => {
                self.page = Page::Sermons;
                self.sermons.search_mode = false;
                self.sermons.open(db, *sermon_id, reference.as_deref())
            }
            search::Target::Book { chapter_id, raw_ref } => {
                let key = db.book_of_chapter(*chapter_id).ok().flatten().map(|b| b.key).unwrap_or_default();
                if self.books.handles(&key) {
                    self.page = Page::Books;
                    self.books.open(db, *chapter_id, raw_ref.as_deref())
                } else {
                    self.page = Page::Expose;
                    self.expose.open(db, *chapter_id, raw_ref.as_deref())
                }
            }
        };
        self.global.open = false;
        self.global.query.clear();
        self.ctx.memory_mut(|m| m.stop_text_input());
        if let Some(p) = prepared {
            self.cue(p);
        }
    }

    fn global_results(&mut self, ui: &mut Ui) {
        if !self.global.open || self.global.query.trim().is_empty() {
            return;
        }
        let Some(anchor) = self.global.anchor_rect else { return };
        let mut opened = None;
        let area = egui::Area::new(egui::Id::unique("resultats-globaux"))
            .order(egui::Order::Foreground)
            .fixed_pos(pos2(anchor.min.x, anchor.max.y + 4.0))
            .show(ui.ctx(), |ui| {
                egui::Frame::NONE
                    .fill(PANEL)
                    .stroke(Stroke::new(1.0, BORDER_STRONG))
                    .corner_radius(10.0)
                    .inner_margin(Margin::same(8))
                    .shadow(egui::Shadow { offset: [0, 8], blur: 24, spread: 0, color: Color32::from_black_alpha(140) })
                    .show(ui, |ui| {
                        ui.set_width(anchor.width().max(440.0));
                        if self.global.hits.is_empty() {
                            let text = if self.global.searching {
                                "Recherche…"
                            } else if self.global.asked.chars().count() < search::MIN_QUERY {
                                "Au moins deux lettres"
                            } else {
                                "Aucun résultat"
                            };
                            ui.label(RichText::new(text).font(regular(12.5)).color(FAINT));
                            return;
                        }
                        ScrollArea::vertical().max_height(420.0).show(ui, |ui| {
                            let mut kind: Option<Kind> = None;
                            for (i, hit) in self.global.hits.iter().enumerate() {
                                if kind != Some(hit.kind) {
                                    kind = Some(hit.kind);
                                    widgets::section(ui, hit.kind.label());
                                }
                                let selected = i == self.global.selected;
                                let (rect, r) = widgets::list_row(ui, selected, 42.0, &hit.title);
                                widgets::paint_text(
                                    ui,
                                    pos2(rect.min.x + 12.0, rect.min.y + 5.0),
                                    Align2::LEFT_TOP,
                                    &hit.title,
                                    semibold(12.5),
                                    TEXT,
                                    rect.width() - 20.0,
                                );
                                widgets::paint_text(
                                    ui,
                                    pos2(rect.min.x + 12.0, rect.min.y + 23.0),
                                    Align2::LEFT_TOP,
                                    &hit.subtitle,
                                    regular(11.5),
                                    MUTED,
                                    rect.width() - 20.0,
                                );
                                if r.clicked() {
                                    opened = Some(hit.clone());
                                }
                            }
                        });
                    });
            });
        if let Some(hit) = opened {
            self.open_hit(&hit);
        } else if ui.input(|i| i.pointer.any_click()) && !area.response.hovered() && !self.global.anchor_hovered(ui) {
            self.global.open = false;
        }
    }

    fn rail(&mut self, ui: &mut Ui) {
        ui.add_space(10.0);
        for (i, page) in Page::ALL.into_iter().enumerate() {
            let selected = self.page == page;
            let (rect, r) = widgets::list_row(ui, selected, 38.0, page.label());
            ui.add_space(2.0);
            icons::paint(
                ui.painter(),
                egui::Rect::from_center_size(pos2(rect.min.x + 22.0, rect.center().y), vec2(17.0, 17.0)),
                page.icon(),
                if selected { ACCENT } else { MUTED },
            );
            widgets::paint_text(
                ui,
                pos2(rect.min.x + 40.0, rect.center().y),
                Align2::LEFT_CENTER,
                page.label(),
                medium(13.5),
                if selected { TEXT } else { MUTED },
                rect.width() - 50.0,
            );
            if r.on_hover_text(format!("Ctrl+{}", i + 1)).clicked() {
                self.page = page;
            }
        }
        ui.add_space(10.0);
        ui.separator();
        for (label, icon, phase) in [
            ("Playlist", Icon::ListVideo, "phase 4"),
            ("Médias", Icon::Image, "phase 7"),
            ("Designs", Icon::SwatchBook, "phase 6"),
            ("Réglages", Icon::Settings, "phase 7"),
        ] {
            let (rect, r) = ui.allocate_exact_size(vec2(ui.available_width(), 36.0), Sense::hover());
            icons::paint(
                ui.painter(),
                egui::Rect::from_center_size(pos2(rect.min.x + 22.0, rect.center().y), vec2(17.0, 17.0)),
                icon,
                FAINT.gamma_multiply(0.6),
            );
            widgets::paint_text(
                ui,
                pos2(rect.min.x + 40.0, rect.center().y),
                Align2::LEFT_CENTER,
                label,
                medium(13.0),
                FAINT.gamma_multiply(0.7),
                rect.width() - 50.0,
            );
            r.on_hover_text(format!("Arrive en {phase} ; la 2.8 reste disponible pour cela."));
        }
        ui.with_layout(Layout::bottom_up(Align::Min), |ui| {
            ui.add_space(6.0);
            if widgets::button(ui, Some(Icon::Info), "Raccourcis  F1", Tone::Secondary).clicked() {
                self.help = !self.help;
            }
        });
    }

    fn monitors(&mut self, ui: &mut Ui, now: f64) {
        let width = ui.available_width();
        let height = width * 9.0 / 16.0;
        // Aperçu.
        monitor_header(ui, "APERÇU", PREVIEW, self.preview.as_ref());
        let (rect, _) = ui.allocate_exact_size(vec2(width, height), Sense::hover());
        self.preview_stage.paint(ui.painter(), rect, now);
        ui.painter().rect_stroke(
            rect,
            CornerRadius::same(4),
            Stroke::new(2.0, PREVIEW.gamma_multiply(0.7)),
            egui::StrokeKind::Outside,
        );
        if self.preview.is_none() {
            ui.painter().text(
                rect.center(),
                Align2::CENTER_CENTER,
                "Cliquez un verset, une strophe ou un paragraphe",
                regular(12.0),
                FAINT,
            );
        }
        ui.add_space(8.0);
        let take = format!("Envoyer au direct   {}", self.shortcuts.text(Key2::Take));
        if widgets::button_sized(
            ui,
            width,
            Size::Hero,
            Some(Icon::Cast),
            &take,
            Tone::Primary(LIVE),
            self.preview.is_some(),
        )
        .clicked()
        {
            self.take();
        }
        ui.add_space(14.0);
        // Direct.
        monitor_header(ui, "DIRECT", LIVE, self.live.as_ref());
        let (rect, _) = ui.allocate_exact_size(vec2(width, height), Sense::hover());
        self.live_stage.paint(ui.painter(), rect, now);
        ui.painter().rect_stroke(
            rect,
            CornerRadius::same(4),
            Stroke::new(2.0, LIVE.gamma_multiply(0.8)),
            egui::StrokeKind::Outside,
        );
        if self.live_stage.hidden() {
            ui.painter().text(
                rect.left_top() + vec2(10.0, 10.0),
                Align2::LEFT_TOP,
                "TEXTE MASQUÉ",
                semibold(11.0),
                WARN,
            );
        }
        ui.add_space(8.0);
        ui.horizontal(|ui| {
            let live = self.live.is_some();
            if widgets::button_sized(ui, 44.0, Size::Large, Some(Icon::ChevronLeft), "", Tone::Secondary, live)
                .on_hover_text("Slide précédent (Page précédente, ←)")
                .clicked()
            {
                self.step(-1);
            }
            let hide_label = if self.live_stage.hidden() { "Afficher" } else { "Masquer" };
            let hide = format!("{hide_label}  {}", self.shortcuts.text(Key2::Hide));
            let icon = if self.live_stage.hidden() { Icon::Eye } else { Icon::EyeOff };
            let w = (ui.available_width() - 44.0 - 8.0) / 2.0;
            if widgets::button_sized(ui, w, Size::Large, Some(icon), &hide, Tone::Secondary, true).clicked() {
                self.toggle_hidden();
            }
            let proj = if self.projecting() { "Fermer la projection" } else { "Projection" };
            let proj = format!("{proj}  {}", self.shortcuts.text(Key2::Projection));
            let tone = if self.projecting() { Tone::Primary(LIVE) } else { Tone::Secondary };
            let r = widgets::button_sized(ui, w, Size::Large, Some(Icon::Monitor), &proj, tone, true)
                .on_hover_text("Clic droit : choisir les écrans");
            if r.clicked() {
                self.toggle_projection();
            }
            self.screens_menu(&r);
            if widgets::button_sized(ui, 44.0, Size::Large, Some(Icon::ChevronRight), "", Tone::Secondary, live)
                .on_hover_text("Slide suivant (Page suivante, →)")
                .clicked()
            {
                self.step(1);
            }
        });
        ui.add_space(10.0);
        // Le programme au direct : chaque slide, cliquable.
        let Some(live) = self.live.as_ref() else { return };
        widgets::section(ui, &format!("Programme au direct · {} slides", live.program.len()));
        let current = live.program.current();
        let mut jump = None;
        let rows: Vec<(String, String)> =
            live.program.slides.iter().map(|s| (s.reference.clone(), s.text.replace('\n', " "))).collect();
        let mut area = ScrollArea::vertical().id_salt("programme-direct").auto_shrink([false, false]);
        if std::mem::take(&mut self.follow_live) {
            area = area.vertical_scroll_offset(crate::library::scroll_offset(ui, current, 40.0));
        }
        area.show_rows(ui, 40.0, rows.len(), |ui, range| {
            for i in range {
                let (reference, text) = &rows[i];
                let (rect, r) = widgets::list_row(ui, i == current, 38.0, reference);
                ui.add_space(2.0);
                widgets::paint_text(
                    ui,
                    pos2(rect.min.x + 12.0, rect.min.y + 4.0),
                    Align2::LEFT_TOP,
                    reference,
                    semibold(11.0),
                    if i == current { LIVE } else { ACCENT },
                    rect.width() - 20.0,
                );
                widgets::paint_text(
                    ui,
                    pos2(rect.min.x + 12.0, rect.min.y + 20.0),
                    Align2::LEFT_TOP,
                    text,
                    regular(11.5),
                    MUTED,
                    rect.width() - 20.0,
                );
                if r.clicked() {
                    jump = Some(i);
                }
            }
        });
        if let Some(row) = jump {
            self.jump(row);
        }
    }

    fn status_bar(&mut self, ui: &mut Ui) {
        ui.horizontal_centered(|ui| {
            widgets::dot(ui, if self.live.is_some() { LIVE } else { PREVIEW });
            ui.label(RichText::new(&self.status).font(medium(11.5)).color(MUTED));
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                if let Some(l) = &self.locations {
                    ui.label(
                        RichText::new(format!("Données : {}", l.beta.root().display()))
                            .font(regular(11.0))
                            .color(FAINT),
                    )
                    .on_hover_text("La bêta travaille sur une copie : la 2.8 et ses données ne sont jamais modifiées.");
                }
            });
        });
    }

    fn help_window(&mut self, ui: &mut Ui) {
        let mut open = self.help;
        egui::Window::new("Raccourcis clavier")
            .open(&mut open)
            .collapsible(false)
            .resizable(false)
            .default_width(420.0)
            .show(ui.ctx(), |ui| {
                egui::Grid::new("raccourcis").num_columns(2).spacing([24.0, 6.0]).show(ui, |ui| {
                    for (action, _, label, _) in shortcuts::ACTIONS {
                        ui.label(RichText::new(label).font(regular(12.5)).color(TEXT));
                        let key = self.shortcuts.text(action);
                        ui.label(
                            RichText::new(if key.is_empty() { "—" } else { key }).font(semibold(12.5)).color(ACCENT),
                        );
                        ui.end_row();
                    }
                    for (label, key) in [
                        ("Slide suivant / précédent", "→ ↓ / ← ↑"),
                        ("Premier / dernier slide", "Début / Fin"),
                        ("Pages du rail", "Ctrl+1 … Ctrl+5"),
                        ("Fermer la projection (sur l'écran de projection)", "Échap"),
                    ] {
                        ui.label(RichText::new(label).font(regular(12.5)).color(TEXT));
                        ui.label(RichText::new(key).font(semibold(12.5)).color(MUTED));
                        ui.end_row();
                    }
                });
                widgets::section(ui, "Dans une phase suivante");
                for (label, phase) in shortcuts::LATER {
                    ui.label(RichText::new(format!("{label} — {phase}")).font(regular(11.5)).color(FAINT));
                }
            });
        self.help = open;
    }
}

impl GlobalSearch {
    fn anchor(&mut self, rect: egui::Rect) {
        self.anchor_rect = Some(rect);
    }

    fn anchor_hovered(&self, ui: &Ui) -> bool {
        self.anchor_rect.is_some_and(|r| ui.rect_contains_pointer(r))
    }
}

fn monitor_header(ui: &mut Ui, title: &str, color: Color32, shown: Option<&Shown>) {
    ui.horizontal(|ui| {
        widgets::dot(ui, color);
        ui.label(RichText::new(title).font(semibold(12.0)).color(color).extra_letter_spacing(0.8));
        if let Some(s) = shown {
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                ui.label(
                    RichText::new(format!("{}/{}", s.program.current() + 1, s.program.len()))
                        .font(medium(11.5))
                        .color(MUTED),
                );
                ui.add_space(6.0);
                ui.add(egui::Label::new(RichText::new(&s.program.title).font(regular(11.5)).color(MUTED)).truncate());
            });
        }
    });
    ui.add_space(4.0);
}

fn waiting(ui: &mut Ui, title: &str, message: &str) {
    egui::CentralPanel::default().frame(egui::Frame::NONE.fill(BG)).show(ui, |ui| {
        ui.add_space(ui.available_height() / 3.0);
        ui.vertical_centered(|ui| {
            ui.label(RichText::new(title).font(semibold(20.0)).color(TEXT));
            ui.add_space(10.0);
            ui.label(RichText::new(message).font(regular(13.5)).color(MUTED));
        });
    });
}

fn bar_frame() -> egui::Frame {
    egui::Frame::new().fill(PANEL).inner_margin(Margin::symmetric(12, 6))
}

fn panel_frame() -> egui::Frame {
    egui::Frame::new().fill(PANEL).inner_margin(Margin::same(12))
}

/// L'heure locale « 16:51 ».
fn chrono_now() -> String {
    #[cfg(windows)]
    {
        use windows::Win32::System::SystemInformation::GetLocalTime;
        // SAFETY : GetLocalTime remplit une structure qu'on lui donne, sans autre effet.
        #[allow(unsafe_code)]
        let t = unsafe { GetLocalTime() };
        format!("{:02}:{:02}", t.wHour, t.wMinute)
    }
    #[cfg(not(windows))]
    {
        String::new()
    }
}

/// L'application créée à sa première image (egui_kittest construit l'état avant le contexte).
pub struct Boot {
    config: Option<Config>,
    app: Option<App>,
}

impl Boot {
    pub fn new(config: Config) -> Self {
        Boot { config: Some(config), app: None }
    }

    pub fn ui(&mut self, ui: &mut Ui) {
        if self.app.is_none()
            && let Some(config) = self.config.take()
        {
            self.app = Some(App::new(ui.ctx(), config));
        }
        if let Some(app) = self.app.as_mut() {
            app.ui(ui);
        }
    }

    /// L'application (après la première image).
    pub fn app(&mut self) -> &mut App {
        self.app.as_mut().unwrap_or_else(|| panic!("Boot::app avant la première image"))
    }

    pub fn get(&self) -> Option<&App> {
        self.app.as_ref()
    }
}
