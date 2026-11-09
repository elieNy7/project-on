//! Le dessin d'une liste d'affichage en image RVBA, sur le processeur (tiny-skia).
//!
//! Sert aux sorties qui veulent des images (NDI, HDMI), aux aperçus des designs et aux captures de
//! référence des tests. Les lettres sont dessinées d'après leurs contours vectoriels : le rendu est
//! net à toutes les tailles et ne dépend pas d'un cache de bitmaps.

use cosmic_text::SwashCache;
use po_layout::{Anchor, DisplayList, Fonts, Item, Rgba, TextLine};
use swash::zeno::Command;
use tiny_skia::{Color, FillRule, Paint, Path, PathBuilder, Pixmap, Rect, Transform};

/// Les erreurs du rendu.
#[derive(Debug)]
pub enum RenderError {
    /// Une taille d'image nulle ou démesurée.
    BadSize {
        width: u32,
        height: u32,
    },
    Png(String),
}

impl std::fmt::Display for RenderError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            RenderError::BadSize { width, height } => write!(f, "taille d'image impossible : {width} × {height}"),
            RenderError::Png(e) => write!(f, "écriture PNG impossible : {e}"),
        }
    }
}

impl std::error::Error for RenderError {}

/// Le moteur de rendu (garde ses contours de lettres en cache).
pub struct Renderer {
    swash: SwashCache,
}

impl Default for Renderer {
    fn default() -> Self {
        Self::new()
    }
}

fn color(c: Rgba) -> Color {
    let [r, g, b, a] = c.0;
    Color::from_rgba8(r, g, b, a)
}

fn paint(c: Rgba) -> Paint<'static> {
    let mut p = Paint::default();
    p.set_color(color(c));
    p.anti_alias = true;
    p
}

/// Le contour d'une lettre (repère de la police : y vers le haut) posé en (x, y).
fn glyph_path(commands: &[Command], x: f32, y: f32) -> Option<Path> {
    let mut pb = PathBuilder::new();
    for command in commands {
        match *command {
            Command::MoveTo(p) => pb.move_to(x + p.x, y - p.y),
            Command::LineTo(p) => pb.line_to(x + p.x, y - p.y),
            Command::QuadTo(c, p) => pb.quad_to(x + c.x, y - c.y, x + p.x, y - p.y),
            Command::CurveTo(c1, c2, p) => pb.cubic_to(x + c1.x, y - c1.y, x + c2.x, y - c2.y, x + p.x, y - p.y),
            Command::Close => pb.close(),
        }
    }
    pb.finish()
}

impl Renderer {
    pub fn new() -> Self {
        Renderer { swash: SwashCache::new() }
    }

    /// Dessine la liste dans une image de `width` × `height` pixels (mise à l'échelle si la liste a
    /// été calculée pour une autre taille).
    pub fn render(
        &mut self,
        fonts: &mut Fonts,
        list: &DisplayList,
        width: u32,
        height: u32,
    ) -> Result<Pixmap, RenderError> {
        let mut pixmap = Pixmap::new(width, height).ok_or(RenderError::BadSize { width, height })?;
        pixmap.fill(color(list.background));
        let transform = Transform::from_scale(width as f32 / list.width.max(1.0), height as f32 / list.height.max(1.0));
        for item in &list.items {
            match item {
                Item::Rect { x, y, w, h, color: c, .. } => {
                    if let Some(rect) = Rect::from_xywh(*x, *y, *w, *h) {
                        pixmap.fill_rect(rect, &paint(*c), transform, None);
                    }
                }
                Item::Text(line) => self.draw_line(&mut pixmap, fonts, line, transform),
            }
        }
        Ok(pixmap)
    }

    fn draw_line(&mut self, pixmap: &mut Pixmap, fonts: &mut Fonts, line: &TextLine, transform: Transform) {
        let buffer = fonts.line(&line.text, &line.family, line.weight, line.size);
        let Some(run) = buffer.layout_runs().next() else { return };
        let left = match line.anchor {
            Anchor::Start => line.x,
            Anchor::Middle => line.x - run.line_w / 2.0,
            Anchor::End => line.x - run.line_w,
        };
        let mut pb = PathBuilder::new();
        for glyph in run.glyphs {
            let key = glyph.physical((0.0, 0.0), 1.0).cache_key;
            let gx = left + glyph.x + glyph.font_size * glyph.x_offset;
            let gy = line.baseline + glyph.y - glyph.font_size * glyph.y_offset;
            if let Some(path) =
                self.swash.get_outline_commands(&mut fonts.system, key).and_then(|cmds| glyph_path(cmds, gx, gy))
            {
                pb.push_path(&path);
            }
        }
        if let Some(path) = pb.finish() {
            pixmap.fill_path(&path, &paint(line.color), FillRule::Winding, transform, None);
        }
    }
}

/// L'image en PNG.
pub fn encode_png(pixmap: &Pixmap) -> Result<Vec<u8>, RenderError> {
    pixmap.encode_png().map_err(|e| RenderError::Png(e.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use po_layout::{SlideContent, SlideStyle, bundled_fonts_dir, layout_slide};

    #[test]
    fn draws_text_inside_the_safe_area() {
        let dir = bundled_fonts_dir();
        let mut fonts = Fonts::from_files(&[dir.join("Passion One/PassionOne-Bold.ttf")]);
        let style = SlideStyle { reference_position: po_layout::ReferencePosition::Bottom, ..SlideStyle::default() };
        let content = SlideContent { text: "Car Dieu a tant aimé le monde".into(), reference: "Jean 3:16".into() };
        let list = layout_slide(&mut fonts, &content, &style, 960.0, 540.0);
        let pixmap = Renderer::new().render(&mut fonts, &list, 960, 540).unwrap();
        let bg = style.background.0;
        // Des pixels de texte (clairs) existent, et aucun dans la marge de 5 %.
        let mut lit = 0usize;
        for (i, px) in pixmap.pixels().iter().enumerate() {
            let (x, y) = ((i % 960) as f32, (i / 960) as f32);
            if px.red() > bg[0] + 60 {
                lit += 1;
                assert!(
                    (47.0..=913.0).contains(&x) && (26.0..=514.0).contains(&y),
                    "pixel de texte hors zone en ({x}, {y})"
                );
            }
        }
        assert!(lit > 5_000, "trop peu de texte dessiné : {lit}");
        assert!(encode_png(&pixmap).unwrap().starts_with(b"\x89PNG"));
    }
}
