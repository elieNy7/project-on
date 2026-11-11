//! La **mise à jour** de Project-On (`updater.py` de la 2.8) : les versions publiées sur GitHub
//! (dépôt `elieNy7/paratech-web`, étiquettes `project-on-v<version>`), la plus récente comparée à
//! celle-ci ; à la demande de l'opérateur, l'installateur `ProjectOn_<version>_Setup.exe` est
//! téléchargé, vérifié, puis lancé (il garde la base, les playlists et les réglages).
//!
//! Sécurité, comme la 2.8 : HTTPS depuis github.com seulement (redirections comprises), taille
//! vérifiée contre celle annoncée, empreinte SHA-256 vérifiée quand les notes la publient, fichier
//! publié seulement s'il est complet. Les échanges passent par `curl.exe`, fourni avec Windows.
//!
//! La bêta ne lance jamais l'installateur (il remplacerait la 2.8) : elle ouvre la page de la
//! version.

use std::path::{Path, PathBuf};

use serde_json::Value;
use sha2::{Digest, Sha256};

pub const RELEASES_URL: &str = "https://api.github.com/repos/elieNy7/paratech-web/releases?per_page=50";
const TAG_PREFIX: &str = "project-on-v";
const ALLOWED_HOSTS: [&str; 3] =
    ["github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"];

/// Une version publiée et son installateur.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UpdateInfo {
    pub version: String,
    pub url: String,
    pub size: u64,
    pub notes: String,
    pub page: String,
    pub sha256: String,
}

/// « 3.0.12 » → (3, 0, 12) ; jusqu'à quatre nombres (`parse_version`).
pub fn parse_version(value: &str) -> Vec<u64> {
    let numbers: Vec<u64> = value
        .split(|c: char| !c.is_ascii_digit())
        .filter(|p| !p.is_empty())
        .take(4)
        .filter_map(|p| p.parse().ok())
        .collect();
    if numbers.is_empty() { vec![0] } else { numbers }
}

pub fn is_newer(remote: &str, local: &str) -> bool {
    parse_version(remote) > parse_version(local)
}

fn host_of(url: &str) -> Option<&str> {
    let rest = url.strip_prefix("https://")?;
    rest.split(['/', '?', '#']).next()?.split('@').next_back()?.split(':').next()
}

fn allowed(url: &str) -> bool {
    host_of(url).is_some_and(|h| ALLOWED_HOSTS.contains(&h))
}

/// La version et l'installateur d'une version publiée (`parse_release`).
pub fn parse_release(release: &Value) -> Option<UpdateInfo> {
    if release.get("draft").and_then(Value::as_bool) == Some(true)
        || release.get("prerelease").and_then(Value::as_bool) == Some(true)
    {
        return None;
    }
    let tag = release.get("tag_name").and_then(Value::as_str).unwrap_or("");
    let version = tag.strip_prefix(TAG_PREFIX).unwrap_or_else(|| tag.trim_start_matches(['v', 'V'])).to_string();
    for asset in release.get("assets").and_then(Value::as_array).into_iter().flatten() {
        let name = asset.get("name").and_then(Value::as_str).unwrap_or("");
        let installer = name
            .strip_prefix("ProjectOn_")
            .and_then(|r| r.strip_suffix("_Setup.exe"))
            .is_some_and(|v| !v.is_empty() && v.chars().all(|c| c.is_ascii_digit() || c == '.'));
        if !installer {
            continue;
        }
        let url = asset.get("browser_download_url").and_then(Value::as_str).unwrap_or("").to_string();
        if !allowed(&url) {
            return None;
        }
        let notes = release.get("body").and_then(Value::as_str).unwrap_or("").to_string();
        return Some(UpdateInfo {
            version,
            url,
            size: asset.get("size").and_then(Value::as_u64).unwrap_or(0),
            sha256: sha256_in(&notes),
            notes,
            page: release.get("html_url").and_then(Value::as_str).unwrap_or("").to_string(),
        });
    }
    None
}

/// L'empreinte « SHA-256 : <64 caractères> » des notes de version.
fn sha256_in(notes: &str) -> String {
    let upper = notes.to_uppercase();
    let Some(at) = upper.find("SHA-256").or_else(|| upper.find("SHA256")) else { return String::new() };
    let after = &notes[at..];
    let hex: String = after
        .split(|c: char| !c.is_ascii_hexdigit())
        .find(|w| w.len() == 64)
        .map(str::to_lowercase)
        .unwrap_or_default();
    hex
}

/// La plus récente version de Project-On parmi celles de tous les logiciels (`pick_latest`).
pub fn pick_latest(releases: &Value) -> Option<UpdateInfo> {
    releases
        .as_array()?
        .iter()
        .filter(|r| r.get("tag_name").and_then(Value::as_str).is_some_and(|t| t.starts_with(TAG_PREFIX)))
        .filter_map(parse_release)
        .max_by(|a, b| parse_version(&a.version).cmp(&parse_version(&b.version)))
}

