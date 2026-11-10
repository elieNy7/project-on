//! Project-On 3.0 (phase 2) : la coque de validation dans une vraie fenêtre.
//!
//! La base est ouverte en LECTURE SEULE : ce prototype n'écrit jamais dans les données. Le serveur
//! Web écoute sur 127.0.0.1:8090 (la 2.8 garde le port 8080).

#![windows_subsystem = "windows"]

use std::path::PathBuf;
use std::sync::Arc;

use po_design::RoomDesign;
use po_layout::Fonts;
use project_on::{Shell, theme};

/// La base de la 2.x : `PROJECT_ON_DB`, sinon `%APPDATA%\Project-On\data\project_on.db`.
fn database_path() -> Option<PathBuf> {
    if let Some(path) = std::env::var_os("PROJECT_ON_DB") {
        return Some(PathBuf::from(path));
    }
    std::env::var_os("APPDATA").map(|d| PathBuf::from(d).join("Project-On").join("data").join("project_on.db"))
}

/// `assets/fonts` à côté de l'exécutable, sinon celui du dépôt (développement).
fn fonts_dir() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(|d| d.join("assets").join("fonts")))
        .filter(|d| d.is_dir())
        .unwrap_or_else(po_layout::bundled_fonts_dir)
}

/// Toutes les polices de Project-On : celle des réglages et celles de l'identification.
fn projection_fonts(dir: &std::path::Path) -> Fonts {
    Fonts::from_dirs(&[dir])
}

/// Le design de la salle lu dans les réglages de la 2.x (lecture seule).
fn room_design() -> RoomDesign {
    let path =
        std::env::var_os("APPDATA").map(|d| PathBuf::from(d).join("Project-On").join("data").join("settings.json"));
    match path {
        Some(path) => RoomDesign::from_projection(&po_settings::Settings::load(&path).settings.projection),
        None => RoomDesign::default(),
    }
}

struct App {
    shell: Shell,
    hub: Arc<po_web::Hub>,
    _server: Option<po_web::Server>,
}

impl eframe::App for App {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        self.shell.web_screens = self.hub.connected();
        self.shell.ui(ui);
        if let Some(slide) = self.shell.taken.take() {
            self.hub.publish(slide, self.shell.design.clone());
        }
        // Le nombre d'écrans Web connectés se rafraîchit même sans clic.
        ui.ctx().request_repaint_after(std::time::Duration::from_secs(1));
    }
}

fn main() -> eframe::Result {
    let fonts = fonts_dir();
    let db = database_path().and_then(|p| po_db::Database::open(&p, po_db::Mode::ReadOnly).ok());
    let hub = po_web::Hub::new(projection_fonts(&fonts));
    let server = po_web::start(hub.clone(), ([127, 0, 0, 1], 8090).into()).ok();
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("Project-On 3.0 — phase 2")
            .with_inner_size([1500.0, 900.0])
            .with_min_inner_size([1100.0, 650.0]),
        renderer: eframe::Renderer::Wgpu,
        ..Default::default()
    };
    eframe::run_native(
        "Project-On",
        options,
        Box::new(move |cc| {
            theme::install(&cc.egui_ctx, &fonts);
            let mut shell = Shell::new(db, projection_fonts(&fonts));
            shell.design = room_design();
            Ok(Box::new(App { shell, hub, _server: server }))
        }),
    )
}
