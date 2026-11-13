//! Les réglages de l'habillage (Réglages → Habillage) : la police, la taille, l'alignement et les
//! couleurs des **sous-titres**, de la **diffusion** (Web, NDI, HDMI) et du **lower third**.
//!
//! Ils s'appliquent par-dessus le design choisi dans la page Designs : le design garde sa forme
//! (boîte, filet, animation, largeur), ces réglages remplacent son texte et ses couleurs. Un
//! habillage non personnalisé garde le design tel quel. Ils sont rangés dans `settings.json`, section
//! `refonte_3`, clé `habillage` (la 2.x les ignore).

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::graphics::{Anchor, Fill, LowerThirdStyle, SubtitleLook, SubtitleStyle};
use crate::{Align, Band, BandPosition, Rgba, RoomDesign, VerticalPosition};

/// Le réglage d'un habillage. Les tailles sont pour un écran de 1080 lignes.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Tuning {
    /// Personnalisé ; sinon le design choisi s'applique tel quel.
    pub enabled: bool,
    pub family: String,
    pub weight: u16,
    pub size: f32,
    pub uppercase: bool,
    pub color: Rgba,
    /// La police du second champ du lower third ; vide : la même que le titre.
    pub second_family: String,
    /// La référence (sous-titres, diffusion) ou le second champ (lower third).
    pub second_size: f32,
    pub second_color: Rgba,
    /// La boîte, la bande ; aucune : le texte seul (diffusion, lower third).
    pub background: Option<Rgba>,
    pub align: Align,
    pub position: BandPosition,
    /// L'apparence des sous-titres (sans effet sur les autres habillages).
    pub look: SubtitleLook,
}

impl Default for Tuning {
    fn default() -> Self {
        let style = SubtitleStyle::new(SubtitleLook::Translucent);
        Tuning { enabled: false, ..Tuning::of_subtitles(&style) }
    }
}

/// Les bornes d'une taille réglée (celles de la projection : un design de slide peut servir à la
/// diffusion).
pub const SIZE_RANGE: std::ops::RangeInclusive<f32> = 8.0..=320.0;

fn size(value: f32) -> f32 {
    if value.is_finite() { value.clamp(*SIZE_RANGE.start(), *SIZE_RANGE.end()) } else { 48.0 }
}

fn weight(value: u16) -> u16 {
    value.clamp(100, 900)
}

fn family(value: &str, fallback: &str) -> String {
    match value.trim() {
        "" => fallback.to_string(),
        f => f.to_string(),
    }
}

fn vertical(position: BandPosition) -> VerticalPosition {
    match position {
        BandPosition::Top => VerticalPosition::Top,
        BandPosition::Center => VerticalPosition::Center,
        BandPosition::Bottom => VerticalPosition::Bottom,
    }
}

/// L'ancrage d'un lower third rangé ainsi : côté `align`, hauteur `position`.
pub fn anchor_of(align: Align, position: BandPosition) -> Anchor {
    match (position, align) {
        (BandPosition::Top, Align::Left) => Anchor::TopLeft,
        (BandPosition::Top, Align::Center) => Anchor::Top,
        (BandPosition::Top, Align::Right) => Anchor::TopRight,
        (BandPosition::Center, Align::Left) => Anchor::Left,
        (BandPosition::Center, Align::Center) => Anchor::Center,
        (BandPosition::Center, Align::Right) => Anchor::Right,
        (BandPosition::Bottom, Align::Left) => Anchor::BottomLeft,
        (BandPosition::Bottom, Align::Center) => Anchor::Bottom,
        (BandPosition::Bottom, Align::Right) => Anchor::BottomRight,
    }
}

fn position_of(anchor: Anchor) -> BandPosition {
    match anchor.factors().1 {
        y if y < 0.25 => BandPosition::Top,
        y if y > 0.75 => BandPosition::Bottom,
        _ => BandPosition::Center,
    }
}

impl Tuning {
    /// Les valeurs d'un style de sous-titres (pour partir du design en personnalisant).
    pub fn of_subtitles(style: &SubtitleStyle) -> Tuning {
        Tuning {
            enabled: true,
            family: style.font.family.clone(),
            weight: style.font.weight,
            size: style.font.size,
            uppercase: style.font.uppercase,
            color: style.font.color,
            second_family: String::new(),
            second_size: (style.font.size * style.reference_scale).round(),
            second_color: style.reference_color(),
            background: Some(style.box_color),
            align: style.align,
            position: style.position,
            look: style.look,
        }
    }

    /// Les valeurs d'un bandeau de diffusion.
    pub fn of_band(band: &Band) -> Tuning {
        Tuning {
            enabled: true,
            family: band.family.clone(),
            weight: band.weight,
            size: band.size,
            uppercase: band.uppercase,
            color: band.text_color,
            second_family: String::new(),
            second_size: band.ref_size,
            second_color: band.ref_color,
            background: band.background,
            align: band.align,
            position: band.position,
            look: SubtitleLook::Translucent,
        }
    }

