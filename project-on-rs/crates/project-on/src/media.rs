//! Les médias : pour commencer, le **diaporama** (`slideshow_controller.py` de la 2.8). Il prend le
//! direct et enchaîne des images, chacune sa durée (8 s par défaut, 0 : à la main), en boucle. À
//! l'arrêt, le direct d'avant revient **à l'identique** ; toute action manuelle rend la main à
//! l'opérateur (une flèche arrête le diaporama puis agit sur le direct rendu ; un nouveau
//! programme mis au direct le clôt sans rien restaurer). Les images viennent d'un dossier, ou de la
//! playlist choisie.

use std::path::Path;

use egui::{RichText, Ui};
use po_design::SlideSource;
use po_program::{Cue, Entry};

use crate::theme::*;
use crate::widgets::{self, Tone};

/// Une image du diaporama.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Media {
    pub name: String,
    pub path: String,
    /// Sa durée en secondes ; 0 : celle par défaut.
    pub seconds: u32,
}

/// L'ordre « naturel » des noms : « photo 2 » avant « photo 10 ».
fn natural_key(name: &str) -> Vec<(u8, u64, String)> {
    let mut key = Vec::new();
    let mut digits = String::new();
    let mut text = String::new();
    for c in name.to_lowercase().chars() {
        if c.is_ascii_digit() {
            if !text.is_empty() {
                key.push((1, 0, std::mem::take(&mut text)));
            }
            digits.push(c);
        } else {
            if !digits.is_empty() {
                key.push((0, digits.parse().unwrap_or(u64::MAX), std::mem::take(&mut digits)));
            }
            text.push(c);
        }
    }
    if !digits.is_empty() {
        key.push((0, digits.parse().unwrap_or(u64::MAX), digits));
    }
    if !text.is_empty() {
        key.push((1, 0, text));
    }
    key
}

/// Les images d'un dossier (sans ses sous-dossiers), dans l'ordre naturel des noms.
pub fn folder_images(dir: &Path) -> Vec<Media> {
    let Ok(entries) = std::fs::read_dir(dir) else { return Vec::new() };
    let mut out: Vec<Media> = entries
        .flatten()
        .map(|e| e.path())
        .filter(|p| {
            let path = p.to_string_lossy();
            p.is_file() && (crate::playlist::is_image_file(&path) || crate::video::is_video_file(&path))
        })
        .map(|p| Media {
            name: p.file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default(),
            path: p.to_string_lossy().to_string(),
            seconds: 0,
        })
        .collect();
    out.sort_by_key(|m| natural_key(&m.name));
    out
}

/// Le programme du diaporama : une image par slide.
pub fn cue(medias: &[Media], title: &str) -> Option<Cue> {
    if medias.is_empty() {
        return None;
    }
    let entries = medias.iter().map(|m| Entry::new(m.name.clone(), String::new())).collect();
    let mut cue = Cue::new(SlideSource::Custom, if title.trim().is_empty() { "Diaporama" } else { title }, entries, 0);
    cue.split = false;
    cue.kinds = vec![SlideSource::Custom; medias.len()];
    cue.backgrounds = medias.iter().map(|m| Some(m.path.clone())).collect();
    Some(cue)
}

/// L'enchaînement : la durée de chaque image et le prochain changement (temps de l'interface).
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Slideshow {
    pub active: bool,
    durations: Vec<u32>,
    pub default_seconds: u32,
    next_at: Option<f64>,
}

impl Slideshow {
    pub fn begin(&mut self, medias: &[Media], default_seconds: u32) {
        self.active = true;
        self.durations = medias.iter().map(|m| m.seconds).collect();
        self.default_seconds = default_seconds;
        self.next_at = None;
    }

    pub fn end(&mut self) {
        self.active = false;
        self.next_at = None;
    }

    /// La durée de l'image `row` (la sienne, sinon celle par défaut ; 0 : à la main).
    pub fn seconds(&self, row: usize) -> u32 {
        match self.durations.get(row) {
            Some(&s) if s > 0 => s,
            _ => self.default_seconds,
        }
    }

    /// Une vidéo au direct : elle donne le tempo (on avancera à sa fin), pas de minuterie.
    pub fn hold(&mut self) {
        self.next_at = None;
    }

