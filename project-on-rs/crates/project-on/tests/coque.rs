//! L'interface rendue hors écran (egui_kittest + wgpu) : aucune fenêtre ne s'ouvre.

use egui_kittest::Harness;
use egui_kittest::kittest::Queryable;
use po_layout::Fonts;
use project_on::{Shell, theme};

fn harness(shell: Shell) -> Harness<'static, Shell> {
    let dir = po_layout::bundled_fonts_dir();
    Harness::builder()
        .with_size([1500.0, 900.0])
        .with_accessibility_check(false)
        .with_context_setup(move |ctx| theme::install(ctx, &dir))
        .wgpu()
        .build_ui_state(|ui, shell: &mut Shell| shell.ui(ui), shell)
}

#[test]
fn sans_base_l_ecran_s_affiche_et_le_dit() {
    let mut h = harness(Shell::new(None, Fonts::from_files::<&str>(&[])));
    h.run_ok();
    h.get_by_label("Base de données introuvable.");
    h.get_by_label("Choisissez une prédication");
    // Rien à envoyer au direct tant que l'Aperçu est vide.
    let ctx = h.ctx.clone();
    h.state_mut().take(&ctx);
    assert!(h.state().taken.is_none());
    let image = h.render().expect("rendu hors écran");
    assert_eq!((image.width(), image.height()), (1500, 900));
}
