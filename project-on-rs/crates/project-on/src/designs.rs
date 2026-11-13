//! La page « Designs » : l'habillage en direct (lower third, sous-titres, sorties NDI et HDMI) et la
//! bibliothèque de designs (grille d'aperçus réels par catégorie, « Mes designs » qu'on duplique,
//! personnalise, importe et exporte).
//!
//! Un clic sur un design de salle le pose dans l'**Aperçu** ; « Appliquer au direct » l'envoie au
//! direct. Le direct n'est jamais modifié par un simple clic.
//!
//! **Un seul design pour les sorties** : le design choisi par « Utiliser pour Web, NDI, HDMI » (un
//! bandeau, ou un design de slide dont le texte est posé sur un fond transparent) habille l'écran
//! Web « Diffusion », la source NDI et les sorties HDMI ; les écrans Web « Salle » le prennent
//! aussi quand c'est un design de slide. La projection de la salle garde son propre design. Ce
//! choix, le lower third et les sous-titres sont gardés d'un lancement à l'autre.

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::mpsc::{Receiver, Sender, channel};

use egui::{Color32, CornerRadius, RichText, Sense, Stroke, Ui, pos2, vec2};
use po_design::graphics::{Anchor, Entrance, Fill, LowerThirdText, Purpose, SubtitleLook};
use po_design::library::{CATEGORIES, Design, DesignBody, MyDesigns};
use po_design::{Align, AnimationKind, Band, Direction, Rgba, RoomDesign, SlideSource};
use po_layout::{DisplayList, Fonts, Slide};
use po_render::Renderer;

use crate::overlay::{LowerThird, Subtitles};
use crate::theme::*;
use crate::widgets::{self, Tone};

/// Ce que la page demande à la régie.
#[derive(Debug, Clone)]
pub enum DesignAction {
    /// Un design de salle dans l'Aperçu.
    Preview(RoomDesign),
    /// Le design de l'Aperçu au direct.
    ApplyLive,
    /// Le design des sorties Web, NDI et HDMI (un bandeau ou un design de slide).
    Output(Design),
    LowerThird(Design),
    Subtitles(Design),
    ToggleLowerThird,
    ToggleSubtitles,
    StepSubtitle(i32),
    Ndi(bool),
    Pattern,
    Status(String),
}

/// Le design des sorties Web, NDI et HDMI.
#[derive(Debug, Clone, PartialEq)]
pub struct Output {
    pub id: String,
    pub name: String,
    pub look: po_web::Look,
}

impl Output {
    /// Un bandeau ou un design de slide peut habiller les sorties ; pas un lower third.
    pub fn of(design: &Design) -> Option<Output> {
        let look = match &design.body {
            DesignBody::Room(room) => po_web::Look::Slide(room.clone()),
            DesignBody::Band(band) => po_web::Look::Band(band.clone()),
            DesignBody::LowerThird(_) | DesignBody::Subtitles(_) => return None,
        };
        Some(Output { id: design.id.clone(), name: design.name.clone(), look })
    }
}

/// Le design des sorties avec les réglages de l'habillage (Réglages → Habillage → Diffusion).
pub fn tuned_look(tuning: &po_design::tuning::Tuning, look: &po_web::Look) -> po_web::Look {
    match look {
        po_web::Look::Band(band) => po_web::Look::Band(tuning.apply_band(band)),
        po_web::Look::Slide(design) => po_web::Look::Slide(tuning.apply_room(design)),
    }
}

/// Les valeurs d'un design des sorties (pour partir de lui en personnalisant).
pub fn look_tuning(look: &po_web::Look) -> po_design::tuning::Tuning {
    match look {
        po_web::Look::Band(band) => po_design::tuning::Tuning::of_band(band),
        po_web::Look::Slide(design) => po_design::tuning::Tuning::of_room(design),
    }
}

/// Les designs choisis, gardés d'un lancement à l'autre : sorties, lower third, sous-titres.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Choices {
    pub output: Option<String>,
    pub lower_third: Option<String>,
    pub subtitles: Option<String>,
}

impl Choices {
    pub fn load(file: &std::path::Path) -> Choices {
        let value: serde_json::Value = std::fs::read_to_string(file)
            .ok()
            .and_then(|t| serde_json::from_str(&t).ok())
            .unwrap_or(serde_json::Value::Null);
        let id = |key: &str| value.get(key).and_then(serde_json::Value::as_str).map(str::to_string);
        Choices { output: id("sorties"), lower_third: id("lower_third"), subtitles: id("sous_titres") }
    }

    pub fn save(&self, file: &std::path::Path) -> std::io::Result<()> {
        let body = serde_json::json!({
            "sorties": self.output,
            "lower_third": self.lower_third,
            "sous_titres": self.subtitles,
        });
        let tmp = file.with_extension("json.tmp");
        std::fs::write(&tmp, body.to_string())?;
        std::fs::rename(&tmp, file)
    }
}

/// La taille des aperçus.
pub const PREVIEW_SIZE: [u32; 2] = [384, 216];

/// Une demande d'aperçu : identifiant, empreinte, design.
pub(crate) type PreviewJob = (String, String, DesignBody);

/// Les aperçus, rendus dans un fil à part avec le contenu en cours (la page Designs, et l'aperçu
/// de la projection dans les Réglages).
pub(crate) struct Previews {
    pub(crate) jobs: Sender<(Vec<PreviewJob>, Slide)>,
    pub(crate) done: Receiver<(String, String, Vec<u8>)>,
}

impl Previews {
    pub(crate) fn start(fonts_dir: PathBuf, wake: impl Fn() + Send + 'static) -> Option<Previews> {
        let (jobs, incoming) = channel::<(Vec<PreviewJob>, Slide)>();
        let (out, done) = channel();
        std::thread::Builder::new()
            .name("po-apercus".into())
            .spawn(move || {
                let mut fonts = crate::worker::fonts_from(&fonts_dir);
                let mut renderer = Renderer::new();
                while let Ok((mut batch, mut slide)) = incoming.recv() {
                    // Seule la dernière demande compte.
                    while let Ok((b, s)) = incoming.try_recv() {
                        (batch, slide) = (b, s);
                    }
                    for (id, key, body) in batch {
                        let pixels = render_preview(&mut fonts, &mut renderer, &body, &slide);
                        if out.send((id, key, pixels)).is_err() {
                            return;
                        }
                        wake();
                    }
                }
            })
            .ok()?;
        Some(Previews { jobs, done })
    }
}

