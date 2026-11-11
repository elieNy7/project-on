//! La page Designs et l'habillage en direct, hors écran (aucune fenêtre) : un design de salle essayé
//! dans l'Aperçu puis appliqué au direct, le lower third (L) et les sous-titres (S) qui avancent
//! dans un long paragraphe avant de changer de slide.

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

#[test]
fn a_room_design_is_tried_in_the_preview_then_applied_live() {
    let mut h = harness();
    // Un verset au direct, puis la page Designs.
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
    until(&mut h, |a| a.live_frame().is_some() && !a.rendering());
    let before = h.state_mut().app().design.clone();

    h.get_by_label("Designs").click();
    h.run_ok();
    h.get_by_label_contains("HABILLAGE EN DIRECT");
    // « Tout » : les designs de salle viennent en tête.
    h.get_by_label("Nuit profonde").click();
    h.run_ok();
    let app = h.state_mut().app();
    let tried = app.preview_design.clone().expect("le design est dans l'Aperçu");
    assert_eq!(app.design, before, "le direct n'a pas bougé");
    assert_ne!(tried, before);

    h.get_by_label("Appliquer au direct").click();
    h.run_ok();
    let app = h.state_mut().app();
    assert_eq!(app.design, tried);
    assert!(app.preview_design.is_none());
}

#[test]
fn l_shows_the_lower_third_and_s_steps_the_subtitles_through_a_paragraph() {
    let mut h = harness();
    // Un long paragraphe de sermon au direct.
    h.get_by_label("La Foi").click();
    h.run_ok();
    h.get_by_label_contains("Elle prend Dieu au mot").click();
    h.run_ok();
    h.state_mut().app().take();
    until(&mut h, |a| a.live_frame().is_some() && !a.rendering());

    // L : le lower third s'affiche, le hub le reçoit ; en mode automatique, il prend le titre du sermon.
    h.state_mut().app().lower_third.auto = true;
    h.key_press(Key::L);
    h.run_ok();
    until(&mut h, |a| a.hub.program().context.lower_third.is_some());
    let overlay = h.state_mut().app().hub.program().context.lower_third.clone().unwrap();
    assert!(overlay.shown);
    assert!(!overlay.text.title.is_empty(), "{:?}", overlay.text);

    // S : les sous-titres s'affichent ; → avance dans le paragraphe sans changer de slide.
    h.state_mut().app().subtitles.style.max_lines = 1;
    h.state_mut().app().subtitles.cut_for = None;
    h.key_press(Key::S);
    h.run_ok();
    until(&mut h, |a| a.hub.program().context.subtitle.is_some());
    let app = h.state_mut().app();
    let chunks = app.subtitles.chunks.len();
    assert!(chunks >= 2, "{chunks} sous-titres");
    let row = app.live.as_ref().unwrap().program.current();
    let first = app.hub.program().context.subtitle.clone().unwrap().1;
    h.key_press(Key::ArrowRight);
    h.run_ok();
    until(&mut h, |a| a.hub.program().context.subtitle.as_ref().is_some_and(|s| s.1 != first));
    let app = h.state_mut().app();
    assert_eq!(app.live.as_ref().unwrap().program.current(), row, "le slide reste");
    assert_eq!(app.subtitles.index, 1);
    // S de nouveau : masqués, → change de slide.
    h.key_press(Key::S);
    h.run_ok();
    until(&mut h, |a| a.hub.program().context.subtitle.is_none());
}
