//! Les réglages de Project-On, dans le `settings.json` de la 2.x.
//!
//! - Les sections dont la 3.0 se sert déjà sont **typées** et lues avec les règles exactes de la 2.8
//!   (`AppSettings.load`) : valeurs par défaut pour les champs absents, conversions de Python,
//!   bornes, garde-fous. Ce sont `projection`, `appearance`, `split` et `hdmi`.
//! - Les autres sections (`obs`, `shortcuts`, `church`, `thumbnail_models` et toute section
//!   inconnue) sont **gardées telles quelles** et réécrites à l'identique. Elles seront typées dans
//!   la phase qui s'en sert.
//! - L'écriture est atomique (fichier temporaire puis renommage) et laisse une copie `.bak`. Un
//!   fichier illisible est relu depuis le `.bak`, avec un avertissement à montrer à l'opérateur ;
//!   un fichier illisible n'est jamais écrasé sans être mis de côté.

mod sections;

use std::io::Write;
use std::path::{Path, PathBuf};

use serde_json::{Map, Value};

pub use sections::{AppearanceSettings, HdmiSettings, HdmiStyle, ProjectionSettings, SplitSettings};

/// Relu depuis la sauvegarde : à montrer à l'opérateur.
pub const RECOVERED_FROM_BACKUP: &str =
    "Paramètres récupérés depuis la dernière sauvegarde valide. Vérifiez vos réglages avant de projeter.";
/// Ni le fichier ni sa sauvegarde ne se lisent.
pub const UNREADABLE: &str = "Paramètres illisibles : valeurs par défaut utilisées. Le fichier original sera conservé à la prochaine sauvegarde.";

/// Les sections typées, dans l'ordre où la 2.8 les écrit (les autres gardent leur place relative).
const TYPED: [&str; 4] = ["projection", "appearance", "hdmi", "split"];
/// L'ordre des sections dans le fichier de la 2.8.
const ORDER: [&str; 8] =
    ["projection", "obs", "appearance", "hdmi", "split", "shortcuts", "church", "thumbnail_models"];

#[derive(Debug, thiserror::Error)]
pub enum SettingsError {
    #[error("Impossible d'écrire les réglages ({path}) : {source}")]
    Write {
        path: PathBuf,
        #[source]
        source: std::io::Error,
    },
}

/// Tous les réglages.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Settings {
    pub projection: ProjectionSettings,
    pub appearance: AppearanceSettings,
    pub hdmi: HdmiSettings,
    pub split: SplitSettings,
    /// Les sections gardées telles quelles, dans leur ordre.
    pub other: Map<String, Value>,
}

/// Des réglages lus, et l'avertissement éventuel à montrer.
#[derive(Debug, Clone, PartialEq)]
pub struct Loaded {
    pub settings: Settings,
    pub warning: Option<&'static str>,
}

fn read_object(path: &Path) -> Result<Map<String, Value>, std::io::Error> {
    let text = std::fs::read_to_string(path)?;
    match serde_json::from_str::<Value>(&text) {
        Ok(Value::Object(map)) => Ok(map),
        Ok(_) => Err(std::io::Error::other("La racine des paramètres doit être un objet JSON.")),
        Err(e) => Err(std::io::Error::other(e)),
    }
}

fn backup_path(path: &Path) -> PathBuf {
    let mut name = path.as_os_str().to_owned();
    name.push(".bak");
    PathBuf::from(name)
}

/// Le contenu du fichier, comme `load_payload` de la 2.8 : le fichier, sinon sa sauvegarde.
fn load_payload(path: &Path) -> (Map<String, Value>, Option<&'static str>) {
    let backup = backup_path(path);
    match read_object(path) {
        Ok(map) => return (map, None),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound && !backup.exists() => return (Map::new(), None),
        Err(_) => {}
    }
    match read_object(&backup) {
        Ok(map) => (map, Some(RECOVERED_FROM_BACKUP)),
        Err(_) => (Map::new(), Some(UNREADABLE)),
    }
}

