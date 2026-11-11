//! Le bandeau : un texte dans une bande, sur fond transparent, pour la diffusion (OBS, vMix,
//! Pgraphics) et les sous-titres. Le style vient des réglages « OBS » de la 2.x (`obs.output`),
//! ceux de la page `/obs` de la 2.8 : vos réglages actuels donnent le même bandeau.

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::{Align, Animation, AnimationKind, Direction, Rgba, parse_color};

/// La forme du bandeau.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BandLayout {
    /// Sous-titres : une bande centrée, le texte au milieu.
    Subtitle,
    /// Lower third : une bande en bas à gauche, la référence en titre.
    LowerThird,
}

/// La place verticale du bandeau.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BandPosition {
    Top,
    Center,
    Bottom,
}

/// La façon de montrer la référence.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ReferenceLook {
    /// Au-dessus du texte, espacée, soulignée d'un filet (la 2.8 : « badge »).
    Badge,
    /// Au-dessus du texte, simplement.
    Line,
    /// Pas de référence.
    Hidden,
}

/// Le style d'un bandeau.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Band {
    pub layout: BandLayout,
    pub position: BandPosition,
    /// L'alignement de la bande dans l'écran.
    pub band_align: Align,
    /// L'alignement du texte dans la bande.
    pub align: Align,
    pub family: String,
    pub weight: u16,
    /// Taille du texte pour un écran de 1080 lignes.
    pub size: f32,
    pub min_size: f32,
    pub uppercase: bool,
    pub letter_spacing: f32,
    pub line_height: f32,
    pub max_lines: usize,
    pub text_color: Rgba,
    pub reference: ReferenceLook,
    pub ref_size: f32,
    pub ref_color: Rgba,
    /// Le filet sous la référence (couleur), ou aucun.
    pub accent: Option<Rgba>,
    /// La couleur de la bande (opacité comprise), ou aucune bande.
    pub background: Option<Rgba>,
    pub radius: f32,
    /// Marges intérieures (horizontale, verticale), pour 1080 lignes.
    pub padding: (f32, f32),
    /// Largeur de la bande, en pourcentage de l'écran.
    pub max_width: f32,
    /// Zone de sécurité, en pourcentage.
    pub safe_area: f32,
    /// Décalage (x, y), pour 1080 lignes.
    pub offset: (f32, f32),
    pub shadow: Option<(Rgba, f32)>,
    pub animation: Animation,
}

impl Default for Band {
    /// Les valeurs par défaut de la sortie OBS de la 2.8.
    fn default() -> Self {
        Band {
            layout: BandLayout::Subtitle,
            position: BandPosition::Bottom,
            band_align: Align::Center,
            align: Align::Center,
            family: "Google Sans".into(),
            weight: 700,
            size: 32.0,
            min_size: 26.0,
            uppercase: true,
            letter_spacing: 2.0,
            line_height: 1.36,
            max_lines: 3,
            text_color: Rgba::WHITE,
            reference: ReferenceLook::Badge,
            ref_size: 24.0,
            ref_color: Rgba::rgb(0xe7, 0xc0, 0x7e),
            accent: Some(Rgba::rgb(0xe7, 0xc0, 0x7e)),
            background: Some(Rgba::new(10, 14, 22, 230)),
            radius: 12.0,
            padding: (37.0, 20.0),
            max_width: 75.0,
            safe_area: 5.0,
            offset: (0.0, 0.0),
            shadow: Some((Rgba::new(0, 0, 0, 115), 10.0)),
            animation: Animation { kind: AnimationKind::Slide, duration_ms: 420, direction: Direction::Up },
        }
    }
}

fn text(v: &Value, key: &str) -> Option<String> {
    v.get(key).and_then(Value::as_str).map(|s| s.trim().to_lowercase())
}

fn number(v: &Value, key: &str) -> Option<f64> {
    v.get(key).and_then(Value::as_f64)
}

