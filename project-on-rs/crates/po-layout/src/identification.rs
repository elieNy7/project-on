//! L'identification fixe de William Marrion Branham (couche 1) : « Reverend William Marrion
//! Branham », discrète, en bas des prédications, de l'Exposé et des brochures.
//!
//! Quatre styles. La couleur s'adapte à la luminosité du fond sous la zone ; un halo s'ajoute si le
//! contraste ne suffit pas (WCAG : 4,5 pour 1). Le bandeau garantit le contraste sur tout fond.

use po_design::{Identification, IdentificationStyle, Rgba, contrast_ratio};

use crate::display::{Item, TextLine, TextShadow};
use crate::fonts::Fonts;

/// Le contraste minimal visé (texte courant, WCAG AA).
pub const MIN_CONTRAST: f32 = 4.5;

const INK_LIGHT: Rgba = Rgba::rgb(255, 255, 255);
const INK_DARK: Rgba = Rgba::rgb(18, 20, 24);
const BAND: Rgba = Rgba::new(8, 10, 14, 158); // ≈ 0,62

/// Les réglages typographiques d'un style, pour un écran de 1080 lignes.
struct Look {
    family: &'static str,
    weight: u16,
    size: f32,
    uppercase: bool,
    /// L'espacement des lettres, en fraction de la taille.
    tracking: f32,
    /// L'opacité de l'encre.
    ink_alpha: f32,
}

fn look(style: IdentificationStyle) -> Look {
    match style {
        IdentificationStyle::Elegant => {
            Look { family: "Spectral", weight: 400, size: 19.0, uppercase: true, tracking: 0.20, ink_alpha: 0.86 }
        }
        IdentificationStyle::Minimal => {
            Look { family: "Lato", weight: 400, size: 20.0, uppercase: false, tracking: 0.02, ink_alpha: 0.80 }
        }
        IdentificationStyle::Band => {
            Look { family: "Lato", weight: 700, size: 16.0, uppercase: true, tracking: 0.14, ink_alpha: 0.92 }
        }
        IdentificationStyle::Transparent => {
            Look { family: "Lato", weight: 700, size: 19.0, uppercase: false, tracking: 0.03, ink_alpha: 0.94 }
        }
    }
}

/// La hauteur réservée en bas de l'écran (au-dessus de la marge de sécurité), en pixels : le texte
/// et la référence ne la traversent jamais.
pub fn reserve(height: f32) -> f32 {
    (58.0 * height / 1080.0).round()
}

/// La zone (x, y, largeur, hauteur) dont la luminosité décide de la couleur.
pub fn probe_zone(width: f32, height: f32, guard_y: f32) -> [f32; 4] {
    let k = height / 1080.0;
    let w = (760.0 * k).min(width);
    [(width - w) / 2.0, height - guard_y - reserve(height), w, reserve(height)]
}

/// L'encre composée sur le fond (son opacité laisse voir le fond).
fn over(ink: Rgba, alpha: f32, background_luminance: f32) -> f32 {
    // Approximation linéaire en luminance : suffisante pour choisir et vérifier le contraste.
    ink.luminance() * alpha + background_luminance * (1.0 - alpha)
}

/// Les éléments de l'identification, posés en bas de l'écran. `luminance` est celle du fond sous la
/// zone (0 = noir, 1 = blanc).
pub fn place(
    fonts: &mut Fonts,
    identification: &Identification,
    width: f32,
    height: f32,
    guard_y: f32,
    luminance: f32,
) -> Vec<Item> {
    let k = height / 1080.0;
    let l = look(identification.style);
    let family = fonts.resolve_family(l.family);
    let size = (l.size * k).round().max(8.0);
    let text = if l.uppercase { identification.text.to_uppercase() } else { identification.text.clone() };
    let spacing = l.tracking * size;
    let text_w = fonts.qt_advance(&text, &family, l.weight, size, spacing) - spacing;
    let m = fonts.qt_metrics(&family, l.weight, size);
    let bottom = height - guard_y;
    let mut items = Vec::new();

    // L'encre (claire ou sombre) qui contraste le mieux avec ce fond.
    let contrast_of = |ink: Rgba| contrast_ratio(over(ink, l.ink_alpha, luminance), luminance);
    let (ink, halo) =
        if contrast_of(INK_DARK) > contrast_of(INK_LIGHT) { (INK_DARK, INK_LIGHT) } else { (INK_LIGHT, INK_DARK) };
    let needs_halo = contrast_of(ink) < MIN_CONTRAST;
    let mut line = TextLine {
        text,
        x: width / 2.0,
        baseline: bottom - m.descent as f32,
        anchor: crate::display::Anchor::Middle,
        size,
        family,
        weight: l.weight,
        color: ink.with_alpha(l.ink_alpha),
        width: text_w,
        letter_spacing: spacing,
        advance_scale: 1.0,
        shadow: None,
    };

    match identification.style {
        IdentificationStyle::Band => {
            let pad_x = (22.0 * k).round();
            let band_h = (size * 2.1).round();
            let band_w = text_w + 2.0 * pad_x;
            let top = bottom - band_h;
            items.push(Item::Rect {
                x: (width - band_w) / 2.0,
                y: top,
                w: band_w,
                h: band_h,
                radius: (6.0 * k).round(),
                color: BAND,
            });
            // Le texte au milieu de la bande, toujours clair : la bande garantit le contraste.
            line.color = INK_LIGHT.with_alpha(l.ink_alpha);
            line.baseline = top + (band_h - m.height as f32) / 2.0 + m.ascent as f32;
        }
        IdentificationStyle::Elegant => {
            // Le filet, fin et court, au-dessus du nom.
            let rule_w = (text_w * 0.30).min(200.0 * k).round();
            let rule_h = (1.0 * k).round().max(1.0);
            let rule_y = line.baseline - m.ascent as f32 - (10.0 * k).round();
            items.push(Item::Rect {
                x: (width - rule_w) / 2.0,
                y: rule_y,
                w: rule_w,
                h: rule_h,
                radius: 0.0,
                color: ink.with_alpha(0.55),
            });
        }
        IdentificationStyle::Minimal => {}
        IdentificationStyle::Transparent => {
            line.shadow = Some(TextShadow { color: halo.with_alpha(0.78), blur: (9.0 * k).max(2.0), dx: 0.0, dy: 0.0 });
        }
    }

    // Sur un fond moyen (photo), l'encre seule ne contraste pas assez : encre pleine et halo serré.
    if needs_halo && identification.style != IdentificationStyle::Band {
        line.color = ink;
        line.shadow = Some(TextShadow { color: halo.with_alpha(0.92), blur: (5.0 * k).max(2.0), dx: 0.0, dy: 0.0 });
    }
    items.push(Item::Text(line));
    items
}
