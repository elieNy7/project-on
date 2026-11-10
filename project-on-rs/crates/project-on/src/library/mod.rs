//! Les bibliothèques : Bible, Cantiques, Prédications, Exposé, Livres.
//!
//! Comme dans la 2.8, un clic prépare dans l'Aperçu tout le programme (le chapitre, le sermon, le
//! cantique) à partir de l'entrée cliquée ; un double-clic l'envoie directement au direct. La ligne
//! préparée porte un liseré vert, celle du direct un liseré rouge.

pub mod bible;
pub mod books;
pub mod hymns;
pub mod sermons;

use egui::{Align2, Color32, CornerRadius, Rect, Response, Sense, Ui, pos2, vec2};
use po_program::Cue;

use crate::icons::Icon;
use crate::theme::*;
use crate::widgets;

/// Une page du rail.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Page {
    Bible,
    Hymns,
    Sermons,
    Expose,
    Books,
}

impl Page {
    pub const ALL: [Page; 5] = [Page::Bible, Page::Hymns, Page::Sermons, Page::Expose, Page::Books];

    pub fn label(self) -> &'static str {
        match self {
            Page::Bible => "Bible",
            Page::Hymns => "Cantiques",
            Page::Sermons => "Prédications",
            Page::Expose => "Exposé",
            Page::Books => "Livres",
        }
    }

    pub fn icon(self) -> Icon {
        match self {
            Page::Bible => Icon::BookOpen,
            Page::Hymns => Icon::Music,
            Page::Sermons => Icon::Mic,
            Page::Expose => Icon::FileText,
            Page::Books => Icon::Library,
        }
    }
}

/// D'où vient un programme : pour retrouver ses lignes dans la bibliothèque.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Origin {
    Sermon(i64),
    Chapter {
        translation: i64,
        book: i64,
        chapter: i64,
    },
    Hymn(i64),
    /// Un chapitre d'ouvrage (une ligne de la table `sermon`).
    BookChapter(i64),
}

/// Un programme préparé par une bibliothèque, et d'où il vient.
#[derive(Debug, Clone, PartialEq)]
pub struct Prepared {
    pub cue: Cue,
    pub origin: Origin,
}

/// Ce que demande un clic.
#[derive(Debug, Clone, PartialEq)]
pub enum Action {
    /// Préparer dans l'Aperçu.
    Cue(Prepared),
    /// Envoyer directement au direct (double-clic).
    Take(Prepared),
}

impl Action {
    /// Un clic (simple ou double) sur une entrée.
    pub fn from_click(response: &Response, prepared: impl FnOnce() -> Prepared) -> Option<Action> {
        if response.double_clicked() {
            Some(Action::Take(prepared()))
        } else if response.clicked() {
            Some(Action::Cue(prepared()))
        } else {
            None
        }
    }
}

/// Les entrées montrées dans l'Aperçu et au direct, pour un programme d'origine donnée.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Marks {
    pub preview: Option<(Origin, usize)>,
    pub live: Option<(Origin, usize)>,
}

impl Marks {
    /// L'état de l'entrée `index` d'un programme venu de `origin`.
    pub fn of(&self, origin: &Origin, index: usize) -> (bool, bool) {
        let hit = |m: &Option<(Origin, usize)>| m.as_ref().is_some_and(|(o, i)| o == origin && *i == index);
        (hit(&self.preview), hit(&self.live))
    }
}

/// La hauteur d'une ligne d'élément (sermon, cantique, chapitre) et d'une ligne d'entrée.
pub const ITEM_ROW: f32 = 46.0;
pub const ENTRY_ROW: f32 = 58.0;

