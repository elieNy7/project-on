//! La page « Réglages » : la projection (texte, fond, transitions, écran), le découpage des slides,
//! la diffusion (couleur de clé HDMI), les raccourcis, le mode PC modeste et l'entretien
//! (sauvegardes, contrôle avant culte). Les réglages sont ceux du `settings.json` de la bêta, écrits
//! avec les mêmes règles que la 2.x (écriture d'un coup, copie `.bak`).

use egui::{Color32, RichText, Ui};
use po_design::{IdentificationStyle, Rgba, parse_color};
use po_settings::Settings;
use serde_json::{Map, Value, json};

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
    /// La galerie des photos de l'église.
    pub gallery: crate::gallery::Gallery,
    /// Le pilotage d'OBS : état, scènes, dernier message.
    pub obs: (crate::obs::ObsState, Vec<String>, String),
    /// La scène où créer la source « Project-On ».
    pub obs_source_scene: String,
}

fn row(ui: &mut Ui, label: &str, add: impl FnOnce(&mut Ui)) {
    ui.horizontal(|ui| {
        ui.add_sized([230.0, 22.0], egui::Label::new(RichText::new(label).font(regular(12.5)).color(MUTED)));
        add(ui);
    });
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

    /// La page. `current` : les réglages en vigueur (le brouillon part d'eux).
    pub fn ui(&mut self, ui: &mut Ui, current: &Settings) -> Vec<SettingsAction> {
        let mut actions = Vec::new();
        let draft = self.draft.get_or_insert_with(|| current.clone());
        let families = self.families.clone();
        let screens = self.screens.clone();
        egui::ScrollArea::vertical().auto_shrink([false, false]).show(ui, |ui| {
            ui.add_space(12.0);
            ui.horizontal(|ui| {
                ui.label(RichText::new("Réglages").font(bold(20.0)).color(TEXT));
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let changed = draft != current;
                    if widgets::button_at(
                        ui,
                        widgets::Size::Normal,
                        None,
                        "Enregistrer",
                        Tone::Primary(ACCENT),
                        changed,
                    )
                    .clicked()
                    {
                        actions.push(SettingsAction::Save(Box::new(draft.clone())));
                    }
                    if changed && widgets::button(ui, None, "Annuler les changements", Tone::Secondary).clicked() {
                        *draft = current.clone();
                    }
                });
            });
            ui.label(
                RichText::new(if cfg!(feature = "bascule") {
                    "Ces réglages sont ceux de Project-On (les mêmes fichiers que la 2.x)."
                } else {
                    "Ces réglages sont ceux de la bêta : la 2.8 garde les siens."
                })
                .font(regular(12.0))
                .color(FAINT),
            );

            widgets::section(ui, "Mode PC modeste");
            let mut modest = low_power(draft);
            row(ui, "Moins d'effets", |ui| {
                if ui.checkbox(&mut modest, "Sans transitions ni aperçus de designs (ordinateur ancien)").changed() {
                    set_3(draft, "low_power", json!(modest));
                }
            });

            widgets::section(ui, "Entretien");
            ui.horizontal(|ui| {
                if widgets::button(ui, None, "Sauvegarder maintenant", Tone::Secondary).clicked() {
                    actions.push(SettingsAction::Backup);
                }
                if widgets::button(ui, None, "Contrôle avant culte  Ctrl+Maj+D", Tone::Secondary).clicked() {
                    actions.push(SettingsAction::Preflight);
                }
            });
            match self.backups.first() {
                Some(b) => {
                    ui.horizontal(|ui| {
                        let name = b.dir.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
                        ui.label(
                            RichText::new(format!(
                                "{} sauvegarde(s) ; la dernière : {name} ({} Mo)",
                                self.backups.len(),
                                b.bytes / 1_000_000
                            ))
                            .font(regular(12.0))
                            .color(MUTED),
                        );
                        if let Some(dir) = b.dir.parent()
                            && widgets::button(ui, None, "Ouvrir le dossier", Tone::Secondary).clicked()
                        {
                            actions.push(SettingsAction::OpenFolder(dir.to_path_buf()));
                        }
                    });
                }
                None => {
                    ui.label(RichText::new("Aucune sauvegarde pour l'instant.").font(regular(12.0)).color(WARN));
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
            if !self.checks.is_empty() {
                ui.add_space(6.0);
                checks_list(ui, &self.checks);
            }
            widgets::section(ui, "Projection : le texte");
            let p = &mut draft.projection;
            row(ui, "Police", |ui| {
                egui::ComboBox::from_id_salt("police").selected_text(p.font_family.as_str()).width(220.0).show_ui(
                    ui,
                    |ui| {
                        for f in &families {
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
                ui.add(egui::DragValue::new(&mut p.text_size).range(10..=320));
            });
            row(ui, "Taille minimale", |ui| {
                ui.add(egui::DragValue::new(&mut p.min_text_size).range(10..=200));
            });
            row(ui, "Capitales", |ui| {
                ui.checkbox(&mut p.uppercase, "");
            });
            row(ui, "Couleur du texte", |ui| color(ui, &mut p.text_color));
            row(ui, "Ombre du texte", |ui| {
                ui.checkbox(&mut p.text_shadow, "");
            });
            row(ui, "Alignement", |ui| {
                choice(ui, "align", &mut p.align, &[("left", "À gauche"), ("center", "Centré"), ("right", "À droite")])
            });
            row(ui, "Référence", |ui| {
                ui.checkbox(&mut p.show_reference, "Afficher");
                choice(ui, "refpos", &mut p.reference_position, &[("top", "En haut"), ("bottom", "En bas")]);
            });
            row(ui, "Couleur de la référence", |ui| color(ui, &mut p.ref_color));

            widgets::section(ui, "Projection : le fond");
            row(ui, "Fond", |ui| choice(ui, "fond", &mut p.bg_mode, &[("color", "Couleur"), ("image", "Image")]));
            row(ui, "Couleur", |ui| color(ui, &mut p.bg_color));
            row(ui, "Dégradé", |ui| {
                ui.checkbox(&mut p.bg_gradient_enabled, "");
                if p.bg_gradient_enabled {
                    color(ui, &mut p.bg_color_2);
                }
            });
            row(ui, "Image (chemin du fichier)", |ui| {
                ui.add(egui::TextEdit::singleline(&mut p.bg_image).desired_width(360.0));
            });
            row(ui, "Assombrir l'image", |ui| {
                ui.add(egui::Slider::new(&mut p.background_dimmer, 0.0..=0.85));
            });

            widgets::section(ui, "Projection : les transitions et l'écran");
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
            row(ui, "Durée (ms)", |ui| {
                ui.add(egui::DragValue::new(&mut p.animation_duration).range(0..=3000));
            });
            row(ui, "Écran de la salle", |ui| {
                let mut options: Vec<(&str, &str)> = vec![("", "Automatique (le plus grand écran secondaire)")];
                options.extend(screens.iter().map(|s| (s.as_str(), s.as_str())));
                choice(ui, "ecran", &mut p.display_screen, &options);
            });

            widgets::section(ui, "Identification de Branham");
            let mut style = identification_style(draft);
            row(ui, "Style", |ui| {
                for s in IdentificationStyle::ALL {
                    ui.radio_value(&mut style, s, s.label());
                }
            });
            if style != identification_style(draft) {
                let key = match style {
                    IdentificationStyle::Elegant => "elegant",
                    IdentificationStyle::Minimal => "minimal",
                    IdentificationStyle::Band => "band",
                    IdentificationStyle::Transparent => "transparent",
                };
                set_3(draft, "identification", json!(key));
            }

            widgets::section(ui, "Découpage des slides");
            let s = &mut draft.split;
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
                ui.checkbox(&mut s.show_part_counter, "");
            });

            widgets::section(ui, "Pilotage d'OBS");
            obs_section(ui, draft, &self.obs, &mut self.obs_source_scene, &mut actions);

            widgets::section(ui, "Diffusion");
            row(ui, "Couleur de clé des sorties HDMI", |ui| {
                choice(
                    ui,
                    "cle",
                    &mut draft.hdmi.key_color,
                    &[("green", "Vert"), ("magenta", "Magenta"), ("blue", "Bleu")],
                );
            });
            row(ui, "Marges 16:9 (letterbox)", |ui| {
                ui.checkbox(&mut draft.hdmi.letterbox, "Sur un écran qui n'est pas en 16:9, marges à la couleur de clé");
            });
            row(ui, "Taille du texte HDMI", |ui| {
                ui.add(egui::Slider::new(&mut draft.hdmi.text_scale, 60..=180).suffix(" %"));
            });
            row(ui, "Décalage vertical HDMI", |ui| {
                ui.add(egui::Slider::new(&mut draft.hdmi.offset_y, -300..=300).suffix(" px (en 1080p)"));
            });
            row(ui, "Rouvrir la sortie HDMI au démarrage", |ui| {
                let shown = if draft.hdmi.enabled && draft.hdmi.screen != "auto" {
                    draft.hdmi.screen.clone()
                } else {
                    "Non".to_string()
                };
                egui::ComboBox::from_id_salt("hdmi-demarrage").selected_text(shown).width(220.0).show_ui(ui, |ui| {
                    if ui.selectable_label(!draft.hdmi.enabled, "Non").clicked() {
                        draft.hdmi.enabled = false;
                    }
                    for s in &screens {
                        let on = draft.hdmi.enabled && draft.hdmi.screen == *s;
                        if ui.selectable_label(on, s).clicked() {
                            draft.hdmi.enabled = true;
                            draft.hdmi.screen = s.clone();
                        }
                    }
                });
            });
            ui.label(
                RichText::new(
                    "Le design des sorties (bandeau ou design de slide) se choisit dans la page Designs : il sert au Web, à NDI et au HDMI.",
                )
                .font(regular(11.5))
                .color(FAINT),
            );

            widgets::section(ui, "Profil de l'église");
            church_profile(ui, draft, &families, &mut self.gallery, &mut actions);

            widgets::section(ui, "Raccourcis");
            let mut keys: Map<String, Value> = draft
                .other
                .get("shortcuts")
                .and_then(|s| s.get("keys"))
                .and_then(Value::as_object)
                .cloned()
                .unwrap_or_default();
            let before = keys.clone();
            for (_, id, label, default) in ACTIONS {
                let mut text = keys.get(id).and_then(Value::as_str).unwrap_or(default).to_string();
                row(ui, label, |ui| {
                    if ui.add(egui::TextEdit::singleline(&mut text).desired_width(140.0)).changed() {
                        keys.insert(id.to_string(), json!(text.trim()));
                    }
                    ui.label(RichText::new(format!("par défaut : {default}")).font(regular(11.0)).color(FAINT));
                });
            }
            if keys != before {
                let section = draft.other.entry("shortcuts".to_string()).or_insert_with(|| json!({}));
                if let Some(map) = section.as_object_mut() {
                    map.insert("keys".into(), Value::Object(keys));
                }
            }

            ui.add_space(24.0);
        });
        actions
    }
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
        let r = ui.add(egui::TextEdit::singleline(value).hint_text(hint).desired_width(width));
        let name = format!("Champ : {label}");
        ui.ctx().accesskit_node_builder(r.id, |n| n.set_label(name));
        changed = r.changed();
    });
    changed
}

