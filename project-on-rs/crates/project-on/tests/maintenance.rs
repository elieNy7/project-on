//! L'entretien depuis la régie, hors écran (aucune fenêtre), sur un dossier de données d'essai :
//! l'historique du culte, la reprise du direct après un arrêt brutal, la page Réglages (mode PC
//! modeste enregistré dans `settings.json`), la sauvegarde et le contrôle avant culte.

// Un essai qui échoue s'arrête : `unwrap` y est permis, aussi dans les fonctions d'aide.
#![allow(clippy::unwrap_used)]

use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use egui::Key;
use egui_kittest::Harness;
use egui_kittest::kittest::Queryable;
use po_db::{Database, InitOptions};
use po_settings::Settings;
use project_on::data::Locations;
use project_on::{App, Boot, Config};

/// Un dossier de données de la bêta, avec une base neuve (démonstration et Bibles du dépôt).
fn beta() -> (tempfile::TempDir, PathBuf) {
    let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
    std::fs::create_dir_all(&base).unwrap();
    let dir = tempfile::tempdir_in(base).unwrap();
    let beta = dir.path().join("bêta");
    let locations = Locations::at(&beta, None);
    let db = locations.beta.database();
    std::fs::create_dir_all(db.parent().unwrap()).unwrap();
    let bibles = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../bible_json");
    Database::open_and_initialize(&db, &InitOptions { bible_json_dir: Some(bibles) }).unwrap();
    (dir, beta)
}

