//! L'import et l'export d'une playlist (`playlist_transfer.py` de la 2.8), au même format : une
//! archive ZIP avec `manifest.json` (`{"app": "Project-On", "format": 2, "name", "items"}`) et les
//! médias sous `media/00000.png`… Une playlist exportée par la 2.8 s'importe dans la 3.0, et
//! inversement. L'ancien format 1 (un JSON seul) se lit encore.
//!
//! Sécurité, comme la 2.8 :
//! - jamais un fichier écrit à l'endroit choisi par l'archive (chemins absolus, `..`, `\` refusés) ;
//! - les médias importés sont nommés par leur empreinte SHA-256 dans le dossier des médias ;
//! - limites de taille (2 Gio, 10 000 fichiers, manifeste de 8 Mio) ;
//! - l'export est publié d'un coup (fichier temporaire puis renommage) ; un média absent l'arrête.

use std::collections::HashMap;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

use po_db::{NewItem, PlaylistItem};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

const MAX_BYTES: u64 = 2 * 1024 * 1024 * 1024;
const MAX_FILES: usize = 10_000;
const MAX_MANIFEST: u64 = 8 * 1024 * 1024;
const FIELDS: [&str; 4] = ["source", "reference", "text", "background"];

/// Un nom de membre d'archive sûr (`_member` de la 2.8).
fn safe_member(name: &str) -> Result<(), String> {
    let bad = name.is_empty()
        || name.contains('\\')
        || name.contains(':')
        || name.starts_with('/')
        || name.split('/').any(|part| part == "..");
    if bad { Err("Chemin d'archive non autorisé".into()) } else { Ok(()) }
}

/// Les éléments lus et vérifiés d'un manifeste (`_validate`).
fn validate(payload: &Value, fallback: &str) -> Result<(String, Vec<NewItem>), String> {
    let items = payload.get("items").and_then(Value::as_array).ok_or("Format de playlist invalide")?;
    let format = payload.get("format").map_or(Some(1), Value::as_i64);
    if !matches!(format, Some(1 | 2)) {
        return Err("Version de playlist non prise en charge".into());
    }
    if items.len() > MAX_FILES {
        return Err("Trop d'éléments".into());
    }
    let mut out = Vec::new();
    for item in items {
        let object = item.as_object().ok_or("Élément de playlist invalide")?;
        let mut row = HashMap::new();
        for key in FIELDS {
            let value = match object.get(key) {
                None | Some(Value::Null) => String::new(),
                Some(Value::String(s)) => s.clone(),
                Some(_) => return Err("Champ de playlist invalide".into()),
            };
            let value = if key == "source" && value.is_empty() { "custom".to_string() } else { value };
            row.insert(key, value);
        }
        let item = NewItem {
            source: row.remove("source").unwrap_or_default(),
            reference: row.remove("reference").unwrap_or_default(),
            text: row.remove("text").unwrap_or_default(),
            background: row.remove("background").unwrap_or_default(),
        };
        if !item.text.trim().is_empty() || !item.background.is_empty() {
            out.push(item);
        }
    }
    if out.is_empty() {
        return Err("Playlist vide".into());
    }
    let name = payload.get("name").and_then(Value::as_str).filter(|n| !n.is_empty()).unwrap_or(fallback);
    Ok((name.to_string(), out))
}

fn extension(path: &str) -> String {
    Path::new(path).extension().map(|e| format!(".{}", e.to_string_lossy().to_lowercase())).unwrap_or_default()
}

