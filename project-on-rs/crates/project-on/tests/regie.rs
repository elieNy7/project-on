//! La régie rendue hors écran (egui_kittest + wgpu) : aucune fenêtre ne s'ouvre. Les essais
//! travaillent sur une base neuve (démonstration + trois Bibles) créée sous `target/tmp`.

// Un essai qui échoue s'arrête : `unwrap` y est permis, aussi dans les fonctions d'aide.
#![allow(clippy::unwrap_used)]

use std::path::{Path, PathBuf};
use std::sync::OnceLock;
use std::time::{Duration, Instant};

use egui::Key;
use egui_kittest::Harness;
use egui_kittest::kittest::Queryable;
use po_db::{Database, InitOptions};
use po_settings::Settings;
use project_on::data::Locations;
use project_on::{App, Boot, Config};

fn scratch() -> tempfile::TempDir {
    let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
    std::fs::create_dir_all(&base).unwrap();
    tempfile::tempdir_in(base).unwrap()
}

/// Une base neuve avec les Bibles du dépôt, créée une fois pour tous les essais.
fn fixture() -> PathBuf {
    static PATH: OnceLock<(tempfile::TempDir, PathBuf)> = OnceLock::new();
    PATH.get_or_init(|| {
        let dir = scratch();
        let path = dir.path().join("project_on.db");
        let bibles = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../bible_json");
        Database::open_and_initialize(&path, &InitOptions { bible_json_dir: Some(bibles) }).unwrap();
        (dir, path)
    })
    .1
    .clone()
}

fn config(database: Option<PathBuf>, locations: Option<Locations>) -> Config {
    Config {
        fonts_dir: po_layout::bundled_fonts_dir(),
        locations,
        database,
        settings: Settings::default(),
        windowed_projection: true,
    }
}

fn harness(config: Config) -> Harness<'static, Boot> {
    let mut h = Harness::builder()
        .with_size([1600.0, 940.0])
        .with_accessibility_check(false)
        .wgpu()
        .build_ui_state(|ui, boot: &mut Boot| boot.ui(ui), Boot::new(config));
    h.run_ok();
    h
}

/// Fait tourner l'interface jusqu'à `done` (au plus 20 s).
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

fn press(h: &mut Harness<'static, Boot>, key: Key) {
    h.key_press(key);
    h.step();
}

#[test]
fn a_click_prepares_the_aperçu_and_f2_sends_it_live() {
    let mut h = harness(config(Some(fixture()), None));
    h.get_by_label("La Foi").click();
    h.run_ok();
    // Un clic sur le deuxième paragraphe : tout le sermon est préparé, à partir de lui.
    h.get_by_label_contains("Elle prend Dieu au mot").click();
    h.run_ok();
    let app = h.state_mut().app();
    let preview = app.preview.as_ref().expect("l'Aperçu est préparé");
    assert_eq!(preview.program.len(), 2);
    assert_eq!(preview.program.current(), 1);
    assert!(app.live.is_none(), "rien n'est parti au direct");
    until(&mut h, |a| a.preview_frame().is_some());

    press(&mut h, Key::F2);
    until(&mut h, |a| a.live_frame().is_some() && !a.rendering());
    let app = h.state_mut().app();
    assert_eq!(app.live.as_ref().unwrap().program.slide().text, preview_text(app));
    assert!(app.taken.is_some(), "le slide part aussi aux écrans Web");
    // Le slide au direct porte l'identification de Branham (une prédication).
    assert!(!app.live_frame().unwrap().list.overlay.is_empty());
}

fn preview_text(app: &App) -> String {
    app.preview.as_ref().unwrap().program.slide().text
}

#[test]
fn a_reference_opens_its_chapter_and_the_keys_drive_the_live() {
    let mut h = harness(config(Some(fixture()), None));
    h.get_by_label("Bible").click();
    h.run_ok();
    let field = h.get_by_label_contains("Référence");
    field.click();
    h.run_ok();
    h.get_by_label_contains("Référence").type_text("Jean 3:16");
    h.run_ok();
    press(&mut h, Key::Enter);
    h.run_ok();
    let app = h.state_mut().app();
    let preview = app.preview.as_ref().expect("la référence prépare son chapitre");
    assert!(preview.program.slide().reference.starts_with("Jean 3:16"), "{}", preview.program.slide().reference);
    assert_eq!(preview.program.title, "Jean 3");
    // Le champ garde le clavier : on le quitte avant de piloter le direct.
    h.state_mut().app().take();
    h.ctx.memory_mut(|m| m.stop_text_input());
    h.step();
    let row = h.state().get().unwrap().live.as_ref().unwrap().program.current();
    press(&mut h, Key::PageDown);
    assert_eq!(h.state().get().unwrap().live.as_ref().unwrap().program.current(), row + 1);
    press(&mut h, Key::ArrowLeft);
    assert_eq!(h.state().get().unwrap().live.as_ref().unwrap().program.current(), row);
    press(&mut h, Key::Home);
    assert_eq!(h.state().get().unwrap().live.as_ref().unwrap().program.current(), 0);
    let slide = h.state().get().unwrap().live.as_ref().unwrap().program.slide();
    assert!(slide.reference.starts_with("Jean 3:1"), "{}", slide.reference);
}

