//! Les **PowerPoint** de la playlist (`office_renderer.py` de la 2.8) : chaque slide est rendu en
//! image 1920 × 1080, puis projeté comme une image. Deux moteurs, comme la 2.8 :
//! 1. **Microsoft PowerPoint**, s'il est installé (export des slides en PNG, fidélité totale) ;
//! 2. **LibreOffice** sinon : la présentation devient un PDF, dont Windows lui-même rend les pages
//!    en images (`Windows.Data.Pdf`).
//!
//! Les images sont gardées dans `media\powerpoint\<nom>-<empreinte>\` avec un marqueur
//! `_complete.json` (taille et date du fichier), **au format de la 2.8** : une présentation déjà
//! rendue par la 2.8 se projette aussitôt, sans moteur. Le rendu se fait dans un dossier d'attente,
//! publié d'un coup : jamais un mélange d'anciens et de nouveaux slides.

use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use serde_json::{Value, json};
use sha2::{Digest, Sha256};

const MARKER: &str = "_complete.json";
const MAX_SLIDES: usize = 1000;
const WIDTH: u32 = 1920;
/// Le temps laissé à un moteur pour une présentation.
const TIMEOUT: Duration = Duration::from_secs(300);

/// Une présentation (`.pptx`, `.ppsx`) ?
pub fn is_powerpoint(path: &str) -> bool {
    matches!(crate::playlist::media_kind(path), crate::playlist::Kind::PowerPoint)
}

/// Le chemin absolu tel que la 2.8 le calcule (`Path.resolve()`), sans le préfixe `\\?\`.
fn absolute(path: &Path) -> PathBuf {
    let full = path.canonicalize().or_else(|_| std::path::absolute(path)).unwrap_or_else(|_| path.to_path_buf());
    let text = full.to_string_lossy();
    match text.strip_prefix(r"\\?\UNC\") {
        Some(rest) => PathBuf::from(format!(r"\\{rest}")),
        None => PathBuf::from(text.strip_prefix(r"\\?\").unwrap_or(&text)),
    }
}

/// Le dossier des images d'une présentation : `media\powerpoint\<nom>-<12 caractères>` (le même que
/// la 2.8 : SHA-256 du chemin absolu en minuscules).
pub fn slides_dir(media: &Path, pptx: &Path) -> PathBuf {
    let full = absolute(pptx);
    let key: String = Sha256::digest(full.to_string_lossy().to_lowercase().as_bytes())
        .iter()
        .take(6)
        .map(|b| format!("{b:02x}"))
        .collect();
    let stem = full.file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
    media.join("powerpoint").join(format!("{stem}-{key}"))
}

fn fingerprint(source: &Path) -> Option<(u64, u64)> {
    let meta = std::fs::metadata(source).ok()?;
    let mtime = meta.modified().ok()?.duration_since(std::time::UNIX_EPOCH).ok()?.as_secs();
    Some((meta.len(), mtime))
}

/// Les images rendues d'un dossier, dans l'ordre des slides.
fn slide_files(dir: &Path) -> Vec<PathBuf> {
    let mut files: Vec<(u32, PathBuf)> = std::fs::read_dir(dir)
        .into_iter()
        .flatten()
        .flatten()
        .filter_map(|e| {
            let name = e.file_name().to_string_lossy().to_string();
            let n = name.strip_prefix("slide-")?.strip_suffix(".png")?.parse().ok()?;
            Some((n, e.path()))
        })
        .collect();
    files.sort();
    files.into_iter().map(|(_, p)| p).collect()
}

/// Les images d'une présentation déjà rendue (par la 3.0 ou la 2.8), si le fichier n'a pas changé.
pub fn cached(media: &Path, pptx: &Path) -> Option<Vec<PathBuf>> {
    let dir = slides_dir(media, pptx);
    let marker: Value = serde_json::from_str(&std::fs::read_to_string(dir.join(MARKER)).ok()?).ok()?;
    let (size, mtime) = fingerprint(pptx)?;
    if marker.get("size")?.as_u64()? != size || marker.get("mtime")?.as_u64()? != mtime {
        return None;
    }
    let files = slide_files(&dir);
    (files.len() as u64 == marker.get("slides")?.as_u64()? && !files.is_empty()).then_some(files)
}

/// Lance un programme sans fenêtre et attend sa fin (au plus [`TIMEOUT`]).
fn run(mut command: std::process::Command) -> Result<std::process::Output, String> {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x0800_0000);
    }
    command.stdout(std::process::Stdio::piped()).stderr(std::process::Stdio::piped());
    let mut child = command.spawn().map_err(|e| e.to_string())?;
    let start = Instant::now();
    loop {
        if child.try_wait().map_err(|e| e.to_string())?.is_some() {
            return child.wait_with_output().map_err(|e| e.to_string());
        }
        if start.elapsed() > TIMEOUT {
            let _ = child.kill();
            return Err("le rendu a pris trop de temps".into());
        }
        std::thread::sleep(Duration::from_millis(100));
    }
}

