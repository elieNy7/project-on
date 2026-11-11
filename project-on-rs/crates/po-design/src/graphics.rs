//! Les habillages par-dessus l'image : les **lower thirds** (nom de l'orateur, thème du sermon,
//! référence biblique…) et les **sous-titres**. Chaque style se règle entièrement : texte, boîte,
//! ligne décorative, position (9 ancrages), opacité, durée et animation d'entrée et de sortie.

use serde::{Deserialize, Serialize};

use crate::{Align, BandPosition, Direction, Rgba};

/// Les 9 ancrages d'un habillage dans l'écran (dans la zone de sécurité).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Anchor {
    TopLeft,
    Top,
    TopRight,
    Left,
    Center,
    Right,
    BottomLeft,
    Bottom,
    BottomRight,
}

impl Anchor {
    pub const ALL: [Anchor; 9] = [
        Anchor::TopLeft,
        Anchor::Top,
        Anchor::TopRight,
        Anchor::Left,
        Anchor::Center,
        Anchor::Right,
        Anchor::BottomLeft,
        Anchor::Bottom,
        Anchor::BottomRight,
    ];

    /// La position (0, ½ ou 1) en largeur et en hauteur.
    pub fn factors(self) -> (f32, f32) {
        let x = match self {
            Anchor::TopLeft | Anchor::Left | Anchor::BottomLeft => 0.0,
            Anchor::Top | Anchor::Center | Anchor::Bottom => 0.5,
            Anchor::TopRight | Anchor::Right | Anchor::BottomRight => 1.0,
        };
        let y = match self {
            Anchor::TopLeft | Anchor::Top | Anchor::TopRight => 0.0,
            Anchor::Left | Anchor::Center | Anchor::Right => 0.5,
            Anchor::BottomLeft | Anchor::Bottom | Anchor::BottomRight => 1.0,
        };
        (x, y)
    }

    pub fn label(self) -> &'static str {
        match self {
            Anchor::TopLeft => "En haut à gauche",
            Anchor::Top => "En haut",
            Anchor::TopRight => "En haut à droite",
            Anchor::Left => "À gauche",
            Anchor::Center => "Au centre",
            Anchor::Right => "À droite",
            Anchor::BottomLeft => "En bas à gauche",
            Anchor::Bottom => "En bas",
            Anchor::BottomRight => "En bas à droite",
        }
    }
}

/// Le style d'une ligne de texte d'habillage. Tailles et épaisseurs pour un écran de 1080 lignes.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Font {
    pub family: String,
    pub weight: u16,
    pub size: f32,
    pub color: Rgba,
    pub uppercase: bool,
    pub letter_spacing: f32,
    pub line_height: f32,
    /// Ombre : couleur et flou.
    pub shadow: Option<(Rgba, f32)>,
    /// Contour : couleur et épaisseur.
    pub outline: Option<(Rgba, f32)>,
}

impl Font {
    pub fn new(family: &str, weight: u16, size: f32, color: Rgba) -> Self {
        Font {
            family: family.into(),
            weight,
            size,
            color,
            uppercase: false,
            letter_spacing: 0.0,
            line_height: 1.2,
            shadow: None,
            outline: None,
        }
    }

    fn upper(mut self, spacing: f32) -> Self {
        self.uppercase = true;
        self.letter_spacing = spacing;
        self
    }

    fn shadow(mut self, color: Rgba, blur: f32) -> Self {
        self.shadow = Some((color, blur));
        self
    }
}

/// Le remplissage de la boîte.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Fill {
    None,
    /// Unie ; semi-transparente si la couleur l'est.
    Solid {
        color: Rgba,
    },
    /// Un dégradé de gauche à droite.
    Gradient {
        from: Rgba,
        to: Rgba,
    },
}

/// Le côté de la ligne décorative.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Side {
    Left,
    Top,
    Bottom,
}

/// La ligne décorative d'une boîte.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Accent {
    pub side: Side,
    pub thickness: f32,
    pub color: Rgba,
}

/// L'entrée (ou la sortie) d'un habillage.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Entrance {
    None,
    Fade,
    /// Glisse depuis (ou vers) ce côté, en fondu.
    Slide(Direction),
    /// Se dévoile dans ce sens.
    Reveal(Direction),
    /// Le texte apparaît mot à mot, la boîte en fondu.
    WordByWord,
}

