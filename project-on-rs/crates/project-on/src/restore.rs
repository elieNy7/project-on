//! La **restauration** d'une sauvegarde : une sauvegarde de la 3.0 (`sauvegardes\<date>`, base et
//! réglages), ou une archive complète de la 2.8 (`project-on-complet-….zip` : base, médias, fonds,
//! réglages sans secrets).
//!
//! La base en service n'est jamais remplacée pendant qu'elle est ouverte. La restauration se fait en
//! deux temps :
//! 1. **Préparer** (dans la régie) : la sauvegarde est vérifiée (contrôle d'intégrité de SQLite ; pour
//!    une archive de la 2.8, les mêmes règles que sa propre restauration : manifeste, tailles,
//!    empreintes SHA-256, noms de fichiers sûrs) et copiée dans `restauration-en-attente`. Les médias
//!    d'une archive sont rangés dans `restaurés\<date>` et la base pointe vers eux.
//! 2. **Appliquer** (au démarrage suivant, avant d'ouvrir la base) : la base et les réglages actuels
//!    sont d'abord sauvegardés (`sauvegardes\<date>-avant-restauration`), puis remplacés.
//!
//! La 2.8 ne savait que reconstruire un profil à côté, à rouvrir à la main ; ici, on revient en
//! arrière d'un clic, et la restauration elle-même peut être défaite (la sauvegarde d'avant).

use std::io::Read;
use std::path::{Path, PathBuf};

use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};

/// Le dossier de la restauration préparée, dans les données.
pub const PENDING: &str = "restauration-en-attente";
/// Les médias et fonds des archives restaurées, dans les données.
pub const RESTORED: &str = "restaurés";

const MAX_BYTES: u64 = 50 * 1024 * 1024 * 1024;
const MAX_FILES: usize = 100_000;
const MAX_MANIFEST: u64 = 16 * 1024 * 1024;
/// Les champs de la base qui désignent un fichier projeté (`_REFERENCE_FIELDS` de la 2.8).
const REFERENCE_FIELDS: [(&str, &str); 2] = [("media_item", "path"), ("playlist_item", "background")];

/// La restauration préparée : ce qu'elle remettra (« la sauvegarde du 2026-11-11_103005 »).
pub fn pending(data: &Path) -> Option<String> {
    let dir = data.join(PENDING);
    if !dir.join("project_on.db").is_file() {
        return None;
    }
    let about = std::fs::read_to_string(dir.join("restauration.json")).ok();
    let label = about
        .and_then(|t| serde_json::from_str::<Value>(&t).ok())
        .and_then(|v| v.get("label").and_then(Value::as_str).map(str::to_string));
    Some(label.unwrap_or_else(|| "une sauvegarde".into()))
}

/// Renonce à la restauration préparée.
pub fn cancel(data: &Path) {
    let _ = std::fs::remove_dir_all(data.join(PENDING));
}

fn fresh_pending(data: &Path) -> Result<PathBuf, String> {
    let dir = data.join(PENDING);
    if dir.exists() {
        std::fs::remove_dir_all(&dir).map_err(|e| format!("restauration précédente : {e}"))?;
    }
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir)
}

fn write_label(dir: &Path, label: &str) -> Result<(), String> {
    std::fs::write(dir.join("restauration.json"), json!({ "label": label }).to_string()).map_err(|e| e.to_string())
}

