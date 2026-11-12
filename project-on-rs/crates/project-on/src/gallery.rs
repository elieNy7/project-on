//! La **galerie des photos de l'église** (`ChurchPhotoGallery` de la 2.8), dans Réglages → Profil
//! de l'église : des vignettes, « Ajouter des photos… » (plusieurs à la fois, copiées dans les
//! données de Project-On : elles restent utilisables si l'original est déplacé), « Retirer ». Les
//! photos servent au modèle « Photo » des images de citation, et la 3.0 les projette aussi en
//! diaporama (avant le culte, pendant une annonce).
//!
//! Les vignettes sont décodées dans un fil à part : une galerie de grandes photos ne fige pas la
//! régie.

use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::sync::mpsc::{Receiver, Sender, channel};

use egui::{RichText, Ui};

use crate::theme::*;
use crate::widgets::{self, Tone};

/// La taille des vignettes.
const THUMB: [u32; 2] = [192, 108];

/// Ce que la galerie demande.
#[derive(Debug, Clone, PartialEq)]
pub enum GalleryAction {
    /// Projeter ces photos en diaporama.
    Project(Vec<String>),
}

/// Une vignette décodée : chemin, pixels RVBA (ou rien : illisible).
type Decoded = (String, Option<([usize; 2], Vec<u8>)>);

/// La galerie et ses vignettes.
pub struct Gallery {
    /// Le dossier où les photos ajoutées sont copiées (`data\church\photos`, comme la 2.8).
    pub folder: Option<PathBuf>,
    thumbs: HashMap<String, egui::TextureHandle>,
    failed: HashSet<String>,
    loading: HashSet<String>,
    done_tx: Sender<Decoded>,
    done_rx: Receiver<Decoded>,
}

impl Default for Gallery {
    fn default() -> Self {
        let (done_tx, done_rx) = channel();
        Gallery {
            folder: None,
            thumbs: HashMap::new(),
            failed: HashSet::new(),
            loading: HashSet::new(),
            done_tx,
            done_rx,
        }
    }
}

/// Une vignette recadrée au 16:9 (`KeepAspectRatioByExpanding` puis centre).
pub fn thumbnail(path: &Path) -> Option<([usize; 2], Vec<u8>)> {
    let image = image::ImageReader::open(path).ok()?.with_guessed_format().ok()?.decode().ok()?;
    let [tw, th] = THUMB;
    let filled = image.resize_to_fill(tw, th, image::imageops::FilterType::Triangle).to_rgba8();
    Some(([filled.width() as usize, filled.height() as usize], filled.into_raw()))
}

/// Une vignette entière (logo, portrait), sans recadrage, dans 256 × 256.
pub fn thumbnail_fit(path: &Path) -> Option<([usize; 2], Vec<u8>)> {
    let image = image::ImageReader::open(path).ok()?.with_guessed_format().ok()?.decode().ok()?;
    let fitted = image.resize(256, 256, image::imageops::FilterType::Triangle).to_rgba8();
    Some(([fitted.width() as usize, fitted.height() as usize], fitted.into_raw()))
}

/// La clé d'une vignette entière (sans recadrage).
const FIT: &str = "entiere|";

/// Où en est une vignette demandée.
pub enum Thumb {
    Ready(egui::TextureHandle),
    Loading,
    Failed,
}