fn boolean(v: &Value, key: &str) -> Option<bool> {
    v.get(key).and_then(Value::as_bool)
}

fn align(value: Option<String>, default: Align) -> Align {
    match value.as_deref() {
        Some("left") => Align::Left,
        Some("right") => Align::Right,
        Some("center") => Align::Center,
        _ => default,
    }
}

impl Band {
    /// Le bandeau des réglages « OBS » de la 2.x (`settings.json`, `obs.output`). Une valeur absente
    /// ou illisible garde celle par défaut.
    pub fn from_obs_output(output: &Value) -> Band {
        let d = Band::default();
        let layout = match text(output, "layout_mode").as_deref() {
            Some("lower_third" | "side_panel" | "focus_card") => BandLayout::LowerThird,
            _ => BandLayout::Subtitle,
        };
        let position = match text(output, "position").as_deref() {
            Some("top") => BandPosition::Top,
            Some("center") => BandPosition::Center,
            Some("bottom") => BandPosition::Bottom,
            _ => d.position,
        };
        let weight = match text(output, "font_weight").as_deref() {
            Some("bold" | "700" | "800" | "900") => 700,
            Some("600" | "semibold") => 600,
            Some("normal" | "regular" | "400") => 400,
            Some("light" | "300") => 300,
            _ => d.weight,
        };
        let background = match boolean(output, "bg_enabled") {
            Some(false) => None,
            _ => {
                let color = output.get("bg_color").and_then(Value::as_str).map(parse_color);
                let opacity = number(output, "bg_opacity").map(|o| o.clamp(0.0, 1.0) as f32);
                match (color, opacity) {
                    // La 2.8 applique l'opacité réglée à la couleur (sans la multiplier).
                    (Some(c), Some(o)) => Some(c.with_alpha(o)),
                    (Some(c), None) => Some(c),
                    (None, _) => d.background,
                }
            }
        };
        let ref_color = output.get("ref_color").and_then(Value::as_str).map(parse_color).unwrap_or(d.ref_color);
        let accent = match boolean(output, "show_accent_bar") {
            Some(false) => None,
            _ => Some(output.get("accent_color").and_then(Value::as_str).map(parse_color).unwrap_or(ref_color)),
        };
        let shadow = match boolean(output, "text_shadow") {
            Some(false) => None,
            _ => Some((
                output.get("shadow_color").and_then(Value::as_str).map(parse_color).unwrap_or(Rgba::new(0, 0, 0, 115)),
                number(output, "shadow_blur").unwrap_or(10.0).clamp(0.0, 60.0) as f32,
            )),
        };
        let reference = if boolean(output, "show_reference") == Some(false) {
            ReferenceLook::Hidden
        } else {
            match text(output, "reference_style").as_deref() {
                Some("inline" | "plain" | "text") => ReferenceLook::Line,
                _ => ReferenceLook::Badge,
            }
        };
        let animation = Animation {
            kind: if boolean(output, "animation_enabled") == Some(false) {
                AnimationKind::None
            } else {
                match text(output, "animation_type").as_deref() {
                    Some("none") => AnimationKind::None,
                    Some("fade") => AnimationKind::Fade,
                    Some("scale" | "zoom") => AnimationKind::Scale,
                    Some("reveal" | "wipe") => AnimationKind::Reveal,
                    Some("blur") => AnimationKind::Blur,
                    Some("slide") => AnimationKind::Slide,
                    _ => d.animation.kind,
                }
            },
            duration_ms: number(output, "animation_duration")
                .map_or(d.animation.duration_ms, |v| v.clamp(0.0, 3000.0) as u32),
            direction: match text(output, "animation_direction").as_deref() {
                Some("down") => Direction::Down,
                Some("left") => Direction::Left,
                Some("right") => Direction::Right,
                _ => Direction::Up,
            },
        };
        Band {
            layout,
            position,
            band_align: align(text(output, "band_align"), d.band_align),
            align: align(text(output, "align"), d.align),
            family: output
                .get("font_family")
                .and_then(Value::as_str)
                .map(str::trim)
                .filter(|s| !s.is_empty())
                .map_or(d.family, str::to_string),
            weight,
            size: number(output, "text_size").map_or(d.size, |v| v.clamp(10.0, 200.0) as f32),
            min_size: number(output, "min_text_size").map_or(d.min_size, |v| v.clamp(8.0, 200.0) as f32),
            uppercase: match text(output, "text_transform").as_deref() {
                Some("uppercase") => true,
                Some(_) => false,
                None => d.uppercase,
            },
            letter_spacing: number(output, "letter_spacing").map_or(d.letter_spacing, |v| v.clamp(-2.0, 24.0) as f32),
            line_height: number(output, "line_height").map_or(d.line_height, |v| v.clamp(0.9, 2.2) as f32),
            max_lines: number(output, "max_lines").map_or(d.max_lines, |v| v.clamp(1.0, 8.0) as usize),
            text_color: output.get("text_color").and_then(Value::as_str).map(parse_color).unwrap_or(d.text_color),
            reference,
            ref_size: number(output, "ref_size").map_or(d.ref_size, |v| v.clamp(8.0, 120.0) as f32),
            ref_color,
            accent,
            background,
            radius: number(output, "border_radius").map_or(d.radius, |v| v.clamp(0.0, 80.0) as f32),
            padding: (
                number(output, "padding_horizontal").map_or(d.padding.0, |v| v.clamp(0.0, 200.0) as f32),
                number(output, "padding_vertical").map_or(d.padding.1, |v| v.clamp(0.0, 200.0) as f32),
            ),
            max_width: number(output, "max_width").map_or(d.max_width, |v| v.clamp(20.0, 100.0) as f32),
            safe_area: number(output, "safe_area_percent").map_or(d.safe_area, |v| v.clamp(0.0, 20.0) as f32),
            offset: (
                number(output, "offset_x").unwrap_or(0.0) as f32,
                number(output, "offset_y").unwrap_or(0.0) as f32,
            ),
            shadow,
            animation,
        }
    }