impl Entrance {
    pub fn label(self) -> &'static str {
        match self {
            Entrance::None => "Aucune",
            Entrance::Fade => "Fondu",
            Entrance::Slide(_) => "Glissement",
            Entrance::Reveal(_) => "Révélation",
            Entrance::WordByWord => "Mot à mot",
        }
    }
}

/// La courbe d'une animation.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Curve {
    Linear,
    /// Douce au départ et à l'arrivée.
    Smooth,
    /// Rapide au départ, douce à l'arrivée.
    Out,
}

impl Curve {
    pub fn apply(self, t: f32) -> f32 {
        let t = t.clamp(0.0, 1.0);
        match self {
            Curve::Linear => t,
            Curve::Smooth => t * t * (3.0 - 2.0 * t),
            Curve::Out => 1.0 - (1.0 - t).powi(3),
        }
    }
}

/// L'entrée et la sortie d'un habillage.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Motion {
    pub enter: Entrance,
    pub exit: Entrance,
    pub duration_ms: u32,
    pub curve: Curve,
}

impl Motion {
    pub const fn new(enter: Entrance, exit: Entrance, duration_ms: u32) -> Self {
        Motion { enter, exit, duration_ms, curve: Curve::Out }
    }
}

/// Ce qu'un lower third présente : il décide des noms des deux champs.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Purpose {
    Generic,
    Speaker,
    Sermon,
    Bible,
}

impl Purpose {
    /// Les noms des deux champs.
    pub fn fields(self) -> (&'static str, &'static str) {
        match self {
            Purpose::Generic => ("Titre", "Sous-titre"),
            Purpose::Speaker => ("Nom", "Fonction"),
            Purpose::Sermon => ("Thème", "Série ou date"),
            Purpose::Bible => ("Référence", "Version"),
        }
    }
}

/// Le style d'un lower third.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct LowerThirdStyle {
    pub purpose: Purpose,
    pub title: Font,
    pub subtitle: Font,
    /// Le sous-titre au-dessus du titre (une référence en surtitre, par exemple).
    pub subtitle_first: bool,
    pub fill: Fill,
    pub radius: f32,
    /// Marges intérieures (horizontale, verticale).
    pub padding: (f32, f32),
    pub accent: Option<Accent>,
    pub anchor: Anchor,
    /// Décalage depuis l'ancrage (x, y).
    pub offset: (f32, f32),
    /// Largeur de la boîte en pourcentage de l'écran ; 0 : celle du texte.
    pub width: f32,
    pub align: Align,
    /// Zone de sécurité, en pourcentage.
    pub safe_area: f32,
    pub opacity: f32,
    /// Durée d'affichage en millisecondes ; 0 : jusqu'au masquage.
    pub hold_ms: u32,
    pub motion: Motion,
}

/// Le contenu d'un lower third.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct LowerThirdText {
    pub title: String,
    pub subtitle: String,
}

impl LowerThirdText {
    pub fn new(title: impl Into<String>, subtitle: impl Into<String>) -> Self {
        LowerThirdText { title: title.into(), subtitle: subtitle.into() }
    }

    pub fn is_empty(&self) -> bool {
        self.title.trim().is_empty() && self.subtitle.trim().is_empty()
    }
}

const GOLD: Rgba = Rgba::rgb(0xe7, 0xc0, 0x7e);
const ORANGE: Rgba = Rgba::rgb(0xf2, 0x8c, 0x45);
const WHITE: Rgba = Rgba::WHITE;
const SOFT: Rgba = Rgba::new(255, 255, 255, 200);
const INK: Rgba = Rgba::rgb(0x0b, 0x12, 0x17);
const SHADE: Rgba = Rgba::new(0, 0, 0, 150);

impl LowerThirdStyle {
    fn base(purpose: Purpose) -> Self {
        LowerThirdStyle {
            purpose,
            title: Font::new("Inter", 700, 46.0, WHITE),
            subtitle: Font::new("Inter", 500, 30.0, SOFT),
            subtitle_first: false,
            fill: Fill::Solid { color: Rgba::new(10, 14, 22, 215) },
            radius: 10.0,
            padding: (34.0, 20.0),
            accent: None,
            anchor: Anchor::BottomLeft,
            offset: (0.0, 0.0),
            width: 0.0,
            align: Align::Left,
            safe_area: 6.0,
            opacity: 1.0,
            hold_ms: 0,
            motion: Motion::new(Entrance::Slide(Direction::Right), Entrance::Fade, 450),
        }
    }
}

