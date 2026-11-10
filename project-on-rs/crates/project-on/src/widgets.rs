//! Les composants de l'interface : boutons (à icône, principaux, fantômes), contrôle segmenté,
//! interrupteur, pastilles, lignes de liste et champ de recherche. Dessinés à la main pour une
//! allure homogène.
//!
//! Origine : `pgraphics-rs/crates/pgraphics/src/widgets.rs` (Pgraphics, ParaTech SARL), repris le
//! 2026-11-10 et publié sous la licence MIT de Project-On. Adaptations : pas de traduction, pas de
//! vu-mètre ni de pastille de sortie ; un champ de recherche en plus.

use std::sync::Arc;

use egui::{
    Align, Align2, Color32, CornerRadius, FontId, Galley, Layout, Margin, Rect, Response, RichText, Sense, Stroke, Ui,
    Vec2, pos2, vec2,
};

use crate::icons::{self, Icon};
use crate::theme::*;

/// L'échelle des boutons : compacte comme dans les logiciels de régie.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Size {
    Small,
    Normal,
    /// Les commandes du direct (Projeter, Masquer).
    Large,
    /// L'envoi au direct : la commande qu'on vise sans regarder.
    Hero,
}

impl Size {
    pub const fn height(self) -> f32 {
        match self {
            Size::Small => 22.0,
            Size::Normal => 26.0,
            Size::Large => 32.0,
            Size::Hero => 40.0,
        }
    }

    pub fn font(self) -> FontId {
        match self {
            Size::Small => medium(11.0),
            Size::Normal => medium(12.5),
            Size::Large => semibold(13.0),
            Size::Hero => bold(14.5),
        }
    }

    const fn glyph(self) -> f32 {
        match self {
            Size::Small => 12.0,
            Size::Normal => 14.0,
            Size::Large => 16.0,
            Size::Hero => 18.0,
        }
    }

    const fn pad(self) -> f32 {
        match self {
            Size::Small => 8.0,
            Size::Normal => 10.0,
            Size::Large => 12.0,
            Size::Hero => 14.0,
        }
    }

    const fn radius(self) -> u8 {
        match self {
            Size::Small => 5,
            Size::Normal => 6,
            Size::Large => 7,
            Size::Hero => 8,
        }
    }
}

/// Le côté d'un bouton icône seul.
pub const ICON_BUTTON: f32 = 26.0;
const GAP: f32 = 6.0;

/// Mélange vers le blanc (survol) ou le noir (appui).
fn lift(c: Color32, t: f32) -> Color32 {
    if t >= 0.0 { c.lerp_to_gamma(Color32::WHITE, t) } else { c.lerp_to_gamma(Color32::BLACK, -t) }
}

/// Un en-tête de section : petites capitales espacées.
pub fn section(ui: &mut Ui, title: &str) {
    ui.add_space(10.0);
    ui.label(RichText::new(title.to_uppercase()).font(semibold(10.5)).color(FAINT).extra_letter_spacing(0.9));
    ui.add_space(2.0);
}

/// Un en-tête de section avec des actions alignées à droite.
pub fn section_with(ui: &mut Ui, title: &str, actions: impl FnOnce(&mut Ui)) {
    ui.add_space(8.0);
    ui.horizontal(|ui| {
        ui.label(RichText::new(title.to_uppercase()).font(semibold(10.5)).color(FAINT).extra_letter_spacing(0.9));
        ui.with_layout(Layout::right_to_left(Align::Center), actions);
    });
}

/// Une carte : surface, bordure fine, coins arrondis.
pub fn card<R>(ui: &mut Ui, add: impl FnOnce(&mut Ui) -> R) -> egui::InnerResponse<R> {
    egui::Frame::NONE
        .fill(SURFACE)
        .stroke(Stroke::new(1.0, BORDER))
        .corner_radius(10.0)
        .inner_margin(Margin::same(12))
        .show(ui, add)
}

/// Un bouton icône seul, discret (il s'éclaire au survol).
pub fn icon_button(ui: &mut Ui, icon: Icon, tip: &str) -> Response {
    icon_button_sized(ui, icon, tip, ICON_BUTTON, MUTED)
}