impl Settings {
    /// Les réglages d'un contenu JSON déjà lu.
    pub fn from_payload(payload: &Map<String, Value>) -> Self {
        let section = |name: &str| payload.get(name).and_then(Value::as_object);
        Self {
            projection: ProjectionSettings::read(section("projection")),
            appearance: AppearanceSettings::read(section("appearance")),
            hdmi: HdmiSettings::read(section("hdmi")),
            split: SplitSettings::read(section("split")),
            other: payload
                .iter()
                .filter(|(k, _)| !TYPED.contains(&k.as_str()))
                .map(|(k, v)| (k.clone(), v.clone()))
                .collect(),
        }
    }

    /// Lit `settings.json` (ou sa sauvegarde). Ne renvoie jamais d'erreur : au pire, les valeurs par
    /// défaut et un avertissement.
    pub fn load(path: &Path) -> Loaded {
        let (payload, warning) = load_payload(path);
        Loaded { settings: Self::from_payload(&payload), warning }
    }

    /// Le contenu JSON à écrire : les sections dans l'ordre de la 2.8, puis les sections inconnues.
    pub fn to_payload(&self) -> Map<String, Value> {
        let typed = |name: &str| -> Option<Value> {
            match name {
                "projection" => serde_json::to_value(&self.projection).ok(),
                "appearance" => serde_json::to_value(&self.appearance).ok(),
                "hdmi" => serde_json::to_value(&self.hdmi).ok(),
                "split" => serde_json::to_value(&self.split).ok(),
                _ => None,
            }
        };
        let mut out = Map::new();
        for name in ORDER {
            if let Some(value) = typed(name).or_else(|| self.other.get(name).cloned()) {
                out.insert(name.to_string(), value);
            }
        }
        for (name, value) in &self.other {
            if !out.contains_key(name) {
                out.insert(name.clone(), value.clone());
            }
        }
        out
    }

    /// Écrit les réglages : fichier temporaire, puis renommage, puis la même chose pour le `.bak`.
    /// Un fichier existant illisible est d'abord mis de côté (`settings.json.corrupt-…`).
    pub fn save(&self, path: &Path) -> Result<(), SettingsError> {
        let err = |source| SettingsError::Write { path: path.to_path_buf(), source };
        let mut data = serde_json::to_string_pretty(&Value::Object(self.to_payload())).map_err(|e| err(e.into()))?;
        data.push('\n');
        if let Some(dir) = path.parent() {
            std::fs::create_dir_all(dir).map_err(err)?;
        }
        if path.exists() && read_object(path).is_err() {
            let stamp =
                std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_millis()).unwrap_or(0);
            let mut aside = path.as_os_str().to_owned();
            aside.push(format!(".corrupt-{stamp}"));
            std::fs::copy(path, PathBuf::from(aside)).map_err(err)?;
        }
        publish(path, data.as_bytes()).map_err(err)?;
        publish(&backup_path(path), data.as_bytes()).map_err(err)
    }
}