/// Le moteur 1 : PowerPoint, piloté par PowerShell (COM), exporte chaque slide en PNG.
fn with_powerpoint(pptx: &Path, out: &Path) -> Result<(), String> {
    const SCRIPT: &str = r#"
$ErrorActionPreference = 'Stop'
$app = New-Object -ComObject PowerPoint.Application
$presentation = $app.Presentations.Open($env:PO_SOURCE, $true, $false, $false)
try {
  $count = $presentation.Slides.Count
  if ($count -gt 1000) { throw "Présentation trop grande : $count slides" }
  for ($i = 1; $i -le $count; $i++) {
    $file = Join-Path $env:PO_OUT ('slide-{0:D4}.png' -f $i)
    $presentation.Slides.Item($i).Export($file, 'PNG', 1920, 1080)
  }
} finally {
  $presentation.Close()
  if ($app.Presentations.Count -eq 0) { $app.Quit() }
}
"#;
    let mut command = std::process::Command::new("powershell.exe");
    command
        .args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", SCRIPT])
        .env("PO_SOURCE", pptx)
        .env("PO_OUT", out);
    let output = run(command)?;
    if !output.status.success() || slide_files(out).is_empty() {
        let why = String::from_utf8_lossy(&output.stderr);
        return Err(format!("PowerPoint : {}", why.lines().find(|l| !l.trim().is_empty()).unwrap_or("indisponible")));
    }
    Ok(())
}

fn soffice() -> Option<PathBuf> {
    ["C:/Program Files/LibreOffice/program/soffice.exe", "C:/Program Files (x86)/LibreOffice/program/soffice.exe"]
        .into_iter()
        .map(PathBuf::from)
        .find(|p| p.is_file())
}

/// Le moteur 2 : LibreOffice convertit en PDF, Windows rend les pages.
fn with_libreoffice(pptx: &Path, out: &Path) -> Result<(), String> {
    let soffice = soffice().ok_or("LibreOffice introuvable")?;
    let pdf_dir = out.join("_pdf");
    std::fs::create_dir_all(&pdf_dir).map_err(|e| e.to_string())?;
    let mut command = std::process::Command::new(soffice);
    command.args(["--headless", "--convert-to", "pdf", "--outdir"]).arg(&pdf_dir).arg(pptx);
    let output = run(command)?;
    let pdf = std::fs::read_dir(&pdf_dir)
        .into_iter()
        .flatten()
        .flatten()
        .map(|e| e.path())
        .find(|p| p.extension().is_some_and(|e| e.eq_ignore_ascii_case("pdf")));
    let result = match pdf {
        Some(pdf) if output.status.success() => {
            let helper = std::env::current_exe().map_err(|e| e.to_string())?;
            pdf_to_png(&helper, &pdf, out)
        }
        _ => Err(format!("conversion LibreOffice échouée : {}", String::from_utf8_lossy(&output.stderr).trim())),
    };
    let _ = std::fs::remove_dir_all(&pdf_dir);
    result.map(|_| ())
}

/// Les pages d'un PDF en images `slide-0001.png`…, 1920 de large (Windows.Data.Pdf).
/// L'option de Project-On qui rend les pages d'un PDF en images, dans un processus à part :
/// `Project-On.exe --pdf-en-images <pdf> <dossier>`.
pub const PDF_HELPER_FLAG: &str = "--pdf-en-images";

