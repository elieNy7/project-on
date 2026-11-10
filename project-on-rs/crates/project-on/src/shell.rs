//! La coque de validation de la phase 0 : un écran réel (pas une maquette) qui branche ensemble la
//! base, la mise en page, le rendu et le thème, pour mesurer la pile. L'interface définitive (rail,
//! bibliothèque complète, playlist, designs) arrive en phase 3.

use egui::{
    Align, Color32, ColorImage, CornerRadius, Key, Layout, RichText, Sense, Stroke, TextureHandle, TextureOptions, Ui,
    vec2,
};
use po_db::{Database, Paragraph, Sermon, SermonFilter};
use po_layout::{Fonts, SlideContent, SlideStyle, layout_slide};
use po_render::Renderer;

use crate::theme;

/// Une image de moniteur (Aperçu ou Direct) et ce qu'elle montre.
struct Monitor {
    content: SlideContent,
    texture: TextureHandle,
}

/// L'état de l'écran.
pub struct Shell {
    db: Option<Database>,
    fonts: Fonts,
    renderer: Renderer,
    style: SlideStyle,
    sermons: Vec<Sermon>,
    filter: String,
    selected: Option<usize>,
    paragraphs: Vec<Paragraph>,
    previewed: Option<usize>,
    preview: Option<Monitor>,
    live: Option<Monitor>,
    /// Ce qui vient de passer au direct, à diffuser aux écrans (Web, projection).
    pub taken: Option<SlideContent>,
    /// Le nombre d'écrans Web connectés (affiché dans la barre).
    pub web_screens: usize,
    error: Option<String>,
}

/// La taille des images des moniteurs (16:9, nette sur un moniteur de ~480 px de large).
const MONITOR_SIZE: (u32, u32) = (960, 540);

impl Shell {
    pub fn new(db: Option<Database>, fonts: Fonts) -> Self {
        let mut shell = Shell {
            db,
            fonts,
            renderer: Renderer::new(),
            style: SlideStyle::default(),
            sermons: Vec::new(),
            filter: String::new(),
            selected: None,
            paragraphs: Vec::new(),
            previewed: None,
            preview: None,
            live: None,
            taken: None,
            web_screens: 0,
            error: None,
        };
        shell.refresh_list();
        shell
    }

    /// Le nombre de sermons de la liste affichée.
    pub fn sermon_count(&self) -> usize {
        self.sermons.len()
    }

    fn refresh_list(&mut self) {
        let Some(db) = &self.db else {
            self.error = Some("Base de données introuvable.".into());
            return;
        };
        let title = self.filter.trim();
        let filter = SermonFilter { title: (!title.is_empty()).then_some(title), ..Default::default() };
        match db.list_sermons(&filter) {
            Ok(list) => {
                self.sermons = list;
                self.error = None;
            }
            Err(e) => self.error = Some(e.to_string()),
        }
        self.selected = None;
        self.paragraphs.clear();
    }

    /// Ouvre un sermon de la liste.
    pub fn select_sermon(&mut self, index: usize) {
        let Some(sermon) = self.sermons.get(index) else { return };
        self.selected = Some(index);
        self.previewed = None;
        if let Some(db) = &self.db {
            match db.paragraphs(sermon.id) {
                Ok(p) => self.paragraphs = p,
                Err(e) => self.error = Some(e.to_string()),
            }
        }
    }

    fn render(&mut self, ctx: &egui::Context, name: &str, content: &SlideContent) -> Option<TextureHandle> {
        let (w, h) = MONITOR_SIZE;
        let list = layout_slide(&mut self.fonts, content, &self.style, w as f32, h as f32);
        match self.renderer.render(&mut self.fonts, &list, w, h) {
            Ok(pixmap) => {
                let image = ColorImage::from_rgba_premultiplied([w as usize, h as usize], pixmap.data());
                Some(ctx.load_texture(name, image, TextureOptions::LINEAR))
            }
            Err(e) => {
                self.error = Some(e.to_string());
                None
            }
        }
    }

    /// Un clic sur un paragraphe : il est préparé dans l'Aperçu, rien ne part au direct.
    pub fn preview_paragraph(&mut self, ctx: &egui::Context, index: usize) {
        let (Some(sermon), Some(paragraph)) =
            (self.selected.and_then(|i| self.sermons.get(i)), self.paragraphs.get(index))
        else {
            return;
        };
        let date = sermon.date.as_deref().unwrap_or("");
        let reference = po_text::format_reference(date, &sermon.title, &paragraph.marker);
        let content = SlideContent { text: paragraph.text.clone(), reference };
        self.previewed = Some(index);
        if let Some(texture) = self.render(ctx, "apercu", &content) {
            self.preview = Some(Monitor { content, texture });
        }
    }

