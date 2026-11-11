//! La mise en page de Project-On : un seul moteur, une liste d'affichage dessinée par tous les
//! écrans (fenêtre de projection, projection Web, NDI, HDMI).
//!
//! - [`layout_room`] : un slide de salle en plein écran, avec la géométrie et l'ajustement du texte
//!   de la 2.8, et l'identification de Branham en bas des prédications.
//! - [`transition::frame`] : une image de transition entre deux slides.

mod backdrop;
mod band;
pub mod church;
mod display;
#[cfg(windows)]
mod dwrite;
mod fit;
mod fonts;
pub mod graphics;
pub mod identification;
mod room;
pub mod transition;

pub use band::{layout_band, layout_stage};
/// La base de polices de cosmic-text (pour lister les fichiers à servir aux navigateurs).
pub use cosmic_text::fontdb;
pub use display::{Anchor, DisplayList, Group, Item, Rgba, Stop, TextLine, TextOutline, TextShadow};
pub use fit::{FontSpec, balanced_lines, fit_text_size, splitlines, wrap_lines};
pub use fonts::{Fonts, QtMetrics, VerticalMetrics};
pub use room::{Probe, Slide, layout_room};

/// Le dossier des polices livrées avec Project-On (`assets/fonts` à la racine du dépôt).
pub fn bundled_fonts_dir() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../assets/fonts")
}

/// Le dossier des fonds livrés avec Project-On (`assets/backgrounds`).
pub fn bundled_backgrounds_dir() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../assets/backgrounds")
}
