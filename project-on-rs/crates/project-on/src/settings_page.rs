//! La page « Réglages » : la projection (texte, fond, transitions, écran), le découpage des slides,
//! la diffusion (couleur de clé HDMI), les raccourcis, le mode PC modeste et l'entretien
//! (sauvegardes, contrôle avant culte). Les réglages sont ceux du `settings.json` de la bêta, écrits
//! avec les mêmes règles que la 2.x (écriture d'un coup, copie `.bak`).

use egui::{Align2, Color32, CornerRadius, Rect, RichText, Sense, Stroke, Ui, pos2, vec2};
use po_design::{IdentificationStyle, Rgba, parse_color};
use po_settings::Settings;
use serde_json::{Map, Value, json};

use crate::icons::Icon;
use crate::maintenance::{Check, Level};
use crate::shortcuts::ACTIONS;
use crate::theme::*;
use crate::widgets::{self, Tone};

/// Ce que la page demande à la régie.
#[derive(Debug, Clone)]
pub enum SettingsAction {
    Save(Box<Settings>),
    Backup,
    Preflight,
    OpenFolder(std::path::PathBuf),
    /// Préparer la restauration d'une sauvegarde (appliquée au prochain démarrage).
    Restore(RestoreChoice),
    /// Renoncer à la restauration préparée.
    CancelRestore,
    /// Fermer Project-On (pour que la restauration se fasse).
    Quit,
    /// Projeter les photos de l'église en diaporama.
    ShowPhotos(Vec<String>),
    /// Relire la liste des scènes d'OBS.
    ObsRefresh,
    /// Créer la source « Project-On » dans cette scène d'OBS.
    ObsCreateSource(String),
    /// Rechercher une mise à jour.
    UpdateCheck,
    /// Télécharger la mise à jour trouvée.
    UpdateDownload,
    /// Lancer l'installateur téléchargé (Project-On se ferme).
    UpdateInstall,
    /// Ouvrir la page de la version (bêta).
    UpdatePage,
}

/// Où en est la mise à jour, pour la page Réglages.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct UpdateView {
    pub busy: bool,
    pub status: String,
    /// Une version plus récente trouvée.
    pub available: Option<crate::updater::UpdateInfo>,
    /// L'installateur téléchargé, prêt à lancer.
    pub ready: Option<std::path::PathBuf>,
}

/// Ce qu'on restaure : une sauvegarde de la 3.0, ou une archive complète de la 2.8.
#[derive(Debug, Clone, PartialEq)]
pub enum RestoreChoice {
    Backup(std::path::PathBuf),
    Archive(std::path::PathBuf),
}

impl RestoreChoice {
    pub fn label(&self) -> String {
        let name = |p: &std::path::Path| p.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
        match self {
            RestoreChoice::Backup(dir) => format!("la sauvegarde du {}", name(dir)),
            RestoreChoice::Archive(file) => format!("l'archive « {} »", name(file)),
        }
    }
}

/// Les réglages propres à la 3.0, rangés à part dans `settings.json` (la 2.x les ignore).
pub const SECTION_3: &str = "refonte_3";

/// Le mode PC modeste : sans transitions ni aperçus de designs.
pub fn low_power(settings: &Settings) -> bool {
    settings.other.get(SECTION_3).and_then(|s| s.get("low_power")).and_then(Value::as_bool).unwrap_or(false)
}

/// Le style de l'identification de Branham choisi.
pub fn identification_style(settings: &Settings) -> IdentificationStyle {
    match settings.other.get(SECTION_3).and_then(|s| s.get("identification")).and_then(Value::as_str) {
        Some("minimal") => IdentificationStyle::Minimal,
        Some("band") => IdentificationStyle::Band,
        Some("transparent") => IdentificationStyle::Transparent,
        _ => IdentificationStyle::Elegant,
    }
}

fn set_3(settings: &mut Settings, key: &str, value: Value) {
    let section = settings.other.entry(SECTION_3.to_string()).or_insert_with(|| Value::Object(Map::new()));
    if !section.is_object() {
        *section = Value::Object(Map::new());
    }
    if let Some(map) = section.as_object_mut() {
        map.insert(key.into(), value);
    }
}

/// Les rubriques de la page Réglages (menu de gauche).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Hash)]
pub enum Tab {
    #[default]
    Projection,
    Slides,
    Church,
    Outputs,
    Obs,
    Shortcuts,
    Maintenance,
    General,
}

impl Tab {
    pub const ALL: [Tab; 8] = [
        Tab::Projection,
        Tab::Slides,
        Tab::Church,
        Tab::Outputs,
        Tab::Obs,
        Tab::Shortcuts,
        Tab::Maintenance,
        Tab::General,
    ];

    pub fn label(self) -> &'static str {
        match self {
            Tab::Projection => "Projection",
            Tab::Slides => "Slides",
            Tab::Church => "Église",
            Tab::Outputs => "Sorties HDMI",
            Tab::Obs => "OBS",
            Tab::Shortcuts => "Raccourcis",
            Tab::Maintenance => "Entretien",
            Tab::General => "Général",
        }
    }

    fn hint(self) -> &'static str {
        match self {
            Tab::Projection => "Le texte, le fond, les transitions et l'écran de la salle",
            Tab::Slides => "Le découpage des longs textes et des strophes",
            Tab::Church => "Le nom, le logo, le pasteur, les réseaux et les photos",
            Tab::Outputs => "La couleur de clé, la taille et la position du texte",
            Tab::Obs => "Changer de scène au direct et au masquage",
            Tab::Shortcuts => "Les touches de la régie",
            Tab::Maintenance => "Les sauvegardes, la restauration et le contrôle avant culte",
            Tab::General => "Le mode PC modeste, la mise à jour, à propos",
        }
    }

    fn icon(self) -> Icon {
        match self {
            Tab::Projection => Icon::Monitor,
            Tab::Slides => Icon::Presentation,
            Tab::Church => Icon::Image,
            Tab::Outputs => Icon::Cast,
            Tab::Obs => Icon::ListVideo,
            Tab::Shortcuts => Icon::Play,
            Tab::Maintenance => Icon::Refresh,
            Tab::General => Icon::Settings,
        }
    }
}

/// La page : un brouillon des réglages, enregistré d'un clic.
#[derive(Default)]
pub struct SettingsView {
    pub draft: Option<Settings>,
    pub checks: Vec<Check>,
    pub backups: Vec<crate::maintenance::Backup>,
    /// La restauration à confirmer.
    pub confirm_restore: Option<RestoreChoice>,
    /// La restauration préparée, faite au prochain démarrage.
    pub pending_restore: Option<String>,
    /// La restauration en cours de préparation (une archive avec ses médias peut être longue).
    pub preparing: bool,
    pub families: Vec<String>,
    pub screens: Vec<String>,
    /// La galerie des photos de l'église (et les vignettes de toutes les images de la page).
    pub gallery: crate::gallery::Gallery,
    /// Le pilotage d'OBS : état, scènes, dernier message.
    pub obs: (crate::obs::ObsState, Vec<String>, String),
    /// La scène où créer la source « Project-On ».
    pub obs_source_scene: String,
    /// La mise à jour de l'application.
    pub update: UpdateView,
    /// La rubrique affichée.
    pub tab: Tab,
    /// Le dossier des polices (`assets/fonts`) : l'aperçu en a besoin, et les fonds fournis sont
    /// à côté (`assets/backgrounds`).
    pub fonts_dir: Option<std::path::PathBuf>,
    preview: Option<crate::designs::Previews>,
    preview_key: String,
    preview_texture: Option<egui::TextureHandle>,
    backgrounds: Option<Vec<String>>,
}

