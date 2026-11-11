//! « Gérer les Bibles » depuis la page Bible, hors écran (aucune fenêtre) : installer une Bible
//! fournie (dans un fil à part), la voir dans le choix des traductions, la supprimer.

// Un essai qui échoue s'arrête : `unwrap` y est permis, aussi dans les fonctions d'aide.
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
    while start.elapsed() < Duration::from_secs(60) {
        h.step();
        if h.state().get().is_some_and(&done) {
            return;
        }
        std::thread::sleep(Duration::from_millis(5));
    }
    panic!("délai dépassé");
}

#[test]
fn a_bundled_bible_is_installed_then_removed() {
    let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
    std::fs::create_dir_all(&base).unwrap();
    let dir = tempfile::tempdir_in(base).unwrap();
    let db = dir.path().join("project_on.db");
    let bibles = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../bible_json");
    Database::open_and_initialize(&db, &InitOptions { bible_json_dir: Some(bibles) }).unwrap();
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
    h.get_by_label("Bible").click();
    h.run_ok();
    h.get_by_label("Gérer les Bibles…").click();
    h.run_ok();
    h.get_by_label("INSTALLÉES");
    h.get_by_label("FOURNIES AVEC PROJECT-ON");
    let count = |a: &App| a.database().unwrap().installed_bibles().unwrap().len();
    let before = count(h.state_mut().app());

    // La King James (fournie) : installée dans un fil à part.
    h.get_by_label("CATALOGUE EN LIGNE (DOMAINE PUBLIC)");
    let kjv = h.get_all_by_label("Installer").count();
    assert!(kjv > 0);
    h.get_all_by_label("Installer").next().unwrap().click();
    h.run_ok();
    until(&mut h, |a| !a.bible_manager.busy());
    let app = h.state_mut().app();
    assert!(app.bible_manager.message.contains("installée"), "{}", app.bible_manager.message);
    assert_eq!(count(app), before + 1);

    // Supprimée (avec confirmation) : elle ne revient pas toute seule.
    let added = {
        let app = h.state_mut().app();
        let bundled: Vec<String> = project_on::bible_manager::bundled_files().into_iter().map(|(m, _)| m).collect();
        app.database().unwrap().installed_bibles().unwrap().into_iter().find(|b| bundled.contains(&b.module)).unwrap()
    };
    let row = h
        .state_mut()
        .app()
        .database()
        .unwrap()
        .installed_bibles()
        .unwrap()
        .iter()
        .position(|b| b.module == added.module)
        .unwrap();
    h.get_all_by_label("Supprimer").nth(row).unwrap().click();
    h.run_ok();
    h.get_all_by_label("Supprimer").last().unwrap().click();
    h.run_ok();
    let app = h.state_mut().app();
    assert_eq!(count(app), before);
    assert!(app.database().unwrap().removed_bibles().contains(&added.module));
}