fn harness(beta: &Path) -> Harness<'static, Boot> {
    let config = Config {
        fonts_dir: po_layout::bundled_fonts_dir(),
        locations: Some(Locations::at(beta, None)),
        database: None,
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

fn verse_live(h: &mut Harness<'static, Boot>) {
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
    until(h, |a| a.live_frame().is_some() && !a.rendering());
}

#[test]
fn the_live_survives_a_crash_and_the_day_is_recorded() {
    let (_dir, beta) = beta();
    let data = Locations::at(&beta, None).beta.data();
    {
        let mut h = harness(&beta);
        verse_live(&mut h);
        h.key_press(Key::PageDown);
        until(&mut h, |a| a.live.as_ref().unwrap().program.current() > 0 && !a.rendering());
        // L'historique du jour : deux slides.
        let day = std::fs::read_dir(data.join("historique")).unwrap().next().unwrap().unwrap().path();
        let events = project_on::history::read(&day);
        assert_eq!(events.len(), 2);
        assert!(events[0].reference.starts_with("Jean 3:16"));
        assert!(project_on::recovery::file(&data).is_file(), "le direct est enregistré");
        // Arrêt brutal : la régie disparaît sans fermeture normale.
    }
    let mut h = harness(&beta);
    let app = h.state_mut().app();
    let offered = app.recovery.as_ref().expect("la reprise est proposée");
    assert!(offered.program.slide().reference.starts_with("Jean 3:17"));
    h.get_by_label("Reprendre le direct").click();
    h.run_ok();
    until(&mut h, |a| a.live_frame().is_some() && !a.rendering());
    let app = h.state_mut().app();
    assert!(app.live.as_ref().unwrap().program.slide().reference.starts_with("Jean 3:17"));
    assert!(app.recovery.is_none());
    // Fermeture normale : plus rien à reprendre.
    app.shutdown();
    assert!(!project_on::recovery::file(&data).exists());
}

#[test]
fn the_settings_page_saves_backs_up_and_checks() {
    let (_dir, beta) = beta();
    let locations = Locations::at(&beta, None);
    let mut h = harness(&beta);
    h.get_by_label("Réglages").click();
    h.run_ok();
    // Mode PC modeste : enregistré dans le settings.json de la bêta, et appliqué.
    h.get_by_label_contains("Sans transitions").click();
    h.run_ok();
    h.get_by_label("Enregistrer").click();
    h.run_ok();
    let saved = Settings::load(&locations.beta.settings()).settings;
    assert_eq!(saved.other["refonte_3"]["low_power"], serde_json::json!(true));
    assert_eq!(h.state_mut().app().design.animation.kind, po_design::AnimationKind::None);
    // La mise à jour : la version installée et la recherche (pas lancée ici : pas de réseau).
    h.get_by_label(&format!("Version installée : {}", env!("CARGO_PKG_VERSION")));
    h.get_by_label("Rechercher une mise à jour");
    // Une sauvegarde : la base et les réglages, listés ensuite.
    h.get_by_label("Sauvegarder maintenant").click();
    h.run_ok();
    let backups = project_on::maintenance::list(&locations.beta.data().join("sauvegardes"));
    assert_eq!(backups.len(), 1);
    assert!(backups[0].dir.join("settings.json").is_file());
    // Le contrôle avant culte : la base est ouverte, la sauvegarde est récente.
    h.get_by_label("Contrôle avant culte  Ctrl+Maj+D").click();
    h.run_ok();
    let checks = h.state_mut().app().settings_view.checks.clone();
    let level = |title: &str| checks.iter().find(|c| c.title == title).map(|c| c.level);
    assert_eq!(level("Base de données"), Some(project_on::maintenance::Level::Ok));
    assert_eq!(level("Sauvegarde"), Some(project_on::maintenance::Level::Ok));
}

#[test]
fn a_backup_is_restored_at_the_next_start_and_the_state_before_is_kept() {
    let (_dir, beta) = beta();
    let locations = Locations::at(&beta, None);
    let mut h = harness(&beta);
    h.get_by_label("Réglages").click();
    h.run_ok();
    h.get_by_label("Sauvegarder maintenant").click();
    h.run_ok();
    // Après la sauvegarde, une playlist de plus.
    let mut other = Database::open(&locations.beta.database(), po_db::Mode::ReadWrite).unwrap();
    other.create_folder("Faite après la sauvegarde").unwrap();
    drop(other);

    h.get_by_label("Restaurer une sauvegarde").click();
    h.run_ok();
    h.get_by_label("Restaurer…").click();
    h.run_ok();
    h.get_by_label_contains("Rien ne change avant le prochain démarrage");
    h.get_by_label("Préparer la restauration").click();
    until(&mut h, |a| a.settings_view.pending_restore.is_some());
    h.run_ok();
    let label = h.state_mut().app().settings_view.pending_restore.clone().unwrap();
    h.get_by_label(&format!("Restauration prête : {label}"));
    h.get_by_label("Fermer Project-On maintenant");
    drop(h);

    // Au démarrage suivant : la base de la sauvegarde, et celle d'avant gardée.
    let mut h = harness(&beta);
    h.run_ok();
    let names: Vec<String> =
        h.state_mut().app().database().unwrap().list_folders().unwrap().into_iter().map(|f| f.name).collect();
    assert!(!names.iter().any(|n| n == "Faite après la sauvegarde"), "{names:?}");
    let backups = project_on::maintenance::list(&locations.beta.data().join("sauvegardes"));
    let safety = backups.iter().find(|b| b.dir.to_string_lossy().ends_with("-avant-restauration")).unwrap();
    let before = Database::open(&safety.dir.join("project_on.db"), po_db::Mode::ReadOnly).unwrap();
    assert!(before.list_folders().unwrap().iter().any(|f| f.name == "Faite après la sauvegarde"));
    assert_eq!(h.state_mut().app().settings_view.pending_restore, None);
}

#[test]
fn obs_control_is_set_in_the_settings_with_its_password_encrypted() {
    let (_dir, beta) = beta();
    let locations = Locations::at(&beta, None);
    let mut h = harness(&beta);
    h.get_by_label("Réglages").click();
    h.run_ok();
    h.get_by_label_contains("Changer de scène au direct").scroll_to_me();
    h.run_ok();
    h.get_by_label_contains("Changer de scène au direct").click();
    h.run_ok();
    h.get_by_label("Champ : mot de passe d'OBS").click();
    h.run_ok();
    h.get_by_label("Champ : mot de passe d'OBS").type_text("secret-obs");
    h.run_ok();
    h.get_by_label("Enregistrer").scroll_to_me();
    h.run_ok();
    h.get_by_label("Enregistrer").click();
    h.run_ok();
    let text = std::fs::read_to_string(locations.beta.settings()).unwrap();
    assert!(!text.contains("secret-obs"), "jamais en clair");
    let saved = Settings::load(&locations.beta.settings()).settings;
    let obs = project_on::obs::ObsSettings::from_settings(&saved);
    assert!(obs.enabled);
    assert_eq!(obs.password, "secret-obs");
    assert_eq!(obs.port, 4455);
}
