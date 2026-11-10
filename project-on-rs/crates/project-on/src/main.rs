//! Project-On 3.0 bêta : la régie.
//!
//! La bêta travaille sur une COPIE des données de la 2.x, faite au premier lancement dans
//! `%APPDATA%\Project-On 3 (bêta)` ; la 2.8 et ses données ne sont jamais modifiées. Le serveur Web
//! écoute sur 127.0.0.1:8090 (la 2.8 garde le port 8080).

#![windows_subsystem = "windows"]

use std::path::PathBuf;
use std::sync::Arc;

use project_on::data::Locations;
use project_on::{App, Config};

/// `assets/fonts` à côté de l'exécutable, sinon celui du dépôt (développement).
fn fonts_dir() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(|d| d.join("assets").join("fonts")))
        .filter(|d| d.is_dir())
        .unwrap_or_else(po_layout::bundled_fonts_dir)
}

struct Shell {
    app: App,
    hub: Arc<po_web::Hub>,
    _server: Option<po_web::Server>,
}

impl eframe::App for Shell {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        self.app.web_screens = self.hub.connected();
        self.app.ui(ui);
        if let Some(slide) = self.app.taken.take() {
            self.hub.publish(slide, self.app.design.clone());
        }
    }
}

fn main() -> eframe::Result {
    let fonts = fonts_dir();
    let locations = Locations::current().ok();
    if let Some(l) = &locations {
        po_core::journal::install(&l.beta.logs());
        po_core::journal::line("Project-On 3.0 bêta : démarrage");
    }
    // Les réglages de la copie de la bêta ; au tout premier lancement, ceux de la 2.x (lus sans
    // rien écrire) en attendant la copie.
    let settings = locations
        .as_ref()
        .map(|l| {
            let own = l.beta.settings();
            let path = if own.is_file() { own } else { l.legacy.as_ref().map(|x| x.settings()).unwrap_or(own) };
            po_settings::Settings::load(&path).settings
        })
        .unwrap_or_default();
    let hub = po_web::Hub::new(project_on::worker::fonts_from(&fonts));
    let server = po_web::start(hub.clone(), ([127, 0, 0, 1], 8090).into()).ok();
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("Project-On 3.0 bêta")
            .with_inner_size([1600.0, 940.0])
            .with_min_inner_size([1200.0, 700.0])
            .with_maximized(true),
        renderer: eframe::Renderer::Wgpu,
        ..Default::default()
    };
    eframe::run_native(
        "Project-On 3 bêta",
        options,
        Box::new(move |cc| {
            let config = Config { fonts_dir: fonts, locations, database: None, settings, windowed_projection: false };
            let app = App::new(&cc.egui_ctx, config);
            Ok(Box::new(Shell { app, hub, _server: server }))
        }),
    )
}
