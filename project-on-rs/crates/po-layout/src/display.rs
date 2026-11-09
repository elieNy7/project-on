//! La liste d'affichage : ce qu'un écran doit dessiner, déjà placé au pixel près.
//!
//! Elle est calculée une seule fois par `po-layout`, puis dessinée telle quelle par chaque
//! afficheur (fenêtre de projection, navigateur de la projection Web, images NDI / HDMI). Les
//! afficheurs ne prennent aucune décision de mise en page : le texte, ses coupures et ses positions
//! sont donc les mêmes partout.

use serde::{Deserialize, Serialize};

/// Une couleur RVBA (0–255), sérialisée en tableau `[r, g, b, a]`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Rgba(pub [u8; 4]);

impl Rgba {
    pub const fn rgb(r: u8, g: u8, b: u8) -> Self {
        Rgba([r, g, b, 255])
    }

    pub const fn new(r: u8, g: u8, b: u8, a: u8) -> Self {
        Rgba([r, g, b, a])
    }
}

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
}

/// Un élément de la liste, dessiné dans l'ordre.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Item {
    Rect { x: f32, y: f32, w: f32, h: f32, radius: f32, color: Rgba },
    Text(TextLine),
}

/// Ce qu'un écran affiche.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DisplayList {
    /// La taille pour laquelle la mise en page a été calculée.
    pub width: f32,
    pub height: f32,
    pub background: Rgba,
    pub items: Vec<Item>,
}

impl DisplayList {
    /// Les lignes de texte de la liste.
    pub fn text_lines(&self) -> impl Iterator<Item = &TextLine> {
        self.items.iter().filter_map(|item| match item {
            Item::Text(line) => Some(line),
            Item::Rect { .. } => None,
        })
    }
}
