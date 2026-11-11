//! La projection native : une fenêtre sans bord, au premier plan, posée exactement sur l'écran de
//! la salle (au pixel près, quelle que soit sa mise à l'échelle), qui montre la scène du Direct.
//! Repris de Pgraphics (`projector.rs`).
//!
//! L'écran est celui de la 2.8 (`display_screen`, sinon le plus grand des écrans secondaires).
//! La projection est toujours **plein écran, comme un diaporama PowerPoint**, même avec un seul
//! écran : elle couvre alors tout l'écran, barre des tâches comprise, et se pilote au clavier comme
//! PowerPoint (→ ← Page↓ Page↑ Espace, B pour masquer le texte, Échap ou F5 pour revenir à la régie).
//! Un rappel discret « Échap : revenir à la régie » s'affiche 3 secondes quand elle couvre la régie.
//!
//! Plusieurs écrans peuvent projeter en même temps (deux vidéoprojecteurs, un écran de retour) :
//! chaque fenêtre pose les mêmes textures, sans rendu de plus.

use egui::{CentralPanel, Context, CursorIcon, ViewportBuilder, ViewportId};

use po_web::ScreenKind;

use crate::outputs::Outputs;
use crate::screens::{self, Screen};
use crate::stage::Stage;

/// Le titre de la fenêtre (Windows la retrouve par son titre pour la poser sur l'écran).
pub const TITLE: &str = "Project-On — Projection";

/// La projection ouverte.
#[derive(Debug, Clone)]
pub struct Projector {
    /// L'écran en plein écran ; `None` : une fenêtre.
    pub screen: Option<Screen>,
    placed: bool,
    /// Le seul écran du poste : la projection couvre la régie.
    alone: bool,
    /// Quand la fenêtre a été montrée la première fois (pour le rappel).
    shown_at: Option<f64>,
    /// Ce que montre l'écran : la salle (le Direct), ou une sortie HDMI de diffusion (bandeau ou
    /// sous-titres sur la couleur de clé, retour de scène).
    pub kind: ScreenKind,
}

impl PartialEq for Projector {
    fn eq(&self, other: &Self) -> bool {
        self.key() == other.key()
    }
}

impl Projector {
    /// Ouvre la projection sur l'écran choisi par les réglages (`display_screen`).
    pub fn open(preferred: &str) -> Projector {
        let all = screens::list();
        let screen = screens::choose(&all, preferred).cloned();
        Projector { screen, placed: false, alone: all.len() < 2, shown_at: None, kind: ScreenKind::Room }
    }

    /// Dans une fenêtre (un seul écran, ou essais).
    pub fn windowed() -> Projector {
        Projector { screen: None, placed: true, alone: false, shown_at: None, kind: ScreenKind::Room }
    }

    /// En plein écran sur `screen`.
    pub fn on(screen: Screen) -> Projector {
        let alone = screens::list().len() < 2;
        Projector { screen: Some(screen), placed: false, alone, shown_at: None, kind: ScreenKind::Room }
    }

    /// Une sortie HDMI de ce genre sur `screen`.
    pub fn output(screen: Screen, kind: ScreenKind) -> Projector {
        Projector { screen: Some(screen), placed: false, alone: false, shown_at: None, kind }
    }

    /// Plein écran sur le seul écran du poste : la projection couvre la régie.
    pub fn covers_regie(&self) -> bool {
        self.alone && self.screen.is_some()
    }

    /// Ce qui distingue deux projections : le nom Windows de l'écran, ou « fenêtre ».
    pub fn key(&self) -> &str {
        self.screen.as_ref().map_or("fenêtre", |s| s.device.as_str())
    }

    /// Le titre de la fenêtre, propre à chaque écran (Windows la retrouve par lui).
    fn title(&self) -> String {
        format!("{TITLE} — {}", self.label())
    }

    /// La taille de rendu des slides : celle de l'écran (bornée à 2560 de large : au-delà, la
    /// carte graphique agrandit), sinon 1920 × 1080.
    pub fn render_size(&self) -> (u32, u32) {
        match &self.screen {
            Some(s) if s.width > 0 && s.height > 0 => {
                if s.width > 2560 {
                    (2560, (2560.0 * s.height as f32 / s.width as f32).round() as u32)
                } else {
                    (s.width, s.height)
                }
            }
            _ => (1920, 1080),
        }
    }

    /// Ce que l'opérateur lit dans la barre : « Écran 2 — 1920 × 1080 » ou « Fenêtre ».
    pub fn label(&self) -> String {
        let place = self.screen.as_ref().map_or_else(|| "Fenêtre".into(), |s| s.label.clone());
        if self.kind == ScreenKind::Room { place } else { format!("{place} · {}", self.kind.label()) }
    }

