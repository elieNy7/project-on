//! Les captures de la régie à plusieurs tailles de fenêtre (plein écran, portable, moitié
//! d'écran de Windows 11) : chaque page est rendue hors écran et écrite sous
//! `target/captures-regie`. Lancer : `cargo test -p project-on --test captures -- --ignored`.

#![allow(clippy::unwrap_used)]

use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use egui_kittest::Harness;
use po_db::{Database, InitOptions};
use po_settings::Settings;
use project_on::library::Page;
use project_on::{App, Boot, Config};

fn fixture(dir: &Path) -> PathBuf {
    let path = dir.join("project_on.db");
    let bibles = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../bible_json");
    Database::open_and_initialize(&path, &InitOptions { bible_json_dir: Some(bibles) }).unwrap();
    path
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
}

#[test]
#[ignore = "écrit des captures (à regarder) sous target/captures-regie"]
fn every_page_at_every_window_size() {
    let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target");
    std::fs::create_dir_all(base.join("tmp")).unwrap();
    let dir = tempfile::tempdir_in(base.join("tmp")).unwrap();
    let db = fixture(dir.path());
    let out = base.join("captures-regie");
    std::fs::create_dir_all(&out).unwrap();
    let pages = [
        Page::Bible,
        Page::Hymns,
        Page::Sermons,
        Page::Expose,
        Page::Books,
        Page::Playlist,
        Page::Designs,
        Page::Settings,
        Page::Media,
        Page::Search,
    ];
    let config = Config {
        fonts_dir: po_layout::bundled_fonts_dir(),
        locations: None,
        database: Some(db.clone()),
        settings: Settings::default(),
        windowed_projection: true,
        web_port: None,
    };
    // Une seule fenêtre, redimensionnée : les icônes sont des textures d'un seul contexte.
    let mut harness = Harness::builder()
        .with_size([1600.0, 940.0])
        .with_accessibility_check(false)
        .wgpu()
        .build_ui_state(|ui, boot: &mut Boot| boot.ui(ui), Boot::new(config));
    harness.run_ok();
    harness.state_mut().app().select_sermon(0);
    harness.state_mut().app().cue_sermon_entry(0);
    harness.state_mut().app().take();
    harness.state_mut().app().cue_sermon_entry(1);
    until(&mut harness, |a| a.live_frame().is_some() && a.preview_frame().is_some() && !a.rendering());
    for (w, h) in [(1600.0, 940.0), (1366.0, 728.0), (960.0, 1000.0), (768.0, 820.0), (640.0, 480.0)] {
        harness.set_size(egui::vec2(w, h));
        for page in pages {
            harness.state_mut().app().page = page;
            for _ in 0..6 {
                harness.step();
            }
            let image = harness.render().unwrap();
            let name = format!("{}x{}-{}.png", w as u32, h as u32, page.label().to_lowercase());
            image.save(out.join(name)).unwrap();
        }
    }
}
