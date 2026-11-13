//! La mise en page des habillages, sur fond transparent : les **lower thirds** et les
//! **sous-titres** (`po_design::graphics`). Leur entrée et leur sortie (fondu, glissement,
//! révélation, mot à mot) sont des images comme les autres : [`graphic_frame`].

use po_design::graphics::{
    Accent, Entrance, Fill, Font, LowerThirdStyle, LowerThirdText, Motion, Side, SubtitleLook, SubtitleStyle,
};
use po_design::{Align, BandPosition, Direction, Rgba};

use crate::display::{Anchor as TextAnchor, Group, Item, Stop, TextLine, TextOutline, TextShadow};
use crate::fit::{FontSpec, balanced_lines};
use crate::fonts::Fonts;

/// Un habillage mis en page : la boîte (fond, filet) et les lignes de texte, avec la fin de
/// chaque mot (pour l'entrée mot à mot).
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Graphic {
    pub width: f32,
    pub height: f32,
    /// Le rectangle de l'habillage (x, y, largeur, hauteur).
    pub rect: [f32; 4],
    pub backing: Vec<Item>,
    pub lines: Vec<(TextLine, Vec<f32>)>,
}

impl Graphic {
    /// Tous les éléments, sans animation.
    pub fn items(&self) -> Vec<Item> {
        let mut items = self.backing.clone();
        items.extend(self.lines.iter().map(|(line, _)| Item::Text(line.clone())));
        items
    }

    pub fn is_empty(&self) -> bool {
        self.backing.is_empty() && self.lines.is_empty()
    }
}

fn scaled_font(fonts: &mut Fonts, font: &Font, k: f32) -> (String, f32, f32) {
    (fonts.resolve_family(&font.family), (font.size * k).round().max(6.0), font.letter_spacing * k)
}

fn transform(text: &str, font: &Font) -> String {
    if font.uppercase { text.to_uppercase() } else { text.to_string() }
}

/// Une ligne posée, avec les fins de ses mots (abscisses absolues, du bord de départ).
#[allow(clippy::too_many_arguments)]
fn line(
    fonts: &mut Fonts,
    text: &str,
    family: &str,
    font: &Font,
    size: f32,
    spacing: f32,
    x: f32,
    anchor: TextAnchor,
    baseline: f32,
    k: f32,
) -> (TextLine, Vec<f32>) {
    let width = fonts.qt_advance(text, family, font.weight, size, spacing);
    let left = match anchor {
        TextAnchor::Start => x,
        TextAnchor::Middle => x - width / 2.0,
        TextAnchor::End => x - width,
    };
    // La fin de chaque mot : la largeur du début de la ligne jusqu'à lui.
    let mut ends = Vec::new();
    let mut offset = 0;
    for word in text.split(' ') {
        offset += word.len();
        if !word.is_empty() {
            ends.push(left + fonts.qt_advance(&text[..offset], family, font.weight, size, spacing));
        }
        offset += 1;
    }
    let shadow = font.shadow.map(|(color, blur)| TextShadow { color, blur: blur * k, dx: 0.0, dy: (2.0 * k).round() });
    let outline = font.outline.map(|(color, width)| TextOutline { color, width: (width * k).max(1.0) });
    (
        TextLine {
            text: text.to_string(),
            x,
            baseline,
            anchor,
            size,
            family: family.to_string(),
            weight: font.weight,
            color: font.color,
            width,
            letter_spacing: spacing,
            advance_scale: 1.0,
            shadow,
            outline,
        },
        ends,
    )
}

fn fill_items(fill: Fill, rect: [f32; 4], radius: f32) -> Vec<Item> {
    let [x, y, w, h] = rect;
    match fill {
        Fill::None => Vec::new(),
        Fill::Solid { color } => vec![Item::Rect { x, y, w, h, radius, color }],
        Fill::Gradient { from, to } => {
            // Un dégradé dans une boîte arrondie : les coins sont rognés par un groupe découpé.
            let gradient = Item::LinearGradient {
                x,
                y,
                w,
                h,
                from: [x, y],
                to: [x + w, y],
                stops: vec![Stop { at: 0.0, color: from }, Stop { at: 1.0, color: to }],
            };
            vec![gradient]
        }
    }
}

fn accent_item(accent: &Accent, rect: [f32; 4], k: f32) -> Item {
    let [x, y, w, h] = rect;
    let t = (accent.thickness * k).max(1.0);
    let (ax, ay, aw, ah) = match accent.side {
        Side::Left => (x, y, t, h),
        Side::Top => (x, y, w, t),
        Side::Bottom => (x, y + h - t, w, t),
    };
    Item::Rect { x: ax, y: ay, w: aw, h: ah, radius: 0.0, color: accent.color }
}