/// Un damier sombre : là où passe la vidéo.
fn checker(list: &mut DisplayList) {
    let cell = 12.0;
    let (w, h) = (list.width, list.height);
    list.background = Rgba::rgb(40, 44, 50);
    let mut items = Vec::new();
    let mut y = 0.0;
    let mut row = 0;
    while y < h {
        let mut x = if row % 2 == 0 { 0.0 } else { cell };
        while x < w {
            items.push(po_layout::Item::Rect { x, y, w: cell, h: cell, radius: 0.0, color: Rgba::rgb(52, 56, 62) });
            x += 2.0 * cell;
        }
        y += cell;
        row += 1;
    }
    list.backdrop = items;
}

fn sample_text(purpose: Purpose) -> LowerThirdText {
    match purpose {
        Purpose::Speaker => LowerThirdText::new("Frère Jean Mukendi", "Pasteur"),
        Purpose::Sermon => LowerThirdText::new("La Foi est une ferme assurance", "47-0412 · Oakland"),
        Purpose::Bible => LowerThirdText::new("Jean 3:16", "Louis Segond 1910"),
        Purpose::Generic => LowerThirdText::new("Bienvenue", "Culte du dimanche"),
    }
}

/// L'aperçu d'un design (384 × 216, RVBA prémultiplié) avec le contenu `slide`.
pub fn render_preview(fonts: &mut Fonts, renderer: &mut Renderer, body: &DesignBody, slide: &Slide) -> Vec<u8> {
    let (w, h) = (1920.0, 1080.0);
    let list = match body {
        DesignBody::Room(design) => {
            let mut probe = |list: &DisplayList, zone: [f32; 4]| renderer.backdrop_luminance(list, zone);
            po_layout::layout_room(fonts, slide, design, w, h, &mut probe)
        }
        DesignBody::Band(band) => {
            let mut list = po_layout::layout_band(fonts, slide, band, w, h);
            checker(&mut list);
            list
        }
        DesignBody::LowerThird(style) => {
            let graphic = po_layout::graphics::layout_lower_third(fonts, &sample_text(style.purpose), style, w, h);
            let mut list = DisplayList::blank(w, h, Rgba::TRANSPARENT);
            list.items = graphic.items();
            checker(&mut list);
            list
        }
        DesignBody::Subtitles(style) => {
            let text =
                po_layout::graphics::subtitle_chunks(fonts, &slide.text, style).into_iter().next().unwrap_or_default();
            let graphic =
                po_layout::graphics::layout_subtitle_with_reference(fonts, &text, &slide.reference, style, w, h);
            let mut list = DisplayList::blank(w, h, Rgba::TRANSPARENT);
            list.items = graphic.items();
            checker(&mut list);
            list
        }
    };
    renderer.render(fonts, &list, PREVIEW_SIZE[0], PREVIEW_SIZE[1]).map(|p| p.data().to_vec()).unwrap_or_default()
}

fn fingerprint(body: &DesignBody) -> String {
    serde_json::to_string(body).unwrap_or_default()
}

/// L'état de la page.
pub struct DesignsView {
    fonts_dir: PathBuf,
    mine: Option<MyDesigns>,
    builtin: Vec<Design>,
    my_list: Vec<Design>,
    /// « Tout », une catégorie, ou « Mes designs ».
    pub filter: String,
    pub selected: Option<String>,
    /// Le design de « Mes designs » en cours de personnalisation.
    editing: Option<Design>,
    new_name: String,
    previews: Option<Previews>,
    textures: HashMap<String, (String, egui::TextureHandle)>,
    asked: HashMap<String, String>,
    sample: Option<(String, String)>,
    pub families: Vec<String>,
    /// Les aperçus rendus (non en mode PC modeste).
    pub previews_enabled: bool,
    /// Les habillages réglés dans Réglages → Habillage : sous-titres, diffusion, lower third.
    pub tuned: [bool; 3],
}

impl DesignsView {
    pub fn new(fonts_dir: PathBuf, designs_dir: Option<PathBuf>, room_2x: &RoomDesign, band_2x: &Band) -> Self {
        let mine = designs_dir.map(MyDesigns::new);
        let my_list = mine.as_ref().map(|m| m.load().0).unwrap_or_default();
        DesignsView {
            fonts_dir,
            mine,
            builtin: po_design::library::builtin(room_2x, band_2x),
            my_list,
            filter: "Tout".into(),
            selected: None,
            editing: None,
            new_name: String::new(),
            previews: None,
            textures: HashMap::new(),
            asked: HashMap::new(),
            sample: None,
            families: Vec::new(),
            previews_enabled: true,
            tuned: [false; 3],
        }
    }

    /// Le dossier des polices (les fonds fournis sont à côté).
    pub fn fonts_dir(&self) -> &std::path::Path {
        &self.fonts_dir
    }

    /// Les designs intégrés suivent les réglages de la 2.x (« Mon design 2.x »).
    pub fn refresh_builtin(&mut self, room_2x: &RoomDesign, band_2x: &Band) {
        self.builtin = po_design::library::builtin(room_2x, band_2x);
    }

    pub fn all(&self) -> impl Iterator<Item = &Design> {
        self.builtin.iter().chain(self.my_list.iter())
    }

    pub fn find(&self, id: &str) -> Option<&Design> {
        self.all().find(|d| d.id == id)
    }

    fn shown(&self) -> Vec<Design> {
        self.all()
            .filter(|d| match self.filter.as_str() {
                "Tout" => true,
                "Mes designs" => !d.builtin,
                category => d.category == category,
            })
            .cloned()
            .collect()
    }