/// La largeur du menu des rubriques.
const NAV_WIDTH: f32 = 172.0;

fn row(ui: &mut Ui, label: &str, add: impl FnOnce(&mut Ui)) {
    let width = (ui.available_width() * 0.36).clamp(150.0, 230.0);
    ui.horizontal(|ui| {
        // Le libellé, aligné à gauche dans sa colonne.
        ui.allocate_ui_with_layout(
            vec2(width, 24.0),
            egui::Layout::left_to_right(egui::Align::Center).with_main_wrap(true),
            |ui| {
                ui.set_min_width(width);
                ui.add(egui::Label::new(RichText::new(label).font(regular(12.5)).color(MUTED)).wrap());
            },
        );
        add(ui);
    });
    ui.add_space(4.0);
}

/// Un groupe de réglages : une carte avec son titre et une phrase d'explication.
fn group(ui: &mut Ui, title: &str, note: &str, add: impl FnOnce(&mut Ui)) {
    widgets::card(ui, |ui| {
        ui.set_width(ui.available_width());
        ui.label(RichText::new(title).font(semibold(14.5)).color(TEXT));
        if !note.is_empty() {
            ui.label(RichText::new(note).font(regular(11.5)).color(FAINT));
        }
        ui.add_space(10.0);
        add(ui);
    });
    ui.add_space(14.0);
}

/// Le menu des rubriques.
fn nav(ui: &mut Ui, tab: &mut Tab) {
    for t in Tab::ALL {
        let selected = *tab == t;
        let (rect, r) = widgets::list_row(ui, selected, 40.0, &format!("Réglages · {}", t.label()));
        ui.add_space(3.0);
        crate::icons::paint(
            ui.painter(),
            Rect::from_center_size(pos2(rect.min.x + 20.0, rect.center().y), vec2(16.0, 16.0)),
            t.icon(),
            if selected { ACCENT } else { MUTED },
        );
        widgets::paint_text(
            ui,
            pos2(rect.min.x + 38.0, rect.center().y),
            Align2::LEFT_CENTER,
            t.label(),
            medium(13.0),
            if selected { TEXT } else { MUTED },
            rect.width() - 46.0,
        );
        if r.on_hover_text(t.hint()).clicked() {
            *tab = t;
        }
    }
}

/// Le nom lisible d'un fond fourni : « bg-photo-croix-aube_16x9.png » → « Croix aube ».
fn background_name(path: &str) -> String {
    let stem = std::path::Path::new(path).file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
    let stem = stem.strip_prefix("bg-").unwrap_or(&stem);
    let stem = stem.split('_').next().unwrap_or(stem);
    let stem = stem.strip_prefix("photo-").or_else(|| stem.strip_prefix("symbole-")).unwrap_or(stem);
    let words = stem.replace('-', " ");
    let mut chars = words.chars();
    chars.next().map(|c| c.to_uppercase().collect::<String>() + chars.as_str()).unwrap_or_default()
}

fn same_file(a: &str, b: &str) -> bool {
    let norm = |p: &str| p.trim().replace('/', "\\").to_lowercase();
    !a.trim().is_empty() && norm(a) == norm(b)
}

/// Les fonds fournis : une grille de vignettes ; un clic choisit le fond. Rend vrai au choix.
fn backgrounds_grid(
    ui: &mut Ui,
    gallery: &mut crate::gallery::Gallery,
    backgrounds: &[String],
    value: &mut String,
) -> bool {
    if backgrounds.is_empty() {
        return false;
    }
    gallery.prefetch(ui.ctx(), backgrounds, false);
    let mut picked = false;
    let gap = 10.0;
    let columns = ((ui.available_width() + gap) / (128.0 + gap)).floor().max(2.0);
    let tile_w = (ui.available_width() - gap * (columns - 1.0)) / columns;
    let tile = vec2(tile_w, tile_w * 9.0 / 16.0);
    ui.horizontal_wrapped(|ui| {
        ui.spacing_mut().item_spacing = vec2(gap, gap);
        for path in backgrounds {
            let name = background_name(path);
            let (rect, r) = ui.allocate_exact_size(tile, Sense::click());
            r.widget_info(|| egui::WidgetInfo::labeled(egui::Role::Button, true, format!("Fond : {name}")));
            let selected = same_file(value, path);
            let t = widgets::hover_t(ui, &r, r.hovered());
            let painter = ui.painter();
            let radius = CornerRadius::same(8);
            if selected {
                crate::theme::paint_glow(painter, rect, radius, ACCENT, 0.45);
            } else {
                crate::theme::paint_shadow(painter, rect, radius, 3, 10, Color32::from_black_alpha(110));
            }
            match gallery.thumb(ui.ctx(), path, false) {
                crate::gallery::Thumb::Ready(texture) => {
                    widgets::paint_image_rounded(painter, rect, texture.id(), radius)
                }
                _ => {
                    painter.rect_filled(rect, radius, WELL);
                }
            }
            let stroke = if selected {
                Stroke::new(2.0, ACCENT)
            } else {
                Stroke::new(1.0, BORDER_STRONG.lerp_to_gamma(ACCENT, 0.6 * t))
            };
            painter.rect_stroke(rect, radius, stroke, egui::StrokeKind::Inside);
            if selected {
                let badge = Rect::from_center_size(pos2(rect.max.x - 13.0, rect.min.y + 13.0), vec2(18.0, 18.0));
                painter.circle_filled(badge.center(), 9.0, ACCENT);
                crate::icons::paint(painter, badge.shrink(4.0), Icon::Check, crate::theme::on_color(ACCENT));
            }
            if r.on_hover_text(&name).clicked() {
                *value = path.clone();
                picked = true;
            }
        }
    });
    picked
}