/// Un lower third, sur un écran `width` × `height`.
pub fn layout_lower_third(
    fonts: &mut Fonts,
    text: &LowerThirdText,
    style: &LowerThirdStyle,
    width: f32,
    height: f32,
) -> Graphic {
    let mut graphic = Graphic { width, height, ..Graphic::default() };
    if text.is_empty() {
        return graphic;
    }
    let k = height / 1080.0;
    let safe_x = width * style.safe_area / 100.0;
    let safe_y = height * style.safe_area / 100.0;
    let (pad_x, pad_y) = (style.padding.0 * k, style.padding.1 * k);
    let max_inner = if style.width > 0.0 {
        (width * style.width / 100.0).min(width - 2.0 * safe_x) - 2.0 * pad_x
    } else {
        (width * 0.7).min(width - 2.0 * safe_x) - 2.0 * pad_x
    };
    // Les deux champs, dans l'ordre choisi ; chacun sur deux lignes au plus.
    let mut blocks = Vec::new();
    let fields = [(&text.title, &style.title), (&text.subtitle, &style.subtitle)];
    let order: [usize; 2] = if style.subtitle_first { [1, 0] } else { [0, 1] };
    for i in order {
        let (value, font) = fields[i];
        let value = transform(value.trim(), font);
        if value.is_empty() {
            continue;
        }
        let (family, mut size, spacing) = scaled_font(fonts, font, k);
        let mut lines;
        loop {
            let spec = FontSpec { family: &family, weight: font.weight, letter_spacing: spacing };
            lines = balanced_lines(fonts, &value, spec, size, max_inner.max(40.0));
            if lines.len() <= 2 || size <= 10.0 * k {
                break;
            }
            size -= 1.0;
        }
        blocks.push((font, family, size, spacing, lines));
    }
    // Les dimensions du texte.
    let gap = (8.0 * k).round();
    let mut text_w: f32 = 0.0;
    let mut text_h = 0.0;
    for (n, (font, family, size, spacing, lines)) in blocks.iter().enumerate() {
        let m = fonts.qt_metrics(family, font.weight, *size);
        for l in lines {
            text_w = text_w.max(fonts.qt_advance(l, family, font.weight, *size, *spacing));
        }
        text_h += m.height as f32 + m.line_spacing as f32 * font.line_height.max(1.0) * (lines.len() as f32 - 1.0);
        if n + 1 < blocks.len() {
            text_h += gap;
        }
    }
    let box_w = if style.width > 0.0 { max_inner + 2.0 * pad_x } else { text_w + 2.0 * pad_x };
    let accent_w = style.accent.filter(|a| a.side == Side::Left).map_or(0.0, |a| a.thickness * k);
    let box_w = box_w + accent_w;
    let box_h = text_h + 2.0 * pad_y;
    let (fx, fy) = style.anchor.factors();
    let x = safe_x + (width - 2.0 * safe_x - box_w) * fx + style.offset.0 * k;
    let y = safe_y + (height - 2.0 * safe_y - box_h) * fy + style.offset.1 * k;
    let rect = [x, y, box_w, box_h];
    graphic.rect = rect;
    graphic.backing = fill_items(style.fill, rect, style.radius * k);
    if let Some(accent) = &style.accent {
        graphic.backing.push(accent_item(accent, rect, k));
    }
    let (tx, anchor) = match style.align {
        Align::Left => (x + accent_w + pad_x, TextAnchor::Start),
        Align::Center => (x + accent_w + (box_w - accent_w) / 2.0, TextAnchor::Middle),
        Align::Right => (x + box_w - pad_x, TextAnchor::End),
    };
    let mut top = y + pad_y;
    for (font, family, size, spacing, lines) in &blocks {
        let m = fonts.qt_metrics(family, font.weight, *size);
        let step = m.line_spacing as f32 * font.line_height.max(1.0);
        for (i, l) in lines.iter().enumerate() {
            let baseline = top + m.ascent as f32 + i as f32 * step;
            graphic.lines.push(line(fonts, l, family, font, *size, *spacing, tx, anchor, baseline, k));
        }
        top += m.height as f32 + step * (lines.len() as f32 - 1.0) + gap;
    }
    if style.opacity < 1.0 {
        let opacity = style.opacity.clamp(0.0, 1.0);
        let all = graphic.items();
        graphic.backing = vec![Item::Group(Group { opacity, ..Group::plain(all) })];
        graphic.lines.clear();
    }
    graphic
}

