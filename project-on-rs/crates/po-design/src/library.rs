//! La bibliothèque de designs : les designs intégrés (salle, bandeau, lower thirds, sous-titres),
//! classés par catégorie, et « Mes designs », un fichier JSON par design dans `data/designs`
//! (écriture atomique), que l'on duplique, personnalise, importe et exporte.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::graphics::{LowerThirdStyle, SubtitleStyle, builtin_lower_thirds, builtin_subtitles};
use crate::{
    AnimationKind, Background, Band, IdentificationStyle, ImageFit, Look, ReferencePosition, Rgba, RoomDesign, Shadow,
    VerticalPosition,
};

/// Les catégories de la bibliothèque, dans l'ordre affiché.
pub const CATEGORIES: [&str; 7] = ["Louange", "Prédication", "Bible", "Annonces", "Diffusion", "Sous-titres", "Sobres"];

/// Ce que décrit un design.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", content = "style", rename_all = "snake_case")]
pub enum DesignBody {
    /// Le slide plein écran de la salle.
    Room(RoomDesign),
    /// Le bandeau de la diffusion (le texte du slide sur la vidéo).
    Band(Band),
    LowerThird(LowerThirdStyle),
    Subtitles(SubtitleStyle),
}

impl DesignBody {
    pub fn kind_label(&self) -> &'static str {
        match self {
            DesignBody::Room(_) => "Salle",
            DesignBody::Band(_) => "Bandeau",
            DesignBody::LowerThird(_) => "Lower third",
            DesignBody::Subtitles(_) => "Sous-titres",
        }
    }
}

/// Un design.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Design {
    /// Identifiant stable (nom de fichier pour « Mes designs »).
    pub id: String,
    pub name: String,
    pub category: String,
    /// Intégré à Project-On (non modifiable : on le duplique).
    #[serde(default)]
    pub builtin: bool,
    /// Le design de départ d'un design personnalisé.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub based_on: Option<String>,
    pub body: DesignBody,
}

fn room(f: impl FnOnce(&mut RoomDesign)) -> RoomDesign {
    let mut d = RoomDesign::default();
    f(&mut d);
    d
}

/// Les designs de salle intégrés.
fn builtin_rooms() -> Vec<(&'static str, &'static str, &'static str, RoomDesign)> {
    vec![
        (
            "salle-nuit",
            "Nuit profonde",
            "Prédication",
            room(|d| {
                d.text.family = "Poppins".into();
                d.text.weight = 600;
                d.background = Background {
                    color: Rgba::rgb(10, 16, 32),
                    gradient: Some((Rgba::rgb(22, 38, 72), 135.0)),
                    image: None,
                    image_fit: ImageFit::Cover,
                    look: Look::Cinematic,
                    dimmer: 0.0,
                };
                d.reference.color = Rgba::rgb(0xe7, 0xc0, 0x7e);
            }),
        ),
        (
            "salle-louange",
            "Louange chaleureuse",
            "Louange",
            room(|d| {
                d.text.family = "Montserrat".into();
                d.text.weight = 700;
                d.text.uppercase = true;
                d.background.color = Rgba::rgb(58, 20, 32);
                d.background.gradient = Some((Rgba::rgb(160, 70, 40), 160.0));
                d.shadow = Some(Shadow { color: Rgba::new(0, 0, 0, 140), blur: 22.0 });
                d.animation.kind = AnimationKind::Fade;
            }),
        ),
        (
            "salle-bible",
            "Bible classique",
            "Bible",
            room(|d| {
                d.text.family = "Lora".into();
                d.text.weight = 400;
                d.text.uppercase = false;
                d.text.line_height = 1.3;
                d.background.color = Rgba::rgb(20, 24, 22);
                d.background.gradient = Some((Rgba::rgb(36, 52, 40), 90.0));
                d.reference.position = ReferencePosition::Top;
                d.reference.color = Rgba::rgb(86, 214, 129);
            }),
        ),
        (
            "salle-annonces",
            "Annonces claires",
            "Annonces",
            room(|d| {
                d.text.family = "Poppins".into();
                d.text.weight = 600;
                d.text.color = Rgba::rgb(0x17, 0x23, 0x2c);
                d.background.color = Rgba::rgb(242, 240, 233);
                d.background.gradient = None;
                d.shadow = None;
                d.reference.color = Rgba::rgb(0xf2, 0x8c, 0x45);
                d.identification.style = IdentificationStyle::Band;
            }),
        ),
        (
            "salle-sobre",
            "Sobre",
            "Sobres",
            room(|d| {
                d.text.family = "Inter".into();
                d.text.weight = 500;
                d.text.uppercase = false;
                d.background.color = Rgba::rgb(12, 12, 12);
                d.background.gradient = None;
                d.background.look = Look::Clean;
                d.shadow = None;
                d.position = VerticalPosition::Center;
                d.identification.style = IdentificationStyle::Minimal;
            }),
        ),
    ]
}

