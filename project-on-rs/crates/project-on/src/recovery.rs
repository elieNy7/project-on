//! La reprise après coupure (`live_recovery.py` de la 2.8) : le programme au direct survit à un
//! arrêt brutal. À chaque changement du direct, il est enregistré d'un coup (fichier temporaire
//! puis renommage) dans `data\live-recovery.json`. Une fermeture normale efface le fichier ; s'il est
//! encore là au démarrage, Project-On s'est arrêté pendant un culte (coupure de courant, plantage) et
//! l'opérateur peut reprendre exactement où il était. Un fichier de plus de 12 heures est ignoré.

use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use po_program::Program;
use serde::{Deserialize, Serialize};

use crate::library::Origin;

/// Au-delà, la reprise n'est plus proposée (`MAX_AGE` de la 2.8).
pub const MAX_AGE: Duration = Duration::from_secs(12 * 3600);

/// Le direct enregistré.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Snapshot {
    pub program: Program,
    pub origin: Origin,
    /// Pour une playlist : l'élément d'origine de chaque entrée.
    pub items: Vec<i64>,
    pub hidden: bool,
    /// Secondes depuis 1970.
    pub saved_at: u64,
}

fn now() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map_or(0, |d| d.as_secs())
}

/// Le fichier de reprise, dans le dossier de données.
pub fn file(data_dir: &Path) -> PathBuf {
    data_dir.join("live-recovery.json")
}

/// Enregistre le direct.
pub fn save(path: &Path, program: &Program, origin: &Origin, items: &[i64], hidden: bool) -> std::io::Result<()> {
    let snapshot =
        Snapshot { program: program.clone(), origin: origin.clone(), items: items.to_vec(), hidden, saved_at: now() };
    let json = serde_json::to_string(&snapshot).map_err(std::io::Error::other)?;
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let tmp = path.with_extension("json.tmp");
    std::fs::write(&tmp, json)?;
    std::fs::rename(&tmp, path)
}

/// Le direct laissé par un arrêt brutal, s'il est récent et lisible.
pub fn load(path: &Path) -> Option<Snapshot> {
    let text = std::fs::read_to_string(path).ok()?;
    let snapshot: Snapshot = serde_json::from_str(&text).ok()?;
    let age = now().saturating_sub(snapshot.saved_at);
    (age <= MAX_AGE.as_secs() && !snapshot.program.is_empty()).then_some(snapshot)
}

/// Fermeture normale, ou reprise refusée : plus rien à reprendre.
pub fn clear(path: &Path) {
    let _ = std::fs::remove_file(path);
}

#[cfg(test)]
mod tests {
    use super::*;
    use po_design::SlideSource;
    use po_program::{Cue, Entry};

    fn scratch(name: &str) -> PathBuf {
        let dir = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/tmp")
            .join(format!("reprise-{}-{name}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        dir
    }

    #[test]
    fn the_live_program_comes_back_after_a_crash_but_not_after_a_normal_exit() {
        let dir = scratch("direct");
        let path = file(&dir);
        let cue = Cue::new(
            SlideSource::Bible,
            "Jean 3",
            vec![Entry::new("Jean 3:16", "Car Dieu a tant aimé le monde"), Entry::new("Jean 3:17", "Dieu, en effet")],
            0,
        );
        let mut program = Program::from_cue(&cue, &po_settings::SplitSettings::default()).unwrap();
        program.set(1);
        save(&path, &program, &Origin::Playlist(7), &[11, 12], true).unwrap();
        let back = load(&path).expect("reprise proposée");
        assert_eq!(back.program, program);
        assert_eq!(back.program.current(), 1);
        assert_eq!((back.origin.clone(), back.items.clone(), back.hidden), (Origin::Playlist(7), vec![11, 12], true));
        // Fermeture normale : plus rien.
        clear(&path);
        assert!(load(&path).is_none());
        // Trop vieux, ou abîmé : ignoré.
        let old = Snapshot { saved_at: now() - MAX_AGE.as_secs() - 60, ..back };
        std::fs::write(&path, serde_json::to_string(&old).unwrap()).unwrap();
        assert!(load(&path).is_none());
        std::fs::write(&path, "{ abîmé").unwrap();
        assert!(load(&path).is_none());
        let _ = std::fs::remove_dir_all(&dir);
    }
}
