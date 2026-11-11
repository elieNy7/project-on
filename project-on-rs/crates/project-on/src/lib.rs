//! L'application Project-On (egui) : la régie de la bêta 3.0.

pub mod app;
pub mod data;
pub mod designs;
pub mod gpu;
pub mod history;
pub mod hymn_editor;
pub mod icons;
pub mod library;
pub mod maintenance;
pub mod media;
pub mod outputs;
pub mod overlay;
pub mod playlist;
pub mod projector;
pub mod recovery;
pub mod screens;
pub mod search;
pub mod service;
pub mod settings_page;
pub mod shortcuts;
pub mod stage;
pub mod theme;
pub mod transfer;
pub mod web;
pub mod widgets;
pub mod worker;

pub use app::{App, Boot, Config};
