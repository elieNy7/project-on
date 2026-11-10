//! Les dossiers de données.
//!
//! - La **2.x** garde ses données dans le dossier choisi à l'installation (registre
//!   `HKCU\Software\Project-On\DataPath`, qui désigne le sous-dossier `data`), sinon dans
//!   `%APPDATA%\Project-On`, sinon dans `%LOCALAPPDATA%\Project-On` (`app_paths.user_data_dir`).
//! - La **bêta 3.0** travaille sur une copie, dans `%APPDATA%\Project-On 3 (bêta)` : les vraies
//!   données ne sont touchées qu'à la bascule.
//! - `PROJECT_ON_DATA` impose un dossier (développement, essais) : rien d'autre n'est lu.
//!
//! Dans chaque dossier : `data\project_on.db`, `data\settings.json`, `data\logs\`, `backgrounds\`,
//! `media\`.

use std::ffi::OsString;
use std::path::{Path, PathBuf};

/// Le dossier de la 2.x sous `%APPDATA%`.
pub const LEGACY_DIR: &str = "Project-On";
/// Le dossier de la bêta 3.0 sous `%APPDATA%`.
pub const BETA_DIR: &str = "Project-On 3 (bêta)";
/// Variable d'environnement qui impose le dossier des données.
pub const DATA_ENV: &str = "PROJECT_ON_DATA";

#[derive(Debug, thiserror::Error)]
pub enum PathError {
    #[error("Windows ne donne ni %APPDATA% ni %LOCALAPPDATA% : impossible de savoir où ranger les données.")]
    NoAppData,
}

/// Les chemins d'un dossier de données.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DataPaths {
    root: PathBuf,
}

impl DataPaths {
    pub fn at(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    pub fn root(&self) -> &Path {
        &self.root
    }

    /// `data\` : la base, les réglages, le journal.
    pub fn data(&self) -> PathBuf {
        self.root.join("data")
    }

    pub fn database(&self) -> PathBuf {
        self.data().join("project_on.db")
    }

    pub fn settings(&self) -> PathBuf {
        self.data().join("settings.json")
    }

    pub fn logs(&self) -> PathBuf {
        self.data().join("logs")
    }

    /// Les images de fond.
    pub fn backgrounds(&self) -> PathBuf {
        self.root.join("backgrounds")
    }

    /// La bibliothèque des médias.
    pub fn media(&self) -> PathBuf {
        self.root.join("media")
    }
}

/// Les variables d'environnement lues, pour pouvoir tester la résolution sans les modifier.
#[derive(Debug, Clone, Default)]
pub struct Environment {
    pub data_override: Option<OsString>,
    pub appdata: Option<OsString>,
    pub local_appdata: Option<OsString>,
    /// `HKCU\Software\Project-On\DataPath`.
    pub registry_data_path: Option<String>,
}

impl Environment {
    /// L'environnement de ce processus.
    pub fn current() -> Self {
        let non_empty = |name: &str| std::env::var_os(name).filter(|v| !v.is_empty());
        Self {
            data_override: non_empty(DATA_ENV),
            appdata: non_empty("APPDATA"),
            local_appdata: non_empty("LOCALAPPDATA"),
            registry_data_path: registry_data_path(),
        }
    }
}

#[cfg(windows)]
fn registry_data_path() -> Option<String> {
    windows_registry::CURRENT_USER
        .open(r"Software\Project-On")
        .and_then(|key| key.get_string("DataPath"))
        .ok()
        .filter(|p| !p.is_empty())
}

#[cfg(not(windows))]
fn registry_data_path() -> Option<String> {
    None
}

/// Le dossier de la 2.x, comme `app_paths.user_data_dir()` : celui de l'installeur s'il existe,
/// sinon `%APPDATA%\Project-On`, sinon `%LOCALAPPDATA%\Project-On`.
pub fn legacy_root(env: &Environment) -> Result<DataPaths, PathError> {
    if let Some(data) = env.registry_data_path.as_deref().map(Path::new).filter(|p| p.exists())
        && let Some(parent) = data.parent()
    {
        return Ok(DataPaths::at(parent));
    }
    if let Some(appdata) = &env.appdata {
        return Ok(DataPaths::at(Path::new(appdata).join(LEGACY_DIR)));
    }
    env.local_appdata.as_ref().map(|local| DataPaths::at(Path::new(local).join(LEGACY_DIR))).ok_or(PathError::NoAppData)
}

/// Le dossier de la bêta 3.0 (ou celui de `PROJECT_ON_DATA`).
pub fn beta_root(env: &Environment) -> Result<DataPaths, PathError> {
    if let Some(forced) = &env.data_override {
        return Ok(DataPaths::at(forced));
    }
    env.appdata
        .as_ref()
        .or(env.local_appdata.as_ref())
        .map(|base| DataPaths::at(Path::new(base).join(BETA_DIR)))
        .ok_or(PathError::NoAppData)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Un dossier temporaire sous `target/tmp` : sur certains postes, le dossier temporaire de
    /// Windows est fermé en écriture aux programmes de test.
    fn scratch() -> tempfile::TempDir {
        let base = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
        std::fs::create_dir_all(&base).unwrap();
        tempfile::tempdir_in(base).unwrap()
    }

    fn env() -> Environment {
        Environment {
            appdata: Some(r"C:\Users\x\AppData\Roaming".into()),
            local_appdata: Some(r"C:\Users\x\AppData\Local".into()),
            ..Default::default()
        }
    }

    #[test]
    fn layout_of_a_data_folder() {
        let paths = DataPaths::at(r"C:\D");
        assert_eq!(paths.database(), Path::new(r"C:\D\data\project_on.db"));
        assert_eq!(paths.settings(), Path::new(r"C:\D\data\settings.json"));
        assert_eq!(paths.logs(), Path::new(r"C:\D\data\logs"));
        assert_eq!(paths.media(), Path::new(r"C:\D\media"));
    }

    #[test]
    fn beta_never_uses_the_legacy_folder() {
        let env = env();
        assert_eq!(legacy_root(&env).unwrap().root(), Path::new(r"C:\Users\x\AppData\Roaming\Project-On"));
        assert_eq!(beta_root(&env).unwrap().root(), Path::new(r"C:\Users\x\AppData\Roaming\Project-On 3 (bêta)"));
        let forced = Environment { data_override: Some(r"D:\essai".into()), ..env };
        assert_eq!(beta_root(&forced).unwrap().root(), Path::new(r"D:\essai"));
    }

    #[test]
    fn installer_folder_wins_when_it_exists() {
        let dir = scratch();
        let data = dir.path().join("data");
        std::fs::create_dir(&data).unwrap();
        let env = Environment { registry_data_path: Some(data.to_string_lossy().into_owned()), ..env() };
        assert_eq!(legacy_root(&env).unwrap().root(), dir.path());
        // Un dossier d'installeur disparu : retour à %APPDATA%.
        let gone = Environment { registry_data_path: Some(r"Z:\absent\data".into()), ..env };
        assert_eq!(legacy_root(&gone).unwrap().root(), Path::new(r"C:\Users\x\AppData\Roaming\Project-On"));
    }

    #[test]
    fn no_appdata_is_an_error() {
        assert!(matches!(beta_root(&Environment::default()), Err(PathError::NoAppData)));
        assert!(matches!(legacy_root(&Environment::default()), Err(PathError::NoAppData)));
    }
}
