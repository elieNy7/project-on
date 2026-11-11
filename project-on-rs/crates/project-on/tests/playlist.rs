//! La page Playlist rendue hors écran (egui_kittest + wgpu) : aucune fenêtre ne s'ouvre. Chaque
//! essai écrit dans sa propre copie d'une base neuve (démonstration + trois Bibles).

// Un essai qui échoue s'arrête : `unwrap` y est permis, aussi dans les fonctions d'aide.
#![allow(clippy::unwrap_used)]

use std::path::{Path, PathBuf};
use std::sync::OnceLock;
use std::time::{Duration, Instant};

use egui::{Key, Modifiers};
use egui_kittest::Harness;
use egui_kittest::kittest::Queryable;
use po_db::{Database, InitOptions, Mode};
use po_program::Entry;
use po_settings::Settings;
use project_on::library::Page;
use project_on::library::playlist::PlaylistAction;
use project_on::{App, Boot, Config};

fn scratch() -> tempfile::TempDir {
    let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
    std::fs::create_dir_all(&base).unwrap();
    tempfile::tempdir_in(base).unwrap()
}

/// Une base neuve avec les Bibles du dépôt, faite une fois ; chaque essai en reçoit une copie.
fn fresh_copy(dir: &tempfile::TempDir) -> PathBuf {
    static MODEL: OnceLock<(tempfile::TempDir, PathBuf)> = OnceLock::new();
    let (_, model) = MODEL.get_or_init(|| {
        let dir = scratch();
        let path = dir.path().join("modele.db");
        let bibles = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../bible_json");
        let (db, _) = Database::open_and_initialize(&path, &InitOptions { bible_json_dir: Some(bibles) }).unwrap();
        // Une seule pièce, sans journal : la copie emporte tout.
        db.connection().execute_batch("PRAGMA wal_checkpoint(TRUNCATE);").unwrap();
        drop(db);
        (dir, path)
    });
    let path = dir.path().join("project_on.db");
    std::fs::copy(model, &path).unwrap();
    path
}

fn harness(db: PathBuf) -> Harness<'static, Boot> {
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

fn refs(db: &Path, folder: &str) -> Vec<(String, String)> {
    let db = Database::open(db, Mode::ReadOnly).unwrap();
    let id = db.list_folders().unwrap().into_iter().find(|f| f.name == folder).map(|f| f.id).unwrap();
    db.list_items(Some(id)).unwrap().into_iter().map(|i| (i.source, i.reference)).collect()
}

#[test]
fn adding_from_the_libraries_then_undo() {
    let dir = scratch();
    let path = fresh_copy(&dir);
    let mut h = harness(path.clone());
    // Un paragraphe de sermon, au clic droit, vers une nouvelle playlist.
    h.get_by_label("La Foi").click();
    h.run_ok();
    h.get_by_label_contains("Elle prend Dieu au mot").click_secondary();
    h.run_ok();
    h.get_by_label("Ajouter à la playlist…").click();
    h.run_ok();
    h.get_by_label("Nom de la nouvelle playlist").click();
    h.run_ok();
    h.get_by_label("Nom de la nouvelle playlist").type_text("Culte");
    h.run_ok();
    h.get_by_label("Ajouter").click();
    h.run_ok();
    let added = refs(&path, "Culte");
    assert_eq!(added.len(), 1);
    assert_eq!(added[0].0, "sermon");
    assert_eq!(added[0].1, "1953-09-12 - La Foi - 2", "le paragraphe entier, avec sa référence");

    // Tout un chapitre de la Bible, dans la même playlist (choisie d'office).
    let app = h.state_mut().app();
    let db = app.database().unwrap();
    let t = db.list_translations().unwrap().into_iter().find(|t| t.lang.as_deref() == Some("fr")).unwrap().id;
    let john = db.list_translation_books(t).unwrap().into_iter().find(|b| b.name == "Jean").unwrap().id;
    app.open_bible(t, john, 3, Some(16));
    assert!(app.preview.is_some());
    h.run_ok();
    h.get_by_label_contains("Car Dieu a tant aimé").click_secondary();
    h.run_ok();
    h.get_by_label("Ajouter tout le chapitre").click();
    h.run_ok();
    h.get_by_label("Ajouter").click();
    h.run_ok();
    let items = refs(&path, "Culte");
    assert_eq!(items.len(), 1 + 36, "le paragraphe et les 36 versets de Jean 3");
    assert_eq!(items[1], ("bible".to_string(), "Jean 3:1".to_string()));

    // La page Playlist : « Annuler » retire l'ajout du chapitre.
    h.key_press_modifiers(Modifiers::COMMAND, Key::Num6);
    h.run_ok();
    assert_eq!(h.state_mut().app().page, Page::Playlist);
    h.get_by_label("Annuler").click();
    h.run_ok();
    assert_eq!(refs(&path, "Culte").len(), 1);
}