fn curl() -> std::process::Command {
    let mut command = std::process::Command::new("curl.exe");
    command.args(["--silent", "--show-error", "--fail", "--location", "--proto", "=https", "--proto-redir", "=https"]);
    command.arg("--user-agent").arg(format!("Project-On/{}", env!("CARGO_PKG_VERSION")));
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x0800_0000);
    }
    command
}

/// La dernière version publiée (`None` : aucune version installable).
pub fn check_latest() -> Result<Option<UpdateInfo>, String> {
    let output = curl()
        .args(["--max-time", "10", "--header", "Accept: application/vnd.github+json", RELEASES_URL])
        .output()
        .map_err(|e| e.to_string())?;
    if !output.status.success() {
        return Err("impossible de joindre GitHub (pas d'Internet ?)".into());
    }
    let releases: Value = serde_json::from_slice(&output.stdout).map_err(|e| e.to_string())?;
    Ok(pick_latest(&releases))
}

/// Télécharge l'installateur dans `folder` et le vérifie ; rend son chemin.
pub fn download(info: &UpdateInfo, folder: &Path) -> Result<PathBuf, String> {
    if !allowed(&info.url) {
        return Err("adresse de téléchargement inattendue".into());
    }
    std::fs::create_dir_all(folder).map_err(|e| e.to_string())?;
    let name = info.url.rsplit('/').next().filter(|n| n.ends_with("_Setup.exe")).ok_or("nom de fichier inattendu")?;
    let target = folder.join(name);
    let partial = target.with_extension("part");
    let _ = std::fs::remove_file(&partial);
    let output = curl()
        .args(["--max-time", "1800", "--write-out", "%{url_effective}", "--output"])
        .arg(&partial)
        .arg(&info.url)
        .output()
        .map_err(|e| e.to_string())?;
    let check = (|| {
        if !output.status.success() {
            return Err(format!("téléchargement impossible : {}", String::from_utf8_lossy(&output.stderr).trim()));
        }
        let effective = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if !allowed(&effective) {
            return Err(format!(
                "téléchargement redirigé vers un hôte inattendu : {}",
                host_of(&effective).unwrap_or("?")
            ));
        }
        let bytes = std::fs::read(&partial).map_err(|e| e.to_string())?;
        if info.size > 0 && bytes.len() as u64 != info.size {
            return Err(format!("fichier incomplet ({} / {} octets)", bytes.len(), info.size));
        }
        if !info.sha256.is_empty() {
            let digest: String = Sha256::digest(&bytes).iter().map(|b| format!("{b:02x}")).collect();
            if digest != info.sha256 {
                return Err("empreinte SHA-256 différente de celle publiée".into());
            }
        }
        Ok(())
    })();
    if let Err(e) = check {
        let _ = std::fs::remove_file(&partial);
        return Err(e);
    }
    std::fs::rename(&partial, &target).map_err(|e| e.to_string())?;
    Ok(target)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn release(tag: &str, asset: &str, url: &str) -> Value {
        json!({
            "tag_name": tag, "draft": false, "prerelease": false, "html_url": "https://github.com/x",
            "body": format!("Notes\nSHA-256 : {}", "ab".repeat(32)),
            "assets": [{"name": asset, "browser_download_url": url, "size": 1234}]
        })
    }

    #[test]
    fn the_latest_project_on_installer_is_picked_among_all_software() {
        let releases = json!([
            release(
                "project-on-v2.8.0",
                "ProjectOn_2.8.0_Setup.exe",
                "https://github.com/elieNy7/paratech-web/releases/download/project-on-v2.8.0/ProjectOn_2.8.0_Setup.exe"
            ),
            release(
                "project-on-v3.0.2",
                "ProjectOn_3.0.2_Setup.exe",
                "https://github.com/elieNy7/paratech-web/releases/download/project-on-v3.0.2/ProjectOn_3.0.2_Setup.exe"
            ),
            release("pgraphics-v9.0.0", "Pgraphics_9.0.0_Setup.exe", "https://github.com/x/Pgraphics.exe"),
            release(
                "project-on-v3.1.0",
                "ProjectOn_3.1.0_Setup.exe",
                "https://evil.example.com/ProjectOn_3.1.0_Setup.exe"
            ),
        ]);
        let latest = pick_latest(&releases).unwrap();
        assert_eq!(latest.version, "3.0.2", "l'hôte inconnu est refusé, Pgraphics ignoré");
        assert_eq!(latest.size, 1234);
        assert_eq!(latest.sha256, "ab".repeat(32));
        assert!(is_newer(&latest.version, "3.0.0"));
        assert!(!is_newer("3.0.0", "3.0.0"));
        assert!(!is_newer("2.8.0", "3.0.0"));
        let mut draft = release("project-on-v9.0.0", "ProjectOn_9.0.0_Setup.exe", "https://github.com/a");
        draft["prerelease"] = json!(true);
        assert!(parse_release(&draft).is_none());
    }

    #[test]
    fn only_https_github_hosts_are_allowed() {
        assert!(allowed("https://github.com/a/b"));
        assert!(allowed("https://objects.githubusercontent.com/x"));
        assert!(!allowed("http://github.com/a"));
        assert!(!allowed("https://github.com.evil.example/a"));
        assert!(!allowed("https://user@evil.example/a"));
    }
}