/// Les lower thirds intégrés : (identifiant, nom, catégorie, style). Le bandeau de la 2.x s'y ajoute
/// dans la bibliothèque (il vient des réglages).
pub fn builtin_lower_thirds() -> Vec<(&'static str, &'static str, &'static str, LowerThirdStyle)> {
    let mut list = Vec::new();
    // 1. Minimaliste : le texte seul, une ombre légère.
    let mut s = LowerThirdStyle::base(Purpose::Generic);
    s.fill = Fill::None;
    s.title = Font::new("Inter", 600, 44.0, WHITE).shadow(SHADE, 12.0);
    s.subtitle = Font::new("Inter", 400, 28.0, SOFT).shadow(SHADE, 10.0);
    s.motion = Motion::new(Entrance::Fade, Entrance::Fade, 400);
    list.push(("lt-minimaliste", "Minimaliste", "Sobres", s));
    // 2. Moderne élégant : boîte sombre, filet doré à gauche.
    let mut s = LowerThirdStyle::base(Purpose::Generic);
    s.title = Font::new("Playfair Display", 700, 48.0, WHITE);
    s.subtitle = Font::new("Inter", 500, 26.0, GOLD).upper(3.0);
    s.accent = Some(Accent { side: Side::Left, thickness: 6.0, color: GOLD });
    s.radius = 4.0;
    list.push(("lt-moderne", "Moderne élégant", "Prédication", s));
    // 3. Fond transparent : pas de boîte, ombre marquée.
    let mut s = LowerThirdStyle::base(Purpose::Generic);
    s.fill = Fill::None;
    s.title = Font::new("Montserrat", 700, 50.0, WHITE).shadow(Rgba::new(0, 0, 0, 200), 18.0);
    s.subtitle = Font::new("Montserrat", 500, 30.0, WHITE).shadow(Rgba::new(0, 0, 0, 200), 14.0);
    list.push(("lt-transparent", "Fond transparent", "Diffusion", s));
    // 4. Texte seul : une ligne, centrée en bas.
    let mut s = LowerThirdStyle::base(Purpose::Generic);
    s.fill = Fill::None;
    s.anchor = Anchor::Bottom;
    s.align = Align::Center;
    s.title = Font::new("Inter", 700, 52.0, WHITE).shadow(SHADE, 14.0);
    s.subtitle = Font::new("Inter", 500, 30.0, SOFT).shadow(SHADE, 12.0);
    s.motion = Motion::new(Entrance::Slide(Direction::Up), Entrance::Fade, 400);
    list.push(("lt-texte-seul", "Texte seul", "Sobres", s));
    // 5. Ligne décorative : un filet sous le texte, sans boîte.
    let mut s = LowerThirdStyle::base(Purpose::Generic);
    s.fill = Fill::None;
    s.accent = Some(Accent { side: Side::Bottom, thickness: 4.0, color: ORANGE });
    s.title = Font::new("Poppins", 600, 46.0, WHITE).shadow(SHADE, 12.0);
    s.subtitle = Font::new("Poppins", 400, 28.0, SOFT).shadow(SHADE, 10.0);
    s.motion = Motion::new(Entrance::Reveal(Direction::Right), Entrance::Fade, 600);
    list.push(("lt-ligne", "Ligne décorative", "Louange", s));
    // 6. Bandeau semi-transparent : toute la largeur, en bas.
    let mut s = LowerThirdStyle::base(Purpose::Generic);
    s.anchor = Anchor::Bottom;
    s.width = 100.0;
    s.safe_area = 0.0;
    s.offset = (0.0, -60.0);
    s.radius = 0.0;
    s.align = Align::Center;
    s.fill = Fill::Solid { color: Rgba::new(0, 0, 0, 150) };
    s.motion = Motion::new(Entrance::Slide(Direction::Up), Entrance::Slide(Direction::Down), 450);
    list.push(("lt-bandeau", "Bandeau semi-transparent", "Diffusion", s));
    // 7. Animé : dégradé, dévoilé de gauche à droite, texte mot à mot.
    let mut s = LowerThirdStyle::base(Purpose::Generic);
    s.fill = Fill::Gradient { from: Rgba::new(242, 140, 69, 235), to: Rgba::new(155, 123, 247, 235) };
    s.title = Font::new("Outfit", 700, 48.0, WHITE);
    s.subtitle = Font::new("Outfit", 500, 28.0, WHITE);
    s.radius = 14.0;
    s.motion = Motion::new(Entrance::WordByWord, Entrance::Reveal(Direction::Left), 900);
    list.push(("lt-anime", "Animé", "Louange", s));
    // 8. Prédication : le thème en grand, la date et le lieu dessous, filet doré en haut.
    let mut s = LowerThirdStyle::base(Purpose::Sermon);
    s.title = Font::new("Cormorant Garamond", 700, 54.0, WHITE);
    s.subtitle = Font::new("Inter", 500, 26.0, GOLD).upper(2.0);
    s.accent = Some(Accent { side: Side::Top, thickness: 4.0, color: GOLD });
    s.fill = Fill::Solid { color: Rgba::new(12, 16, 24, 225) };
    list.push(("lt-predication", "Prédication", "Prédication", s));
    // 9. Nom de l'orateur : nom en gras, fonction en capitales.
    let mut s = LowerThirdStyle::base(Purpose::Speaker);
    s.title = Font::new("Inter", 700, 46.0, INK);
    s.subtitle = Font::new("Inter", 600, 24.0, Rgba::rgb(0x5f, 0x71, 0x7c)).upper(2.5);
    s.fill = Fill::Solid { color: Rgba::new(255, 255, 255, 240) };
    s.accent = Some(Accent { side: Side::Left, thickness: 8.0, color: ORANGE });
    s.radius = 2.0;
    list.push(("lt-orateur", "Nom de l'orateur", "Prédication", s));
    // 10. Thème du sermon : la série en surtitre.
    let mut s = LowerThirdStyle::base(Purpose::Sermon);
    s.subtitle_first = true;
    s.title = Font::new("Lora", 700, 50.0, WHITE);
    s.subtitle = Font::new("Inter", 600, 22.0, GOLD).upper(3.0);
    s.fill = Fill::Gradient { from: Rgba::new(10, 14, 22, 235), to: Rgba::new(10, 14, 22, 120) };
    list.push(("lt-theme", "Thème du sermon", "Prédication", s));
    // 11. Référence biblique : compacte, en haut à droite.
    let mut s = LowerThirdStyle::base(Purpose::Bible);
    s.anchor = Anchor::TopRight;
    s.align = Align::Right;
    s.title = Font::new("Inter", 700, 40.0, WHITE);
    s.subtitle = Font::new("Inter", 600, 22.0, Rgba::rgb(86, 214, 129)).upper(2.0);
    s.accent = Some(Accent { side: Side::Bottom, thickness: 4.0, color: Rgba::rgb(86, 214, 129) });
    s.motion = Motion::new(Entrance::Slide(Direction::Left), Entrance::Fade, 400);
    list.push(("lt-bible", "Référence biblique", "Bible", s));
    // 12. Annonce : grande boîte claire au centre en bas, pour une information.
    let mut s = LowerThirdStyle::base(Purpose::Generic);
    s.anchor = Anchor::Bottom;
    s.align = Align::Center;
    s.width = 60.0;
    s.title = Font::new("Poppins", 700, 44.0, INK);
    s.subtitle = Font::new("Poppins", 500, 28.0, Rgba::rgb(0x25, 0x34, 0x3e));
    s.fill = Fill::Solid { color: Rgba::new(242, 240, 233, 245) };
    s.radius = 18.0;
    s.motion = Motion::new(Entrance::Slide(Direction::Up), Entrance::Slide(Direction::Down), 500);
    list.push(("lt-annonce", "Annonce", "Annonces", s));
    // 13. Sobre : texte gris clair, petite capitale, sans boîte, en haut à gauche.
    let mut s = LowerThirdStyle::base(Purpose::Generic);
    s.anchor = Anchor::TopLeft;
    s.fill = Fill::None;
    s.title = Font::new("Inter", 600, 34.0, WHITE).upper(2.0).shadow(SHADE, 10.0);
    s.subtitle = Font::new("Inter", 400, 24.0, SOFT).shadow(SHADE, 8.0);
    s.motion = Motion::new(Entrance::Fade, Entrance::Fade, 500);
    list.push(("lt-sobre", "Sobre", "Sobres", s));
    list
}

