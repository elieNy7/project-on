//! Le bandeau sur fond transparent (diffusion pour OBS, vMix ou Pgraphics, et sous-titres) et
//! l'écran de retour de scène. Mêmes listes d'affichage que la salle : le navigateur, la fenêtre et
//! les sorties NDI / HDMI les dessinent de la même façon.

use po_design::{Align, Band, BandPosition, ReferenceLook, Rgba};

use crate::display::{Anchor, DisplayList, Item, TextLine, TextShadow};
use crate::fit::{FontSpec, wrap_lines};
use crate::fonts::Fonts;
use crate::room::Slide;

/// Des lignes posées l'une sous l'autre à partir de `top`.
#[allow(clippy::too_many_arguments)]
fn push_lines(
    list: &mut DisplayList,
    fonts: &mut Fonts,
    lines: &[String],
    family: &str,
    weight: u16,
    size: f32,
    line_height: f32,
    letter_spacing: f32,
    color: Rgba,
    x: f32,
    anchor: Anchor,
    top: f32,
    shadow: Option<TextShadow>,
) -> f32 {
    let m = fonts.qt_metrics(family, weight, size);
    let step = m.line_spacing as f32 * line_height;
    for (i, line) in lines.iter().enumerate() {
        let width = fonts.qt_advance(line, family, weight, size, letter_spacing);
        list.items.push(Item::Text(TextLine {
            text: line.clone(),
            x,
            baseline: top + m.ascent as f32 + i as f32 * step,
            anchor,
            size,
            family: family.to_string(),
            weight,
            color,
            width,
            letter_spacing,
            advance_scale: 1.0,
            shadow,
        }));
    }
    if lines.is_empty() { 0.0 } else { m.height as f32 + step * (lines.len() as f32 - 1.0) }
}

/// La plus grande taille (de `size` à `floor`) où le texte tient en `max_lines` lignes de `width`.
fn fit_lines(
    fonts: &mut Fonts,
    text: &str,
    spec: FontSpec<'_>,
    width: f32,
    size: f32,
    floor: f32,
    max_lines: usize,
) -> (f32, Vec<String>) {
    let mut s = size.round().max(floor);
    loop {
        let lines = wrap_lines(fonts, text, spec, s, width);
        if lines.len() <= max_lines || s <= floor {
            return (s, lines);
        }
        s -= 1.0;
    }
}