/// Les designs intégrés. `room` et `band` : ceux des réglages de la 2.x (« Mon design 2.x »,
/// « Mon bandeau 2.x »), en tête de leur catégorie.
pub fn builtin(room_2x: &RoomDesign, band_2x: &Band) -> Vec<Design> {
    let design = |id: &str, name: &str, category: &str, body: DesignBody| Design {
        id: id.into(),
        name: name.into(),
        category: category.into(),
        builtin: true,
        based_on: None,
        body,
    };
    let mut out = vec![
        design("salle-2x", "Mon design 2.x", "Prédication", DesignBody::Room(room_2x.clone())),
        design("bandeau-2x", "Mon bandeau 2.x", "Diffusion", DesignBody::Band(band_2x.clone())),
    ];
    for (id, name, category, d) in builtin_rooms() {
        out.push(design(id, name, category, DesignBody::Room(d)));
    }
    let mut lower = band_2x.clone();
    lower.layout = crate::BandLayout::LowerThird;
    out.push(design("bandeau-lower-third", "Bandeau en lower third", "Diffusion", DesignBody::Band(lower)));
    let mut side = band_2x.clone();
    side.layout = crate::BandLayout::SidePanel;
    out.push(design("bandeau-panneau", "Panneau latéral", "Diffusion", DesignBody::Band(side)));
    let mut card = band_2x.clone();
    card.layout = crate::BandLayout::FocusCard;
    out.push(design("bandeau-carte", "Carte", "Diffusion", DesignBody::Band(card)));
    for (id, name, category, style) in builtin_lower_thirds() {
        out.push(design(id, name, category, DesignBody::LowerThird(style)));
    }
    for (id, name, style) in builtin_subtitles() {
        out.push(design(id, name, "Sous-titres", DesignBody::Subtitles(style)));
    }
    out
}

/// Un identifiant de fichier sûr à partir d'un nom : lettres, chiffres et tirets.
pub fn slug(name: &str) -> String {
    let mut out = String::new();
    for c in po_text_like_fold(name).chars() {
        if c.is_ascii_alphanumeric() {
            out.push(c.to_ascii_lowercase());
        } else if !out.ends_with('-') && !out.is_empty() {
            out.push('-');
        }
    }
    let out = out.trim_end_matches('-').chars().take(48).collect::<String>();
    if out.is_empty() { "design".into() } else { out }
}

/// Les accents retirés (é → e) pour les noms de fichiers.
fn po_text_like_fold(text: &str) -> String {
    text.chars()
        .map(|c| match c {
            'à' | 'â' | 'ä' | 'á' | 'À' | 'Â' | 'Ä' => 'a',
            'é' | 'è' | 'ê' | 'ë' | 'É' | 'È' | 'Ê' | 'Ë' => 'e',
            'î' | 'ï' | 'í' | 'Î' | 'Ï' => 'i',
            'ô' | 'ö' | 'ó' | 'Ô' | 'Ö' => 'o',
            'ù' | 'û' | 'ü' | 'ú' | 'Ù' | 'Û' | 'Ü' => 'u',
            'ç' | 'Ç' => 'c',
            'ÿ' => 'y',
            other => other,
        })
        .collect()
}

/// Les erreurs de « Mes designs ».
#[derive(Debug)]
pub enum LibraryError {
    Io(std::io::Error),
    /// Un fichier qui n'est pas un design de Project-On.
    NotADesign(String),
}

