//! Le diaporama d'un dossier, hors écran (aucune fenêtre) : il prend le direct, avance seul, et une
//! flèche le rend à l'opérateur avec le direct d'avant ; un autre programme le clôt sans rien rendre.

// Un essai qui échoue s'arrête : `unwrap` y est permis, aussi dans les fonctions d'aide.
#![allow(clippy::unwrap_used)]

use std::path::Path;
use std::time::{Duration, Instant};

use egui::Key;
use egui_kittest::Harness;
use egui_kittest::kittest::Queryable;
use po_db::{Database, InitOptions};
use po_settings::Settings;
use project_on::library::Origin;
use project_on::{App, Boot, Config};

fn harness(dir: &Path) -> Harness<'static, Boot> {
    let path = dir.join("project_on.db");
    let bibles = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../bible_json");
    Database::open_and_initialize(&path, &InitOptions { bible_json_dir: Some(bibles) }).unwrap();
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

fn until(h: &mut Harness<'static, Boot>, done: impl Fn(&App) -> bool) {
    let start = Instant::now();
    while start.elapsed() < Duration::from_secs(20) {
        h.step();
        if h.state().get().is_some_and(&done) {
            return;
        }
        std::thread::sleep(Duration::from_millis(5));
    }
    panic!("délai dépassé");
}

#[test]
fn the_slideshow_takes_the_live_advances_and_gives_it_back() {
    let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
    std::fs::create_dir_all(&base).unwrap();
    let dir = tempfile::tempdir_in(base).unwrap();
    let images = dir.path().join("Annonces");
    std::fs::create_dir_all(&images).unwrap();
    for (i, name) in ["bg-ardoise_16x9.png", "bg-bordeaux_16x9.png", "bg-indigo_16x9.png"].iter().enumerate() {
        std::fs::copy(po_layout::bundled_backgrounds_dir().join(name), images.join(format!("annonce {}.png", i + 1)))
            .unwrap();
    }
    let mut h = harness(dir.path());

    // Un verset au direct.
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

    // La page Médias : le dossier, 1 s par image, « Lancer le diaporama ».
    h.get_by_label("Médias").click();
    h.run_ok();
    h.get_by_label("Dossier d'images").click();
    h.run_ok();
    h.get_by_label("Dossier d'images").type_text(&images.to_string_lossy());
    h.run_ok();
    h.ctx.memory_mut(|m| m.stop_text_input());
    h.get_by_label("3 média(s)");
    h.state_mut().app().media_view.seconds = 1;
    h.get_by_label("Lancer le diaporama").click();
    h.run_ok();
    let app = h.state_mut().app();
    let live = app.live.as_ref().unwrap();
    assert_eq!(live.origin, Origin::Slideshow);
    assert_eq!((live.program.title.as_str(), live.program.len()), ("Annonces", 3));
    assert!(live.program.slide().background.unwrap().ends_with("annonce 1.png"));
    assert_eq!(app.slideshow_position(), Some((0, 3)));

    // Il avance seul.
    until(&mut h, |a| a.slideshow_position() == Some((1, 3)));

    // Une flèche : le diaporama s'arrête, le verset revient, et la flèche agit sur lui.
    h.state_mut().app().page = project_on::library::Page::Bible;
    h.run_ok();
    h.key_press(Key::ArrowRight);
    h.run_ok();
    let app = h.state_mut().app();
    assert!(!app.slideshow.active);
    let live = app.live.as_ref().unwrap();
    assert!(live.program.slide().reference.starts_with("Jean 3:17"), "{}", live.program.slide().reference);

    // De nouveau, puis un autre programme au direct : clos sans rien rendre.
    let medias = project_on::media::folder_images(&images);
    h.state_mut().app().start_slideshow(medias, "Annonces");
    h.run_ok();
    assert!(h.state_mut().app().slideshow.active);
    h.state_mut().app().take();
    h.run_ok();
    let app = h.state_mut().app();
    assert!(!app.slideshow.active);
    assert_ne!(app.live.as_ref().unwrap().origin, Origin::Slideshow);
}