    /// Les valeurs d'un design de slide (servant à la diffusion).
    pub fn of_room(design: &RoomDesign) -> Tuning {
        Tuning {
            enabled: true,
            family: design.text.family.clone(),
            weight: design.text.weight,
            size: design.text.size,
            uppercase: design.text.uppercase,
            color: design.text.color,
            second_family: String::new(),
            second_size: design.reference.size,
            second_color: design.reference.color,
            background: None,
            align: design.align,
            position: match design.position {
                VerticalPosition::Top => BandPosition::Top,
                VerticalPosition::Center => BandPosition::Center,
                VerticalPosition::Bottom => BandPosition::Bottom,
            },
            look: SubtitleLook::Translucent,
        }
    }

    /// Les valeurs d'un lower third.
    pub fn of_lower_third(style: &LowerThirdStyle) -> Tuning {
        Tuning {
            enabled: true,
            family: style.title.family.clone(),
            weight: style.title.weight,
            size: style.title.size,
            uppercase: style.title.uppercase,
            color: style.title.color,
            second_family: style.subtitle.family.clone(),
            second_size: style.subtitle.size,
            second_color: style.subtitle.color,
            background: match style.fill {
                Fill::None => None,
                Fill::Solid { color } => Some(color),
                Fill::Gradient { from, .. } => Some(from),
            },
            align: style.align,
            position: position_of(style.anchor),
            look: SubtitleLook::Translucent,
        }
    }

    /// Les sous-titres réglés. L'apparence choisie reprend son ombre ou son contour ; la couleur de
    /// la boîte reste celle réglée.
    pub fn apply_subtitles(&self, style: &SubtitleStyle) -> SubtitleStyle {
        let mut s = style.clone();
        if !self.enabled {
            return s;
        }
        if s.look != self.look {
            s.set_look(self.look);
        }
        s.font.family = family(&self.family, &style.font.family);
        s.font.weight = weight(self.weight);
        s.font.size = size(self.size);
        s.font.uppercase = self.uppercase;
        s.font.color = self.color;
        s.reference_scale = (size(self.second_size) / s.font.size).clamp(0.3, 1.0);
        s.reference_color = Some(self.second_color);
        if let Some(color) = self.background {
            s.box_color = color;
        }
        s.align = self.align;
        s.position = self.position;
        s
    }

    /// Le bandeau de diffusion réglé : le texte, la référence, la bande, et sa place (l'alignement
    /// range la bande et le texte du même côté).
    pub fn apply_band(&self, band: &Band) -> Band {
        let mut b = band.clone();
        if !self.enabled {
            return b;
        }
        b.family = family(&self.family, &band.family);
        b.weight = weight(self.weight);
        b.size = size(self.size);
        b.min_size = b.min_size.min(b.size);
        b.uppercase = self.uppercase;
        b.text_color = self.color;
        // Le filet suivait la couleur de la référence : il la suit encore.
        if b.accent == Some(b.ref_color) {
            b.accent = Some(self.second_color);
        }
        b.ref_size = size(self.second_size);
        b.ref_color = self.second_color;
        b.background = self.background;
        b.align = self.align;
        b.band_align = self.align;
        b.position = self.position;
        b
    }

    /// Un design de slide servant à la diffusion, réglé (son fond n'y paraît pas).
    pub fn apply_room(&self, design: &RoomDesign) -> RoomDesign {
        let mut d = design.clone();
        if !self.enabled {
            return d;
        }
        d.text.family = family(&self.family, &design.text.family);
        d.text.weight = weight(self.weight);
        d.text.size = size(self.size);
        d.text.min_size = d.text.min_size.min(d.text.size);
        d.text.uppercase = self.uppercase;
        d.text.color = self.color;
        d.reference.size = size(self.second_size);
        d.reference.color = self.second_color;
        d.align = self.align;
        d.position = vertical(self.position);
        d
    }

    /// Le lower third réglé : le titre, le second champ, la boîte, et sa place (l'alignement le
    /// range de ce côté de l'écran, la position en haut, au milieu ou en bas).
    pub fn apply_lower_third(&self, style: &LowerThirdStyle) -> LowerThirdStyle {
        let mut s = style.clone();
        if !self.enabled {
            return s;
        }
        s.title.family = family(&self.family, &style.title.family);
        s.title.weight = weight(self.weight);
        s.title.size = size(self.size);
        s.title.uppercase = self.uppercase;
        s.title.color = self.color;
        s.subtitle.family = family(&self.second_family, &s.title.family);
        s.subtitle.size = size(self.second_size);
        s.subtitle.color = self.second_color;
        s.fill = match (style.fill, self.background) {
            (_, None) => Fill::None,
            (Fill::Gradient { to, .. }, Some(from)) => Fill::Gradient { from, to },
            (_, Some(color)) => Fill::Solid { color },
        };
        s.align = self.align;
        s.anchor = anchor_of(self.align, self.position);
        s
    }
}

/// Les trois habillages réglés.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Tunings {
    #[serde(rename = "sous_titres")]
    pub subtitles: Tuning,
    #[serde(rename = "diffusion")]
    pub broadcast: Tuning,
    pub lower_third: Tuning,
}

/// La clé des réglages de l'habillage dans la section `refonte_3`.
pub const KEY: &str = "habillage";

