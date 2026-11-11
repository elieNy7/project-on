//! L'éditeur de cantiques, hors écran (aucune fenêtre), sur une base d'essai : créer un cantique
//! avec son refrain, le modifier, le supprimer après confirmation.

// Un essai qui échoue s'arrête : `unwrap` y est permis, aussi dans les fonctions d'aide.
#![allow(clippy::unwrap_used)]

use std::path::Path;

use egui_kittest::Harness;
use egui_kittest::kittest::Queryable;
use po_db::{Database, InitOptions};
use po_settings::Settings;
use project_on::{Boot, Config};

fn harness(dir: &Path) -> Harness<'static, Boot> {
    let path = dir.join("project_on.db");
    Database::open_and_initialize(&path, &InitOptions::default()).unwrap();
    let config = Config {
        fonts_dir: po_layout::bundled_fonts_dir(),
        locations: None,
        database: Some(path),
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
    h
}

fn type_into(h: &mut Harness<'static, Boot>, label: &str, text: &str) {
    h.get_by_label(label).click();
    h.run_ok();
    h.get_by_label(label).type_text(text);
    h.run_ok();
}

#[test]
fn a_hymn_is_created_with_its_chorus_then_modified_then_deleted() {
    let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
    std::fs::create_dir_all(&base).unwrap();
    let dir = tempfile::tempdir_in(base).unwrap();
    let mut h = harness(dir.path());
    h.get_by_label("Cantiques").click();
    h.run_ok();

    // Nouveau cantique : titre, numéro, deux strophes et un refrain.
    h.get_by_label("Nouveau cantique").click();
    h.run_ok();
    type_into(&mut h, "Titre du cantique", "Gloire à l'Agneau");
    type_into(&mut h, "Numéro du cantique", "777");
    type_into(
        &mut h,
        "Paroles du cantique",
        "Il est venu\nPour nous sauver\n\nRefrain\nGloire, gloire\n\nIl reviendra",
    );
    h.get_by_label_contains("Une ligne vide sépare");
    h.get_by_label("Refrain · 1 ligne(s)");
    h.get_by_label("Enregistrer").click();
    h.run_ok();
    let app = h.state_mut().app();
    assert!(app.hymns.editor.is_none(), "l'éditeur se ferme : {:?}", app.hymns.editor_error);
    let db = app.database().unwrap();
    let id = app.hymns.selected_id().expect("le cantique enregistré est choisi");
    let hymn = db.hymn(id).unwrap().unwrap();
    assert_eq!((hymn.title.as_str(), hymn.number.as_deref()), ("Gloire à l'Agneau", Some("777")));
    let stanzas = db.stanzas(id).unwrap();
    let labels: Vec<_> = stanzas.iter().map(|s| (s.label.as_str(), s.is_chorus)).collect();
    assert_eq!(labels, [("Strophe 1", false), ("Refrain", true), ("Strophe 2", false)]);

    // Modifier : le titre change, les strophes restent.
    h.get_by_label("Modifier").click();
    h.run_ok();
    type_into(&mut h, "Titre du cantique", " (nouvelle version)");
    h.get_by_label("Enregistrer").click();
    h.run_ok();
    let app = h.state_mut().app();
    let db = app.database().unwrap();
    assert_eq!(db.hymn(id).unwrap().unwrap().title, "Gloire à l'Agneau (nouvelle version)");
    assert_eq!(db.stanzas(id).unwrap().len(), 3);

    // Un cantique sans paroles n'est pas enregistré.
    h.get_by_label("Nouveau cantique").click();
    h.run_ok();
    type_into(&mut h, "Titre du cantique", "Vide");
    h.get_by_label("Enregistrer").click();
    h.run_ok();
    assert_eq!(h.state_mut().app().hymns.editor_error.as_deref(), Some("Saisissez au moins une strophe."));
    h.state_mut().app().hymns.editor = None;
    h.run_ok();

    // Supprimer, après confirmation.
    h.get_by_label("Supprimer").click();
    h.run_ok();
    h.get_by_label("Supprimer définitivement").click();
    h.run_ok();
    let app = h.state_mut().app();
    assert!(app.database().unwrap().hymn(id).unwrap().is_none());
    assert!(app.hymns.selected_id().is_none());
}