/// Une image choisie par l'opérateur : sa vignette, son nom, « Choisir… » et « Retirer ».
/// `fit` : l'image entière (logo, portrait), sinon recadrée au 16:9 (fond).
fn image_field(ui: &mut Ui, gallery: &mut crate::gallery::Gallery, label: &str, value: &mut String, fit: bool) -> bool {
    let mut changed = false;
    row(ui, label, |ui| {
        let size = if fit { vec2(72.0, 72.0) } else { vec2(128.0, 72.0) };
        let (rect, _) = ui.allocate_exact_size(size, Sense::hover());
        let path = value.trim().to_string();
        let thumb = (!path.is_empty()).then(|| gallery.thumb(ui.ctx(), &path, fit));
        let painter = ui.painter();
        let radius = CornerRadius::same(8);
        painter.rect(rect, radius, WELL, Stroke::new(1.0, BORDER), egui::StrokeKind::Inside);
        let missing = matches!(thumb, Some(crate::gallery::Thumb::Failed));
        match &thumb {
            None => crate::icons::paint(
                painter,
                Rect::from_center_size(rect.center(), vec2(22.0, 22.0)),
                Icon::Image,
                FAINT,
            ),
            Some(crate::gallery::Thumb::Ready(texture)) => {
                if fit {
                    let inner = widgets::fit_in(rect.shrink(5.0), texture.size_vec2());
                    widgets::paint_image_rounded(painter, inner, texture.id(), CornerRadius::same(4));
                } else {
                    widgets::paint_image_rounded(painter, rect.shrink(1.0), texture.id(), radius);
                }
            }
            Some(crate::gallery::Thumb::Loading) => {
                painter.text(rect.center(), Align2::CENTER_CENTER, "…", regular(14.0), FAINT);
            }
            Some(crate::gallery::Thumb::Failed) => {
                crate::icons::paint(
                    painter,
                    Rect::from_center_size(rect.center(), vec2(22.0, 22.0)),
                    Icon::Alert,
                    WARN,
                );
            }
        }
        ui.add_space(10.0);
        ui.vertical(|ui| {
            let file = std::path::Path::new(&path);
            let name = file.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
            if path.is_empty() {
                ui.label(RichText::new("Aucune image").font(medium(12.5)).color(FAINT));
            } else {
                ui.add(egui::Label::new(RichText::new(&name).font(semibold(12.5)).color(TEXT)).truncate());
                let detail = if missing {
                    RichText::new("Fichier introuvable ou illisible").font(regular(11.0)).color(WARN)
                } else {
                    let folder = file.parent().map(|p| p.display().to_string()).unwrap_or_default();
                    RichText::new(folder).font(regular(11.0)).color(FAINT)
                };
                ui.add(egui::Label::new(detail).truncate()).on_hover_text(&path);
            }
            ui.add_space(2.0);
            ui.horizontal(|ui| {
                let choose =
                    widgets::button_at(ui, widgets::Size::Small, Some(Icon::Image), "Choisir…", Tone::Secondary, true)
                        .on_hover_text(format!("Choisir : {label}"));
                if choose.clicked()
                    && let Some(file) = rfd::FileDialog::new()
                        .set_title(label)
                        .add_filter("Images", &["png", "jpg", "jpeg", "webp", "bmp"])
                        .pick_file()
                {
                    *value = file.to_string_lossy().to_string();
                    changed = true;
                }
                if !path.is_empty()
                    && widgets::button_at(ui, widgets::Size::Small, None, "Retirer", Tone::Danger, true).clicked()
                {
                    value.clear();
                    changed = true;
                }
            });
        });
    });
    changed
}

fn color(ui: &mut Ui, value: &mut String) {
    let c = parse_color(value);
    let mut c32 = Color32::from_rgba_unmultiplied(c.0[0], c.0[1], c.0[2], c.0[3]);
    if egui::color_picker::color_edit_button_srgba(ui, &mut c32, egui::color_picker::Alpha::OnlyBlend).changed() {
        let [r, g, b, a] = c32.to_srgba_unmultiplied();
        *value = if a == 255 {
            format!("#{r:02x}{g:02x}{b:02x}")
        } else {
            format!("rgba({r}, {g}, {b}, {:.2})", f32::from(a) / 255.0)
        };
    }
    ui.label(RichText::new(value.as_str()).font(regular(11.5)).color(FAINT));
}

fn choice(ui: &mut Ui, id: &str, value: &mut String, options: &[(&str, &str)]) {
    let shown = options.iter().find(|(v, _)| *v == value.as_str()).map_or(value.clone(), |(_, l)| (*l).to_string());
    egui::ComboBox::from_id_salt(id).selected_text(shown).width(220.0).show_ui(ui, |ui| {
        for (v, l) in options {
            if ui.selectable_label(value == v, *l).clicked() {
                *value = (*v).to_string();
            }
        }
    });
}

impl SettingsView {
    /// Restaurer : une sauvegarde de la liste, ou une archive de la 2.8 ; confirmation, puis
    /// application au prochain démarrage.
    fn restore_ui(
        ui: &mut Ui,
        backups: &[crate::maintenance::Backup],
        confirm_restore: &mut Option<RestoreChoice>,
        pending_restore: Option<&str>,
        preparing: bool,
        actions: &mut Vec<SettingsAction>,
    ) {
        ui.add_space(6.0);
        if preparing {
            ui.horizontal(|ui| {
                ui.spinner();
                ui.label(RichText::new("Vérification de la sauvegarde…").font(regular(12.0)).color(MUTED));
            });
            return;
        }
        if let Some(label) = pending_restore {
            widgets::card(ui, |ui| {
                ui.set_width(ui.available_width());
                ui.label(RichText::new(format!("Restauration prête : {label}")).font(semibold(13.0)).color(WARN));
                ui.label(
                    RichText::new(
                        "Elle se fera au prochain démarrage de Project-On : la base et les réglages actuels seront d'abord sauvegardés, puis remplacés.",
                    )
                    .font(regular(12.0))
                    .color(MUTED),
                );
                ui.horizontal(|ui| {
                    if widgets::button(ui, None, "Fermer Project-On maintenant", Tone::Primary(WARN)).clicked() {
                        actions.push(SettingsAction::Quit);
                    }
                    if widgets::button(ui, None, "Annuler la restauration", Tone::Secondary).clicked() {
                        actions.push(SettingsAction::CancelRestore);
                    }
                });
            });
            return;
        }
        if let Some(choice) = confirm_restore.clone() {
            widgets::card(ui, |ui| {
                ui.set_width(ui.available_width());
                ui.label(RichText::new(format!("Restaurer {} ?", choice.label())).font(semibold(13.0)).color(TEXT));
                ui.label(
                    RichText::new(
                        "Les playlists, cantiques et réglages reviendront à leur état de cette sauvegarde. Rien ne change avant le prochain démarrage, et la base actuelle sera sauvegardée d'abord : la restauration peut être défaite.",
                    )
                    .font(regular(12.0))
                    .color(MUTED),
                );
                ui.horizontal(|ui| {
                    if widgets::button(ui, None, "Préparer la restauration", Tone::Primary(WARN)).clicked() {
                        actions.push(SettingsAction::Restore(choice.clone()));
                        *confirm_restore = None;
                    }
                    if widgets::button(ui, None, "Annuler", Tone::Secondary).clicked() {
                        *confirm_restore = None;
                    }
                });
            });
            return;
        }
        egui::CollapsingHeader::new(RichText::new("Restaurer une sauvegarde").font(medium(12.5)).color(TEXT))
            .id_salt("restaurer")
            .show(ui, |ui| {
                for b in backups {
                    let name = b.dir.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
                    ui.horizontal(|ui| {
                        ui.add_sized(
                            [300.0, 22.0],
                            egui::Label::new(
                                RichText::new(format!("{name} · {} Mo", b.bytes / 1_000_000))
                                    .font(regular(12.0))
                                    .color(MUTED),
                            ),
                        );
                        if widgets::button(ui, None, "Restaurer…", Tone::Secondary)
                            .on_hover_text(format!("Restaurer la sauvegarde du {name}"))
                            .clicked()
                        {
                            *confirm_restore = Some(RestoreChoice::Backup(b.dir.clone()));
                        }
                    });
                }
                if widgets::button(ui, None, "Restaurer une archive de la 2.8…", Tone::Secondary)
                    .on_hover_text("Une « sauvegarde complète » de la 2.8 (fichier .zip : base, médias, réglages)")
                    .clicked()
                    && let Some(file) = rfd::FileDialog::new()
                        .set_title("Archive Project-On à restaurer")
                        .add_filter("Archive Project-On", &["zip"])
                        .pick_file()
                {
                    *confirm_restore = Some(RestoreChoice::Archive(file));
                }
            });
    }

