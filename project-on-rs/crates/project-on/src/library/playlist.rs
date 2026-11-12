//! La page Playlist : les playlists, leurs slides (genre, deux lignes de texte), les sections du
//! déroulé en en-têtes repliables, la sélection multiple (Ctrl, Maj), le glisser-déposer, le menu
//! contextuel (projeter, dupliquer, copier ou déplacer vers une autre playlist, commencer une
//! section ici) et le panneau « Déroulé du culte ».
//!
//! La page ne modifie rien elle-même : elle rend des [`PlaylistAction`] que l'application applique
//! (avec l'annulation), puis elle se recharge.

use std::collections::HashSet;

use egui::{
    Align, Align2, CornerRadius, Key, Layout, Modifiers, Rect, RichText, ScrollArea, Sense, Stroke, Ui, pos2, vec2,
};
use po_db::{Database, Folder, PlaylistItem, Section};

use crate::icons;
use crate::playlist::{drop_selection, item_kind, move_selection};
use crate::service::{self, Tracker, clock, describe_delay, format_duration};
use crate::theme::*;
use crate::widgets::{self, Size, Tone};

/// Les noms de sections proposés (`SECTION_SUGGESTIONS` de la 2.8).
pub const SECTION_SUGGESTIONS: [&str; 8] =
    ["Louange", "Annonces", "Prière", "Offrande", "Prédication", "Sainte Cène", "Baptêmes", "Clôture"];

/// Ce que demande la page.
#[derive(Debug, Clone, PartialEq)]
pub enum PlaylistAction {
    SelectFolder(i64),
    CreateFolder(String),
    RenameFolder(i64, String),
    DeleteFolder(i64),
    CreateItem(String, String),
    UpdateItem(i64, String, String),
    Delete(Vec<i64>),
    Duplicate(Vec<i64>),
    Reorder(Vec<i64>),
    CopyTo(Vec<i64>, i64),
    MoveTo(Vec<i64>, i64),
    Undo,
    /// Préparer la playlist dans l'Aperçu à partir de cet élément.
    Cue(i64),
    /// L'envoyer au direct à partir de cet élément (double-clic, « Projeter »).
    Take(i64),
    /// Une section commence à ce slide (`None` : une nouvelle section, avec son nom et sa durée).
    StartSectionAt {
        section: Option<i64>,
        item: i64,
        name: String,
        duration: i64,
    },
    DetachSection(i64),
    AddSection {
        name: String,
        duration: i64,
        item: Option<i64>,
    },
    UpdateSection {
        id: i64,
        name: String,
        duration: i64,
        item: Option<i64>,
    },
    DeleteSection(i64),
    MoveSection(i64, i64),
    SetStartTime(String),
    StartService,
    StopService,
    NextSection,
    /// Exporter la playlist choisie (archive au format de la 2.8).
    Export,
    /// Importer une playlist exportée (par la 2.8 ou la 3.0).
    Import(std::path::PathBuf),
    /// Lancer le diaporama des images de la playlist.
    Slideshow,
}

/// Le dossier d'échange des playlists : « Documents\Project-On playlists ».
pub fn exchange_dir() -> Option<std::path::PathBuf> {
    std::env::var_os("USERPROFILE").map(|h| std::path::PathBuf::from(h).join("Documents").join("Project-On playlists"))
}

/// Les playlists exportées du dossier d'échange (archives et anciens JSON), les plus récentes d'abord.
pub fn exchange_files() -> Vec<std::path::PathBuf> {
    let Some(dir) = exchange_dir() else { return Vec::new() };
    let Ok(entries) = std::fs::read_dir(dir) else { return Vec::new() };
    let mut files: Vec<(std::time::SystemTime, std::path::PathBuf)> = entries
        .flatten()
        .map(|e| e.path())
        .filter(|p| {
            p.extension()
                .and_then(|e| e.to_str())
                .is_some_and(|e| matches!(e.to_lowercase().as_str(), "zip" | "json" | "poplaylist"))
        })
        .map(|p| (std::fs::metadata(&p).and_then(|m| m.modified()).unwrap_or(std::time::UNIX_EPOCH), p))
        .collect();
    files.sort_by_key(|f| std::cmp::Reverse(f.0));
    files.into_iter().map(|(_, p)| p).collect()
}

/// Une boîte de dialogue ouverte.
#[derive(Debug, Clone, PartialEq)]
enum Dialog {
    Folder { id: Option<i64>, name: String },
    Item { id: Option<i64>, reference: String, text: String },
    DeleteFolder { id: i64, name: String },
    Section { id: Option<i64>, name: String, duration: i64, link: Option<i64>, linked: bool },
}

/// Les éléments montrés dans l'Aperçu et au direct.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct PlaylistMarks {
    pub preview: Option<i64>,
    pub live: Option<i64>,
}

const ROW: f32 = 54.0;
const HEADER: f32 = 32.0;