    /// L'image `row` vient de passer au direct à `now` : la minuterie se réarme avec sa durée.
    pub fn arm(&mut self, row: usize, now: f64) {
        let seconds = self.seconds(row);
        self.next_at = (self.active && seconds > 0).then(|| now + f64::from(seconds.min(3600)));
    }

    /// L'heure du prochain changement, s'il y en a un.
    pub fn next_at(&self) -> Option<f64> {
        self.next_at
    }

    /// Faut-il passer à l'image suivante ?
    pub fn due(&self, now: f64) -> bool {
        self.active && self.next_at.is_some_and(|t| now >= t)
    }

    /// L'image après `row` (la première après la dernière : en boucle).
    pub fn following(row: usize, count: usize) -> usize {
        if count == 0 { 0 } else { (row + 1) % count }
    }
}

/// Ce que la page Médias demande à la régie.
#[derive(Debug, Clone, PartialEq)]
pub enum MediaAction {
    Start(Vec<Media>, String),
    Stop,
    Church(ChurchScreen),
}

/// Un écran de l'église.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ChurchScreen {
    Welcome,
    Speaker,
    Socials,
}

impl ChurchScreen {
    /// (nom du fichier, libellé).
    pub fn names(self) -> (&'static str, &'static str) {
        match self {
            ChurchScreen::Welcome => ("accueil", "Accueil"),
            ChurchScreen::Speaker => ("orateur-du-jour", "Orateur du jour"),
            ChurchScreen::Socials => ("reseaux-sociaux", "Réseaux sociaux"),
        }
    }
}

/// La page Médias.
#[derive(Debug, Clone, Default)]
pub struct MediaView {
    pub folder: String,
    pub found: Vec<Media>,
    scanned: Option<String>,
    pub seconds: u32,
}

impl MediaView {
    /// La page, avec la durée par image des réglages (`media_default_duration`).
    pub fn new(seconds: u32) -> Self {
        MediaView { seconds, ..MediaView::default() }
    }

    fn rescan(&mut self) {
        let folder = self.folder.trim().trim_matches('"').to_string();
        if self.scanned.as_deref() != Some(folder.as_str()) {
            self.found = if folder.is_empty() { Vec::new() } else { folder_images(Path::new(&folder)) };
            self.scanned = Some(folder);
        }
    }

