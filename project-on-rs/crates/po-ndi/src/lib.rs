//! La sortie NDI de Project-On : une image BGRA **avec transparence** (le bandeau, les lower thirds,
//! les sous-titres) envoyée sur le réseau local, pour vMix, OBS, Pgraphics, un mélangeur NDI.
//!
//! Repris de Pgraphics (`pg-moteur/src/outputs/ndi.rs`, MIT) : la bibliothèque NDI
//! (`Processing.NDI.Lib.x64.dll`, du dossier `ndi/` de l'application ou du runtime NDI 6 installé)
//! est chargée **à la demande** ; sans elle, Project-On marche sans NDI. L'envoi se fait dans un
//! fil à part : une image en retard est remplacée par la suivante, jamais attendue. L'image courante
//! est renvoyée régulièrement (10 fois par seconde), car un récepteur qui arrive après le dernier
//! changement doit la recevoir aussi.
//!
//! Seul module de Project-On qui appelle la bibliothèque NDI : le code `unsafe` est limité aux
//! appels, avec des structures du SDK (`Processing.NDI.Lib.h`, v5 et v6).

#![allow(unsafe_code)]

use std::ffi::{CString, c_char, c_void};
use std::path::{Path, PathBuf};
use std::sync::mpsc::{Receiver, RecvTimeoutError, Sender as Channel, channel};
use std::sync::{Arc, Mutex, OnceLock};
use std::thread::JoinHandle;
use std::time::Duration;

const DLL: &str = "Processing.NDI.Lib.x64.dll";
/// `NDI_LIB_FOURCC('B','G','R','A')`.
const FOURCC_BGRA: u32 = u32::from_le_bytes(*b"BGRA");
const PROGRESSIVE: i32 = 1;
/// `NDIlib_send_timecode_synthesize`.
const TIMECODE_SYNTHESIZE: i64 = i64::MAX;

#[repr(C)]
struct SendCreate {
    name: *const c_char,
    groups: *const c_char,
    clock_video: bool,
    clock_audio: bool,
}

#[repr(C)]
struct VideoFrame {
    xres: i32,
    yres: i32,
    fourcc: u32,
    frame_rate_n: i32,
    frame_rate_d: i32,
    aspect: f32,
    frame_format: i32,
    timecode: i64,
    data: *const u8,
    line_stride: i32,
    metadata: *const c_char,
    timestamp: i64,
}

type Initialize = unsafe extern "C" fn() -> bool;
type Create = unsafe extern "C" fn(*const SendCreate) -> *mut c_void;
type Destroy = unsafe extern "C" fn(*mut c_void);
type SendVideo = unsafe extern "C" fn(*mut c_void, *const VideoFrame);
type Connections = unsafe extern "C" fn(*mut c_void, u32) -> i32;

#[cfg(windows)]
type Farproc = unsafe extern "system" fn() -> isize;

struct Library {
    create: Create,
    destroy: Destroy,
    video: SendVideo,
    connections: Connections,
    path: PathBuf,
}

static LIBRARY: OnceLock<Result<Library, String>> = OnceLock::new();

/// Les emplacements possibles de la bibliothèque : ceux de l'application d'abord (`ndi/` à côté de
/// l'exécutable, comme la 2.x), puis le runtime NDI installé.
pub fn candidates(app_dirs: &[PathBuf]) -> Vec<PathBuf> {
    let mut dirs: Vec<PathBuf> = Vec::new();
    if let Some(p) = std::env::var_os("PROJECT_ON_NDI").map(PathBuf::from) {
        dirs.push(p);
    }
    dirs.extend(app_dirs.iter().cloned());
    if let Some(exe_dir) = std::env::current_exe().ok().and_then(|e| e.parent().map(Path::to_path_buf)) {
        dirs.push(exe_dir.join("ndi"));
        dirs.push(exe_dir);
    }
    for var in ["NDI_RUNTIME_DIR_V6", "NDI_RUNTIME_DIR_V5", "NDI_RUNTIME_DIR"] {
        if let Some(p) = std::env::var_os(var) {
            dirs.push(PathBuf::from(p));
        }
    }
    for base in ["PROGRAMFILES", "PROGRAMFILES(X86)"] {
        if let Some(p) = std::env::var_os(base) {
            dirs.push(PathBuf::from(p).join("NDI").join("NDI 6 Runtime").join("v6"));
        }
    }
    dirs.into_iter()
        .map(|d| if d.extension().is_some_and(|e| e.eq_ignore_ascii_case("dll")) { d } else { d.join(DLL) })
        .collect()
}

