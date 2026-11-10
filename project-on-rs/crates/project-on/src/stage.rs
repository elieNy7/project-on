//! La scène : ce que montrent le Direct, l'Aperçu et les fenêtres de projection, posé par la carte
//! graphique.
//!
//! Chaque slide arrive du fil de rendu en trois couches (fond opaque, contenu et identification
//! transparents) qui deviennent des textures. Une transition ne redessine rien : à chaque image, la
//! carte graphique pose les textures de l'ancien et du nouveau slide selon le plan de
//! `po_layout::transition::plan`, le même qui sert au rendu par le processeur. Le Direct et la
//! projection montrent les mêmes textures : aucun rendu de plus pour un écran de plus.

use std::sync::Arc;

use egui::{Color32, ColorImage, Painter, Pos2, Rect, TextureHandle, TextureOptions, pos2, vec2};
use po_design::{Animation, AnimationKind, Direction};
use po_layout::transition::{Layer, overlay_plan, plan};
use po_layout::{DisplayList, Slide};
use tiny_skia::Pixmap;

use crate::worker::Done;

/// La durée du fondu de « Masquer ».
const HIDE_SECONDS: f64 = 0.25;

/// Un slide prêt à poser : ses textures et sa mise en page.
pub struct Frame {
    pub slide: Slide,
    /// La mise en page (sa taille, sa scène, son identification).
    pub list: DisplayList,
    backdrop: TextureHandle,
    content: TextureHandle,
    overlay: Option<TextureHandle>,
    blurred: Option<TextureHandle>,
}

fn options() -> TextureOptions {
    TextureOptions {
        magnification: egui::TextureFilter::Linear,
        minification: egui::TextureFilter::Linear,
        // Les moniteurs montrent le slide réduit : sans mipmaps, les lettres scintilleraient.
        mipmap_mode: Some(egui::TextureFilter::Linear),
        ..Default::default()
    }
}

fn image(pixmap: &Pixmap) -> ColorImage {
    ColorImage::from_rgba_premultiplied([pixmap.width() as usize, pixmap.height() as usize], pixmap.data())
}

impl Frame {
    /// Envoie les couches d'un slide dessiné à la carte graphique.
    pub fn upload(ctx: &egui::Context, name: &str, slide: Slide, done: Done) -> Frame {
        let empty_overlay = done.list.overlay.is_empty();
        Frame {
            slide,
            backdrop: ctx.load_texture(format!("{name}-fond"), image(&done.layers.backdrop), options()),
            content: ctx.load_texture(format!("{name}-contenu"), image(&done.layers.content), options()),
            overlay: (!empty_overlay)
                .then(|| ctx.load_texture(format!("{name}-identification"), image(&done.layers.overlay), options())),
            blurred: done.blurred.as_ref().map(|b| ctx.load_texture(format!("{name}-flou"), image(b), options())),
            list: done.list,
        }
    }
}

/// Le rectangle de taille `w` × `h` (rapport conservé) centré dans `area`.
pub fn fit(area: Rect, w: f32, h: f32) -> Rect {
    let ratio = w / h.max(1.0);
    let size = if area.width() / area.height().max(1.0) > ratio {
        vec2(area.height() * ratio, area.height())
    } else {
        vec2(area.width(), area.width() / ratio)
    };
    Rect::from_center_size(area.center(), size)
}

fn alpha(opacity: f32) -> Color32 {
    // Textures prémultipliées : la teinte multiplie les quatre canaux.
    let a = (opacity.clamp(0.0, 1.0) * 255.0).round() as u8;
    Color32::from_rgba_premultiplied(a, a, a, a)
}

const FULL_UV: Rect = Rect { min: Pos2 { x: 0.0, y: 0.0 }, max: Pos2 { x: 1.0, y: 1.0 } };

/// Une scène : le slide montré, le précédent pendant une transition, et l'état « masqué ».
#[derive(Default)]
pub struct Stage {
    current: Option<Arc<Frame>>,
    previous: Option<Arc<Frame>>,
    animation: Option<(Animation, f64)>,
    hidden: bool,
    hidden_since: f64,
}

impl Stage {
    /// Montre `frame`, avec une transition depuis le slide montré (aucune pour le premier).
    pub fn show(&mut self, frame: Frame, animation: Animation, now: f64) {
        let had = self.current.take();
        self.previous = had.clone();
        let animate = had.is_some() && animation.kind != AnimationKind::None && animation.duration_ms > 0;
        self.animation = animate.then_some((animation, now));
        if !animate {
            self.previous = None;
        }
        self.current = Some(Arc::new(frame));
    }