    /// Demande les aperçus manquants (ou périmés) au fil de rendu.
    fn request_previews(&mut self, ctx: &egui::Context, designs: &[Design], slide: &Slide) {
        if !self.previews_enabled {
            return;
        }
        let sample_key = (slide.text.clone(), slide.reference.clone());
        if self.sample.as_ref() != Some(&sample_key) {
            // Le contenu a changé : tous les aperçus sont à refaire.
            self.sample = Some(sample_key);
            self.asked.clear();
        }
        if self.previews.is_none() {
            let wake = ctx.clone();
            self.previews = Previews::start(self.fonts_dir.clone(), move || wake.request_repaint());
        }
        let Some(previews) = &self.previews else { return };
        let mut batch = Vec::new();
        for d in designs {
            let key = fingerprint(&d.body);
            if self.asked.get(&d.id) != Some(&key) {
                self.asked.insert(d.id.clone(), key.clone());
                batch.push((d.id.clone(), key, d.body.clone()));
            }
        }
        if !batch.is_empty() {
            let _ = previews.jobs.send((batch, slide.clone()));
        }
        while let Ok((id, key, pixels)) = previews.done.try_recv() {
            if pixels.len() != (PREVIEW_SIZE[0] * PREVIEW_SIZE[1] * 4) as usize {
                continue;
            }
            let image = egui::ColorImage::from_rgba_premultiplied(
                [PREVIEW_SIZE[0] as usize, PREVIEW_SIZE[1] as usize],
                &pixels,
            );
            let texture = ctx.load_texture(format!("design-{id}"), image, egui::TextureOptions::LINEAR);
            self.textures.insert(id, (key, texture));
        }
    }

    /// La page entière.
    #[allow(clippy::too_many_arguments)]
    pub fn ui(
        &mut self,
        ui: &mut Ui,
        lower_third: &mut LowerThird,
        subtitles: &mut Subtitles,
        ndi: (bool, Option<Result<String, String>>, i32),
        hdmi_count: usize,
        sample: &Slide,
        output: &Output,
    ) -> Vec<DesignAction> {
        let mut actions = Vec::new();
        egui::ScrollArea::vertical().auto_shrink([false, false]).show(ui, |ui| {
            ui.add_space(12.0);
            ui.label(RichText::new("Designs").font(bold(20.0)).color(TEXT));
            ui.add_space(4.0);
            live_card(ui, lower_third, subtitles, ndi, hdmi_count, output, self.tuned, &mut actions);
            ui.add_space(10.0);
            self.filters(ui);
            let designs = self.shown();
            self.request_previews(ui.ctx(), &designs, sample);
            // Le design choisi et ses actions, au-dessus de la grille (toujours à portée de main).
            if let Some(id) = self.selected.clone()
                && let Some(design) = self.find(&id).cloned()
            {
                self.details(ui, &design, output, &mut actions);
                ui.add_space(10.0);
            }
            self.grid(ui, &designs, lower_third, subtitles, output, &mut actions);
        });
        actions
    }

    fn filters(&mut self, ui: &mut Ui) {
        ui.horizontal_wrapped(|ui| {
            for name in ["Tout"].into_iter().chain(CATEGORIES).chain(["Mes designs"]) {
                let on = self.filter == name;
                let tone = if on { Tone::Primary(ACCENT) } else { Tone::Secondary };
                if widgets::button_at(ui, widgets::Size::Small, None, name, tone, true).clicked() {
                    self.filter = name.to_string();
                }
            }
        });
        ui.add_space(8.0);
    }

    fn grid(
        &mut self,
        ui: &mut Ui,
        designs: &[Design],
        lower_third: &LowerThird,
        subtitles: &Subtitles,
        output: &Output,
        actions: &mut Vec<DesignAction>,
    ) {
        if designs.is_empty() {
            ui.label(
                RichText::new("Aucun design ici. Dupliquez un design pour le personnaliser.")
                    .font(regular(12.5))
                    .color(MUTED),
            );
            return;
        }
        let card_w = 232.0;
        let columns = ((ui.available_width() + 12.0) / (card_w + 12.0)).floor().max(1.0) as usize;
        for row in designs.chunks(columns) {
            ui.horizontal(|ui| {
                for d in row {
                    let selected = self.selected.as_deref() == Some(d.id.as_str());
                    let in_use = match &d.body {
                        DesignBody::LowerThird(_) => lower_third.id == d.id,
                        DesignBody::Subtitles(_) => subtitles.id == d.id,
                        DesignBody::Room(_) | DesignBody::Band(_) => output.id == d.id,
                    };
                    let r = self.card(ui, d, card_w, selected, in_use);
                    if r.clicked() {
                        self.selected = Some(d.id.clone());
                        self.editing = None;
                        if let DesignBody::Room(room) = &d.body {
                            actions.push(DesignAction::Preview(room.clone()));
                            actions.push(DesignAction::Status(format!("« {} » dans l'Aperçu", d.name)));
                        }
                    }
                    if r.double_clicked() {
                        match &d.body {
                            DesignBody::LowerThird(_) => actions.push(DesignAction::LowerThird(d.clone())),
                            DesignBody::Subtitles(_) => actions.push(DesignAction::Subtitles(d.clone())),
                            DesignBody::Band(_) => actions.push(DesignAction::Output(d.clone())),
                            DesignBody::Room(_) => {}
                        }
                    }
                    ui.add_space(12.0);
                }
            });
            ui.add_space(12.0);
        }
    }