/// Le sous-titre d'un slide : **tout son texte**, comme les autres sorties (demande du 12 novembre
/// 2026 : le texte n'est plus coupé en morceaux qu'on fait avancer). `layout_subtitle` ajoute des
/// lignes, puis réduit la taille, pour qu'il tienne en entier.
pub fn subtitle_chunks(_fonts: &mut Fonts, text: &str, style: &SubtitleStyle) -> Vec<String> {
    let text = po_text::py::strip(text);
    if text.is_empty() {
        return Vec::new();
    }
    vec![po_text::words(&transform(text, &style.font)).join(" ")]
}

/// Les marges intérieures d'un sous-titre (horizontale, verticale) à la taille `size` : elles
/// suivent le texte, pour qu'un grand sous-titre garde une boîte aussi aérée qu'un petit.
fn subtitle_pad(look: SubtitleLook, size: f32) -> (f32, f32) {
    match look {
        SubtitleLook::Translucent => (0.8 * size, 0.38 * size),
        SubtitleLook::BoxPerLine => (0.36 * size, 0.12 * size),
        SubtitleLook::Bar => (0.0, 0.42 * size),
        SubtitleLook::Transparent | SubtitleLook::Outline => (0.0, 0.0),
    }
}

/// Un sous-titre sur un écran `width` × `height`, en lignes équilibrées. Jusqu'à `style.max_lines`
/// lignes il garde sa taille (ou presque) ; un texte plus long prend plus de lignes, et la taille
/// baisse seulement s'il ne tient pas dans sa zone (la moitié de l'écran, l'écran entier au centre).
pub fn layout_subtitle(fonts: &mut Fonts, text: &str, style: &SubtitleStyle, width: f32, height: f32) -> Graphic {
    layout_subtitle_with_reference(fonts, text, "", style, width, height)
}

/// L'écart entre le texte et la référence, à la taille `size` : plus large avec un filet entre
/// les deux.
fn reference_gap(style: &SubtitleStyle, size: f32) -> f32 {
    if subtitle_rule(style) { 0.6 * size } else { 0.3 * size }
}

/// Un filet court entre le texte et la référence (la bande pleine largeur a le sien en haut ; les
/// boîtes par ligne n'en ont pas).
fn subtitle_rule(style: &SubtitleStyle) -> bool {
    style.accent.is_some() && !matches!(style.look, SubtitleLook::Bar | SubtitleLook::BoxPerLine)
}

