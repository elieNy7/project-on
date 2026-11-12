//! Les écrans de l'église, hors écran (aucune fenêtre) : Ctrl+Maj+W, P et R projettent l'accueil,
//! l'orateur du jour et les réseaux sociaux (rendus en image, comme la 2.8), et le profil se règle
//! dans Réglages.

// Un essai qui échoue s'arrête : `unwrap` y est permis, aussi dans les fonctions d'aide.
#![allow(clippy::unwrap_used)]

use std::path::Path;

use egui::{Key, Modifiers};
use egui_kittest::Harness;
use egui_kittest::kittest::Queryable;
use po_db::{Database, InitOptions};
use po_settings::Settings;
use project_on::library::Origin;
use project_on::{App, Boot, Config};
use serde_json::json;

fn live_image(app: &App) -> String {
    let live = app.live.as_ref().unwrap();
    assert_eq!(live.origin, Origin::Church);
    live.program.slide().background.unwrap()
}

#[test]
fn the_church_screens_are_projected_and_the_profile_is_set_in_the_settings() {
    let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
    std::fs::create_dir_all(&base).unwrap();
    let dir = tempfile::tempdir_in(base).unwrap();
    let db = dir.path().join("project_on.db");
    Database::open_and_initialize(&db, &InitOptions::default()).unwrap();
    let mut settings = Settings::default();
    settings.other.insert(
        "church".into(),
        json!({
            "name": "OUVRIERS DE LA ONZIÈME HEURE", "motto": "Tenez-vous tranquilles",
            "service_times": "Dimanche : 9H30", "socials": {"youtube": "@Eglise", "whatsapp": "+243812436993"},
            "qr_target": "youtube", "pastor_title": "Révérend", "pastor_name": "Joseph Nyembo",
            "quote_style": "minimal"
        }),
    );
    let config = Config {
        fonts_dir: po_layout::bundled_fonts_dir(),
        locations: None,
        database: Some(db),
        settings,
        windowed_projection: true,
        web_port: None,
    };
    let mut h = Harness::builder()
        .with_size([1600.0, 940.0])
        .with_accessibility_check(false)
        .wgpu()
        .build_ui_state(|ui, boot: &mut Boot| boot.ui(ui), Boot::new(config));
    h.run_ok();

    // Ctrl+Maj+W : l'accueil, une image PNG au direct, nommée du nom de l'église.
    h.key_press_modifiers(Modifiers::COMMAND | Modifiers::SHIFT, Key::W);
    h.run_ok();
    let welcome = live_image(h.state_mut().app());
    assert!(welcome.contains("accueil-") && welcome.ends_with(".png"), "{welcome}");
    let png = std::fs::read(&welcome).unwrap();
    assert_eq!(&png[1..4], b"PNG");
    assert_eq!(h.state_mut().app().live.as_ref().unwrap().program.title, "OUVRIERS DE LA ONZIÈME HEURE");

    // Ctrl+Maj+R puis Ctrl+Maj+P.
    h.key_press_modifiers(Modifiers::COMMAND | Modifiers::SHIFT, Key::R);
    h.run_ok();
    assert!(live_image(h.state_mut().app()).contains("reseaux-sociaux-"));
    h.key_press_modifiers(Modifiers::COMMAND | Modifiers::SHIFT, Key::P);
    h.run_ok();
    assert!(live_image(h.state_mut().app()).contains("orateur-du-jour-"));
    assert_eq!(h.state_mut().app().live.as_ref().unwrap().program.title, "Révérend Joseph Nyembo");

    // Réglages → Profil de l'église : l'orateur invité, enregistré au format de la 2.x.
    h.get_by_label("Réglages").click();
    h.run_ok();
    h.get_by_label("Réglages · Église").click();
    h.run_ok();
    // La section est loin dans la page : on la fait venir à l'écran.
    h.get_by_label("Champ : Orateur invité : nom (vide : le pasteur)").scroll_to_me();
    h.run_ok();
    h.get_by_label("Champ : Orateur invité : nom (vide : le pasteur)").click();
    h.run_ok();
    h.get_by_label("Champ : Orateur invité : nom (vide : le pasteur)").type_text("Frère Paul");
    h.run_ok();
    h.ctx.memory_mut(|m| m.stop_text_input());
    h.get_by_label("Enregistrer").scroll_to_me();
    h.run_ok();
    h.get_by_label("Enregistrer").click();
    h.run_ok();
    let church = h.state_mut().app().settings.other["church"].clone();
    assert_eq!(church["speaker_name"], "Frère Paul");
    assert_eq!(church["quote_style"], "minimal", "les champs de la 2.x sont gardés");
    // L'écran de l'orateur montre maintenant l'invité ; l'image a changé de nom.
    h.state_mut().app().show_church(project_on::media::ChurchScreen::Speaker);
    h.run_ok();
    assert_eq!(h.state_mut().app().live.as_ref().unwrap().program.title, "Frère Paul");
}