#[derive(Default)]
pub struct PlaylistView {
    folders: Vec<(Folder, usize)>,
    pub folder: Option<i64>,
    pub items: Vec<PlaylistItem>,
    pub sections: Vec<Section>,
    collapsed: HashSet<i64>,
    /// Les éléments choisis, le dernier cliqué en premier.
    pub selected: Vec<i64>,
    anchor: Option<i64>,
    drag: Option<Vec<i64>>,
    /// Où la sélection glissée se posera (dernière position vue du pointeur).
    drop_at: usize,
    dialog: Option<Dialog>,
    loaded: bool,
    pub start_time: String,
    pub show_plan: bool,
    selected_section: Option<i64>,
    /// La liste des slides a le clavier (Suppr, Ctrl+D, Ctrl+A…).
    list_focus: bool,
    message: Option<String>,
    /// Où en est le rendu de chaque PowerPoint (« 12 slides », « en préparation »…).
    pub office_labels: std::collections::HashMap<String, String>,
}

impl PlaylistView {
    /// Recharge les playlists et la playlist choisie (après chaque modification).
    pub fn reload(&mut self, db: &Database, select: Option<Vec<i64>>) {
        self.loaded = true;
        self.folders = db
            .list_folders()
            .unwrap_or_default()
            .into_iter()
            .map(|f| {
                let n = db.list_items(Some(f.id)).map(|v| v.len()).unwrap_or(0);
                (f, n)
            })
            .collect();
        if self.folder.is_none_or(|id| !self.folders.iter().any(|(f, _)| f.id == id)) {
            self.folder = self.folders.first().map(|(f, _)| f.id);
        }
        self.items = self.folder.map(|f| db.list_items(Some(f)).unwrap_or_default()).unwrap_or_default();
        self.sections = self.folder.map(|f| db.list_sections(f).unwrap_or_default()).unwrap_or_default();
        self.start_time = self.folder.map(|f| db.start_time(f).unwrap_or_default()).unwrap_or_default();
        let ids: HashSet<i64> = self.items.iter().map(|i| i.id).collect();
        self.selected = match select {
            Some(s) => s.into_iter().filter(|id| ids.contains(id)).collect(),
            None => self.selected.iter().copied().filter(|id| ids.contains(id)).collect(),
        };
        if self.selected.is_empty()
            && let Some(first) = self.items.first()
        {
            self.selected = vec![first.id];
        }
    }

    pub fn ensure_loaded(&mut self, db: &Database) {
        if !self.loaded {
            self.reload(db, None);
        }
    }

    /// L'ordre de la playlist.
    pub fn order(&self) -> Vec<i64> {
        self.items.iter().map(|i| i.id).collect()
    }

    /// Les éléments choisis, dans l'ordre de la playlist.
    pub fn selection(&self) -> Vec<i64> {
        self.items.iter().map(|i| i.id).filter(|id| self.selected.contains(id)).collect()
    }

    pub fn folder_name(&self) -> String {
        self.folders.iter().find(|(f, _)| Some(f.id) == self.folder).map(|(f, _)| f.name.clone()).unwrap_or_default()
    }

    pub fn other_folders(&self) -> Vec<(i64, String)> {
        self.folders.iter().filter(|(f, _)| Some(f.id) != self.folder).map(|(f, _)| (f.id, f.name.clone())).collect()
    }

    pub fn say(&mut self, message: impl Into<String>) {
        self.message = Some(message.into());
    }

    /// Un clic sur un slide : seul, Ctrl (ajoute / retire), Maj (plage depuis le dernier cliqué).
    pub fn click(&mut self, id: i64, modifiers: Modifiers) {
        if modifiers.command {
            if let Some(i) = self.selected.iter().position(|s| *s == id) {
                self.selected.remove(i);
            } else {
                self.selected.insert(0, id);
            }
            self.anchor = Some(id);
        } else if modifiers.shift
            && let Some(anchor) = self.anchor
        {
            let order = self.order();
            let (a, b) = (order.iter().position(|x| *x == anchor), order.iter().position(|x| *x == id));
            if let (Some(a), Some(b)) = (a, b) {
                let (lo, hi) = (a.min(b), a.max(b));
                self.selected = order[lo..=hi].to_vec();
                self.selected.retain(|x| *x != id);
                self.selected.insert(0, id);
            }
        } else {
            self.selected = vec![id];
            self.anchor = Some(id);
        }
    }

    pub fn ui(
        &mut self,
        ui: &mut Ui,
        db: &Database,
        marks: PlaylistMarks,
        tracker: &Tracker,
        undo_available: bool,
    ) -> Vec<PlaylistAction> {
        self.ensure_loaded(db);
        let mut actions = Vec::new();
        let left = 250.0;
        ui.horizontal_top(|ui| {
            ui.allocate_ui_with_layout(vec2(left, ui.available_height()), Layout::top_down(Align::Min), |ui| {
                ui.set_width(left);
                self.folder_column(ui, &mut actions);
            });
            ui.add_space(10.0);
            ui.allocate_ui_with_layout(ui.available_size(), Layout::top_down(Align::Min), |ui| {
                self.items_column(ui, marks, tracker, undo_available, &mut actions);
            });
        });
        self.keyboard(ui, &mut actions);
        self.dialogs(ui, &mut actions);
        actions
    }