    fn card(&self, ui: &mut Ui, d: &Design, width: f32, selected: bool, in_use: bool) -> egui::Response {
        let height = width * 9.0 / 16.0 + 44.0;
        let (rect, response) = ui.allocate_exact_size(vec2(width, height), Sense::click());
        let t = widgets::hover_t(ui, &response, response.hovered());
        let painter = ui.painter();
        let radius = CornerRadius::same(12);
        if selected {
            crate::theme::paint_glow(painter, rect, radius, ACCENT, 0.35);
        } else {
            crate::theme::paint_shadow(
                painter,
                rect,
                radius,
                4,
                14,
                Color32::from_black_alpha((70.0 + 50.0 * t) as u8),
            );
        }
        let stroke =
            if selected { Stroke::new(2.0, ACCENT) } else { Stroke::new(1.0, BORDER.lerp_to_gamma(BORDER_STRONG, t)) };
        painter.rect_filled(rect, radius, SURFACE.lerp_to_gamma(RAISED, 0.5 * t));
        crate::theme::paint_relief(painter, rect, radius, 0.8);
        painter.rect_stroke(rect, radius, stroke, egui::StrokeKind::Inside);
        let image = egui::Rect::from_min_size(rect.min + vec2(4.0, 4.0), vec2(width - 8.0, (width - 8.0) * 9.0 / 16.0));
        match self.textures.get(&d.id) {
            Some((_, texture)) => {
                painter.image(
                    texture.id(),
                    image,
                    egui::Rect::from_min_max(pos2(0.0, 0.0), pos2(1.0, 1.0)),
                    Color32::WHITE,
                );
            }
            None => {
                painter.rect_filled(image, CornerRadius::same(6), WELL);
            }
        }
        widgets::paint_text(
            ui,
            pos2(rect.min.x + 8.0, image.max.y + 12.0),
            egui::Align2::LEFT_CENTER,
            &d.name,
            semibold(12.5),
            TEXT,
            width - 16.0,
        );
        let mut tag = d.body.kind_label().to_string();
        if !d.builtin {
            tag.push_str(" · mon design");
        }
        if in_use {
            tag.push_str(" · utilisé");
        }
        widgets::paint_text(
            ui,
            pos2(rect.min.x + 8.0, image.max.y + 30.0),
            egui::Align2::LEFT_CENTER,
            &tag,
            regular(11.0),
            if in_use { PREVIEW } else { MUTED },
            width - 16.0,
        );
        let label = d.name.clone();
        ui.ctx().accesskit_node_builder(response.id, |n| {
            n.set_role(egui::accesskit::Role::Button);
            n.set_label(label);
        });
        response
    }

    fn details(&mut self, ui: &mut Ui, design: &Design, output: &Output, actions: &mut Vec<DesignAction>) {
        widgets::card(ui, |ui| {
            ui.set_width(ui.available_width());
            ui.horizontal(|ui| {
                ui.label(RichText::new(&design.name).font(semibold(15.0)).color(TEXT));
                ui.label(
                    RichText::new(format!("{} · {}", design.body.kind_label(), design.category))
                        .font(regular(12.0))
                        .color(MUTED),
                );
            });
            ui.add_space(6.0);
            ui.horizontal_wrapped(|ui| {
                match &design.body {
                    DesignBody::Room(_) => {
                        if widgets::button(ui, None, "Appliquer au direct", Tone::Primary(LIVE))
                            .on_hover_text("La projection de la salle prend ce design")
                            .clicked()
                        {
                            actions.push(DesignAction::ApplyLive);
                        }
                        output_button(ui, design, output, actions);
                    }
                    DesignBody::Band(_) => output_button(ui, design, output, actions),
                    DesignBody::LowerThird(_) => {
                        if widgets::button(ui, None, "Utiliser comme lower third", Tone::Primary(ACCENT)).clicked() {
                            actions.push(DesignAction::LowerThird(design.clone()));
                        }
                    }
                    DesignBody::Subtitles(_) => {
                        if widgets::button(ui, None, "Utiliser pour les sous-titres", Tone::Primary(ACCENT)).clicked() {
                            actions.push(DesignAction::Subtitles(design.clone()));
                        }
                    }
                }
                ui.add(
                    egui::TextEdit::singleline(&mut self.new_name).hint_text("Nom de la copie").desired_width(160.0),
                );
                if widgets::button(ui, None, "Dupliquer", Tone::Secondary).clicked() {
                    let name = if self.new_name.trim().is_empty() {
                        format!("{} (copie)", design.name)
                    } else {
                        self.new_name.trim().to_string()
                    };
                    match self.mine.as_ref().map(|m| m.duplicate(design, &name)) {
                        Some(Ok(copy)) => {
                            actions.push(DesignAction::Status(format!("« {} » ajouté à Mes designs", copy.name)));
                            self.selected = Some(copy.id.clone());
                            self.editing = Some(copy);
                            self.new_name.clear();
                            self.reload();
                        }
                        Some(Err(e)) => actions.push(DesignAction::Status(format!("Copie impossible : {e}"))),
                        None => actions.push(DesignAction::Status("Mes designs : dossier de données absent".into())),
                    }
                }
                if !design.builtin {
                    if widgets::button(ui, None, "Personnaliser", Tone::Secondary).clicked() {
                        self.editing = Some(design.clone());
                    }
                    if widgets::button(ui, None, "Exporter", Tone::Secondary).clicked() {
                        actions.push(DesignAction::Status(self.export(design)));
                    }
                    if widgets::button(ui, None, "Supprimer", Tone::Danger).clicked()
                        && let Some(mine) = &self.mine
                    {
                        let _ = mine.delete(&design.id);
                        self.selected = None;
                        self.editing = None;
                        self.reload();
                        actions.push(DesignAction::Status(format!("« {} » supprimé", design.name)));
                    }
                }
                if widgets::button(ui, None, "Importer…", Tone::Secondary)
                    .on_hover_text("Les designs du dossier « Project-On designs » de vos Documents")
                    .clicked()
                {
                    actions.push(DesignAction::Status(self.import_all()));
                }
            });
        });
        if let Some(mut editing) = self.editing.clone().filter(|e| e.id == design.id) {
            ui.add_space(8.0);
            let changed = widgets::card(ui, |ui| editor(ui, &mut editing, &self.families)).inner;
            if changed {
                if let Some(mine) = &self.mine
                    && let Ok(saved) = mine.save(&editing)
                {
                    editing = saved;
                    self.reload();
                }
                if let DesignBody::Room(room) = &editing.body {
                    actions.push(DesignAction::Preview(room.clone()));
                }
                self.editing = Some(editing);
            } else {
                self.editing = Some(editing);
            }
        }
    }

    fn reload(&mut self) {
        if let Some(mine) = &self.mine {
            self.my_list = mine.load().0;
        }
    }

    /// Le dossier d'échange : « Documents\Project-On designs ».
    fn exchange_dir() -> Option<PathBuf> {
        std::env::var_os("USERPROFILE").map(|home| PathBuf::from(home).join("Documents").join("Project-On designs"))
    }