/// Une ligne d'élément : titre, sous-titre, pastille à droite.
pub fn item_row(ui: &mut Ui, selected: bool, title: &str, subtitle: &str, chip: Option<&str>) -> Response {
    let (rect, response) = widgets::list_row(ui, selected, ITEM_ROW - 2.0, title);
    ui.add_space(2.0);
    let chip_w = if let Some(chip) = chip {
        let g = ui.painter().layout_no_wrap(chip.to_string(), semibold(10.0), MUTED);
        let w = g.size().x + 12.0;
        let r = Rect::from_min_size(pos2(rect.max.x - w - 8.0, rect.center().y - 9.0), vec2(w, 18.0));
        ui.painter().rect_filled(r, CornerRadius::same(9), RAISED);
        ui.painter().galley(pos2(r.min.x + 6.0, r.center().y - g.size().y / 2.0), g, MUTED);
        w + 12.0
    } else {
        0.0
    };
    let width = rect.width() - 24.0 - chip_w;
    widgets::paint_text(
        ui,
        pos2(rect.min.x + 12.0, rect.min.y + 7.0),
        Align2::LEFT_TOP,
        title,
        semibold(13.0),
        if selected { TEXT } else { TEXT.gamma_multiply(0.92) },
        width,
    );
    widgets::paint_text(
        ui,
        pos2(rect.min.x + 12.0, rect.min.y + 25.0),
        Align2::LEFT_TOP,
        subtitle,
        regular(11.5),
        MUTED,
        width,
    );
    response
}

/// Une ligne d'entrée (verset, strophe, paragraphe) : repère, deux lignes de texte, liseré de
/// l'Aperçu (vert) ou du direct (rouge).
pub fn entry_row(ui: &mut Ui, marker: &str, text: &str, preview: bool, live: bool) -> Response {
    let width = ui.available_width();
    let (rect, response) = ui.allocate_exact_size(vec2(width, ENTRY_ROW - 4.0), Sense::click());
    response.widget_info(|| egui::WidgetInfo::labeled(egui::Role::Button, true, format!("{marker} {text}")));
    ui.add_space(4.0);
    let painter = ui.painter();
    let fill = if live {
        LIVE.gamma_multiply(0.12)
    } else if preview {
        PREVIEW.gamma_multiply(0.10)
    } else if response.hovered() {
        SURFACE
    } else {
        PANEL.lerp_to_gamma(SURFACE, 0.45)
    };
    painter.rect_filled(rect, CornerRadius::same(8), fill);
    let bar = |c: Color32| {
        let r = Rect::from_min_size(pos2(rect.min.x, rect.min.y + 6.0), vec2(3.0, rect.height() - 12.0));
        painter.rect_filled(r, CornerRadius::same(2), c);
    };
    if live {
        bar(LIVE);
    } else if preview {
        bar(PREVIEW);
    }
    let marker_w = 54.0;
    widgets::paint_text(
        ui,
        pos2(rect.min.x + 12.0, rect.min.y + 9.0),
        Align2::LEFT_TOP,
        marker,
        semibold(11.5),
        ACCENT,
        marker_w - 8.0,
    );
    widgets::paint_wrapped(
        ui,
        pos2(rect.min.x + 12.0 + marker_w, rect.min.y + 8.0),
        &text.replace('\n', " "),
        regular(12.5),
        TEXT.gamma_multiply(0.94),
        rect.width() - marker_w - 24.0,
        2,
    );
    response
}

/// Un message centré dans une zone vide (« Choisissez un sermon »).
pub fn empty(ui: &mut Ui, text: &str) {
    ui.add_space(40.0);
    ui.vertical_centered(|ui| {
        ui.label(egui::RichText::new(text).font(regular(13.0)).color(FAINT));
    });
}

/// Le décalage qui montre la ligne `row` d'une liste à lignes de hauteur fixe (`show_rows`), au
/// tiers de la hauteur visible. Chaque ligne occupe sa hauteur plus l'espacement d'egui.
pub fn scroll_offset(ui: &Ui, row: usize, row_height: f32) -> f32 {
    let step = row_height + ui.spacing().item_spacing.y;
    (row as f32 * step - ui.available_height() / 3.0).max(0.0)
}