    /// Les sous-titres : le même bandeau, en bas, sans référence.
    pub fn subtitles(&self) -> Band {
        Band {
            layout: BandLayout::Subtitle,
            position: BandPosition::Bottom,
            reference: ReferenceLook::Hidden,
            accent: None,
            max_lines: self.max_lines.min(2),
            ..self.clone()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn the_2x_obs_settings_give_the_band() {
        let output = json!({
            "layout_mode": "subtitle", "font_family": "Google Sans", "text_size": 32, "ref_size": 24,
            "position": "center", "band_align": "center", "show_accent_bar": true, "accent_color": "#e7c07e",
            "bg_enabled": true, "bg_color": "rgba(10, 14, 22, 0.90)", "bg_opacity": 0.9, "text_color": "#ffffff",
            "text_transform": "uppercase", "max_width": 75, "max_lines": 3, "border_radius": 12,
            "animation_type": "slide", "animation_duration": 420, "reference_style": "badge", "font_weight": "bold"
        });
        let band = Band::from_obs_output(&output);
        assert_eq!(band.position, BandPosition::Center);
        assert_eq!(band.background, Some(Rgba::new(10, 14, 22, 229)));
        assert_eq!(band.accent, Some(Rgba::rgb(0xe7, 0xc0, 0x7e)));
        assert_eq!((band.size, band.weight, band.uppercase), (32.0, 700, true));
        assert_eq!(band.animation.kind, AnimationKind::Slide);
        assert_eq!(Band::from_obs_output(&json!({})), Band::default());
        let quiet =
            Band::from_obs_output(&json!({"bg_enabled": false, "show_reference": false, "text_transform": "none"}));
        assert_eq!((quiet.background, quiet.reference, quiet.uppercase), (None, ReferenceLook::Hidden, false));
        assert_eq!(band.subtitles().reference, ReferenceLook::Hidden);
    }
}