    fn export(&self, design: &Design) -> String {
        let Some(dir) = Self::exchange_dir() else { return "Dossier Documents introuvable".into() };
        let file = dir.join(format!("{}.json", po_design::library::slug(&design.name)));
        match std::fs::create_dir_all(&dir)
            .map_err(po_design::library::LibraryError::Io)
            .and_then(|()| po_design::library::export(design, &file))
        {
            Ok(()) => format!("Exporté : {}", file.display()),
            Err(e) => format!("Export impossible : {e}"),
        }
    }

    fn import_all(&mut self) -> String {
        let (Some(dir), Some(mine)) = (Self::exchange_dir(), &self.mine) else { return "Import impossible".into() };
        let Ok(entries) = std::fs::read_dir(&dir) else {
            return format!("Déposez des designs exportés dans {}", dir.display());
        };
        let known: Vec<_> = self.my_list.iter().map(|d| (d.name.clone(), fingerprint(&d.body))).collect();
        let (mut added, mut refused) = (0, 0);
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) != Some("json") {
                continue;
            }
            // Un design déjà là (même nom, même réglage) n'est pas importé deux fois.
            let duplicate = std::fs::read_to_string(&path)
                .ok()
                .and_then(|t| serde_json::from_str::<Design>(&t).ok())
                .is_some_and(|d| known.contains(&(d.name.clone(), fingerprint(&d.body))));
            if duplicate {
                continue;
            }
            match mine.import(&path) {
                Ok(_) => added += 1,
                Err(_) => refused += 1,
            }
        }
        self.reload();
        match (added, refused) {
            (0, 0) => "Aucun nouveau design à importer".into(),
            (a, 0) => format!("{a} design(s) importé(s)"),
            (a, r) => format!("{a} design(s) importé(s), {r} fichier(s) refusé(s)"),
        }
    }
}

/// Le bouton qui fait d'un design celui des sorties Web, NDI et HDMI.
fn output_button(ui: &mut Ui, design: &Design, output: &Output, actions: &mut Vec<DesignAction>) {
    if output.id == design.id {
        ui.label(RichText::new("✔ Utilisé pour Web, NDI, HDMI").font(semibold(12.0)).color(PREVIEW));
        return;
    }
    let about = match design.body {
        DesignBody::Room(_) => {
            "Le texte de ce design, sur fond transparent, sur l'écran Web Diffusion, la source NDI et les sorties HDMI ; les écrans Web Salle le prennent en entier. La projection de la salle ne change pas."
        }
        _ => {
            "Ce bandeau sur l'écran Web Diffusion, la source NDI et les sorties HDMI. La projection de la salle ne change pas."
        }
    };
    if widgets::button(ui, None, "Utiliser pour Web, NDI, HDMI", Tone::Primary(ACCENT)).on_hover_text(about).clicked() {
        actions.push(DesignAction::Output(design.clone()));
    }
}

/// L'habillage en direct : lower third, sous-titres, sorties.
fn live_card(
    ui: &mut Ui,
    lower_third: &mut LowerThird,
    subtitles: &mut Subtitles,
    (ndi_on, ndi_status, receivers): (bool, Option<Result<String, String>>, i32),
    hdmi_count: usize,
    output: &Output,
    [tuned_subtitles, tuned_output, tuned_lower_third]: [bool; 3],
    actions: &mut Vec<DesignAction>,
) {
    let tuned_note = |ui: &mut Ui, tuned: bool| {
        if tuned {
            ui.label(RichText::new("· police et couleurs : Réglages → Habillage").font(regular(11.5)).color(FAINT));
        }
    };
    widgets::card(ui, |ui| {
        ui.set_width(ui.available_width());
        ui.label(RichText::new("HABILLAGE EN DIRECT").font(semibold(10.5)).color(FAINT));
        ui.add_space(4.0);
        ui.horizontal_wrapped(|ui| {
            ui.label(RichText::new("Web, NDI, HDMI :").font(medium(12.0)).color(MUTED));
            ui.label(RichText::new(format!("« {} »", output.name)).font(semibold(12.5)).color(TEXT));
            let what = match output.look {
                po_web::Look::Band(_) => "bandeau, fond transparent",
                po_web::Look::Slide(_) => "texte du design, fond transparent",
            };
            ui.label(
                RichText::new(format!("({what}) · la projection garde son design")).font(regular(11.5)).color(FAINT),
            );
            tuned_note(ui, tuned_output);
        });
        ui.add_space(6.0);
        ui.horizontal(|ui| {
            let label = if lower_third.shown { "Masquer le lower third  L" } else { "Afficher le lower third  L" };
            let tone = if lower_third.shown { Tone::Primary(LIVE) } else { Tone::Secondary };
            if widgets::button(ui, None, label, tone).clicked() {
                actions.push(DesignAction::ToggleLowerThird);
            }
            ui.label(RichText::new(&lower_third.name).font(medium(12.0)).color(MUTED));
            ui.checkbox(&mut lower_third.auto, "Suivre le direct");
            tuned_note(ui, tuned_lower_third);
        });
        if !lower_third.auto {
            let (first, second) = lower_third.style.purpose.fields();
            ui.horizontal(|ui| {
                ui.add(egui::TextEdit::singleline(&mut lower_third.text.title).hint_text(first).desired_width(240.0));
                ui.add(
                    egui::TextEdit::singleline(&mut lower_third.text.subtitle).hint_text(second).desired_width(240.0),
                );
            });
        }
        ui.add_space(6.0);
        ui.horizontal(|ui| {
            let label = if subtitles.shown { "Masquer les sous-titres  S" } else { "Afficher les sous-titres  S" };
            let tone = if subtitles.shown { Tone::Primary(LIVE) } else { Tone::Secondary };
            if widgets::button(ui, None, label, tone).clicked() {
                actions.push(DesignAction::ToggleSubtitles);
            }
            ui.label(RichText::new(&subtitles.name).font(medium(12.0)).color(MUTED));
            tuned_note(ui, tuned_subtitles);
            // Un texte long n'est plus coupé : les flèches ne servent que s'il y a plusieurs parties.
            if subtitles.shown && subtitles.chunks.len() > 1 {
                if widgets::button(ui, None, "◀", Tone::Secondary).clicked() {
                    actions.push(DesignAction::StepSubtitle(-1));
                }
                ui.label(
                    RichText::new(format!("{} / {}", subtitles.index + 1, subtitles.chunks.len()))
                        .font(semibold(12.0))
                        .color(TEXT),
                );
                if widgets::button(ui, None, "▶", Tone::Secondary).clicked() {
                    actions.push(DesignAction::StepSubtitle(1));
                }
                ui.label(RichText::new("← → avancent dans le paragraphe").font(regular(11.5)).color(FAINT));
            }
        });
        ui.add_space(6.0);
        ui.horizontal(|ui| {
            let mut on = ndi_on;
            if ui.checkbox(&mut on, "Source NDI « Project-On Diffusion »").changed() {
                actions.push(DesignAction::Ndi(on));
            }
            match (&ndi_status, ndi_on) {
                (Some(Ok(_)), true) => {
                    ui.label(RichText::new(format!("{receivers} récepteur(s)")).font(medium(11.5)).color(PREVIEW));
                }
                (Some(Err(e)), true) => {
                    ui.label(RichText::new(e).font(regular(11.5)).color(WARN));
                }
                _ => {}
            }
            ui.add_space(12.0);
            let hdmi = match hdmi_count {
                0 => "Sortie HDMI : clic droit sur « Projection », puis un écran et « Diffusion »".to_string(),
                n => format!("{n} sortie(s) HDMI"),
            };
            ui.label(RichText::new(hdmi).font(regular(11.5)).color(MUTED));
            if hdmi_count > 0 && widgets::button(ui, None, "Mire  F8", Tone::Secondary).clicked() {
                actions.push(DesignAction::Pattern);
            }
        });
    });
}