    /// L'aperçu de la projection avec le brouillon (rendu dans un fil à part, comme les designs).
    fn refresh_preview(&mut self, ctx: &egui::Context, current: &Settings) {
        let settings = self.draft.as_ref().unwrap_or(current);
        let mut design = po_design::RoomDesign::from_projection(&settings.projection);
        design.identification.style = identification_style(settings);
        let body = po_design::library::DesignBody::Room(design);
        let key = serde_json::to_string(&body).unwrap_or_default();
        if self.preview.is_none() {
            let Some(dir) = self.fonts_dir.clone() else { return };
            let wake = ctx.clone();
            self.preview = crate::designs::Previews::start(dir, move || wake.request_repaint());
        }
        let Some(previews) = &self.preview else { return };
        if key != self.preview_key {
            self.preview_key = key.clone();
            let _ = previews.jobs.send((vec![("reglages".to_string(), key, body)], crate::designs::sample_slide()));
        }
        let [w, h] = crate::designs::PREVIEW_SIZE;
        while let Ok((_, _, pixels)) = previews.done.try_recv() {
            if pixels.len() != (w * h * 4) as usize {
                continue;
            }
            let image = egui::ColorImage::from_rgba_premultiplied([w as usize, h as usize], &pixels);
            match &mut self.preview_texture {
                Some(texture) => texture.set(image, egui::TextureOptions::LINEAR),
                None => {
                    self.preview_texture =
                        Some(ctx.load_texture("apercu-reglages", image, egui::TextureOptions::LINEAR))
                }
            }
        }
    }

    /// Les fonds fournis (16:9), à côté des polices : photos, puis symboles, puis couleurs.
    fn background_files(&mut self) -> Vec<String> {
        let fonts_dir = self.fonts_dir.clone();
        self.backgrounds
            .get_or_insert_with(|| {
                let dir = fonts_dir.as_ref().and_then(|f| f.parent()).map(|a| a.join("backgrounds"));
                let mut files: Vec<String> = dir
                    .and_then(|d| std::fs::read_dir(d).ok())
                    .into_iter()
                    .flatten()
                    .filter_map(Result::ok)
                    .map(|e| e.path())
                    .filter(|p| p.file_name().and_then(|n| n.to_str()).is_some_and(|n| n.ends_with("_16x9.png")))
                    .map(|p| p.to_string_lossy().to_string())
                    .collect();
                let rank = |p: &String| {
                    let name = std::path::Path::new(p).file_name().map(|n| n.to_string_lossy().to_string());
                    match name.as_deref() {
                        Some(n) if n.starts_with("bg-photo-") => 0,
                        Some(n) if n.starts_with("bg-symbole-") => 1,
                        _ => 2,
                    }
                };
                files.sort_by(|a, b| rank(a).cmp(&rank(b)).then_with(|| a.cmp(b)));
                files
            })
            .clone()
    }

    /// La page. `current` : les réglages en vigueur (le brouillon part d'eux).
    pub fn ui(&mut self, ui: &mut Ui, current: &Settings) -> Vec<SettingsAction> {
        let mut actions = Vec::new();
        let backgrounds = if self.tab == Tab::Projection {
            self.refresh_preview(ui.ctx(), current);
            self.background_files()
        } else {
            Vec::new()
        };
        let draft = self.draft.get_or_insert_with(|| current.clone());
        let families = self.families.clone();
        let screens = self.screens.clone();
        let changed = draft != current;

        // L'en-tête : le titre, et l'enregistrement toujours à portée de main.
        ui.horizontal(|ui| {
            ui.vertical(|ui| {
                ui.label(RichText::new("Réglages").font(bold(22.0)).color(TEXT));
                ui.label(
                    RichText::new(if cfg!(feature = "bascule") {
                        "Ces réglages sont ceux de Project-On (les mêmes fichiers que la 2.x)."
                    } else {
                        "Ces réglages sont ceux de la bêta : la 2.8 garde les siens."
                    })
                    .font(regular(12.0))
                    .color(FAINT),
                );
            });
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if widgets::button_at(
                    ui,
                    widgets::Size::Large,
                    Some(Icon::Check),
                    "Enregistrer",
                    Tone::Primary(ACCENT),
                    changed,
                )
                .clicked()
                {
                    actions.push(SettingsAction::Save(Box::new(draft.clone())));
                }
                if changed {
                    if widgets::button_at(
                        ui,
                        widgets::Size::Large,
                        None,
                        "Annuler les changements",
                        Tone::Secondary,
                        true,
                    )
                    .clicked()
                    {
                        *draft = current.clone();
                    }
                    widgets::status_pill(ui, "Non enregistré", WARN);
                }
            });
        });
        ui.add_space(14.0);

        let height = ui.available_height();
        ui.horizontal_top(|ui| {
            ui.allocate_ui_with_layout(vec2(NAV_WIDTH, height), egui::Layout::top_down(egui::Align::Min), |ui| {
                ui.set_width(NAV_WIDTH);
                nav(ui, &mut self.tab);
            });
            ui.add_space(14.0);
            let width = ui.available_width();
            ui.allocate_ui_with_layout(vec2(width, height), egui::Layout::top_down(egui::Align::Min), |ui| {
                egui::ScrollArea::vertical().id_salt(("reglages", self.tab)).auto_shrink([false, false]).show(
                    ui,
                    |ui| {
                        ui.set_width(ui.available_width() - 12.0);
                        ui.add_space(4.0);
                        match self.tab {
                            Tab::Projection => projection_tab(
                                ui,
                                draft,
                                &families,
                                &screens,
                                self.preview_texture.as_ref(),
                                &backgrounds,
                                &mut self.gallery,
                            ),
                            Tab::Slides => slides_tab(ui, draft),
                            Tab::Church => {
                                church_profile(ui, draft, &families, &mut self.gallery, &mut actions);
                            }
                            Tab::Outputs => outputs_tab(ui, draft, &screens),
                            Tab::Obs => group(
                                ui,
                                "Pilotage d'OBS",
                                "Project-On change la scène d'OBS quand un slide passe au direct et quand le texte est masqué.",
                                |ui| obs_section(ui, draft, &self.obs, &mut self.obs_source_scene, &mut actions),
                            ),
                            Tab::Shortcuts => shortcuts_tab(ui, draft),
                            Tab::Maintenance => {
                                group(
                                    ui,
                                    "Sauvegardes",
                                    "Une copie de la base et des réglages ; une sauvegarde se restaure au prochain démarrage.",
                                    |ui| {
                                        ui.horizontal(|ui| {
                                            if widgets::button(ui, None, "Sauvegarder maintenant", Tone::Secondary)
                                                .clicked()
                                            {
                                                actions.push(SettingsAction::Backup);
                                            }
                                            if let Some(dir) = self.backups.first().and_then(|b| b.dir.parent())
                                                && widgets::button(ui, None, "Ouvrir le dossier", Tone::Secondary)
                                                    .clicked()
                                            {
                                                actions.push(SettingsAction::OpenFolder(dir.to_path_buf()));
                                            }
                                        });
                                        ui.add_space(4.0);
                                        match self.backups.first() {
                                            Some(b) => {
                                                let name = b
                                                    .dir
                                                    .file_name()
                                                    .map(|n| n.to_string_lossy().to_string())
                                                    .unwrap_or_default();
                                                ui.label(
                                                    RichText::new(format!(
                                                        "{} sauvegarde(s) ; la dernière : {name} ({} Mo)",
                                                        self.backups.len(),
                                                        b.bytes / 1_000_000
                                                    ))
                                                    .font(regular(12.0))
                                                    .color(MUTED),
                                                );
                                            }
                                            None => {
                                                ui.label(
                                                    RichText::new("Aucune sauvegarde pour l'instant.")
                                                        .font(regular(12.0))
                                                        .color(WARN),
                                                );
                                            }
                                        }
                                        Self::restore_ui(
                                            ui,
                                            &self.backups,
                                            &mut self.confirm_restore,
                                            self.pending_restore.as_deref(),
                                            self.preparing,
                                            &mut actions,
                                        );
                                    },
                                );
                                group(
                                    ui,
                                    "Contrôle avant culte",
                                    "Écrans, base, sauvegarde, sorties : tout est vérifié en un clic.",
                                    |ui| {
                                        if widgets::button(ui, None, "Contrôle avant culte  Ctrl+Maj+D", Tone::Secondary)
                                            .clicked()
                                        {
                                            actions.push(SettingsAction::Preflight);
                                        }
                                        if !self.checks.is_empty() {
                                            ui.add_space(6.0);
                                            checks_list(ui, &self.checks);
                                        }
                                    },
                                );
                            }
                            Tab::General => general_tab(ui, draft, &self.update, &mut actions),
                        }
                        ui.add_space(24.0);
                    },
                );
            });
        });
        actions
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Background {
    Color,
    Gradient,
    Image,
}