/// L'apparence des sous-titres.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SubtitleLook {
    /// Le texte seul, avec une ombre.
    Transparent,
    /// Une bande semi-transparente derrière toutes les lignes.
    Translucent,
    /// Le texte cerné d'un contour, sans boîte.
    Outline,
    /// Une boîte ajustée derrière chaque ligne (à la télévision).
    BoxPerLine,
}

impl SubtitleLook {
    pub const ALL: [SubtitleLook; 4] =
        [SubtitleLook::Transparent, SubtitleLook::Translucent, SubtitleLook::Outline, SubtitleLook::BoxPerLine];

    pub fn label(self) -> &'static str {
        match self {
            SubtitleLook::Transparent => "Transparent",
            SubtitleLook::Translucent => "Semi-transparent",
            SubtitleLook::Outline => "Contour",
            SubtitleLook::BoxPerLine => "Boîte par ligne",
        }
    }
}

/// Le style des sous-titres.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SubtitleStyle {
    pub look: SubtitleLook,
    pub font: Font,
    /// La couleur de la bande ou des boîtes.
    pub box_color: Rgba,
    pub position: BandPosition,
    /// De 1 à 3 lignes, équilibrées.
    pub max_lines: usize,
    /// Largeur utile, en pourcentage de l'écran.
    pub width: f32,
    /// Marge depuis le bord (haut ou bas), en pourcentage.
    pub margin: f32,
}