impl std::fmt::Display for LibraryError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            LibraryError::Io(e) => write!(f, "{e}"),
            LibraryError::NotADesign(why) => write!(f, "ce fichier n'est pas un design de Project-On ({why})"),
        }
    }
}

impl std::error::Error for LibraryError {}

impl From<std::io::Error> for LibraryError {
    fn from(e: std::io::Error) -> Self {
        LibraryError::Io(e)
    }
}

/// « Mes designs » : un dossier, un fichier par design.
#[derive(Debug, Clone)]
pub struct MyDesigns {
    dir: PathBuf,
}

impl MyDesigns {
    pub fn new(dir: impl Into<PathBuf>) -> Self {
        MyDesigns { dir: dir.into() }
    }

    pub fn dir(&self) -> &Path {
        &self.dir
    }

    /// Les designs du dossier, par nom. Un fichier illisible est ignoré (et signalé dans le
    /// second élément).
    pub fn load(&self) -> (Vec<Design>, Vec<String>) {
        let mut designs = Vec::new();
        let mut skipped = Vec::new();
        let Ok(entries) = std::fs::read_dir(&self.dir) else { return (designs, skipped) };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) != Some("json") {
                continue;
            }
            match read(&path) {
                Ok(mut d) => {
                    d.builtin = false;
                    // Le fichier fait foi pour l'identifiant.
                    if let Some(stem) = path.file_stem().and_then(|s| s.to_str()) {
                        d.id = stem.to_string();
                    }
                    designs.push(d);
                }
                Err(e) => skipped.push(format!("{} : {e}", path.display())),
            }
        }
        designs.sort_by_key(|d| d.name.to_lowercase());
        (designs, skipped)
    }

    /// Un identifiant libre pour ce nom.
    fn free_id(&self, name: &str) -> String {
        let base = format!("mon-{}", slug(name));
        let mut id = base.clone();
        let mut n = 2;
        while self.dir.join(format!("{id}.json")).exists() {
            id = format!("{base}-{n}");
            n += 1;
        }
        id
    }

    /// Enregistre un design (écriture atomique : fichier temporaire puis renommage). Un design
    /// intégré est enregistré comme une copie. Rend le design tel qu'enregistré.
    pub fn save(&self, design: &Design) -> Result<Design, LibraryError> {
        std::fs::create_dir_all(&self.dir)?;
        let mut design = design.clone();
        if design.builtin || design.id.is_empty() {
            design.based_on = design.based_on.or_else(|| design.builtin.then(|| design.id.clone()));
            design.id = self.free_id(&design.name);
            design.builtin = false;
        }
        let path = self.dir.join(format!("{}.json", slug_id(&design.id)));
        let tmp = path.with_extension("json.tmp");
        let json = serde_json::to_string_pretty(&design).map_err(|e| LibraryError::NotADesign(e.to_string()))?;
        std::fs::write(&tmp, json)?;
        std::fs::rename(&tmp, &path)?;
        Ok(design)
    }

    /// Duplique un design sous un nouveau nom, dans « Mes designs ».
    pub fn duplicate(&self, design: &Design, name: &str) -> Result<Design, LibraryError> {
        let copy = Design {
            id: String::new(),
            name: name.trim().to_string(),
            based_on: Some(design.id.clone()),
            builtin: false,
            ..design.clone()
        };
        self.save(&copy)
    }

    /// Supprime un design de « Mes designs ».
    pub fn delete(&self, id: &str) -> Result<(), LibraryError> {
        let path = self.dir.join(format!("{}.json", slug_id(id)));
        if path.exists() {
            std::fs::remove_file(path)?;
        }
        Ok(())
    }

    /// Importe un fichier de design (exporté par Project-On) dans « Mes designs ».
    pub fn import(&self, file: &Path) -> Result<Design, LibraryError> {
        let mut design = read(file)?;
        design.id = String::new();
        design.builtin = false;
        self.save(&design)
    }
}