/// Projection : l'aperçu, le texte, le fond, les transitions, l'identification de Branham.
fn projection_tab(
    ui: &mut Ui,
    draft: &mut Settings,
    families: &[String],
    screens: &[String],
    preview: Option<&egui::TextureHandle>,
    backgrounds: &[String],
    gallery: &mut crate::gallery::Gallery,
) {
    group(ui, "Aperçu", "Ce que verra l'assemblée avec ces réglages, avant même de les enregistrer.", |ui| {
        let width = ui.available_width().min(560.0);
        let (rect, _) = ui.allocate_exact_size(vec2(width, width * 9.0 / 16.0), Sense::hover());
        let painter = ui.painter();
        let radius = CornerRadius::same(8);
        crate::theme::paint_shadow(painter, rect, radius, 6, 22, Color32::from_black_alpha(150));
        match preview {
            Some(texture) => widgets::paint_image_rounded(painter, rect, texture.id(), radius),
            None => {
                painter.rect_filled(rect, radius, WELL);
                painter.text(rect.center(), Align2::CENTER_CENTER, "Aperçu en préparation…", regular(12.0), FAINT);
            }
        }
        painter.rect_stroke(rect, radius, Stroke::new(1.0, BORDER_STRONG), egui::StrokeKind::Inside);
    });

    let mut style = identification_style(draft);
    let p = &mut draft.projection;
    group(ui, "Le texte", "La police, la taille et les couleurs des paroles et de la référence.", |ui| {
        row(ui, "Police", |ui| {
            egui::ComboBox::from_id_salt("police").selected_text(p.font_family.as_str()).width(220.0).show_ui(
                ui,
                |ui| {
                    for f in families {
                        if ui.selectable_label(p.font_family == *f, f).clicked() {
                            p.font_family = f.clone();
                        }
                    }
                },
            );
        });
        row(ui, "Graisse", |ui| {
            choice(
                ui,
                "graisse",
                &mut p.font_weight,
                &[("normal", "Normale"), ("600", "Demi-grasse"), ("bold", "Grasse")],
            )
        });
        row(ui, "Taille du texte (px en 1080p)", |ui| {
            ui.add(egui::Slider::new(&mut p.text_size, 10..=320));
        });
        row(ui, "Taille minimale", |ui| {
            ui.add(egui::Slider::new(&mut p.min_text_size, 10..=200));
        });
        row(ui, "Capitales", |ui| {
            ui.checkbox(&mut p.uppercase, "Tout en capitales");
        });
        row(ui, "Couleur du texte", |ui| color(ui, &mut p.text_color));
        row(ui, "Ombre du texte", |ui| {
            ui.checkbox(&mut p.text_shadow, "Une ombre douce sous les lettres");
        });
        row(ui, "Alignement", |ui| {
            let mut align = match p.align.as_str() {
                "left" => 0,
                "right" => 2,
                _ => 1,
            };
            if widgets::segmented(ui, &mut align, &[(0, "À gauche"), (1, "Centré"), (2, "À droite")]) {
                p.align = ["left", "center", "right"][align].to_string();
            }
        });
        row(ui, "Référence", |ui| {
            ui.checkbox(&mut p.show_reference, "Afficher");
            let mut top = p.reference_position == "top";
            if widgets::segmented(ui, &mut top, &[(true, "En haut"), (false, "En bas")]) {
                p.reference_position = if top { "top" } else { "bottom" }.to_string();
            }
        });
        row(ui, "Couleur de la référence", |ui| color(ui, &mut p.ref_color));
    });

    group(ui, "Le fond", "Une couleur, un dégradé ou une image derrière le texte.", |ui| {
        let mut mode = if p.bg_mode == "image" {
            Background::Image
        } else if p.bg_gradient_enabled {
            Background::Gradient
        } else {
            Background::Color
        };
        row(ui, "Fond", |ui| {
            if widgets::segmented(
                ui,
                &mut mode,
                &[(Background::Color, "Couleur unie"), (Background::Gradient, "Dégradé"), (Background::Image, "Image")],
            ) {
                match mode {
                    Background::Color => {
                        p.bg_mode = "color".into();
                        p.bg_gradient_enabled = false;
                    }
                    Background::Gradient => {
                        p.bg_mode = "color".into();
                        p.bg_gradient_enabled = true;
                    }
                    Background::Image => p.bg_mode = "image".into(),
                }
            }
        });
        match mode {
            Background::Color => row(ui, "Couleur", |ui| color(ui, &mut p.bg_color)),
            Background::Gradient => {
                row(ui, "Première couleur", |ui| color(ui, &mut p.bg_color));
                row(ui, "Seconde couleur", |ui| color(ui, &mut p.bg_color_2));
            }
            Background::Image => {
                if !backgrounds.is_empty() {
                    ui.label(RichText::new("Fonds fournis avec Project-On").font(medium(12.5)).color(TEXT));
                    ui.add_space(6.0);
                    backgrounds_grid(ui, gallery, backgrounds, &mut p.bg_image);
                    ui.add_space(12.0);
                }
                image_field(ui, gallery, "Image choisie", &mut p.bg_image, false);
                row(ui, "Assombrir l'image", |ui| {
                    ui.add(egui::Slider::new(&mut p.background_dimmer, 0.0..=0.85));
                });
            }
        }
    });

    group(ui, "Transitions et écran", "Le passage d'un slide à l'autre, et l'écran de la salle.", |ui| {
        row(ui, "Transition", |ui| {
            ui.checkbox(&mut p.animation_enabled, "");
            choice(
                ui,
                "anim",
                &mut p.animation_type,
                &[
                    ("fade", "Fondu"),
                    ("slide", "Glissement"),
                    ("scale", "Zoom"),
                    ("blur", "Flou"),
                    ("reveal", "Balayage"),
                ],
            );
        });
        row(ui, "Durée", |ui| {
            ui.add(egui::Slider::new(&mut p.animation_duration, 0..=3000).suffix(" ms"));
        });
        row(ui, "Écran de la salle", |ui| {
            let mut options: Vec<(&str, &str)> = vec![("", "Automatique (le plus grand écran secondaire)")];
            options.extend(screens.iter().map(|s| (s.as_str(), s.as_str())));
            choice(ui, "ecran", &mut p.display_screen, &options);
        });
    });

    group(
        ui,
        "Identification de Branham",
        "Sur les prédications, l'Exposé des Sept Âges et les brochures (jamais sur les biographies).",
        |ui| {
            row(ui, "Style", |ui| {
                let options: Vec<(IdentificationStyle, &str)> =
                    IdentificationStyle::ALL.iter().map(|s| (*s, s.label())).collect();
                widgets::segmented(ui, &mut style, &options);
            });
        },
    );
    if style != identification_style(draft) {
        let key = match style {
            IdentificationStyle::Elegant => "elegant",
            IdentificationStyle::Minimal => "minimal",
            IdentificationStyle::Band => "band",
            IdentificationStyle::Transparent => "transparent",
        };
        set_3(draft, "identification", json!(key));
    }
}