    fn folder_column(&mut self, ui: &mut Ui, actions: &mut Vec<PlaylistAction>) {
        widgets::section_with(ui, "Playlists", |ui| {
            if widgets::button(ui, Some(icons::Icon::Plus), "Nouvelle", Tone::Secondary).clicked() {
                self.dialog = Some(Dialog::Folder { id: None, name: String::new() });
            }
        });
        ui.add_space(4.0);
        if self.folders.is_empty() {
            super::empty(ui, "Aucune playlist : « Nouvelle » en crée une.");
            return;
        }
        ScrollArea::vertical().id_salt("playlists").auto_shrink([false, false]).show(ui, |ui| {
            for (folder, count) in self.folders.clone() {
                let selected = Some(folder.id) == self.folder;
                let r = super::item_row(
                    ui,
                    selected,
                    &folder.name,
                    &format!("{count} slide{}", if count > 1 { "s" } else { "" }),
                    None,
                );
                if r.clicked() && !selected {
                    actions.push(PlaylistAction::SelectFolder(folder.id));
                }
                r.context_menu(|ui| {
                    if ui.button("Renommer…").clicked() {
                        self.dialog = Some(Dialog::Folder { id: Some(folder.id), name: folder.name.clone() });
                        ui.close();
                    }
                    if ui.button("Supprimer la playlist…").clicked() {
                        self.dialog = Some(Dialog::DeleteFolder { id: folder.id, name: folder.name.clone() });
                        ui.close();
                    }
                });
            }
        });
    }

