//! Le dessin d'une liste d'affichage en image RVBA, sur le processeur (tiny-skia).
//!
//! Sert aux sorties qui veulent des images (NDI, HDMI), aux aperçus et aux captures de référence
//! des tests. Les lettres sont dessinées d'après leurs contours vectoriels : le rendu est net à
//! toutes les tailles. Les fonds (dégradés, images), les ombres et halos, et les groupes animés des
//! transitions (opacité, déplacement, zoom, flou, découpe) sont dessinés ici.
//!
//! [`Renderer::backdrop_luminance`] mesure la luminosité d'un fond : la mise en page s'en sert
//! pour choisir la couleur de l'identification.

mod blur;

use std::collections::HashMap;

use cosmic_text::SwashCache;
use po_layout::{Anchor, DisplayList, Fonts, Group, Item, Rgba, Stop, TextLine, TextShadow};
use swash::zeno::Command;
use tiny_skia::{
    Color, FillRule, FilterQuality, GradientStop, LinearGradient, Mask, Paint, Path, PathBuilder, Pattern, Pixmap,
    PixmapPaint, Point, PremultipliedColorU8, RadialGradient, Rect, Shader, SpreadMode, Transform,
};

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

/// Le moteur de rendu (garde en cache les contours des lettres et les images décodées).
pub struct Renderer {
    swash: SwashCache,
    images: HashMap<String, Option<Pixmap>>,
    /// Des polices vides : le fond, seul dessiné par la sonde de luminosité, n'a pas de texte.
    no_fonts: Fonts,
    /// Les derniers fonds dessinés (dégradés, image, voiles) : un fond ne change pas d'un slide à
    /// l'autre, et chaque sortie (projection, aperçu, NDI) a sa taille.
    backdrops: Vec<(String, Pixmap)>,
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

fn stops(list: &[Stop]) -> Vec<GradientStop> {
    list.iter().map(|s| GradientStop::new(s.at, color(s.color))).collect()
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

/// Un rectangle aux coins arrondis.
fn rounded_rect(x: f32, y: f32, w: f32, h: f32, r: f32) -> Option<Path> {
    let r = r.min(w / 2.0).min(h / 2.0).max(0.0);
    if r <= 0.0 {
        return Rect::from_xywh(x, y, w, h).map(PathBuilder::from_rect);
    }
    // Arcs approchés par des cubiques (k = 0,5523).
    let k = 0.552_284_8 * r;
    let mut pb = PathBuilder::new();
    pb.move_to(x + r, y);
    pb.line_to(x + w - r, y);
    pb.cubic_to(x + w - r + k, y, x + w, y + r - k, x + w, y + r);
    pb.line_to(x + w, y + h - r);
    pb.cubic_to(x + w, y + h - r + k, x + w - r + k, y + h, x + w - r, y + h);
    pb.line_to(x + r, y + h);
    pb.cubic_to(x + r - k, y + h, x, y + h - r + k, x, y + h - r);
    pb.line_to(x, y + r);
    pb.cubic_to(x, y + r - k, x + r - k, y, x + r, y);
    pb.close();
    pb.finish()
}

/// Une image décodée, en RVBA prémultiplié.
/// La couverture (opacité 0–255) d'un chemin, sur la zone de l'image où elle peut compter : ses
/// limites agrandies de `margin`, rognées à l'image agrandie de `margin + slack`.
struct Coverage {
    alpha: Vec<u8>,
    x0: i64,
    y0: i64,
    w: usize,
    h: usize,
}

fn coverage(pixmap: &Pixmap, path: &Path, transform: Transform, margin: f32, slack: f32) -> Option<Coverage> {
    let bounds = path.bounds().transform(transform)?;
    let edge = margin + slack;
    let (pw, ph) = (pixmap.width() as f32, pixmap.height() as f32);
    let x0 = (bounds.left() - margin).max(-edge).floor();
    let y0 = (bounds.top() - margin).max(-edge).floor();
    let x1 = (bounds.right() + margin).min(pw + edge).ceil();
    let y1 = (bounds.bottom() + margin).min(ph + edge).ceil();
    if x1 <= x0 || y1 <= y0 {
        return None;
    }
    let (w, h) = ((x1 - x0) as u32, (y1 - y0) as u32);
    // Un remplissage opaque : le chemin rapide de tiny-skia ; seule l'opacité est gardée.
    let mut layer = Pixmap::new(w, h)?;
    layer.fill_path(path, &paint(Rgba::BLACK), FillRule::Winding, transform.post_translate(-x0, -y0), None);
    let alpha = layer.pixels().iter().map(|p| p.alpha()).collect();
    Some(Coverage { alpha, x0: x0 as i64, y0: y0 as i64, w: w as usize, h: h as usize })
}

/// Pose `color` dans l'image avec l'opacité `alpha` (`w` × `h`, coin en `(ox, oy)`), en « source
/// par-dessus » sur des couleurs prémultipliées.
fn blend(pixmap: &mut Pixmap, alpha: &[u8], w: usize, h: usize, (ox, oy): (i64, i64), color: Rgba) {
    let (pw, ph) = (i64::from(pixmap.width()), i64::from(pixmap.height()));
    let (w, h) = (w as i64, h as i64);
    let (mx0, mx1) = ((-ox).max(0), (pw - ox).min(w));
    let (my0, my1) = ((-oy).max(0), (ph - oy).min(h));
    if mx0 >= mx1 || my0 >= my1 {
        return;
    }
    let [r, g, b, a] = color.0;
    let scale = |c: u8, k: u8| ((u16::from(c) * u16::from(k) + 127) / 255) as u8;
    let pixels = pixmap.pixels_mut();
    for my in my0..my1 {
        let src = &alpha[(my * w + mx0) as usize..(my * w + mx1) as usize];
        let start = ((oy + my) * pw + ox + mx0) as usize;
        for (dst, &m) in pixels[start..start + src.len()].iter_mut().zip(src) {
            if m == 0 {
                continue;
            }
            let alpha = scale(a, m);
            let keep = 255 - alpha;
            if let Some(c) = PremultipliedColorU8::from_rgba(
                scale(r, alpha) + scale(dst.red(), keep),
                scale(g, alpha) + scale(dst.green(), keep),
                scale(b, alpha) + scale(dst.blue(), keep),
                alpha + scale(dst.alpha(), keep),
            ) {
                *dst = c;
            }
        }
    }
}

/// Des lettres (`path`) avec leur ombre : la couverture des lettres est calculée une fois, floutée
/// pour l'ombre (seule l'opacité : l'ombre n'a qu'une couleur), puis reprise telle quelle pour le
/// texte. Sans couleur de texte (`None`), seule l'ombre est posée.
///
/// Avant : un calque RVBA de la taille de l'écran par ligne, flouté sur ses quatre canaux, puis les
/// lettres dessinées une seconde fois (0,4 s pour un paragraphe de 35 lignes en 960 × 540).
fn draw_shadowed(pixmap: &mut Pixmap, path: &Path, shadow: TextShadow, color: Option<Rgba>, transform: Transform) {
    let radius = shadow.blur * transform.sx;
    let (dx, dy) = (shadow.dx * transform.sx, shadow.dy * transform.sy);
    let margin = blur::reach(radius) + 1.0;
    let Some(c) = coverage(pixmap, path, transform, margin, dx.abs().max(dy.abs())) else { return };
    let mut blurred = c.alpha.clone();
    blur::blur_alpha(&mut blurred, c.w, c.h, radius);
    let offset = ((c.x0 as f32 + dx).round() as i64, (c.y0 as f32 + dy).round() as i64);
    blend(pixmap, &blurred, c.w, c.h, offset, shadow.color);
    if let Some(color) = color {
        blend(pixmap, &c.alpha, c.w, c.h, (c.x0, c.y0), color);
    }
}

fn load_image(path: &str) -> Option<Pixmap> {
    let rgba = image::open(path).ok()?.to_rgba8();
    let (w, h) = rgba.dimensions();
    let mut pixmap = Pixmap::new(w, h)?;
    for (dst, src) in pixmap.pixels_mut().iter_mut().zip(rgba.pixels()) {
        let [r, g, b, a] = src.0;
        *dst = tiny_skia::ColorU8::from_rgba(r, g, b, a).premultiply();
    }
    Some(pixmap)
}

impl Renderer {
    pub fn new() -> Self {
        Renderer {
            swash: SwashCache::new(),
            images: HashMap::new(),
            no_fonts: Fonts::from_files::<&str>(&[]),
            backdrops: Vec::new(),
        }
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
        let transform = Self::transform(list, width, height);
        let mut pixmap = self.backdrop(fonts, list, width, height)?;
        for layer in [&list.items, &list.overlay] {
            self.draw_items(&mut pixmap, fonts, layer, transform);
        }
        Ok(pixmap)
    }

    fn transform(list: &DisplayList, width: u32, height: u32) -> Transform {
        Transform::from_scale(width as f32 / list.width.max(1.0), height as f32 / list.height.max(1.0))
    }

    /// Le fond seul, opaque. Il se dessine une fois : les slides suivants le recopient tant qu'il
    /// ne change pas.
    pub fn backdrop(
        &mut self,
        fonts: &mut Fonts,
        list: &DisplayList,
        width: u32,
        height: u32,
    ) -> Result<Pixmap, RenderError> {
        let key = serde_json::to_string(&(&list.backdrop, list.background, width, height, list.width, list.height))
            .unwrap_or_default();
        if let Some(i) = self.backdrops.iter().position(|(cached, _)| *cached == key) {
            return Ok(self.backdrops[i].1.clone());
        }
        let mut pixmap = Pixmap::new(width, height).ok_or(RenderError::BadSize { width, height })?;
        pixmap.fill(color(list.background));
        self.draw_items(&mut pixmap, fonts, &list.backdrop, Self::transform(list, width, height));
        if self.backdrops.len() >= 4 {
            self.backdrops.remove(0);
        }
        self.backdrops.push((key, pixmap.clone()));
        Ok(pixmap)
    }

    /// Les trois couches d'un slide, pour les poser sur la carte graphique : le fond (opaque), le
    /// contenu et la surcouche (transparents, en couleurs prémultipliées). Posées l'une sur l'autre,
    /// elles donnent l'image de [`Renderer::render`].
    pub fn render_layers(
        &mut self,
        fonts: &mut Fonts,
        list: &DisplayList,
        width: u32,
        height: u32,
    ) -> Result<Layers, RenderError> {
        let transform = Self::transform(list, width, height);
        let backdrop = self.backdrop(fonts, list, width, height)?;
        let mut content = Pixmap::new(width, height).ok_or(RenderError::BadSize { width, height })?;
        self.draw_items(&mut content, fonts, &list.items, transform);
        let mut overlay = Pixmap::new(width, height).ok_or(RenderError::BadSize { width, height })?;
        self.draw_items(&mut overlay, fonts, &list.overlay, transform);
        Ok(Layers { backdrop, content, overlay })
    }

    /// La luminance moyenne (0 à 1) du fond de la liste (sans le texte) dans la zone (x, y, largeur,
    /// hauteur) : le fond est dessiné au quart de sa taille, puis mesuré.
    pub fn backdrop_luminance(&mut self, list: &DisplayList, zone: [f32; 4]) -> f32 {
        let (w, h) = (((list.width / 4.0).round() as u32).max(1), ((list.height / 4.0).round() as u32).max(1));
        let backdrop_only = DisplayList { items: Vec::new(), overlay: Vec::new(), ..list.clone() };
        let mut fonts = std::mem::replace(&mut self.no_fonts, Fonts::from_files::<&str>(&[]));
        let rendered = self.render(&mut fonts, &backdrop_only, w, h);
        self.no_fonts = fonts;
        let Ok(pixmap) = rendered else { return 0.0 };
        let k = w as f32 / list.width.max(1.0);
        let x0 = ((zone[0] * k).floor().max(0.0) as u32).min(w - 1);
        let y0 = ((zone[1] * k).floor().max(0.0) as u32).min(h - 1);
        let x1 = (((zone[0] + zone[2]) * k).ceil() as u32).clamp(x0 + 1, w);
        let y1 = (((zone[1] + zone[3]) * k).ceil() as u32).clamp(y0 + 1, h);
        let mut sum = 0.0f64;
        let mut n = 0u32;
        for y in y0..y1 {
            for x in x0..x1 {
                if let Some(p) = pixmap.pixel(x, y) {
                    let c = p.demultiply();
                    sum += f64::from(Rgba::new(c.red(), c.green(), c.blue(), 255).luminance());
                    n += 1;
                }
            }
        }
        if n == 0 { 0.0 } else { (sum / f64::from(n)) as f32 }
    }

    fn draw_items(&mut self, pixmap: &mut Pixmap, fonts: &mut Fonts, items: &[Item], transform: Transform) {
        let mut i = 0;
        while i < items.len() {
            // Les lignes d'un même bloc (même ombre, même police) : une seule ombre sous toutes les
            // lignes, comme la 2.8 (`ShadowTextLabel` floute le bloc entier), puis le texte.
            if let Item::Text(first) = &items[i]
                && let Some(shadow) = first.shadow
                && first.outline.is_none()
            {
                let same_block = |item: &Item| {
                    matches!(item, Item::Text(l) if l.shadow == Some(shadow) && l.size == first.size
                        && l.family == first.family && l.color == first.color)
                };
                let end = i + items[i..].iter().take_while(|item| same_block(item)).count();
                self.draw_block(pixmap, fonts, &items[i..end], shadow, transform);
                i = end;
                continue;
            }
            self.draw_item(pixmap, fonts, &items[i], transform);
            i += 1;
        }
    }

    /// Un bloc de lignes qui partagent une ombre et une couleur : l'ombre de toutes les lignes, puis
    /// les lignes.
    fn draw_block(
        &mut self,
        pixmap: &mut Pixmap,
        fonts: &mut Fonts,
        block: &[Item],
        shadow: TextShadow,
        transform: Transform,
    ) {
        let lines: Vec<(&TextLine, Path)> = block
            .iter()
            .filter_map(|item| match item {
                Item::Text(line) => self.line_path(fonts, line).map(|path| (line, path)),
                _ => None,
            })
            .collect();
        let Some(color) = lines.first().map(|(line, _)| line.color) else { return };
        let mut all = PathBuilder::new();
        for (_, path) in &lines {
            all.push_path(path);
        }
        if let Some(all) = all.finish() {
            draw_shadowed(pixmap, &all, shadow, Some(color), transform);
        }
    }

    fn draw_item(&mut self, pixmap: &mut Pixmap, fonts: &mut Fonts, item: &Item, transform: Transform) {
        match item {
            Item::Rect { x, y, w, h, radius, color: c } => {
                if let Some(path) = rounded_rect(*x, *y, *w, *h, *radius) {
                    pixmap.fill_path(&path, &paint(*c), FillRule::Winding, transform, None);
                }
            }
            Item::LinearGradient { x, y, w, h, from, to, stops: list } => {
                let shader = LinearGradient::new(
                    Point::from_xy(from[0], from[1]),
                    Point::from_xy(to[0], to[1]),
                    stops(list),
                    SpreadMode::Pad,
                    Transform::identity(),
                );
                self.fill_shader(pixmap, [*x, *y, *w, *h], shader, transform);
            }
            Item::RadialGradient { x, y, w, h, center, radius, stops: list } => {
                let c = Point::from_xy(center[0], center[1]);
                let shader =
                    RadialGradient::new(c, 0.0, c, *radius, stops(list), SpreadMode::Pad, Transform::identity());
                self.fill_shader(pixmap, [*x, *y, *w, *h], shader, transform);
            }
            Item::Image { path, x, y, w, h, opacity } => {
                let image = self.images.entry(path.clone()).or_insert_with(|| load_image(path));
                if let Some(image) = image.as_ref()
                    && let Some(rect) = Rect::from_xywh(*x, *y, *w, *h)
                {
                    let sx = w / image.width() as f32;
                    let sy = h / image.height() as f32;
                    let shader = Pattern::new(
                        image.as_ref(),
                        SpreadMode::Pad,
                        FilterQuality::Bicubic,
                        *opacity,
                        Transform::from_row(sx, 0.0, 0.0, sy, *x, *y),
                    );
                    let p = Paint { shader, anti_alias: true, ..Paint::default() };
                    pixmap.fill_rect(rect, &p, transform, None);
                }
            }
            Item::Text(line) => self.draw_line(pixmap, fonts, line, transform),
            Item::Group(group) => self.draw_group(pixmap, fonts, group, transform),
        }
    }

    fn fill_shader(
        &mut self,
        pixmap: &mut Pixmap,
        rect: [f32; 4],
        shader: Option<Shader<'static>>,
        transform: Transform,
    ) {
        if let (Some(shader), Some(r)) = (shader, Rect::from_xywh(rect[0], rect[1], rect[2], rect[3])) {
            let p = Paint { shader, anti_alias: true, ..Paint::default() };
            pixmap.fill_rect(r, &p, transform, None);
        }
    }

    /// Le contour de toutes les lettres d'une ligne, posé à sa place.
    fn line_path(&mut self, fonts: &mut Fonts, line: &TextLine) -> Option<Path> {
        let buffer = fonts.line(&line.text, &line.family, line.weight, line.size);
        let run = buffer.layout_runs().next()?;
        let glyphs: Vec<_> = run.glyphs.to_vec();
        let advances: Vec<f32> = glyphs.iter().map(|g| g.w * line.advance_scale + line.letter_spacing).collect();
        // La largeur visible : sans l'espacement après la dernière lettre.
        let visible = advances.iter().sum::<f32>() - if glyphs.is_empty() { 0.0 } else { line.letter_spacing };
        let left = match line.anchor {
            Anchor::Start => line.x,
            Anchor::Middle => line.x - visible / 2.0,
            Anchor::End => line.x - visible,
        };
        let mut pb = PathBuilder::new();
        let mut pen = 0.0;
        for (glyph, advance) in glyphs.iter().zip(&advances) {
            let key = glyph.physical((0.0, 0.0), 1.0).cache_key;
            let gx = left + pen + glyph.font_size * glyph.x_offset;
            let gy = line.baseline + glyph.y - glyph.font_size * glyph.y_offset;
            if let Some(path) =
                self.swash.get_outline_commands(&mut fonts.system, key).and_then(|cmds| glyph_path(cmds, gx, gy))
            {
                pb.push_path(&path);
            }
            pen += advance;
        }
        pb.finish()
    }

    fn draw_line(&mut self, pixmap: &mut Pixmap, fonts: &mut Fonts, line: &TextLine, transform: Transform) {
        let Some(path) = self.line_path(fonts, line) else { return };
        let Some(outline) = line.outline else {
            match line.shadow {
                Some(shadow) => draw_shadowed(pixmap, &path, shadow, Some(line.color), transform),
                None => pixmap.fill_path(&path, &paint(line.color), FillRule::Winding, transform, None),
            }
            return;
        };
        // Le contour : un trait arrondi deux fois plus large, dont la moitié dépasse des lettres,
        // puis les lettres par-dessus (l'ombre éventuelle dessous).
        if let Some(shadow) = line.shadow {
            draw_shadowed(pixmap, &path, shadow, None, transform);
        }
        let stroke = tiny_skia::Stroke {
            width: outline.width * 2.0,
            line_join: tiny_skia::LineJoin::Round,
            line_cap: tiny_skia::LineCap::Round,
            ..tiny_skia::Stroke::default()
        };
        pixmap.stroke_path(&path, &paint(outline.color), &stroke, transform, None);
        pixmap.fill_path(&path, &paint(line.color), FillRule::Winding, transform, None);
    }

    fn draw_group(&mut self, pixmap: &mut Pixmap, fonts: &mut Fonts, group: &Group, transform: Transform) {
        if group.opacity <= 0.004 || group.items.is_empty() {
            return;
        }
        let Some(mut layer) = Pixmap::new(pixmap.width(), pixmap.height()) else { return };
        self.draw_items(&mut layer, fonts, &group.items, transform);
        if group.blur > 0.0 {
            let full = Rect::from_xywh(0.0, 0.0, layer.width() as f32, layer.height() as f32);
            if let Some(full) = full {
                blur::blur_region(&mut layer, full, group.blur * transform.sx);
            }
        }
        // Le déplacement et le zoom du groupe, ramenés aux pixels de l'image.
        let (ox, oy) = (group.origin[0] * transform.sx, group.origin[1] * transform.sy);
        let placement = Transform::from_translate(group.dx * transform.sx, group.dy * transform.sy)
            .pre_translate(ox, oy)
            .pre_scale(group.scale, group.scale)
            .pre_translate(-ox, -oy);
        let mask = group.clip.and_then(|[x, y, w, h]| {
            let mut mask = Mask::new(pixmap.width(), pixmap.height())?;
            let rect = Rect::from_xywh(x, y, w.max(0.0), h.max(0.0))?;
            mask.fill_path(&PathBuilder::from_rect(rect), FillRule::Winding, true, transform);
            Some(mask)
        });
        // Sans zoom ni déplacement fractionnaire, le calque est recopié pixel pour pixel.
        let exact =
            (group.scale - 1.0).abs() < 1e-4 && placement.tx.fract().abs() < 1e-4 && placement.ty.fract().abs() < 1e-4;
        let quality = if exact { FilterQuality::Nearest } else { FilterQuality::Bilinear };
        let p = PixmapPaint { opacity: group.opacity.clamp(0.0, 1.0), quality, ..PixmapPaint::default() };
        pixmap.draw_pixmap(0, 0, layer.as_ref(), &p, placement, mask.as_ref());
    }
}

/// Les couches d'un slide (voir [`Renderer::render_layers`]).
#[derive(Clone)]
pub struct Layers {
    pub backdrop: Pixmap,
    pub content: Pixmap,
    pub overlay: Pixmap,
}

/// Une copie floutée d'une couche (la transition « flou » la pose en fondu avec la couche nette).
pub fn blurred(layer: &Pixmap, radius: f32) -> Pixmap {
    let mut out = layer.clone();
    if let Some(all) = Rect::from_xywh(0.0, 0.0, layer.width() as f32, layer.height() as f32) {
        blur::blur_region(&mut out, all, radius);
    }
    out
}

/// L'image en PNG.
pub fn encode_png(pixmap: &Pixmap) -> Result<Vec<u8>, RenderError> {
    pixmap.encode_png().map_err(|e| RenderError::Png(e.to_string()))
}

#[cfg(test)]
mod tests;