/// Le profil de l'église (section `church` des réglages, au format de la 2.x) : il sert aux
/// écrans d'accueil, de l'orateur du jour et des réseaux sociaux.
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
    field(ui, "Nom de l'église", &mut p.name, "Assemblée de…", 360.0);
    field(ui, "Titre d'accueil", &mut p.welcome_title, "Bienvenue", 240.0);
    field(ui, "Devise ou verset", &mut p.motto, "", 480.0);
    row(ui, "Horaires des cultes (un par ligne)", |ui| {
        ui.add(egui::TextEdit::multiline(&mut p.service_times).desired_rows(3).desired_width(360.0));
    });
    field(ui, "Contact (adresse)", &mut p.contact, "", 480.0);
    field(ui, "Logo (chemin du fichier)", &mut p.logo, r"C:\…\logo.png", 480.0);
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
    row(ui, "Fond des écrans", |ui| {
        ui.radio_value(&mut p.background, ChurchBackground::Gradient, "Dégradé");
        ui.radio_value(&mut p.background, ChurchBackground::Solid, "Uni");
        ui.radio_value(&mut p.background, ChurchBackground::Image, "Image");
    });
    if p.background == ChurchBackground::Image {
        field(ui, "Image de fond", &mut p.background_image, "", 480.0);
        row(ui, "Assombrir l'image (%)", |ui| {
            ui.add(egui::Slider::new(&mut p.background_dim, 0..=85));
        });
    }
    field(ui, "Titre du pasteur", &mut p.pastor_title, "Pasteur", 200.0);
    field(ui, "Nom du pasteur", &mut p.pastor_name, "", 300.0);
    field(ui, "Photo du pasteur (PNG sans fond)", &mut p.pastor_photo, "", 480.0);
    field(ui, "Orateur invité : titre", &mut p.speaker_title, "Frère", 200.0);
    field(ui, "Orateur invité : nom (vide : le pasteur)", &mut p.speaker_name, "", 300.0);
    field(ui, "Orateur invité : photo", &mut p.speaker_photo, "", 480.0);
    field(ui, "Message du jour", &mut p.speaker_message, "", 480.0);
    ui.label(RichText::new("Réseaux sociaux").font(semibold(12.5)).color(TEXT));
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
    row(ui, "Réseaux sur l'écran d'accueil", |ui| {
        ui.checkbox(&mut p.show_socials_welcome, "");
    });
    row(ui, "Réseaux sur les images de citation", |ui| {
        ui.checkbox(&mut p.show_socials_quotes, "");
    });
    ui.add_space(6.0);
    ui.label(RichText::new("Photos de l'église").font(semibold(12.5)).color(TEXT));
    ui.label(
        RichText::new("Le fond du modèle « Photo » des images de citation ; projetables en diaporama.")
            .font(regular(11.5))
            .color(FAINT),
    );
    let mut wanted = Vec::new();
    gallery.ui(ui, &mut p.photos, &mut wanted);
    for crate::gallery::GalleryAction::Project(photos) in wanted {
        actions.push(SettingsAction::ShowPhotos(photos));
    }
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