    /// La page. `running` : le diaporama en cours (image, nombre).
    pub fn ui(&mut self, ui: &mut Ui, running: Option<(usize, usize)>) -> Vec<MediaAction> {
        let mut actions = Vec::new();
        self.rescan();
        ui.add_space(12.0);
        ui.label(RichText::new("Médias").font(bold(20.0)).color(TEXT));
        ui.add_space(4.0);
        widgets::card(ui, |ui| {
            ui.set_width(ui.available_width());
            ui.label(RichText::new("ÉCRANS DE L'ÉGLISE").font(semibold(10.5)).color(FAINT));
            ui.add_space(4.0);
            ui.horizontal(|ui| {
                for (screen, label) in [
                    (ChurchScreen::Welcome, "Accueil  Ctrl+Maj+W"),
                    (ChurchScreen::Speaker, "Orateur du jour  Ctrl+Maj+P"),
                    (ChurchScreen::Socials, "Réseaux sociaux  Ctrl+Maj+R"),
                ] {
                    if widgets::button(ui, None, label, Tone::Secondary).clicked() {
                        actions.push(MediaAction::Church(screen));
                    }
                }
            });
            ui.label(
                RichText::new(
                    "Le nom, le logo, les horaires et les réseaux se règlent dans Réglages → Profil de l'église.",
                )
                .font(regular(11.5))
                .color(FAINT),
            );
        });
        ui.add_space(8.0);
        widgets::card(ui, |ui| {
            ui.set_width(ui.available_width());
            ui.label(RichText::new("DIAPORAMA D'UN DOSSIER").font(semibold(10.5)).color(FAINT));
            ui.add_space(4.0);
            ui.horizontal(|ui| {
                let r = ui.add(
                    egui::TextEdit::singleline(&mut self.folder)
                        .hint_text("C:\\Users\\…\\Images\\Annonces")
                        .desired_width(420.0),
                );
                ui.ctx().accesskit_node_builder(r.id, |n| n.set_label("Dossier d'images"));
                if widgets::button(ui, None, "Choisir…", Tone::Secondary).clicked()
                    && let Some(dir) = rfd::FileDialog::new().set_title("Dossier d'images du diaporama").pick_folder()
                {
                    self.folder = dir.to_string_lossy().to_string();
                }
            });
            let count = self.found.len();
            let detail = match (self.folder.trim().is_empty(), count) {
                (true, _) => "Choisissez un dossier : ses images défilent dans l'ordre de leurs noms.".to_string(),
                (false, 0) => "Aucune image ni vidéo dans ce dossier.".to_string(),
                (false, n) => format!("{n} média(s)"),
            };
            ui.label(RichText::new(detail).font(regular(12.0)).color(MUTED));
            ui.horizontal(|ui| {
                ui.label(RichText::new("Durée par image").font(regular(12.5)).color(MUTED));
                ui.add(egui::DragValue::new(&mut self.seconds).range(0..=600).suffix(" s"));
                ui.label(RichText::new("(0 : on avance à la main)").font(regular(11.5)).color(FAINT));
            });
            ui.add_space(6.0);
            ui.horizontal(|ui| match running {
                Some((index, total)) => {
                    if widgets::button(ui, None, "Arrêter le diaporama", Tone::Primary(LIVE)).clicked() {
                        actions.push(MediaAction::Stop);
                    }
                    ui.label(RichText::new(format!("Image {} / {total}", index + 1)).font(semibold(12.5)).color(TEXT));
                    ui.label(
                        RichText::new("Une flèche ou un autre contenu au direct rend la main.")
                            .font(regular(11.5))
                            .color(FAINT),
                    );
                }
                None => {
                    let enabled = count > 0;
                    if widgets::button_at(
                        ui,
                        widgets::Size::Normal,
                        None,
                        "Lancer le diaporama",
                        Tone::Primary(ACCENT),
                        enabled,
                    )
                    .clicked()
                    {
                        let title = Path::new(self.folder.trim())
                            .file_name()
                            .map_or_else(|| "Diaporama".to_string(), |n| n.to_string_lossy().to_string());
                        actions.push(MediaAction::Start(self.found.clone(), title));
                    }
                }
            });
        });
        actions
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_folder_gives_its_images_in_natural_order() {
        let dir = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/tmp")
            .join(format!("diaporama-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(dir.join("sous-dossier")).unwrap();
        for name in ["photo 10.jpg", "photo 2.PNG", "Accueil.webp", "notes.txt", "photo 1.jpeg", "clip.mp4"] {
            std::fs::write(dir.join(name), b"x").unwrap();
        }
        let names: Vec<String> = folder_images(&dir).into_iter().map(|m| m.name).collect();
        assert_eq!(names, ["Accueil", "clip", "photo 1", "photo 2", "photo 10"], "images et vidéos");
        assert!(folder_images(&dir.join("absent")).is_empty());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn the_slideshow_program_has_one_image_per_slide() {
        let medias: Vec<Media> = ["a", "b", "c"]
            .iter()
            .map(|n| Media { name: (*n).into(), path: format!("C:/img/{n}.png"), seconds: 0 })
            .collect();
        let prepared = cue(&medias, "Annonces").unwrap();
        let program = po_program::Program::from_cue(&prepared, &po_settings::SplitSettings::default()).unwrap();
        assert_eq!(program.len(), 3);
        assert_eq!(program.title, "Annonces");
        assert_eq!(program.slide().background.as_deref(), Some("C:/img/a.png"));
        assert!(cue(&[], "x").is_none());
    }

    #[test]
    fn each_image_keeps_its_time_then_the_show_loops() {
        let medias = vec![
            Media { name: "a".into(), path: "a.png".into(), seconds: 0 },
            Media { name: "b".into(), path: "b.png".into(), seconds: 3 },
        ];
        let mut show = Slideshow::default();
        show.begin(&medias, 8);
        show.arm(0, 100.0);
        assert!(!show.due(107.9));
        assert!(show.due(108.0), "8 s par défaut");
        show.arm(1, 108.0);
        assert!(show.due(111.0), "sa propre durée : 3 s");
        assert_eq!(Slideshow::following(1, 2), 0, "en boucle");
        // 0 par défaut et pas de durée propre : on avance à la main.
        show.begin(&medias, 0);
        show.arm(0, 0.0);
        assert_eq!(show.next_at(), None);
        show.end();
        assert!(!show.due(1e9));
    }
}