/// [`layout_subtitle`], avec la **référence** du slide (« Jean 3:16 », « 47-0412 · E-12 ») en
/// petit sous le texte (demande du 12 novembre 2026). Vide : pas de ligne.
///
/// L'alignement range le texte et sa boîte à gauche, au centre ou à droite de la largeur utile ;
/// la référence prend sa couleur (l'or des modèles à boîte), et un filet peut la séparer du texte.
pub fn layout_subtitle_with_reference(
    fonts: &mut Fonts,
    text: &str,
    reference: &str,
    style: &SubtitleStyle,
    width: f32,
    height: f32,
) -> Graphic {
    let mut graphic = Graphic { width, height, ..Graphic::default() };
    let text = transform(po_text::py::strip(text), &style.font);
    if text.is_empty() {
        return graphic;
    }
    let reference = po_text::py::strip(reference).to_string();
    let boxes = style.look == SubtitleLook::BoxPerLine;
    let k = height / 1080.0;
    let ref_scale = style.reference_scale.clamp(0.3, 1.0);
    let (family, mut size, spacing) = scaled_font(fonts, &style.font, k);
    // La zone utile : centrée dans l'écran, `style.width` % de sa largeur.
    let zone_w = (width * style.width.clamp(20.0, 100.0) / 100.0).min(width);
    let zone_x = (width - zone_w) / 2.0;
    let max_lines = style.max_lines.clamp(1, 3);
    let margin = height * style.margin / 100.0;
    let room = match style.position {
        BandPosition::Center => height - 2.0 * margin,
        BandPosition::Top | BandPosition::Bottom => height / 2.0 - margin,
    };
    // Au-delà de `max_lines` lignes, la taille ne descend pas sous 72 % de la sienne tant que le
    // texte tient dans sa zone : on préfère des lignes de plus à des lettres trop petites.
    let soft_floor = (size * 0.72).max(12.0 * k);
    // La hauteur de la ligne de référence (et de son écart avec le texte) à la taille `size`.
    let reference_h = |fonts: &mut Fonts, size: f32| -> f32 {
        if reference.is_empty() {
            return 0.0;
        }
        let pad_y = subtitle_pad(style.look, size).1;
        let r = fonts.qt_metrics(&family, style.font.weight, (size * ref_scale).max(10.0 * k));
        r.height as f32 + reference_gap(style, size) + if boxes { 2.0 * pad_y } else { 0.0 }
    };
    let mut lines;
    loop {
        let (pad_x, pad_y) = subtitle_pad(style.look, size);
        let spec = FontSpec { family: &family, weight: style.font.weight, letter_spacing: spacing };
        lines = balanced_lines(fonts, &text, spec, size, (zone_w - 2.0 * pad_x).max(40.0));
        let m = fonts.qt_metrics(&family, style.font.weight, size);
        let step = m.line_spacing as f32 * style.font.line_height.max(1.0);
        let block = m.height as f32 + step * (lines.len() as f32 - 1.0) + 2.0 * pad_y + reference_h(fonts, size);
        let fits = block <= room;
        if (fits && (lines.len() <= max_lines || size <= soft_floor)) || size <= 12.0 * k {
            break;
        }
        size -= 1.0;
    }
    let (pad_x, pad_y) = subtitle_pad(style.look, size);
    let m = fonts.qt_metrics(&family, style.font.weight, size);
    let step = m.line_spacing as f32 * style.font.line_height.max(1.0);
    let text_h = m.height as f32 + step * (lines.len() as f32 - 1.0);
    let block_h = text_h + 2.0 * pad_y + reference_h(fonts, size);
    let top = match style.position {
        BandPosition::Top => margin,
        BandPosition::Center => (height - block_h) / 2.0,
        BandPosition::Bottom => height - margin - block_h,
    };
    // Le point d'accroche du texte, et le bord gauche d'une boîte de largeur `w` (texte compris).
    let (tx, anchor) = match style.align {
        Align::Left => (zone_x + pad_x, TextAnchor::Start),
        Align::Center => (width / 2.0, TextAnchor::Middle),
        Align::Right => (zone_x + zone_w - pad_x, TextAnchor::End),
    };
    let box_x = |w: f32| match style.align {
        Align::Left => zone_x,
        Align::Center => width / 2.0 - w / 2.0 - pad_x,
        Align::Right => zone_x + zone_w - w - 2.0 * pad_x,
    };
    let widths: Vec<f32> =
        lines.iter().map(|l| fonts.qt_advance(l, &family, style.font.weight, size, spacing)).collect();
    // La référence : même police, plus petite, dans sa couleur, sous le texte.
    let ref_size = (size * ref_scale).max(10.0 * k);
    let ref_spacing = spacing * ref_scale;
    let rm = fonts.qt_metrics(&family, style.font.weight, ref_size);
    let ref_w = if reference.is_empty() {
        0.0
    } else {
        fonts.qt_advance(&reference, &family, style.font.weight, ref_size, ref_spacing)
    };
    let gap = reference_gap(style, size);
    let ref_top = top + pad_y + text_h + gap + if boxes { 2.0 * pad_y } else { 0.0 };
    let widest = widths.iter().copied().fold(ref_w, f32::max);
    graphic.rect = if style.look == SubtitleLook::Bar {
        [0.0, top, width, block_h]
    } else {
        [box_x(widest), top, widest + 2.0 * pad_x, block_h]
    };
    match style.look {
        SubtitleLook::Translucent => {
            let [x, y, w, h] = graphic.rect;
            let radius = (0.24 * size).max(4.0 * k);
            graphic.backing.push(Item::Rect { x, y, w, h, radius, color: style.box_color });
        }
        SubtitleLook::Bar => {
            let [x, y, w, h] = graphic.rect;
            graphic.backing.push(Item::Rect { x, y, w, h, radius: 0.0, color: style.box_color });
            if let Some(color) = style.accent {
                let t = (0.07 * size).max(2.0 * k).round();
                graphic.backing.push(Item::Rect { x, y, w, h: t, radius: 0.0, color });
            }
        }
        SubtitleLook::BoxPerLine => {
            let radius = (0.1 * size).max(3.0 * k);
            for (i, w) in widths.iter().enumerate() {
                let y = top + i as f32 * step + (step - m.height as f32).min(0.0);
                graphic.backing.push(Item::Rect {
                    x: box_x(*w),
                    y,
                    w: w + 2.0 * pad_x,
                    h: m.height as f32 + 2.0 * pad_y,
                    radius,
                    color: style.box_color,
                });
            }
            if !reference.is_empty() {
                graphic.backing.push(Item::Rect {
                    x: box_x(ref_w),
                    y: ref_top - pad_y,
                    w: ref_w + 2.0 * pad_x,
                    h: rm.height as f32 + 2.0 * pad_y,
                    radius,
                    color: style.box_color,
                });
            }
        }
        SubtitleLook::Transparent | SubtitleLook::Outline => {}
    }
    // Le filet court entre le texte et la référence, aligné comme eux.
    if let Some(color) = style.accent.filter(|_| subtitle_rule(style) && !reference.is_empty()) {
        let (w, t) = ((1.2 * size).min(widest), (0.06 * size).max(2.0 * k).round());
        let x = match anchor {
            TextAnchor::Start => tx,
            TextAnchor::Middle => tx - w / 2.0,
            TextAnchor::End => tx - w,
        };
        let y = (top + pad_y + text_h + gap / 2.0 - t / 2.0).round();
        graphic.backing.push(Item::Rect { x, y, w, h: t, radius: t / 2.0, color });
    }
    for (i, l) in lines.iter().enumerate() {
        let baseline = top + pad_y + m.ascent as f32 + i as f32 * step;
        graphic.lines.push(line(fonts, l, &family, &style.font, size, spacing, tx, anchor, baseline, k));
    }
    if !reference.is_empty() {
        let mut font = style.font.clone();
        font.uppercase = false;
        font.color = style.reference_color();
        let baseline = ref_top + rm.ascent as f32;
        graphic.lines.push(line(fonts, &reference, &family, &font, ref_size, ref_spacing, tx, anchor, baseline, k));
    }
    graphic
}