impl Tunings {
    /// Les réglages lus de la section `refonte_3` ; illisibles ou absents : rien de personnalisé.
    pub fn from_section(section: Option<&Value>) -> Tunings {
        section.and_then(|s| s.get(KEY)).and_then(|v| serde_json::from_value(v.clone()).ok()).unwrap_or_default()
    }

    pub fn to_value(&self) -> Value {
        serde_json::to_value(self).unwrap_or(Value::Null)
    }

    pub fn any(&self) -> bool {
        self.subtitles.enabled || self.broadcast.enabled || self.lower_third.enabled
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::graphics::{builtin_lower_thirds, builtin_subtitles};
    use serde_json::json;

    #[test]
    fn a_tuning_taken_from_a_design_changes_nothing() {
        // Partir du design : personnaliser sans rien toucher garde le même habillage.
        for (id, _, _, style) in builtin_lower_thirds() {
            assert_eq!(Tuning::of_lower_third(&style).apply_lower_third(&style), style, "{id}");
        }
        let band = Band::default();
        assert_eq!(Tuning::of_band(&band).apply_band(&band), band);
        let room = RoomDesign::default();
        assert_eq!(Tuning::of_room(&room).apply_room(&room), room);
        for (id, _, style) in builtin_subtitles() {
            let tuned = Tuning::of_subtitles(&style).apply_subtitles(&style);
            assert_eq!(tuned.reference_color(), style.reference_color(), "{id}");
            assert_eq!((tuned.look, &tuned.font, tuned.box_color), (style.look, &style.font, style.box_color), "{id}");
            assert!((tuned.reference_scale - style.reference_scale).abs() < 0.02, "{id}");
        }
    }

    #[test]
    fn a_disabled_tuning_keeps_the_design() {
        let mut t = Tuning::of_band(&Band::default());
        t.size = 90.0;
        t.enabled = false;
        assert_eq!(t.apply_band(&Band::default()), Band::default());
        let style = SubtitleStyle::new(SubtitleLook::Outline);
        assert_eq!(Tuning::default().apply_subtitles(&style), style);
    }

    #[test]
    fn the_settings_replace_font_size_alignment_and_colors() {
        let red = Rgba::rgb(220, 30, 30);
        let mut t = Tuning::of_subtitles(&SubtitleStyle::new(SubtitleLook::Transparent));
        t.family = "Montserrat".into();
        t.size = 64.0;
        t.second_size = 32.0;
        t.color = red;
        t.align = Align::Left;
        t.position = BandPosition::Top;
        t.look = SubtitleLook::Bar;
        let s = t.apply_subtitles(&SubtitleStyle::new(SubtitleLook::Transparent));
        assert_eq!((s.font.family.as_str(), s.font.size, s.font.color), ("Montserrat", 64.0, red));
        assert_eq!((s.align, s.position, s.look), (Align::Left, BandPosition::Top, SubtitleLook::Bar));
        assert_eq!(s.reference_scale, 0.5);
        assert!(s.font.shadow.is_none(), "la bande n'a pas l'ombre du texte transparent");

        // Le lower third : rangé à droite, en haut ; sans boîte.
        let style = builtin_lower_thirds().remove(1).3;
        let mut t = Tuning::of_lower_third(&style);
        t.align = Align::Right;
        t.position = BandPosition::Top;
        t.background = None;
        t.second_family = String::new();
        let s = t.apply_lower_third(&style);
        assert_eq!((s.anchor, s.align, s.fill), (Anchor::TopRight, Align::Right, Fill::None));
        assert_eq!(s.subtitle.family, s.title.family, "second champ : même police que le titre");

        // La diffusion : la bande suit l'alignement ; une taille folle est bornée.
        let mut t = Tuning::of_band(&Band::default());
        t.align = Align::Right;
        t.size = 5000.0;
        let b = t.apply_band(&Band::default());
        assert_eq!((b.align, b.band_align, b.size), (Align::Right, Align::Right, *SIZE_RANGE.end()));
        assert!(b.min_size <= b.size);
    }

    #[test]
    fn the_tunings_are_kept_in_the_settings() {
        let mut tunings = Tunings::default();
        assert!(!tunings.any());
        tunings.lower_third = Tuning::of_lower_third(&builtin_lower_thirds().remove(0).3);
        tunings.lower_third.size = 52.0;
        let section = json!({ "low_power": false, KEY: tunings.to_value() });
        assert_eq!(Tunings::from_section(Some(&section)), tunings);
        assert!(section[KEY].get("sous_titres").is_some() && section[KEY].get("diffusion").is_some());
        // Absent, abîmé ou incomplet : rien n'est perdu ni personnalisé à tort.
        assert_eq!(Tunings::from_section(None), Tunings::default());
        assert_eq!(Tunings::from_section(Some(&json!({ KEY: "abîmé" }))), Tunings::default());
        let partial = Tunings::from_section(Some(&json!({ KEY: { "diffusion": { "enabled": true, "size": 40 } } })));
        assert!(partial.broadcast.enabled && partial.broadcast.size == 40.0 && !partial.subtitles.enabled);
    }
}
