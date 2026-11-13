//! La page Designs et l'habillage en direct, hors écran (aucune fenêtre) : un design de salle essayé
//! dans l'Aperçu puis appliqué au direct, le lower third (L) et les sous-titres (S), qui montrent
//! tout le texte du slide.

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
fn l_shows_the_lower_third_and_s_shows_the_whole_slide_as_subtitle() {
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

    // Les sous-titres sont affichés d'office : tout le texte du slide (plus de morceaux).
    h.state_mut().app().subtitles.cut_for = None;
    assert!(h.state_mut().app().subtitles.shown, "affichés d'office");
    until(&mut h, |a| a.hub.program().context.subtitle.is_some());
    let app = h.state_mut().app();
    assert_eq!(app.subtitles.chunks.len(), 1);
    let live = app.live.as_ref().unwrap().program.slide();
    let shown = app.hub.program().context.subtitle.clone().unwrap().1;
    let words = |t: &str| po_text::words(t).join(" ").to_lowercase();
    assert_eq!(words(&shown), words(&live.text), "tout le texte");
    // Une flèche change de slide (← au dernier slide), et le sous-titre suit.
    let (row, count) = app.live.as_ref().map(|l| (l.program.current(), l.program.len())).unwrap();
    assert!(count > 1);
    let (key, expected) = if row + 1 < count { (Key::ArrowRight, row + 1) } else { (Key::ArrowLeft, row - 1) };
    h.key_press(key);
    h.run_ok();
    until(&mut h, |a| a.hub.program().context.subtitle.as_ref().is_some_and(|s| s.1 != shown));
    let app = h.state_mut().app();
    assert_eq!(app.live.as_ref().unwrap().program.current(), expected, "la flèche change de slide");
    // S : masqués ; S de nouveau : réaffichés.
    h.key_press(Key::S);
    h.run_ok();
    until(&mut h, |a| a.hub.program().context.subtitle.is_none());
    h.key_press(Key::S);
    h.run_ok();
    until(&mut h, |a| a.hub.program().context.subtitle.is_some());
}

#[test]
fn the_chosen_design_dresses_web_ndi_and_hdmi_but_not_the_projection() {
    let mut h = harness();
    let projection = h.state_mut().app().design.clone();
    h.get_by_label("Designs").click();
    h.run_ok();
    // Au départ : le bandeau de la 2.x.
    h.get_by_label("« Mon bandeau 2.x »");
    h.get_by_label("Nuit profonde").click();
    h.run_ok();
    h.get_by_label("Utiliser pour Web, NDI, HDMI").click();
    h.run_ok();
    let app = h.state_mut().app();
    assert_eq!(app.output.name, "Nuit profonde");
    let po_web::Look::Slide(chosen) = app.output.look.clone() else { panic!("un design de slide") };
    assert_eq!(app.design, projection, "la projection garde son design");
    // Les sorties le reçoivent : diffusion (Web, NDI, HDMI) et écrans Web de salle.
    until(&mut h, |a| a.hub.program().context.broadcast == po_web::Look::Slide(chosen.clone()));
    assert_eq!(h.state_mut().app().hub.program().context.design, chosen);
    h.get_by_label("« Nuit profonde »");
    h.get_by_label("✔ Utilisé pour Web, NDI, HDMI");

    // Un bandeau, choisi de la même façon, remplace le design de slide.
    h.get_by_label("Diffusion").click();
    h.run_ok();
    let band = h
        .state_mut()
        .app()
        .designs
        .all()
        .find(|d| matches!(d.body, po_design::library::DesignBody::Band(_)) && d.id != "bandeau-2x")
        .cloned()
        .unwrap();
    h.get_by_label(&band.name).click();
    h.run_ok();
    h.get_by_label("Utiliser pour Web, NDI, HDMI").click();
    h.run_ok();
    until(&mut h, |a| matches!(a.hub.program().context.broadcast, po_web::Look::Band(_)));
    let app = h.state_mut().app();
    assert_eq!(app.output.id, band.id);
    assert_eq!(app.hub.program().context.design, projection, "la salle Web revient au design de la projection");
}

#[test]
fn the_chosen_designs_are_kept_between_launches() {
    let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
    std::fs::create_dir_all(&dir).unwrap();
    let file = tempfile::tempdir_in(dir).unwrap().keep().join("designs-choisis.json");
    let choices = project_on::designs::Choices {
        output: Some("nuit".into()),
        lower_third: Some("lt-moderne".into()),
        subtitles: None,
    };
    choices.save(&file).unwrap();
    assert_eq!(project_on::designs::Choices::load(&file), choices);
    assert_eq!(project_on::designs::Choices::load(&file.with_extension("absent")), Default::default());
    std::fs::remove_dir_all(file.parent().unwrap()).unwrap();
}

