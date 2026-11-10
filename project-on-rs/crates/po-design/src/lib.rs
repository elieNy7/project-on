//! Les designs de Project-On.
//!
//! Phase 2 : le **design de la salle** (le style actuel de la projection, repris des réglages de
//! la 2.x), les **animations** entre les slides et l'**identification** de William Marrion
//! Branham (couche 1). Les lower thirds, sous-titres et la bibliothèque de designs viendront en
//! phase 6, sur ce même modèle.

mod color;

use po_settings::ProjectionSettings;
use serde::{Deserialize, Serialize};

pub use color::{Rgba, contrast_ratio, parse_color};

/// L'alignement horizontal du texte.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Align {
    Left,
    Center,
    Right,
}

/// La place verticale du texte dans sa zone.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum VerticalPosition {
    Top,
    Center,
    Bottom,
}

/// Où la référence est épinglée.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ReferencePosition {
    Top,
    Bottom,
}

/// Le voile posé sur une image de fond (`slide_style` de la 2.x).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Look {
    /// Voile doux, dégradés haut et bas, vignette.
    Cinematic,
    /// Un seul voile uni.
    Clean,
    /// Dégradé latéral côté texte (texte à gauche).
    Split,
}

/// Le cadrage d'une image de fond.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ImageFit {
    /// Remplit l'écran (l'image est recadrée).
    Cover,
    /// Entière (des bandes de la couleur de fond restent visibles).
    Contain,
}

/// Le fond d'un slide de salle.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Background {
    pub color: Rgba,
    /// Un dégradé vers une seconde couleur, avec son angle en degrés (180 = de haut en bas).
    pub gradient: Option<(Rgba, f32)>,
    /// Une image posée sur la couleur.
    pub image: Option<String>,
    pub image_fit: ImageFit,
    pub look: Look,
    /// L'assombrissement de l'image (0 à 0,85).
    pub dimmer: f32,
}

/// Le style du texte projeté.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TextStyle {
    pub family: String,
    pub weight: u16,
    /// La taille réglée, en pixels pour un écran de 1080 lignes.
    pub size: f32,
    /// Le plancher de lisibilité, en pixels pour 1080 lignes.
    pub min_size: f32,
    pub uppercase: bool,
    pub color: Rgba,
    /// L'interligne (1 = celui de la police).
    pub line_height: f32,
    /// L'espace ajouté après chaque lettre, en pixels.
    pub letter_spacing: f32,
}

/// La référence épinglée (« 47-0412 - La Foi - ¶12 »).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ReferenceStyle {
    pub show: bool,
    pub position: ReferencePosition,
    /// En pixels pour 1080 lignes.
    pub size: f32,
    pub color: Rgba,
}

/// L'ombre portée du texte et de la référence.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Shadow {
    pub color: Rgba,
    /// Le flou, en pixels (4 à 80).
    pub blur: f32,
}

/// Le type de transition entre deux slides.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AnimationKind {
    None,
    Fade,
    Slide,
    Scale,
    Blur,
    Reveal,
}

/// Le sens d'un glissement ou d'un balayage.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Direction {
    Up,
    Down,
    Left,
    Right,
}

/// La transition entre deux slides.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Animation {
    pub kind: AnimationKind,
    pub duration_ms: u32,
    pub direction: Direction,
}

/// Le style de l'identification de Branham.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IdentificationStyle {
    /// Petites capitales espacées, avec un filet.
    Elegant,
    /// Texte seul, discret.
    Minimal,
    /// Sur une bande semi-transparente : lisible sur n'importe quel fond.
    Band,
    /// Texte avec un halo léger, sans fond.
    Transparent,
}

impl IdentificationStyle {
    pub const ALL: [IdentificationStyle; 4] = [Self::Elegant, Self::Minimal, Self::Band, Self::Transparent];

    pub fn label(self) -> &'static str {
        match self {
            Self::Elegant => "Typographie élégante",
            Self::Minimal => "Texte minimaliste",
            Self::Band => "Bandeau discret",
            Self::Transparent => "Identification transparente",
        }
    }
}

/// Le texte fixe de l'identification (décision du 9 novembre 2026 : « Reverend », sans accent).
pub const BRANHAM: &str = "Reverend William Marrion Branham";

/// L'identification fixe et discrète, en bas des prédications de William Marrion Branham.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Identification {
    pub enabled: bool,
    pub style: IdentificationStyle,
    pub text: String,
}