/// Les pages d'un PDF en images `slide-0001.png`…, 1920 de large, par Windows (`Windows.Data.Pdf`).
///
/// Le moteur PDF de Windows plante à la sortie du processus qui l'a utilisé : le rendu se fait
/// donc dans un processus à part, Project-On lui-même lancé avec [`PDF_HELPER_FLAG`], qui finit
/// sans repasser par ce nettoyage ([`pdf_helper_main`]). `helper` : l'exécutable à lancer
/// (Project-On ; dans un essai, celui construit par Cargo).
pub fn pdf_to_png(helper: &Path, pdf: &Path, out: &Path) -> Result<usize, String> {
    let mut command = std::process::Command::new(helper);
    command.arg(PDF_HELPER_FLAG).arg(pdf).arg(out);
    let output = run(command)?;
    let count = slide_files(out).len();
    if count == 0 {
        return Err(format!(
            "rendu des pages impossible : {}",
            String::from_utf8_lossy(&output.stderr).lines().next().unwrap_or("aucune page")
        ));
    }
    Ok(count)
}

/// Le rendu dans le processus d'aide : les pages du PDF, puis la fin immédiate du processus (code
/// 0 si tout est rendu). Ne revient pas.
#[cfg(windows)]
pub fn pdf_helper_main(pdf: &Path, out: &Path) -> ! {
    use windows::Win32::System::Threading::{GetCurrentProcess, TerminateProcess};
    #[allow(unsafe_code)]
    // SAFETY : initialisation de WinRT pour ce fil (le processus ne fait que ce rendu).
    unsafe {
        let _ = windows::Win32::System::WinRT::RoInitialize(windows::Win32::System::WinRT::RO_INIT_MULTITHREADED);
    }
    let code = match render_pdf_pages(pdf, out) {
        Ok(_) => 0,
        Err(e) => {
            eprintln!("{e}");
            1
        }
    };
    #[allow(unsafe_code)]
    // SAFETY : fin du processus d'aide sans le nettoyage des bibliothèques (celui qui plante) ;
    // les images sont déjà écrites et fermées.
    unsafe {
        let _ = TerminateProcess(GetCurrentProcess(), code);
    }
    std::process::exit(code as i32)
}

#[cfg(not(windows))]
pub fn pdf_helper_main(_pdf: &Path, _out: &Path) -> ! {
    std::process::exit(1)
}

#[cfg(windows)]
fn render_pdf_pages(pdf: &Path, out: &Path) -> Result<usize, String> {
    use windows::Data::Pdf::{PdfDocument, PdfPageRenderOptions};
    use windows::Storage::Streams::{DataReader, DataWriter, InMemoryRandomAccessStream};
    let err = |e: windows::core::Error| format!("rendu des pages impossible : {}", e.message());
    // Le PDF est lu en mémoire : pas de règles d'accès aux fichiers de Windows.Storage.
    let bytes = std::fs::read(pdf).map_err(|e| e.to_string())?;
    let source = InMemoryRandomAccessStream::new().map_err(err)?;
    let writer = DataWriter::CreateDataWriter(&source).map_err(err)?;
    writer.WriteBytes(&bytes).map_err(err)?;
    writer.StoreAsync().map_err(err)?.join().map_err(err)?;
    writer.FlushAsync().map_err(err)?.join().map_err(err)?;
    let _ = writer.DetachStream();
    source.Seek(0).map_err(err)?;
    let document = PdfDocument::LoadFromStreamAsync(&source).map_err(err)?.join().map_err(err)?;
    let count = document.PageCount().map_err(err)? as usize;
    if count > MAX_SLIDES {
        return Err(format!("Présentation trop grande : {count} pages (au plus {MAX_SLIDES})"));
    }
    for index in 0..count {
        let page = document.GetPage(index as u32).map_err(err)?;
        let options = PdfPageRenderOptions::new().map_err(err)?;
        options.SetDestinationWidth(WIDTH).map_err(err)?;
        let stream = InMemoryRandomAccessStream::new().map_err(err)?;
        page.RenderWithOptionsToStreamAsync(&stream, &options).map_err(err)?.join().map_err(err)?;
        let size = stream.Size().map_err(err)? as u32;
        let input = stream.GetInputStreamAt(0).map_err(err)?;
        let reader = DataReader::CreateDataReader(&input).map_err(err)?;
        reader.LoadAsync(size).map_err(err)?.join().map_err(err)?;
        let mut bytes = vec![0u8; size as usize];
        reader.ReadBytes(&mut bytes).map_err(err)?;
        // Tout est fermé tout de suite : rien ne reste aux fils de Windows à la sortie.
        let _ = reader.Close();
        let _ = input.Close();
        let _ = stream.Close();
        let _ = page.Close();
        std::fs::write(out.join(format!("slide-{:04}.png", index + 1)), bytes).map_err(|e| e.to_string())?;
    }
    let _ = writer.Close();
    let _ = source.Close();
    Ok(count)
}