#[cfg(windows)]
fn load(app_dirs: &[PathBuf]) -> Result<Library, String> {
    use std::os::windows::ffi::OsStrExt;
    use windows::Win32::System::LibraryLoader::{GetProcAddress, LoadLibraryW};
    use windows::core::{PCSTR, PCWSTR};

    let path = candidates(app_dirs)
        .into_iter()
        .find(|p| p.is_file())
        .ok_or_else(|| "bibliothèque NDI introuvable : installez le runtime NDI 6 (ndi.video)".to_string())?;
    let wide: Vec<u16> = path.as_os_str().encode_wide().chain(std::iter::once(0)).collect();
    // SAFETY : chemin terminé par un zéro ; la bibliothèque reste chargée jusqu'à la fin du programme.
    let module = unsafe { LoadLibraryW(PCWSTR(wide.as_ptr())) }.map_err(|e| format!("{} : {e}", path.display()))?;
    let symbol = |name: &[u8]| {
        // SAFETY : nom terminé par un zéro.
        unsafe { GetProcAddress(module, PCSTR(name.as_ptr())) }
            .ok_or_else(|| format!("{} : fonction absente", String::from_utf8_lossy(&name[..name.len() - 1])))
    };
    // SAFETY : signatures du SDK NDI (Processing.NDI.Lib.h, v5 et v6).
    unsafe {
        let initialize = std::mem::transmute::<Farproc, Initialize>(symbol(b"NDIlib_initialize\0")?);
        if !initialize() {
            return Err("NDI refuse de démarrer sur ce processeur".into());
        }
        Ok(Library {
            create: std::mem::transmute::<Farproc, Create>(symbol(b"NDIlib_send_create\0")?),
            destroy: std::mem::transmute::<Farproc, Destroy>(symbol(b"NDIlib_send_destroy\0")?),
            video: std::mem::transmute::<Farproc, SendVideo>(symbol(b"NDIlib_send_send_video_v2\0")?),
            connections: std::mem::transmute::<Farproc, Connections>(symbol(b"NDIlib_send_get_no_connections\0")?),
            path,
        })
    }
}

#[cfg(not(windows))]
fn load(_: &[PathBuf]) -> Result<Library, String> {
    Err("NDI : seulement sous Windows pour l'instant".into())
}

fn library(app_dirs: &[PathBuf]) -> Result<&'static Library, String> {
    LIBRARY.get_or_init(|| load(app_dirs)).as_ref().map_err(Clone::clone)
}

/// La bibliothèque NDI est-elle là ? Rend son chemin, ou pourquoi elle manque.
pub fn available(app_dirs: &[PathBuf]) -> Result<PathBuf, String> {
    library(app_dirs).map(|l| l.path.clone())
}

/// Une image BGRA non prémultipliée, ligne par ligne, sans marge.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Image {
    pub width: u32,
    pub height: u32,
    pub bgra: Vec<u8>,
}

impl Image {
    /// Depuis des pixels RGBA **prémultipliés** (ceux de tiny-skia) : NDI attend du BGRA droit.
    pub fn from_premultiplied_rgba(width: u32, height: u32, rgba: &[u8]) -> Image {
        let mut bgra = Vec::with_capacity(rgba.len());
        for px in rgba.as_chunks::<4>().0 {
            let a = px[3];
            let un = |c: u8| {
                if a == 0 { 0 } else { ((u32::from(c) * 255 + u32::from(a) / 2) / u32::from(a)).min(255) as u8 }
            };
            bgra.extend_from_slice(&[un(px[2]), un(px[1]), un(px[0]), a]);
        }
        Image { width, height, bgra }
    }
}

/// Un émetteur NDI. Il s'arrête quand on le lâche.
pub struct Sender {
    frames: Option<Channel<Arc<Image>>>,
    connections: Arc<Mutex<i32>>,
    thread: Option<JoinHandle<()>>,
    pub name: String,
}

struct Handle(*mut c_void);
// SAFETY : l'émetteur NDI n'est utilisé que par le fil d'envoi.
unsafe impl Send for Handle {}