#[test]
fn the_dressing_settings_restyle_the_subtitles_the_broadcast_and_the_lower_third() {
    use po_design::tuning::Tunings;
    use po_design::{Align, BandPosition, Rgba};
    let mut h = harness();
    // Un paragraphe de sermon au direct, le lower third affiché (L).
    h.get_by_label("La Foi").click();
    h.run_ok();
    h.get_by_label_contains("Elle prend Dieu au mot").click();
    h.run_ok();
    h.state_mut().app().take();
    until(&mut h, |a| a.live_frame().is_some() && !a.rendering());
    h.state_mut().app().lower_third.auto = true;
    h.key_press(Key::L);
    h.run_ok();
    until(&mut h, |a| a.hub.program().context.lower_third.is_some() && a.hub.program().context.subtitle.is_some());
    let designed = h.state_mut().app().hub.program().context.subtitle.clone().unwrap().0;

    // Réglages → Habillage : les trois habillages, chacun parti de son design.
    h.get_by_label("Réglages").click();
    h.run_ok();
    h.get_by_label("Réglages · Habillage").click();
    h.run_ok();
    let groups = ["Sous-titres", "Diffusion", "Lower third"];
    let personalize = |group: &str| format!("Personnaliser : {group}");
    // Chaque habillage nomme le design dont il part.
    let subtitles = h.state_mut().app().subtitles.name.clone();
    h.get_by_label(&format!("Design choisi : « {subtitles} » (page Designs)"));
    for group in groups {
        h.get_by_label(&personalize(group)).scroll_to_me();
        h.run_ok();
        h.get_by_label(&personalize(group)).click();
        h.run_ok();
    }
    let tunings = |h: &mut Harness<'static, Boot>| {
        let draft = h.state_mut().app().settings_view.draft.clone().unwrap();
        Tunings::from_section(draft.other.get("refonte_3"))
    };
    let mut t = tunings(&mut h);
    assert!(t.subtitles.enabled && t.broadcast.enabled && t.lower_third.enabled);
    // Personnaliser part du design : tant qu'aucune valeur ne change, rien ne bouge.
    assert_eq!(t.subtitles.apply_subtitles(&designed).font, designed.font);
    h.get_by_label("Non enregistré");

    // La police, la taille, l'alignement et les couleurs changent, puis « Enregistrer ».
    let gold = Rgba::rgb(0xe7, 0xc0, 0x7e);
    t.subtitles.size = 64.0;
    t.subtitles.align = Align::Left;
    t.subtitles.family = "Montserrat".into();
    t.broadcast.size = 40.0;
    t.broadcast.color = gold;
    t.lower_third.align = Align::Right;
    t.lower_third.position = BandPosition::Top;
    {
        let app = h.state_mut().app();
        let draft = app.settings_view.draft.as_mut().unwrap();
        let section = draft.other.entry("refonte_3".to_string()).or_insert_with(|| serde_json::json!({}));
        section.as_object_mut().unwrap().insert(po_design::tuning::KEY.into(), t.to_value());
    }
    h.run_ok();
    h.get_by_label("Enregistrer").click();
    h.run_ok();
    until(&mut h, |a| {
        a.hub.program().context.subtitle.as_ref().is_some_and(|(s, _)| s.font.size == 64.0 && s.align == Align::Left)
    });
    let context = h.state_mut().app().hub.program().context.clone();
    let (subtitle, _) = context.subtitle.unwrap();
    assert_eq!(subtitle.font.family, "Montserrat");
    assert_eq!(subtitle.look, designed.look, "le style du design reste");
    let po_web::Look::Band(band) = context.broadcast else { panic!("le bandeau de la 2.x") };
    assert_eq!((band.size, band.text_color), (40.0, gold));
    let lower_third = context.lower_third.unwrap().style;
    assert_eq!((lower_third.align, lower_third.anchor), (Align::Right, po_design::graphics::Anchor::TopRight));
    // Les sous-titres au direct (écran Web) : le texte à gauche, plus grand.
    let program = h.state_mut().app().hub.program();
    let list = h.state_mut().app().hub.layout(&program, po_web::ScreenKind::Subtitles, 1920.0, 1080.0);
    let first = list.text_lines().next().unwrap();
    assert_eq!(first.anchor, po_layout::Anchor::Start);
    assert!(first.x < 1920.0 * 0.2, "{}", first.x);
    // La page Designs le signale.
    h.get_by_label("Designs").click();
    h.run_ok();
    assert_eq!(h.query_all_by_label("· police et couleurs : Réglages → Habillage").count(), 3);

    // Ne plus personnaliser : le design revient tel quel.
    h.get_by_label("Réglages").click();
    h.run_ok();
    h.get_by_label(&personalize(groups[0])).scroll_to_me();
    h.run_ok();
    h.get_by_label(&personalize(groups[0])).click();
    h.run_ok();
    assert!(!tunings(&mut h).subtitles.enabled);
    h.get_by_label("Enregistrer").click();
    h.run_ok();
    until(&mut h, |a| a.hub.program().context.subtitle.as_ref().is_some_and(|(s, _)| s.font == designed.font));
    assert!(h.state_mut().app().tunings.lower_third.enabled, "les autres restent personnalisés");
}