#[cfg(not(windows))]
fn render_pdf_pages(_pdf: &Path, _out: &Path) -> Result<usize, String> {
    Err("rendu des PDF disponible sous Windows seulement".into())
}

/// Rend une présentation (ou reprend son cache) : les images de ses slides, dans l'ordre.
pub fn render(media: &Path, pptx: &Path) -> Result<Vec<PathBuf>, String> {
    if !pptx.is_file() {
        return Err(format!(
            "fichier introuvable : {}",
            pptx.file_name().map(|n| n.to_string_lossy()).unwrap_or_default()
        ));
    }
    if let Some(files) = cached(media, pptx) {
        return Ok(files);
    }
    let dir = slides_dir(media, pptx);
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let staging = dir.join(format!("_attente-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&staging);
    std::fs::create_dir_all(&staging).map_err(|e| e.to_string())?;
    let result = (|| {
        let mut errors = Vec::new();
        if let Err(e) = with_powerpoint(pptx, &staging) {
            errors.push(e);
            for f in slide_files(&staging) {
                let _ = std::fs::remove_file(f);
            }
            with_libreoffice(pptx, &staging).map_err(|e| {
                errors.push(e);
                format!(
                    "aucun moteur de rendu : installez Microsoft PowerPoint ou LibreOffice ({})",
                    errors.join(" ; ")
                )
            })?;
        }
        let files = slide_files(&staging);
        if files.is_empty() || files.len() > MAX_SLIDES {
            return Err(format!("{} slide(s) rendu(s)", files.len()));
        }
        // Publication : l'ancien rendu s'efface, les nouveaux slides et le marqueur arrivent.
        let _ = std::fs::remove_file(dir.join(MARKER));
        for old in slide_files(&dir) {
            let _ = std::fs::remove_file(old);
        }
        for f in &files {
            let name = f.file_name().ok_or("nom de fichier")?;
            std::fs::rename(f, dir.join(name)).map_err(|e| e.to_string())?;
        }
        let (size, mtime) = fingerprint(pptx).ok_or("fichier illisible")?;
        let marker = json!({ "size": size, "mtime": mtime, "slides": files.len() });
        std::fs::write(dir.join(MARKER), marker.to_string()).map_err(|e| e.to_string())?;
        Ok(slide_files(&dir))
    })();
    let _ = std::fs::remove_dir_all(&staging);
    result
}

/// Où en est une présentation de la playlist.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RenderState {
    /// Rendue : son nombre de slides.
    Ready(usize),
    Working,
    Failed(String),
}

/// Les rendus demandés par la régie (un fil par présentation).
#[derive(Default)]
pub struct Renders {
    jobs: std::collections::HashMap<String, std::thread::JoinHandle<Result<Vec<PathBuf>, String>>>,
    done: std::collections::HashMap<String, RenderState>,
}

impl Renders {
    /// Demande le rendu d'une présentation qui n'est ni prête ni en cours.
    pub fn request(&mut self, media: &Path, pptx: &str) {
        if self.jobs.contains_key(pptx) || self.done.contains_key(pptx) {
            return;
        }
        if let Some(files) = cached(media, Path::new(pptx)) {
            self.done.insert(pptx.to_string(), RenderState::Ready(files.len()));
            return;
        }
        let (media, file) = (media.to_path_buf(), PathBuf::from(pptx));
        po_core::journal::line(&format!("PowerPoint : rendu de {}", file.display()));
        self.jobs.insert(pptx.to_string(), std::thread::spawn(move || render(&media, &file)));
    }

    /// Les rendus terminés depuis le dernier appel.
    pub fn poll(&mut self) -> Vec<String> {
        let finished: Vec<String> = self.jobs.iter().filter(|(_, h)| h.is_finished()).map(|(k, _)| k.clone()).collect();
        for key in &finished {
            if let Some(handle) = self.jobs.remove(key) {
                let state = match handle.join().unwrap_or_else(|_| Err("rendu interrompu".into())) {
                    Ok(files) => RenderState::Ready(files.len()),
                    Err(e) => RenderState::Failed(e),
                };
                po_core::journal::line(&format!("PowerPoint : {key} : {state:?}"));
                self.done.insert(key.clone(), state);
            }
        }
        finished
    }

    pub fn busy(&self) -> bool {
        !self.jobs.is_empty()
    }

    pub fn state(&self, pptx: &str) -> Option<RenderState> {
        if self.jobs.contains_key(pptx) {
            return Some(RenderState::Working);
        }
        self.done.get(pptx).cloned()
    }

    /// Oublie un échec (pour réessayer).
    pub fn retry(&mut self, pptx: &str) {
        if matches!(self.done.get(pptx), Some(RenderState::Failed(_))) {
            self.done.remove(pptx);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scratch() -> tempfile::TempDir {
        let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
        std::fs::create_dir_all(&base).unwrap();
        tempfile::tempdir_in(base).unwrap()
    }

    #[test]
    fn a_render_cached_by_the_2_8_is_reused_and_invalidated_when_the_file_changes() {
        let dir = scratch();
        let media = dir.path().join("media");
        let pptx = dir.path().join("Annonces du dimanche.pptx");
        std::fs::write(&pptx, b"PK presentation").unwrap();
        let slides = slides_dir(&media, &pptx);
        assert!(slides.parent().unwrap().ends_with("powerpoint"));
        assert!(slides.file_name().unwrap().to_string_lossy().starts_with("Annonces du dimanche-"));
        // Un rendu laissé par la 2.8 : les images et le marqueur.
        std::fs::create_dir_all(&slides).unwrap();
        for n in [1, 2, 10] {
            std::fs::write(slides.join(format!("slide-{n:04}.png")), b"png").unwrap();
        }
        let (size, mtime) = fingerprint(&pptx).unwrap();
        std::fs::write(slides.join(MARKER), json!({"size": size, "mtime": mtime, "slides": 3}).to_string()).unwrap();
        let files = cached(&media, &pptx).unwrap();
        let names: Vec<String> = files.iter().map(|f| f.file_name().unwrap().to_string_lossy().to_string()).collect();
        assert_eq!(names, ["slide-0001.png", "slide-0002.png", "slide-0010.png"], "ordre des slides");
        assert_eq!(render(&media, &pptx).unwrap(), files, "aucun moteur sollicité");
        // Le fichier change : le rendu n'est plus valable.
        std::fs::write(&pptx, b"PK presentation modifiee").unwrap();
        assert!(cached(&media, &pptx).is_none());
    }

    #[test]
    fn the_cache_folder_is_the_one_of_the_2_8() {
        // `hashlib.sha256(str(Path(p).resolve()).lower().encode()).hexdigest()[:12]` de la 2.8.
        let media = Path::new("C:/media");
        let dir = slides_dir(media, Path::new(r"C:\Église\Cultes\Annonces.pptx"));
        let expected: String = Sha256::digest(r"c:\église\cultes\annonces.pptx".as_bytes())
            .iter()
            .take(6)
            .map(|b| format!("{b:02x}"))
            .collect();
        assert_eq!(dir, media.join("powerpoint").join(format!("Annonces-{expected}")));
    }
}