impl Sender {
    /// Crée la source NDI `name` (par exemple « Project-On Diffusion »).
    pub fn start(name: &str, app_dirs: &[PathBuf]) -> Result<Sender, String> {
        let lib = library(app_dirs)?;
        let c_name = CString::new(name).map_err(|_| "nom NDI invalide".to_string())?;
        let settings =
            SendCreate { name: c_name.as_ptr(), groups: std::ptr::null(), clock_video: false, clock_audio: false };
        // SAFETY : structure du SDK, nom valide pendant l'appel (NDI le copie).
        let handle = unsafe { (lib.create)(&settings) };
        if handle.is_null() {
            return Err("NDI : la source ne peut pas être créée".into());
        }
        let handle = Handle(handle);
        let (frames, incoming) = channel::<Arc<Image>>();
        let connections = Arc::new(Mutex::new(0));
        let seen = connections.clone();
        let thread = std::thread::Builder::new()
            .name("po-ndi".into())
            .spawn(move || send_loop(lib, handle, incoming, seen))
            .map_err(|e| e.to_string())?;
        Ok(Sender { frames: Some(frames), connections, thread: Some(thread), name: name.to_string() })
    }

    /// Envoie une image, sans attendre : si le fil d'envoi est occupé, seule la plus récente des
    /// images en attente partira.
    pub fn send(&self, image: Arc<Image>) {
        if let Some(frames) = &self.frames {
            let _ = frames.send(image);
        }
    }

    /// Le nombre de récepteurs connectés (vMix, OBS…).
    pub fn connections(&self) -> i32 {
        *self.connections.lock().unwrap_or_else(|e| e.into_inner())
    }
}

impl Drop for Sender {
    fn drop(&mut self) {
        // Le canal fermé arrête le fil, qui détruit l'émetteur.
        self.frames = None;
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

fn send_loop(lib: &'static Library, handle: Handle, incoming: Receiver<Arc<Image>>, connections: Arc<Mutex<i32>>) {
    let mut current: Option<Arc<Image>> = None;
    loop {
        match incoming.recv_timeout(Duration::from_millis(100)) {
            Ok(image) => {
                // Les images arrivées entre-temps : seule la dernière compte.
                current = Some(incoming.try_iter().last().unwrap_or(image));
            }
            Err(RecvTimeoutError::Timeout) => {}
            Err(RecvTimeoutError::Disconnected) => break,
        }
        if let Some(image) = &current {
            let expected = image.width as usize * image.height as usize * 4;
            if image.bgra.len() == expected && image.width > 0 {
                let frame = VideoFrame {
                    xres: image.width as i32,
                    yres: image.height as i32,
                    fourcc: FOURCC_BGRA,
                    frame_rate_n: 10,
                    frame_rate_d: 1,
                    aspect: image.width as f32 / image.height as f32,
                    frame_format: PROGRESSIVE,
                    timecode: TIMECODE_SYNTHESIZE,
                    data: image.bgra.as_ptr(),
                    line_stride: image.width as i32 * 4,
                    metadata: std::ptr::null(),
                    timestamp: 0,
                };
                // SAFETY : image valide pendant l'appel (envoi synchrone).
                unsafe { (lib.video)(handle.0, &frame) };
            }
        }
        // SAFETY : émetteur valide, pas d'attente.
        let n = unsafe { (lib.connections)(handle.0, 0) };
        *connections.lock().unwrap_or_else(|e| e.into_inner()) = n;
    }
    // SAFETY : plus aucun envoi après cette ligne.
    unsafe { (lib.destroy)(handle.0) };
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn premultiplied_pixels_become_straight_bgra() {
        // Blanc opaque, rouge à moitié transparent (prémultiplié : 128,0,0,128), transparent.
        let image = Image::from_premultiplied_rgba(3, 1, &[255, 255, 255, 255, 128, 0, 0, 128, 0, 0, 0, 0]);
        assert_eq!(image.bgra, [255, 255, 255, 255, 0, 0, 255, 128, 0, 0, 0, 0]);
    }

    #[test]
    fn the_library_is_looked_for_beside_the_application_then_in_the_runtime() {
        let dirs = candidates(&[PathBuf::from("C:/app/ndi")]);
        assert!(dirs[0].ends_with("ndi/Processing.NDI.Lib.x64.dll") || dirs.iter().any(|d| d.starts_with("C:/app")));
        assert!(dirs.iter().all(|d| d.file_name().is_some_and(|n| n == DLL)));
    }

    /// À lancer à la main (`cargo test -p po-ndi -- --ignored`) : crée une vraie source NDI, ce
    /// qui peut faire apparaître la demande du pare-feu de Windows.
    #[test]
    #[ignore]
    fn sends_frames_when_the_runtime_is_installed() {
        if available(&[]).is_err() {
            return;
        }
        let sender = Sender::start("Project-On essai", &[]).unwrap();
        let image = Arc::new(Image { width: 64, height: 36, bgra: vec![128; 64 * 36 * 4] });
        for _ in 0..5 {
            sender.send(image.clone());
            std::thread::sleep(Duration::from_millis(50));
        }
        assert!(sender.connections() >= 0);
    }
}