pub fn icon_button_sized(ui: &mut Ui, icon: Icon, tip: &str, size: f32, color: Color32) -> Response {
    let (rect, response) = ui.allocate_exact_size(Vec2::splat(size), Sense::click());
    let hovered = response.hovered();
    if hovered {
        ui.painter().rect_filled(rect, CornerRadius::same(6), HOVER);
    }
    let inset = (size * 0.22).round();
    icons::paint(ui.painter(), rect.shrink(inset), icon, if hovered { TEXT } else { color });
    response.widget_info(|| egui::WidgetInfo::labeled(egui::Role::Button, true, tip));
    response.on_hover_text(tip)
}

/// Un bouton icône à deux états.
pub fn icon_toggle(ui: &mut Ui, icon: Icon, on: bool, color: Color32, tip: &str) -> Response {
    let (rect, response) = ui.allocate_exact_size(Vec2::splat(ICON_BUTTON), Sense::click());
    let painter = ui.painter();
    if on {
        painter.rect_filled(rect, CornerRadius::same(6), color.gamma_multiply(0.16));
    } else if response.hovered() {
        painter.rect_filled(rect, CornerRadius::same(6), HOVER);
    }
    let tint = if on {
        color
    } else if response.hovered() {
        TEXT
    } else {
        MUTED
    };
    icons::paint(painter, rect.shrink(6.0), icon, tint);
    response.widget_info(|| egui::WidgetInfo::selected(egui::Role::CheckBox, true, on, tip));
    response.on_hover_text(tip)
}

#[derive(Clone, Copy, PartialEq)]
pub enum Tone {
    /// Rempli d'une couleur (action principale).
    Primary(Color32),
    /// Bouton ordinaire : un fond plus clair que son panneau, sans bordure.
    Secondary,
    /// Fantôme qui rougit au survol.
    Danger,
}

fn galley(ui: &Ui, text: &str, font: FontId) -> Arc<Galley> {
    ui.painter().layout_no_wrap(text.to_string(), font, Color32::PLACEHOLDER)
}

/// Un bouton ordinaire : icône facultative, texte, ton ; sa largeur suit le texte.
pub fn button(ui: &mut Ui, icon: Option<Icon>, text: &str, tone: Tone) -> Response {
    button_at(ui, Size::Normal, icon, text, tone, true)
}

/// Un bouton à une taille de l'échelle, sa largeur suivant le texte.
pub fn button_at(ui: &mut Ui, size: Size, icon: Option<Icon>, text: &str, tone: Tone, enabled: bool) -> Response {
    let g = (!text.is_empty()).then(|| galley(ui, text, size.font()));
    let content = icon.map_or(0.0, |_| size.glyph()) + g.as_ref().map_or(0.0, |g| g.size().x);
    let gap = if icon.is_some() && g.is_some() { GAP } else { 0.0 };
    let width = (content + gap + size.pad() * 2.0).max(size.height());
    button_sized(ui, width, size, icon, text, tone, enabled)
}

/// Un bouton de largeur imposée, le contenu centré.
pub fn button_sized(
    ui: &mut Ui,
    width: f32,
    size: Size,
    icon: Option<Icon>,
    text: &str,
    tone: Tone,
    enabled: bool,
) -> Response {
    let g = (!text.is_empty()).then(|| galley(ui, text, size.font()));
    let sense = if enabled { Sense::click() } else { Sense::hover() };
    let (rect, response) = ui.allocate_exact_size(vec2(width, size.height()), sense);
    paint_button(ui, rect, &response, icon, g, tone, size, enabled);
    response.widget_info(|| egui::WidgetInfo::labeled(egui::Role::Button, enabled, text));
    response
}

