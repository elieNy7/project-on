//! Le rendu des pages d'un PDF par Windows, dans le processus d'aide de Project-On (le moteur
//! LibreOffice des PowerPoint) : aucune fenêtre ne s'ouvre.

#![allow(clippy::unwrap_used)]

use std::path::Path;

#[cfg(windows)]
#[test]
fn windows_renders_the_pages_of_a_pdf_in_a_helper_process() {
    let pdf = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../cantiques/Cantique Pene Na Yo.pdf");
    if !pdf.is_file() {
        return;
    }
    let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
    std::fs::create_dir_all(&base).unwrap();
    let dir = tempfile::tempdir_in(base).unwrap();
    let helper = Path::new(env!("CARGO_BIN_EXE_project-on"));
    let count = project_on::office::pdf_to_png(helper, &pdf, dir.path()).unwrap();
    assert!(count > 10, "{count}");
    let first = std::fs::read(dir.path().join("slide-0001.png")).unwrap();
    assert_eq!(&first[1..4], b"PNG");
    assert_eq!(u32::from_be_bytes([first[16], first[17], first[18], first[19]]), 1920);
}

/// Un PowerPoint déjà rendu (par la 2.8 ou la 3.0) se projette slide par slide dans la playlist.
#[test]
fn a_rendered_powerpoint_plays_in_the_playlist() {
    use egui_kittest::Harness;
    use po_db::{Database, InitOptions};
    use project_on::{Boot, Config};

    let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
    std::fs::create_dir_all(&base).unwrap();
    let dir = tempfile::tempdir_in(base).unwrap();
    let db_path = dir.path().join("project_on.db");
    let pptx = dir.path().join("Annonces.pptx");
    std::fs::write(&pptx, b"PK une presentation").unwrap();
    let (item, folder) = {
        let (mut db, _) = Database::open_and_initialize(&db_path, &InitOptions::default()).unwrap();
        let folder = db.create_folder("Annonces").unwrap();
        let item = db.add_item("media", "", "", Some(folder), &pptx.to_string_lossy()).unwrap();
        (item, folder)
    };
    // Le rendu laissé par la 2.8 : deux images et le marqueur, dans les médias (à côté de la base).
    let slides = project_on::office::slides_dir(&dir.path().join("media"), &pptx);
    std::fs::create_dir_all(&slides).unwrap();
    for (n, name) in [(1, "bg-ardoise_4x3.png"), (2, "bg-indigo_16x9.png")] {
        std::fs::copy(po_layout::bundled_backgrounds_dir().join(name), slides.join(format!("slide-{n:04}.png")))
            .unwrap();
    }
    let meta = std::fs::metadata(&pptx).unwrap();
    let mtime = meta.modified().unwrap().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs();
    let marker = serde_json::json!({ "size": meta.len(), "mtime": mtime, "slides": 2 });
    std::fs::write(slides.join("_complete.json"), marker.to_string()).unwrap();

    let config = Config {
        fonts_dir: po_layout::bundled_fonts_dir(),
        locations: None,
        database: Some(db_path),
        settings: po_settings::Settings::default(),
        windowed_projection: true,
        web_port: None,
    };
    let mut h = Harness::builder()
        .with_size([1600.0, 940.0])
        .with_accessibility_check(false)
        .wgpu()
        .build_ui_state(|ui, boot: &mut Boot| boot.ui(ui), Boot::new(config));
    h.run_ok();
    {
        let app = h.state_mut().app();
        app.page = project_on::library::Page::Playlist;
        app.playlist.folder = Some(folder);
    }
    h.run_ok();
    let app = h.state_mut().app();
    let path = pptx.to_string_lossy().to_string();
    assert_eq!(app.playlist.office_labels.get(&path).map(String::as_str), Some("PowerPoint · 2 slides"));
    app.play_playlist(item, true);
    let live = app.live.as_ref().unwrap();
    assert_eq!(live.program.len(), 2);
    assert!(live.program.slide().background.unwrap().ends_with("slide-0001.png"));
}