/// Slides : le découpage des longs textes et des strophes.
fn slides_tab(ui: &mut Ui, draft: &mut Settings) {
    let s = &mut draft.split;
    group(
        ui,
        "Découpage des slides",
        "Un long paragraphe est coupé en fin de phrase, en parties équilibrées ; une strophe longue aussi.",
        |ui| {
            row(ui, "Couper les longs textes", |ui| {
                ui.checkbox(&mut s.text_enabled, "");
                ui.add(egui::DragValue::new(&mut s.max_chars).range(80..=2000).suffix(" caractères"));
            });
            row(ui, "Cantiques", |ui| {
                ui.checkbox(&mut s.hymn_enabled, "Couper les strophes");
                ui.add(egui::DragValue::new(&mut s.hymn_max_lines).range(2..=12).suffix(" lignes"));
            });
            row(ui, "Refrain", |ui| {
                ui.checkbox(&mut s.hymn_repeat_chorus, "Répéter après chaque couplet");
            });
            row(ui, "Compteur « (2/5) »", |ui| {
                ui.checkbox(&mut s.show_part_counter, "Afficher la partie en cours");
            });
        },
    );
}

/// Sorties HDMI : la couleur de clé, la taille et la position du texte, le démarrage.
fn outputs_tab(ui: &mut Ui, draft: &mut Settings, screens: &[String]) {
    group(
        ui,
        "Sorties HDMI",
        "Le texte sur fond de clé chroma, pour un mélangeur (ATEM, Roland). Le design se choisit dans la page Designs : il sert au Web, à NDI et au HDMI.",
        |ui| {
            row(ui, "Couleur de clé", |ui| {
                choice(
                    ui,
                    "cle",
                    &mut draft.hdmi.key_color,
                    &[("green", "Vert"), ("magenta", "Magenta"), ("blue", "Bleu")],
                );
            });
            row(ui, "Marges 16:9 (letterbox)", |ui| {
                ui.checkbox(
                    &mut draft.hdmi.letterbox,
                    "Sur un écran qui n'est pas en 16:9, marges à la couleur de clé",
                );
            });
            row(ui, "Taille du texte", |ui| {
                ui.add(egui::Slider::new(&mut draft.hdmi.text_scale, 60..=180).suffix(" %"));
            });
            row(ui, "Décalage vertical", |ui| {
                ui.add(egui::Slider::new(&mut draft.hdmi.offset_y, -300..=300).suffix(" px (en 1080p)"));
            });
            row(ui, "Rouvrir au démarrage", |ui| {
                let shown = if draft.hdmi.enabled && draft.hdmi.screen != "auto" {
                    draft.hdmi.screen.clone()
                } else {
                    "Non".to_string()
                };
                egui::ComboBox::from_id_salt("hdmi-demarrage").selected_text(shown).width(220.0).show_ui(ui, |ui| {
                    if ui.selectable_label(!draft.hdmi.enabled, "Non").clicked() {
                        draft.hdmi.enabled = false;
                    }
                    for s in screens {
                        let on = draft.hdmi.enabled && draft.hdmi.screen == *s;
                        if ui.selectable_label(on, s).clicked() {
                            draft.hdmi.enabled = true;
                            draft.hdmi.screen = s.clone();
                        }
                    }
                });
            });
        },
    );
}

/// Raccourcis : les touches de chaque commande de la régie.
fn shortcuts_tab(ui: &mut Ui, draft: &mut Settings) {
    let mut keys: Map<String, Value> = draft
        .other
        .get("shortcuts")
        .and_then(|s| s.get("keys"))
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    let before = keys.clone();
    group(
        ui,
        "Raccourcis clavier",
        "Une touche ou une combinaison (Ctrl+Maj+D…) ; vide : la touche par défaut.",
        |ui| {
            for (_, id, label, default) in ACTIONS {
                let mut text = keys.get(id).and_then(Value::as_str).unwrap_or(default).to_string();
                row(ui, label, |ui| {
                    if ui.add(egui::TextEdit::singleline(&mut text).desired_width(140.0)).changed() {
                        keys.insert(id.to_string(), json!(text.trim()));
                    }
                    ui.label(RichText::new(format!("par défaut : {default}")).font(regular(11.0)).color(FAINT));
                });
            }
        },
    );
    if keys != before {
        let section = draft.other.entry("shortcuts".to_string()).or_insert_with(|| json!({}));
        if let Some(map) = section.as_object_mut() {
            map.insert("keys".into(), Value::Object(keys));
        }
    }
}