impl Default for Identification {
    fn default() -> Self {
        Self { enabled: true, style: IdentificationStyle::Elegant, text: BRANHAM.into() }
    }
}

/// D'où vient un slide : il décide de l'identification et de la couleur du filet.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case", tag = "kind")]
pub enum SlideSource {
    Bible,
    Hymn,
    /// Une prédication de William Marrion Branham (toutes celles de la base le sont).
    Sermon,
    /// L'Exposé des Sept Âges de l'Église.
    Expose,
    /// Une brochure (`TR-…`).
    Brochure,
    /// Un autre livre (`BK-…`) : les biographies notamment.
    Book,
    /// Un texte saisi, une annonce.
    Custom,
}

impl SlideSource {
    /// La source d'un paragraphe de la table `sermon`, d'après son code de date : `BK-AGES…`
    /// pour l'Exposé, `TR-…` pour les brochures, les autres `BK-…` pour les livres (dont les
    /// biographies `BK-SENT`, `BK-PVSA`), le reste pour les prédications.
    pub fn of_sermon_date(date: &str) -> Self {
        let date = date.trim();
        if date.starts_with("BK-AGES") {
            Self::Expose
        } else if date.starts_with("TR-") {
            Self::Brochure
        } else if date.starts_with("BK-") {
            Self::Book
        } else {
            Self::Sermon
        }
    }

    /// L'identification apparaît-elle ? Prédications, Exposé et brochures seulement (décision 3) ;
    /// jamais les biographies, la Bible, les cantiques ni les textes saisis.
    pub fn shows_identification(&self) -> bool {
        matches!(self, Self::Sermon | Self::Expose | Self::Brochure)
    }

    /// La couleur du filet sous la référence (la palette des sources de la 2.x).
    pub fn accent(&self) -> Rgba {
        match self {
            Self::Bible => Rgba::new(86, 214, 129, 220),
            Self::Sermon | Self::Brochure | Self::Book => Rgba::new(224, 160, 68, 220),
            Self::Hymn => Rgba::new(185, 151, 255, 220),
            Self::Expose => Rgba::new(0, 172, 193, 220),
            Self::Custom => Rgba::new(109, 180, 255, 220),
        }
    }
}

/// Le design de la salle : tout ce qui décide de l'image d'un slide de texte en plein écran.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RoomDesign {
    pub text: TextStyle,
    pub reference: ReferenceStyle,
    pub shadow: Option<Shadow>,
    pub align: Align,
    pub position: VerticalPosition,
    /// La marge réglée, en pixels ; la zone de sécurité de 5 % reste le minimum.
    pub safe_margin: f32,
    pub background: Background,
    pub animation: Animation,
    pub identification: Identification,
}

/// La graisse d'un réglage de la 2.x (`_font_weight_to_qt`).
fn weight(value: &str) -> u16 {
    match value.to_lowercase().as_str() {
        "bold" | "700" | "800" | "900" => 700,
        "600" | "semibold" | "demi" => 600,
        "light" | "300" | "200" => 300,
        _ => 400,
    }
}

