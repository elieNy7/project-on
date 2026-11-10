//! Les couleurs : `Rgba`, et la lecture des couleurs écrites dans les réglages de la 2.x
//! (`SlideCanvas._parse_color`, puis `QColor(texte)`).

use serde::{Deserialize, Serialize};

/// Une couleur RVBA (0–255), sérialisée en tableau `[r, g, b, a]`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Rgba(pub [u8; 4]);

impl Rgba {
    pub const BLACK: Rgba = Rgba([0, 0, 0, 255]);
    pub const WHITE: Rgba = Rgba([255, 255, 255, 255]);
    pub const TRANSPARENT: Rgba = Rgba([0, 0, 0, 0]);

    pub const fn rgb(r: u8, g: u8, b: u8) -> Self {
        Rgba([r, g, b, 255])
    }

    pub const fn new(r: u8, g: u8, b: u8, a: u8) -> Self {
        Rgba([r, g, b, a])
    }

    /// La même couleur avec l'opacité `alpha` (0–1), arrondie comme `int(a * 255)` de la 2.8.
    pub fn with_alpha(self, alpha: f32) -> Self {
        let [r, g, b, _] = self.0;
        Rgba([r, g, b, (alpha.clamp(0.0, 1.0) * 255.0) as u8])
    }

    pub fn alpha(self) -> f32 {
        f32::from(self.0[3]) / 255.0
    }

    /// La luminance relative (WCAG 2), sans tenir compte de l'opacité.
    pub fn luminance(self) -> f32 {
        let channel = |c: u8| {
            let c = f32::from(c) / 255.0;
            if c <= 0.03928 { c / 12.92 } else { ((c + 0.055) / 1.055).powf(2.4) }
        };
        let [r, g, b, _] = self.0;
        0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
    }
}

/// Le rapport de contraste WCAG entre deux luminances relatives (1 à 21).
pub fn contrast_ratio(a: f32, b: f32) -> f32 {
    let (hi, lo) = if a > b { (a, b) } else { (b, a) };
    (hi + 0.05) / (lo + 0.05)
}

fn hex_digit(c: u8) -> Option<u8> {
    (c as char).to_digit(16).map(|d| d as u8)
}

/// `#rgb`, `#rrggbb`, `#aarrggbb` (l'ordre de Qt : l'opacité d'abord).
fn parse_hex(hex: &str) -> Option<Rgba> {
    let b = hex.as_bytes();
    let pair = |i: usize| Some(hex_digit(b[i])? * 16 + hex_digit(b[i + 1])?);
    match b.len() {
        3 => Some(Rgba::rgb(hex_digit(b[0])? * 17, hex_digit(b[1])? * 17, hex_digit(b[2])? * 17)),
        6 => Some(Rgba::rgb(pair(0)?, pair(2)?, pair(4)?)),
        8 => Some(Rgba::new(pair(2)?, pair(4)?, pair(6)?, pair(0)?)),
        _ => None,
    }
}

/// Les noms de couleurs que les réglages de la 2.x utilisent (QColor connaît les 147 noms SVG ;
/// ceux-ci couvrent les réglages livrés et les valeurs courantes).
fn named(name: &str) -> Option<Rgba> {
    Some(match name {
        "black" => Rgba::BLACK,
        "white" => Rgba::WHITE,
        "transparent" => Rgba::TRANSPARENT,
        "red" => Rgba::rgb(255, 0, 0),
        "green" => Rgba::rgb(0, 128, 0),
        "lime" => Rgba::rgb(0, 255, 0),
        "blue" => Rgba::rgb(0, 0, 255),
        "yellow" => Rgba::rgb(255, 255, 0),
        "magenta" | "fuchsia" => Rgba::rgb(255, 0, 255),
        "cyan" | "aqua" => Rgba::rgb(0, 255, 255),
        "gray" | "grey" => Rgba::rgb(128, 128, 128),
        "silver" => Rgba::rgb(192, 192, 192),
        "navy" => Rgba::rgb(0, 0, 128),
        "maroon" => Rgba::rgb(128, 0, 0),
        "purple" => Rgba::rgb(128, 0, 128),
        "orange" => Rgba::rgb(255, 165, 0),
        "gold" => Rgba::rgb(255, 215, 0),
        "ivory" => Rgba::rgb(255, 255, 240),
        _ => return None,
    })
}

/// Une couleur des réglages, comme la 2.8 : `rgba(r, g, b, a)` (a de 0 à 1), sinon ce que `QColor`
/// comprend (`#rrggbb`, nom). Une couleur illisible donne du noir opaque, comme `QColor()` invalide
/// rendu par Qt.
pub fn parse_color(text: &str) -> Rgba {
    let t = text.trim();
    if t.contains("rgba") {
        if let Some(inner) = t.strip_prefix("rgba(").and_then(|s| s.strip_suffix(')')) {
            let parts: Vec<&str> = inner.split(',').map(str::trim).collect();
            if let [r, g, b, a] = parts.as_slice()
                && let (Ok(r), Ok(g), Ok(b), Ok(a)) =
                    (r.parse::<u32>(), g.parse::<u32>(), b.parse::<u32>(), a.parse::<f32>())
            {
                let byte = |v: u32| v.min(255) as u8;
                return Rgba::new(byte(r), byte(g), byte(b), (a * 255.0).clamp(0.0, 255.0) as u8);
            }
        }
        return Rgba::BLACK;
    }
    if let Some(inner) = t.strip_prefix("rgb(").and_then(|s| s.strip_suffix(')')) {
        let parts: Vec<u32> = inner.split(',').filter_map(|p| p.trim().parse().ok()).collect();
        if let [r, g, b] = parts.as_slice() {
            return Rgba::rgb((*r).min(255) as u8, (*g).min(255) as u8, (*b).min(255) as u8);
        }
        return Rgba::BLACK;
    }
    if let Some(hex) = t.strip_prefix('#') {
        return parse_hex(hex).unwrap_or(Rgba::BLACK);
    }
    named(&t.to_lowercase()).unwrap_or(Rgba::BLACK)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn colors_of_the_settings() {
        assert_eq!(parse_color("rgba(255,255,255,0.92)"), Rgba::new(255, 255, 255, 234));
        assert_eq!(parse_color("rgba(255, 255, 255, 0.78)"), Rgba::new(255, 255, 255, 198));
        assert_eq!(parse_color("#0c0f14"), Rgba::rgb(12, 15, 20));
        assert_eq!(parse_color("#fff"), Rgba::WHITE);
        assert_eq!(parse_color("#80ff0000"), Rgba::new(255, 0, 0, 128));
        assert_eq!(parse_color("White"), Rgba::WHITE);
        assert_eq!(parse_color("pas une couleur"), Rgba::BLACK);
    }

    #[test]
    fn contrast() {
        assert!((contrast_ratio(Rgba::WHITE.luminance(), Rgba::BLACK.luminance()) - 21.0).abs() < 0.01);
        assert!(contrast_ratio(0.5, 0.5) < 1.01);
    }
}
