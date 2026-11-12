//! Le thème de Project-On : celui de la brique partagée `po-ui` (bleu nuit et or, relief doux), plus
//! le logo de Project-On.

pub use po_ui::theme::*;

/// Le logo de Project-On (1024 × 1024), intégré à l'exécutable : il ne peut pas manquer.
pub const LOGO_PNG: &[u8] = include_bytes!("../../../../assets/logo/app icon.png");

/// L'icône des fenêtres (régie, projection) : le logo, comme le raccourci du Bureau.
/// Décodée une seule fois (la fenêtre de projection la redonne à chaque image).
pub fn window_icon() -> Option<std::sync::Arc<egui::IconData>> {
    static ICON: std::sync::OnceLock<Option<std::sync::Arc<egui::IconData>>> = std::sync::OnceLock::new();
    ICON.get_or_init(|| png_icon(LOGO_PNG)).clone()
}

/// Le logo peint dans `rect` (barre du haut, accueil).
pub fn paint_logo(painter: &egui::Painter, rect: egui::Rect) {
    paint_png(painter, rect, "po-logo", LOGO_PNG);
}