impl SubtitleStyle {
    pub fn new(look: SubtitleLook) -> Self {
        let mut font = Font::new("Inter", 600, 48.0, WHITE);
        font.line_height = 1.25;
        match look {
            SubtitleLook::Transparent => font.shadow = Some((Rgba::new(0, 0, 0, 220), 10.0)),
            SubtitleLook::Outline => font.outline = Some((Rgba::BLACK, 3.0)),
            SubtitleLook::Translucent | SubtitleLook::BoxPerLine => {}
        }
        SubtitleStyle {
            look,
            font,
            box_color: Rgba::new(0, 0, 0, if look == SubtitleLook::BoxPerLine { 200 } else { 150 }),
            position: BandPosition::Bottom,
            max_lines: 2,
            width: 80.0,
            margin: 7.0,
        }
    }
}

/// Les modèles de sous-titres intégrés : (identifiant, nom, style).
pub fn builtin_subtitles() -> Vec<(&'static str, &'static str, SubtitleStyle)> {
    SubtitleLook::ALL
        .into_iter()
        .map(|look| {
            let id = match look {
                SubtitleLook::Transparent => "st-transparent",
                SubtitleLook::Translucent => "st-semi-transparent",
                SubtitleLook::Outline => "st-contour",
                SubtitleLook::BoxPerLine => "st-boite-par-ligne",
            };
            (id, look.label(), SubtitleStyle::new(look))
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn there_are_at_least_twelve_lower_thirds_with_distinct_ids() {
        let list = builtin_lower_thirds();
        assert!(list.len() >= 12, "{} styles", list.len());
        let mut ids: Vec<_> = list.iter().map(|(id, ..)| *id).collect();
        ids.sort_unstable();
        ids.dedup();
        assert_eq!(ids.len(), list.len());
        // Chaque usage demandé a son style.
        for purpose in [Purpose::Speaker, Purpose::Sermon, Purpose::Bible] {
            assert!(list.iter().any(|(.., s)| s.purpose == purpose));
        }
        assert_eq!(Purpose::Speaker.fields(), ("Nom", "Fonction"));
        // Un style passe en JSON et revient tel quel.
        for (.., style) in &list {
            let json = serde_json::to_string(style).unwrap();
            assert_eq!(&serde_json::from_str::<LowerThirdStyle>(&json).unwrap(), style);
        }
    }

    #[test]
    fn anchors_and_curves() {
        assert_eq!(Anchor::BottomRight.factors(), (1.0, 1.0));
        assert_eq!(Anchor::Center.factors(), (0.5, 0.5));
        for curve in [Curve::Linear, Curve::Smooth, Curve::Out] {
            assert_eq!(curve.apply(0.0), 0.0);
            assert_eq!(curve.apply(1.0), 1.0);
            assert!(curve.apply(0.5) > 0.0 && curve.apply(0.5) < 1.0);
        }
        assert_eq!(builtin_subtitles().len(), 4);
        assert!(SubtitleStyle::new(SubtitleLook::Outline).font.outline.is_some());
    }
}