/// Copie une photo dans `folder`, sans doublon (`copy_church_photo` de la 2.8) : un fichier du
/// même nom mais différent reçoit « -1 », « -2 »… Sans dossier, ou si la copie échoue, le chemin
/// d'origine est gardé.
pub fn copy_photo(source: &Path, folder: Option<&Path>) -> PathBuf {
    let Some(folder) = folder else { return source.to_path_buf() };
    if source.parent().and_then(|p| p.canonicalize().ok()) == folder.canonicalize().ok() {
        return source.to_path_buf();
    }
    let copy = || -> std::io::Result<PathBuf> {
        std::fs::create_dir_all(folder)?;
        let name = source.file_name().ok_or_else(|| std::io::Error::other("nom de fichier absent"))?;
        let stem = source.file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
        let ext = source.extension().map(|e| format!(".{}", e.to_string_lossy())).unwrap_or_default();
        let bytes = std::fs::read(source)?;
        let mut target = folder.join(name);
        let mut index = 1;
        while target.exists() && std::fs::read(&target)? != bytes {
            target = folder.join(format!("{stem}-{index}{ext}"));
            index += 1;
        }
        if !target.exists() {
            std::fs::write(&target, &bytes)?;
        }
        Ok(target)
    };
    copy().unwrap_or_else(|_| source.to_path_buf())
}

impl Gallery {
    /// Les vignettes prêtes deviennent des textures ; celles qui manquent sont demandées.
    fn refresh(&mut self, ctx: &egui::Context, photos: &[String]) {
        while let Ok((path, decoded)) = self.done_rx.try_recv() {
            self.loading.remove(&path);
            match decoded {
                Some((size, pixels)) => {
                    let image = egui::ColorImage::from_rgba_unmultiplied(size, &pixels);
                    let texture = ctx.load_texture(format!("photo-{path}"), image, egui::TextureOptions::LINEAR);
                    self.thumbs.insert(path, texture);
                }
                None => {
                    self.failed.insert(path);
                }
            }
        }
        let missing: Vec<String> = photos
            .iter()
            .filter(|p| !self.thumbs.contains_key(*p) && !self.failed.contains(*p) && !self.loading.contains(*p))
            .cloned()
            .collect();
        if missing.is_empty() {
            return;
        }
        self.loading.extend(missing.iter().cloned());
        let tx = self.done_tx.clone();
        let wake = ctx.clone();
        std::thread::spawn(move || {
            for path in missing {
                let decoded = match path.strip_prefix(FIT) {
                    Some(file) => thumbnail_fit(Path::new(file)),
                    None => thumbnail(Path::new(&path)),
                };
                if tx.send((path, decoded)).is_err() {
                    return;
                }
                wake.request_repaint();
            }
        });
    }

    /// Demande d'un coup les vignettes de plusieurs images (un seul fil pour toutes).
    pub fn prefetch(&mut self, ctx: &egui::Context, paths: &[String], fit: bool) {
        let keys: Vec<String> = paths.iter().map(|p| if fit { format!("{FIT}{p}") } else { p.clone() }).collect();
        self.refresh(ctx, &keys);
    }

    /// La vignette d'une image quelconque (`fit` : entière, sinon recadrée au 16:9), décodée dans
    /// un fil à part la première fois.
    pub fn thumb(&mut self, ctx: &egui::Context, path: &str, fit: bool) -> Thumb {
        let key = if fit { format!("{FIT}{path}") } else { path.to_string() };
        self.refresh(ctx, std::slice::from_ref(&key));
        if let Some(texture) = self.thumbs.get(&key) {
            Thumb::Ready(texture.clone())
        } else if self.failed.contains(&key) {
            Thumb::Failed
        } else {
            Thumb::Loading
        }
    }

