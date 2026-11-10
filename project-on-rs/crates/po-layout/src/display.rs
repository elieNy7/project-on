//! La liste d'affichage : ce qu'un écran doit dessiner, déjà placé au pixel près.
//!
//! Elle est calculée une seule fois par `po-layout`, puis dessinée telle quelle par chaque
//! afficheur (fenêtre de projection, navigateur de la projection Web, images NDI / HDMI). Les
//! afficheurs ne prennent aucune décision de mise en page : le texte, ses coupures et ses positions
//! sont donc les mêmes partout.
//!
//! Trois couches, dessinées dans l'ordre :
//! - `backdrop` : le fond (couleur, dégradé, image, voiles). Il ne bouge pas pendant une transition.
//! - `items` : le texte, la référence et son filet — ce qui change d'un slide à l'autre.
//! - `overlay` : ce qui reste par-dessus (l'identification de Branham).

pub use po_design::Rgba;
use serde::{Deserialize, Serialize};

/// Le point d'accroche horizontal d'une ligne de texte.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Anchor {
    /// `x` est le bord gauche de la ligne.
    Start,
    /// `x` est le milieu de la ligne : un écart de largeur entre deux moteurs de texte se répartit
    /// des deux côtés.
    Middle,
    /// `x` est le bord droit de la ligne.
    End,
}

/// L'ombre (ou le halo, sans décalage) d'une ligne de texte.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct TextShadow {
    pub color: Rgba,
    /// Le rayon du flou, en pixels.
    pub blur: f32,
    pub dx: f32,
    pub dy: f32,
}

fn one() -> f32 {
    1.0
}

fn is_one(v: &f32) -> bool {
    (*v - 1.0).abs() < f32::EPSILON
}

fn is_zero(v: &f32) -> bool {
    *v == 0.0
}

/// Une ligne de texte placée.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TextLine {
    pub text: String,
    pub x: f32,
    /// La ligne de base, en pixels depuis le haut de l'écran.
    pub baseline: f32,
    pub anchor: Anchor,
    /// La taille de la police, en pixels.
    pub size: f32,
    pub family: String,
    pub weight: u16,
    pub color: Rgba,
    /// La largeur mesurée par `po-layout` (pour information : un afficheur ne s'en sert pas pour
    /// couper).
    pub width: f32,
    /// L'espace ajouté après chaque lettre, en pixels.
    #[serde(default, skip_serializing_if = "is_zero")]
    pub letter_spacing: f32,
    /// L'avance de chaque lettre est multipliée par ce facteur (1,12 pour la référence, comme la 2.x).
    #[serde(default = "one", skip_serializing_if = "is_one")]
    pub advance_scale: f32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub shadow: Option<TextShadow>,
}

/// Un arrêt de dégradé : position (0 à 1) et couleur.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Stop {
    pub at: f32,
    pub color: Rgba,
}

/// Un groupe d'éléments dessinés ensemble, avec une opacité, un déplacement, une échelle, un flou
/// ou une découpe : c'est ce qu'animent les transitions.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Group {
    pub opacity: f32,
    pub dx: f32,
    pub dy: f32,
    pub scale: f32,
    /// Le centre de la mise à l'échelle.
    pub origin: [f32; 2],
    /// Le rayon du flou, en pixels (0 = net).
    pub blur: f32,
    /// Seule cette zone (x, y, largeur, hauteur) est dessinée.
    pub clip: Option<[f32; 4]>,
    pub items: Vec<Item>,
}

impl Group {
    pub fn plain(items: Vec<Item>) -> Self {
        Group { opacity: 1.0, dx: 0.0, dy: 0.0, scale: 1.0, origin: [0.0, 0.0], blur: 0.0, clip: None, items }
    }
}

/// Un élément de la liste, dessiné dans l'ordre.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Item {
    Rect {
        x: f32,
        y: f32,
        w: f32,
        h: f32,
        radius: f32,
        color: Rgba,
    },
    /// Un rectangle rempli d'un dégradé linéaire de `from` à `to` (prolongé au-delà).
    LinearGradient {
        x: f32,
        y: f32,
        w: f32,
        h: f32,
        from: [f32; 2],
        to: [f32; 2],
        stops: Vec<Stop>,
    },
    /// Un rectangle rempli d'un dégradé circulaire (prolongé au-delà du rayon).
    RadialGradient {
        x: f32,
        y: f32,
        w: f32,
        h: f32,
        center: [f32; 2],
        radius: f32,
        stops: Vec<Stop>,
    },
    /// Une image (fichier local), étirée dans le rectangle donné.
    Image {
        path: String,
        x: f32,
        y: f32,
        w: f32,
        h: f32,
        opacity: f32,
    },
    Text(TextLine),
    Group(Group),
}

/// Ce qu'un écran affiche.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DisplayList {
    /// La taille pour laquelle la mise en page a été calculée.
    pub width: f32,
    pub height: f32,
    pub background: Rgba,
    /// La zone sûre où vivent le texte et la référence (x, y, largeur, hauteur) : les transitions
    /// s'y appuient (centre du zoom, balayage).
    #[serde(default)]
    pub stage: [f32; 4],
    #[serde(default)]
    pub backdrop: Vec<Item>,
    pub items: Vec<Item>,
    #[serde(default)]
    pub overlay: Vec<Item>,
}

impl DisplayList {
    /// Un écran vide de la couleur donnée.
    pub fn blank(width: f32, height: f32, background: Rgba) -> Self {
        DisplayList {
            width,
            height,
            background,
            stage: [0.0, 0.0, width, height],
            backdrop: Vec::new(),
            items: Vec::new(),
            overlay: Vec::new(),
        }
    }

    /// Les lignes de texte du contenu (sans le fond ni l'identification).
    pub fn text_lines(&self) -> impl Iterator<Item = &TextLine> {
        self.items.iter().filter_map(|item| match item {
            Item::Text(line) => Some(line),
            _ => None,
        })
    }

    /// Les lignes de texte de l'identification.
    pub fn overlay_lines(&self) -> impl Iterator<Item = &TextLine> {
        self.overlay.iter().filter_map(|item| match item {
            Item::Text(line) => Some(line),
            _ => None,
        })
    }
}