    /// F2 : l'Aperçu passe au Direct.
    pub fn take(&mut self, ctx: &egui::Context) {
        let Some(content) = self.preview.as_ref().map(|m| m.content.clone()) else { return };
        if let Some(texture) = self.render(ctx, "direct", &content) {
            self.live = Some(Monitor { content: content.clone(), texture });
            self.taken = Some(content);
        }
    }

    pub fn ui(&mut self, ui: &mut Ui) {
        if ui.input(|i| i.key_pressed(Key::F2)) {
            self.take(ui.ctx());
        }
        egui::Panel::top("barre").exact_size(48.0).frame(bar_frame()).show(ui, |ui| self.command_bar(ui));
        egui::Panel::left("rail").exact_size(112.0).resizable(false).frame(bar_frame()).show(ui, rail);
        egui::Panel::left("bibliotheque")
            .exact_size(340.0)
            .resizable(false)
            .frame(panel_frame())
            .show(ui, |ui| self.library(ui));
        egui::Panel::right("moniteurs")
            .exact_size(500.0)
            .resizable(false)
            .frame(panel_frame())
            .show(ui, |ui| self.monitors(ui));
        egui::CentralPanel::no_frame().frame(panel_frame().fill(theme::BG)).show(ui, |ui| self.paragraph_list(ui));
    }

    fn command_bar(&mut self, ui: &mut Ui) {
        ui.horizontal_centered(|ui| {
            ui.label(RichText::new("Project-On").font(theme::semibold(16.0)).color(theme::TEXT));
            ui.label(RichText::new("3.0 · phase 1").font(theme::regular(11.5)).color(theme::FAINT));
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                let web = self.web_screens;
                pill(ui, &format!("Web · {web}"), if web > 0 { theme::PREVIEW } else { theme::FAINT });
                pill(ui, "Salle", if self.live.is_some() { theme::LIVE } else { theme::FAINT });
            });
        });
    }

    fn library(&mut self, ui: &mut Ui) {
        ui.label(RichText::new("PRÉDICATIONS").font(theme::semibold(12.0)).color(theme::MUTED));
        ui.add_space(6.0);
        let edit =
            egui::TextEdit::singleline(&mut self.filter).hint_text("Filtrer par titre…").desired_width(f32::INFINITY);
        if ui.add(edit).changed() {
            self.refresh_list();
        }
        ui.add_space(4.0);
        let count = self.sermons.len();
        ui.label(RichText::new(format!("{count} sermons")).font(theme::regular(11.5)).color(theme::FAINT));
        if let Some(error) = &self.error {
            ui.colored_label(theme::WARN, error);
        }
        ui.add_space(4.0);
        let row_h = 40.0;
        let mut clicked = None;
        // Seules les lignes visibles sont dessinées : la liste reste fluide quelle que soit sa taille.
        egui::ScrollArea::vertical().auto_shrink(false).show_rows(ui, row_h, count, |ui, rows| {
            for i in rows {
                let sermon = &self.sermons[i];
                if list_row(ui, self.selected == Some(i), row_h, sermon.date.as_deref().unwrap_or(""), &sermon.title)
                    .clicked()
                {
                    clicked = Some(i);
                }
            }
        });
        if let Some(i) = clicked {
            self.select_sermon(i);
        }
    }

    fn paragraph_list(&mut self, ui: &mut Ui) {
        let Some(sermon) = self.selected.and_then(|i| self.sermons.get(i)) else {
            ui.centered_and_justified(|ui| {
                ui.label(RichText::new("Choisissez une prédication").color(theme::FAINT));
            });
            return;
        };
        ui.label(RichText::new(&sermon.title).font(theme::semibold(17.0)).color(theme::TEXT));
        ui.label(
            RichText::new(format!("{} · {}", sermon.date.as_deref().unwrap_or(""), sermon.tradition))
                .color(theme::MUTED),
        );
        ui.add_space(8.0);
        let mut clicked = None;
        egui::ScrollArea::vertical().auto_shrink(false).show(ui, |ui| {
            for (i, paragraph) in self.paragraphs.iter().enumerate() {
                let selected = self.previewed == Some(i);
                let frame = egui::Frame::new()
                    .fill(if selected { theme::RAISED } else { theme::SURFACE })
                    .stroke(if selected { Stroke::new(1.0, theme::PREVIEW) } else { Stroke::NONE })
                    .corner_radius(CornerRadius::same(7))
                    .inner_margin(egui::Margin::symmetric(12, 8));
                let response = frame
                    .show(ui, |ui| {
                        ui.set_width(ui.available_width());
                        ui.horizontal_top(|ui| {
                            ui.label(RichText::new(&paragraph.marker).font(theme::medium(12.0)).color(theme::ACCENT));
                            ui.add(egui::Label::new(RichText::new(&paragraph.text).color(theme::TEXT)).wrap());
                        });
                    })
                    .response
                    .interact(Sense::click());
                if response.clicked() {
                    clicked = Some(i);
                }
                ui.add_space(4.0);
            }
        });
        if let Some(i) = clicked {
            self.preview_paragraph(ui.ctx(), i);
        }
    }

    fn monitors(&mut self, ui: &mut Ui) {
        monitor(ui, "APERÇU", theme::PREVIEW, self.preview.as_ref());
        ui.add_space(8.0);
        let take = egui::Button::new(
            RichText::new("Envoyer au direct   F2").font(theme::semibold(14.0)).color(Color32::WHITE),
        )
        .fill(theme::LIVE)
        .min_size(vec2(ui.available_width(), 40.0));
        if ui.add_enabled(self.preview.is_some(), take).clicked() {
            self.take(ui.ctx());
        }
        ui.add_space(14.0);
        monitor(ui, "DIRECT", theme::LIVE, self.live.as_ref());
    }
}

