//! L'entretien : les **sauvegardes** de la base (copie cohérente pendant l'utilisation, avec les
//! réglages, les 10 dernières gardées) et le **contrôle avant culte** (Ctrl+Shift+D), une liste de
//! vérifications avec, pour chacune, ce qu'il faut faire.

use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime};

/// Combien de sauvegardes garder.
pub const KEEP: usize = 10;

/// Une sauvegarde : le dossier `sauvegardes\AAAA-MM-JJ_HHMMSS` (base et réglages).
#[derive(Debug, Clone, PartialEq)]
pub struct Backup {
    pub dir: PathBuf,
    pub when: SystemTime,
    pub bytes: u64,
}

/// « 2026-11-11_103005 » pour un horodatage local (heures, minutes, secondes depuis minuit).
pub fn stamp(date: &str, seconds: f64) -> String {
    let s = seconds.max(0.0) as u64;
    format!("{date}_{:02}{:02}{:02}", s / 3600 % 24, s % 3600 / 60, s % 60)
}

/// Sauvegarde la base `database` (et `settings`, s'il existe) dans `root\<stamp>`, puis ne garde que
/// les [`KEEP`] dernières.
pub fn backup(database: &Path, settings: &Path, root: &Path, stamp: &str) -> Result<Backup, String> {
    let dir = root.join(stamp);
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let report = po_db::copy_database(database, &dir.join("project_on.db")).map_err(|e| e.to_string())?;
    if settings.is_file() {
        std::fs::copy(settings, dir.join("settings.json")).map_err(|e| e.to_string())?;
    }
    prune(root);
    Ok(Backup { dir, when: SystemTime::now(), bytes: report.size_bytes })
}

/// Les sauvegardes, la plus récente d'abord.
pub fn list(root: &Path) -> Vec<Backup> {
    let Ok(entries) = std::fs::read_dir(root) else { return Vec::new() };
    let mut out: Vec<Backup> = entries
        .flatten()
        .filter(|e| e.path().join("project_on.db").is_file())
        .map(|e| {
            let db = e.path().join("project_on.db");
            let meta = std::fs::metadata(&db).ok();
            Backup {
                dir: e.path(),
                when: meta.as_ref().and_then(|m| m.modified().ok()).unwrap_or(SystemTime::UNIX_EPOCH),
                bytes: meta.map_or(0, |m| m.len()),
            }
        })
        .collect();
    // Les noms sont des dates : l'ordre alphabétique est l'ordre du temps.
    out.sort_by(|a, b| b.dir.file_name().cmp(&a.dir.file_name()));
    out
}

fn prune(root: &Path) {
    for old in list(root).into_iter().skip(KEEP) {
        let _ = std::fs::remove_dir_all(old.dir);
    }
}

/// Le résultat d'une vérification.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Level {
    Ok,
    Warning,
    Problem,
}

/// Une vérification du contrôle avant culte.
#[derive(Debug, Clone, PartialEq)]
pub struct Check {
    pub level: Level,
    pub title: String,
    pub detail: String,
}

/// Ce que le contrôle avant culte regarde.
#[derive(Debug, Clone)]
pub struct Situation {
    pub database_open: bool,
    pub screens: usize,
    pub font_families: usize,
    /// L'adresse du serveur Web, ou son erreur.
    pub web: Option<Result<String, String>>,
    /// La bibliothèque NDI : son chemin, ou pourquoi elle manque.
    pub ndi: Result<String, String>,
    pub last_backup: Option<Duration>,
    /// Les fichiers d'images ou de vidéos de la playlist choisie qui manquent.
    pub missing_media: Vec<String>,
    pub playlist: Option<(String, usize)>,
}

fn check(level: Level, title: &str, detail: impl Into<String>) -> Check {
    Check { level, title: title.into(), detail: detail.into() }
}

