//! « Importer un PDF » dans la page Cantiques (`PdfImportDialog` de la 2.8) : le recueil est lu
//! dans un fil à part (`po_pdf`), ses cantiques sont listés (cochés par défaut), avec un préfixe
//! (« CS ») et un numéro de départ pour ceux sans numéro ; l'aperçu montre le titre final
//! (« CS-12. Grâce infinie ») et les strophes. Les cantiques déjà présents (même titre) ne sont pas
//! ajoutés une seconde fois.

use std::path::{Path, PathBuf};
use std::thread::JoinHandle;

use egui::{RichText, Ui};
use po_db::{Database, Mode};
use po_pdf::PdfHymn;

use crate::theme::*;
use crate::widgets::{self, Tone};

/// Le titre d'un cantique importé : « PRÉFIXE-numéro. Nom » (`_effective_title` de la 2.8). Un
/// titre déjà de la forme « XX-12. Nom » garde son nom.
pub fn final_title(prefix: &str, number: &str, title: &str) -> String {
    let name = title
        .split_once(". ")
        .filter(|(head, _)| {
            let digits = head.rsplit('-').next().unwrap_or("");
            !digits.is_empty() && digits.chars().all(|c| c.is_ascii_digit())
        })
        .map_or(title, |(_, rest)| rest);
    format!("{prefix}-{number}. {name}")
}

/// Le numéro final : celui du recueil, sinon le numéro de départ plus le rang (`_effective_number`).
fn final_number(hymn: &PdfHymn, start: u32, rank: usize) -> String {
    if hymn.number.chars().all(|c| c.is_ascii_digit()) && !hymn.number.is_empty() {
        match hymn.number.trim_start_matches('0') {
            "" => "0".to_string(),
            n => n.to_string(),
        }
    } else {
        (start as usize + rank).to_string()
    }
}

enum Job {
    Reading(JoinHandle<Result<Vec<PdfHymn>, String>>),
    Importing(JoinHandle<Result<(usize, usize), String>>),
}

/// La fenêtre d'import.
pub struct PdfImport {
    pub open: bool,
    file: Option<PathBuf>,
    hymns: Vec<PdfHymn>,
    chosen: Vec<bool>,
    shown: usize,
    pub prefix: String,
    start: u32,
    job: Option<Job>,
    pub message: String,
}

impl Default for PdfImport {
    fn default() -> Self {
        PdfImport {
            open: false,
            file: None,
            hymns: Vec::new(),
            chosen: Vec::new(),
            shown: 0,
            prefix: "PDF".into(),
            start: 1,
            job: None,
            message: String::new(),
        }
    }
}

impl PdfImport {
    pub fn busy(&self) -> bool {
        self.job.is_some()
    }

    /// Les cantiques trouvés (essais).
    pub fn found(&self) -> &[PdfHymn] {
        &self.hymns
    }

    /// Lit un recueil (dans un fil à part).
    pub fn read(&mut self, path: PathBuf) {
        self.open = true;
        self.hymns.clear();
        self.chosen.clear();
        self.shown = 0;
        // Le préfixe proposé : les deux premières lettres du nom du fichier (comme l'import en série
        // de la 2.8).
        let stem = path.file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
        let letters: String = stem.chars().filter(|c| c.is_alphabetic()).take(2).collect::<String>().to_uppercase();
        if letters.chars().count() == 2 {
            self.prefix = letters;
        }
        self.message = format!("Lecture de « {} »…", path.file_name().map(|n| n.to_string_lossy()).unwrap_or_default());
        let file = path.clone();
        self.file = Some(path);
        self.job = Some(Job::Reading(std::thread::spawn(move || po_pdf::hymns_from_pdf(&file))));
    }

    fn import(&mut self, db_path: &Path) {
        let prefix = self.prefix.trim().to_uppercase();
        let prefix = if prefix.is_empty() { "PDF".to_string() } else { prefix };
        let start = self.start;
        let selected: Vec<(String, Vec<String>)> = self
            .hymns
            .iter()
            .zip(&self.chosen)
            .filter(|(_, on)| **on)
            .enumerate()
            .map(|(rank, (h, _))| (final_title(&prefix, &final_number(h, start, rank), &h.title), h.stanzas.clone()))
            .collect();
        let path = db_path.to_path_buf();
        self.message = format!("Import de {} cantique(s)…", selected.len());
        self.job = Some(Job::Importing(std::thread::spawn(move || {
            let mut db = Database::open(&path, Mode::ReadWrite).map_err(|e| e.to_string())?;
            let (mut added, mut skipped) = (0, 0);
            for (title, stanzas) in &selected {
                if db.hymn_exists(title).map_err(|e| e.to_string())? {
                    skipped += 1;
                    continue;
                }
                db.import_hymn(title, stanzas, None, "fr").map_err(|e| e.to_string())?;
                added += 1;
            }
            db.update_prefix_sort_keys(&prefix).map_err(|e| e.to_string())?;
            Ok((added, skipped))
        })));
    }