fn bar_frame() -> egui::Frame {
    egui::Frame::new().fill(theme::PANEL).inner_margin(egui::Margin::symmetric(12, 6))
}

fn panel_frame() -> egui::Frame {
    egui::Frame::new().fill(theme::PANEL).inner_margin(egui::Margin::same(12))
}

fn pill(ui: &mut Ui, text: &str, color: Color32) {
    egui::Frame::new()
        .fill(color.gamma_multiply(0.16))
        .corner_radius(CornerRadius::same(11))
        .inner_margin(egui::Margin::symmetric(10, 3))
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                let (dot, _) = ui.allocate_exact_size(vec2(8.0, 8.0), Sense::hover());
                ui.painter().circle_filled(dot.center(), 4.0, color);
                ui.label(RichText::new(text).font(theme::medium(12.0)).color(theme::TEXT));
            });
        });
}

/// Le rail : seules les Prédications sont branchées en phase 0.
fn rail(ui: &mut Ui) {
    ui.add_space(6.0);
    for (label, active) in [
        ("Bible", false),
        ("Cantiques", false),
        ("Prédications", true),
        ("Livres", false),
        ("Médias", false),
        ("Playlist", false),
        ("Designs", false),
        ("Réglages", false),
    ] {
        let (rect, _) = ui.allocate_exact_size(vec2(ui.available_width(), 34.0), Sense::hover());
        if active {
            ui.painter().rect_filled(rect, CornerRadius::same(7), theme::RAISED);
            ui.painter().rect_filled(
                egui::Rect::from_min_size(rect.min, vec2(3.0, rect.height())),
                CornerRadius::same(2),
                theme::ACCENT,
            );
        }
        ui.painter().text(
            rect.left_center() + vec2(10.0, 0.0),
            egui::Align2::LEFT_CENTER,
            label,
            theme::medium(12.0),
            if active { theme::TEXT } else { theme::FAINT },
        );
        ui.add_space(2.0);
    }
}

fn list_row(ui: &mut Ui, selected: bool, height: f32, date: &str, title: &str) -> egui::Response {
    let (rect, response) = ui.allocate_exact_size(vec2(ui.available_width(), height), Sense::click());
    let fill = if selected {
        theme::ACCENT.gamma_multiply(0.18)
    } else if response.hovered() {
        theme::HOVER
    } else {
        Color32::TRANSPARENT
    };
    ui.painter().rect_filled(rect, CornerRadius::same(7), fill);
    let painter = ui.painter_at(rect.shrink2(vec2(10.0, 0.0)));
    painter.text(rect.left_top() + vec2(10.0, 6.0), egui::Align2::LEFT_TOP, date, theme::regular(11.0), theme::MUTED);
    painter.text(rect.left_top() + vec2(10.0, 20.0), egui::Align2::LEFT_TOP, title, theme::medium(13.0), theme::TEXT);
    response
}

fn monitor(ui: &mut Ui, label: &str, color: Color32, image: Option<&Monitor>) {
    ui.horizontal(|ui| {
        let (dot, _) = ui.allocate_exact_size(vec2(8.0, 8.0), Sense::hover());
        ui.painter().circle_filled(dot.center(), 4.0, color);
        ui.label(RichText::new(label).font(theme::semibold(12.0)).color(color));
    });
    ui.add_space(4.0);
    let width = ui.available_width();
    let (rect, _) = ui.allocate_exact_size(vec2(width, width * 9.0 / 16.0), Sense::hover());
    let painter = ui.painter();
    match image {
        Some(m) => {
            painter.image(
                m.texture.id(),
                rect,
                egui::Rect::from_min_max([0.0, 0.0].into(), [1.0, 1.0].into()),
                Color32::WHITE,
            );
        }
        None => {
            painter.rect_filled(rect, CornerRadius::same(4), Color32::BLACK);
            painter.text(rect.center(), egui::Align2::CENTER_CENTER, "Vide", theme::regular(12.0), theme::FAINT);
        }
    }
    painter.rect_stroke(rect, CornerRadius::same(4), Stroke::new(2.0, color), egui::StrokeKind::Outside);
}