#[test]
fn the_live_verse_becomes_a_quote_image_to_copy_or_project() {
    let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
    std::fs::create_dir_all(&base).unwrap();
    let dir = tempfile::tempdir_in(base).unwrap();
    let db = dir.path().join("project_on.db");
    let bibles = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../bible_json");
    Database::open_and_initialize(&db, &InitOptions { bible_json_dir: Some(bibles) }).unwrap();
    let mut settings = Settings::default();
    settings.other.insert("church".into(), json!({ "name": "OUVRIERS DE LA ONZIÈME HEURE", "quote_style": "minimal" }));
    let config = Config {
        fonts_dir: po_layout::bundled_fonts_dir(),
        locations: None,
        database: Some(db),
        settings,
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
    h.get_by_label_contains("Référence").click();
    h.run_ok();
    h.get_by_label_contains("Référence").type_text("Jean 3:16");
    h.run_ok();
    h.key_press(Key::Enter);
    h.run_ok();
    h.state_mut().app().take();
    h.ctx.memory_mut(|m| m.stop_text_input());
    h.run_ok();

    // Ctrl+Maj+I : le verset au direct, avec le modèle de l'église.
    h.key_press_modifiers(Modifiers::COMMAND | Modifiers::SHIFT, Key::I);
    h.run_ok();
    let quote = &h.state_mut().app().quote;
    assert!(quote.open);
    assert!(quote.text.contains("Dieu a tant aimé"), "{}", quote.text);
    assert!(quote.reference.starts_with("Jean 3:16"));
    assert_eq!(quote.style, "minimal");
    h.get_by_label("Image de citation");

    h.get_by_label("Copier l'image").click();
    h.run_ok();
    assert!(h.state_mut().app().quote.message.starts_with("Image copiée"));
    h.get_by_label("Image copiée ✓");

    h.get_by_label("Projeter").click();
    h.run_ok();
    let image = live_image(h.state_mut().app());
    assert!(image.contains("citation-") && image.ends_with(".png"), "{image}");
}

#[test]
fn the_church_photos_are_listed_projected_and_removed() {
    let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
    std::fs::create_dir_all(&base).unwrap();
    let dir = tempfile::tempdir_in(base).unwrap();
    let db = dir.path().join("project_on.db");
    Database::open_and_initialize(&db, &InitOptions::default()).unwrap();
    let photos: Vec<String> = ["bg-ardoise_4x3.png", "bg-indigo_16x9.png"]
        .iter()
        .map(|n| po_layout::bundled_backgrounds_dir().join(n).to_string_lossy().to_string())
        .collect();
    let mut settings = Settings::default();
    settings.other.insert("church".into(), json!({ "name": "Église", "photos": photos }));
    let config = Config {
        fonts_dir: po_layout::bundled_fonts_dir(),
        locations: None,
        database: Some(db),
        settings,
        windowed_projection: true,
        web_port: None,
    };
    let mut h = Harness::builder()
        .with_size([1600.0, 940.0])
        .with_accessibility_check(false)
        .wgpu()
        .build_ui_state(|ui, boot: &mut Boot| boot.ui(ui), Boot::new(config));
    h.run_ok();
    h.get_by_label("Réglages").click();
    h.run_ok();
    h.get_by_label("Réglages · Église").click();
    h.run_ok();
    h.get_by_label("Projeter en diaporama").scroll_to_me();
    h.run_ok();
    h.get_by_label("2 photos");
    h.get_by_label("Projeter en diaporama").click();
    h.run_ok();
    let app = h.state_mut().app();
    let live = app.live.as_ref().unwrap();
    assert_eq!(live.origin, Origin::Slideshow);
    assert_eq!(live.program.len(), 2);
    assert!(app.slideshow.active);

    // ✕ retire une photo de la galerie (le brouillon des réglages, à enregistrer).
    h.get_all_by_label("✕").next().unwrap().click();
    h.run_ok();
    h.get_by_label("1 photo");
    let draft = h.state_mut().app().settings_view.draft.clone().unwrap();
    assert_eq!(draft.other["church"]["photos"].as_array().unwrap().len(), 1);
}
