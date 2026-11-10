//! Les fondations de Project-On : où sont les données, le journal, et les conversions de valeurs
//! « à la Python » qui permettent de relire les fichiers de la 2.x à l'identique.
//!
//! Ni egui ni base de données ici : les autres crates en dépendent toutes.

pub mod journal;
pub mod paths;
pub mod pyval;

pub use paths::{DataPaths, PathError};