/// Le bandeau d'un slide, sur fond transparent, pour un écran `width` × `height`.
pub fn layout_band(fonts: &mut Fonts, slide: &Slide, band: &Band, width: f32, height: f32) -> DisplayList {
    let mut list = DisplayList::blank(width, height, Rgba::TRANSPARENT);
    let k = height / 1080.0;
    let text = if band.uppercase { slide.text.to_uppercase() } else { slide.text.clone() };
    let reference = if band.reference == ReferenceLook::Hidden {
        String::new()
    } else {
        slide.reference.lines().collect::<Vec<_>>().join(" · ")
    };
    if po_text::py::strip(&text).is_empty() && reference.trim().is_empty() {
        return list;
    }
    let family = fonts.resolve_family(&band.family);
    let safe_x = width * band.safe_area / 100.0;
    let safe_y = height * band.safe_area / 100.0;
    let band_w = (width * band.max_width / 100.0).min(width - 2.0 * safe_x).max(200.0 * k);
    let (pad_x, pad_y) = (band.padding.0 * k, band.padding.1 * k);
    let inner = band_w - 2.0 * pad_x;
    let shadow = band.shadow.map(|(color, blur)| TextShadow { color, blur: blur * k, dx: 0.0, dy: (k * 2.0).round() });
    let spec = FontSpec { family: &family, weight: band.weight, letter_spacing: band.letter_spacing * k };
    let (size, lines) = fit_lines(fonts, &text, spec, inner, band.size * k, band.min_size * k, band.max_lines);

    // La référence au-dessus, puis le filet, puis le texte.
    let ref_size = (band.ref_size * k).round();
    let ref_spec = FontSpec {
        family: &family,
        weight: 500,
        letter_spacing: if band.reference == ReferenceLook::Badge { 1.5 * k } else { 0.0 },
    };
    let ref_text = if band.reference == ReferenceLook::Badge { reference.to_uppercase() } else { reference };
    let ref_lines =
        if ref_text.trim().is_empty() { Vec::new() } else { wrap_lines(fonts, &ref_text, ref_spec, ref_size, inner) };
    let ref_m = fonts.qt_metrics(&family, 500, ref_size);
    let ref_h = if ref_lines.is_empty() { 0.0 } else { ref_m.height as f32 * ref_lines.len() as f32 };
    let accent_gap = if ref_lines.is_empty() { 0.0 } else { (14.0 * k).round() };
    let accent_h = if ref_lines.is_empty() || band.accent.is_none() { 0.0 } else { (3.0 * k).round().max(2.0) };
    let text_m = fonts.qt_metrics(&family, band.weight, size);
    let step = text_m.line_spacing as f32 * band.line_height;
    let text_h = if lines.is_empty() { 0.0 } else { text_m.height as f32 + step * (lines.len() as f32 - 1.0) };
    let between = if ref_lines.is_empty() || lines.is_empty() { 0.0 } else { (12.0 * k).round() };
    let band_h = pad_y * 2.0 + ref_h + accent_gap + accent_h + between + text_h;

    let band_x = match band.band_align {
        Align::Left => safe_x,
        Align::Right => width - safe_x - band_w,
        Align::Center => (width - band_w) / 2.0,
    } + band.offset.0 * k;
    let band_y = match band.position {
        BandPosition::Top => safe_y,
        BandPosition::Center => (height - band_h) / 2.0,
        BandPosition::Bottom => height - safe_y - band_h,
    } + band.offset.1 * k;
    list.stage = [band_x, band_y, band_w, band_h];
    if let Some(color) = band.background {
        list.items.push(Item::Rect { x: band_x, y: band_y, w: band_w, h: band_h, radius: band.radius * k, color });
    }
    let (x, anchor) = match band.align {
        Align::Left => (band_x + pad_x, Anchor::Start),
        Align::Right => (band_x + band_w - pad_x, Anchor::End),
        Align::Center => (band_x + band_w / 2.0, Anchor::Middle),
    };
    let mut y = band_y + pad_y;
    if !ref_lines.is_empty() {
        push_lines(
            &mut list,
            fonts,
            &ref_lines,
            &family,
            500,
            ref_size,
            1.0,
            ref_spec.letter_spacing,
            band.ref_color,
            x,
            anchor,
            y,
            shadow,
        );
        y += ref_h + accent_gap;
        if let Some(color) = band.accent {
            let w = (inner * 0.18).clamp(80.0 * k, 280.0 * k);
            let ax = match band.align {
                Align::Left => x,
                Align::Right => x - w,
                Align::Center => x - w / 2.0,
            };
            list.items.push(Item::Rect { x: ax, y, w, h: accent_h, radius: accent_h / 2.0, color });
        }
        y += accent_h + between;
    }
    push_lines(
        &mut list,
        fonts,
        &lines,
        &family,
        band.weight,
        size,
        band.line_height,
        band.letter_spacing * k,
        band.text_color,
        x,
        anchor,
        y,
        shadow,
    );
    list
}