fn vector(direction: Direction) -> (f32, f32) {
    match direction {
        Direction::Up => (0.0, -1.0),
        Direction::Down => (0.0, 1.0),
        Direction::Left => (-1.0, 0.0),
        Direction::Right => (1.0, 0.0),
    }
}

/// Le rectangle dévoilé à la part `e` (0 à 1), dans le sens `direction`.
fn revealed(rect: [f32; 4], direction: Direction, e: f32) -> [f32; 4] {
    let [x, y, w, h] = rect;
    match direction {
        Direction::Right => [x, y, w * e, h],
        Direction::Left => [x + w * (1.0 - e), y, w * e, h],
        Direction::Down => [x, y, w, h * e],
        Direction::Up => [x, y + h * (1.0 - e), w, h * e],
    }
}

/// Un habillage à un instant de son entrée (`entering`, `progress` de 0 à 1) ou de sa sortie
/// (`progress` de 0, encore entier, à 1, disparu). Rend les éléments à dessiner.
pub fn graphic_frame(graphic: &Graphic, motion: &Motion, progress: f32, entering: bool) -> Vec<Item> {
    if graphic.is_empty() {
        return Vec::new();
    }
    let p = motion.curve.apply(progress);
    let entrance = if entering { motion.enter } else { motion.exit };
    // `shown` : la part visible (1 = entier).
    let shown = if entering { p } else { 1.0 - p };
    if shown >= 0.999 {
        return graphic.items();
    }
    if shown <= 0.001 {
        return Vec::new();
    }
    let k = graphic.height / 1080.0;
    let [x, y, w, h] = graphic.rect;
    let wrap = |opacity: f32, dx: f32, dy: f32, clip: Option<[f32; 4]>, items: Vec<Item>| {
        Item::Group(Group { opacity, dx, dy, clip, ..Group::plain(items) })
    };
    match entrance {
        Entrance::None => {
            if entering {
                graphic.items()
            } else {
                Vec::new()
            }
        }
        Entrance::Fade => vec![wrap(shown, 0.0, 0.0, None, graphic.items())],
        Entrance::Slide(direction) => {
            let (vx, vy) = vector(direction);
            let distance = if vx != 0.0 { w.min(160.0 * k) } else { h.min(90.0 * k) };
            // Entrée : arrive en allant dans le sens donné ; sortie : repart dans ce sens.
            let travel = if entering { -(1.0 - shown) } else { 1.0 - shown };
            vec![wrap(shown, vx * distance * travel, vy * distance * travel, None, graphic.items())]
        }
        Entrance::Reveal(direction) => {
            let pad = 40.0 * k;
            let outer = [x - pad, y - pad, w + 2.0 * pad, h + 2.0 * pad];
            vec![wrap(1.0, 0.0, 0.0, Some(revealed(outer, direction, shown)), graphic.items())]
        }
        Entrance::WordByWord => {
            if !entering {
                return vec![wrap(shown, 0.0, 0.0, None, graphic.items())];
            }
            // La boîte en fondu sur le premier tiers, puis les mots un à un.
            let mut items = vec![wrap((shown / 0.3).min(1.0), 0.0, 0.0, None, graphic.backing.clone())];
            let total: usize = graphic.lines.iter().map(|(_, ends)| ends.len()).sum();
            let words = if shown <= 0.3 { 0.0 } else { (shown - 0.3) / 0.7 * total as f32 };
            let mut before = 0usize;
            for (text_line, ends) in &graphic.lines {
                let visible = (words - before as f32).clamp(0.0, ends.len() as f32);
                before += ends.len();
                if visible <= 0.0 {
                    continue;
                }
                let full = visible.floor() as usize;
                let left = match text_line.anchor {
                    TextAnchor::Start => text_line.x,
                    TextAnchor::Middle => text_line.x - text_line.width / 2.0,
                    TextAnchor::End => text_line.x - text_line.width,
                };
                let right = if full >= ends.len() {
                    left + text_line.width + 20.0 * k
                } else if full == 0 {
                    left
                } else {
                    ends[full - 1]
                };
                let clip = [left - 20.0 * k, y - h, right - left + 20.0 * k + 6.0 * k, 3.0 * h];
                items.push(wrap(1.0, 0.0, 0.0, Some(clip), vec![Item::Text(text_line.clone())]));
                // Le mot en cours apparaît en fondu.
                let partial = visible - full as f32;
                if full < ends.len() && partial > 0.0 {
                    let next = ends[full];
                    let clip = [right, y - h, next - right + 6.0 * k, 3.0 * h];
                    items.push(wrap(partial, 0.0, 0.0, Some(clip), vec![Item::Text(text_line.clone())]));
                }
            }
            items
        }
    }
}

