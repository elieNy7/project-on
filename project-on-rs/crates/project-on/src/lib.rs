//! L'application Project-On (egui) : la régie de la bêta 3.0.

pub mod app;
pub mod data;
pub mod icons;
pub mod library;
pub mod playlist;
pub mod projector;
pub mod screens;
pub mod search;
pub mod service;
pub mod shortcuts;
pub mod stage;
pub mod theme;
pub mod widgets;
pub mod worker;

pub use app::{App, Boot, Config};
