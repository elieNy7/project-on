//! Les écrans Web depuis la régie (hors écran, aucune fenêtre) : ce qui part au direct, le slide
//! suivant, le texte masqué, et le bouton « Web » avec ses adresses. Le serveur écoute ce poste
//! seulement, sur un port libre.

// Un essai qui échoue s'arrête : `unwrap` y est permis, aussi dans les fonctions d'aide.
#![allow(clippy::unwrap_used)]

use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::OnceLock;
use std::time::{Duration, Instant};

use egui::Key;
use egui_kittest::Harness;
use egui_kittest::kittest::Queryable;
use po_db::{Database, InitOptions};
use po_settings::Settings;
use project_on::{App, Boot, Config};

fn fixture() -> PathBuf {
    static PATH: OnceLock<(tempfile::TempDir, PathBuf)> = OnceLock::new();
    PATH.get_or_init(|| {
        let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
        std::fs::create_dir_all(&base).unwrap();
        let dir = tempfile::tempdir_in(base).unwrap();
        let path = dir.path().join("project_on.db");
        let bibles = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../bible_json");
        Database::open_and_initialize(&path, &InitOptions { bible_json_dir: Some(bibles) }).unwrap();
        (dir, path)
    })
    .1
    .clone()
}

fn harness() -> Harness<'static, Boot> {
    let config = Config {
        fonts_dir: po_layout::bundled_fonts_dir(),
        locations: None,
        database: Some(fixture()),
        settings: Settings::default(),
        windowed_projection: true,
        web_port: Some(0),
    };
    let mut h = Harness::builder()
        .with_size([1600.0, 940.0])
        .with_accessibility_check(false)
        .wgpu()
        .build_ui_state(|ui, boot: &mut Boot| boot.ui(ui), Boot::new(config));
    h.run_ok();
    h
}

fn until(h: &mut Harness<'static, Boot>, done: impl Fn(&App) -> bool) {
    let start = Instant::now();
    while start.elapsed() < Duration::from_secs(20) {
        h.step();
        if h.state().get().is_some_and(&done) {
            return;
        }
        std::thread::sleep(Duration::from_millis(2));
    }
    panic!("délai dépassé");
}

/// Une page du serveur Web de la régie, comme la demanderait un navigateur.
fn get(app: &App, path: &str) -> String {
    let addr = app.web.as_ref().unwrap().addr().unwrap();
    let mut s = std::net::TcpStream::connect(addr).unwrap();
    s.write_all(format!("GET {path} HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n").as_bytes()).unwrap();
    let mut out = String::new();
    s.read_to_string(&mut out).unwrap();
    out
}

#[test]
fn the_live_reaches_the_web_screens_with_the_next_slide_and_the_hidden_text() {
    let mut h = harness();
    h.get_by_label("Bible").click();
    h.run_ok();
    h.get_by_label_contains("Référence").click();
    h.run_ok();
    h.get_by_label_contains("Référence").type_text("Jean 3:16");
    h.run_ok();
    h.key_press(Key::Enter);
    h.run_ok();
    h.state_mut().app().take();
    h.ctx.memory_mut(|m| m.stop_text_input());
    until(&mut h, |a| a.web.as_ref().unwrap().hub.program().seq == 1);

    // Le slide au direct et le suivant (pour le retour de scène).
    let app = h.state_mut().app();
    let program = app.web.as_ref().unwrap().hub.program();
    assert!(program.slide.reference.starts_with("Jean 3:16"), "{}", program.slide.reference);
    assert!(program.context.next.as_ref().unwrap().reference.starts_with("Jean 3:17"));
    assert!(!program.context.clock.is_empty() || cfg!(not(windows)));
    // L'adresse de la 2.8 donne le même slide.
    let json = get(app, "/slide.json");
    assert!(json.contains("\"reference\":\"Jean 3:16"), "{json}");

    // Slide suivant : nouveau numéro, nouveau « suivant ».
    h.key_press(Key::PageDown);
    until(&mut h, |a| a.web.as_ref().unwrap().hub.program().seq == 2);
    let program = h.state_mut().app().web.as_ref().unwrap().hub.program();
    assert!(program.slide.reference.starts_with("Jean 3:17"));
    assert!(program.context.next.as_ref().unwrap().reference.starts_with("Jean 3:18"));

    // Texte masqué : les écrans le savent, sans nouveau slide.
    h.state_mut().app().toggle_hidden();
    until(&mut h, |a| a.web.as_ref().unwrap().hub.program().context.hidden);
    assert_eq!(h.state_mut().app().web.as_ref().unwrap().hub.program().seq, 2);
}

#[test]
fn the_web_button_lists_the_screen_addresses() {
    let mut h = harness();
    let port = h.state_mut().app().web.as_ref().unwrap().addr().unwrap().port();
    h.get_by_label("Web").click();
    h.run_ok();
    h.get_by_label_contains("ADRESSES SUR CE POSTE");
    h.get_by_label("Aucun écran ouvert.");
    for screen in ["salle", "diffusion", "sous-titres", "retour"] {
        h.get_by_label(&format!("http://127.0.0.1:{port}/ecran/{screen}"));
    }
    h.get_by_label_contains("Ouvrir aux appareils du réseau");
    // Une page d'écran ouverte ailleurs (ici par une simple requête) : le serveur répond.
    let page = get(h.state_mut().app(), "/ecran/diffusion");
    assert!(page.starts_with("HTTP/1.1 200") && page.contains("transparent"));
    // L'ancienne adresse d'OBS mène à la diffusion.
    assert!(get(h.state_mut().app(), "/obs").contains("/ecran/diffusion"));
}
