//! L'**image de citation** (Ctrl+Shift+I, `QuoteImageDialog` de la 2.8) : le slide au direct (ou
//! un texte tapé) en image aux couleurs de l'église, pour WhatsApp, Facebook ou Instagram. Huit
//! modèles, trois formats ; un aperçu qui suit la frappe ; « Enregistrer l'image… » (PNG, dans
//! « Documents\Project-On images » par défaut), « Copier l'image » et « Projeter ».

use std::hash::{Hash, Hasher};
use std::path::PathBuf;
use std::time::Instant;

use egui::{RichText, Ui};
use po_design::church::{ChurchProfile, QUOTE_FORMATS, QUOTE_STYLES};

use crate::theme::*;
use crate::widgets::{self, Tone};

/// Ce que la fenêtre demande à la régie.
#[derive(Debug, Clone, PartialEq)]
pub enum QuoteAction {
    /// Enregistrer l'image (PNG) dans ce fichier.
    Save(PathBuf),
    Copy,
    /// Projeter l'image.
    Project,
    /// Garder le modèle choisi dans le profil de l'église.
    RememberStyle(String),
}

/// La fenêtre de l'image de citation.
pub struct QuoteWindow {
    pub open: bool,
    pub text: String,
    pub reference: String,
    pub style: String,
    pub format: String,
    /// L'aperçu et l'empreinte de ce qu'il montre.
    preview: Option<(u64, egui::TextureHandle)>,
    /// « Image copiée ✓ » pendant deux secondes.
    copied: Option<Instant>,
    pub message: String,
}

impl Default for QuoteWindow {
    fn default() -> Self {
        QuoteWindow {
            open: false,
            text: String::new(),
            reference: String::new(),
            style: "classic".into(),
            format: "square".into(),
            preview: None,
            copied: None,
            message: String::new(),
        }
    }
}

/// La largeur et la hauteur d'un format.
pub fn size_of(format: &str) -> (u32, u32) {
    QUOTE_FORMATS.iter().find(|(k, ..)| *k == format).map_or((1080, 1080), |(_, _, w, h)| (*w, *h))
}

/// Le dossier proposé pour les images.
pub fn images_dir() -> Option<PathBuf> {
    std::env::var_os("USERPROFILE").map(|home| PathBuf::from(home).join("Documents").join("Project-On images"))
}

impl QuoteWindow {
    /// Ouvre la fenêtre avec ce texte (le slide au direct) et le modèle du profil.
    pub fn open_with(&mut self, text: &str, reference: &str, profile: &ChurchProfile) {
        self.open = true;
        self.text = text.trim().to_string();
        self.reference = reference.lines().map(str::trim).filter(|l| !l.is_empty()).collect::<Vec<_>>().join("\n");
        self.style = profile.quote_style.clone();
        self.message.clear();
        self.preview = None;
    }

    /// La mise en page de l'image, à sa vraie taille.
    pub fn layout(&self, fonts: &mut po_layout::Fonts, profile: &ChurchProfile) -> po_layout::DisplayList {
        let (w, h) = size_of(&self.format);
        po_layout::church::layout_quote(fonts, profile, &self.text, &self.reference, &self.style, w as f32, h as f32)
    }

    fn fingerprint(&self, profile: &ChurchProfile) -> u64 {
        let mut hasher = std::collections::hash_map::DefaultHasher::new();
        (&self.text, &self.reference, &self.style, &self.format, format!("{profile:?}")).hash(&mut hasher);
        hasher.finish()
    }

    /// La fenêtre. `render(largeur, hauteur)` rend l'image en RVBA prémultiplié à cette taille.
    pub fn show(
        &mut self,
        ctx: &egui::Context,
        profile: &ChurchProfile,
        render: impl FnOnce(&Self, u32, u32) -> Option<Vec<u8>>,
    ) -> Vec<QuoteAction> {
        let mut actions = Vec::new();
        if !self.open {
            return actions;
        }
        // L'aperçu suit le texte, le modèle et le format (rendu seulement quand ils changent).
        let (w, h) = size_of(&self.format);
        let scale = (420.0 / w.max(h) as f32).min(1.0);
        let (pw, ph) = ((w as f32 * scale).round() as u32, (h as f32 * scale).round() as u32);
        let print = self.fingerprint(profile);
        if self.preview.as_ref().is_none_or(|(p, _)| *p != print)
            && let Some(pixels) = render(self, pw, ph)
            && pixels.len() == (pw * ph * 4) as usize
        {
            let image = egui::ColorImage::from_rgba_premultiplied([pw as usize, ph as usize], &pixels);
            let texture = ctx.load_texture("citation", image, egui::TextureOptions::LINEAR);
            self.preview = Some((print, texture));
        }
        let mut open = self.open;
        egui::Window::new("Image de citation")
            .open(&mut open)
            .collapsible(false)
            .resizable(false)
            .default_width(820.0)
            .show(ctx, |ui| {
                ui.horizontal_top(|ui| {
                    ui.vertical(|ui| {
                        ui.set_width(340.0);
                        self.form(ui, profile, &mut actions);
                    });
                    ui.add_space(12.0);
                    if let Some((_, texture)) = &self.preview {
                        ui.add(egui::Image::new(texture).fit_to_exact_size(egui::vec2(pw as f32, ph as f32)));
                    }
                });
            });
        self.open = open;
        if self.copied.is_some_and(|t| t.elapsed().as_secs_f32() < 2.0) {
            ctx.request_repaint_after(std::time::Duration::from_millis(500));
        }
        actions
    }