impl RoomDesign {
    /// Le design de la salle tiré des réglages « Projection » de la 2.x, avec les mêmes bornes que
    /// `ProjectionSettings.to_presentation_config` et `SlideCanvas._apply_config`.
    pub fn from_projection(p: &ProjectionSettings) -> Self {
        let choice = |value: &str| value.trim().to_lowercase();
        let family = match p.font_family.trim() {
            "" => "Poppins".to_string(),
            f => f.to_string(),
        };
        let image = (p.bg_mode == "image" && !p.bg_image.trim().is_empty()).then(|| p.bg_image.clone());
        RoomDesign {
            text: TextStyle {
                family,
                weight: weight(&p.font_weight),
                size: p.text_size.clamp(10, 320) as f32,
                min_size: p.min_text_size.max(10) as f32,
                uppercase: p.uppercase,
                color: parse_color(&p.text_color),
                line_height: (p.line_height as f32).clamp(0.9, 2.2).clamp(0.8, 2.0),
                letter_spacing: p.letter_spacing.clamp(-2, 24) as f32,
            },
            reference: ReferenceStyle {
                show: p.show_reference,
                position: if choice(&p.reference_position) == "top" {
                    ReferencePosition::Top
                } else {
                    ReferencePosition::Bottom
                },
                size: p.ref_size.clamp(8, 160) as f32,
                color: parse_color(&p.ref_color),
            },
            shadow: p.text_shadow.then(|| Shadow {
                color: parse_color(&p.shadow_color),
                blur: (if p.shadow_blur == 0 { 18 } else { p.shadow_blur }).clamp(4, 80) as f32,
            }),
            align: match choice(&p.align).as_str() {
                "left" => Align::Left,
                "right" => Align::Right,
                _ => Align::Center,
            },
            position: match choice(&p.position).as_str() {
                "top" => VerticalPosition::Top,
                "bottom" => VerticalPosition::Bottom,
                _ => VerticalPosition::Center,
            },
            safe_margin: p.safe_margin.clamp(0, 240) as f32,
            background: Background {
                color: parse_color(&p.bg_color),
                gradient: p.bg_gradient_enabled.then(|| (parse_color(&p.bg_color_2), p.bg_gradient_angle as f32)),
                image,
                image_fit: if p.bg_image_fit == "contain" { ImageFit::Contain } else { ImageFit::Cover },
                look: match choice(&p.slide_style).as_str() {
                    "clean" => Look::Clean,
                    "split" => Look::Split,
                    _ => Look::Cinematic,
                },
                dimmer: (p.background_dimmer as f32).clamp(0.0, 0.85),
            },
            animation: Animation {
                kind: if !p.animation_enabled {
                    AnimationKind::None
                } else {
                    match choice(&p.animation_type).as_str() {
                        "none" => AnimationKind::None,
                        "slide" => AnimationKind::Slide,
                        "scale" => AnimationKind::Scale,
                        "blur" => AnimationKind::Blur,
                        "reveal" => AnimationKind::Reveal,
                        _ => AnimationKind::Fade,
                    }
                },
                duration_ms: p.animation_duration.max(0) as u32,
                direction: match choice(&p.animation_direction).as_str() {
                    "down" => Direction::Down,
                    "left" => Direction::Left,
                    "right" => Direction::Right,
                    _ => Direction::Up,
                },
            },
            identification: Identification::default(),
        }
    }
}

impl Default for RoomDesign {
    /// Les réglages de projection par défaut de la 2.x.
    fn default() -> Self {
        Self::from_projection(&ProjectionSettings::default())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn identification_only_on_branham_texts() {
        assert!(SlideSource::of_sermon_date("47-0412").shows_identification());
        assert!(SlideSource::of_sermon_date("BK-AGES-CH03").shows_identification());
        assert!(SlideSource::of_sermon_date("BK-AGES-SHP-CH03").shows_identification());
        assert!(SlideSource::of_sermon_date("TR-0001").shows_identification());
        assert!(!SlideSource::of_sermon_date("BK-SENT-CH01").shows_identification());
        assert!(!SlideSource::of_sermon_date("BK-PVSA-CH01").shows_identification());
        assert!(!SlideSource::Bible.shows_identification());
        assert!(!SlideSource::Hymn.shows_identification());
        assert!(!SlideSource::Custom.shows_identification());
        assert_eq!(Identification::default().text, "Reverend William Marrion Branham");
    }

    #[test]
    fn design_from_the_2x_settings() {
        let p = ProjectionSettings {
            font_family: "Passion One".into(),
            text_size: 45,
            ref_size: 33,
            uppercase: true,
            reference_position: "top".into(),
            text_color: "rgba(255,255,255,0.92)".into(),
            text_shadow: false,
            bg_mode: "image".into(),
            bg_image: "fond.png".into(),
            animation_type: "zoom".into(),
            line_height: 3.0,
            ..ProjectionSettings::default()
        };
        let d = RoomDesign::from_projection(&p);
        assert_eq!((d.text.family.as_str(), d.text.weight, d.text.size), ("Passion One", 700, 45.0));
        assert_eq!(d.reference.position, ReferencePosition::Top);
        assert_eq!(d.text.color, Rgba::new(255, 255, 255, 234));
        assert!(d.shadow.is_none());
        assert_eq!(d.background.image.as_deref(), Some("fond.png"));
        assert_eq!(d.animation.kind, AnimationKind::Fade);
        assert_eq!(d.text.line_height, 2.0);
        let json = serde_json::to_string(&d).unwrap();
        assert_eq!(serde_json::from_str::<RoomDesign>(&json).unwrap(), d);
    }
}