    pub fn clear(&mut self) {
        *self = Stage { hidden: self.hidden, hidden_since: self.hidden_since, ..Stage::default() };
    }

    pub fn current(&self) -> Option<&Frame> {
        self.current.as_deref()
    }

    pub fn hidden(&self) -> bool {
        self.hidden
    }

    /// Masque (ou rend) le texte et l'identification ; le fond reste.
    pub fn set_hidden(&mut self, hidden: bool, now: f64) {
        if hidden != self.hidden {
            // Repartir de l'opacité actuelle si l'opérateur change d'avis pendant le fondu.
            let left = (HIDE_SECONDS - (now - self.hidden_since)).max(0.0);
            self.hidden = hidden;
            self.hidden_since = now - left;
        }
    }

    /// L'avancement (0 à 1) de la transition en cours.
    fn progress(&self, now: f64) -> Option<(Animation, f32)> {
        let (animation, start) = self.animation?;
        let t = ((now - start) / (f64::from(animation.duration_ms) / 1000.0)) as f32;
        (t < 1.0).then_some((animation, t.max(0.0)))
    }

    /// L'opacité du texte (1 = visible, 0 = masqué).
    fn visibility(&self, now: f64) -> f32 {
        let k = ((now - self.hidden_since) / HIDE_SECONDS).clamp(0.0, 1.0) as f32;
        if self.hidden { 1.0 - k } else { k }
    }

    /// Une transition ou un fondu est en cours : il faut repeindre à la prochaine image.
    pub fn animating(&self, now: f64) -> bool {
        self.progress(now).is_some() || (now - self.hidden_since) < HIDE_SECONDS
    }

    /// Termine ce qui est fini (libère les textures de l'ancien slide).
    pub fn tick(&mut self, now: f64) {
        if self.animation.is_some() && self.progress(now).is_none() {
            self.animation = None;
            self.previous = None;
        }
    }

    /// Pose la scène dans `area` (rapport du slide conservé, bandes noires autour), au temps `now`.
    pub fn paint(&self, painter: &Painter, area: Rect, now: f64) {
        painter.rect_filled(area, 0.0, Color32::BLACK);
        let Some(current) = self.current.as_deref() else { return };
        let (w, h) = (current.list.width, current.list.height);
        let screen = fit(area, w, h);
        let k = screen.width() / w.max(1.0);
        let at = |x: f32, y: f32| pos2(screen.min.x + x * k, screen.min.y + y * k);
        painter.image(current.backdrop.id(), screen, FULL_UV, Color32::WHITE);

        let (animation, t) = self
            .progress(now)
            .unwrap_or((Animation { kind: AnimationKind::None, duration_ms: 0, direction: Direction::Up }, 1.0));
        let visible = self.visibility(now);
        if visible <= 0.004 {
            return;
        }
        let frame_of = |layer: Layer| match layer {
            Layer::To => Some(current),
            Layer::From => self.previous.as_deref(),
        };
        for p in plan(current.list.stage, w, h, &animation, t) {
            let Some(frame) = frame_of(p.layer) else { continue };
            let texture = if p.blur > 0.0 { frame.blurred.as_ref().unwrap_or(&frame.content) } else { &frame.content };
            // Le calque entier, déplacé puis agrandi autour de son centre de zoom.
            let [ox, oy] = p.origin;
            let corner = |x: f32, y: f32| at(p.dx + ox + p.scale * (x - ox), p.dy + oy + p.scale * (y - oy));
            let quad = Rect::from_min_max(corner(0.0, 0.0), corner(w, h));
            let clip = match p.clip {
                Some([x, y, cw, ch]) => Rect::from_min_max(at(x, y), at(x + cw.max(0.0), y + ch.max(0.0))),
                None => screen,
            }
            .intersect(screen)
            .intersect(painter.clip_rect());
            painter.with_clip_rect(clip).image(texture.id(), quad, FULL_UV, alpha(p.opacity * visible));
        }
        let same_overlay = self.previous.as_deref().is_none_or(|prev| prev.list.overlay == current.list.overlay);
        for (layer, opacity) in overlay_plan(same_overlay, &animation, t) {
            if let Some(texture) = frame_of(layer).and_then(|f| f.overlay.as_ref()) {
                painter.image(texture.id(), screen, FULL_UV, alpha(opacity * visible));
            }
        }
    }
}
