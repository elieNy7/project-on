//! Project-On 3.0 bêta : la régie.
//!
//! La bêta travaille sur ses propres données, dans `%APPDATA%\Project-On 3 (bêta)` : au premier
//! lancement, une COPIE de celles de la 2.x ou de la base fournie avec l'installateur. La 2.8 et ses
//! données ne sont jamais modifiées. Le serveur Web écoute sur 127.0.0.1:8090 (la 2.8 garde 8080).

#![windows_subsystem = "windows"]

use std::path::PathBuf;
use std::sync::Arc;

use project_on::data::Locations;
use project_on::{App, Config};

/// Le dossier de l'exécutable.
fn exe_dir() -> Option<PathBuf> {
    std::env::current_exe().ok().and_then(|exe| exe.parent().map(PathBuf::from))
}

/// `assets/fonts` à côté de l'exécutable, sinon celui du dépôt (développement).
fn fonts_dir() -> PathBuf {
    exe_dir()
        .map(|d| d.join("assets").join("fonts"))
        .filter(|d| d.is_dir())
        .unwrap_or_else(po_layout::bundled_fonts_dir)
}

/// La base fournie avec l'installateur (`data\project_on.db` à côté de l'exécutable).
fn bundled_database() -> Option<PathBuf> {
    exe_dir().map(|d| d.join("data").join("project_on.db")).filter(|p| p.is_file())
}

/// Un message à l'écran quand la régie ne peut pas s'ouvrir (sans lui, rien ne s'afficherait).
#[cfg(windows)]
fn alert(message: &str) {
    use windows::Win32::UI::WindowsAndMessaging::{MB_ICONERROR, MB_OK, MessageBoxW};
    use windows::core::HSTRING;
    // SAFETY : une boîte de message modale, avec deux chaînes valides.
    #[allow(unsafe_code)]
    unsafe {
        MessageBoxW(None, &HSTRING::from(message), &HSTRING::from("Project-On 3 (bêta)"), MB_OK | MB_ICONERROR);
    }
}

#[cfg(not(windows))]
fn alert(message: &str) {
    eprintln!("{message}");
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

fn main() {
    let fonts = fonts_dir();
    let locations = Locations::current().ok().map(|l| l.with_bundled(bundled_database()));
    if let Some(l) = &locations {
        po_core::journal::install(&l.beta.logs());
        po_core::journal::line(&format!("Project-On {} : démarrage", env!("CARGO_PKG_VERSION")));
    }
    // Une panique laisse sa trace dans le journal (l'application n'a pas de console).
    std::panic::set_hook(Box::new(|info| {
        po_core::journal::line(&format!("ERREUR (panique) : {info}"));
    }));
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
        wgpu_options: project_on::gpu::configuration(),
        ..Default::default()
    };
    let result = eframe::run_native(
        "Project-On 3 bêta",
        options,
        Box::new(move |cc| {
            if let Some(state) = &cc.wgpu_render_state {
                let info = state.adapter.get_info();
                po_core::journal::line(&format!("carte graphique : {} ({:?})", info.name, info.backend));
            }
            let config = Config { fonts_dir: fonts, locations, database: None, settings, windowed_projection: false };
            let app = App::new(&cc.egui_ctx, config);
            Ok(Box::new(Shell { app, hub, _server: server }))
        }),
    );
    if let Err(e) = result {
        po_core::journal::line(&format!("ERREUR au démarrage : {e}"));
        alert(&format!(
            "Project-On 3 (bêta) ne peut pas s'ouvrir :\n\n{e}\n\nMettez à jour le pilote de la carte graphique, puis réessayez."
        ));
    }
}