    /// La fenêtre ; rend vrai quand des cantiques ont été ajoutés (la liste se recharge).
    pub fn show(&mut self, ctx: &egui::Context, db_path: &Path) -> bool {
        let mut changed = false;
        match self.job.take() {
            Some(Job::Reading(h)) if h.is_finished() => {
                match h.join().unwrap_or_else(|_| Err("lecture interrompue".into())) {
                    Ok(hymns) if hymns.is_empty() => self.message = "Aucun cantique trouvé dans ce PDF.".into(),
                    Ok(hymns) => {
                        self.message.clear();
                        self.chosen = vec![true; hymns.len()];
                        self.hymns = hymns;
                    }
                    Err(e) => self.message = e,
                }
            }
            Some(Job::Importing(h)) if h.is_finished() => {
                match h.join().unwrap_or_else(|_| Err("import interrompu".into())) {
                    Ok((added, skipped)) => {
                        self.message = match skipped {
                            0 => format!("{added} cantique(s) importé(s)."),
                            n => format!("{added} cantique(s) importé(s), {n} déjà présent(s)."),
                        };
                        changed = added > 0;
                    }
                    Err(e) => self.message = format!("Import interrompu : {e}"),
                }
                po_core::journal::line(&format!("import PDF : {}", self.message));
            }
            other => self.job = other,
        }
        if self.job.is_some() {
            ctx.request_repaint_after(std::time::Duration::from_millis(200));
        }
        if !self.open {
            return changed;
        }
        let mut open = self.open;
        let name =
            self.file.as_ref().and_then(|f| f.file_name()).map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
        egui::Window::new(format!("Importer « {name} »"))
            .open(&mut open)
            .collapsible(false)
            .default_size([860.0, 560.0])
            .show(ctx, |ui| self.body(ui, db_path));
        self.open = open;
        changed
    }

    fn body(&mut self, ui: &mut Ui, db_path: &Path) {
        if let Some(Job::Reading(_) | Job::Importing(_)) = &self.job {
            ui.horizontal(|ui| {
                ui.spinner();
                ui.label(RichText::new(&self.message).font(medium(12.5)).color(WARN));
            });
            return;
        }
        if self.hymns.is_empty() {
            ui.label(RichText::new(&self.message).font(medium(12.5)).color(MUTED));
            return;
        }
        let count = self.chosen.iter().filter(|c| **c).count();
        ui.horizontal(|ui| {
            ui.label(
                RichText::new(format!("{} cantique(s) trouvé(s)", self.hymns.len())).font(semibold(13.0)).color(TEXT),
            );
            ui.add_space(16.0);
            ui.label(RichText::new("Préfixe").font(regular(12.0)).color(MUTED));
            let r = ui.add(egui::TextEdit::singleline(&mut self.prefix).desired_width(60.0));
            ui.ctx().accesskit_node_builder(r.id, |n| n.set_label("Champ : préfixe"));
            ui.label(RichText::new("Numéro de départ (sans numéro)").font(regular(12.0)).color(MUTED));
            ui.add(egui::DragValue::new(&mut self.start).range(1..=9999));
        });
        ui.horizontal(|ui| {
            let label = format!("Importer la sélection ({count})");
            if widgets::button_at(ui, widgets::Size::Normal, None, &label, Tone::Primary(ACCENT), count > 0).clicked() {
                self.import(db_path);
            }
            ui.label(
                RichText::new("Un cantique de même titre déjà présent n'est pas ajouté une seconde fois.")
                    .font(regular(11.5))
                    .color(FAINT),
            );
        });
        if !self.message.is_empty() {
            ui.label(RichText::new(&self.message).font(regular(12.0)).color(PREVIEW));
        }
        ui.add_space(6.0);
        let prefix = if self.prefix.trim().is_empty() { "PDF".to_string() } else { self.prefix.trim().to_uppercase() };
        ui.horizontal_top(|ui| {
            ui.vertical(|ui| {
                ui.set_width(360.0);
                ui.horizontal(|ui| {
                    if ui.small_button("Tout cocher").clicked() {
                        self.chosen.iter_mut().for_each(|c| *c = true);
                    }
                    if ui.small_button("Tout décocher").clicked() {
                        self.chosen.iter_mut().for_each(|c| *c = false);
                    }
                });
                egui::ScrollArea::vertical().id_salt("pdf-liste").max_height(380.0).show_rows(
                    ui,
                    22.0,
                    self.hymns.len(),
                    |ui, range| {
                        for i in range {
                            ui.horizontal(|ui| {
                                ui.checkbox(&mut self.chosen[i], "");
                                let h = &self.hymns[i];
                                let label = format!("{} · {}", h.number, h.title);
                                if ui.selectable_label(self.shown == i, label).clicked() {
                                    self.shown = i;
                                }
                            });
                        }
                    },
                );
            });
            ui.separator();
            ui.vertical(|ui| {
                if let Some(h) = self.hymns.get(self.shown) {
                    let rank = self.chosen.iter().take(self.shown).filter(|c| **c).count();
                    let title = final_title(&prefix, &final_number(h, self.start, rank), &h.title);
                    ui.label(RichText::new(title).font(semibold(14.0)).color(TEXT));
                    ui.label(RichText::new(format!("{} strophe(s)", h.stanzas.len())).font(regular(11.5)).color(FAINT));
                    egui::ScrollArea::vertical().id_salt("pdf-apercu").max_height(380.0).show(ui, |ui| {
                        for s in &h.stanzas {
                            ui.label(RichText::new(s).font(regular(12.5)).color(MUTED));
                            ui.add_space(6.0);
                        }
                    });
                }
            });
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn imported_titles_are_numbered_like_the_2_8() {
        assert_eq!(final_title("CS", "12", "Grâce Infinie"), "CS-12. Grâce Infinie");
        assert_eq!(final_title("CS", "12", "AB-7. Déjà Numéroté"), "CS-12. Déjà Numéroté");
        let h = |n: &str| PdfHymn { number: n.into(), title: String::new(), stanzas: Vec::new() };
        assert_eq!(final_number(&h("012"), 1, 0), "12");
        assert_eq!(final_number(&h("137B"), 50, 3), "53");
    }
}