/// Général : le mode PC modeste, la mise à jour, à propos.
fn general_tab(ui: &mut Ui, draft: &mut Settings, update: &UpdateView, actions: &mut Vec<SettingsAction>) {
    group(ui, "Mode PC modeste", "Pour un ordinateur ancien : moins d'effets, la régie reste fluide.", |ui| {
        let mut modest = low_power(draft);
        row(ui, "Moins d'effets", |ui| {
            if ui.checkbox(&mut modest, "Sans transitions ni aperçus de designs (ordinateur ancien)").changed() {
                set_3(draft, "low_power", json!(modest));
            }
        });
    });
    group(ui, "Mise à jour", "Les nouvelles versions gardent vos cantiques, playlists et réglages.", |ui| {
        update_section(ui, draft, update, actions);
    });
    group(ui, "À propos", "", |ui| {
        ui.horizontal(|ui| {
            let (rect, _) = ui.allocate_exact_size(vec2(64.0, 64.0), Sense::hover());
            crate::theme::paint_shadow(
                ui.painter(),
                rect,
                CornerRadius::same(15),
                6,
                18,
                Color32::from_black_alpha(150),
            );
            crate::theme::paint_logo(ui.painter(), rect);
            ui.add_space(12.0);
            ui.vertical(|ui| {
                ui.label(
                    RichText::new(format!("Project-On {}", env!("CARGO_PKG_VERSION"))).font(bold(16.0)).color(TEXT),
                );
                ui.label(RichText::new("Projection pour églises · gratuit").font(regular(12.5)).color(MUTED));
                ui.label(RichText::new("ParaTech Sarl, Kinshasa").font(regular(12.0)).color(FAINT));
                ui.hyperlink_to(
                    RichText::new("Site de Project-On").font(medium(12.0)),
                    "https://elieny7.github.io/paratech-web/project-on.html",
                );
            });
        });
    });
}

/// Une couleur du profil de l'église.
fn rgba_edit(ui: &mut Ui, value: &mut Rgba) -> bool {
    let mut c32 = Color32::from_rgba_unmultiplied(value.0[0], value.0[1], value.0[2], 255);
    let changed =
        egui::color_picker::color_edit_button_srgba(ui, &mut c32, egui::color_picker::Alpha::Opaque).changed();
    if changed {
        let [r, g, b, _] = c32.to_srgba_unmultiplied();
        *value = Rgba::rgb(r, g, b);
    }
    changed
}

fn field(ui: &mut Ui, label: &str, value: &mut String, hint: &str, width: f32) -> bool {
    let mut changed = false;
    row(ui, label, |ui| {
        let width = width.min(ui.available_width());
        let r = ui.add(egui::TextEdit::singleline(value).hint_text(hint).desired_width(width));
        let name = format!("Champ : {label}");
        ui.ctx().accesskit_node_builder(r.id, |n| n.set_label(name));
        changed = r.changed();
    });
    changed
}

/// Le profil de l'église (section `church` des réglages, au format de la 2.x) : il sert aux
/// écrans d'accueil, de l'orateur du jour et des réseaux sociaux, et aux images de citation.
fn church_profile(
    ui: &mut Ui,
    draft: &mut Settings,
    families: &[String],
    gallery: &mut crate::gallery::Gallery,
    actions: &mut Vec<SettingsAction>,
) {
    use po_design::church::{ChurchBackground, ChurchProfile, SOCIAL_PLATFORMS};
    let mut p = ChurchProfile::from_settings(draft.other.get("church"));
    let before = p.clone();
    group(ui, "Identité", "Le nom, le logo et les couleurs de l'église, sur ses écrans et ses images.", |ui| {
        field(ui, "Nom de l'église", &mut p.name, "Assemblée de…", 360.0);
        field(ui, "Titre d'accueil", &mut p.welcome_title, "Bienvenue", 240.0);
        field(ui, "Devise ou verset", &mut p.motto, "", 480.0);
        row(ui, "Horaires des cultes (un par ligne)", |ui| {
            let width = ui.available_width().min(360.0);
            ui.add(egui::TextEdit::multiline(&mut p.service_times).desired_rows(3).desired_width(width));
        });
        field(ui, "Contact (adresse)", &mut p.contact, "", 480.0);
        image_field(ui, gallery, "Logo", &mut p.logo, true);
        row(ui, "Couleurs (fond, accent, texte)", |ui| {
            rgba_edit(ui, &mut p.primary_color);
            rgba_edit(ui, &mut p.accent_color);
            rgba_edit(ui, &mut p.text_color);
        });
        row(ui, "Police", |ui| {
            egui::ComboBox::from_id_salt("police-eglise").selected_text(p.font_family.as_str()).width(220.0).show_ui(
                ui,
                |ui| {
                    for f in families {
                        if ui.selectable_label(p.font_family == *f, f).clicked() {
                            p.font_family = f.clone();
                        }
                    }
                },
            );
        });
    });
    group(ui, "Écrans de l'église", "Le fond de l'accueil, de l'orateur du jour et des réseaux sociaux.", |ui| {
        row(ui, "Fond des écrans", |ui| {
            widgets::segmented(
                ui,
                &mut p.background,
                &[
                    (ChurchBackground::Gradient, "Dégradé"),
                    (ChurchBackground::Solid, "Uni"),
                    (ChurchBackground::Image, "Image"),
                ],
            );
        });
        if p.background == ChurchBackground::Image {
            image_field(ui, gallery, "Image de fond", &mut p.background_image, false);
            row(ui, "Assombrir l'image", |ui| {
                ui.add(egui::Slider::new(&mut p.background_dim, 0..=85).suffix(" %"));
            });
        }
    });
    group(
        ui,
        "Pasteur et orateur du jour",
        "L'écran « orateur du jour » (Ctrl+Maj+P) montre l'invité, sinon le pasteur.",
        |ui| {
            field(ui, "Titre du pasteur", &mut p.pastor_title, "Pasteur", 200.0);
            field(ui, "Nom du pasteur", &mut p.pastor_name, "", 300.0);
            image_field(ui, gallery, "Photo du pasteur (PNG sans fond)", &mut p.pastor_photo, true);
            ui.add_space(6.0);
            field(ui, "Orateur invité : titre", &mut p.speaker_title, "Frère", 200.0);
            field(ui, "Orateur invité : nom (vide : le pasteur)", &mut p.speaker_name, "", 300.0);
            image_field(ui, gallery, "Orateur invité : photo", &mut p.speaker_photo, true);
            field(ui, "Message du jour", &mut p.speaker_message, "", 480.0);
        },
    );
    group(
        ui,
        "Réseaux sociaux",
        "Affichés sur l'écran d'accueil et les images de citation, avec un QR code.",
        |ui| {
            let mut socials: Vec<(String, String)> = Vec::new();
            for platform in SOCIAL_PLATFORMS {
                let mut value = p.social(platform.key).unwrap_or("").to_string();
                field(ui, platform.label, &mut value, platform.placeholder, 320.0);
                if !value.trim().is_empty() {
                    socials.push((platform.key.to_string(), value.trim().to_string()));
                }
            }
            p.socials = socials;
            row(ui, "QR code vers", |ui| {
                let shown = po_design::church::platform(&p.qr_target).map_or("Aucun", |q| q.label);
                egui::ComboBox::from_id_salt("qr-eglise").selected_text(shown).show_ui(ui, |ui| {
                    ui.selectable_value(&mut p.qr_target, String::new(), "Aucun");
                    for (k, _) in p.socials.clone() {
                        let label = po_design::church::platform(&k).map_or(k.clone(), |q| q.label.to_string());
                        ui.selectable_value(&mut p.qr_target, k, label);
                    }
                });
            });
            row(ui, "Sur l'écran d'accueil", |ui| {
                ui.checkbox(&mut p.show_socials_welcome, "Afficher les réseaux");
            });
            row(ui, "Sur les images de citation", |ui| {
                ui.checkbox(&mut p.show_socials_quotes, "Afficher les réseaux");
            });
        },
    );
    group(
        ui,
        "Photos de l'église",
        "Le fond du modèle « Photo » des images de citation ; projetables en diaporama.",
        |ui| {
            let mut wanted = Vec::new();
            gallery.ui(ui, &mut p.photos, &mut wanted);
            for crate::gallery::GalleryAction::Project(photos) in wanted {
                actions.push(SettingsAction::ShowPhotos(photos));
            }
        },
    );
    if p != before {
        let section = draft.other.entry("church".to_string()).or_insert_with(|| json!({}));
        if !section.is_object() {
            *section = json!({});
        }
        if let Some(map) = section.as_object_mut() {
            p.write_into(map);
        }
    }
}