    fn form(&mut self, ui: &mut Ui, profile: &ChurchProfile, actions: &mut Vec<QuoteAction>) {
        ui.label(RichText::new("Texte").font(medium(12.0)).color(MUTED));
        ui.add(egui::TextEdit::multiline(&mut self.text).desired_rows(6).desired_width(330.0));
        ui.label(RichText::new("Référence").font(medium(12.0)).color(MUTED));
        ui.add(egui::TextEdit::multiline(&mut self.reference).desired_rows(2).desired_width(330.0));
        ui.add_space(4.0);
        ui.label(RichText::new("Modèle").font(medium(12.0)).color(MUTED));
        let shown = QUOTE_STYLES.iter().find(|(k, _)| *k == self.style).map_or("", |(_, l)| *l);
        egui::ComboBox::from_id_salt("citation-modele").selected_text(shown).width(330.0).show_ui(ui, |ui| {
            for (key, label) in QUOTE_STYLES {
                if ui.selectable_label(self.style == key, label).clicked() && self.style != key {
                    self.style = key.to_string();
                    actions.push(QuoteAction::RememberStyle(key.to_string()));
                }
            }
        });
        ui.label(RichText::new("Format").font(medium(12.0)).color(MUTED));
        let shown = QUOTE_FORMATS.iter().find(|(k, ..)| *k == self.format).map_or("", |(_, l, ..)| *l);
        egui::ComboBox::from_id_salt("citation-format").selected_text(shown).width(330.0).show_ui(ui, |ui| {
            for (key, label, ..) in QUOTE_FORMATS {
                ui.selectable_value(&mut self.format, key.to_string(), label);
            }
        });
        if profile.name.is_empty() && profile.logo.is_empty() {
            ui.label(
                RichText::new("Astuce : renseignez le profil de l'église (Réglages) pour signer vos images.")
                    .font(regular(11.5))
                    .color(FAINT),
            );
        }
        ui.add_space(8.0);
        let empty = self.text.trim().is_empty();
        ui.horizontal_wrapped(|ui| {
            if widgets::button_at(
                ui,
                widgets::Size::Normal,
                None,
                "Enregistrer l'image…",
                Tone::Primary(ACCENT),
                !empty,
            )
            .clicked()
            {
                let mut dialog = rfd::FileDialog::new()
                    .set_title("Enregistrer l'image")
                    .add_filter("Image PNG", &["png"])
                    .set_file_name(format!("citation-{}.png", slug(&self.reference)));
                if let Some(dir) = images_dir() {
                    let _ = std::fs::create_dir_all(&dir);
                    dialog = dialog.set_directory(dir);
                }
                if let Some(path) = dialog.save_file() {
                    actions.push(QuoteAction::Save(path.with_extension("png")));
                }
            }
            let copied = self.copied.is_some_and(|t| t.elapsed().as_secs_f32() < 2.0);
            let label = if copied { "Image copiée ✓" } else { "Copier l'image" };
            if widgets::button_at(ui, widgets::Size::Normal, None, label, Tone::Secondary, !empty).clicked() {
                actions.push(QuoteAction::Copy);
                self.copied = Some(Instant::now());
            }
            if widgets::button_at(ui, widgets::Size::Normal, None, "Projeter", Tone::Secondary, !empty)
                .on_hover_text("Mettre l'image au direct")
                .clicked()
            {
                actions.push(QuoteAction::Project);
            }
        });
        if !self.message.is_empty() {
            ui.label(RichText::new(&self.message).font(regular(11.5)).color(MUTED));
        }
    }
}

/// « Jean 3:16 » → « jean-3-16 » (le nom proposé pour le fichier).
fn slug(reference: &str) -> String {
    let first = reference.lines().next().unwrap_or("");
    let mut out = String::new();
    for c in first.chars().flat_map(char::to_lowercase) {
        if c.is_alphanumeric() {
            out.push(c);
        } else if !out.ends_with('-') && !out.is_empty() {
            out.push('-');
        }
    }
    let out = out.trim_end_matches('-').chars().take(40).collect::<String>();
    if out.is_empty() { "image".into() } else { out }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_file_name_comes_from_the_reference() {
        assert_eq!(slug("Jean 3:16\nLouis Segond"), "jean-3-16");
        assert_eq!(slug(""), "image");
        assert_eq!(size_of("story"), (1080, 1920));
        assert_eq!(size_of("inconnu"), (1080, 1080));
    }
}