/// Écrit `data` dans `path` sans jamais laisser un fichier à moitié écrit.
fn publish(path: &Path, data: &[u8]) -> std::io::Result<()> {
    let dir = path.parent().unwrap_or(Path::new("."));
    let name = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    let temporary = dir.join(format!("{name}.{}.tmp", std::process::id()));
    let result = (|| {
        let mut file = std::fs::File::create(&temporary)?;
        file.write_all(data)?;
        file.sync_all()?;
        drop(file);
        std::fs::rename(&temporary, path)
    })();
    if result.is_err() {
        let _ = std::fs::remove_file(&temporary);
    }
    result
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    /// Un dossier temporaire sous `target/tmp` : sur certains postes, le dossier temporaire de
    /// Windows est fermé en écriture aux programmes de test.
    fn scratch() -> tempfile::TempDir {
        let base = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
        std::fs::create_dir_all(&base).unwrap();
        tempfile::tempdir_in(base).unwrap()
    }

    #[test]
    fn missing_file_gives_defaults_without_warning() {
        let dir = scratch();
        let loaded = Settings::load(&dir.path().join("settings.json"));
        assert_eq!(loaded.settings, Settings::default());
        assert_eq!(loaded.warning, None);
    }

    #[test]
    fn values_are_read_like_python() {
        let payload = json!({
            "projection": {"text_size": "4", "ref_size": -3, "line_height": 0.1, "panel_opacity": 7,
                           "font_family": "  ", "uppercase": "non", "bg_mode": "image", "bg_image": "Z:/absent.png",
                           "media_default_duration": 999, "auto_fit": true},
            "appearance": {"theme": "LIGHT", "language": "de", "mica": null},
            "split": {"max_chars": "5000", "hymn_max_lines": 2.9, "text_enabled": 0},
            "hdmi": {"key_color": " Magenta ", "text_scale": 0, "offset_y": -900,
                     "style": {"text_size": 30.5, "accent_mode": "AUTO", "line_height": "3", "bg_color_2": "",
                               "bg_color": " ", "letter_spacing": "x"}},
        });
        let s = Settings::from_payload(payload.as_object().unwrap());
        assert_eq!((s.projection.text_size, s.projection.ref_size), (8, 24));
        assert_eq!(s.projection.line_height, 0.5);
        assert_eq!(s.projection.panel_opacity, 1.0);
        assert_eq!(s.projection.font_family, "Poppins");
        assert!(s.projection.uppercase && !s.projection.auto_fit);
        assert_eq!(s.projection.bg_mode, "color");
        assert_eq!(s.projection.media_default_duration, 120);
        assert_eq!(
            (s.appearance.theme.as_str(), s.appearance.language.as_str(), s.appearance.mica),
            ("light", "fr", false)
        );
        assert_eq!((s.split.max_chars, s.split.hymn_max_lines, s.split.text_enabled), (800, 2, false));
        assert_eq!((s.hdmi.key_color.as_str(), s.hdmi.text_scale, s.hdmi.offset_y), ("magenta", 100, -300));
        let style = &s.hdmi.style;
        assert_eq!((style.text_size, style.accent_mode.as_str(), style.line_height), (30, "auto", 2.0));
        assert_eq!(
            (style.bg_color_2.as_str(), style.bg_color.as_str(), style.letter_spacing),
            ("", "rgba(10, 14, 22, 0.94)", 0)
        );
    }

    #[test]
    fn unknown_sections_survive_a_round_trip() {
        let dir = scratch();
        let path = dir.path().join("settings.json");
        std::fs::write(
            &path,
            r#"{"church": {"name": "Tabernacle"}, "projection": {"text_size": 45}, "futur": [1, 2]}"#,
        )
        .unwrap();
        let loaded = Settings::load(&path);
        loaded.settings.save(&path).unwrap();
        let written: Value = serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
        let keys: Vec<&str> = written.as_object().unwrap().keys().map(String::as_str).collect();
        assert_eq!(keys, ["projection", "appearance", "hdmi", "split", "church", "futur"]);
        assert_eq!(written["church"], json!({"name": "Tabernacle"}));
        assert_eq!(written["projection"]["text_size"], json!(45));
        assert_eq!(std::fs::read(&path).unwrap(), std::fs::read(backup_path(&path)).unwrap());
    }

    #[test]
    fn unreadable_file_falls_back_to_backup_and_is_kept_aside() {
        let dir = scratch();
        let path = dir.path().join("settings.json");
        std::fs::write(backup_path(&path), r#"{"projection": {"text_size": 50}}"#).unwrap();
        std::fs::write(&path, "{ cassé").unwrap();
        let loaded = Settings::load(&path);
        assert_eq!(loaded.warning, Some(RECOVERED_FROM_BACKUP));
        assert_eq!(loaded.settings.projection.text_size, 50);
        loaded.settings.save(&path).unwrap();
        let aside = std::fs::read_dir(dir.path())
            .unwrap()
            .flatten()
            .filter(|e| e.file_name().to_string_lossy().contains(".corrupt-"))
            .count();
        assert_eq!(aside, 1);
        std::fs::write(&path, "[]").unwrap();
        std::fs::write(backup_path(&path), "nul").unwrap();
        assert_eq!(Settings::load(&path).warning, Some(UNREADABLE));
    }
}