/// Le contrôle avant culte.
pub fn preflight(s: &Situation) -> Vec<Check> {
    let mut out = Vec::new();
    out.push(if s.database_open {
        check(Level::Ok, "Base de données", "Ouverte : Bible, cantiques, prédications et playlists disponibles.")
    } else {
        check(
            Level::Problem,
            "Base de données",
            "Aucune base ouverte : relancez Project-On ou restaurez une sauvegarde.",
        )
    });
    out.push(match s.screens {
        0 => check(Level::Problem, "Écrans", "Aucun écran détecté."),
        1 => check(
            Level::Warning,
            "Écrans",
            "Un seul écran : branchez le vidéoprojecteur (la projection s'ouvrirait dans une fenêtre).",
        ),
        n => check(Level::Ok, "Écrans", format!("{n} écrans : la projection ira sur l'écran de la salle.")),
    });
    out.push(if s.font_families >= 10 {
        check(Level::Ok, "Polices", format!("{} familles chargées.", s.font_families))
    } else {
        check(Level::Warning, "Polices", "Peu de polices trouvées : réinstallez Project-On.")
    });
    out.push(match &s.web {
        Some(Ok(addr)) => check(Level::Ok, "Écrans Web", format!("Prêts sur {addr}.")),
        Some(Err(e)) => check(Level::Warning, "Écrans Web", e.clone()),
        None => check(Level::Warning, "Écrans Web", "Serveur Web arrêté."),
    });
    out.push(match &s.ndi {
        Ok(_) => check(Level::Ok, "NDI", "Bibliothèque NDI disponible."),
        Err(_) => check(
            Level::Warning,
            "NDI",
            "Pas de NDI sur ce poste (facultatif) : installez le runtime NDI 6 pour l'utiliser.",
        ),
    });
    out.push(match s.last_backup {
        Some(age) if age < Duration::from_secs(7 * 86_400) => {
            check(Level::Ok, "Sauvegarde", format!("Dernière sauvegarde il y a {} jour(s).", age.as_secs() / 86_400))
        }
        Some(_) => {
            check(Level::Warning, "Sauvegarde", "Plus d'une semaine sans sauvegarde : faites-en une (Réglages).")
        }
        None => check(Level::Warning, "Sauvegarde", "Aucune sauvegarde : faites-en une avant le culte (Réglages)."),
    });
    match &s.playlist {
        Some((name, count)) if s.missing_media.is_empty() => {
            out.push(check(
                Level::Ok,
                "Playlist",
                format!("« {name} » : {count} élément(s), tous les fichiers sont là."),
            ));
        }
        Some((name, _)) => out.push(check(
            Level::Problem,
            "Playlist",
            format!("« {name} » : fichier(s) introuvable(s) : {}", s.missing_media.join(", ")),
        )),
        None => out.push(check(Level::Warning, "Playlist", "Aucune playlist choisie pour le culte.")),
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn backups_are_consistent_copies_and_only_the_last_ten_are_kept() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/tmp")
            .join(format!("sauvegardes-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let source = root.join("source");
        std::fs::create_dir_all(&source).unwrap();
        let db = source.join("project_on.db");
        po_db::Database::open_and_initialize(&db, &po_db::InitOptions::default()).unwrap();
        std::fs::write(source.join("settings.json"), "{}").unwrap();
        let backups = root.join("sauvegardes");
        for i in 0..12 {
            let b = backup(&db, &source.join("settings.json"), &backups, &stamp("2026-11-11", 36_000.0 + f64::from(i)))
                .unwrap();
            assert!(b.bytes > 0);
            assert!(b.dir.join("settings.json").is_file());
        }
        let list = list(&backups);
        assert_eq!(list.len(), KEEP);
        assert!(list[0].dir.ends_with("2026-11-11_100011"), "la plus récente d'abord");
        assert!(po_db::Database::open(&list[0].dir.join("project_on.db"), po_db::Mode::ReadOnly).is_ok());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn the_preflight_says_what_to_do() {
        let ok = Situation {
            database_open: true,
            screens: 2,
            font_families: 40,
            web: Some(Ok("127.0.0.1:8090".into())),
            ndi: Ok("ndi.dll".into()),
            last_backup: Some(Duration::from_secs(3600)),
            missing_media: Vec::new(),
            playlist: Some(("Dimanche".into(), 12)),
        };
        assert!(preflight(&ok).iter().all(|c| c.level == Level::Ok));
        let bad = Situation { screens: 1, missing_media: vec!["photo.jpg".into()], last_backup: None, ..ok };
        let checks = preflight(&bad);
        assert!(checks.iter().any(|c| c.title == "Écrans" && c.level == Level::Warning));
        assert!(
            checks.iter().any(|c| c.title == "Playlist" && c.level == Level::Problem && c.detail.contains("photo.jpg"))
        );
        assert!(checks.iter().any(|c| c.title == "Sauvegarde" && c.level == Level::Warning));
    }
}