    fn toolbar(&mut self, ui: &mut Ui, undo_available: bool, actions: &mut Vec<PlaylistAction>) {
        let has_folder = self.folder.is_some();
        let selection = self.selection();
        ui.horizontal(|ui| {
            if widgets::button_at(
                ui,
                Size::Normal,
                Some(icons::Icon::Plus),
                "Nouveau slide",
                Tone::Secondary,
                has_folder,
            )
            .clicked()
            {
                self.dialog = Some(Dialog::Item { id: None, reference: String::new(), text: String::new() });
            }
            let one = (selection.len() == 1).then(|| selection[0]);
            if widgets::button_at(ui, Size::Normal, None, "Modifier", Tone::Secondary, one.is_some()).clicked()
                && let Some(item) = one.and_then(|id| self.items.iter().find(|i| i.id == id))
            {
                self.dialog = Some(Dialog::Item {
                    id: Some(item.id),
                    reference: item.reference.clone(),
                    text: item.text.clone(),
                });
            }
            if widgets::button_at(
                ui,
                Size::Normal,
                Some(icons::Icon::X),
                "Supprimer",
                Tone::Danger,
                !selection.is_empty(),
            )
            .on_hover_text("Supprimer les slides choisis (Suppr) ; Ctrl+Z annule")
            .clicked()
            {
                actions.push(PlaylistAction::Delete(selection.clone()));
            }
            if widgets::button_at(
                ui,
                Size::Normal,
                Some(icons::Icon::ChevronUp),
                "",
                Tone::Secondary,
                !selection.is_empty(),
            )
            .on_hover_text("Monter les slides choisis (Ctrl+↑)")
            .clicked()
            {
                self.move_selected(-1, actions);
            }
            if widgets::button_at(
                ui,
                Size::Normal,
                Some(icons::Icon::ChevronDown),
                "",
                Tone::Secondary,
                !selection.is_empty(),
            )
            .on_hover_text("Descendre les slides choisis (Ctrl+↓)")
            .clicked()
            {
                self.move_selected(1, actions);
            }
            if widgets::button_at(
                ui,
                Size::Normal,
                Some(icons::Icon::Refresh),
                "Annuler",
                Tone::Secondary,
                undo_available,
            )
            .on_hover_text("Annuler la dernière modification des playlists (Ctrl+Z)")
            .clicked()
            {
                actions.push(PlaylistAction::Undo);
            }
            let images = self.items.iter().any(|i| {
                i.source == "media"
                    && (crate::playlist::is_image_file(&i.background) || crate::video::is_video_file(&i.background))
            });
            if widgets::button_at(ui, Size::Normal, None, "Diaporama", Tone::Secondary, images)
                .on_hover_text("Les images et vidéos de la playlist défilent au direct ; une flèche rend la main")
                .clicked()
            {
                actions.push(PlaylistAction::Slideshow);
            }
            if widgets::button_at(ui, Size::Normal, None, "Exporter", Tone::Secondary, has_folder)
                .on_hover_text("Dans « Documents\\Project-On playlists », avec ses images (format de la 2.8)")
                .clicked()
            {
                actions.push(PlaylistAction::Export);
            }
            let import = widgets::button(ui, None, "Importer…", Tone::Secondary).on_hover_text(
                "Une playlist exportée par la 2.8 ou la 3.0, déposée dans « Documents\\Project-On playlists »",
            );
            egui::Popup::menu(&import).show(|ui| {
                ui.set_min_width(320.0);
                let files = exchange_files();
                if files.is_empty() {
                    ui.label("Déposez les playlists exportées dans « Documents\\Project-On playlists ».");
                }
                for file in files.into_iter().take(30) {
                    let name = file.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
                    if ui.button(name).clicked() {
                        actions.push(PlaylistAction::Import(file));
                        ui.close();
                    }
                }
            });
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                let start = selection.first().copied().or_else(|| self.items.first().map(|i| i.id));
                if widgets::button_at(
                    ui,
                    Size::Normal,
                    Some(icons::Icon::Cast),
                    "Projeter",
                    Tone::Primary(LIVE),
                    start.is_some(),
                )
                .on_hover_text("Projeter la playlist à partir du slide choisi")
                .clicked()
                    && let Some(start) = start
                {
                    actions.push(PlaylistAction::Take(start));
                }
            });
        });
    }

    fn move_selected(&mut self, delta: i32, actions: &mut Vec<PlaylistAction>) {
        let order = self.order();
        let moved = move_selection(&order, &self.selected, delta);
        if moved != order {
            actions.push(PlaylistAction::Reorder(moved));
        }
    }

    fn items_column(
        &mut self,
        ui: &mut Ui,
        marks: PlaylistMarks,
        tracker: &Tracker,
        undo_available: bool,
        actions: &mut Vec<PlaylistAction>,
    ) {
        let Some(_) = self.folder else {
            super::empty(
                ui,
                "Créez une playlist, puis ajoutez-y des versets, des strophes ou des paragraphes (clic droit dans la bibliothèque).",
            );
            return;
        };
        ui.horizontal(|ui| {
            ui.label(RichText::new(self.folder_name()).font(semibold(16.0)).color(TEXT));
            ui.label(RichText::new(format!("{} slides", self.items.len())).font(regular(12.0)).color(MUTED));
            if let Some(message) = &self.message {
                ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                    ui.label(RichText::new(message).font(regular(11.5)).color(FAINT));
                });
            }
        });
        ui.add_space(6.0);
        self.toolbar(ui, undo_available, actions);
        ui.add_space(8.0);
        let plan_height = if self.show_plan { 250.0 } else { 34.0 };
        let list_height = (ui.available_height() - plan_height).max(120.0);
        let list_rect = ui.allocate_ui(vec2(ui.available_width(), list_height), |ui| {
            ScrollArea::vertical().id_salt(("slides", self.folder)).auto_shrink([false, false]).show(ui, |ui| {
                self.slide_list(ui, marks, actions);
            });
        });
        // Un clic dans la liste lui donne le clavier ; ailleurs, il le lui reprend.
        if ui.input(|i| i.pointer.any_pressed()) {
            self.list_focus =
                list_rect.response.rect.contains(ui.input(|i| i.pointer.interact_pos().unwrap_or_default()));
        }
        ui.add_space(6.0);
        self.plan_panel(ui, tracker, actions);
    }

    fn slide_list(&mut self, ui: &mut Ui, marks: PlaylistMarks, actions: &mut Vec<PlaylistAction>) {
        if self.items.is_empty() {
            super::empty(
                ui,
                "Playlist vide. Clic droit sur un verset, une strophe ou un paragraphe → « Ajouter à la playlist ».",
            );
            return;
        }
        ui.spacing_mut().item_spacing.y = 4.0;
        let order = self.order();
        let mut rows: Vec<(usize, Rect)> = Vec::new();
        let mut header: Option<(i64, bool)> = None;
        let pointer = ui.input(|i| i.pointer.interact_pos());
        for (index, item) in self.items.clone().iter().enumerate() {
            for section in self.sections.clone().iter().filter(|s| s.item_id == Some(item.id)) {
                let count = self.section_count(section.id);
                let collapsed = self.collapsed.contains(&section.id);
                self.section_header(ui, section, count, collapsed, actions);
                header = Some((section.id, collapsed));
            }
            if header.is_some_and(|(_, collapsed)| collapsed) {
                continue;
            }
            let rect = self.item_row(ui, item, marks, actions);
            rows.push((index, rect));
        }
        // Le glisser-déposer : une ligne montre où la sélection se posera.
        if let Some(dragged) = self.drag.clone() {
            if let Some(p) = pointer {
                self.drop_at = rows.iter().find(|(_, r)| p.y < r.center().y).map_or(order.len(), |(i, _)| *i);
            }
            let at = self.drop_at;
            let y = rows
                .iter()
                .find(|(i, _)| *i == at)
                .map_or_else(|| rows.last().map_or(0.0, |(_, r)| r.max.y + 2.0), |(_, r)| r.min.y - 2.0);
            let x = rows.first().map_or(0.0, |(_, r)| r.min.x);
            let w = rows.first().map_or(0.0, |(_, r)| r.width());
            ui.painter().line_segment([pos2(x, y), pos2(x + w, y)], Stroke::new(2.0, ACCENT));
            if ui.input(|i| i.pointer.any_released()) {
                let new = drop_selection(&order, &dragged, at);
                if new != order {
                    actions.push(PlaylistAction::Reorder(new));
                }
                self.drag = None;
            }
        }
    }

    fn section_count(&self, section: i64) -> usize {
        let starts: Vec<Option<usize>> =
            self.sections.iter().map(|s| s.item_id.and_then(|id| self.items.iter().position(|i| i.id == id))).collect();
        let Some(me) = self.sections.iter().position(|s| s.id == section) else { return 0 };
        let Some(start) = starts[me] else { return 0 };
        let end = starts.iter().flatten().copied().filter(|p| *p > start).min().unwrap_or(self.items.len());
        end - start
    }

    fn section_header(
        &mut self,
        ui: &mut Ui,
        section: &Section,
        count: usize,
        collapsed: bool,
        actions: &mut Vec<PlaylistAction>,
    ) {
        let (rect, r) = ui.allocate_exact_size(vec2(ui.available_width(), HEADER), Sense::click());
        let label = format!(
            "{} · {} min · {count} slide{}",
            section.name,
            section.duration_min,
            if count > 1 { "s" } else { "" }
        );
        r.widget_info(|| egui::WidgetInfo::labeled(egui::Role::Button, true, &label));
        ui.painter().rect_filled(rect, CornerRadius::same(6), WELL);
        let chevron = if collapsed { icons::Icon::ChevronRight } else { icons::Icon::ChevronDown };
        icons::paint(
            ui.painter(),
            Rect::from_center_size(pos2(rect.min.x + 14.0, rect.center().y), vec2(14.0, 14.0)),
            chevron,
            MUTED,
        );
        widgets::paint_text(
            ui,
            pos2(rect.min.x + 28.0, rect.center().y),
            Align2::LEFT_CENTER,
            &section.name.to_uppercase(),
            semibold(11.5),
            ACCENT,
            rect.width() - 160.0,
        );
        let info = format!("{} min · {count} slide{}", section.duration_min, if count > 1 { "s" } else { "" });
        widgets::paint_text(
            ui,
            pos2(rect.max.x - 10.0, rect.center().y),
            Align2::RIGHT_CENTER,
            &info,
            regular(11.5),
            MUTED,
            150.0,
        );
        if r.clicked() {
            if collapsed {
                self.collapsed.remove(&section.id);
            } else {
                self.collapsed.insert(section.id);
            }
        }
        r.context_menu(|ui| {
            if ui.button("Ne plus commencer la section ici").clicked() {
                actions.push(PlaylistAction::DetachSection(section.id));
                ui.close();
            }
        });
    }

    fn item_row(
        &mut self,
        ui: &mut Ui,
        item: &PlaylistItem,
        marks: PlaylistMarks,
        actions: &mut Vec<PlaylistAction>,
    ) -> Rect {
        let kind = item_kind(&item.source, &item.reference, &item.background);
        let (rect, r) = ui.allocate_exact_size(vec2(ui.available_width(), ROW), Sense::click_and_drag());
        r.widget_info(|| {
            egui::WidgetInfo::selected(
                egui::Role::ListBoxOption,
                true,
                self.selected.contains(&item.id),
                format!("{} {}", item.reference, item.text),
            )
        });
        let selected = self.selected.contains(&item.id);
        let (preview, live) = (marks.preview == Some(item.id), marks.live == Some(item.id));
        let mark = if live {
            widgets::Mark::Live
        } else if preview {
            widgets::Mark::Preview
        } else if selected {
            widgets::Mark::Selected
        } else {
            widgets::Mark::None
        };
        widgets::paint_tile(ui, rect, &r, mark);
        let painter = ui.painter();
        icons::paint(
            painter,
            Rect::from_center_size(pos2(rect.min.x + 20.0, rect.min.y + 18.0), vec2(16.0, 16.0)),
            kind.icon(),
            MUTED,
        );
        // Un PowerPoint dit où en est son rendu (« 12 slides », « préparation… »).
        let label = if kind == crate::playlist::Kind::PowerPoint {
            self.office_labels.get(item.background.trim()).cloned().unwrap_or_else(|| kind.label().to_string())
        } else {
            kind.label().to_string()
        };
        widgets::paint_text(
            ui,
            pos2(rect.min.x + 20.0, rect.min.y + 38.0),
            Align2::CENTER_CENTER,
            &label,
            medium(8.5),
            FAINT,
            40.0,
        );
        let x = rect.min.x + 44.0;
        let w = rect.width() - 54.0;
        widgets::paint_text(
            ui,
            pos2(x, rect.min.y + 6.0),
            Align2::LEFT_TOP,
            &item.reference,
            semibold(12.5),
            if live { LIVE } else { ACCENT },
            w,
        );
        widgets::paint_wrapped(
            ui,
            pos2(x, rect.min.y + 23.0),
            &item.text.replace('\n', " "),
            regular(11.5),
            TEXT.gamma_multiply(0.85),
            w,
            2,
        );

        if r.drag_started() {
            if !selected {
                self.selected = vec![item.id];
                self.anchor = Some(item.id);
            }
            self.drag = Some(self.selection());
        }
        if r.double_clicked() {
            self.selected = vec![item.id];
            actions.push(PlaylistAction::Take(item.id));
        } else if r.clicked() {
            let modifiers = ui.input(|i| i.modifiers);
            self.click(item.id, modifiers);
            if !modifiers.command && !modifiers.shift {
                actions.push(PlaylistAction::Cue(item.id));
            }
        }
        r.context_menu(|ui| {
            if !self.selected.contains(&item.id) {
                self.selected = vec![item.id];
            }
            let selection = self.selection();
            let n = selection.len();
            ui.set_min_width(240.0);
            if ui.button("Projeter à partir d'ici").clicked() {
                actions.push(PlaylistAction::Take(item.id));
                ui.close();
            }
            if ui.button("Préparer dans l'Aperçu").clicked() {
                actions.push(PlaylistAction::Cue(item.id));
                ui.close();
            }
            ui.separator();
            if n == 1 && ui.button("Modifier…").clicked() {
                self.dialog = Some(Dialog::Item {
                    id: Some(item.id),
                    reference: item.reference.clone(),
                    text: item.text.clone(),
                });
                ui.close();
            }
            if ui.button(format!("Dupliquer ({n})  Ctrl+D")).clicked() {
                actions.push(PlaylistAction::Duplicate(selection.clone()));
                ui.close();
            }
            let others = self.other_folders();
            ui.add_enabled_ui(!others.is_empty(), |ui| {
                ui.menu_button(format!("Copier vers ({n})"), |ui| {
                    for (id, name) in &others {
                        if ui.button(name).clicked() {
                            actions.push(PlaylistAction::CopyTo(selection.clone(), *id));
                            ui.close();
                        }
                    }
                });
                ui.menu_button(format!("Déplacer vers ({n})"), |ui| {
                    for (id, name) in &others {
                        if ui.button(name).clicked() {
                            actions.push(PlaylistAction::MoveTo(selection.clone(), *id));
                            ui.close();
                        }
                    }
                });
            });
            ui.menu_button("Commencer une section ici", |ui| {
                if ui.button("Nouvelle section…").clicked() {
                    self.dialog = Some(Dialog::Section {
                        id: None,
                        name: String::new(),
                        duration: 10,
                        link: Some(item.id),
                        linked: true,
                    });
                    ui.close();
                }
                for s in self.sections.clone() {
                    if ui.button(&s.name).clicked() {
                        actions.push(PlaylistAction::StartSectionAt {
                            section: Some(s.id),
                            item: item.id,
                            name: s.name.clone(),
                            duration: s.duration_min,
                        });
                        ui.close();
                    }
                }
            });
            ui.separator();
            if ui.button(format!("Supprimer ({n})  Suppr")).clicked() {
                actions.push(PlaylistAction::Delete(selection.clone()));
                ui.close();
            }
        });
        rect
    }

    fn keyboard(&mut self, ui: &mut Ui, actions: &mut Vec<PlaylistAction>) {
        if self.dialog.is_some() || ui.ctx().egui_wants_keyboard_input() {
            return;
        }
        let consume = |m: Modifiers, k: Key| ui.ctx().input_mut(|i| i.consume_key(m, k));
        // Ctrl+Z vaut sur toute la page Playlist.
        if consume(Modifiers::COMMAND, Key::Z) {
            actions.push(PlaylistAction::Undo);
        }
        if !self.list_focus || self.items.is_empty() {
            return;
        }
        let selection = self.selection();
        if consume(Modifiers::NONE, Key::Delete) && !selection.is_empty() {
            actions.push(PlaylistAction::Delete(selection.clone()));
        }
        if consume(Modifiers::COMMAND, Key::D) && !selection.is_empty() {
            actions.push(PlaylistAction::Duplicate(selection.clone()));
        }
        if consume(Modifiers::COMMAND, Key::A) {
            self.selected = self.order();
        }
        if consume(Modifiers::COMMAND, Key::ArrowUp) {
            self.move_selected(-1, actions);
        }
        if consume(Modifiers::COMMAND, Key::ArrowDown) {
            self.move_selected(1, actions);
        }
    }

    fn plan_panel(&mut self, ui: &mut Ui, tracker: &Tracker, actions: &mut Vec<PlaylistAction>) {
        ui.horizontal(|ui| {
            let chevron = if self.show_plan { icons::Icon::ChevronDown } else { icons::Icon::ChevronRight };
            if widgets::button(ui, Some(chevron), "Déroulé du culte", Tone::Secondary).clicked() {
                self.show_plan = !self.show_plan;
            }
            let now = service::now_seconds();
            let base = service::parse_start_time(&self.start_time).map(|(h, m)| f64::from(h * 3600 + m * 60));
            if let Some(s) = tracker.status(now, base) {
                let color = if s.delay > 60.0 { WARN } else { PREVIEW };
                widgets::dot(ui, color);
                let remaining = if s.remaining >= 0.0 {
                    format!("{} restantes", format_duration(s.remaining))
                } else {
                    format!("{} de dépassement", format_duration(-s.remaining))
                };
                ui.label(
                    RichText::new(format!(
                        "{} · {remaining} · {} · fin estimée {}",
                        s.name,
                        describe_delay(s.delay),
                        clock(s.expected_end)
                    ))
                    .font(medium(12.0))
                    .color(TEXT),
                );
                ui.ctx().request_repaint_after(std::time::Duration::from_secs(1));
            } else {
                let total = self.sections.iter().map(|s| s.duration_min).sum::<i64>();
                ui.label(
                    RichText::new(format!("{} sections · {total} min", self.sections.len()))
                        .font(regular(12.0))
                        .color(MUTED),
                );
            }
        });
        if !self.show_plan {
            return;
        }
        ui.add_space(6.0);
        ui.horizontal(|ui| {
            ui.label(RichText::new("Début prévu").font(regular(12.0)).color(MUTED));
            let r = ui.add(egui::TextEdit::singleline(&mut self.start_time).desired_width(60.0).hint_text("9:30"));
            ui.ctx().accesskit_node_builder(r.id, |n| n.set_label("Début prévu"));
            if r.lost_focus() {
                actions.push(PlaylistAction::SetStartTime(self.start_time.trim().to_string()));
            }
            if tracker.running() {
                if widgets::button(ui, Some(icons::Icon::CircleStop), "Arrêter", Tone::Secondary).clicked() {
                    actions.push(PlaylistAction::StopService);
                }
                if widgets::button(ui, Some(icons::Icon::ChevronRight), "Section suivante", Tone::Secondary).clicked() {
                    actions.push(PlaylistAction::NextSection);
                }
            } else if widgets::button_at(
                ui,
                Size::Normal,
                Some(icons::Icon::Play),
                "Démarrer",
                Tone::Primary(PREVIEW),
                !self.sections.is_empty(),
            )
            .clicked()
            {
                actions.push(PlaylistAction::StartService);
            }
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                let chosen = self.selected_section;
                if widgets::button_at(
                    ui,
                    Size::Small,
                    Some(icons::Icon::ChevronDown),
                    "",
                    Tone::Secondary,
                    chosen.is_some(),
                )
                .clicked()
                    && let Some(id) = chosen
                {
                    actions.push(PlaylistAction::MoveSection(id, 1));
                }
                if widgets::button_at(
                    ui,
                    Size::Small,
                    Some(icons::Icon::ChevronUp),
                    "",
                    Tone::Secondary,
                    chosen.is_some(),
                )
                .clicked()
                    && let Some(id) = chosen
                {
                    actions.push(PlaylistAction::MoveSection(id, -1));
                }
                if widgets::button_at(ui, Size::Small, None, "Supprimer", Tone::Danger, chosen.is_some()).clicked()
                    && let Some(id) = chosen
                {
                    actions.push(PlaylistAction::DeleteSection(id));
                    self.selected_section = None;
                }
                if widgets::button_at(ui, Size::Small, None, "Modifier", Tone::Secondary, chosen.is_some()).clicked()
                    && let Some(s) = self.sections.iter().find(|s| Some(s.id) == chosen)
                {
                    self.dialog = Some(Dialog::Section {
                        id: Some(s.id),
                        name: s.name.clone(),
                        duration: s.duration_min,
                        link: s.item_id,
                        linked: s.item_id.is_some(),
                    });
                }
                if widgets::button_at(ui, Size::Small, Some(icons::Icon::Plus), "Section", Tone::Secondary, true)
                    .clicked()
                {
                    let link = self.selection().first().copied();
                    self.dialog =
                        Some(Dialog::Section { id: None, name: String::new(), duration: 10, link, linked: false });
                }
            });
        });
        ui.add_space(4.0);
        let base = service::parse_start_time(&self.start_time)
            .map(|(h, m)| f64::from(h * 3600 + m * 60))
            .or(tracker.started_at);
        ScrollArea::vertical().id_salt("sections").auto_shrink([false, false]).show(ui, |ui| {
            egui::Grid::new("deroule").num_columns(5).striped(true).spacing([16.0, 4.0]).show(ui, |ui| {
                for h in ["Section", "Durée", "Prévue", "Réelle", "Commence au slide"] {
                    ui.label(RichText::new(h).font(semibold(11.0)).color(FAINT));
                }
                ui.end_row();
                for (i, s) in self.sections.clone().iter().enumerate() {
                    let current = tracker.current == Some(i) && tracker.running();
                    let name = RichText::new(&s.name).font(medium(12.5)).color(if current { PREVIEW } else { TEXT });
                    if ui.selectable_label(self.selected_section == Some(s.id), name).clicked() {
                        self.selected_section = Some(s.id);
                    }
                    ui.label(RichText::new(format!("{} min", s.duration_min)).font(regular(12.0)).color(MUTED));
                    let planned = base
                        .map(|b| clock(b + tracker.planned_offset_min(i) as f64 * 60.0))
                        .unwrap_or_else(|| "—".into());
                    ui.label(RichText::new(planned).font(regular(12.0)).color(MUTED));
                    let actual = tracker.actual_starts.get(&i).map(|t| clock(*t)).unwrap_or_else(|| "—".into());
                    ui.label(RichText::new(actual).font(regular(12.0)).color(MUTED));
                    let linked = s
                        .item_id
                        .and_then(|id| self.items.iter().find(|it| it.id == id))
                        .map(|it| it.reference.clone())
                        .unwrap_or_else(|| "—".into());
                    ui.label(RichText::new(linked).font(regular(12.0)).color(MUTED));
                    ui.end_row();
                }
            });
        });
    }

    fn dialogs(&mut self, ui: &mut Ui, actions: &mut Vec<PlaylistAction>) {
        let Some(mut dialog) = self.dialog.take() else { return };
        let mut keep = true;
        let title = match &dialog {
            Dialog::Folder { id: None, .. } => "Nouvelle playlist",
            Dialog::Folder { .. } => "Renommer la playlist",
            Dialog::Item { id: None, .. } => "Nouveau slide",
            Dialog::Item { .. } => "Modifier le slide",
            Dialog::DeleteFolder { .. } => "Supprimer la playlist",
            Dialog::Section { id: None, .. } => "Nouvelle section",
            Dialog::Section { .. } => "Modifier la section",
        };
        let enter = ui.input(|i| i.key_pressed(Key::Enter) && !i.modifiers.shift);
        let escape = ui.input(|i| i.key_pressed(Key::Escape));
        egui::Window::new(title).collapsible(false).resizable(false).anchor(Align2::CENTER_CENTER, [0.0, 0.0]).show(
            ui.ctx(),
            |ui| {
                ui.set_min_width(380.0);
                let mut ok = false;
                match &mut dialog {
                    Dialog::Folder { name, .. } => {
                        let r = ui
                            .add(egui::TextEdit::singleline(name).hint_text("Culte du dimanche").desired_width(360.0));
                        ui.ctx().accesskit_node_builder(r.id, |n| n.set_label("Nom de la playlist"));
                        r.request_focus();
                        ok = enter && !name.trim().is_empty();
                    }
                    Dialog::Item { reference, text, .. } => {
                        ui.label(RichText::new("Référence").font(regular(12.0)).color(MUTED));
                        let r = ui.add(egui::TextEdit::singleline(reference).desired_width(360.0));
                        ui.ctx().accesskit_node_builder(r.id, |n| n.set_label("Référence du slide"));
                        ui.label(RichText::new("Texte").font(regular(12.0)).color(MUTED));
                        let r = ui.add(egui::TextEdit::multiline(text).desired_width(360.0).desired_rows(6));
                        ui.ctx().accesskit_node_builder(r.id, |n| n.set_label("Texte du slide"));
                    }
                    Dialog::DeleteFolder { name, .. } => {
                        ui.label(format!(
                            "Supprimer « {name} » et tous ses slides ? Cette suppression ne s'annule pas."
                        ));
                    }
                    Dialog::Section { name, duration, link, linked, .. } => {
                        let r = ui.add(
                            egui::TextEdit::singleline(name)
                                .hint_text(SECTION_SUGGESTIONS[..4].join(" · ") + "…")
                                .desired_width(360.0),
                        );
                        ui.ctx().accesskit_node_builder(r.id, |n| n.set_label("Nom de la section"));
                        ui.horizontal_wrapped(|ui| {
                            for s in SECTION_SUGGESTIONS {
                                if ui.small_button(s).clicked() {
                                    *name = s.to_string();
                                }
                            }
                        });
                        ui.horizontal(|ui| {
                            ui.label("Durée");
                            ui.add(egui::DragValue::new(duration).range(1..=240).suffix(" min"));
                        });
                        if link.is_some() {
                            ui.checkbox(linked, "Commence au slide choisi");
                        }
                    }
                }
                ui.add_space(8.0);
                ui.horizontal(|ui| {
                    let label = if matches!(dialog, Dialog::DeleteFolder { .. }) { "Supprimer" } else { "Valider" };
                    if widgets::button(ui, None, label, Tone::Primary(ACCENT)).clicked() {
                        ok = true;
                    }
                    if widgets::button(ui, None, "Annuler", Tone::Secondary).clicked() || escape {
                        keep = false;
                    }
                });
                if ok {
                    keep = false;
                    match &dialog {
                        Dialog::Folder { id: None, name } => {
                            actions.push(PlaylistAction::CreateFolder(name.trim().to_string()))
                        }
                        Dialog::Folder { id: Some(id), name } => {
                            actions.push(PlaylistAction::RenameFolder(*id, name.trim().to_string()))
                        }
                        Dialog::Item { id: None, reference, text } => {
                            actions.push(PlaylistAction::CreateItem(reference.clone(), text.clone()))
                        }
                        Dialog::Item { id: Some(id), reference, text } => {
                            actions.push(PlaylistAction::UpdateItem(*id, reference.clone(), text.clone()));
                        }
                        Dialog::DeleteFolder { id, .. } => actions.push(PlaylistAction::DeleteFolder(*id)),
                        Dialog::Section { id, name, duration, link, linked } => {
                            let name = name.trim().to_string();
                            if name.is_empty() {
                                keep = true;
                            } else {
                                let item = if *linked { *link } else { None };
                                match (id, item) {
                                    (None, Some(item)) => actions.push(PlaylistAction::StartSectionAt {
                                        section: None,
                                        item,
                                        name,
                                        duration: *duration,
                                    }),
                                    (None, None) => actions.push(PlaylistAction::AddSection {
                                        name,
                                        duration: *duration,
                                        item: None,
                                    }),
                                    (Some(id), item) => actions.push(PlaylistAction::UpdateSection {
                                        id: *id,
                                        name,
                                        duration: *duration,
                                        item,
                                    }),
                                }
                            }
                        }
                    }
                }
            },
        );
        if keep {
            self.dialog = Some(dialog);
        }
    }
}
