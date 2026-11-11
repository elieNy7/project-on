//! Une vraie vidéo au direct, hors écran (aucune fenêtre, sans son) : FFmpeg fabrique une vidéo
//! d'essai ; dans un diaporama, son image arrive dans la régie, puis, à sa fin, l'image suivante
//! passe au direct. Sauté si FFmpeg n'est pas installé.

// Un essai qui échoue s'arrête : `unwrap` y est permis, aussi dans les fonctions d'aide.
#![allow(clippy::unwrap_used)]

use std::path::Path;
use std::process::Command;
use std::time::{Duration, Instant};

use egui_kittest::Harness;
use po_db::{Database, InitOptions};
use po_settings::Settings;
use project_on::{App, Boot, Config};

fn until(h: &mut Harness<'static, Boot>, what: &str, done: impl Fn(&App) -> bool) {
    let start = Instant::now();
    while start.elapsed() < Duration::from_secs(30) {
        h.step();
        if h.state().get().is_some_and(&done) {
            return;
        }
        std::thread::sleep(Duration::from_millis(10));
    }
    panic!("délai dépassé : {what}");
}

#[test]
fn a_video_plays_live_and_the_slideshow_moves_on_at_its_end() {
    let Some(ffmpeg) = project_on::video::find_ffmpeg() else {
        eprintln!("FFmpeg absent : essai sauté");
        return;
    };
    let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
    std::fs::create_dir_all(&base).unwrap();
    let dir = tempfile::tempdir_in(base).unwrap();
    let folder = dir.path().join("Culte");
    std::fs::create_dir_all(&folder).unwrap();
    // 1 : une vidéo de 1,5 s avec du son ; 2 : une image.
    let clip = folder.join("1 clip.mp4");
    let made = Command::new(&ffmpeg)
        .args(["-hide_banner", "-loglevel", "error", "-y"])
        .args(["-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=1.5"])
        .args(["-f", "lavfi", "-i", "sine=frequency=440:duration=1.5"])
        .args(["-pix_fmt", "yuv420p", "-shortest"])
        .arg(&clip)
        .status()
        .unwrap();
    assert!(made.success());
    std::fs::copy(po_layout::bundled_backgrounds_dir().join("bg-indigo_16x9.png"), folder.join("2 annonce.png"))
        .unwrap();

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

    let app = h.state_mut().app();
    app.video_muted = true;
    app.media_view.seconds = 30;
    let medias = project_on::media::folder_images(&folder);
    assert_eq!(medias.len(), 2, "la vidéo et l'image");
    app.start_slideshow(medias, "Culte");
    h.run_ok();
    // La vidéo est au direct, son image arrive dans la régie ; pas de minuterie (elle donne le tempo).
    until(&mut h, "le lecteur", |a| a.video.as_ref().is_some_and(|v| v.texture().is_some()));
    let app = h.state_mut().app();
    assert!(app.live_video_path().unwrap().ends_with("1 clip.mp4"));
    assert_eq!(app.slideshow.next_at(), None);
    let video = app.video.as_ref().unwrap();
    assert_eq!(video.texture().unwrap().size(), [320, 180]);
    assert!(video.player.probe.has_audio);
    // À sa fin, l'image suivante passe au direct, et le lecteur s'arrête.
    until(&mut h, "l'image suivante", |a| a.slideshow_position() == Some((1, 2)));
    let app = h.state_mut().app();
    assert!(app.video.is_none());
    assert!(app.live_video_path().is_none());
    assert!(app.slideshow.next_at().is_some(), "l'image a sa durée");
}