    /// La galerie : vignettes (✕ pour retirer), ajout, projection. Rend vrai si la liste a changé.
    pub fn ui(&mut self, ui: &mut Ui, photos: &mut Vec<String>, actions: &mut Vec<GalleryAction>) -> bool {
        self.refresh(ui.ctx(), photos);
        let mut changed = false;
        let mut remove = None;
        let (tw, th) = (THUMB[0] as f32 * 0.75, THUMB[1] as f32 * 0.75);
        ui.horizontal_wrapped(|ui| {
            for (i, path) in photos.iter().enumerate() {
                ui.vertical(|ui| {
                    let name = Path::new(path).file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
                    match self.thumbs.get(path) {
                        Some(texture) => {
                            ui.add(egui::Image::new(texture).fit_to_exact_size(egui::vec2(tw, th)))
                                .on_hover_text(path.as_str());
                        }
                        None => {
                            let (rect, _) = ui.allocate_exact_size(egui::vec2(tw, th), egui::Sense::hover());
                            ui.painter().rect_filled(rect, 4.0, SURFACE);
                            let note = if self.failed.contains(path) { "illisible" } else { "…" };
                            ui.painter().text(rect.center(), egui::Align2::CENTER_CENTER, note, regular(11.0), FAINT);
                        }
                    }
                    ui.horizontal(|ui| {
                        ui.set_width(tw);
                        let short: String = name.chars().take(18).collect();
                        ui.label(RichText::new(short).font(regular(10.5)).color(FAINT));
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            if ui
                                .small_button("✕")
                                .on_hover_text(format!("Retirer « {name} » de la galerie (le fichier reste)"))
                                .clicked()
                            {
                                remove = Some(i);
                            }
                        });
                    });
                });
            }
        });
        if let Some(i) = remove {
            photos.remove(i);
            changed = true;
        }
        ui.horizontal(|ui| {
            if widgets::button(ui, None, "Ajouter des photos…", Tone::Secondary).clicked()
                && let Some(files) = rfd::FileDialog::new()
                    .set_title("Photos de l'église")
                    .add_filter("Images", &["png", "jpg", "jpeg"])
                    .pick_files()
            {
                for file in files {
                    let target = copy_photo(&file, self.folder.as_deref()).to_string_lossy().to_string();
                    if !photos.contains(&target) {
                        photos.push(target);
                        changed = true;
                    }
                }
            }
            if !photos.is_empty()
                && widgets::button(ui, None, "Projeter en diaporama", Tone::Secondary)
                    .on_hover_text("Les photos au direct, l'une après l'autre, en boucle")
                    .clicked()
            {
                actions.push(GalleryAction::Project(photos.clone()));
            }
            let count = match photos.len() {
                0 => "Aucune photo".to_string(),
                1 => "1 photo".to_string(),
                n => format!("{n} photos"),
            };
            ui.label(RichText::new(count).font(regular(12.0)).color(MUTED));
        });
        changed
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scratch() -> tempfile::TempDir {
        let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
        std::fs::create_dir_all(&base).unwrap();
        tempfile::tempdir_in(base).unwrap()
    }

    #[test]
    fn photos_are_copied_once_and_same_names_do_not_collide() {
        let dir = scratch();
        let (a, b) = (dir.path().join("a"), dir.path().join("b"));
        std::fs::create_dir_all(&a).unwrap();
        std::fs::create_dir_all(&b).unwrap();
        std::fs::write(a.join("culte.jpg"), b"premiere").unwrap();
        std::fs::write(b.join("culte.jpg"), b"seconde").unwrap();
        let folder = dir.path().join("photos");
        let first = copy_photo(&a.join("culte.jpg"), Some(&folder));
        assert_eq!(first, folder.join("culte.jpg"));
        assert_eq!(copy_photo(&a.join("culte.jpg"), Some(&folder)), first, "pas de doublon");
        assert_eq!(copy_photo(&b.join("culte.jpg"), Some(&folder)), folder.join("culte-1.jpg"));
        assert_eq!(copy_photo(&first, Some(&folder)), first, "déjà dans la galerie");
        assert_eq!(copy_photo(&a.join("culte.jpg"), None), a.join("culte.jpg"));
    }

    #[test]
    fn a_thumbnail_fills_16_9() {
        let photo = po_layout::bundled_backgrounds_dir().join("bg-ardoise_4x3.png");
        let ([w, h], pixels) = thumbnail(&photo).unwrap();
        assert_eq!((w, h), (192, 108));
        assert_eq!(pixels.len(), w * h * 4);
        assert!(thumbnail(Path::new("C:/introuvable.jpg")).is_none());
    }
}