/// La mire d'une sortie HDMI (F8) : des barres de couleur, un dégradé de gris, un cadre de 5 % et
/// la définition, pour régler le mélangeur ou le vidéoprojecteur.
pub fn test_pattern(width: f32, height: f32) -> crate::display::DisplayList {
    let mut list = crate::display::DisplayList::blank(width, height, Rgba::BLACK);
    let bars = [
        Rgba::rgb(192, 192, 192),
        Rgba::rgb(192, 192, 0),
        Rgba::rgb(0, 192, 192),
        Rgba::rgb(0, 192, 0),
        Rgba::rgb(192, 0, 192),
        Rgba::rgb(192, 0, 0),
        Rgba::rgb(0, 0, 192),
    ];
    let bar_w = width / bars.len() as f32;
    for (i, color) in bars.iter().enumerate() {
        list.items.push(Item::Rect {
            x: i as f32 * bar_w,
            y: 0.0,
            w: bar_w + 1.0,
            h: height * 0.67,
            radius: 0.0,
            color: *color,
        });
    }
    list.items.push(Item::LinearGradient {
        x: 0.0,
        y: height * 0.67,
        w: width,
        h: height * 0.13,
        from: [0.0, 0.0],
        to: [width, 0.0],
        stops: vec![Stop { at: 0.0, color: Rgba::BLACK }, Stop { at: 1.0, color: Rgba::WHITE }],
    });
    // Le cadre de la zone de sécurité (5 %).
    let (mx, my) = (width * 0.05, height * 0.05);
    let t = (height / 540.0).max(1.0);
    for (x, y, w, h) in [
        (mx, my, width - 2.0 * mx, t),
        (mx, height - my - t, width - 2.0 * mx, t),
        (mx, my, t, height - 2.0 * my),
        (width - mx - t, my, t, height - 2.0 * my),
    ] {
        list.items.push(Item::Rect { x, y, w, h, radius: 0.0, color: Rgba::WHITE });
    }
    let k = height / 1080.0;
    let size = (40.0 * k).round();
    let text = format!("Project-On · sortie HDMI · {} × {}", width.round(), height.round());
    list.items.push(Item::Text(TextLine {
        text,
        x: width / 2.0,
        baseline: height * 0.9,
        anchor: TextAnchor::Middle,
        size,
        family: "Inter".into(),
        weight: 600,
        color: Rgba::WHITE,
        width: 0.0,
        letter_spacing: 0.0,
        advance_scale: 1.0,
        shadow: None,
        outline: None,
    }));
    list
}

