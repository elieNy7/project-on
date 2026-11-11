//! « Importer un PDF » dans la page Cantiques, hors écran (aucune fenêtre) : le recueil
//! « Pene Na Yo » du dépôt est lu dans un fil à part, ses cantiques importés avec un préfixe, puis
//! importés à nouveau sans doublon.

#![allow(clippy::unwrap_used)]

use std::path::Path;
use std::time::{Duration, Instant};

use egui_kittest::Harness;
use egui_kittest::kittest::Queryable;
use po_db::{Database, InitOptions};
use po_settings::Settings;
use project_on::{App, Boot, Config};

fn until(h: &mut Harness<'static, Boot>, done: impl Fn(&App) -> bool) {
    let start = Instant::now();
    while start.elapsed() < Duration::from_secs(120) {
        h.step();
        if h.state().get().is_some_and(&done) {
            return;
        }
        std::thread::sleep(Duration::from_millis(5));
    }
    panic!("délai dépassé");
}

#[test]
fn a_hymnal_pdf_is_imported_once() {
    let pdf = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../cantiques/Cantique Pene Na Yo.pdf");
    if !pdf.is_file() {
        return;
    }
    let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
    std::fs::create_dir_all(&base).unwrap();
    let dir = tempfile::tempdir_in(base).unwrap();
    let db = dir.path().join("project_on.db");
    Database::open_and_initialize(&db, &InitOptions::default()).unwrap();
    let config = Config {
        fonts_dir: po_layout::bundled_fonts_dir(),
        locations: None,
        database: Some(db),
        settings: Settings::default(),
        windowed_projection: true,
        web_port: None,
    };
    let mut h = Harness::builder()
        .with_size([1600.0, 940.0])
        .with_accessibility_check(false)
        .wgpu()
        .build_ui_state(|ui, boot: &mut Boot| boot.ui(ui), Boot::new(config));
    h.run_ok();
    h.get_by_label("Cantiques").click();
    h.run_ok();
    h.get_by_label("Importer un PDF…");
    let before = h.state_mut().app().database().unwrap().list_hymns(None, None, None).unwrap().len();

    // (La boîte de choix du fichier ne s'ouvre pas dans un essai : le fichier est donné.)
    h.state_mut().app().pdf_import.read(pdf);
    until(&mut h, |a| !a.pdf_import.busy());
    assert_eq!(h.state_mut().app().pdf_import.found().len(), 150);
    h.run_ok();
    h.get_by_label("150 cantique(s) trouvé(s)");
    h.get_by_label("Importer la sélection (150)").click();
    h.run_ok();
    until(&mut h, |a| !a.pdf_import.busy());
    let app = h.state_mut().app();
    assert_eq!(app.pdf_import.message, "150 cantique(s) importé(s).");
    let hymns = app.database().unwrap().list_hymns(None, None, None).unwrap();
    assert_eq!(hymns.len(), before + 150);
    assert!(hymns.iter().any(|x| x.title.starts_with("CA-")), "le préfixe tiré du nom du fichier");

    // Une seconde fois : rien n'est ajouté.
    h.get_by_label("Importer la sélection (150)").click();
    h.run_ok();
    until(&mut h, |a| !a.pdf_import.busy());
    let app = h.state_mut().app();
    assert_eq!(app.pdf_import.message, "0 cantique(s) importé(s), 150 déjà présent(s).");
}
