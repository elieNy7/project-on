//! Les données de la bêta : une COPIE de celles de la 2.x, faite au premier lancement.
//!
//! La bêta travaille dans `%APPDATA%\Project-On 3 (bêta)` et ne touche jamais au dossier de la 2.x :
//! la base y est seulement lue (API de sauvegarde de SQLite, comme une sauvegarde de la 2.8), et
//! `settings.json` y est seulement copié. Une copie déjà présente n'est jamais écrasée.
//!
//! Après le lancement, la base est lue une fois en arrière-plan : la première recherche d'un culte
//! n'attend plus le disque (6 s → 0,1 s mesurés en phase 1).

use std::io::Read;
use std::path::{Path, PathBuf};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use po_core::DataPaths;

/// Ce que la copie a fait.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CopyReport {
    /// Taille de la base copiée, en octets.
    pub database_bytes: u64,
    /// `settings.json` copié (absent dans la 2.x, ou déjà présent dans la bêta : non).
    pub settings: bool,
    pub elapsed: Duration,
}

/// La bêta n'a pas encore de base : il faut copier celle de la 2.x.
pub fn needs_copy(beta: &DataPaths) -> bool {
    !beta.database().is_file()
}

/// Copie la base et les réglages de la 2.x dans la bêta. Ne remplace jamais un fichier de la bêta.
pub fn copy_from_legacy(legacy: &DataPaths, beta: &DataPaths) -> Result<CopyReport, String> {
    let started = Instant::now();
    if beta.database().exists() {
        return Err("la bêta a déjà sa base : rien n'est copié".into());
    }
    std::fs::create_dir_all(beta.data()).map_err(|e| format!("dossier de la bêta : {e}"))?;
    let report = po_db::copy_database(&legacy.database(), &beta.database())
        .map_err(|e| format!("copie de la base de la 2.x : {e}"))?;
    let mut settings = false;
    if legacy.settings().is_file() && !beta.settings().exists() {
        std::fs::copy(legacy.settings(), beta.settings()).map_err(|e| format!("copie des réglages : {e}"))?;
        settings = true;
    }
    Ok(CopyReport { database_bytes: report.size_bytes, settings, elapsed: started.elapsed() })
}

/// Lit tout le fichier `path` une fois, en arrière-plan, pour que Windows le garde en mémoire. Rend
/// le nombre d'octets lus et la durée.
pub fn warm_up(path: PathBuf) -> JoinHandle<(u64, Duration)> {
    std::thread::Builder::new()
        .name("prechauffage-base".into())
        .spawn(move || {
            let started = Instant::now();
            let mut total = 0u64;
            if let Ok(mut file) = std::fs::File::open(&path) {
                let mut buffer = vec![0u8; 4 << 20];
                while let Ok(n) = file.read(&mut buffer) {
                    if n == 0 {
                        break;
                    }
                    total += n as u64;
                }
            }
            (total, started.elapsed())
        })
        .unwrap_or_else(|_| std::thread::spawn(|| (0, Duration::ZERO)))
}

/// Où sont les données : la bêta, et la 2.x d'où elle est copiée.
#[derive(Debug, Clone)]
pub struct Locations {
    pub beta: DataPaths,
    pub legacy: Option<DataPaths>,
}

impl Locations {
    /// Les dossiers de ce poste (`PROJECT_ON_DATA` impose celui de la bêta).
    pub fn current() -> Result<Self, String> {
        let env = po_core::paths::Environment::current();
        let beta = po_core::paths::beta_root(&env).map_err(|e| e.to_string())?;
        let legacy = po_core::paths::legacy_root(&env).ok().filter(|l| l.database().is_file());
        Ok(Locations { beta, legacy })
    }

    pub fn at(beta: impl Into<PathBuf>, legacy: Option<&Path>) -> Self {
        Locations { beta: DataPaths::at(beta), legacy: legacy.map(DataPaths::at) }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use po_db::{Database, InitOptions, Mode};

    fn scratch() -> tempfile::TempDir {
        let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
        std::fs::create_dir_all(&base).unwrap();
        tempfile::tempdir_in(base).unwrap()
    }

    #[test]
    fn the_beta_copies_once_and_never_overwrites() {
        let dir = scratch();
        let legacy = DataPaths::at(dir.path().join("Project-On"));
        let beta = DataPaths::at(dir.path().join("Project-On 3 (bêta)"));
        std::fs::create_dir_all(legacy.data()).unwrap();
        let (mut db, _) = Database::open_and_initialize(&legacy.database(), &InitOptions::default()).unwrap();
        db.create_folder("Culte du dimanche").unwrap();
        std::fs::write(legacy.settings(), r#"{"projection": {"font_family": "Poppins"}}"#).unwrap();
        let legacy_bytes = std::fs::read(legacy.settings()).unwrap();

        assert!(needs_copy(&beta));
        let report = copy_from_legacy(&legacy, &beta).unwrap();
        assert!(report.database_bytes > 0 && report.settings);
        assert!(!needs_copy(&beta));
        let copy = Database::open(&beta.database(), Mode::ReadOnly).unwrap();
        assert!(copy.list_folders().unwrap().iter().any(|f| f.name == "Culte du dimanche"));
        // La 2.x n'a pas changé ; une seconde copie est refusée.
        assert_eq!(std::fs::read(legacy.settings()).unwrap(), legacy_bytes);
        assert!(copy_from_legacy(&legacy, &beta).is_err());

        let (bytes, _) = warm_up(beta.database()).join().unwrap();
        assert_eq!(bytes, std::fs::metadata(beta.database()).unwrap().len());
    }
}
