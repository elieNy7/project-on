//! La mise en page d'un slide de salle en plein écran, avec la géométrie de `SlideCanvas` (2.8) :
//! zone de sécurité de 5 %, référence épinglée en haut ou en bas avec son filet, texte qui remplit
//! la place restante, centré. En plus de la 2.8 : l'identification de Branham en bas des
//! prédications, et jamais de badge d'orateur.
//!
//! Les dispositions en bandeau (lower third, sous-titre, panneau, carte) deviennent des designs en
//! phase 6.

use po_design::{Align, Look, ReferencePosition, RoomDesign, SlideSource, VerticalPosition};

use crate::backdrop::backdrop;
use crate::display::{Anchor, DisplayList, Item, Stop, TextLine, TextShadow};
use crate::fit::{FontSpec, balanced_lines, fit_text_size, largest_unbroken_size, splitlines, wrap_lines};
use crate::fonts::Fonts;
use crate::identification;

/// Un slide de texte à projeter.
#[derive(Debug, Clone, PartialEq)]
pub struct Slide {
    pub text: String,
    pub reference: String,
    pub source: SlideSource,
    /// Un fond propre à ce slide (image d'un élément de playlist), à la place de celui du design.
    pub background: Option<String>,
}

impl Slide {
    pub fn new(text: impl Into<String>, reference: impl Into<String>, source: SlideSource) -> Self {
        Slide { text: text.into(), reference: reference.into(), source, background: None }
    }
}

/// La luminance moyenne (0 = noir, 1 = blanc) du fond déjà composé, dans une zone (x, y, largeur,
/// hauteur) : fournie par le moteur de rendu, elle décide de la couleur de l'identification.
pub type Probe<'a> = &'a mut dyn FnMut(&DisplayList, [f32; 4]) -> f32;

/// `round()` de Python (au pair le plus proche en cas d'égalité).
fn py_round(v: f64) -> i32 {
    v.round_ties_even() as i32
}

/// La géométrie de la 2.8 pour un écran donné.
struct Geometry {
    guard_x: i32,
    guard_y: i32,
    /// L'ombre agrandit les étiquettes : marge intérieure de chaque côté.
    pad: i32,
    available_w: i32,
    available_h: i32,
    ref_zone_h: i32,
    gap: i32,
    ref_edge_gap: i32,
    stage_top: i32,
    stage_h: i32,
}