/// L'écran de retour de scène : le slide au direct en grand, le suivant en dessous, l'heure et,
/// pendant le culte, la section en cours. Pour les chanteurs et le prédicateur.
pub fn layout_stage(
    fonts: &mut Fonts,
    current: &Slide,
    next: Option<&Slide>,
    clock: &str,
    status: &str,
    hidden: bool,
    width: f32,
    height: f32,
) -> DisplayList {
    let mut list = DisplayList::blank(width, height, Rgba::rgb(8, 10, 14));
    let k = height / 1080.0;
    let margin = (48.0 * k).round();
    let family = fonts.resolve_family("Inter");
    let inner = width - 2.0 * margin;
    let muted = Rgba::rgb(0x93, 0xa3, 0xad);
    let accent = Rgba::rgb(0xf2, 0x8c, 0x45);
    // L'en-tête : la référence à gauche, l'heure à droite, la section en cours au milieu.
    let head = (40.0 * k).round();
    let head_m = fonts.qt_metrics(&family, 600, head);
    let baseline = margin + head_m.ascent as f32;
    let push = |list: &mut DisplayList,
                fonts: &mut Fonts,
                text: &str,
                x: f32,
                anchor: Anchor,
                size: f32,
                color: Rgba,
                weight: u16| {
        let width = fonts.qt_advance(text, &family, weight, size, 0.0);
        list.items.push(Item::Text(TextLine {
            text: text.to_string(),
            x,
            baseline,
            anchor,
            size,
            family: family.clone(),
            weight,
            color,
            width,
            letter_spacing: 0.0,
            advance_scale: 1.0,
            shadow: None,
        }));
    };
    push(&mut list, fonts, clock, width - margin, Anchor::End, head, Rgba::WHITE, 700);
    let reference = current.reference.lines().collect::<Vec<_>>().join(" · ");
    if !reference.is_empty() {
        push(&mut list, fonts, &reference, margin, Anchor::Start, (head * 0.8).round(), accent, 600);
    }
    if !status.is_empty() {
        push(&mut list, fonts, status, width / 2.0, Anchor::Middle, (head * 0.7).round(), muted, 500);
    }
    if hidden {
        let y = margin + head_m.height as f32 + 8.0 * k;
        list.items.push(Item::Rect {
            x: margin,
            y,
            w: 260.0 * k,
            h: 36.0 * k,
            radius: 6.0 * k,
            color: Rgba::new(239, 79, 79, 220),
        });
        let size = (22.0 * k).round();
        let m = fonts.qt_metrics(&family, 700, size);
        list.items.push(Item::Text(TextLine {
            text: "TEXTE MASQUÉ".into(),
            x: margin + 130.0 * k,
            baseline: y + (36.0 * k - m.height as f32) / 2.0 + m.ascent as f32,
            anchor: Anchor::Middle,
            size,
            family: family.clone(),
            weight: 700,
            color: Rgba::WHITE,
            width: fonts.qt_advance("TEXTE MASQUÉ", &family, 700, size, 0.0),
            letter_spacing: 0.0,
            advance_scale: 1.0,
            shadow: None,
        }));
    }
    // Le slide au direct : 60 % de la hauteur.
    let top = margin + head_m.height as f32 + 56.0 * k;
    let current_h = height * 0.58;
    let spec = FontSpec { family: &family, weight: 600, letter_spacing: 0.0 };
    let (size, lines) = fit_block(fonts, &current.text, spec, inner, current_h, 96.0 * k, 26.0 * k);
    push_lines(&mut list, fonts, &lines, &family, 600, size, 1.12, 0.0, Rgba::WHITE, margin, Anchor::Start, top, None);
    // Le suivant, en dessous d'un trait.
    let rule_y = top + current_h + 16.0 * k;
    list.items.push(Item::Rect {
        x: margin,
        y: rule_y,
        w: inner,
        h: (2.0 * k).max(1.0),
        radius: 0.0,
        color: Rgba::new(255, 255, 255, 40),
    });
    let label = (24.0 * k).round();
    let label_m = fonts.qt_metrics(&family, 700, label);
    let next_top = rule_y + 20.0 * k;
    push_lines(
        &mut list,
        fonts,
        &["SUIVANT".to_string()],
        &family,
        700,
        label,
        1.0,
        2.0 * k,
        muted,
        margin,
        Anchor::Start,
        next_top,
        None,
    );
    if let Some(next) = next {
        let body_top = next_top + label_m.height as f32 + 10.0 * k;
        let room = (height - margin - body_top).max(40.0 * k);
        let reference = next.reference.lines().collect::<Vec<_>>().join(" · ");
        let next_text = if reference.is_empty() {
            next.text.clone()
        } else {
            format!("{reference} — {}", next.text.replace('\n', " "))
        };
        let (size, lines) = fit_block(fonts, &next_text, spec, inner, room, 44.0 * k, 20.0 * k);
        push_lines(
            &mut list,
            fonts,
            &lines,
            &family,
            500,
            size,
            1.1,
            0.0,
            muted,
            margin,
            Anchor::Start,
            body_top,
            None,
        );
    }
    list.stage = [margin, top, inner, current_h];
    list
}