fn paint_button(
    ui: &Ui,
    rect: Rect,
    response: &Response,
    icon: Option<Icon>,
    text: Option<Arc<Galley>>,
    tone: Tone,
    size: Size,
    enabled: bool,
) {
    let hovered = enabled && response.hovered();
    let pressed = enabled && response.is_pointer_button_down_on();
    let radius = CornerRadius::same(size.radius());
    let icon_size = size.glyph();
    let (fill, fg) = match tone {
        Tone::Primary(c) => {
            let fill = if pressed {
                lift(c, -0.15)
            } else if hovered {
                lift(c, 0.10)
            } else {
                c
            };
            (fill, Color32::WHITE)
        }
        Tone::Secondary => {
            let fill = if pressed {
                lift(HOVER, 0.05)
            } else if hovered {
                HOVER
            } else {
                RAISED
            };
            (fill, TEXT)
        }
        Tone::Danger => {
            (if hovered { PGM.gamma_multiply(0.14) } else { Color32::TRANSPARENT }, if hovered { PGM } else { MUTED })
        }
    };
    let alpha = if enabled { 1.0 } else { 0.4 };
    let painter = ui.painter();
    painter.rect_filled(rect, radius, fill.gamma_multiply(alpha));
    let gap = if icon.is_some() && text.is_some() { GAP } else { 0.0 };
    let content_w = icon.map_or(0.0, |_| icon_size) + gap + text.as_ref().map_or(0.0, |g| g.size().x);
    let mut x = rect.center().x - content_w / 2.0;
    if let Some(icon) = icon {
        let r = Rect::from_center_size(pos2(x + icon_size / 2.0, rect.center().y), Vec2::splat(icon_size));
        icons::paint(painter, r, icon, fg.gamma_multiply(alpha));
        x += icon_size + gap;
    }
    if let Some(g) = text {
        let pos = pos2(x, rect.center().y - g.size().y / 2.0);
        painter.galley(pos, g, fg.gamma_multiply(alpha));
    }
}

/// Un contrôle segmenté : renvoie vrai si la valeur a changé.
pub fn segmented<T: PartialEq + Copy>(ui: &mut Ui, value: &mut T, options: &[(T, &str)]) -> bool {
    let size = Size::Small;
    let (height, pad) = (size.height(), size.pad());
    let inset = 3.0;
    let segments: Vec<(T, &str, Arc<Galley>, f32)> = options
        .iter()
        .map(|(v, text)| {
            let g = galley(ui, text, size.font());
            let w = g.size().x + pad * 2.0;
            (*v, *text, g, w)
        })
        .collect();
    let total: f32 = segments.iter().map(|s| s.3).sum::<f32>() + inset * 2.0;
    let (outer, _) = ui.allocate_exact_size(vec2(total, height + inset * 2.0), Sense::hover());
    let radius = size.radius();
    ui.painter().rect_filled(outer, CornerRadius::same(radius + 2), WELL);
    let mut x = outer.min.x + inset;
    let mut changed = false;
    for (i, (v, label, g, w)) in segments.into_iter().enumerate() {
        let rect = Rect::from_min_size(pos2(x, outer.min.y + inset), vec2(w, height));
        let response = ui.interact(rect, ui.scope_id().with(("segment", i)), Sense::click());
        let selected = *value == v;
        response.widget_info(|| egui::WidgetInfo::selected(egui::Role::RadioButton, true, selected, label));
        let painter = ui.painter();
        if selected {
            painter.rect_filled(rect, CornerRadius::same(radius), HOVER);
        } else if response.hovered() {
            painter.rect_filled(rect, CornerRadius::same(radius), SURFACE);
        }
        let color = if selected { TEXT } else { MUTED };
        painter.galley(pos2(rect.min.x + pad, rect.center().y - g.size().y / 2.0), g, color);
        if response.clicked() && !selected {
            *value = v;
            changed = true;
        }
        x += w;
    }
    changed
}

/// Une petite pastille de texte (traduction, état).
pub fn chip(ui: &mut Ui, text: &str, color: Color32) -> Response {
    let g = galley(ui, text, semibold(10.0));
    let size = vec2(g.size().x + 12.0, 18.0);
    let (rect, response) = ui.allocate_exact_size(size, Sense::hover());
    let painter = ui.painter();
    painter.rect_filled(rect, CornerRadius::same(9), color.gamma_multiply(0.16));
    painter.galley(pos2(rect.min.x + 6.0, rect.center().y - g.size().y / 2.0), g, color);
    response
}

/// Un point d'état.
pub fn dot(ui: &mut Ui, color: Color32) -> Response {
    let (rect, response) = ui.allocate_exact_size(Vec2::splat(10.0), Sense::hover());
    ui.painter().circle_filled(rect.center(), 4.0, color);
    response
}

