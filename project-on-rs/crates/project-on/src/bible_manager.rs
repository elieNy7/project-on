//! « Gérer les Bibles » (`BibleManagerDialog` de la 2.8), depuis la page Bible : les traductions
//! installées (et les supprimer), les Bibles fournies avec Project-On, le catalogue des Bibles du
//! domaine public à télécharger, et l'import d'un fichier (XML Zefania ou Beblia, JSON) pour une
//! version dont l'église détient les droits (lingala, swahili, tshiluba…).
//!
//! Lire et installer une Bible (30 000 versets) se fait dans un fil à part, sur une connexion à
//! elle : la régie ne se fige pas. Le téléchargement passe par `curl.exe`, fourni avec Windows.

use std::path::{Path, PathBuf};
use std::thread::JoinHandle;

use egui::{RichText, Ui};
use po_db::bibles::{CATALOG, CatalogEntry, InstalledBible, LANGS, load_bible_file};
use po_db::{Database, Mode};

use crate::theme::*;
use crate::widgets::{self, Tone};

/// Le dossier des Bibles fournies : à côté de l'exécutable, sinon celui du dépôt (essais).
pub fn bundled_dir() -> Option<PathBuf> {
    let beside = std::env::current_exe().ok().and_then(|exe| exe.parent().map(|d| d.join("bibles")));
    let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../bibles");
    beside.into_iter().chain([repo]).find(|d| d.is_dir())
}

/// Les fichiers des Bibles fournies : (module, chemin).
pub fn bundled_files() -> Vec<(String, PathBuf)> {
    let Some(dir) = bundled_dir() else { return Vec::new() };
    let Ok(entries) = std::fs::read_dir(dir) else { return Vec::new() };
    let mut out: Vec<(String, PathBuf)> = entries
        .flatten()
        .map(|e| e.path())
        .filter_map(|p| {
            let name = p.file_name()?.to_string_lossy().to_string();
            Some((name.strip_suffix(".json.gz")?.to_string(), p))
        })
        .collect();
    out.sort();
    out
}