/// La couleur d'un fond de clé (sortie HDMI vers un mélangeur).
pub fn key_color(name: &str) -> Rgba {
    match name.trim().to_lowercase().as_str() {
        "magenta" => Rgba::rgb(255, 0, 255),
        "blue" | "bleu" => Rgba::rgb(0, 0, 255),
        _ => Rgba::rgb(0, 255, 0),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use po_design::graphics::{builtin_lower_thirds, builtin_subtitles};

    fn fonts() -> Fonts {
        Fonts::from_dirs(&[crate::bundled_fonts_dir()])
    }

    #[test]
    fn every_lower_third_stays_on_screen() {
        let mut fonts = fonts();
        let text = LowerThirdText::new("Frère Jean-Baptiste Mukendi", "Pasteur de l'assemblée de Lubumbashi");
        for (id, _, _, style) in builtin_lower_thirds() {
            for (w, h) in [(1920.0, 1080.0), (1280.0, 720.0)] {
                let g = layout_lower_third(&mut fonts, &text, &style, w, h);
                let [x, y, bw, bh] = g.rect;
                assert!(
                    x >= -0.5 && y >= -0.5 && x + bw <= w + 0.5 && y + bh <= h + 0.5,
                    "{id} hors écran : {:?}",
                    g.rect
                );
                let items = g.items();
                assert!(!items.is_empty(), "{id} vide");
                // Le titre et le sous-titre sont là, dans la boîte.
                for (l, _) in &g.lines {
                    assert!(l.baseline > y && l.baseline < y + bh + 1.0, "{id} : {} hors de la boîte", l.text);
                }
            }
        }
        let empty =
            layout_lower_third(&mut fonts, &LowerThirdText::default(), &builtin_lower_thirds()[0].3, 1920.0, 1080.0);
        assert!(empty.is_empty());
    }

    #[test]
    fn a_subtitle_shows_the_whole_text_of_the_slide() {
        let mut fonts = fonts();
        let text = "Et il arriva, comme il était en prière en un certain lieu, qu'après qu'il eut cessé, \
                    un de ses disciples lui dit : Seigneur, enseigne-nous à prier, comme aussi Jean l'a \
                    enseigné à ses disciples. Et il leur dit : Quand vous priez, dites : Père, que ton nom \
                    soit sanctifié ; que ton règne vienne.";
        for (_, _, style) in builtin_subtitles() {
            let chunks = subtitle_chunks(&mut fonts, text, &style);
            // Un seul sous-titre : tout le texte, rien ne se perd.
            assert_eq!(chunks.len(), 1, "{chunks:?}");
            let g = layout_subtitle(&mut fonts, &chunks[0], &style, 1920.0, 1080.0);
            let shown: Vec<String> = g.lines.iter().map(|(l, _)| l.text.clone()).collect();
            assert_eq!(
                po_text::words(&shown.join(" ")).join(" ").to_lowercase(),
                po_text::words(text).join(" ").to_lowercase()
            );
            assert!(g.lines.len() > style.max_lines, "un long texte prend des lignes de plus");
            assert!(g.rect[1] >= 0.0 && g.rect[1] + g.rect[3] <= 1080.0, "{:?}", g.rect);
            // Un texte court garde sa taille et ses lignes.
            let short = layout_subtitle(&mut fonts, "Que ton règne vienne", &style, 1920.0, 1080.0);
            assert_eq!(short.lines.len(), 1);
            // La référence, en petit sous le texte, dans le cadre du sous-titre.
            let with = layout_subtitle_with_reference(
                &mut fonts,
                "Que ton règne vienne",
                "Matthieu 6:10",
                &style,
                1920.0,
                1080.0,
            );
            assert_eq!(with.lines.len(), 2);
            let (text_line, reference) = (&with.lines[0].0, &with.lines[1].0);
            assert_eq!(reference.text, "Matthieu 6:10");
            assert!(reference.baseline > text_line.baseline, "sous le texte");
            assert!(reference.size < text_line.size, "plus petite");
            assert!(with.rect[1] + with.rect[3] <= 1080.0 && with.rect[3] > short.rect[3]);
        }
        assert!(subtitle_chunks(&mut fonts, "  ", &builtin_subtitles()[0].2).is_empty());
    }

    #[test]
    fn boxes_follow_the_look() {
        let mut fonts = fonts();
        let text = "Que ton règne vienne, que ta volonté soit faite sur la terre comme au ciel.";
        let looks = builtin_subtitles();
        let mut count = |i: usize| layout_subtitle(&mut fonts, text, &looks[i].2, 1920.0, 1080.0);
        let transparent = count(0);
        assert!(transparent.backing.is_empty() && transparent.lines[0].0.shadow.is_some());
        assert_eq!(count(1).backing.len(), 1, "une bande");
        let outline = count(2);
        assert!(outline.backing.is_empty() && outline.lines[0].0.outline.is_some());
        let per_line = count(3);
        assert_eq!(per_line.backing.len(), per_line.lines.len(), "une boîte par ligne");
        let bar = count(4);
        assert_eq!(bar.backing.len(), 2, "la bande et son filet");
        assert_eq!((bar.rect[0], bar.rect[2]), (0.0, 1920.0), "toute la largeur");
    }

    #[test]
    fn subtitles_follow_their_alignment_and_show_the_reference_in_its_color() {
        let mut fonts = fonts();
        let (text, reference) = ("Que ton règne vienne", "Matthieu 6:10");
        for look in SubtitleLook::ALL {
            let mut style = SubtitleStyle::new(look);
            let mut at = |align: Align| {
                style.align = align;
                layout_subtitle_with_reference(&mut fonts, text, reference, &style, 1920.0, 1080.0)
            };
            let (left, center, right) = (at(Align::Left), at(Align::Center), at(Align::Right));
            for (g, anchor) in [(&left, TextAnchor::Start), (&center, TextAnchor::Middle), (&right, TextAnchor::End)] {
                // Le texte et la référence, accrochés du même côté, au même point.
                let (first, under) = (&g.lines[0].0, &g.lines[1].0);
                assert_eq!((first.anchor, under.anchor), (anchor, anchor), "{look:?}");
                assert!((first.x - under.x).abs() < 0.01, "{look:?}");
                let [x, _, w, _] = g.rect;
                assert!(x >= -0.5 && x + w <= 1920.5, "{look:?} hors écran : {:?}", g.rect);
            }
            assert!(left.lines[0].0.x < 1920.0 * 0.25 && right.lines[0].0.x > 1920.0 * 0.75, "{look:?}");
            if look != SubtitleLook::Bar {
                assert!(left.rect[0] < center.rect[0] && center.rect[0] < right.rect[0], "{look:?}");
            }
            assert_eq!(center.lines[1].0.color, SubtitleStyle::new(look).reference_color(), "{look:?}");
        }
        // Le modèle semi-transparent : la boîte, et un filet doré entre le texte et la référence.
        let style = SubtitleStyle::new(SubtitleLook::Translucent);
        let g = layout_subtitle_with_reference(&mut fonts, text, reference, &style, 1920.0, 1080.0);
        assert_eq!(g.backing.len(), 2);
        let Item::Rect { y, color, .. } = g.backing[1] else { panic!("un filet") };
        assert_eq!(Some(color), style.accent);
        assert!(y > g.lines[0].0.baseline && y < g.lines[1].0.baseline, "entre le texte et la référence");
        // Une taille plus grande : une boîte plus grande, aussi aérée.
        let mut big = style.clone();
        big.font.size = 72.0;
        let large = layout_subtitle_with_reference(&mut fonts, text, reference, &big, 1920.0, 1080.0);
        assert!(large.rect[3] > g.rect[3] && large.lines[0].0.size > g.lines[0].0.size);
    }

    #[test]
    fn entrances_and_exits() {
        let mut fonts = fonts();
        let text = LowerThirdText::new("Le thème du jour", "Série : la foi");
        for (id, _, _, style) in builtin_lower_thirds() {
            let g = layout_lower_third(&mut fonts, &text, &style, 1920.0, 1080.0);
            let full = g.items();
            // Fin de l'entrée : entier ; début : rien ; fin de la sortie : rien.
            assert_eq!(graphic_frame(&g, &style.motion, 1.0, true), full, "{id}");
            assert!(graphic_frame(&g, &style.motion, 0.0, true).is_empty(), "{id}");
            assert_eq!(graphic_frame(&g, &style.motion, 0.0, false), full, "{id}");
            assert!(graphic_frame(&g, &style.motion, 1.0, false).is_empty(), "{id}");
            // À mi-chemin : quelque chose, mais pas tout.
            let mid = graphic_frame(&g, &style.motion, 0.5, true);
            assert!(!mid.is_empty() && mid != full, "{id}");
        }
        // Mot à mot : le nombre de mots visibles croît.
        let style = builtin_lower_thirds().into_iter().find(|(id, ..)| *id == "lt-anime").unwrap().3;
        let g = layout_lower_third(&mut fonts, &text, &style, 1920.0, 1080.0);
        // Les groupes de texte visibles : aucun tant que la boîte apparaît, puis de plus en plus.
        let words = |p: f32| {
            graphic_frame(&g, &style.motion, p, true)
                .iter()
                .filter(|i| matches!(i, Item::Group(group) if group.items.iter().any(|x| matches!(x, Item::Text(_)))))
                .count()
        };
        assert_eq!(words(0.1), 0);
        assert!(words(0.2) > 0 && words(0.2) <= words(0.4), "{} {}", words(0.2), words(0.4));
    }
}