#[test]
fn b_hides_the_text_but_not_while_typing() {
    let mut h = harness(config(Some(fixture()), None));
    press(&mut h, Key::B);
    assert!(h.state_mut().app().hidden(), "B masque le texte");
    press(&mut h, Key::B);
    assert!(!h.state_mut().app().hidden());
    // Taper « Bible » dans un champ ne masque rien.
    h.get_by_label_contains("Rechercher un sermon").click();
    h.run_ok();
    h.get_by_label_contains("Rechercher un sermon").type_text("Bible");
    h.run_ok();
    press(&mut h, Key::B);
    assert!(!h.state_mut().app().hidden());
}

#[test]
fn global_search_with_accents_like_a_french_keyboard() {
    let mut h = harness(config(Some(fixture()), None));
    h.key_press_modifiers(egui::Modifiers::COMMAND, Key::K);
    h.run_ok();
    // « grâce » : l'accent circonflexe arrive comme du texte (touche morte du clavier AZERTY).
    h.get_by_label_contains("Rechercher partout").type_text("grâce");
    until(&mut h, |a| !a.global_results_now().1 && !a.global_results_now().0.is_empty());
    let app = h.state_mut().app();
    let (hits, _) = app.global_results_now();
    assert!(hits.iter().any(|hit| hit.kind == project_on::search::Kind::Bible), "des versets");
    // « Jean 3:16 » : la référence d'abord.
    app.search_everywhere("Jean 3:16");
    h.step();
    until(&mut h, |a| !a.global_results_now().1 && !a.global_results_now().0.is_empty());
    let app = h.state_mut().app();
    assert_eq!(app.global_results_now().0[0].title, "Jean 3:16");
    app.open_global(0);
    assert_eq!(app.page, project_on::library::Page::Bible);
    assert!(app.preview.as_ref().unwrap().program.slide().reference.starts_with("Jean 3:16"));
}

#[test]
fn f5_opens_and_closes_the_projection() {
    let mut h = harness(config(Some(fixture()), None));
    h.ctx.set_embed_viewports(true);
    h.state_mut().app().select_sermon(0);
    h.state_mut().app().cue_sermon_entry(0);
    h.state_mut().app().take();
    press(&mut h, Key::F5);
    assert!(h.state_mut().app().projecting());
    until(&mut h, |a| a.live_frame().is_some() && !a.rendering());
    // La fenêtre de projection (ici intégrée à l'image) montre le direct.
    let image = h.render().expect("rendu hors écran");
    assert_eq!((image.width(), image.height()), (1600, 940));
    // Un second écran (ici fictif, 4K) : les deux projettent, le rendu suit le plus grand.
    let tv = project_on::screens::Screen {
        device: r"\\.\DISPLAY9".into(),
        label: "Écran 9 — 3840 × 2160".into(),
        x: 0,
        y: 0,
        width: 3840,
        height: 2160,
        primary: false,
    };
    h.state_mut().app().toggle_projector(project_on::projector::Projector::on(tv));
    h.step();
    assert_eq!(h.state_mut().app().projection(), (2, (2560, 1440)));
    press(&mut h, Key::F5);
    assert!(!h.state_mut().app().projecting(), "F5 ferme toutes les projections");
}

#[test]
fn the_first_launch_copies_the_2x_data_and_leaves_it_untouched() {
    let dir = scratch();
    let legacy = dir.path().join("Project-On");
    let beta = dir.path().join("Project-On 3 (bêta)");
    std::fs::create_dir_all(legacy.join("data")).unwrap();
    std::fs::copy(fixture(), legacy.join("data").join("project_on.db")).unwrap();
    std::fs::write(legacy.join("data").join("settings.json"), r#"{"projection": {"font_family": "Poppins"}}"#).unwrap();
    let before = std::fs::read(legacy.join("data").join("project_on.db")).unwrap();

    let locations = Locations::at(&beta, Some(&legacy));
    let mut h = harness(config(None, Some(locations)));
    until(&mut h, |a| a.database().is_some());
    h.run_ok();
    h.get_by_label("La Foi");
    assert!(beta.join("data").join("project_on.db").is_file());
    assert!(beta.join("data").join("settings.json").is_file());
    assert_eq!(
        std::fs::read(legacy.join("data").join("project_on.db")).unwrap(),
        before,
        "la base de la 2.x n'a pas changé"
    );
}

#[test]
fn without_2x_data_the_beta_says_so() {
    let dir = scratch();
    let locations = Locations::at(dir.path().join("bêta"), None);
    let h = harness(config(None, Some(locations)));
    h.get_by_label_contains("Aucune base à copier");
}

#[test]
fn the_first_launch_offers_the_bundled_database() {
    let dir = scratch();
    let legacy = dir.path().join("Project-On");
    std::fs::create_dir_all(legacy.join("data")).unwrap();
    std::fs::copy(fixture(), legacy.join("data").join("project_on.db")).unwrap();
    let bundled = dir.path().join("installation").join("data").join("project_on.db");
    std::fs::create_dir_all(bundled.parent().unwrap()).unwrap();
    std::fs::copy(fixture(), &bundled).unwrap();
    let before = std::fs::read(legacy.join("data").join("project_on.db")).unwrap();

    let locations = Locations::at(dir.path().join("bêta"), Some(&legacy)).with_bundled(Some(bundled));
    let mut h = harness(config(None, Some(locations)));
    assert!(h.state_mut().app().choosing());
    h.get_by_label("Mes données de Project-On 2.8");
    h.get_by_label("La base fournie avec Project-On").click();
    until(&mut h, |a| a.database().is_some());
    h.run_ok();
    h.get_by_label("La Foi");
    assert!(dir.path().join("bêta").join("data").join("project_on.db").is_file());
    assert_eq!(std::fs::read(legacy.join("data").join("project_on.db")).unwrap(), before, "la 2.x n'a pas changé");
}