fn color_edit(ui: &mut Ui, label: &str, color: &mut Rgba) -> bool {
    let mut c = Color32::from_rgba_unmultiplied(color.0[0], color.0[1], color.0[2], color.0[3]);
    let mut changed = false;
    ui.horizontal(|ui| {
        ui.label(RichText::new(label).font(regular(12.0)).color(MUTED));
        if egui::color_picker::color_edit_button_srgba(ui, &mut c, egui::color_picker::Alpha::OnlyBlend).changed() {
            *color = Rgba(c.to_srgba_unmultiplied());
            changed = true;
        }
    });
    changed
}

fn family_edit(ui: &mut Ui, label: &str, family: &mut String, families: &[String]) -> bool {
    let mut changed = false;
    ui.horizontal(|ui| {
        ui.label(RichText::new(label).font(regular(12.0)).color(MUTED));
        egui::ComboBox::from_id_salt(("famille", label)).selected_text(family.as_str()).width(180.0).show_ui(
            ui,
            |ui| {
                for f in families {
                    if ui.selectable_label(family == f, f).clicked() {
                        *family = f.clone();
                        changed = true;
                    }
                }
            },
        );
    });
    changed
}

fn decimal_edit(ui: &mut Ui, label: &str, value: &mut f32, range: std::ops::RangeInclusive<f32>) -> bool {
    ui.horizontal(|ui| {
        ui.label(RichText::new(label).font(regular(12.0)).color(MUTED));
        ui.add(egui::Slider::new(value, range).fixed_decimals(2)).changed()
    })
    .inner
}

fn align_edit(ui: &mut Ui, label: &str, value: &mut Align) -> bool {
    ui.horizontal(|ui| {
        ui.label(RichText::new(label).font(regular(12.0)).color(MUTED));
        let mut changed = false;
        for (a, l) in [(Align::Left, "À gauche"), (Align::Center, "Centré"), (Align::Right, "À droite")] {
            changed |= ui.radio_value(value, a, l).changed();
        }
        changed
    })
    .inner
}

