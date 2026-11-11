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
use po_design::library::{Design, DesignBody};
use po_design::{AnimationKind, RoomDesign};
use po_layout::Slide;
use po_layout::transition::blur_radius;
use po_program::Program;
use po_settings::{Settings, SplitSettings};

use crate::data::{CopyReport, Locations};
use crate::designs::{DesignAction, DesignsView};
use crate::icons::{self, Icon};
use crate::library::books::{BOOK_KEYS, BooksView, EXPOSE_KEYS};
use crate::library::playlist::{PlaylistAction, PlaylistMarks, PlaylistView};
use crate::library::{Action, Marks, Origin, Page, Prepared, bible::BibleView, hymns::HymnsView, sermons::SermonsView};
use crate::outputs::{Outputs, Wanted};
use crate::overlay::{LowerThird, Subtitles};
use crate::playlist::Playlists;
use crate::projector::Projector;
use crate::search::{self, Hit, Kind, Request, Response, SearchThread};
use crate::service::{self, Tracker};
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
    /// Pour une playlist : l'élément d'origine de chaque entrée du programme.
    pub items: Vec<i64>,
}

impl Shown {
    /// L'élément de playlist du slide montré.
    pub fn item(&self) -> Option<i64> {
        self.items.get(self.program.current_entry()).copied()
    }
}

/// « Ajouter à la playlist » : les entrées proposées et la playlist choisie.
struct AddDialog {
    entries: Vec<po_program::Entry>,
    source: &'static str,
    /// Pour « une plage… » : le premier et le dernier rang ajoutés.
    range: Option<(usize, usize)>,
    folder: Option<i64>,
    new_name: String,
}

/// Le démarrage : la copie des données au premier lancement.
enum Startup {
    Ready,
    /// Les données de la 2.x et la base fournie sont là : l'opérateur choisit.
    Choose,
    Copying {
        handle: JoinHandle<Result<CopyReport, String>>,
        since: Instant,
    },
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
    /// Le port du serveur Web (0 : un port libre) ; `None` : pas d'écrans Web (essais).
    pub web_port: Option<u16>,
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
    pub playlist: PlaylistView,
    pub playlists: Playlists,
    /// Le déroulé du culte et la playlist qu'il suit.
    pub tracker: Tracker,
    tracker_folder: Option<i64>,
    add: Option<AddDialog>,
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
    /// Les écrans Web (salle, diffusion, sous-titres, retour de scène).
    pub web: Option<crate::web::Web>,
    /// Ce qui est au direct, tel que le voit chaque genre d'écran (Web, NDI, HDMI).
    pub hub: std::sync::Arc<po_web::Hub>,
    pub outputs: Outputs,
    pub lower_third: LowerThird,
    pub subtitles: Subtitles,
    /// On recule : le slide précédent montre son dernier sous-titre.
    subtitles_backwards: bool,
    pub designs: DesignsView,
    /// Un design de salle essayé dans l'Aperçu (bibliothèque de designs).
    pub preview_design: Option<RoomDesign>,
    /// La source NDI « Project-On Diffusion ».
    pub ndi: bool,
    /// La mire sur les sorties HDMI (F8).
    pub hdmi_pattern: bool,
    hdmi_key: po_design::Rgba,
    /// Les réglages en vigueur (ceux de la bêta).
    pub settings: Settings,
    pub settings_view: crate::settings_page::SettingsView,
    /// Le direct laissé par un arrêt brutal, proposé à la reprise.
    pub recovery: Option<crate::recovery::Snapshot>,
    /// Les fenêtres du contrôle avant culte et de l'historique.
    pub preflight_open: bool,
    pub history_open: bool,
    /// Le diaporama, le direct qu'il a remplacé (rendu à l'arrêt) et la page Médias.
    pub slideshow: crate::media::Slideshow,
    slideshow_before: Option<(Option<Shown>, bool)>,
    pub media_view: crate::media::MediaView,
    /// La vidéo au direct, et ses réglages de lecture.
    pub video: Option<crate::video::LiveVideo>,
    /// Sans son (essais).
    pub video_muted: bool,
    video_looping: bool,
    video_volume: f32,
    /// La vidéo qui n'a pas pu être lue (pour ne pas réessayer à chaque image).
    video_failed: Option<String>,
    /// Le design des sorties Web, NDI et HDMI (au départ, le bandeau « OBS » de la 2.x).
    pub output: crate::designs::Output,
    help: bool,
    status: String,
    warm_up: Option<JoinHandle<(u64, Duration)>>,
    /// Durée du dernier rendu d'un slide (ms).
    pub last_render_ms: f64,
    /// La liste du programme au direct doit montrer le slide courant.
    follow_live: bool,
    /// L'image de citation (Ctrl+Shift+I).
    pub quote: crate::quote::QuoteWindow,
    /// La préparation d'une restauration (vérification dans un fil à part).
    restore_job: Option<JoinHandle<Result<String, String>>>,
}