/// Exporte un design dans un fichier.
pub fn export(design: &Design, file: &Path) -> Result<(), LibraryError> {
    let json = serde_json::to_string_pretty(design).map_err(|e| LibraryError::NotADesign(e.to_string()))?;
    let tmp = file.with_extension("tmp");
    std::fs::write(&tmp, json)?;
    std::fs::rename(&tmp, file)?;
    Ok(())
}

fn read(path: &Path) -> Result<Design, LibraryError> {
    let text = std::fs::read_to_string(path)?;
    serde_json::from_str(text.trim_start_matches('\u{feff}')).map_err(|e| LibraryError::NotADesign(e.to_string()))
}

/// Un identifiant ramené aux caractères sûrs (jamais de chemin).
fn slug_id(id: &str) -> String {
    let s: String = id.chars().filter(|c| c.is_ascii_alphanumeric() || *c == '-').take(64).collect();
    if s.is_empty() { "design".into() } else { s }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scratch() -> PathBuf {
        let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp").join(format!(
            "designs-{}-{}",
            std::process::id(),
            line!()
        ));
        let _ = std::fs::remove_dir_all(&dir);
        dir
    }

    #[test]
    fn the_library_has_every_kind_and_category() {
        let list = builtin(&RoomDesign::default(), &Band::default());
        for category in CATEGORIES {
            assert!(list.iter().any(|d| d.category == category), "{category} vide");
        }
        let lower = list.iter().filter(|d| matches!(d.body, DesignBody::LowerThird(_))).count();
        assert!(lower >= 12);
        assert!(list.iter().any(|d| d.id == "bandeau-2x"));
        let mut ids: Vec<_> = list.iter().map(|d| d.id.clone()).collect();
        ids.sort();
        ids.dedup();
        assert_eq!(ids.len(), list.len(), "identifiants uniques");
        assert_eq!(slug("Prédication du Dimanche !"), "predication-du-dimanche");
        assert_eq!(slug("../.."), "design");
    }

    #[test]
    fn my_designs_are_saved_one_file_each_and_come_back() {
        let dir = scratch();
        let mine = MyDesigns::new(&dir);
        let list = builtin(&RoomDesign::default(), &Band::default());
        let original = list.iter().find(|d| d.id == "lt-moderne").unwrap();
        // Dupliquer un design intégré : une copie dans « Mes designs », qui garde son origine.
        let mut copy = mine.duplicate(original, "Mon orateur").unwrap();
        assert_eq!(copy.id, "mon-mon-orateur");
        assert_eq!(copy.based_on.as_deref(), Some("lt-moderne"));
        assert!(!copy.builtin);
        // Personnaliser puis enregistrer : même fichier.
        if let DesignBody::LowerThird(style) = &mut copy.body {
            style.title.size = 60.0;
        }
        mine.save(&copy).unwrap();
        let again = mine.duplicate(original, "Mon orateur").unwrap();
        assert_eq!(again.id, "mon-mon-orateur-2", "un nom déjà pris : un autre fichier");
        let (loaded, skipped) = mine.load();
        assert!(skipped.is_empty());
        assert_eq!(loaded.len(), 2);
        assert_eq!(loaded.iter().find(|d| d.id == copy.id), Some(&copy));
        // Aucun fichier temporaire ne reste.
        assert!(std::fs::read_dir(&dir).unwrap().flatten().all(|e| e.path().extension().unwrap() == "json"));
        // Exporter, importer : le même design, sous un nouvel identifiant.
        let file = dir.join("export.podesign");
        export(&copy, &file).unwrap();
        let imported = mine.import(&file).unwrap();
        assert_eq!(imported.body, copy.body);
        assert_ne!(imported.id, copy.id);
        // Un fichier qui n'est pas un design est refusé ; un fichier abîmé est ignoré au chargement.
        std::fs::write(dir.join("faux.json"), "{\"pas\": 1}").unwrap();
        assert!(mine.import(&dir.join("faux.json")).is_err());
        let (loaded, skipped) = mine.load();
        assert_eq!((loaded.len(), skipped.len()), (3, 1));
        mine.delete(&copy.id).unwrap();
        assert_eq!(mine.load().0.len(), 2);
        let _ = std::fs::remove_dir_all(&dir);
    }
}