/// Les réglages détaillés d'un bandeau (ceux de la page « Navigateur OBS » de la 2.8).
fn band_details(ui: &mut Ui, b: &mut po_design::Band) -> bool {
    let mut changed = false;
    egui::CollapsingHeader::new(RichText::new("Réglages détaillés").font(medium(12.5)).color(TEXT))
        .id_salt("bandeau-details")
        .show(ui, |ui| {
            ui.label(RichText::new("TEXTE").font(semibold(10.5)).color(FAINT));
            ui.horizontal(|ui| {
                ui.label(RichText::new("Graisse").font(regular(12.0)).color(MUTED));
                for (w, l) in [(400, "Normale"), (500, "Moyenne"), (600, "Demi-gras"), (700, "Gras"), (800, "Extra")] {
                    changed |= ui.radio_value(&mut b.weight, w, l).changed();
                }
            });
            changed |= size_edit(ui, "Taille minimale (texte long)", &mut b.min_size, 12.0..=96.0);
            changed |= decimal_edit(ui, "Espacement des lettres", &mut b.letter_spacing, 0.0..=10.0);
            changed |= decimal_edit(ui, "Interligne", &mut b.line_height, 1.0..=2.0);
            let mut lines = b.max_lines as f32;
            if size_edit(ui, "Lignes au plus", &mut lines, 1.0..=8.0) {
                b.max_lines = lines as usize;
                changed = true;
            }
            changed |= align_edit(ui, "Texte", &mut b.align);
            let mut shadow = b.shadow.is_some();
            if ui.checkbox(&mut shadow, "Ombre du texte").changed() {
                b.shadow = shadow.then_some((Rgba::new(0, 0, 0, 160), 6.0));
                changed = true;
            }
            if let Some((color, blur)) = &mut b.shadow {
                changed |= color_edit(ui, "Couleur de l'ombre", color);
                changed |= size_edit(ui, "Flou de l'ombre", blur, 0.0..=30.0);
            }

            ui.add_space(4.0);
            ui.label(RichText::new("RÉFÉRENCE").font(semibold(10.5)).color(FAINT));
            ui.horizontal(|ui| {
                for (look, l) in [
                    (po_design::ReferenceLook::Badge, "Espacée, soulignée"),
                    (po_design::ReferenceLook::Line, "Simple"),
                    (po_design::ReferenceLook::Hidden, "Masquée"),
                ] {
                    changed |= ui.radio_value(&mut b.reference, look, l).changed();
                }
            });
            if b.reference != po_design::ReferenceLook::Hidden {
                changed |= size_edit(ui, "Taille de la référence", &mut b.ref_size, 12.0..=60.0);
                changed |= color_edit(ui, "Couleur de la référence", &mut b.ref_color);
                let mut accent = b.accent.is_some();
                if ui.checkbox(&mut accent, "Filet sous la référence").changed() {
                    b.accent = accent.then_some(b.ref_color);
                    changed = true;
                }
                if let Some(color) = &mut b.accent {
                    changed |= color_edit(ui, "Couleur du filet", color);
                }
            }

            ui.add_space(4.0);
            ui.label(RichText::new("BANDE").font(semibold(10.5)).color(FAINT));
            let mut band = b.background.is_some();
            if ui.checkbox(&mut band, "Bande derrière le texte").changed() {
                b.background = band.then_some(Rgba::new(10, 14, 22, 230));
                changed = true;
            }
            changed |= size_edit(ui, "Arrondi", &mut b.radius, 0.0..=60.0);
            changed |= size_edit(ui, "Marge intérieure (côtés)", &mut b.padding.0, 0.0..=120.0);
            changed |= size_edit(ui, "Marge intérieure (haut, bas)", &mut b.padding.1, 0.0..=120.0);
            changed |= size_edit(ui, "Largeur (% de l'écran)", &mut b.max_width, 20.0..=100.0);

            ui.add_space(4.0);
            ui.label(RichText::new("PLACE DANS L'IMAGE").font(semibold(10.5)).color(FAINT));
            if b.layout == po_design::BandLayout::Subtitle {
                ui.horizontal(|ui| {
                    ui.label(RichText::new("Position").font(regular(12.0)).color(MUTED));
                    for (p, l) in [
                        (po_design::BandPosition::Bottom, "En bas"),
                        (po_design::BandPosition::Center, "Au centre"),
                        (po_design::BandPosition::Top, "En haut"),
                    ] {
                        changed |= ui.radio_value(&mut b.position, p, l).changed();
                    }
                });
                changed |= align_edit(ui, "Bande", &mut b.band_align);
            }
            changed |= size_edit(ui, "Zone de sécurité (%)", &mut b.safe_area, 0.0..=15.0);
            changed |= size_edit(ui, "Décalage horizontal", &mut b.offset.0, -400.0..=400.0);
            changed |= size_edit(ui, "Décalage vertical", &mut b.offset.1, -400.0..=400.0);

            ui.add_space(4.0);
            ui.horizontal(|ui| {
                ui.label(RichText::new("Transition").font(regular(12.0)).color(MUTED));
                for (kind, label) in [
                    (AnimationKind::None, "Aucune"),
                    (AnimationKind::Fade, "Fondu"),
                    (AnimationKind::Slide, "Glissement"),
                    (AnimationKind::Scale, "Zoom"),
                    (AnimationKind::Blur, "Flou"),
                    (AnimationKind::Reveal, "Balayage"),
                ] {
                    changed |= ui.radio_value(&mut b.animation.kind, kind, label).changed();
                }
            });
            let mut ms = b.animation.duration_ms as f32;
            if size_edit(ui, "Durée de la transition (ms)", &mut ms, 0.0..=2000.0) {
                b.animation.duration_ms = ms as u32;
                changed = true;
            }
        });
    changed
}

fn size_edit(ui: &mut Ui, label: &str, value: &mut f32, range: std::ops::RangeInclusive<f32>) -> bool {
    ui.horizontal(|ui| {
        ui.label(RichText::new(label).font(regular(12.0)).color(MUTED));
        ui.add(egui::Slider::new(value, range).integer()).changed()
    })
    .inner
}

