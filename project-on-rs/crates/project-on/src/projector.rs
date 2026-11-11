//! La projection native : une fenêtre sans bord, au premier plan, posée exactement sur l'écran de
//! la salle (au pixel près, quelle que soit sa mise à l'échelle), qui montre la scène du Direct.
//! Repris de Pgraphics (`projector.rs`).
//!
//! L'écran est celui de la 2.8 (`display_screen`, sinon le plus grand des écrans secondaires).
//! Avec un seul écran branché, la projection s'ouvre dans une fenêtre : en plein écran, elle
//! couvrirait la régie et l'opérateur ne verrait plus rien (la 2.8 le faisait).
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
        let screen = screens::choose(&all, preferred).cloned().filter(|_| all.len() >= 2);
        Projector { screen, placed: false, kind: ScreenKind::Room }
    }

    /// Dans une fenêtre (un seul écran, ou essais).
    pub fn windowed() -> Projector {
        Projector { screen: None, placed: true, kind: ScreenKind::Room }
    }

    /// En plein écran sur `screen`.
    pub fn on(screen: Screen) -> Projector {
        Projector { screen: Some(screen), placed: false, kind: ScreenKind::Room }
    }

    /// Une sortie HDMI de ce genre sur `screen`.
    pub fn output(screen: Screen, kind: ScreenKind) -> Projector {
        Projector { screen: Some(screen), placed: false, kind }
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

    /// Montre la fenêtre de projection. Rend `false` si l'opérateur l'a fermée (Échap, fermeture).
    pub fn show(&mut self, ctx: &Context, stage: &Stage, outputs: &Outputs, now: f64) -> bool {
        let full = self.screen.is_some();
        let title = self.title();
        let mut builder = ViewportBuilder::default().with_title(&title).with_min_inner_size([320.0, 180.0]);
        builder = if full {
            builder.with_decorations(false).with_always_on_top().with_taskbar(false)
        } else {
            builder.with_inner_size([960.0, 540.0])
        };
        let mut keep = true;
        let id = ViewportId::from_hash_of(("projection", self.key()));
        ctx.show_viewport_immediate(id, builder, |ui, _| {
            let ctx = ui.ctx().clone();
            if let Some(screen) = &self.screen
                && !self.placed
            {
                self.placed = screens::place(&title, screen);
            }
            if ctx.input(|i| i.viewport().close_requested() || i.key_pressed(egui::Key::Escape)) {
                keep = false;
                return;
            }
            CentralPanel::no_frame().show(ui, |ui| {
                let area = ui.max_rect();
                if self.kind == ScreenKind::Room {
                    stage.paint(ui.painter(), area, now);
                } else if let Some(texture) = outputs.texture(self.kind) {
                    let uv = egui::Rect::from_min_max(egui::pos2(0.0, 0.0), egui::pos2(1.0, 1.0));
                    ui.painter().image(texture.id(), area, uv, egui::Color32::WHITE);
                }
                if full && ui.rect_contains_pointer(area) {
                    // Pas de flèche sur l'écran de la salle.
                    ctx.set_cursor_icon(CursorIcon::None);
                }
            });
        });
        keep
    }
}

#[cfg(test)]
mod tests {
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