/// La plus grande taille (de `ceiling` à `floor`) où le texte tient dans `width` × `height`.
fn fit_block(
    fonts: &mut Fonts,
    text: &str,
    spec: FontSpec<'_>,
    width: f32,
    height: f32,
    ceiling: f32,
    floor: f32,
) -> (f32, Vec<String>) {
    let mut s = ceiling.round().max(floor);
    loop {
        let lines = wrap_lines(fonts, text, spec, s, width);
        let m = fonts.qt_metrics(spec.family, spec.weight, s);
        let h = m.height as f32 + m.line_spacing as f32 * 1.12 * (lines.len().max(1) as f32 - 1.0);
        if h <= height || s <= floor {
            return (s, lines);
        }
        s -= 2.0;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use po_design::SlideSource;

    fn fonts() -> Fonts {
        Fonts::from_dirs(&[crate::bundled_fonts_dir()])
    }

    #[test]
    fn the_band_fits_its_lines_inside_the_band_on_a_transparent_screen() {
        let mut fonts = fonts();
        let slide = Slide::new(
            "Car Dieu a tant aimé le monde qu'il a donné son Fils unique, afin que quiconque croit en lui ne périsse point, mais qu'il ait la vie éternelle.",
            "Jean 3:16",
            SlideSource::Bible,
        );
        for (w, h) in [(1920.0, 1080.0), (1280.0, 720.0), (3840.0, 2160.0)] {
            let list = layout_band(&mut fonts, &slide, &Band::default(), w, h);
            assert_eq!(list.background.alpha(), 0.0, "fond transparent");
            let [x, y, bw, bh] = list.stage;
            assert!(x >= 0.0 && y >= 0.0 && x + bw <= w && y + bh <= h);
            let texts: Vec<_> = list.text_lines().collect();
            assert_eq!(texts[0].text, "JEAN 3:16", "la référence en tête, en capitales");
            assert!(texts.len() - 1 <= 3, "au plus 3 lignes");
            for t in &texts {
                assert!(t.baseline > y && t.baseline < y + bh, "{} hors de la bande", t.text);
                assert!(t.width <= bw, "{} trop large", t.text);
            }
        }
        // Rien au direct : rien à l'écran.
        let empty = layout_band(&mut fonts, &Slide::new("", "", SlideSource::Custom), &Band::default(), 1920.0, 1080.0);
        assert!(empty.items.is_empty());
    }

    #[test]
    fn the_stage_shows_the_live_slide_the_next_one_and_the_time() {
        let mut fonts = fonts();
        let current = Slide::new("La foi est une ferme assurance.", "Hébreux 11:1", SlideSource::Bible);
        let next = Slide::new("C'est par la foi qu'Abraham obéit.", "Hébreux 11:8", SlideSource::Bible);
        let list = layout_stage(
            &mut fonts,
            &current,
            Some(&next),
            "10:42",
            "Prédication · 12:00 restantes",
            true,
            1920.0,
            1080.0,
        );
        let all: Vec<String> = list.text_lines().map(|l| l.text.clone()).collect();
        let joined = all.join(" | ");
        for wanted in ["10:42", "Hébreux 11:1", "SUIVANT", "TEXTE MASQUÉ", "Prédication · 12:00 restantes"] {
            assert!(joined.contains(wanted), "{wanted} absent : {joined}");
        }
        assert!(joined.contains("Hébreux 11:8 — C'est par la foi"));
        for l in list.text_lines() {
            assert!(l.baseline <= 1080.0, "{} hors de l'écran", l.text);
        }
    }
}