/// L'éditeur d'un design de « Mes designs ». Rend `true` si quelque chose a changé.
fn editor(ui: &mut Ui, design: &mut Design, families: &[String]) -> bool {
    let mut changed = false;
    ui.label(RichText::new("PERSONNALISER").font(semibold(10.5)).color(FAINT));
    ui.horizontal(|ui| {
        ui.label(RichText::new("Nom").font(regular(12.0)).color(MUTED));
        changed |= ui.add(egui::TextEdit::singleline(&mut design.name).desired_width(220.0)).lost_focus();
        egui::ComboBox::from_id_salt("categorie").selected_text(design.category.as_str()).show_ui(ui, |ui| {
            for c in CATEGORIES {
                if ui.selectable_label(design.category == c, c).clicked() {
                    design.category = c.to_string();
                    changed = true;
                }
            }
        });
    });
    match &mut design.body {
        DesignBody::Room(d) => {
            changed |= family_edit(ui, "Police", &mut d.text.family, families);
            changed |= size_edit(ui, "Taille", &mut d.text.size, 20.0..=160.0);
            changed |= ui.checkbox(&mut d.text.uppercase, "Capitales").changed();
            changed |= color_edit(ui, "Texte", &mut d.text.color);
            changed |= color_edit(ui, "Fond", &mut d.background.color);
            let mut gradient = d.background.gradient.is_some();
            if ui.checkbox(&mut gradient, "Dégradé").changed() {
                d.background.gradient = gradient.then_some((d.background.color, 135.0));
                changed = true;
            }
            if let Some((color, _)) = &mut d.background.gradient {
                changed |= color_edit(ui, "Seconde couleur", color);
            }
            ui.horizontal(|ui| {
                ui.label(RichText::new("Transition").font(regular(12.0)).color(MUTED));
                for (kind, label) in [
                    (AnimationKind::None, "Aucune"),
                    (AnimationKind::Fade, "Fondu"),
                    (AnimationKind::Slide, "Glissement"),
                    (AnimationKind::Scale, "Zoom"),
                    (AnimationKind::Blur, "Flou"),
                    (AnimationKind::Reveal, "Balayage"),
                ] {
                    changed |= ui.radio_value(&mut d.animation.kind, kind, label).changed();
                }
            });
        }
        DesignBody::Band(b) => {
            changed |= family_edit(ui, "Police", &mut b.family, families);
            changed |= size_edit(ui, "Taille", &mut b.size, 16.0..=96.0);
            changed |= ui.checkbox(&mut b.uppercase, "Capitales").changed();
            changed |= color_edit(ui, "Texte", &mut b.text_color);
            let mut bg = b.background.unwrap_or(Rgba::new(10, 14, 22, 230));
            if color_edit(ui, "Bande", &mut bg) {
                b.background = Some(bg);
                changed = true;
            }
            ui.horizontal(|ui| {
                for (layout, label) in [
                    (po_design::BandLayout::Subtitle, "Sous-titre"),
                    (po_design::BandLayout::LowerThird, "Lower third"),
                    (po_design::BandLayout::SidePanel, "Panneau"),
                    (po_design::BandLayout::FocusCard, "Carte"),
                ] {
                    changed |= ui.radio_value(&mut b.layout, layout, label).changed();
                }
            });
            changed |= band_details(ui, b);
        }
        DesignBody::LowerThird(s) => {
            changed |= family_edit(ui, "Police du titre", &mut s.title.family, families);
            changed |= size_edit(ui, "Taille du titre", &mut s.title.size, 16.0..=110.0);
            changed |= color_edit(ui, "Titre", &mut s.title.color);
            changed |= family_edit(ui, "Police du sous-titre", &mut s.subtitle.family, families);
            changed |= size_edit(ui, "Taille du sous-titre", &mut s.subtitle.size, 12.0..=80.0);
            changed |= color_edit(ui, "Sous-titre", &mut s.subtitle.color);
            ui.horizontal(|ui| {
                ui.label(RichText::new("Boîte").font(regular(12.0)).color(MUTED));
                let mut kind = match s.fill {
                    Fill::None => 0,
                    Fill::Solid { .. } => 1,
                    Fill::Gradient { .. } => 2,
                };
                let before = kind;
                ui.radio_value(&mut kind, 0, "Aucune");
                ui.radio_value(&mut kind, 1, "Unie");
                ui.radio_value(&mut kind, 2, "Dégradé");
                if kind != before {
                    let base = Rgba::new(10, 14, 22, 215);
                    s.fill = match kind {
                        0 => Fill::None,
                        1 => Fill::Solid { color: base },
                        _ => Fill::Gradient { from: base, to: Rgba::new(10, 14, 22, 90) },
                    };
                    changed = true;
                }
            });
            match &mut s.fill {
                Fill::Solid { color } => changed |= color_edit(ui, "Couleur de la boîte", color),
                Fill::Gradient { from, to } => {
                    changed |= color_edit(ui, "Début du dégradé", from);
                    changed |= color_edit(ui, "Fin du dégradé", to);
                }
                Fill::None => {}
            }
            ui.horizontal_wrapped(|ui| {
                ui.label(RichText::new("Position").font(regular(12.0)).color(MUTED));
                for anchor in Anchor::ALL {
                    changed |= ui.radio_value(&mut s.anchor, anchor, anchor.label()).changed();
                }
            });
            ui.horizontal(|ui| {
                ui.label(RichText::new("Texte").font(regular(12.0)).color(MUTED));
                changed |= ui.radio_value(&mut s.align, Align::Left, "À gauche").changed();
                changed |= ui.radio_value(&mut s.align, Align::Center, "Centré").changed();
                changed |= ui.radio_value(&mut s.align, Align::Right, "À droite").changed();
            });
            ui.horizontal(|ui| {
                ui.label(RichText::new("Entrée").font(regular(12.0)).color(MUTED));
                for entrance in [
                    Entrance::None,
                    Entrance::Fade,
                    Entrance::Slide(Direction::Right),
                    Entrance::Reveal(Direction::Right),
                    Entrance::WordByWord,
                ] {
                    changed |= ui.radio_value(&mut s.motion.enter, entrance, entrance.label()).changed();
                }
            });
            let mut hold = s.hold_ms as f32 / 1000.0;
            if size_edit(ui, "Durée d'affichage (s, 0 = jusqu'au masquage)", &mut hold, 0.0..=60.0) {
                s.hold_ms = (hold * 1000.0) as u32;
                changed = true;
            }
        }
        DesignBody::Subtitles(s) => {
            ui.horizontal_wrapped(|ui| {
                let mut look = s.look;
                for l in SubtitleLook::ALL {
                    ui.radio_value(&mut look, l, l.label());
                }
                if look != s.look {
                    s.set_look(look);
                    changed = true;
                }
            });
            changed |= family_edit(ui, "Police", &mut s.font.family, families);
            changed |= size_edit(ui, "Taille", &mut s.font.size, 20.0..=100.0);
            changed |= color_edit(ui, "Texte", &mut s.font.color);
            if s.look.has_box() {
                changed |= color_edit(ui, "Boîte", &mut s.box_color);
            }
            let mut reference = s.reference_color();
            if color_edit(ui, "Référence", &mut reference) {
                s.reference_color = Some(reference);
                changed = true;
            }
            let mut accent = s.accent.is_some();
            if ui.checkbox(&mut accent, "Filet doré").changed() {
                s.accent = accent.then_some(Rgba::rgb(0xe7, 0xc0, 0x7e).with_alpha(0.9));
                changed = true;
            }
            if let Some(color) = &mut s.accent {
                changed |= color_edit(ui, "Couleur du filet", color);
            }
            let mut lines = s.max_lines as f32;
            if size_edit(ui, "Lignes à pleine taille", &mut lines, 1.0..=3.0) {
                s.max_lines = lines as usize;
                changed = true;
            }
            changed |= align_edit(ui, "Alignement", &mut s.align);
            ui.horizontal(|ui| {
                ui.label(RichText::new("Position").font(regular(12.0)).color(MUTED));
                changed |= ui.radio_value(&mut s.position, po_design::BandPosition::Bottom, "En bas").changed();
                changed |= ui.radio_value(&mut s.position, po_design::BandPosition::Center, "Au centre").changed();
                changed |= ui.radio_value(&mut s.position, po_design::BandPosition::Top, "En haut").changed();
            });
        }
    }
    changed
}

/// Un slide d'exemple pour les aperçus, quand rien n'est au direct.
pub fn sample_slide() -> Slide {
    Slide::new(
        "Car Dieu a tant aimé le monde qu'il a donné son Fils unique, afin que quiconque croit en lui ne périsse point.",
        "Jean 3:16",
        SlideSource::Bible,
    )
}