/// Télécharge une Bible du catalogue et la convertit (sans l'installer).
pub fn download(entry: &CatalogEntry) -> Result<po_db::bibles::BiblePayload, String> {
    let file = std::env::temp_dir().join(format!("project-on-{}.json", entry.code));
    let mut cmd = std::process::Command::new("curl.exe");
    cmd.args(["-L", "--fail", "--silent", "--show-error", "--max-time", "300", "-o"]).arg(&file).arg(entry.url());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000);
    }
    let output = cmd.output().map_err(|e| format!("téléchargement impossible : {e}"))?;
    if !output.status.success() {
        let _ = std::fs::remove_file(&file);
        return Err(format!(
            "téléchargement impossible (connexion ?) : {}",
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    let text = std::fs::read_to_string(&file).map_err(|e| e.to_string());
    let _ = std::fs::remove_file(&file);
    let data: serde_json::Value =
        serde_json::from_str(text?.trim_start_matches('\u{feff}')).map_err(|e| e.to_string())?;
    let payload = po_db::bibles::from_scrollmapper(
        &data,
        &entry.module(),
        entry.shortname,
        entry.name,
        entry.lang,
        entry.license,
    );
    if payload.verses.len() < 1000 {
        return Err(format!("Bible incomplète ({} versets)", payload.verses.len()));
    }
    Ok(payload)
}

/// Ce qu'on installe.
enum Source {
    File { path: PathBuf, shortname: String, lang: String },
    Catalog(CatalogEntry),
}

/// La fenêtre.
pub struct BibleManager {
    pub open: bool,
    /// Pour l'import d'un fichier.
    lang: String,
    shortname: String,
    /// L'installation en cours : ce qu'elle installe, et son fil.
    job: Option<(String, JoinHandle<Result<String, String>>)>,
    pub message: String,
    confirm_remove: Option<InstalledBible>,
    installed: Option<Vec<InstalledBible>>,
}

impl Default for BibleManager {
    fn default() -> Self {
        BibleManager {
            open: false,
            lang: "fr".into(),
            shortname: String::new(),
            job: None,
            message: String::new(),
            confirm_remove: None,
            installed: None,
        }
    }
}

impl BibleManager {
    pub fn busy(&self) -> bool {
        self.job.is_some()
    }

    fn start(&mut self, label: String, db_path: &Path, source: Source) {
        let path = db_path.to_path_buf();
        self.message = format!("Installation : {label}…");
        po_core::journal::line(&format!("Bibles : installation de {label}"));
        let handle = std::thread::spawn(move || {
            let payload = match source {
                Source::File { path, shortname, lang } => {
                    load_bible_file(&path, &shortname, &lang).map_err(|e| e.to_string())?
                }
                Source::Catalog(entry) => download(&entry)?,
            };
            if payload.verses.is_empty() {
                return Err("aucun verset reconnu dans ce fichier".into());
            }
            let mut db = Database::open(&path, Mode::ReadWrite).map_err(|e| e.to_string())?;
            db.install_bible(&payload).map_err(|e| e.to_string())?;
            let name = if payload.shortname.is_empty() { payload.name.clone() } else { payload.shortname.clone() };
            Ok(format!("{name} installée ({} versets)", payload.verses.len()))
        });
        self.job = Some((label, handle));
    }

    /// La fenêtre. Rend vrai quand les traductions ont changé (la page Bible se recharge).
    pub fn show(&mut self, ctx: &egui::Context, db: &mut Database, db_path: &Path) -> bool {
        let mut changed = false;
        if self.job.as_ref().is_some_and(|(_, h)| h.is_finished())
            && let Some((label, handle)) = self.job.take()
        {
            self.message = match handle.join().unwrap_or_else(|_| Err("installation interrompue".into())) {
                Ok(done) => {
                    changed = true;
                    done
                }
                Err(e) => format!("{label} : {e}"),
            };
            po_core::journal::line(&format!("Bibles : {}", self.message));
            self.installed = None;
        }
        if self.job.is_some() {
            ctx.request_repaint_after(std::time::Duration::from_millis(200));
        }
        if !self.open {
            return changed;
        }
        if self.installed.is_none() {
            self.installed = Some(db.installed_bibles().unwrap_or_default());
        }
        let installed = self.installed.clone().unwrap_or_default();
        let removed = db.removed_bibles();
        let mut open = self.open;
        egui::Window::new("Gérer les Bibles")
            .open(&mut open)
            .collapsible(false)
            .default_width(620.0)
            .default_height(560.0)
            .show(ctx, |ui| {
                egui::ScrollArea::vertical().max_height(560.0).show(ui, |ui| {
                    changed |= self.body(ui, db, db_path, &installed, &removed);
                });
            });
        self.open = open;
        changed
    }

    fn body(
        &mut self,
        ui: &mut Ui,
        db: &mut Database,
        db_path: &Path,
        installed: &[InstalledBible],
        removed: &std::collections::BTreeSet<String>,
    ) -> bool {
        let mut changed = false;
        let busy = self.job.is_some();
        if !self.message.is_empty() {
            ui.horizontal(|ui| {
                if busy {
                    ui.spinner();
                }
                ui.label(RichText::new(&self.message).font(medium(12.5)).color(if busy { WARN } else { MUTED }));
            });
            ui.add_space(6.0);
        }
        widgets::section(ui, "Installées");
        for b in installed {
            ui.horizontal(|ui| {
                let title =
                    if b.shortname.is_empty() { b.name.clone() } else { format!("{} — {}", b.shortname, b.name) };
                ui.add_sized(
                    [400.0, 22.0],
                    egui::Label::new(RichText::new(title).font(medium(12.5)).color(TEXT)).truncate(),
                );
                ui.label(
                    RichText::new(format!("{} · {} versets", lang_label(&b.lang), b.verses))
                        .font(regular(11.5))
                        .color(MUTED),
                );
                if installed.len() > 1
                    && widgets::button_at(ui, widgets::Size::Small, None, "Supprimer", Tone::Danger, !busy)
                        .on_hover_text(format!("Supprimer « {} » de la base", b.name))
                        .clicked()
                {
                    self.confirm_remove = Some(b.clone());
                }
            });
        }
        if let Some(b) = self.confirm_remove.clone() {
            widgets::card(ui, |ui| {
                ui.label(
                    RichText::new(format!("Supprimer « {} » ({} versets) ?", b.name, b.verses))
                        .font(semibold(12.5))
                        .color(TEXT),
                );
                ui.label(
                    RichText::new("Elle pourra être réinstallée depuis cette fenêtre.")
                        .font(regular(11.5))
                        .color(MUTED),
                );
                ui.horizontal(|ui| {
                    if widgets::button(ui, None, "Supprimer", Tone::Danger).clicked() {
                        self.message = match db.remove_bible(&b.module) {
                            Ok(_) => format!("{} supprimée", b.name),
                            Err(e) => format!("Suppression impossible : {e}"),
                        };
                        self.confirm_remove = None;
                        self.installed = None;
                        changed = true;
                    }
                    if widgets::button(ui, None, "Annuler", Tone::Secondary).clicked() {
                        self.confirm_remove = None;
                    }
                });
            });
        }

        let present: std::collections::BTreeSet<&str> = installed.iter().map(|b| b.module.as_str()).collect();
        let bundled: Vec<(String, PathBuf)> =
            bundled_files().into_iter().filter(|(m, _)| !present.contains(m.as_str())).collect();
        if !bundled.is_empty() {
            widgets::section(ui, "Fournies avec Project-On");
            for (module, path) in bundled {
                let entry = CATALOG.iter().find(|e| e.module() == module);
                let name = entry.map_or(module.clone(), |e| e.name.to_string());
                ui.horizontal(|ui| {
                    ui.add_sized(
                        [400.0, 22.0],
                        egui::Label::new(RichText::new(&name).font(medium(12.5)).color(TEXT)).truncate(),
                    );
                    if removed.contains(&module) {
                        ui.label(RichText::new("supprimée").font(regular(11.5)).color(FAINT));
                    }
                    if widgets::button_at(ui, widgets::Size::Small, None, "Installer", Tone::Secondary, !busy).clicked()
                    {
                        let lang = entry.map_or("fr", |e| e.lang).to_string();
                        self.start(
                            name.clone(),
                            db_path,
                            Source::File { path: path.clone(), shortname: String::new(), lang },
                        );
                    }
                });
            }
        }

        widgets::section(ui, "Catalogue en ligne (domaine public)");
        ui.label(
            RichText::new(
                "Téléchargées depuis le projet scrollmapper/bible_databases (GitHub) ; une connexion est nécessaire.",
            )
            .font(regular(11.5))
            .color(FAINT),
        );
        for entry in CATALOG.iter().filter(|e| !present.contains(e.module().as_str())) {
            ui.horizontal(|ui| {
                ui.add_sized(
                    [400.0, 22.0],
                    egui::Label::new(RichText::new(entry.name).font(medium(12.5)).color(TEXT)).truncate(),
                )
                .on_hover_text(if entry.note.is_empty() { entry.license } else { entry.note });
                ui.label(RichText::new(lang_label(entry.lang)).font(regular(11.5)).color(MUTED));
                if widgets::button_at(ui, widgets::Size::Small, None, "Télécharger", Tone::Secondary, !busy).clicked()
                {
                    self.start(entry.name.to_string(), db_path, Source::Catalog(*entry));
                }
            });
        }

        widgets::section(ui, "Importer un fichier");
        ui.label(
            RichText::new("Une Bible en XML (Zefania, Beblia) ou en JSON (scrollmapper, Project-On), éventuellement .gz : pour une version dont votre église détient les droits.")
                .font(regular(11.5))
                .color(FAINT),
        );
        ui.horizontal(|ui| {
            ui.label(RichText::new("Langue").font(regular(12.0)).color(MUTED));
            egui::ComboBox::from_id_salt("bible-langue").selected_text(lang_label(&self.lang)).width(140.0).show_ui(
                ui,
                |ui| {
                    for (code, label) in LANGS {
                        ui.selectable_value(&mut self.lang, code.to_string(), label);
                    }
                },
            );
            ui.label(RichText::new("Nom court").font(regular(12.0)).color(MUTED));
            ui.add(egui::TextEdit::singleline(&mut self.shortname).hint_text("Lingala 1952").desired_width(140.0));
            if widgets::button_at(ui, widgets::Size::Normal, None, "Choisir le fichier…", Tone::Secondary, !busy)
                .clicked()
                && let Some(path) = rfd::FileDialog::new()
                    .set_title("Bible à importer")
                    .add_filter("Bible", &["xml", "json", "gz"])
                    .pick_file()
            {
                let label = path.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
                let (shortname, lang) = (self.shortname.trim().to_string(), self.lang.clone());
                self.start(label, db_path, Source::File { path, shortname, lang });
            }
        });
        changed
    }
}

fn lang_label(code: &str) -> String {
    LANGS.iter().find(|(c, _)| *c == code).map_or_else(|| code.to_string(), |(_, l)| (*l).to_string())
}