/// Exporte une playlist dans `path` (archive ZIP). Rend le nombre d'éléments.
pub fn export(path: &Path, name: &str, items: &[PlaylistItem]) -> Result<usize, String> {
    let mut rows: Vec<NewItem> = items
        .iter()
        .map(|i| NewItem {
            source: if i.source.is_empty() { "custom".into() } else { i.source.clone() },
            reference: i.reference.clone(),
            text: i.text.clone(),
            background: i.background.clone(),
        })
        .filter(|i| !i.text.trim().is_empty() || !i.background.is_empty())
        .collect();
    if rows.is_empty() {
        return Err("Playlist vide".into());
    }
    let dir = path.parent().ok_or("Dossier de destination invalide")?;
    std::fs::create_dir_all(dir).map_err(|e| e.to_string())?;
    let temporary = path.with_extension("tmp");
    let result = (|| -> Result<usize, String> {
        let file = std::fs::File::create(&temporary).map_err(|e| e.to_string())?;
        let mut zip = zip::ZipWriter::new(file);
        let options = zip::write::SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        let mut names: HashMap<PathBuf, String> = HashMap::new();
        let mut total = 0u64;
        for row in &mut rows {
            if row.background.is_empty() {
                continue;
            }
            let source = PathBuf::from(&row.background);
            // Une couleur ou un réglage de fond n'est pas un fichier : il reste tel quel.
            if !crate::playlist::is_image_file(&row.background)
                && crate::playlist::media_kind(&row.background) == crate::playlist::Kind::Image
            {
                continue;
            }
            if !source.is_file() {
                return Err(format!("Média absent : {}", source.display()));
            }
            let key = source.canonicalize().unwrap_or(source.clone());
            if !names.contains_key(&key) {
                total += std::fs::metadata(&source).map(|m| m.len()).unwrap_or(0);
                if total > MAX_BYTES {
                    return Err("Archive supérieure à la limite de 2 Gio".into());
                }
                let member = format!("media/{:05}{}", names.len(), extension(&row.background));
                zip.start_file(member.as_str(), options).map_err(|e| e.to_string())?;
                let mut src = std::fs::File::open(&source).map_err(|e| e.to_string())?;
                std::io::copy(&mut src, &mut zip).map_err(|e| e.to_string())?;
                names.insert(key.clone(), member);
            }
            row.background = names[&key].clone();
        }
        let manifest = json!({
            "app": "Project-On",
            "format": 2,
            "name": name,
            "items": rows.iter().map(|r| json!({
                "source": r.source, "reference": r.reference, "text": r.text, "background": r.background
            })).collect::<Vec<_>>(),
        });
        let data = serde_json::to_vec(&manifest).map_err(|e| e.to_string())?;
        if data.len() as u64 > MAX_MANIFEST {
            return Err("Manifeste trop volumineux".into());
        }
        zip.start_file("manifest.json", options).map_err(|e| e.to_string())?;
        zip.write_all(&data).map_err(|e| e.to_string())?;
        zip.finish().map_err(|e| e.to_string())?;
        std::fs::rename(&temporary, path).map_err(|e| e.to_string())?;
        Ok(rows.len())
    })();
    let _ = std::fs::remove_file(&temporary);
    result
}

/// L'empreinte en hexadécimal.
fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// Range un média dans `dir` sous son empreinte (`_store`) ; un fichier de même nom mais de contenu
/// différent n'est jamais écrasé.
fn store(bytes: &[u8], suffix: &str, dir: &Path) -> Result<PathBuf, String> {
    std::fs::create_dir_all(dir).map_err(|e| e.to_string())?;
    let digest = hex(&Sha256::digest(bytes));
    let target = dir.join(format!("{digest}{suffix}"));
    if target.exists() {
        let existing = std::fs::read(&target).map_err(|e| e.to_string())?;
        if hex(&Sha256::digest(&existing)) != digest {
            return Err("Média existant endommagé ; aucun écrasement".into());
        }
        return Ok(target);
    }
    let temporary = dir.join(format!("{digest}.tmp"));
    std::fs::write(&temporary, bytes).map_err(|e| e.to_string())?;
    std::fs::rename(&temporary, &target).map_err(|e| e.to_string())?;
    Ok(target)
}