/// Une ligne de liste sélectionnable : survol, sélection avec un liseré ambre.
pub fn list_row(ui: &mut Ui, selected: bool, height: f32, label: &str) -> (Rect, Response) {
    let width = ui.available_width();
    let (rect, response) = ui.allocate_exact_size(vec2(width, height), Sense::click());
    response.widget_info(|| egui::WidgetInfo::selected(egui::Role::ListBoxOption, true, selected, label));
    let painter = ui.painter();
    if selected {
        painter.rect_filled(rect, CornerRadius::same(7), RAISED);
        let bar = Rect::from_min_size(pos2(rect.min.x, rect.min.y + 6.0), vec2(3.0, (rect.height() - 12.0).max(4.0)));
        painter.rect_filled(bar, CornerRadius::same(2), ACCENT);
    } else if response.hovered() {
        painter.rect_filled(rect, CornerRadius::same(7), SURFACE);
    }
    (rect, response)
}

/// Un texte peint, tronqué à `max_width`.
pub fn paint_text(
    ui: &Ui,
    pos: egui::Pos2,
    anchor: Align2,
    text: &str,
    font: FontId,
    color: Color32,
    max_width: f32,
) -> Rect {
    let mut job = egui::text::LayoutJob::simple_singleline(text.to_string(), font, color);
    job.wrap = egui::text::TextWrapping::truncate_at_width(max_width.max(10.0));
    let g = ui.painter().layout_job(job);
    let rect = anchor.anchor_size(pos, g.size());
    ui.painter().galley(rect.min, g, color);
    rect
}

/// Un texte peint sur plusieurs lignes (au plus `max_rows`), dans `width`.
pub fn paint_wrapped(
    ui: &Ui,
    pos: egui::Pos2,
    text: &str,
    font: FontId,
    color: Color32,
    width: f32,
    max_rows: usize,
) -> Rect {
    let mut job = egui::text::LayoutJob::simple(text.to_string(), font, color, width.max(10.0));
    job.wrap.max_rows = max_rows;
    let g = ui.painter().layout_job(job);
    let rect = Rect::from_min_size(pos, g.size());
    ui.painter().galley(rect.min, g, color);
    rect
}

/// Un champ de recherche : loupe, texte, croix pour effacer. Rend la réponse du champ.
pub fn search_field(ui: &mut Ui, text: &mut String, hint: &str, width: f32) -> Response {
    let height = Size::Normal.height() + 4.0;
    let (outer, _) = ui.allocate_exact_size(vec2(width, height), Sense::hover());
    ui.painter().rect(outer, CornerRadius::same(7), WELL, Stroke::new(1.0, BORDER), egui::StrokeKind::Inside);
    let glyph = Rect::from_center_size(pos2(outer.min.x + 15.0, outer.center().y), Vec2::splat(14.0));
    icons::paint(ui.painter(), glyph, Icon::Search, FAINT);
    let clear = !text.is_empty();
    let edit_rect = Rect::from_min_max(
        pos2(outer.min.x + 28.0, outer.min.y + 2.0),
        pos2(outer.max.x - if clear { 28.0 } else { 8.0 }, outer.max.y - 2.0),
    );
    let response = ui.put(
        edit_rect,
        egui::TextEdit::singleline(text)
            .hint_text(RichText::new(hint).color(FAINT))
            .frame(egui::Frame::NONE)
            .align(Align2::LEFT_CENTER)
            .font(regular(13.0)),
    );
    // Le nom du champ pour les lecteurs d'écran (et les essais) : son invite.
    ui.ctx().accesskit_node_builder(response.id, |node| node.set_label(hint));
    if clear {
        let x = Rect::from_center_size(pos2(outer.max.x - 15.0, outer.center().y), Vec2::splat(20.0));
        let r = ui.interact(x, response.id.with("effacer"), Sense::click());
        icons::paint(ui.painter(), x.shrink(4.0), Icon::X, if r.hovered() { TEXT } else { FAINT });
        if r.clicked() {
            text.clear();
            response.request_focus();
        }
    }
    response
}