/// Met un slide en page pour un écran de `width` × `height` pixels.
pub fn layout_room(
    fonts: &mut Fonts,
    slide: &Slide,
    design: &RoomDesign,
    width: f32,
    height: f32,
    probe: Probe<'_>,
) -> DisplayList {
    let (sw, sh) = (width.round() as i32, height.round() as i32);
    let scale = (f64::from(sh) / 1080.0).clamp(1.0, 3.0);
    let family = fonts.resolve_family(&design.text.family);
    let weight = design.text.weight;
    let uppercase = design.text.uppercase;
    let text = if uppercase { slide.text.to_uppercase() } else { slide.text.clone() };
    let reference = if uppercase { slide.reference.to_uppercase() } else { slide.reference.clone() };
    let has_text = !po_text::py::strip(&text).is_empty();
    let pinned = design.reference.show;
    let has_ref = pinned && !po_text::py::strip(&reference).is_empty();
    let ref_px = py_round(f64::from(design.reference.size) * scale).max(8);
    let ref_metrics = fonts.qt_metrics(&family, 600, ref_px as f32);
    let shadow = design.shadow.map(|s| {
        let blur = s.blur.clamp(4.0, 80.0) as i32;
        (s.color, blur)
    });
    let pad = shadow.map_or(0, |(_, blur)| (blur as f32 * 0.75) as i32 + 6);
    let show_identification =
        design.identification.enabled && slide.source.shows_identification() && (has_text || has_ref);

    // ── Géométrie (`_apply_layout_metrics`, mode plein écran) ──
    let edge = design.safe_margin.clamp(0.0, 240.0) as i32;
    let guard_x = edge.max(py_round(f64::from(sw) * 0.05));
    let guard_y = edge.max(py_round(f64::from(sh) * 0.05));
    let reserve = if show_identification { identification::reserve(sh as f32) as i32 } else { 0 };
    let stage_h = (sh - guard_y * 2 - reserve).max(240);
    let ref_zone_h = if pinned { 3 + 8 + ref_metrics.line_spacing + 2 * pad } else { 0 };
    let gap = if pinned { (f64::from(sh) * 0.03) as i32 } else { 0 };
    let ref_edge_gap = if pinned { 16.max((f64::from(sh) * 0.024) as i32) } else { 0 };
    // La 2.8 plante quand la référence est désactivée en plein écran (`available_height` jamais
    // calculée) : la 3.0 donne alors toute la scène au texte.
    let available_h = if pinned { (stage_h - ref_zone_h - gap - ref_edge_gap).max(240) } else { stage_h };
    let g = Geometry {
        guard_x,
        guard_y,
        pad,
        available_w: (sw - guard_x * 2).max(320),
        available_h,
        ref_zone_h,
        gap,
        ref_edge_gap,
        stage_top: guard_y,
        stage_h,
    };

    // Une image seule (une affiche, une photo de la playlist) : montrée en entier, sur du noir,
    // sans voile ; sinon le fond du design, ou l'image propre au slide derrière le texte.
    let (background, backdrop_items) = match slide.background.as_deref() {
        Some(path) if !has_text && !has_ref => crate::backdrop::image_alone(path, width, height),
        own => backdrop(&design.background, own, has_text || has_ref, width, height),
    };
    let mut list = DisplayList {
        width,
        height,
        background,
        stage: [g.guard_x as f32, g.guard_y as f32, g.available_w as f32, g.stage_h as f32],
        backdrop: backdrop_items,
        items: Vec::new(),
        overlay: Vec::new(),
    };

    // ── Places de la zone de texte et de la zone de référence ──
    let ref_at_top = design.reference.position == ReferencePosition::Top;
    let inner_top = g.stage_top + if pinned && ref_at_top { g.ref_edge_gap } else { 0 };
    let inner_bottom = g.stage_top + g.stage_h - if pinned && !ref_at_top { g.ref_edge_gap } else { 0 };
    let (content_y, zone_y) = if has_ref {
        if ref_at_top {
            (inner_top + g.ref_zone_h + g.gap, inner_top)
        } else {
            (inner_top, inner_top + g.available_h + g.gap)
        }
    } else {
        // Zone de référence cachée : la zone de texte (de hauteur fixe) se place dans la scène.
        let cell = inner_bottom - inner_top;
        let offset = match design.position {
            VerticalPosition::Top => 0,
            VerticalPosition::Bottom => cell - g.available_h,
            VerticalPosition::Center => (cell - g.available_h) / 2,
        };
        (inner_top + offset, 0)
    };

    let align = if design.background.look == Look::Split { Align::Left } else { design.align };
    let (anchor, x) = match align {
        Align::Center => (Anchor::Middle, g.guard_x as f32 + g.available_w as f32 / 2.0),
        Align::Left => (Anchor::Start, (g.guard_x + g.pad) as f32),
        Align::Right => (Anchor::End, (g.guard_x + g.available_w - g.pad) as f32),
    };
    let text_shadow =
        shadow.map(|(color, blur)| TextShadow { color, blur: blur as f32, dx: 0.0, dy: (blur / 8).max(1) as f32 });

    // ── Le texte (`_render_slide_content`) ──
    if has_text {
        let spec = FontSpec { family: &family, weight, letter_spacing: design.text.letter_spacing };
        let box_w = (g.available_w - 2 * g.pad).max(320);
        let wrap_w = (box_w - (box_w as f32 * 0.02) as i32).max(300) as f32;
        let box_h = (g.available_h - 2 * g.pad).max(200);
        let target = py_round(f64::from(design.text.size) * scale).max(10);
        let floor = py_round(f64::from(design.text.min_size) * scale).max(10);
        let ceiling = py_round(f64::from(target) * 4.0);
        let line_height = design.text.line_height.clamp(0.8, 2.0);
        let (mut size, _greedy) = fit_text_size(fonts, &text, spec, wrap_w, box_h, ceiling, floor, line_height);
        let mut lines = balanced_lines(fonts, &text, spec, size as f32, wrap_w);
        let source_lines: Vec<String> =
            splitlines(po_text::py::strip(&text)).iter().map(|l| po_text::py::strip(l).to_string()).collect();
        if source_lines.len() > 1 && lines.len() > source_lines.len() {
            // Des vers coupés (cantique) : un peu plus petit, chaque vers sur sa ligne, tant que la
            // taille réglée est respectée.
            let unbroken =
                largest_unbroken_size(fonts, &source_lines, spec, wrap_w, box_h as f32, size, floor, line_height);
            if unbroken >= target.min(size) {
                size = unbroken;
                lines = source_lines;
            }
        }
        let m = fonts.qt_metrics(&family, weight, size as f32);
        let n = lines.len() as f64;
        let step = f64::from(m.line_spacing) * f64::from(line_height);
        let block = f64::from(m.height) + step * (n - 1.0);
        let extra = if (line_height - 1.0).abs() > 1e-3 && lines.len() > 1 {
            py_round((n - 1.0) * f64::from(m.line_spacing) * (f64::from(line_height) - 1.0))
        } else {
            0
        };
        let label_content_h = m.height + (lines.len() as i32 - 1).max(0) * m.line_spacing + extra;
        let label_h = label_content_h + 2 * g.pad;
        let label_top = content_y + (g.available_h - label_h) / 2;
        let content_top = f64::from(label_top + g.pad);
        let first_top = match design.position {
            VerticalPosition::Top => content_top,
            VerticalPosition::Bottom => content_top + f64::from(label_content_h) - block,
            VerticalPosition::Center => content_top + (f64::from(label_content_h) - block) / 2.0,
        };
        for (i, line) in lines.iter().enumerate() {
            let line_w = fonts.qt_advance(line, &family, weight, size as f32, design.text.letter_spacing);
            list.items.push(Item::Text(TextLine {
                text: line.clone(),
                x,
                baseline: (first_top + f64::from(m.ascent) + i as f64 * step) as f32,
                anchor,
                size: size as f32,
                family: family.clone(),
                weight,
                color: design.text.color,
                width: line_w,
                letter_spacing: design.text.letter_spacing,
                advance_scale: 1.0,
                shadow: text_shadow,
                outline: None,
            }));
        }
    }

    // ── La référence et son filet ──
    if has_ref {
        let wrap_spec = FontSpec { family: &family, weight: 600, letter_spacing: design.text.letter_spacing };
        let box_w = (g.available_w - 2 * g.pad).max(320);
        let wrap_w = (box_w - (box_w as f32 * 0.02) as i32).max(300) as f32;
        let ref_lines = wrap_lines(fonts, &reference, wrap_spec, ref_px as f32, wrap_w);
        let label_y = if ref_at_top { zone_y } else { zone_y + 11 };
        let label_content_h = f64::from(g.ref_zone_h - 11 - 2 * g.pad);
        let rm = ref_metrics;
        let block = f64::from(rm.height) + f64::from(rm.line_spacing) * (ref_lines.len() as f64 - 1.0);
        let content_top = f64::from(label_y + g.pad);
        let first_top = match design.position {
            VerticalPosition::Top => content_top,
            VerticalPosition::Bottom => content_top + label_content_h - block,
            VerticalPosition::Center => content_top + (label_content_h - block) / 2.0,
        };
        for (i, line) in ref_lines.iter().enumerate() {
            list.items.push(Item::Text(TextLine {
                text: line.clone(),
                x,
                baseline: (first_top + f64::from(rm.ascent) + i as f64 * f64::from(rm.line_spacing)) as f32,
                anchor,
                size: ref_px as f32,
                family: family.clone(),
                weight: 600,
                color: design.reference.color,
                width: fonts.qt_advance(line, &family, 600, ref_px as f32, 0.0) * 1.12,
                letter_spacing: 0.0,
                advance_scale: 1.12,
                shadow: text_shadow,
                outline: None,
            }));
        }
        let accent_w = 120.max(280.min(sw / 6));
        let accent_x = match align {
            Align::Left => g.guard_x,
            Align::Right => g.guard_x + g.available_w - accent_w,
            Align::Center => g.guard_x + (g.available_w - accent_w) / 2,
        };
        let accent_y = if ref_at_top { zone_y + g.ref_zone_h - 3 } else { zone_y };
        let color = slide.source.accent();
        let clear = color.with_alpha(0.0);
        list.items.push(Item::LinearGradient {
            x: accent_x as f32,
            y: accent_y as f32,
            w: accent_w as f32,
            h: 3.0,
            from: [accent_x as f32, 0.0],
            to: [(accent_x + accent_w) as f32, 0.0],
            stops: vec![
                Stop { at: 0.0, color: clear },
                Stop { at: 0.15, color },
                Stop { at: 0.85, color },
                Stop { at: 1.0, color: clear },
            ],
        });
    }

    // ── L'identification de Branham ──
    if show_identification {
        let zone = identification::probe_zone(width, height, g.guard_y as f32);
        let luminance = probe(&list, zone);
        list.overlay = identification::place(fonts, &design.identification, width, height, g.guard_y as f32, luminance);
    }
    list
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::bundled_fonts_dir;

    fn fonts() -> Fonts {
        Fonts::from_dirs(&[bundled_fonts_dir()])
    }

    fn dark(_: &DisplayList, _: [f32; 4]) -> f32 {
        0.02
    }

    fn design() -> RoomDesign {
        let mut d = RoomDesign::default();
        d.text.family = "Passion One".into();
        d.text.size = 45.0;
        d.reference.size = 33.0;
        d.reference.position = ReferencePosition::Top;
        d.text.uppercase = true;
        d.shadow = None;
        d
    }

    #[test]
    fn short_text_fills_the_screen() {
        let mut f = fonts();
        let list =
            layout_room(&mut f, &Slide::new("Amen", "", SlideSource::Custom), &design(), 1920.0, 1080.0, &mut dark);
        let line = list.text_lines().next().unwrap();
        assert_eq!(line.text, "AMEN");
        assert_eq!(line.size, 180.0);
    }

    #[test]
    fn long_text_and_reference_stay_in_the_safe_area() {
        let long = "Et maintenant, frère, la foi est une ferme assurance des choses qu'on espère, une \
            démonstration de celles qu'on ne voit pas. Abraham a cru Dieu, et cela lui fut imputé à justice ; il \
            appelait les choses qui n'étaient pas comme si elles étaient, parce que Dieu l'avait dit.";
        let mut f = fonts();
        for (w, h) in [(1920.0, 1080.0), (1280.0, 720.0), (3840.0, 2160.0)] {
            let slide = Slide::new(long, "47-0412 - La foi est une ferme assurance - ¶12", SlideSource::Sermon);
            let list = layout_room(&mut f, &slide, &design(), w, h, &mut dark);
            let lines: Vec<_> = list.text_lines().collect();
            assert!(lines.len() >= 3);
            for line in &lines {
                assert!(line.width <= w * 0.9 + 1.0, "{w}×{h} : ligne de {}", line.width);
                assert!(line.baseline <= h * 0.95, "{w}×{h} : sous la zone sûre");
            }
            // L'identification est là, sous le texte.
            let ident = list.overlay_lines().next().unwrap();
            let last = lines.iter().map(|l| l.baseline).fold(0.0, f32::max);
            assert!(ident.baseline > last);
            assert!(ident.text.contains("WILLIAM MARRION BRANHAM"));
        }
    }

    #[test]
    fn hymn_verses_are_not_broken() {
        let mut f = fonts();
        let stanza = "À toi la gloire, ô Ressuscité,\nÀ toi la victoire pour l'éternité !";
        let list = layout_room(
            &mut f,
            &Slide::new(stanza, "12 - À toi la gloire", SlideSource::Hymn),
            &design(),
            1920.0,
            1080.0,
            &mut dark,
        );
        let texts: Vec<&str> = list.text_lines().filter(|l| l.size > 40.0).map(|l| l.text.as_str()).collect();
        assert_eq!(texts, ["À TOI LA GLOIRE, Ô RESSUSCITÉ,", "À TOI LA VICTOIRE POUR L'ÉTERNITÉ !"]);
        assert!(list.overlay.is_empty(), "pas d'identification sur un cantique");
    }

    #[test]
    fn identification_never_touches_the_text() {
        let long = "Et maintenant, frère, la foi est une ferme assurance des choses qu'on espère, une \
            démonstration de celles qu'on ne voit pas. Abraham a cru Dieu, et cela lui fut imputé à justice. "
            .repeat(3);
        let mut f = fonts();
        for style in po_design::IdentificationStyle::ALL {
            for position in [ReferencePosition::Top, ReferencePosition::Bottom] {
                for (w, h) in [(1920.0, 1080.0), (1280.0, 720.0), (1024.0, 768.0), (3840.0, 2160.0)] {
                    let mut d = design();
                    d.identification.style = style;
                    d.reference.position = position;
                    let slide =
                        Slide::new(long.as_str(), "63-0317M - Le Dévoilement de Dieu - ¶12", SlideSource::Sermon);
                    let list = layout_room(&mut f, &slide, &d, w, h, &mut dark);
                    // Le haut de l'identification (filet, bande ou lettres).
                    let top = list
                        .overlay
                        .iter()
                        .map(|item| match item {
                            Item::Rect { y, .. } => *y,
                            Item::Text(t) => t.baseline - t.size,
                            _ => h,
                        })
                        .fold(h, f32::min);
                    let bottom = list.text_lines().map(|l| l.baseline + l.size * 0.3).fold(0.0, f32::max);
                    assert!(
                        bottom < top,
                        "{style:?} {position:?} {w}×{h} : texte jusqu'à {bottom}, identification dès {top}"
                    );
                    assert!(
                        list.overlay_lines().all(|l| l.baseline <= h * 0.95 + 1.0),
                        "{style:?} {w}×{h} : hors zone sûre"
                    );
                }
            }
        }
    }

    #[test]
    fn no_reference_setting_does_not_crash() {
        let mut f = fonts();
        let mut d = design();
        d.reference.show = false;
        let list =
            layout_room(&mut f, &Slide::new("Gloire", "Jean 3:16", SlideSource::Bible), &d, 1920.0, 1080.0, &mut dark);
        assert_eq!(list.text_lines().count(), 1);
    }
}