/// Lit une playlist exportée (archive de la 2.8 ou de la 3.0, ou JSON format 1) ; ses médias sont
/// copiés dans `media_dir`. Rend son nom et ses éléments.
pub fn read(path: &Path, media_dir: &Path) -> Result<(String, Vec<NewItem>), String> {
    let fallback = path.file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
    let file = std::fs::File::open(path).map_err(|e| e.to_string())?;
    let Ok(mut archive) = zip::ZipArchive::new(file) else {
        // L'ancien format : un JSON seul, les médias à côté.
        if std::fs::metadata(path).map(|m| m.len()).unwrap_or(0) > MAX_MANIFEST {
            return Err("Manifeste trop volumineux".into());
        }
        let text = std::fs::read_to_string(path).map_err(|e| e.to_string())?;
        let payload: Value = serde_json::from_str(text.trim_start_matches('\u{feff}')).map_err(|e| e.to_string())?;
        let (name, mut items) = validate(&payload, &fallback)?;
        for item in &mut items {
            if item.background.is_empty() || !crate::playlist::is_image_file(&item.background) {
                continue;
            }
            let mut source = PathBuf::from(&item.background);
            if !source.is_absolute() {
                source = path.parent().unwrap_or(Path::new(".")).join(source);
            }
            let bytes = std::fs::read(&source).map_err(|e| format!("{} : {e}", source.display()))?;
            item.background = store(&bytes, &extension(&item.background), media_dir)?.to_string_lossy().to_string();
        }
        return Ok((name, items));
    };
    if archive.len() > MAX_FILES {
        return Err("Archive trop volumineuse".into());
    }
    let mut total = 0u64;
    let mut members = Vec::new();
    for i in 0..archive.len() {
        let entry = archive.by_index(i).map_err(|e| e.to_string())?;
        let name = entry.name().map_err(|e| e.to_string())?.to_string();
        safe_member(&name)?;
        // Un lien symbolique n'est jamais suivi.
        if entry.unix_mode().is_some_and(|m| m & 0o170000 == 0o120000) || members.contains(&name) {
            return Err("Membre dupliqué ou lien non autorisé".into());
        }
        total += entry.size();
        members.push(name);
    }
    if total > MAX_BYTES {
        return Err("Archive trop volumineuse".into());
    }
    let manifest = {
        let mut entry = archive.by_name("manifest.json").map_err(|_| "Manifeste absent".to_string())?;
        if entry.size() > MAX_MANIFEST {
            return Err("Manifeste trop volumineux".into());
        }
        let mut data = Vec::new();
        entry.read_to_end(&mut data).map_err(|e| e.to_string())?;
        serde_json::from_slice::<Value>(&data).map_err(|e| e.to_string())?
    };
    let (name, mut items) = validate(&manifest, &fallback)?;
    // Toutes les références vérifiées avant d'écrire le moindre média.
    for item in &items {
        if !item.background.is_empty() && item.background.starts_with("media/") {
            safe_member(&item.background)?;
            if !members.contains(&item.background) {
                return Err(format!("Média absent de l'archive : {}", item.background));
            }
        }
    }
    let mut resolved: HashMap<String, String> = HashMap::new();
    for item in &mut items {
        let member = item.background.clone();
        if member.is_empty() || !member.starts_with("media/") {
            continue;
        }
        if !resolved.contains_key(&member) {
            let mut entry = archive.by_name(&member).map_err(|e| e.to_string())?;
            let mut bytes = Vec::new();
            entry.read_to_end(&mut bytes).map_err(|e| e.to_string())?;
            let stored = store(&bytes, &extension(&member), media_dir)?;
            resolved.insert(member.clone(), stored.to_string_lossy().to_string());
        }
        item.background = resolved[&member].clone();
    }
    Ok((name, items))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scratch(name: &str) -> PathBuf {
        let dir = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/tmp")
            .join(format!("transfert-{}-{name}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn item(id: i64, source: &str, reference: &str, text: &str, background: &str) -> PlaylistItem {
        PlaylistItem {
            id,
            folder_id: Some(1),
            source: source.into(),
            reference: reference.into(),
            text: text.into(),
            sort_order: Some(id),
            background: background.into(),
        }
    }

    #[test]
    fn a_playlist_goes_out_and_comes_back_with_its_media() {
        let dir = scratch("aller-retour");
        let image = dir.join("affiche.PNG");
        std::fs::write(&image, b"une image").unwrap();
        let items = [
            item(1, "bible", "Jean 3:16", "Car Dieu a tant aimé le monde", ""),
            item(2, "media", "affiche", "", &image.to_string_lossy()),
            item(3, "custom", "Prière", "Notre Père", &image.to_string_lossy()),
            item(4, "custom", "Couleur", "Fond uni", "#123456"),
            item(5, "custom", "", "   ", ""),
        ];
        let archive = dir.join("Culte.zip");
        assert_eq!(export(&archive, "Culte du dimanche", &items).unwrap(), 4, "l'élément vide n'est pas exporté");
        // Le manifeste a la forme de la 2.8 ; l'image n'y est qu'une fois.
        let mut zip = zip::ZipArchive::new(std::fs::File::open(&archive).unwrap()).unwrap();
        assert_eq!(zip.len(), 2);
        let mut manifest = String::new();
        zip.by_name("manifest.json").unwrap().read_to_string(&mut manifest).unwrap();
        let manifest: Value = serde_json::from_str(&manifest).unwrap();
        assert_eq!((manifest["app"].as_str(), manifest["format"].as_i64()), (Some("Project-On"), Some(2)));
        assert_eq!(manifest["items"][1]["background"], "media/00000.png");
        assert_eq!(manifest["items"][3]["background"], "#123456");
        // Retour : le média est rangé sous son empreinte, une seule fois.
        let media = dir.join("medias");
        let (name, back) = read(&archive, &media).unwrap();
        assert_eq!(name, "Culte du dimanche");
        assert_eq!(back.len(), 4);
        assert_eq!(back[0].reference, "Jean 3:16");
        assert!(back[1].background.ends_with(".png") && Path::new(&back[1].background).is_file());
        assert_eq!(back[1].background, back[2].background);
        assert_eq!(std::fs::read(&back[1].background).unwrap(), b"une image");
        assert_eq!(std::fs::read_dir(&media).unwrap().count(), 1);
        // Une seconde importation réutilise le même fichier.
        let (_, again) = read(&archive, &media).unwrap();
        assert_eq!(again[1].background, back[1].background);
        // Un média absent arrête l'export, sans laisser de fichier.
        let missing = [item(1, "media", "x", "", &dir.join("absent.jpg").to_string_lossy())];
        assert!(export(&dir.join("absent.zip"), "x", &missing).unwrap_err().contains("Média absent"));
        assert!(!dir.join("absent.zip").exists() && !dir.join("absent.tmp").exists());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn dangerous_or_broken_archives_are_refused() {
        let dir = scratch("refus");
        let make = |name: &str, members: &[(&str, &[u8])]| {
            let path = dir.join(name);
            let mut zip = zip::ZipWriter::new(std::fs::File::create(&path).unwrap());
            for (member, data) in members {
                zip.start_file(*member, zip::write::SimpleFileOptions::default()).unwrap();
                zip.write_all(data).unwrap();
            }
            zip.finish().unwrap();
            path
        };
        let manifest = br#"{"app":"Project-On","format":2,"name":"X","items":[{"source":"media","reference":"a","text":"","background":"media/00000.png"}]}"#;
        let traversal = make("traversee.zip", &[("../evil.txt", b"x"), ("manifest.json", manifest)]);
        assert!(read(&traversal, &dir.join("m")).is_err());
        let missing = make("absent.zip", &[("manifest.json", manifest)]);
        assert!(read(&missing, &dir.join("m")).unwrap_err().contains("Média absent"));
        let empty = make("vide.zip", &[("manifest.json", br#"{"format":2,"items":[]}"#)]);
        assert_eq!(read(&empty, &dir.join("m")).unwrap_err(), "Playlist vide");
        let future = make("futur.zip", &[("manifest.json", br#"{"format":3,"items":[{"text":"a"}]}"#)]);
        assert!(read(&future, &dir.join("m")).unwrap_err().contains("Version"));
        assert!(!dir.join("m").exists(), "rien n'a été écrit");
        // L'ancien format 1 : un JSON, le média à côté.
        std::fs::write(dir.join("photo.jpg"), b"photo").unwrap();
        std::fs::write(
            dir.join("ancien.json"),
            r#"{"name":"Ancienne","items":[{"text":"Bonjour"},{"source":"media","background":"photo.jpg"}]}"#,
        )
        .unwrap();
        let (name, items) = read(&dir.join("ancien.json"), &dir.join("m")).unwrap();
        assert_eq!(name, "Ancienne");
        assert_eq!(items[0].source, "custom");
        assert!(Path::new(&items[1].background).starts_with(dir.join("m")));
        let _ = std::fs::remove_dir_all(&dir);
    }
}