/// Le bandeau des écrans Web : les réglages « OBS » de la 2.x (`obs.output`), sinon ceux par défaut.
fn band_of(settings: &Settings) -> po_design::Band {
    settings
        .other
        .get("obs")
        .and_then(|o| o.get("output"))
        .map_or_else(po_design::Band::default, po_design::Band::from_obs_output)
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
        let hub = po_web::Hub::new(crate::worker::fonts_from(&config.fonts_dir));
        let wake_outputs = ctx.clone();
        let outputs = Outputs::start(hub.clone(), move || wake_outputs.request_repaint());
        let band_2x = band_of(settings);
        let designs_dir = config.locations.as_ref().map(|l| l.beta.data().join("designs"));
        let mut designs = DesignsView::new(
            config.fonts_dir.clone(),
            designs_dir,
            &RoomDesign::from_projection(&settings.projection),
            &band_2x,
        );
        designs.families = crate::worker::fonts_from(&config.fonts_dir).families();
        let lower_third = po_design::graphics::builtin_lower_thirds()
            .into_iter()
            .find(|(id, ..)| *id == "lt-moderne")
            .map(|(id, name, _, style)| LowerThird::new(id, name, style))
            .unwrap_or_else(|| {
                LowerThird::new("lt", "Lower third", po_design::graphics::builtin_lower_thirds().remove(0).3)
            });
        let subtitles = po_design::graphics::builtin_subtitles()
            .into_iter()
            .nth(1)
            .map(|(id, name, style)| Subtitles::new(id, name, style))
            .unwrap_or_else(|| {
                Subtitles::new(
                    "st",
                    "Sous-titres",
                    po_design::graphics::SubtitleStyle::new(po_design::graphics::SubtitleLook::Translucent),
                )
            });
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
            playlist: PlaylistView::default(),
            playlists: Playlists::default(),
            tracker: Tracker::default(),
            tracker_folder: None,
            add: None,
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
            web: None,
            hub,
            outputs,
            lower_third,
            subtitles,
            subtitles_backwards: false,
            designs,
            preview_design: None,
            ndi: false,
            hdmi_pattern: false,
            hdmi_key: po_layout::graphics::key_color(&settings.hdmi.key_color),
            settings: settings.clone(),
            settings_view: crate::settings_page::SettingsView::default(),
            recovery: None,
            preflight_open: false,
            history_open: false,
            slideshow: crate::media::Slideshow::default(),
            slideshow_before: None,
            video: None,
            video_muted: false,
            video_looping: false,
            video_volume: 1.0,
            video_failed: None,
            media_view: crate::media::MediaView::new(settings.projection.media_default_duration.clamp(0, 600) as u32),
            output: crate::designs::Output {
                id: "bandeau-2x".into(),
                name: "Mon bandeau 2.x".into(),
                look: po_web::Look::Band(band_2x),
            },
            help: false,
            status: "Prêt".into(),
            warm_up: None,
            last_render_ms: 0.0,
            follow_live: false,
            restore_job: None,
            quote: crate::quote::QuoteWindow::default(),
        };
        app.apply_settings(config.settings.clone());
        app.restore_choices();
        if let Some(port) = config.web_port {
            let file = config.locations.as_ref().map(|l| l.beta.data().join("web.json"));
            app.web = Some(crate::web::Web::start(app.hub.clone(), port, file));
        }
        match (config.database, config.locations) {
            (Some(path), _) => app.open_database(path),
            (None, Some(locations)) => {
                if crate::data::needs_copy(&locations.beta) {
                    match locations.origins().as_slice() {
                        [] => {
                            app.startup = Startup::Failed(
                                "Aucune base à copier : ni données de Project-On 2.x sur ce poste, ni base fournie avec l'installateur.".into(),
                            );
                        }
                        [only] => app.start_copy(*only),
                        _ => app.startup = Startup::Choose,
                    }
                } else {
                    app.open_database(locations.beta.database());
                }
            }
            (None, None) => app.startup = Startup::Failed("Dossier des données introuvable.".into()),
        }
        app
    }

    /// Lance la première copie de la base, sur un fil à part.
    pub fn start_copy(&mut self, origin: crate::data::Origin) {
        let Some(locations) = self.locations.clone() else { return };
        po_core::journal::line(&format!("bêta : première copie depuis {origin:?}"));
        let handle = std::thread::spawn(move || locations.copy(origin));
        self.startup = Startup::Copying { handle, since: Instant::now() };
    }

    /// Le premier lancement attend le choix de la base.
    pub fn choosing(&self) -> bool {
        matches!(self.startup, Startup::Choose)
    }

    /// Les réglages de la copie de la bêta (lus après la copie).
    fn reload_settings(&mut self) {
        let Some(locations) = &self.locations else { return };
        let loaded = Settings::load(&locations.beta.settings()).settings;
        self.apply_settings(loaded);
    }

    /// Met en vigueur des réglages : design de la salle, découpage, raccourcis, diffusion.
    pub fn apply_settings(&mut self, loaded: Settings) {
        self.design = RoomDesign::from_projection(&loaded.projection);
        self.design.identification.style = crate::settings_page::identification_style(&loaded);
        if crate::settings_page::low_power(&loaded) {
            self.design.animation.kind = AnimationKind::None;
        }
        self.designs.previews_enabled = !crate::settings_page::low_power(&loaded);
        self.split = loaded.split.clone();
        self.display_screen = loaded.projection.display_screen.clone();
        self.shortcuts = Shortcuts::from_settings(loaded.other.get("shortcuts"));
        self.hdmi_key = po_layout::graphics::key_color(&loaded.hdmi.key_color);
        self.designs.refresh_builtin(&self.design, &band_of(&loaded));
        // Les designs « 2.x » suivent les réglages : celui des sorties aussi.
        if let Some(output) = self.designs.find(&self.output.id).and_then(crate::designs::Output::of) {
            self.output = output;
        }
        self.settings = loaded;
    }

    /// Le fichier des designs choisis (sorties, lower third, sous-titres).
    fn choices_file(&self) -> Option<PathBuf> {
        self.data_dir().map(|d| d.join("designs-choisis.json"))
    }

    /// Reprend les designs choisis au dernier lancement.
    fn restore_choices(&mut self) {
        let Some(file) = self.choices_file() else { return };
        let choices = crate::designs::Choices::load(&file);
        let find = |id: &Option<String>| id.as_deref().and_then(|id| self.designs.find(id)).cloned();
        let (output, lower_third, subtitles) =
            (find(&choices.output), find(&choices.lower_third), find(&choices.subtitles));
        if let Some(output) = output.as_ref().and_then(crate::designs::Output::of) {
            self.output = output;
        }
        if let Some(Design { id, name, body: DesignBody::LowerThird(style), .. }) = lower_third {
            self.lower_third.id = id;
            self.lower_third.name = name;
            self.lower_third.style = style;
        }
        if let Some(Design { id, name, body: DesignBody::Subtitles(style), .. }) = subtitles {
            self.subtitles.id = id;
            self.subtitles.name = name;
            self.subtitles.style = style;
            self.subtitles.cut_for = None;
        }
    }

    fn save_choices(&self) {
        let Some(file) = self.choices_file() else { return };
        let choices = crate::designs::Choices {
            output: Some(self.output.id.clone()),
            lower_third: Some(self.lower_third.id.clone()),
            subtitles: Some(self.subtitles.id.clone()),
        };
        if let Err(e) = choices.save(&file) {
            po_core::journal::line(&format!("designs : choix non enregistré ({e})"));
        }
    }

    /// Le dossier de données de la bêta.
    fn data_dir(&self) -> Option<PathBuf> {
        self.locations.as_ref().map(|l| l.beta.data())
    }

    /// Enregistre les réglages (Réglages → Enregistrer).
    fn save_settings(&mut self, settings: Settings) {
        if let Some(locations) = &self.locations
            && let Err(e) = settings.save(&locations.beta.settings())
        {
            self.status = format!("Réglages non enregistrés : {e}");
            return;
        }
        self.apply_settings(settings);
        self.settings_view.draft = None;
        self.render(Target::Live);
        self.render(Target::Preview);
        self.status = "Réglages enregistrés".into();
    }

    /// Sauvegarde la base et les réglages maintenant.
    fn backup_now(&mut self) {
        let (Some(db), Some(locations)) = (&self.db_path, &self.locations) else {
            self.status = "Sauvegarde impossible : pas de dossier de données".into();
            return;
        };
        let root = locations.beta.data().join("sauvegardes");
        let stamp = crate::maintenance::stamp(&today(), service::now_seconds());
        match crate::maintenance::backup(db, &locations.beta.settings(), &root, &stamp) {
            Ok(b) => {
                self.status = format!("Sauvegarde faite : {}", b.dir.display());
                self.settings_view.backups = crate::maintenance::list(&root);
            }
            Err(e) => self.status = format!("Sauvegarde impossible : {e}"),
        }
    }

    /// Prépare une restauration (vérifiée dans un fil à part) ; elle se fera au prochain démarrage.
    pub fn prepare_restore(&mut self, choice: crate::settings_page::RestoreChoice) {
        let Some(data) = self.data_dir() else {
            self.status = "Restauration impossible : pas de dossier de données".into();
            return;
        };
        let stamp = crate::maintenance::stamp(&today(), service::now_seconds());
        po_core::journal::line(&format!("restauration : préparation de {}", choice.label()));
        self.settings_view.preparing = true;
        self.restore_job = Some(std::thread::spawn(move || match choice {
            crate::settings_page::RestoreChoice::Backup(dir) => crate::restore::prepare_backup(&dir, &data),
            crate::settings_page::RestoreChoice::Archive(file) => crate::restore::prepare_archive(&file, &data, &stamp),
        }));
    }

    /// La restauration préparée est-elle vérifiée ?
    pub fn poll_restore(&mut self) {
        if !self.restore_job.as_ref().is_some_and(JoinHandle::is_finished) {
            if self.restore_job.is_some() {
                self.ctx.request_repaint_after(Duration::from_millis(200));
            }
            return;
        }
        let Some(job) = self.restore_job.take() else { return };
        self.settings_view.preparing = false;
        match job.join().unwrap_or_else(|_| Err("préparation interrompue".into())) {
            Ok(label) => {
                po_core::journal::line(&format!("restauration : {label} prête"));
                self.status = format!("Restauration prête : {label} (au prochain démarrage)");
                self.settings_view.pending_restore = Some(label);
            }
            Err(e) => {
                po_core::journal::line(&format!("restauration refusée : {e}"));
                self.status = format!("Restauration impossible : {e}");
            }
        }
    }

    /// Le contrôle avant culte (Ctrl+Shift+D).
    pub fn preflight(&mut self) -> Vec<crate::maintenance::Check> {
        let backups = self.data_dir().map(|d| crate::maintenance::list(&d.join("sauvegardes"))).unwrap_or_default();
        let last_backup = backups.first().and_then(|b| b.when.elapsed().ok());
        let (playlist, missing_media) = match (&self.db, self.playlist.folder) {
            (Some(db), Some(folder)) => {
                let items = db.list_items(Some(folder)).unwrap_or_default();
                let name = db.folder(folder).ok().flatten().map(|f| f.name).unwrap_or_default();
                let missing = items
                    .iter()
                    .filter(|i| {
                        i.source == "media"
                            && !i.background.is_empty()
                            && !std::path::Path::new(&i.background).is_file()
                    })
                    .map(|i| {
                        std::path::Path::new(&i.background)
                            .file_name()
                            .map_or(i.background.clone(), |n| n.to_string_lossy().to_string())
                    })
                    .collect();
                (Some((name, items.len())), missing)
            }
            _ => (None, Vec::new()),
        };
        let situation = crate::maintenance::Situation {
            database_open: self.db.is_some(),
            screens: crate::screens::list().len(),
            font_families: self.designs.families.len(),
            web: self.web.as_ref().map(|w| match (&w.error, w.addr()) {
                (None, Some(addr)) => Ok(addr.to_string()),
                (Some(e), _) => Err(e.clone()),
                (None, None) => Err("Serveur Web arrêté".into()),
            }),
            ndi: po_ndi::available(&[]).map(|p| p.display().to_string()),
            last_backup,
            missing_media,
            playlist,
        };
        crate::maintenance::preflight(&situation)
    }

    /// Ouvre la base de la bêta (sa copie : la 2.x n'est jamais ouverte en écriture). Une copie
    /// d'une 2.x plus ancienne reçoit les migrations (additives) ; sinon, rien n'est réécrit.
    fn open_database(&mut self, path: PathBuf) {
        // Une restauration préparée se fait maintenant, avant que la base ne soit ouverte.
        let mut restored = None;
        if let Some(locations) = &self.locations {
            let stamp = crate::maintenance::stamp(&today(), service::now_seconds());
            restored = crate::restore::apply_pending(&locations.beta.data(), &path, &locations.beta.settings(), &stamp);
        }
        match &restored {
            Some(Ok(label)) => {
                po_core::journal::line(&format!("restauration : {label} remise en place"));
                self.status = format!("Restauré : {label}. L'état d'avant est dans les sauvegardes.");
                self.reload_settings();
            }
            Some(Err(e)) => {
                po_core::journal::line(&format!("restauration échouée : {e}"));
                self.status = format!("Restauration échouée : {e}");
            }
            None => {}
        }
        let opened = Database::open(&path, Mode::ReadWrite).and_then(|db| {
            if db.schema_version()? < po_db::SCHEMA_VERSION {
                drop(db);
                Database::open_and_initialize(&path, &po_db::InitOptions::default()).map(|(db, _)| db)
            } else {
                Ok(db)
            }
        });
        match opened {
            Ok(db) => {
                self.bible.ensure_loaded(&db);
                self.db = Some(db);
                let wake = self.ctx.clone();
                self.search = Some(SearchThread::spawn(path.clone(), move || wake.request_repaint()));
                self.warm_up = Some(crate::data::warm_up(path.clone()));
                self.db_path = Some(path);
                self.startup = Startup::Ready;
                if let Some(dir) = self.data_dir() {
                    self.recovery = crate::recovery::load(&crate::recovery::file(&dir));
                    self.settings_view.backups = crate::maintenance::list(&dir.join("sauvegardes"));
                    self.settings_view.pending_restore = crate::restore::pending(&dir);
                    // Les photos ajoutées sont copiées dans les données, comme dans la 2.8.
                    self.settings_view.gallery.folder = Some(dir.join("church").join("photos"));
                }
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
            if let Some(dir) = self.data_dir() {
                let event = crate::history::Event {
                    at: service::now_seconds(),
                    reference: slide.reference.clone(),
                    text: slide.text.clone(),
                    kind: format!("{:?}", slide.source).to_lowercase(),
                };
                let _ = crate::history::record(&crate::history::file(&dir, &today()), &event);
                let _ = crate::recovery::save(
                    &crate::recovery::file(&dir),
                    &shown.program,
                    &shown.origin,
                    &shown.items,
                    self.live_stage.hidden(),
                );
            }
            self.taken = Some(slide.clone());
            self.follow_live = true;
            // Un slide de playlist passe au direct : la section qui commence par lui démarre.
            if let Some(item) = shown.item()
                && self.tracker.enter_item(item, service::now_seconds())
                && let Some(s) = self.tracker.current.and_then(|i| self.tracker.sections.get(i))
            {
                po_core::journal::line(&format!("déroulé : section « {} »", s.name));
            }
        }
        // Un design essayé dans la bibliothèque ne touche que l'Aperçu.
        let design = match (target, &self.preview_design) {
            (Target::Preview, Some(tried)) => tried.clone(),
            _ => self.design.clone(),
        };
        self.worker.submit(Job { target, id, slide, design, width, height, blur });
    }

    /// Prépare un programme dans l'Aperçu.
    pub fn cue(&mut self, prepared: Prepared) {
        self.cue_items(prepared, Vec::new());
    }

    fn cue_items(&mut self, prepared: Prepared, items: Vec<i64>) {
        match Program::from_cue(&prepared.cue, &self.split) {
            Some(program) => {
                self.preview = Some(Shown { program, origin: prepared.origin, items });
                self.render(Target::Preview);
            }
            None => self.status = "Rien à projeter : texte vide.".into(),
        }
    }

    /// Envoie l'Aperçu au direct (F2).
    pub fn take(&mut self) {
        self.abandon_slideshow();
        if let Some(preview) = self.preview.clone() {
            self.live = Some(preview);
            self.render(Target::Live);
            self.status = "Au direct".into();
        }
    }

    /// Slide suivant (`+1`) ou précédent (`-1`) au direct.
    pub fn step(&mut self, delta: i32) {
        // Une flèche pendant le diaporama : il s'arrête, et la flèche agit sur le direct rendu.
        if self.slideshow.active {
            self.stop_slideshow();
        }
        // Sous-titres affichés : ← et → avancent d'abord dans le paragraphe.
        if self.live.is_some() && self.subtitles.step(delta) {
            self.status = format!("Sous-titre {} / {}", self.subtitles.index + 1, self.subtitles.chunks.len());
            return;
        }
        self.subtitles_backwards = delta < 0;
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
            // Dans le diaporama : on repart de l'image choisie.
            let now = self.ctx.input(|i| i.time);
            self.slideshow.arm(row, now);
        }
    }

    // ── Diaporama ───────────────────────────────────────────────────────────────────────────────

    /// Lance un diaporama : il prend le direct (celui d'avant reviendra à l'arrêt).
    pub fn start_slideshow(&mut self, medias: Vec<crate::media::Media>, title: &str) {
        let Some(program) = crate::media::cue(&medias, title).and_then(|c| Program::from_cue(&c, &self.split)) else {
            self.status = "Diaporama : aucune image".into();
            return;
        };
        if !self.slideshow.active {
            self.slideshow_before = Some((self.live.clone(), self.live_stage.hidden()));
        }
        if self.live_stage.hidden() {
            self.toggle_hidden();
        }
        self.live = Some(Shown { program, origin: Origin::Slideshow, items: Vec::new() });
        self.slideshow.begin(&medias, self.media_view.seconds);
        self.render(Target::Live);
        let now = self.ctx.input(|i| i.time);
        self.slideshow.arm(0, now);
        if self.live_video_path().is_some() {
            self.slideshow.hold();
        }
        self.status = format!("Diaporama « {} » : {} média(s)", title.trim(), medias.len());
    }

    /// Arrête le diaporama et rend le direct d'avant, à l'identique.
    pub fn stop_slideshow(&mut self) {
        if !self.slideshow.active {
            return;
        }
        self.slideshow.end();
        if let Some((live, hidden)) = self.slideshow_before.take() {
            self.live = live;
            if self.live.is_some() {
                self.render(Target::Live);
            } else {
                // Rien n'était au direct : les écrans se vident.
                self.live_stage.clear();
                self.taken = Some(Slide::new("", "", po_design::SlideSource::Custom));
            }
            if hidden != self.live_stage.hidden() {
                self.toggle_hidden();
            }
        }
        self.status = "Diaporama arrêté : le direct d'avant est revenu".into();
    }

    /// Un autre programme prend le direct : le diaporama se clôt sans rien rendre.
    fn abandon_slideshow(&mut self) {
        if self.slideshow.active {
            self.slideshow.end();
            self.slideshow_before = None;
        }
    }

    /// L'image suivante quand son temps est passé.
    fn tick_slideshow(&mut self, now: f64) {
        // Une vidéo passe au média suivant à sa fin ; une image, à la fin de sa durée.
        let video_done = self.slideshow.active && self.video.as_ref().is_some_and(|v| v.player.ended());
        if (self.slideshow.due(now) || video_done)
            && let Some(live) = self.live.as_mut()
        {
            let next = crate::media::Slideshow::following(live.program.current(), live.program.len());
            live.program.set(next);
            self.render(Target::Live);
            self.slideshow.arm(next, now);
            if self.live_video_path().is_some() {
                self.slideshow.hold();
            }
            // La vidéo d'après (même fichier en boucle compris) repart de zéro.
            self.video = None;
        }
        if let Some(at) = self.slideshow.next_at() {
            self.ctx.request_repaint_after(Duration::from_secs_f64((at - now).max(0.05)));
        }
    }

    /// Le fichier vidéo du slide au direct, s'il y en a un.
    pub fn live_video_path(&self) -> Option<String> {
        let slide = self.live.as_ref()?.program.slide();
        slide.background.filter(|b| crate::video::is_video_file(b))
    }

    /// Démarre ou arrête le lecteur selon le slide au direct, et prépare son image.
    fn sync_video(&mut self) {
        let wanted = self.live_video_path();
        let playing = self.video.as_ref().map(|v| v.player.path.to_string_lossy().to_string());
        if wanted != playing {
            self.video = None;
            if let Some(path) = wanted.clone().filter(|p| self.video_failed.as_deref() != Some(p.as_str())) {
                let max = self.render_size();
                match crate::video::Player::start(
                    std::path::Path::new(&path),
                    0.0,
                    self.video_looping,
                    max,
                    self.video_muted,
                ) {
                    Ok(player) => {
                        player.set_volume(self.video_volume);
                        self.video = Some(crate::video::LiveVideo::new(player));
                        self.video_failed = None;
                    }
                    Err(e) => {
                        po_core::journal::line(&format!("vidéo : {e}"));
                        self.status = e;
                        self.video_failed = Some(path);
                    }
                }
            }
        }
        if let Some(video) = &mut self.video {
            video.upload(&self.ctx);
            if !video.player.paused() && !video.player.ended() {
                self.ctx.request_repaint_after(Duration::from_millis(15));
            }
        }
    }

    /// Recommence la vidéo au direct (ou la relance en boucle, ou non), à partir de `from` secondes.
    fn restart_video(&mut self, from: f64) {
        let Some(path) = self.live_video_path() else { return };
        self.video = None;
        let max = self.render_size();
        match crate::video::Player::start(std::path::Path::new(&path), from, self.video_looping, max, self.video_muted)
        {
            Ok(player) => {
                player.set_volume(self.video_volume);
                self.video = Some(crate::video::LiveVideo::new(player));
            }
            Err(e) => self.status = e,
        }
    }

    /// Les commandes de la vidéo au direct, sous le moniteur.
    fn video_controls(&mut self, ui: &mut Ui) {
        let Some(video) = &self.video else { return };
        let (paused, ended) = (video.player.paused(), video.player.ended());
        let (position, duration) = (video.player.position(), video.player.probe.duration_s);
        let mut restart = None;
        ui.horizontal(|ui| {
            let label = if paused || ended { "Lecture" } else { "Pause" };
            if widgets::button(ui, None, label, Tone::Secondary).clicked() {
                if ended {
                    restart = Some(0.0);
                } else {
                    video.player.set_paused(!paused);
                }
            }
            if widgets::button(ui, None, "Recommencer", Tone::Secondary).clicked() {
                restart = Some(0.0);
            }
            ui.label(
                RichText::new(format!("{} / {}", crate::video::clock(position), crate::video::clock(duration)))
                    .font(semibold(12.0))
                    .color(TEXT),
            );
            let mut looping = self.video_looping;
            if ui.checkbox(&mut looping, "Boucle").changed() {
                self.video_looping = looping;
                restart = Some(position);
            }
            let mut volume = self.video_volume;
            if ui.add(egui::Slider::new(&mut volume, 0.0..=1.0).show_value(false).text("Volume")).changed() {
                self.video_volume = volume;
                video.player.set_volume(volume);
            }
        });
        if let Some(from) = restart {
            self.restart_video(from);
        }
    }

    /// Projette un écran de l'église : rendu en image (aux couleurs et au profil de l'église), puis
    /// mis au direct comme une image, comme la 2.8.
    pub fn show_church(&mut self, screen: crate::media::ChurchScreen) {
        use crate::media::ChurchScreen;
        let profile = po_design::church::ChurchProfile::from_settings(self.settings.other.get("church"));
        let (file, default_label) = screen.names();
        let label = match screen {
            ChurchScreen::Welcome if !profile.name.is_empty() => profile.name.clone(),
            ChurchScreen::Speaker if !profile.speaker_label().is_empty() => profile.speaker_label(),
            _ => default_label.to_string(),
        };
        let (w, h) = (1920, 1080);
        let png = self.hub.render_png(w, h, |fonts| match screen {
            ChurchScreen::Welcome => po_layout::church::layout_welcome(fonts, &profile, w as f32, h as f32),
            ChurchScreen::Speaker => po_layout::church::layout_speaker(fonts, &profile, w as f32, h as f32),
            ChurchScreen::Socials => po_layout::church::layout_socials(fonts, &profile, w as f32, h as f32),
        });
        match png {
            Ok(png) => self.project_image(&png, file, &label),
            Err(e) => self.status = format!("Écran de l'église impossible : {e}"),
        }
    }

    /// Met au direct une image rendue (écran de l'église, image de citation), comme une image de la
    /// playlist. `file` : le début du nom du fichier gardé dans les données.
    pub fn project_image(&mut self, png: &[u8], file: &str, label: &str) {
        let label = label.to_string();
        // Un nom propre à chaque rendu : une image déjà chargée ne masque jamais la nouvelle.
        let dir = self
            .data_dir()
            .or_else(|| self.db_path.as_ref().and_then(|p| p.parent().map(std::path::Path::to_path_buf)))
            .unwrap_or_else(std::env::temp_dir)
            .join("church");
        let digest: String = {
            use sha2::Digest;
            sha2::Sha256::digest(png).iter().take(6).map(|b| format!("{b:02x}")).collect()
        };
        let path = dir.join(format!("{file}-{digest}.png"));
        if let Ok(entries) = std::fs::read_dir(&dir) {
            for old in entries.flatten() {
                let name = old.file_name().to_string_lossy().to_string();
                if name.starts_with(&format!("{file}-")) && old.path() != path {
                    let _ = std::fs::remove_file(old.path());
                }
            }
        }
        if let Err(e) = std::fs::create_dir_all(&dir).and_then(|()| std::fs::write(&path, png)) {
            self.status = format!("Écran de l'église impossible : {e}");
            return;
        }
        let media = crate::media::Media { name: label.clone(), path: path.to_string_lossy().to_string(), seconds: 0 };
        let Some(program) = crate::media::cue(&[media], &label).and_then(|c| Program::from_cue(&c, &self.split)) else {
            return;
        };
        self.abandon_slideshow();
        self.live = Some(Shown { program, origin: Origin::Church, items: Vec::new() });
        self.render(Target::Live);
        self.status = format!("Au direct : {label}");
    }

    /// Ouvre l'image de citation avec le slide au direct (sinon celui de l'Aperçu).
    pub fn open_quote(&mut self) {
        let profile = po_design::church::ChurchProfile::from_settings(self.settings.other.get("church"));
        let slide = self.live.as_ref().or(self.preview.as_ref()).map(|s| s.program.slide());
        let (text, reference) = slide.map(|s| (s.text, s.reference)).unwrap_or_default();
        self.quote.open_with(&text, &reference, &profile);
    }

    fn quote_window(&mut self, ctx: &egui::Context) {
        if !self.quote.open {
            return;
        }
        let profile = po_design::church::ChurchProfile::from_settings(self.settings.other.get("church"));
        let hub = self.hub.clone();
        let actions = self
            .quote
            .show(ctx, &profile, |quote, w, h| hub.render_list_rgba(w, h, |fonts| quote.layout(fonts, &profile)).ok());
        let (w, h) = crate::quote::size_of(&self.quote.format);
        for action in actions {
            match action {
                crate::quote::QuoteAction::Save(path) => {
                    let png = self.hub.render_png(w, h, |fonts| self.quote.layout(fonts, &profile));
                    self.quote.message = match png.and_then(|png| std::fs::write(&path, png).map_err(|e| e.to_string()))
                    {
                        Ok(()) => format!("Enregistrée : {}", path.display()),
                        Err(e) => format!("Image non enregistrée : {e}"),
                    };
                    self.status = self.quote.message.clone();
                }
                crate::quote::QuoteAction::Copy => {
                    match self.hub.render_list_rgba(w, h, |fonts| self.quote.layout(fonts, &profile)) {
                        Ok(pixels) => {
                            let image = egui::ColorImage::from_rgba_premultiplied([w as usize, h as usize], &pixels);
                            ctx.copy_image(image);
                            self.quote.message = "Image copiée : collez-la dans WhatsApp ou Facebook (Ctrl+V).".into();
                        }
                        Err(e) => self.quote.message = format!("Copie impossible : {e}"),
                    }
                }
                crate::quote::QuoteAction::Project => {
                    match self.hub.render_png(w, h, |fonts| self.quote.layout(fonts, &profile)) {
                        Ok(png) => {
                            let label = self.quote.reference.lines().next().unwrap_or("Citation").to_string();
                            let label = if label.is_empty() { "Citation".to_string() } else { label };
                            self.project_image(&png, "citation", &label);
                        }
                        Err(e) => self.quote.message = format!("Projection impossible : {e}"),
                    }
                }
                crate::quote::QuoteAction::RememberStyle(style) => {
                    // Le modèle choisi reste celui de l'église (comme dans la 2.8).
                    let mut settings = self.settings.clone();
                    let church = settings.other.entry("church".to_string()).or_insert_with(|| serde_json::json!({}));
                    if let Some(map) = church.as_object_mut() {
                        map.insert("quote_style".into(), serde_json::json!(style));
                        self.save_settings(settings);
                    }
                }
            }
        }
    }

    /// Le diaporama en cours : l'image montrée et leur nombre.
    pub fn slideshow_position(&self) -> Option<(usize, usize)> {
        let live = self.live.as_ref().filter(|_| self.slideshow.active)?;
        Some((live.program.current(), live.program.len()))
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
                let current = self.projectors.iter().find(|p| **p == projector).map(|p| p.kind);
                let on = current == Some(po_web::ScreenKind::Room);
                if ui.add(egui::Button::selectable(on, &screen.label)).clicked() {
                    if current.is_some_and(|k| k != po_web::ScreenKind::Room) {
                        self.toggle_output(screen.clone(), po_web::ScreenKind::Room);
                    } else {
                        self.toggle_projector(projector);
                    }
                    ui.close();
                }
                // Une sortie HDMI de diffusion sur cet écran (vers un mélangeur vidéo).
                ui.horizontal(|ui| {
                    ui.add_space(14.0);
                    for kind in
                        [po_web::ScreenKind::Broadcast, po_web::ScreenKind::Subtitles, po_web::ScreenKind::Stage]
                    {
                        let on = current == Some(kind);
                        if ui.add(egui::Button::selectable(on, RichText::new(kind.label()).size(11.5))).clicked() {
                            self.toggle_output(screen.clone(), kind);
                            ui.close();
                        }
                    }
                });
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
            Action::Add { entries, source, range } => {
                let folder = self.playlist.folder;
                self.add = Some(AddDialog { entries, source, range, folder, new_name: String::new() });
            }
        }
    }

    /// Les titres des biographies (pas d'identification de Branham sur elles, même en playlist).
    fn biographies(db: &Database) -> Vec<String> {
        db.list_books()
            .unwrap_or_default()
            .into_iter()
            .filter(|b| crate::library::books::BOOK_KEYS[..2].contains(&b.key.as_str()))
            .map(|b| b.title)
            .collect()
    }

    /// Projette (ou prépare) la playlist choisie à partir de l'élément `item`.
    pub fn play_playlist(&mut self, item: i64, take: bool) {
        let (Some(db), Some(folder)) = (self.db.as_ref(), self.playlist.folder) else { return };
        let items = db.list_items(Some(folder)).unwrap_or_default();
        let name = self.playlist.folder_name();
        let Some(program) = crate::playlist::program(&name, &items, Some(item), &Self::biographies(db)) else {
            self.status = "Rien à projeter dans cette playlist (slides vides ou médias).".into();
            return;
        };
        let prepared = Prepared { cue: program.cue, origin: Origin::Playlist(folder) };
        self.cue_items(prepared, program.item_of_entry);
        if take {
            self.take();
        }
    }

    /// Ouvre un chapitre de la Bible sur un verset et le prépare (essais, mesures).
    pub fn open_bible(&mut self, translation: i64, book: i64, chapter: i64, verse: Option<i64>) {
        let Some(db) = self.db.as_ref() else { return };
        self.page = Page::Bible;
        if let Some(p) = self.bible.open(db, translation, book, chapter, verse) {
            self.cue(p);
        }
    }

    /// Ajoute des entrées à la playlist choisie (essais, mesures).
    pub fn playlists_add(&mut self, entries: &[po_program::Entry], source: &'static str) {
        let (Some(folder), Some(db)) = (self.playlist.folder, self.db.as_mut()) else { return };
        self.playlists.add_entries(db, Some(folder), "", entries, source);
        self.playlist.reload(db, None);
        self.sync_tracker();
    }

    /// Le déroulé suit la playlist choisie (sauf pendant un culte suivi sur une autre playlist).
    fn sync_tracker(&mut self) {
        let sections: Vec<service::PlanSection> = self
            .playlist
            .sections
            .iter()
            .map(|s| service::PlanSection {
                id: s.id,
                name: s.name.clone(),
                duration_min: s.duration_min,
                item_id: s.item_id,
            })
            .collect();
        if self.tracker_folder == self.playlist.folder {
            self.tracker.sections = sections;
        } else if !self.tracker.running() {
            self.tracker = Tracker::new(sections);
            self.tracker_folder = self.playlist.folder;
        }
    }

    /// Applique les demandes de la page Playlist, puis la recharge.
    pub fn apply_playlist(&mut self, actions: Vec<PlaylistAction>) {
        for action in actions {
            let folder = self.playlist.folder;
            let mut select = None;
            let mut play = None;
            let mut start = false;
            let mut slideshow = None;
            {
                let Some(db) = self.db.as_mut() else { return };
                let p = &mut self.playlists;
                match action {
                    PlaylistAction::SelectFolder(id) => {
                        self.playlist.folder = Some(id);
                        self.playlist.selected.clear();
                    }
                    PlaylistAction::CreateFolder(name) => {
                        if let Some(id) = p.create_folder(db, &name) {
                            self.playlist.folder = Some(id);
                        }
                    }
                    PlaylistAction::RenameFolder(id, name) => {
                        p.rename_folder(db, id, &name);
                    }
                    PlaylistAction::DeleteFolder(id) => {
                        p.delete_folder(db, id);
                        if folder == Some(id) {
                            self.playlist.folder = None;
                        }
                    }
                    PlaylistAction::CreateItem(reference, text) => {
                        if let Some(f) = folder {
                            select = p.create_item(db, f, &reference, &text).map(|id| vec![id]);
                        }
                    }
                    PlaylistAction::UpdateItem(id, reference, text) => {
                        if let Some(f) = folder {
                            p.update_item(db, f, id, &reference, &text);
                            select = Some(vec![id]);
                        }
                    }
                    PlaylistAction::Delete(ids) => {
                        if let Some(f) = folder {
                            let n = p.delete_items(db, f, &ids);
                            self.playlist.say(format!("{n} slide{} supprimé{} · Ctrl+Z annule", plural(n), plural(n)));
                        }
                    }
                    PlaylistAction::Duplicate(ids) => {
                        if let Some(f) = folder {
                            select = Some(p.duplicate(db, f, &ids));
                        }
                    }
                    PlaylistAction::Reorder(order) => {
                        if let Some(f) = folder {
                            let keep = self.playlist.selection();
                            p.reorder(db, f, &order);
                            select = Some(keep);
                        }
                    }
                    PlaylistAction::CopyTo(ids, destination) => {
                        let n = p.copy_to(db, &ids, destination).len();
                        self.playlist.say(format!("{n} slide{} copié{}", plural(n), plural(n)));
                    }
                    PlaylistAction::MoveTo(ids, destination) => {
                        if let Some(f) = folder {
                            let n = p.move_to(db, &ids, f, destination);
                            self.playlist.say(format!("{n} slide{} déplacé{}", plural(n), plural(n)));
                        }
                    }
                    PlaylistAction::Undo => {
                        let message = if p.undo(db) { "Modification annulée" } else { "Rien à annuler" };
                        self.playlist.say(message);
                    }
                    PlaylistAction::Cue(item) => play = Some((item, false)),
                    PlaylistAction::Take(item) => play = Some((item, true)),
                    PlaylistAction::StartSectionAt { section, item, name, duration } => {
                        if let Some(f) = folder {
                            match section {
                                None => {
                                    let _ = db.add_section(f, &name, duration, Some(item));
                                }
                                Some(id) => {
                                    let _ = db.update_section(id, &name, duration, Some(item));
                                }
                            }
                        }
                    }
                    PlaylistAction::DetachSection(id) => {
                        if let Some(s) = self.playlist.sections.iter().find(|s| s.id == id) {
                            let _ = db.update_section(id, &s.name, s.duration_min, None);
                        }
                    }
                    PlaylistAction::AddSection { name, duration, item } => {
                        if let Some(f) = folder {
                            let _ = db.add_section(f, &name, duration, item);
                        }
                    }
                    PlaylistAction::UpdateSection { id, name, duration, item } => {
                        let _ = db.update_section(id, &name, duration, item);
                    }
                    PlaylistAction::DeleteSection(id) => {
                        let _ = db.delete_section(id);
                    }
                    PlaylistAction::MoveSection(id, delta) => {
                        let _ = db.move_section(id, delta);
                    }
                    PlaylistAction::SetStartTime(text) => {
                        if let Some(f) = folder {
                            let _ = db.set_start_time(f, &text);
                        }
                    }
                    PlaylistAction::StartService => start = true,
                    PlaylistAction::StopService => self.tracker.stop(),
                    PlaylistAction::NextSection => {
                        self.tracker.next(service::now_seconds());
                    }
                    PlaylistAction::Export => {
                        if let Some(f) = folder {
                            let name = db.folder(f).ok().flatten().map(|f| f.name).unwrap_or_else(|| "Playlist".into());
                            let items = db.list_items(Some(f)).unwrap_or_default();
                            let message = match crate::library::playlist::exchange_dir() {
                                Some(dir) => {
                                    let file = dir.join(format!("{}.zip", po_design::library::slug(&name)));
                                    match crate::transfer::export(&file, &name, &items) {
                                        Ok(n) => format!("{n} élément(s) exporté(s) : {}", file.display()),
                                        Err(e) => format!("Export impossible : {e}"),
                                    }
                                }
                                None => "Dossier Documents introuvable".into(),
                            };
                            self.playlist.say(&message);
                        }
                    }
                    PlaylistAction::Slideshow => {
                        if let Some(f) = folder {
                            let name =
                                db.folder(f).ok().flatten().map(|f| f.name).unwrap_or_else(|| "Diaporama".into());
                            // La durée de chaque image : celle de la bibliothèque de médias de la 2.x.
                            let library = db.list_media().unwrap_or_default();
                            let medias: Vec<crate::media::Media> = db
                                .list_items(Some(f))
                                .unwrap_or_default()
                                .into_iter()
                                .filter(|i| i.source == "media" && crate::playlist::is_image_file(&i.background))
                                .map(|i| crate::media::Media {
                                    name: if i.reference.trim().is_empty() {
                                        i.background.clone()
                                    } else {
                                        i.reference.clone()
                                    },
                                    seconds: library
                                        .iter()
                                        .find(|m| m.path == i.background)
                                        .map_or(0, |m| m.duration_seconds.clamp(0, 3600) as u32),
                                    path: i.background,
                                })
                                .collect();
                            slideshow = Some((medias, name));
                        }
                    }
                    PlaylistAction::Import(file) => {
                        let media = self
                            .locations
                            .as_ref()
                            .map_or_else(|| file.with_extension("medias"), |l| l.beta.data().join("media"));
                        let message = match crate::transfer::read(&file, &media) {
                            Ok((name, items)) => match db.import_folder(&name, &items) {
                                Ok(id) => {
                                    self.playlist.folder = Some(id);
                                    self.playlist.selected.clear();
                                    format!("Playlist « {name} » importée : {} élément(s)", items.len())
                                }
                                Err(e) => format!("Import impossible : {e}"),
                            },
                            Err(e) => format!("Import impossible : {e}"),
                        };
                        self.playlist.say(&message);
                    }
                }
                self.playlist.reload(db, select);
            }
            self.sync_tracker();
            if start {
                self.sync_tracker_now();
                self.tracker.start(service::now_seconds());
            }
            if let Some((item, take)) = play {
                self.play_playlist(item, take);
            }
            if let Some((medias, name)) = slideshow {
                self.start_slideshow(medias, &name);
            }
        }
    }

    /// Le déroulé prend la playlist choisie (au démarrage du suivi).
    fn sync_tracker_now(&mut self) {
        self.tracker_folder = None;
        self.tracker.stop();
        self.sync_tracker();
    }

    /// La fenêtre « Ajouter à la playlist ».
    fn add_window(&mut self, ui: &mut Ui) {
        let Some(mut dialog) = self.add.take() else { return };
        let mut keep = true;
        let mut confirmed = false;
        let folders = self.playlist_folders();
        egui::Window::new("Ajouter à la playlist")
            .collapsible(false)
            .resizable(false)
            .anchor(Align2::CENTER_CENTER, [0.0, 0.0])
            .show(ui.ctx(), |ui| {
                ui.set_min_width(420.0);
                let label =
                    |e: &po_program::Entry| e.reference.rsplit(" - ").next().unwrap_or(&e.reference).to_string();
                if let Some((from, to)) = dialog.range.as_mut() {
                    let last = dialog.entries.len().saturating_sub(1);
                    ui.horizontal(|ui| {
                        ui.label("De");
                        egui::ComboBox::from_id_salt("plage-debut")
                            .selected_text(label(&dialog.entries[*from]))
                            .show_ui(ui, |ui| {
                                for (i, e) in dialog.entries.iter().enumerate() {
                                    ui.selectable_value(from, i, label(e));
                                }
                            });
                        ui.label("à");
                        egui::ComboBox::from_id_salt("plage-fin").selected_text(label(&dialog.entries[*to])).show_ui(
                            ui,
                            |ui| {
                                for (i, e) in dialog.entries.iter().enumerate() {
                                    ui.selectable_value(to, i, label(e));
                                }
                            },
                        );
                    });
                    *to = (*to).clamp(*from, last);
                }
                let count = match dialog.range {
                    Some((a, b)) => b - a + 1,
                    None => dialog.entries.len(),
                };
                ui.label(
                    RichText::new(format!("{count} slide{} à ajouter", plural(count))).font(medium(12.5)).color(TEXT),
                );
                ui.add_space(6.0);
                for (id, name) in &folders {
                    ui.radio_value(&mut dialog.folder, Some(*id), name);
                }
                ui.horizontal(|ui| {
                    ui.radio_value(&mut dialog.folder, None, "Nouvelle playlist :");
                    let r = ui.add(
                        egui::TextEdit::singleline(&mut dialog.new_name)
                            .hint_text("Culte du dimanche")
                            .desired_width(200.0),
                    );
                    ui.ctx().accesskit_node_builder(r.id, |n| n.set_label("Nom de la nouvelle playlist"));
                    if r.changed() {
                        dialog.folder = None;
                    }
                });
                ui.add_space(8.0);
                ui.horizontal(|ui| {
                    let ready = dialog.folder.is_some() || !dialog.new_name.trim().is_empty();
                    if widgets::button_at(ui, Size::Normal, Some(Icon::Plus), "Ajouter", Tone::Primary(ACCENT), ready)
                        .clicked()
                    {
                        confirmed = true;
                    }
                    if widgets::button(ui, None, "Annuler", Tone::Secondary).clicked()
                        || ui.input(|i| i.key_pressed(Key::Escape))
                    {
                        keep = false;
                    }
                });
            });
        if confirmed {
            keep = false;
            let chosen: Vec<po_program::Entry> = match dialog.range {
                Some((a, b)) => dialog.entries[a..=b.min(dialog.entries.len().saturating_sub(1))].to_vec(),
                None => dialog.entries.clone(),
            };
            if let Some(db) = self.db.as_mut()
                && let Some((folder, ids)) =
                    self.playlists.add_entries(db, dialog.folder, &dialog.new_name, &chosen, dialog.source)
            {
                let name = db.folder(folder).ok().flatten().map(|f| f.name).unwrap_or_default();
                self.status = format!(
                    "{} slide{} ajouté{} à « {name} » · Ctrl+Z (page Playlist) annule",
                    ids.len(),
                    plural(ids.len()),
                    plural(ids.len())
                );
                if self.playlist.folder.is_none() || self.playlist.folder == Some(folder) {
                    self.playlist.folder = Some(folder);
                }
                self.playlist.reload(db, None);
                self.sync_tracker();
            }
        }
        if keep {
            self.add = Some(dialog);
        }
    }

    fn playlist_folders(&self) -> Vec<(i64, String)> {
        self.db
            .as_ref()
            .map(|db| db.list_folders().unwrap_or_default().into_iter().map(|f| (f.id, f.name)).collect())
            .unwrap_or_default()
    }

    /// L'Aperçu et le direct, en éléments de playlist.
    fn playlist_marks(&self) -> PlaylistMarks {
        let of = |s: &Option<Shown>| {
            s.as_ref()
                .filter(|s| matches!(s.origin, Origin::Playlist(f) if Some(f) == self.playlist.folder))
                .and_then(Shown::item)
        };
        PlaylistMarks { preview: of(&self.preview), live: of(&self.live) }
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
                Key2::LowerThird => self.toggle_lower_third(),
                Key2::Subtitles => self.toggle_subtitles(),
                Key2::HdmiPattern => self.toggle_pattern(),
                Key2::NextSection => {
                    if self.tracker.next(service::now_seconds()) {
                        self.status = "Déroulé : section suivante".into();
                    }
                }
                Key2::Preflight => {
                    self.settings_view.checks = self.preflight();
                    self.preflight_open = true;
                }
                Key2::History => self.history_open = !self.history_open,
                Key2::Welcome => self.show_church(crate::media::ChurchScreen::Welcome),
                Key2::Pastor => self.show_church(crate::media::ChurchScreen::Speaker),
                Key2::Socials => self.show_church(crate::media::ChurchScreen::Socials),
                Key2::Quote => self.open_quote(),
            }
        }
        let typing = self.ctx.egui_wants_keyboard_input();
        // Ctrl+1 … Ctrl+5 : les pages du rail.
        let pages = [Key::Num1, Key::Num2, Key::Num3, Key::Num4, Key::Num5, Key::Num6];
        for (key, page) in pages.into_iter().zip(Page::ALL) {
            if self.ctx.input_mut(|i| i.consume_key(egui::Modifiers::COMMAND, key)) {
                self.page = page;
            }
        }
        if self.ctx.input_mut(|i| i.consume_key(egui::Modifiers::COMMAND, Key::Num7)) {
            self.page = Page::Designs;
        }
        if self.ctx.input_mut(|i| i.consume_key(egui::Modifiers::COMMAND, Key::Num8)) {
            self.page = Page::Settings;
        }
        if self.ctx.input_mut(|i| i.consume_key(egui::Modifiers::COMMAND, Key::Num9)) {
            self.page = Page::Media;
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
        // La projection couvre la régie (un seul écran) : Échap y revient, comme dans PowerPoint.
        if self.projectors.iter().any(Projector::covers_regie) && pressed(Key::Escape) {
            self.projectors.retain(|p| !p.covers_regie());
            self.status = "Projection fermée".into();
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
            Page::Playlist | Page::Designs | Page::Settings | Page::Media => {}
        }
    }

    /// Une fermeture normale : plus de reprise à proposer au prochain démarrage.
    pub fn shutdown(&mut self) {
        if let Some(dir) = self.data_dir() {
            crate::recovery::clear(&crate::recovery::file(&dir));
        }
    }

    /// Reprend le direct laissé par un arrêt brutal.
    pub fn resume(&mut self) {
        let Some(snapshot) = self.recovery.take() else { return };
        self.abandon_slideshow();
        self.live = Some(Shown { program: snapshot.program, origin: snapshot.origin, items: snapshot.items });
        if snapshot.hidden != self.live_stage.hidden() {
            self.toggle_hidden();
        }
        self.render(Target::Live);
        self.status = "Direct repris".into();
    }

    fn recovery_banner(&mut self, ui: &mut Ui) {
        let Some(snapshot) = &self.recovery else { return };
        let title = snapshot.program.title.clone();
        let row = snapshot.program.current() + 1;
        let mut resume = false;
        let mut dismiss = false;
        egui::Panel::top("reprise").frame(bar_frame().fill(Color32::from_rgb(0x3a, 0x2a, 0x12))).show(ui, |ui| {
            ui.horizontal(|ui| {
                widgets::dot(ui, WARN);
                ui.label(
                    RichText::new(format!(
                        "Project-On s'est arrêté pendant le direct : « {title} », slide {row}. Reprendre là où vous étiez ?"
                    ))
                    .font(medium(12.5))
                    .color(TEXT),
                );
                if widgets::button(ui, None, "Reprendre le direct", Tone::Primary(ACCENT)).clicked() {
                    resume = true;
                }
                if widgets::button(ui, None, "Ignorer", Tone::Secondary).clicked() {
                    dismiss = true;
                }
            });
        });
        if resume {
            self.resume();
        } else if dismiss {
            self.recovery = None;
            self.shutdown();
        }
    }

    fn preflight_window(&mut self, ui: &mut Ui) {
        if !self.preflight_open {
            return;
        }
        let mut open = true;
        let checks = self.settings_view.checks.clone();
        egui::Window::new("Contrôle avant culte").open(&mut open).collapsible(false).default_width(560.0).show(
            ui.ctx(),
            |ui| {
                crate::settings_page::checks_list(ui, &checks);
            },
        );
        self.preflight_open = open;
    }

    fn history_window(&mut self, ui: &mut Ui) {
        if !self.history_open {
            return;
        }
        let Some(dir) = self.data_dir() else {
            self.history_open = false;
            self.status = "Historique : pas de dossier de données".into();
            return;
        };
        let path = crate::history::file(&dir, &today());
        let events = crate::history::read(&path);
        let mut open = true;
        let mut export: Option<(&str, String)> = None;
        egui::Window::new("Historique du culte").open(&mut open).default_size([640.0, 420.0]).show(ui.ctx(), |ui| {
            ui.horizontal(|ui| {
                ui.label(
                    RichText::new(format!("{} slide(s) aujourd'hui", events.len())).font(medium(12.5)).color(TEXT),
                );
                if widgets::button(ui, None, "Exporter en tableur", Tone::Secondary).clicked() {
                    export = Some(("csv", crate::history::to_csv(&events)));
                }
                if widgets::button(ui, None, "Exporter en sous-titres (SRT)", Tone::Secondary)
                    .on_hover_text("Calés sur le premier slide du jour (le début de l'enregistrement)")
                    .clicked()
                {
                    let origin = events.first().map_or(0.0, |e| e.at);
                    export = Some(("srt", crate::history::to_srt(&events, origin)));
                }
            });
            egui::ScrollArea::vertical().show(ui, |ui| {
                for e in events.iter().rev() {
                    ui.horizontal(|ui| {
                        ui.label(RichText::new(crate::history::clock(e.at)).font(semibold(12.0)).color(ACCENT));
                        ui.label(RichText::new(e.reference.replace('\n', " · ")).font(medium(12.0)).color(TEXT));
                        let preview: String = e.text.chars().take(80).collect();
                        ui.label(RichText::new(preview).font(regular(11.5)).color(MUTED));
                    });
                }
            });
        });
        self.history_open = open;
        if let Some((ext, body)) = export {
            let target = std::env::var_os("USERPROFILE")
                .map(|h| PathBuf::from(h).join("Documents").join("Project-On exports"))
                .unwrap_or_else(|| dir.join("exports"));
            let file = target.join(format!("historique-{}.{ext}", today()));
            self.status = match std::fs::create_dir_all(&target).and_then(|()| std::fs::write(&file, body)) {
                Ok(()) => format!("Exporté : {}", file.display()),
                Err(e) => format!("Export impossible : {e}"),
            };
        }
    }

    // ── Habillage et sorties ────────────────────────────────────────────────────────────────────

    /// L : affiche ou masque le lower third.
    pub fn toggle_lower_third(&mut self) {
        self.lower_third.toggle();
        self.status = if self.lower_third.shown { "Lower third affiché".into() } else { "Lower third masqué".into() };
    }

    /// S : affiche ou masque les sous-titres.
    pub fn toggle_subtitles(&mut self) {
        self.subtitles.shown = !self.subtitles.shown;
        self.status = if self.subtitles.shown {
            "Sous-titres affichés : ← et → avancent dans le paragraphe".into()
        } else {
            "Sous-titres masqués".into()
        };
    }

    /// F8 : la mire sur les sorties HDMI.
    pub fn toggle_pattern(&mut self) {
        self.hdmi_pattern = !self.hdmi_pattern;
        self.status = if self.hdmi_pattern { "Mire HDMI".into() } else { "Mire HDMI retirée".into() };
    }

    /// Ouvre (ou ferme) une sortie HDMI de ce genre sur un écran.
    pub fn toggle_output(&mut self, screen: crate::screens::Screen, kind: po_web::ScreenKind) {
        let wanted = Projector::output(screen, kind);
        match self.projectors.iter().position(|p| *p == wanted) {
            Some(i) if self.projectors[i].kind == kind => {
                self.projectors.remove(i);
                self.status = format!("Sortie fermée : {}", wanted.label());
            }
            Some(i) => {
                self.projectors[i].kind = kind;
                self.status = format!("Sortie : {}", wanted.label());
            }
            None => {
                self.status = format!("Sortie : {}", wanted.label());
                self.projectors.push(wanted);
            }
        }
    }

    /// Les sorties HDMI ouvertes (hors salle).
    pub fn hdmi_outputs(&self) -> usize {
        self.projectors.iter().filter(|p| p.kind != po_web::ScreenKind::Room).count()
    }

    fn apply_design(&mut self, action: DesignAction) {
        match action {
            DesignAction::Preview(design) => {
                self.preview_design = Some(design);
                self.render(Target::Preview);
            }
            DesignAction::ApplyLive => {
                if let Some(design) = self.preview_design.take() {
                    self.design = design;
                    self.render(Target::Live);
                    self.render(Target::Preview);
                    self.status = "Design appliqué au direct".into();
                }
            }
            DesignAction::Output(design) => {
                if let Some(output) = crate::designs::Output::of(&design) {
                    self.status = format!("Web, NDI et HDMI : « {} »", output.name);
                    self.output = output;
                    self.save_choices();
                }
            }
            DesignAction::LowerThird(design) => {
                if let po_design::library::DesignBody::LowerThird(style) = design.body {
                    self.lower_third.id = design.id;
                    self.lower_third.name = design.name.clone();
                    self.lower_third.style = style;
                    self.status = format!("Lower third : « {} »", design.name);
                    self.save_choices();
                }
            }
            DesignAction::Subtitles(design) => {
                if let po_design::library::DesignBody::Subtitles(style) = design.body {
                    self.subtitles.id = design.id;
                    self.subtitles.name = design.name.clone();
                    self.subtitles.style = style;
                    // Un autre style : le découpage est à refaire.
                    self.subtitles.cut_for = None;
                    self.status = format!("Sous-titres : « {} »", design.name);
                    self.save_choices();
                }
            }
            DesignAction::ToggleLowerThird => self.toggle_lower_third(),
            DesignAction::ToggleSubtitles => self.toggle_subtitles(),
            DesignAction::StepSubtitle(delta) => {
                self.subtitles.step(delta);
            }
            DesignAction::Ndi(on) => self.ndi = on,
            DesignAction::Pattern => self.toggle_pattern(),
            DesignAction::Status(text) => self.status = text,
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
                        "Copie de la base (une seule fois)… {seconds} s\nLa 2.8 et ses données ne sont pas modifiées."
                    ),
                );
                ui.ctx().request_repaint_after(Duration::from_millis(250));
                return;
            }
            Startup::Choose => {
                if let Some(origin) = choose_origin(ui) {
                    self.start_copy(origin);
                }
                return;
            }
            Startup::Failed(message) => {
                waiting(ui, "Project-On 3 ne peut pas démarrer", message);
                return;
            }
            Startup::Ready => {}
        }
        self.keyboard();
        self.recovery_banner(ui);
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
        self.add_window(ui);
        self.preflight_window(ui);
        self.history_window(ui);
        self.quote_window(ui.ctx());
        if self.help {
            self.help_window(ui);
        }
        let before = self.projectors.len();
        let (ctx, stage, outputs) = (self.ctx.clone(), &self.live_stage, &self.outputs);
        let video = self.video.as_ref().and_then(|v| v.texture());
        let (mut steps, mut hide) = (0, false);
        self.projectors.retain_mut(|p| {
            let keys = p.show(&ctx, stage, outputs, video, now);
            steps += keys.step;
            hide |= keys.hide;
            keys.keep
        });
        // Les touches tapées dans la projection plein écran (comme dans PowerPoint).
        for _ in 0..steps.unsigned_abs().min(5) {
            self.step(steps.signum());
        }
        if hide {
            self.toggle_hidden();
        }
        if self.projectors.len() < before {
            self.status = "Projection fermée".into();
        }
        if self.live_stage.animating(now) || self.preview_stage.animating(now) {
            ui.ctx().request_repaint();
        }
        self.tick_slideshow(now);
        self.poll_restore();
        self.sync_video();
        self.sync_web();
        // L'horloge de la barre (et celle du retour de scène).
        ui.ctx().request_repaint_after(Duration::from_secs(1));
    }

    /// Les écrans Web suivent le direct : le slide, le suivant, le texte masqué, le déroulé et
    /// l'heure. Rien ne part si rien n'a changé.
    fn sync_web(&mut self) {
        let now = Instant::now();
        // Les sous-titres du slide au direct (redécoupés quand il change).
        if let Some(slide) = self.live.as_ref().map(|l| l.program.slide())
            && self.subtitles.needs_cut(&slide)
        {
            let chunks = self.hub.subtitle_chunks(&slide.text, &self.subtitles.style);
            self.subtitles.cut(&slide, chunks, self.subtitles_backwards);
            self.subtitles_backwards = false;
        }
        let live = self.live.as_ref().map(|l| (l.program.slide(), l.program.title.clone()));
        let text = self.lower_third.current_text(live.as_ref().map(|(s, t)| (s, t.as_str())));
        let lower_third = (self.lower_third.visible(now) && !text.is_empty()).then(|| po_web::Overlay {
            style: self.lower_third.style.clone(),
            text,
            shown: self.lower_third.shown,
            since: self.lower_third.since,
        });
        let subtitle = self.subtitles.current().map(|t| (self.subtitles.style.clone(), t.to_string()));
        let next = self.live.as_ref().and_then(|l| l.program.slide_at(l.program.current() + 1));
        // Le design choisi pour les sorties habille la diffusion (Web, NDI, HDMI) ; un design de slide
        // habille aussi les écrans Web de salle. La projection locale garde le sien.
        let room = match &self.output.look {
            po_web::Look::Slide(design) => design.clone(),
            po_web::Look::Band(_) => self.design.clone(),
        };
        let context = po_web::Context {
            design: room,
            broadcast: self.output.look.clone(),
            next,
            hidden: self.live_stage.hidden(),
            clock: chrono_now(),
            status: self.service_line(),
            lower_third,
            subtitle,
        };
        self.hub.update(self.taken.take(), context);
        let hdmi = self
            .projectors
            .iter()
            .filter(|p| p.kind != po_web::ScreenKind::Room)
            .map(|p| (p.kind, p.render_size()))
            .collect();
        self.outputs.want(Wanted { ndi: self.ndi, hdmi, key: Some(self.hdmi_key), pattern: self.hdmi_pattern });
        self.outputs.upload(&self.ctx);
    }

    /// Le déroulé en une ligne, pour le retour de scène : « Prédication · 12:00 restantes ».
    fn service_line(&self) -> String {
        let now = service::now_seconds();
        let base = service::parse_start_time(&self.playlist.start_time).map(|(h, m)| f64::from(h * 3600 + m * 60));
        let Some(s) = self.tracker.status(now, base) else { return String::new() };
        if s.remaining >= 0.0 {
            format!("{} · {} restantes", s.name, service::format_duration(s.remaining))
        } else {
            format!("{} · {} de dépassement", s.name, service::format_duration(-s.remaining))
        }
    }

    fn library(&mut self, ui: &mut Ui) {
        if self.page == Page::Media {
            let running = self.slideshow_position();
            for action in self.media_view.ui(ui, running) {
                match action {
                    crate::media::MediaAction::Start(medias, title) => self.start_slideshow(medias, &title),
                    crate::media::MediaAction::Stop => self.stop_slideshow(),
                    crate::media::MediaAction::Church(screen) => self.show_church(screen),
                }
            }
            return;
        }
        if self.page == Page::Settings {
            if self.settings_view.families.is_empty() {
                self.settings_view.families = self.designs.families.clone();
                self.settings_view.screens = crate::screens::list().into_iter().map(|s| s.device).collect();
            }
            let current = self.settings.clone();
            for action in self.settings_view.ui(ui, &current) {
                match action {
                    crate::settings_page::SettingsAction::Save(settings) => self.save_settings(*settings),
                    crate::settings_page::SettingsAction::Backup => self.backup_now(),
                    crate::settings_page::SettingsAction::Preflight => {
                        self.settings_view.checks = self.preflight();
                    }
                    crate::settings_page::SettingsAction::OpenFolder(dir) => {
                        let _ = std::process::Command::new("explorer").arg(dir).spawn();
                    }
                    crate::settings_page::SettingsAction::Restore(choice) => self.prepare_restore(choice),
                    crate::settings_page::SettingsAction::CancelRestore => {
                        if let Some(dir) = self.data_dir() {
                            crate::restore::cancel(&dir);
                        }
                        self.settings_view.pending_restore = None;
                        self.status = "Restauration annulée".into();
                    }
                    crate::settings_page::SettingsAction::ShowPhotos(photos) => {
                        let medias = photos
                            .iter()
                            .map(|p| crate::media::Media {
                                name: std::path::Path::new(p)
                                    .file_stem()
                                    .map(|n| n.to_string_lossy().to_string())
                                    .unwrap_or_default(),
                                path: p.clone(),
                                seconds: 0,
                            })
                            .collect();
                        self.start_slideshow(medias, "Photos de l'église");
                    }
                    crate::settings_page::SettingsAction::Quit => {
                        ui.ctx().send_viewport_cmd(egui::ViewportCommand::Close);
                    }
                }
            }
            return;
        }
        if self.page == Page::Designs {
            let sample = self
                .preview
                .as_ref()
                .or(self.live.as_ref())
                .map(|s| s.program.slide())
                .unwrap_or_else(crate::designs::sample_slide);
            let ndi = (self.ndi, self.outputs.ndi_status(), self.outputs.ndi_receivers());
            let hdmi = self.hdmi_outputs();
            let output = self.output.clone();
            let actions = self.designs.ui(ui, &mut self.lower_third, &mut self.subtitles, ndi, hdmi, &sample, &output);
            for action in actions {
                self.apply_design(action);
            }
            return;
        }
        if self.page == Page::Playlist {
            let Some(db) = self.db.as_ref() else { return };
            let marks = self.playlist_marks();
            let undo = self.playlists.undo.available();
            let actions = self.playlist.ui(ui, db, marks, &self.tracker, undo);
            if !actions.is_empty() {
                self.apply_playlist(actions);
            } else if self.tracker_folder != self.playlist.folder {
                self.sync_tracker();
            }
            return;
        }
        let Some(db) = self.db.as_ref() else { return };
        let marks = self.marks();
        let search = self.search.as_ref();
        let action = match self.page {
            Page::Sermons => self.sermons.ui(ui, db, &marks, search),
            Page::Bible => self.bible.ui(ui, db, &marks, search),
            Page::Hymns => self.hymns.ui(ui, db, &marks, search, self.split.hymn_repeat_chorus),
            Page::Expose => self.expose.ui(ui, db, &marks, search),
            Page::Books => self.books.ui(ui, db, &marks, search),
            Page::Playlist | Page::Designs | Page::Settings | Page::Media => None,
        };
        if let Some(action) = action {
            self.apply(action);
        }
        // L'éditeur de cantiques écrit dans la base.
        if let Some(request) = self.hymns.request.take()
            && let Some(db) = self.db.as_mut()
        {
            match request {
                crate::library::hymns::HymnRequest::Save(draft) => match draft.check() {
                    Ok(stanzas) => {
                        let saved = db.save_hymn(draft.id, &draft.title, &stanzas, draft.number(), &draft.language);
                        match saved {
                            Ok(id) => {
                                self.hymns.saved(db, id);
                                self.status = format!("Cantique « {} » enregistré", draft.title.trim());
                            }
                            Err(e) => self.hymns.editor_error = Some(format!("Enregistrement impossible : {e}")),
                        }
                    }
                    Err(message) => self.hymns.editor_error = Some(message.into()),
                },
                crate::library::hymns::HymnRequest::Delete(id) => match db.delete_hymn(id) {
                    Ok(()) => {
                        self.hymns.deleted(db);
                        self.status = "Cantique supprimé".into();
                    }
                    Err(e) => self.status = format!("Suppression impossible : {e}"),
                },
            }
        }
    }

    fn command_bar(&mut self, ui: &mut Ui) {
        ui.horizontal_centered(|ui| {
            ui.label(RichText::new("Project-On").font(bold(17.0)).color(TEXT));
            widgets::chip(ui, if cfg!(feature = "bascule") { "3.0" } else { "3.0 bêta" }, ACCENT);
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
                if let Some(web) = self.web.as_mut() {
                    web.button(ui);
                }
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
        let designs = self.page == Page::Designs;
        let (rect, r) = widgets::list_row(ui, designs, 38.0, Page::Designs.label());
        ui.add_space(2.0);
        icons::paint(
            ui.painter(),
            egui::Rect::from_center_size(pos2(rect.min.x + 22.0, rect.center().y), vec2(17.0, 17.0)),
            Icon::SwatchBook,
            if designs { ACCENT } else { MUTED },
        );
        widgets::paint_text(
            ui,
            pos2(rect.min.x + 40.0, rect.center().y),
            Align2::LEFT_CENTER,
            Page::Designs.label(),
            medium(13.5),
            if designs { TEXT } else { MUTED },
            rect.width() - 50.0,
        );
        if r.on_hover_text("Designs, lower thirds, sous-titres, NDI et HDMI (Ctrl+7)").clicked() {
            self.page = Page::Designs;
        }
        let settings = self.page == Page::Settings;
        let (rect, r) = widgets::list_row(ui, settings, 38.0, Page::Settings.label());
        ui.add_space(2.0);
        icons::paint(
            ui.painter(),
            egui::Rect::from_center_size(pos2(rect.min.x + 22.0, rect.center().y), vec2(17.0, 17.0)),
            Icon::Settings,
            if settings { ACCENT } else { MUTED },
        );
        widgets::paint_text(
            ui,
            pos2(rect.min.x + 40.0, rect.center().y),
            Align2::LEFT_CENTER,
            Page::Settings.label(),
            medium(13.5),
            if settings { TEXT } else { MUTED },
            rect.width() - 50.0,
        );
        if r.on_hover_text("Réglages, sauvegardes, contrôle avant culte (Ctrl+8)").clicked() {
            self.page = Page::Settings;
        }
        let media = self.page == Page::Media;
        let (rect, r) = widgets::list_row(ui, media, 38.0, Page::Media.label());
        ui.add_space(2.0);
        icons::paint(
            ui.painter(),
            egui::Rect::from_center_size(pos2(rect.min.x + 22.0, rect.center().y), vec2(17.0, 17.0)),
            Icon::Image,
            if media { ACCENT } else { MUTED },
        );
        widgets::paint_text(
            ui,
            pos2(rect.min.x + 40.0, rect.center().y),
            Align2::LEFT_CENTER,
            Page::Media.label(),
            medium(13.5),
            if media { TEXT } else { MUTED },
            rect.width() - 50.0,
        );
        if r.on_hover_text("Le diaporama d'un dossier d'images (Ctrl+9)").clicked() {
            self.page = Page::Media;
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
        if let Some(texture) = self.video.as_ref().and_then(|v| v.texture()) {
            crate::video::paint(ui.painter(), rect, texture);
        }
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
        self.video_controls(ui);
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

/// Le premier lancement : vos données de la 2.8, ou la base fournie avec Project-On.
fn choose_origin(ui: &mut Ui) -> Option<crate::data::Origin> {
    use crate::data::Origin;
    let mut chosen = None;
    egui::CentralPanel::default().frame(egui::Frame::NONE.fill(BG)).show(ui, |ui| {
        ui.add_space(ui.available_height() / 4.0);
        ui.vertical_centered(|ui| {
            ui.label(RichText::new("Bienvenue dans Project-On 3 (bêta)").font(semibold(22.0)).color(TEXT));
            ui.add_space(6.0);
            ui.label(
                RichText::new("Avec quelle base voulez-vous essayer la bêta ? Elle travaille sur une copie : la 2.8 n'est jamais modifiée.")
                    .font(regular(13.5))
                    .color(MUTED),
            );
            ui.add_space(24.0);
            let choices = [
                (
                    Origin::Legacy,
                    "Mes données de Project-On 2.8",
                    "Vos playlists, vos cantiques ajoutés, vos Bibles importées et vos réglages.",
                ),
                (
                    Origin::Bundled,
                    "La base fournie avec Project-On",
                    "Les Bibles, cantiques, prédications et livres livrés avec l'installateur, sans vos playlists. Vos réglages de projection sont repris.",
                ),
            ];
            for (origin, title, detail) in choices {
                let r = widgets::button_sized(ui, 520.0, Size::Hero, None, title, Tone::Primary(ACCENT), true);
                if r.clicked() {
                    chosen = Some(origin);
                }
                ui.add_space(4.0);
                ui.label(RichText::new(detail).font(regular(12.0)).color(FAINT));
                ui.add_space(18.0);
            }
        });
    });
    chosen
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

/// La date locale « 2026-11-11 ».
fn today() -> String {
    #[cfg(windows)]
    {
        use windows::Win32::System::SystemInformation::GetLocalTime;
        // SAFETY : GetLocalTime remplit une structure qu'on lui donne, sans autre effet.
        #[allow(unsafe_code)]
        let t = unsafe { GetLocalTime() };
        format!("{:04}-{:02}-{:02}", t.wYear, t.wMonth, t.wDay)
    }
    #[cfg(not(windows))]
    {
        "1970-01-01".into()
    }
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

fn plural(n: usize) -> &'static str {
    if n > 1 { "s" } else { "" }
}