/// Le pilotage d'OBS (obs-websocket 5) : connexion, scènes du direct et du texte masqué, source
/// navigateur. Les réglages sont ceux de la 2.x (`obs.remote`), le mot de passe chiffré.
fn obs_section(
    ui: &mut Ui,
    draft: &mut Settings,
    (state, scenes, message): &(crate::obs::ObsState, Vec<String>, String),
    source_scene: &mut String,
    actions: &mut Vec<SettingsAction>,
) {
    let mut o = crate::obs::ObsSettings::from_settings(draft);
    let before = o.clone();
    row(ui, "Piloter OBS", |ui| {
        ui.checkbox(&mut o.enabled, "Changer de scène au direct et au masquage (obs-websocket, OBS 28 ou plus)");
    });
    if o.enabled {
        field(ui, "Adresse d'OBS", &mut o.host, "127.0.0.1", 200.0);
        row(ui, "Port", |ui| {
            ui.add(egui::DragValue::new(&mut o.port).range(1..=65535));
        });
        row(ui, "Mot de passe (OBS → Outils → Paramètres WebSocket)", |ui| {
            let r = ui.add(egui::TextEdit::singleline(&mut o.password).password(true).desired_width(220.0));
            ui.ctx().accesskit_node_builder(r.id, |n| n.set_label("Champ : mot de passe d'OBS"));
        });
        row(ui, "État", |ui| {
            let color = match state {
                crate::obs::ObsState::Connected => PREVIEW,
                crate::obs::ObsState::Failed(_) => WARN,
                _ => MUTED,
            };
            ui.label(RichText::new(state.label()).font(medium(12.0)).color(color));
            if *state == crate::obs::ObsState::Connected
                && widgets::button(ui, None, "Actualiser les scènes", Tone::Secondary).clicked()
            {
                actions.push(SettingsAction::ObsRefresh);
            }
        });
        let scene_choice = |ui: &mut Ui, id: &str, value: &mut String| {
            let shown = if value.is_empty() { "Ne pas changer".to_string() } else { value.clone() };
            egui::ComboBox::from_id_salt(id).selected_text(shown).width(220.0).show_ui(ui, |ui| {
                ui.selectable_value(value, String::new(), "Ne pas changer");
                for s in scenes {
                    ui.selectable_value(value, s.clone(), s);
                }
            });
        };
        row(ui, "Scène quand un slide passe au direct", |ui| scene_choice(ui, "obs-direct", &mut o.scene_on_live));
        row(ui, "Scène quand le texte est masqué", |ui| scene_choice(ui, "obs-masque", &mut o.scene_on_hide));
        if !scenes.is_empty() {
            row(ui, "Source « Project-On » (écran Diffusion)", |ui| {
                if source_scene.is_empty() || !scenes.contains(source_scene) {
                    *source_scene = scenes[0].clone();
                }
                egui::ComboBox::from_id_salt("obs-source").selected_text(source_scene.as_str()).width(180.0).show_ui(
                    ui,
                    |ui| {
                        for s in scenes {
                            ui.selectable_value(source_scene, s.clone(), s);
                        }
                    },
                );
                if widgets::button(ui, None, "Créer dans OBS", Tone::Secondary).clicked() {
                    actions.push(SettingsAction::ObsCreateSource(source_scene.clone()));
                }
            });
        }
        if !message.is_empty() {
            ui.label(RichText::new(message).font(regular(11.5)).color(MUTED));
        }
        ui.label(
            RichText::new(
                "Le mot de passe est chiffré pour ce compte Windows, comme dans la 2.8. Enregistrez pour appliquer.",
            )
            .font(regular(11.5))
            .color(FAINT),
        );
    }
    if o != before {
        o.write_into(draft);
    }
}

/// La mise à jour (`UpdateDialog` de la 2.8) : rechercher, télécharger, installer.
fn update_section(ui: &mut Ui, draft: &mut Settings, update: &UpdateView, actions: &mut Vec<SettingsAction>) {
    row(ui, "Au démarrage", |ui| {
        ui.checkbox(
            &mut draft.appearance.check_updates,
            "Rechercher une nouvelle version (si Internet est disponible)",
        );
    });
    ui.horizontal(|ui| {
        ui.label(
            RichText::new(format!("Version installée : {}", env!("CARGO_PKG_VERSION")))
                .font(regular(12.0))
                .color(MUTED),
        );
        if widgets::button_at(
            ui,
            widgets::Size::Normal,
            None,
            "Rechercher une mise à jour",
            Tone::Secondary,
            !update.busy,
        )
        .clicked()
        {
            actions.push(SettingsAction::UpdateCheck);
        }
        if update.busy {
            ui.spinner();
        }
    });
    if !update.status.is_empty() {
        ui.label(RichText::new(&update.status).font(medium(12.0)).color(if update.available.is_some() {
            PREVIEW
        } else {
            MUTED
        }));
    }
    if let Some(path) = &update.ready {
        ui.horizontal(|ui| {
            if widgets::button(ui, None, "Installer maintenant (Project-On se ferme)", Tone::Primary(ACCENT)).clicked()
            {
                actions.push(SettingsAction::UpdateInstall);
            }
            ui.label(RichText::new(path.display().to_string()).font(regular(11.0)).color(FAINT));
        });
    } else if update.available.is_some() && !update.busy {
        ui.horizontal(|ui| {
            if cfg!(feature = "bascule") {
                if widgets::button(ui, None, "Télécharger la mise à jour", Tone::Primary(ACCENT)).clicked() {
                    actions.push(SettingsAction::UpdateDownload);
                }
            } else if widgets::button(ui, None, "Ouvrir la page de la version", Tone::Secondary).clicked() {
                actions.push(SettingsAction::UpdatePage);
            }
            ui.label(
                RichText::new("L'installation garde vos cantiques, playlists et réglages.")
                    .font(regular(11.5))
                    .color(FAINT),
            );
        });
    }
}

/// La liste des vérifications du contrôle avant culte.
pub fn checks_list(ui: &mut Ui, checks: &[Check]) {
    for c in checks {
        ui.horizontal(|ui| {
            let color = match c.level {
                Level::Ok => PREVIEW,
                Level::Warning => WARN,
                Level::Problem => LIVE,
            };
            widgets::dot(ui, color);
            ui.label(RichText::new(&c.title).font(semibold(12.5)).color(TEXT));
            ui.label(RichText::new(&c.detail).font(regular(12.0)).color(MUTED));
        });
    }
}

/// La couleur de clé lue des réglages (pour l'aperçu).
pub fn key_color(settings: &Settings) -> Rgba {
    po_layout::graphics::key_color(&settings.hdmi.key_color)
}