#[test]
fn selection_keys_and_drag_and_drop() {
    let dir = scratch();
    let path = fresh_copy(&dir);
    let mut h = harness(path.clone());
    {
        let app = h.state_mut().app();
        app.apply_playlist(vec![PlaylistAction::CreateFolder("Louange".into())]);
        let entries: Vec<Entry> =
            ["A", "B", "C", "D", "E"].iter().map(|r| Entry::new(*r, format!("Texte {r}"))).collect();
        app.page = Page::Playlist;
        let folder = app.playlist.folder;
        let app_db = app.database().is_some();
        assert!(app_db && folder.is_some());
        app.playlists_add(&entries, "custom");
    }
    h.run_ok();
    let order = |_: &mut Harness<'static, Boot>| {
        refs(&path, "Louange").into_iter().map(|(_, r)| r).collect::<Vec<_>>().join("")
    };
    assert_eq!(order(&mut h), "ABCDE");
    // A, puis Ctrl+clic sur C : deux slides choisis ; Ctrl+↓ les descend d'un cran.
    h.get_by_label_contains("A Texte A").click();
    h.run_ok();
    h.get_by_label_contains("C Texte C").click_modifiers(Modifiers::COMMAND);
    h.run_ok();
    assert_eq!(h.state_mut().app().playlist.selection().len(), 2);
    h.key_press_modifiers(Modifiers::COMMAND, Key::ArrowDown);
    h.run_ok();
    assert_eq!(order(&mut h), "BADCE");
    // Suppr retire la sélection ; Ctrl+Z la rend.
    h.key_press(Key::Delete);
    h.run_ok();
    assert_eq!(order(&mut h), "BDE");
    h.key_press_modifiers(Modifiers::COMMAND, Key::Z);
    h.run_ok();
    assert_eq!(order(&mut h), "BADCE");
    // Glisser E tout en haut.
    let e = h.get_by_label_contains("E Texte E").rect();
    let b = h.get_by_label_contains("B Texte B").rect();
    h.drag_at(e.center());
    h.step();
    h.hover_at(e.center() - egui::vec2(0.0, 20.0));
    h.step();
    h.hover_at(b.center() - egui::vec2(0.0, 20.0));
    h.step();
    h.drop_at(b.center() - egui::vec2(0.0, 20.0));
    h.run_ok();
    assert_eq!(order(&mut h), "EBADC");
}

#[test]
fn a_playlist_goes_live_and_drives_the_service_plan() {
    let dir = scratch();
    let path = fresh_copy(&dir);
    let mut h = harness(path.clone());
    let (bible, sermon) = {
        let app = h.state_mut().app();
        app.apply_playlist(vec![PlaylistAction::CreateFolder("Culte".into())]);
        app.page = Page::Playlist;
        app.playlists_add(&[Entry::new("Jean 3:16", "Car Dieu a tant aimé le monde.")], "bible");
        app.playlists_add(&[Entry::new("47-0412 - La Foi - ¶3", "La foi est une ferme assurance.")], "sermon");
        app.playlists_add(&[Entry::new("Annonces", "Réunion de prière mercredi.")], "custom");
        let ids: Vec<i64> = app.playlist.items.iter().map(|i| i.id).collect();
        (ids[0], ids[1])
    };
    // La prédication commence au paragraphe de sermon.
    h.state_mut().app().apply_playlist(vec![PlaylistAction::StartSectionAt {
        section: None,
        item: sermon,
        name: "Prédication".into(),
        duration: 45,
    }]);
    h.run_ok();
    h.get_by_label_contains("Prédication · 45 min · 2 slides");
    // Double-clic sur le verset : la playlist part au direct depuis lui.
    h.get_by_label_contains("Jean 3:16").click();
    h.run_ok();
    {
        let app = h.state_mut().app();
        assert_eq!(app.preview.as_ref().unwrap().item(), Some(bible), "un clic prépare l'Aperçu");
        app.take();
    }
    until(&mut h, |a| a.live_frame().is_some() && !a.rendering());
    assert!(!h.state_mut().app().tracker.running(), "aucune section ne commence au verset");
    // Slide suivant : le paragraphe de sermon passe au direct, la section démarre toute seule.
    h.ctx.memory_mut(|m| m.stop_text_input());
    h.key_press(Key::PageDown);
    until(&mut h, |a| !a.rendering());
    let app = h.state_mut().app();
    assert_eq!(app.live.as_ref().unwrap().item(), Some(sermon));
    assert!(app.tracker.running());
    assert_eq!(app.tracker.current, Some(0));
    // Le sermon garde l'identification de Branham, même joué depuis une playlist.
    assert!(!app.live_frame().unwrap().list.overlay.is_empty());
    let rows = refs(&path, "Culte");
    assert_eq!(rows.len(), 3);
}