    /// Montre la fenêtre de projection, et rend ce que l'opérateur y a demandé au clavier.
    pub fn show(
        &mut self,
        ctx: &Context,
        stage: &Stage,
        outputs: &Outputs,
        video: Option<&egui::TextureHandle>,
        now: f64,
    ) -> Keys {
        let full = self.screen.is_some();
        let title = self.title();
        let mut builder = ViewportBuilder::default().with_title(&title).with_min_inner_size([320.0, 180.0]);
        builder = if full {
            builder.with_decorations(false).with_always_on_top().with_taskbar(false)
        } else {
            builder.with_inner_size([960.0, 540.0])
        };
        let mut keys = Keys { keep: true, step: 0, hide: false };
        let shown_at = *self.shown_at.get_or_insert(now);
        let hint = full && self.alone && now - shown_at < 3.0;
        let id = ViewportId::from_hash_of(("projection", self.key()));
        ctx.show_viewport_immediate(id, builder, |ui, _| {
            let ctx = ui.ctx().clone();
            if let Some(screen) = &self.screen
                && !self.placed
            {
                self.placed = screens::place(&title, screen);
            }
            // Les touches d'un diaporama PowerPoint.
            ctx.input(|i| {
                use egui::Key;
                if i.viewport().close_requested() || i.key_pressed(Key::Escape) || i.key_pressed(Key::F5) {
                    keys.keep = false;
                }
                if [Key::ArrowRight, Key::ArrowDown, Key::PageDown, Key::Space, Key::Enter]
                    .iter()
                    .any(|k| i.key_pressed(*k))
                {
                    keys.step += 1;
                }
                if [Key::ArrowLeft, Key::ArrowUp, Key::PageUp, Key::Backspace].iter().any(|k| i.key_pressed(*k)) {
                    keys.step -= 1;
                }
                if i.key_pressed(Key::B) {
                    keys.hide = true;
                }
            });
            if !keys.keep {
                return;
            }
            CentralPanel::no_frame().show(ui, |ui| {
                let area = ui.max_rect();
                if self.kind == ScreenKind::Room {
                    stage.paint(ui.painter(), area, now);
                    if let Some(texture) = video {
                        crate::video::paint(ui.painter(), area, texture);
                    }
                } else if let Some(texture) = outputs.texture(self.kind) {
                    // Une image 16:9 sur un écran qui ne l'est pas (letterbox) : les marges sont à la
                    // couleur de clé, que le mélangeur efface.
                    let fill = match outputs.wanted().key {
                        Some(key) if self.kind.transparent() => egui::Color32::from_rgb(key.0[0], key.0[1], key.0[2]),
                        _ => egui::Color32::BLACK,
                    };
                    ui.painter().rect_filled(area, 0.0, fill);
                    let uv = egui::Rect::from_min_max(egui::pos2(0.0, 0.0), egui::pos2(1.0, 1.0));
                    ui.painter().image(texture.id(), fit(area, texture.size_vec2()), uv, egui::Color32::WHITE);
                }
                if full && ui.rect_contains_pointer(area) {
                    // Pas de flèche sur l'écran de la salle.
                    ctx.set_cursor_icon(CursorIcon::None);
                }
                if hint {
                    let text = "Échap : revenir à la régie   ·   ← → : slides   ·   B : masquer le texte";
                    let font = egui::FontId::proportional(15.0);
                    let galley = ui.painter().layout_no_wrap(text.into(), font, egui::Color32::WHITE);
                    let pos = egui::pos2(area.center().x - galley.size().x / 2.0, area.max.y - 56.0);
                    let back = egui::Rect::from_min_size(pos, galley.size()).expand2(egui::vec2(14.0, 8.0));
                    ui.painter().rect_filled(back, 8.0, egui::Color32::from_black_alpha(170));
                    ui.painter().galley(pos, galley, egui::Color32::WHITE);
                    ctx.request_repaint_after(std::time::Duration::from_millis(500));
                }
            });
        });
        keys
    }
}

/// Le plus grand rectangle de proportions `size`, centré dans `area`.
pub fn fit(area: egui::Rect, size: egui::Vec2) -> egui::Rect {
    if size.x <= 0.0 || size.y <= 0.0 {
        return area;
    }
    let scale = (area.width() / size.x).min(area.height() / size.y);
    egui::Rect::from_center_size(area.center(), size * scale)
}

/// La taille de rendu d'une sortie HDMI : celle de l'écran, ou du 16:9 qui y tient (letterbox).
pub fn hdmi_size((w, h): (u32, u32), letterbox: bool) -> (u32, u32) {
    if !letterbox || w == 0 || h == 0 || w * 9 == h * 16 {
        return (w, h);
    }
    if w * 9 > h * 16 { (h * 16 / 9, h) } else { (w, w * 9 / 16) }
}

/// Ce que l'opérateur a demandé dans la fenêtre de projection.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Keys {
    /// Faux : la projection se ferme (Échap, F5, fermeture).
    pub keep: bool,
    /// Slides suivants (positif) ou précédents (négatif).
    pub step: i32,
    /// B : masquer ou afficher le texte.
    pub hide: bool,
}

#[cfg(test)]
mod tests {
    #[test]
    fn hdmi_outputs_keep_16_9_on_other_screens() {
        assert_eq!(hdmi_size((1920, 1200), true), (1920, 1080));
        assert_eq!(hdmi_size((1920, 1200), false), (1920, 1200));
        assert_eq!(hdmi_size((1440, 1080), true), (1440, 810));
        assert_eq!(hdmi_size((1920, 1080), true), (1920, 1080));
        let area = egui::Rect::from_min_size(egui::pos2(0.0, 0.0), egui::vec2(1920.0, 1200.0));
        let r = fit(area, egui::vec2(1920.0, 1080.0));
        assert_eq!((r.min.y, r.max.y), (60.0, 1140.0));
    }

    use super::*;

    #[test]
    fn render_size_follows_the_screen() {
        let screen =
            |w, h| Screen { device: "x".into(), label: "x".into(), x: 0, y: 0, width: w, height: h, primary: false };
        let p = Projector::on(screen(1280, 720));
        assert_eq!(p.render_size(), (1280, 720));
        let p = Projector::on(screen(3840, 2160));
        assert_eq!(p.render_size(), (2560, 1440));
        assert_eq!(Projector::windowed().render_size(), (1920, 1080));
    }
}