/// Prépare la restauration d'une sauvegarde de la 3.0 (un dossier de `sauvegardes`).
pub fn prepare_backup(backup: &Path, data: &Path) -> Result<String, String> {
    let name = backup.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
    let label = format!("la sauvegarde du {name}");
    let dir = fresh_pending(data)?;
    let result = (|| {
        // Copiée par SQLite et vérifiée : une sauvegarde abîmée est refusée ici, pas au démarrage.
        po_db::copy_database(&backup.join("project_on.db"), &dir.join("project_on.db"))
            .map_err(|e| format!("Sauvegarde illisible : {e}"))?;
        let settings = backup.join("settings.json");
        if settings.is_file() {
            let text = std::fs::read_to_string(&settings).map_err(|e| e.to_string())?;
            serde_json::from_str::<Value>(&text).map_err(|e| format!("Réglages de la sauvegarde illisibles : {e}"))?;
            std::fs::write(dir.join("settings.json"), text).map_err(|e| e.to_string())?;
        }
        write_label(&dir, &label)
    })();
    if result.is_err() {
        cancel(data);
    }
    result.map(|()| label)
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// Un nom de membre d'archive sûr (`_bundle_member` de la 2.8).
fn bundle_member(name: &str) -> Result<(), String> {
    if name.is_empty() || name.contains('\\') || name.contains(':') || name.starts_with('/') {
        return Err(format!("Chemin d'archive invalide : {name}"));
    }
    let parts: Vec<&str> = name.split('/').collect();
    if parts.iter().any(|p| p.is_empty() || *p == "." || *p == "..") {
        return Err(format!("Chemin d'archive hors profil : {name}"));
    }
    if !matches!(parts[0], "data" | "media" | "backgrounds") {
        return Err(format!("Dossier d'archive non autorisé : {name}"));
    }
    let reserved = |p: &str| {
        let stem = p.split('.').next().unwrap_or("").to_lowercase();
        matches!(stem.as_str(), "con" | "prn" | "aux" | "nul")
            || (stem.len() == 4
                && (stem.starts_with("com") || stem.starts_with("lpt"))
                && stem.as_bytes()[3].is_ascii_digit())
    };
    if parts.iter().any(|p| p.ends_with(' ') || p.ends_with('.') || reserved(p)) {
        return Err(format!("Nom de fichier non portable : {name}"));
    }
    Ok(())
}

/// Les réglages sans secrets (`_safe_settings` de la 2.8).
fn safe_settings(value: Value) -> Value {
    match value {
        Value::Object(map) => Value::Object(
            map.into_iter()
                .filter(|(k, _)| {
                    let k = k.to_lowercase();
                    !["password", "secret", "token", "credential", "api_key"].iter().any(|w| k.contains(w))
                })
                .map(|(k, v)| (k, safe_settings(v)))
                .collect::<Map<_, _>>(),
        ),
        Value::Array(items) => Value::Array(items.into_iter().map(safe_settings).collect()),
        other => other,
    }
}

/// Les chemins des réglages qui désignaient un fichier de l'archive pointent vers sa copie.
fn relocate_settings(value: Value, mapping: &std::collections::HashMap<String, String>) -> Value {
    match value {
        Value::Object(map) => Value::Object(map.into_iter().map(|(k, v)| (k, relocate_settings(v, mapping))).collect()),
        Value::Array(items) => Value::Array(items.into_iter().map(|v| relocate_settings(v, mapping)).collect()),
        Value::String(s) => Value::String(mapping.get(&s).cloned().unwrap_or(s)),
        other => other,
    }
}

/// Prépare la restauration d'une archive complète de la 2.8. `stamp` nomme le dossier des médias
/// (`restaurés\<stamp>`).
pub fn prepare_archive(archive: &Path, data: &Path, stamp: &str) -> Result<String, String> {
    let label =
        format!("l'archive « {} »", archive.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default());
    let dir = fresh_pending(data)?;
    let media_root = data.join(RESTORED).join(stamp);
    let result = extract_archive(archive, &dir, &media_root).and_then(|()| write_label(&dir, &label));
    if result.is_err() {
        cancel(data);
        let _ = std::fs::remove_dir_all(&media_root);
    }
    result.map(|()| label)
}

fn extract_archive(archive: &Path, pending: &Path, media_root: &Path) -> Result<(), String> {
    let file = std::fs::File::open(archive).map_err(|e| format!("Archive illisible : {e}"))?;
    let mut zip = zip::ZipArchive::new(file).map_err(|e| format!("Sauvegarde invalide : {e}"))?;
    if zip.len() > MAX_FILES {
        return Err("Archive trop grande".into());
    }
    let mut names = Vec::new();
    let mut total = 0u64;
    for i in 0..zip.len() {
        let entry = zip.by_index(i).map_err(|e| e.to_string())?;
        total += entry.size();
        names.push(entry.name().map_err(|e| e.to_string())?.to_string());
    }
    let mut folded: Vec<String> = names.iter().map(|n| n.to_lowercase()).collect();
    folded.sort();
    folded.dedup();
    if folded.len() != names.len() {
        return Err("Noms dupliqués dans l'archive".into());
    }
    if total > MAX_BYTES {
        return Err("Volume décompressé excessif".into());
    }
    let manifest: Value = {
        let mut entry =
            zip.by_name("manifest.json").map_err(|_| "Ce n'est pas une sauvegarde de Project-On (manifeste absent)")?;
        if entry.size() > MAX_MANIFEST {
            return Err("Manifeste trop grand".into());
        }
        let mut text = String::new();
        entry.read_to_string(&mut text).map_err(|e| e.to_string())?;
        serde_json::from_str(&text).map_err(|e| format!("Manifeste illisible : {e}"))?
    };
    if manifest.get("format").and_then(Value::as_str) != Some("project-on-backup")
        || manifest.get("format_version").and_then(Value::as_i64) != Some(1)
    {
        return Err("Format de sauvegarde non pris en charge".into());
    }
    let entries = manifest.get("files").and_then(Value::as_object).ok_or("Inventaire du manifeste absent")?;
    let mut expected: Vec<&str> = entries.keys().map(String::as_str).chain(["manifest.json"]).collect();
    let mut actual: Vec<&str> = names.iter().map(String::as_str).collect();
    expected.sort_unstable();
    actual.sort_unstable();
    if expected != actual {
        return Err("Inventaire du manifeste incohérent".into());
    }
    if manifest.get("database").and_then(Value::as_str) != Some("data/project_on.db")
        || !entries.contains_key("data/project_on.db")
    {
        return Err("Base absente du manifeste".into());
    }
    let settings_member = match manifest.get("settings") {
        None | Some(Value::Null) => None,
        Some(Value::String(s)) if s == "data/settings.json" => Some(s.as_str()),
        _ => return Err("Chemin de réglages invalide".into()),
    };

    // Extraction vérifiée : la base et les réglages dans un dossier de travail, les médias à leur place.
    let work = pending.join("archive");
    for (name, meta) in entries {
        bundle_member(name)?;
        if name.starts_with("data/") && name != "data/project_on.db" && name != "data/settings.json" {
            return Err(format!("Fichier de données non autorisé : {name}"));
        }
        let mut entry = zip.by_name(name).map_err(|e| e.to_string())?;
        if entry.is_dir() || entry.is_symlink() {
            return Err("Liens et dossiers non autorisés".into());
        }
        if Some(entry.size()) != meta.get("size").and_then(Value::as_u64) {
            return Err(format!("Taille différente du manifeste : {name}"));
        }
        let output = match name.split_once('/') {
            Some(("data", rest)) => work.join(rest),
            _ => media_root.join(name),
        };
        if let Some(parent) = output.parent() {
            std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
        let mut out = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)
            .map_err(|e| format!("{}: {e}", output.display()))?;
        let mut hasher = Sha256::new();
        let mut buffer = vec![0u8; 1024 * 1024];
        loop {
            let n = entry.read(&mut buffer).map_err(|e| e.to_string())?;
            if n == 0 {
                break;
            }
            hasher.update(&buffer[..n]);
            std::io::Write::write_all(&mut out, &buffer[..n]).map_err(|e| e.to_string())?;
        }
        if Some(hex(&hasher.finalize()).as_str()) != meta.get("sha256").and_then(Value::as_str) {
            return Err(format!("Empreinte différente du manifeste : {name}"));
        }
    }

    // Les fichiers référencés par la base et les réglages pointent vers leur copie restaurée.
    let mut mapping = std::collections::HashMap::new();
    if let Some(map) = manifest.get("path_map").and_then(Value::as_object) {
        for (old, member) in map {
            let member = member.as_str().ok_or("Références de fichiers invalides")?;
            if !entries.contains_key(member) || !(member.starts_with("media/") || member.starts_with("backgrounds/")) {
                return Err("Références de fichiers invalides".into());
            }
            let new = media_root.join(member.replace('/', std::path::MAIN_SEPARATOR_STR));
            mapping.insert(old.clone(), new.to_string_lossy().to_string());
        }
    }
    let db_path = pending.join("project_on.db");
    po_db::copy_database(&work.join("project_on.db"), &db_path)
        .map_err(|e| format!("Base de l'archive invalide : {e}"))?;
    {
        let db = po_db::Database::open(&db_path, po_db::Mode::ReadWrite)
            .map_err(|e| format!("Base de l'archive illisible : {e}"))?;
        let conn = db.connection();
        for (table, column) in REFERENCE_FIELDS {
            let has: bool = conn
                .query_row("SELECT COUNT(*) FROM pragma_table_info(?1) WHERE name = ?2", [table, column], |r| {
                    r.get::<_, i64>(0)
                })
                .map(|n| n > 0)
                .unwrap_or(false);
            if !has {
                continue;
            }
            for (old, new) in &mapping {
                conn.execute(&format!("UPDATE \"{table}\" SET \"{column}\" = ?1 WHERE \"{column}\" = ?2"), [new, old])
                    .map_err(|e| e.to_string())?;
            }
        }
        let verdict: String = conn.query_row("PRAGMA quick_check", [], |r| r.get(0)).map_err(|e| e.to_string())?;
        if !verdict.eq_ignore_ascii_case("ok") {
            return Err(format!("Base invalide après relocalisation : {verdict}"));
        }
    }
    if settings_member.is_some() {
        let text = std::fs::read_to_string(work.join("settings.json")).map_err(|e| e.to_string())?;
        let value: Value =
            serde_json::from_str(&text).map_err(|e| format!("Réglages de l'archive illisibles : {e}"))?;
        if !value.is_object() {
            return Err("Les réglages de l'archive ne sont pas un objet JSON".into());
        }
        let value = relocate_settings(safe_settings(value), &mapping);
        let text = serde_json::to_string_pretty(&value).map_err(|e| e.to_string())?;
        std::fs::write(pending.join("settings.json"), text).map_err(|e| e.to_string())?;
    }
    std::fs::remove_dir_all(&work).map_err(|e| e.to_string())?;
    Ok(())
}

/// Au démarrage, **avant d'ouvrir la base** : applique la restauration préparée, s'il y en a une.
/// La base et les réglages en place sont d'abord sauvegardés (`<stamp>-avant-restauration`).
/// `None` : rien à restaurer ; sinon ce qui a été remis, ou pourquoi rien n'a changé.
pub fn apply_pending(data: &Path, database: &Path, settings: &Path, stamp: &str) -> Option<Result<String, String>> {
    let dir = data.join(PENDING);
    let label = pending(data)?;
    let result = (|| {
        if database.is_file() {
            crate::maintenance::backup(
                database,
                settings,
                &data.join("sauvegardes"),
                &format!("{stamp}-avant-restauration"),
            )
            .map_err(|e| format!("la base actuelle n'a pas pu être sauvegardée ({e}) : rien n'est restauré"))?;
        }
        // La base a été fermée proprement : ses fichiers de journal ne servent plus.
        for suffix in ["-wal", "-shm"] {
            let mut side = database.as_os_str().to_owned();
            side.push(suffix);
            let _ = std::fs::remove_file(PathBuf::from(side));
        }
        std::fs::rename(dir.join("project_on.db"), database).map_err(|e| format!("base non remplacée : {e}"))?;
        let new_settings = dir.join("settings.json");
        if new_settings.is_file() {
            if settings.is_file() {
                let _ = std::fs::copy(settings, settings.with_extension("json.bak"));
            }
            std::fs::rename(&new_settings, settings).map_err(|e| format!("réglages non remplacés : {e}"))?;
        }
        Ok(label)
    })();
    let _ = std::fs::remove_dir_all(&dir);
    Some(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn scratch() -> tempfile::TempDir {
        let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
        std::fs::create_dir_all(&base).unwrap();
        tempfile::tempdir_in(base).unwrap()
    }

    fn database_with(path: &Path, folder: &str) {
        let (mut db, _) = po_db::Database::open_and_initialize(path, &po_db::InitOptions::default()).unwrap();
        db.create_folder(folder).unwrap();
    }

    fn folders(path: &Path) -> Vec<String> {
        let db = po_db::Database::open(path, po_db::Mode::ReadOnly).unwrap();
        db.list_folders().unwrap().into_iter().map(|f| f.name).collect()
    }

    #[test]
    fn a_backup_is_prepared_then_applied_at_the_next_start_after_a_safety_backup() {
        let dir = scratch();
        let data = dir.path().join("data");
        std::fs::create_dir_all(&data).unwrap();
        let (database, settings) = (data.join("project_on.db"), data.join("settings.json"));
        database_with(&database, "Avant");
        std::fs::write(&settings, r#"{"projection":{"font_size":40}}"#).unwrap();
        let backup =
            crate::maintenance::backup(&database, &settings, &data.join("sauvegardes"), "2026-11-01_090000").unwrap();
        // Le travail continue après la sauvegarde.
        database_with(&database, "Après");
        std::fs::write(&settings, r#"{"projection":{"font_size":60}}"#).unwrap();

        assert_eq!(pending(&data), None);
        let label = prepare_backup(&backup.dir, &data).unwrap();
        assert_eq!(label, "la sauvegarde du 2026-11-01_090000");
        assert_eq!(pending(&data).as_deref(), Some(label.as_str()));
        // Rien n'a encore changé.
        assert!(folders(&database).contains(&"Après".to_string()));

        let applied = apply_pending(&data, &database, &settings, "2026-11-02_100000").unwrap().unwrap();
        assert_eq!(applied, label);
        assert!(!folders(&database).contains(&"Après".to_string()), "la base d'avant est revenue");
        assert!(std::fs::read_to_string(&settings).unwrap().contains("40"));
        assert_eq!(pending(&data), None);
        // La base remplacée est gardée : on peut défaire la restauration.
        let safety = data.join("sauvegardes").join("2026-11-02_100000-avant-restauration");
        assert!(folders(&safety.join("project_on.db")).contains(&"Après".to_string()));
        assert!(apply_pending(&data, &database, &settings, "x").is_none());
    }

    #[test]
    fn a_damaged_backup_is_refused_before_anything_changes() {
        let dir = scratch();
        let data = dir.path().join("data");
        let broken = dir.path().join("abimee");
        std::fs::create_dir_all(&broken).unwrap();
        std::fs::write(broken.join("project_on.db"), b"pas une base SQLite").unwrap();
        assert!(prepare_backup(&broken, &data).is_err());
        assert_eq!(pending(&data), None);
    }

    /// Une archive complète comme celle de la 2.8 (`create_backup_bundle`).
    fn archive_28(dir: &Path, image_path: &str, tamper: bool) -> PathBuf {
        let db = dir.join("source.db");
        let (mut database, _) = po_db::Database::open_and_initialize(&db, &po_db::InitOptions::default()).unwrap();
        let folder = database.create_folder("Culte de Noël").unwrap();
        database.add_item("custom", "Affiche", "", Some(folder), image_path).unwrap();
        drop(database);
        let copy = dir.join("copie.db");
        po_db::copy_database(&db, &copy).unwrap();
        let image = b"\x89PNG faux contenu";
        let settings = json!({ "church": { "logo_path": image_path, "obs_password": "secret" } }).to_string();
        let files: Vec<(&str, Vec<u8>)> = vec![
            ("data/project_on.db", std::fs::read(&copy).unwrap()),
            ("data/settings.json", settings.into_bytes()),
            ("backgrounds/affiche.png", image.to_vec()),
        ];
        let mut inventory = Map::new();
        for (name, bytes) in &files {
            let mut sha = hex(&Sha256::digest(bytes));
            if tamper && name.starts_with("backgrounds") {
                sha = "0".repeat(64);
            }
            inventory.insert((*name).into(), json!({ "size": bytes.len(), "sha256": sha }));
        }
        let manifest = json!({
            "format": "project-on-backup", "format_version": 1,
            "database": "data/project_on.db", "settings": "data/settings.json",
            "path_map": { image_path: "backgrounds/affiche.png" },
            "files": inventory,
        });
        let path = dir.join("project-on-complet.zip");
        let mut zip = zip::ZipWriter::new(std::fs::File::create(&path).unwrap());
        let options = zip::write::SimpleFileOptions::default();
        for (name, bytes) in &files {
            zip.start_file(*name, options).unwrap();
            zip.write_all(bytes).unwrap();
        }
        zip.start_file("manifest.json", options).unwrap();
        zip.write_all(manifest.to_string().as_bytes()).unwrap();
        zip.finish().unwrap();
        path
    }

    #[test]
    fn a_full_archive_of_the_2_8_comes_back_with_its_media_and_without_secrets() {
        let dir = scratch();
        let data = dir.path().join("data");
        std::fs::create_dir_all(&data).unwrap();
        let (database, settings) = (data.join("project_on.db"), data.join("settings.json"));
        database_with(&database, "Actuel");
        let old_image = "C:\\Users\\ancien\\AppData\\Roaming\\Project-On\\backgrounds\\affiche.png";
        let archive = archive_28(dir.path(), old_image, false);

        let label = prepare_archive(&archive, &data, "2026-11-12_080000").unwrap();
        assert_eq!(label, "l'archive « project-on-complet.zip »");
        apply_pending(&data, &database, &settings, "2026-11-12_080001").unwrap().unwrap();

        assert!(folders(&database).contains(&"Culte de Noël".to_string()));
        let restored = data.join(RESTORED).join("2026-11-12_080000").join("backgrounds").join("affiche.png");
        assert!(restored.is_file(), "l'image est restaurée dans les données");
        let db = po_db::Database::open(&database, po_db::Mode::ReadOnly).unwrap();
        let folder = db.list_folders().unwrap().into_iter().find(|f| f.name == "Culte de Noël").unwrap();
        let items = db.list_items(Some(folder.id)).unwrap();
        assert_eq!(items[0].background, restored.to_string_lossy(), "la playlist pointe vers la copie");
        let text = std::fs::read_to_string(&settings).unwrap();
        assert!(!text.contains("secret"), "pas de mot de passe restauré");
        assert!(text.contains("affiche.png") && !text.contains("ancien"), "{text}");
    }

    #[test]
    fn a_tampered_or_foreign_archive_is_refused_and_leaves_nothing_behind() {
        let dir = scratch();
        let data = dir.path().join("data");
        std::fs::create_dir_all(&data).unwrap();
        let archive = archive_28(dir.path(), "C:\\fonds\\affiche.png", true);
        let error = prepare_archive(&archive, &data, "s").unwrap_err();
        assert!(error.contains("Empreinte"), "{error}");
        assert_eq!(pending(&data), None);
        assert!(!data.join(RESTORED).join("s").exists());

        // Une archive quelconque (une playlist exportée, un zip de photos) n'est pas une sauvegarde.
        let other = dir.path().join("photos.zip");
        let mut zip = zip::ZipWriter::new(std::fs::File::create(&other).unwrap());
        zip.start_file("photo.jpg", zip::write::SimpleFileOptions::default()).unwrap();
        zip.write_all(b"jpeg").unwrap();
        zip.finish().unwrap();
        assert!(prepare_archive(&other, &data, "t").unwrap_err().contains("manifeste"));

        for bad in ["../evil.db", "data/../../x", "C:/x", "media\\x", "autre/x", "media/con.png", "media/a. "] {
            assert!(bundle_member(bad).is_err(), "{bad}");
        }
        assert!(bundle_member("media/photos/culte.jpg").is_ok());
    }
}
