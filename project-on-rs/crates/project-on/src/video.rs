//! La lecture des vidéos (repris de Pgraphics, `pg-moteur/src/source/media.rs`, MIT) : FFmpeg
//! décode la vidéo en images RVBA déjà à la bonne taille, que le lecteur pose **à leur heure**, et
//! le son part vers la sortie audio de Windows. Une vidéo se met en pause, reprend, recommence,
//! tourne en boucle ; sa fin est signalée (le diaporama passe alors au média suivant).
//!
//! FFmpeg est cherché dans `PROJECT_ON_FFMPEG`, puis dans le dossier `ffmpeg\` à côté de
//! l'exécutable (comme Pgraphics), puis dans le PATH. Sans lui, les vidéos ne sont pas lues (la
//! régie le dit).

use std::io::Read;
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

/// `CREATE_NO_WINDOW` : FFmpeg ne fait jamais apparaître de console.
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// Les images par seconde de la lecture.
pub const FPS: u32 = 30;

/// Un fichier vidéo, d'après son extension.
pub fn is_video_file(path: &str) -> bool {
    let ext = Path::new(path.trim()).extension().map(|e| e.to_string_lossy().to_lowercase()).unwrap_or_default();
    matches!(ext.as_str(), "mp4" | "m4v" | "mov" | "mkv" | "webm" | "avi" | "wmv" | "mpg" | "mpeg")
}

/// FFmpeg : `PROJECT_ON_FFMPEG`, sinon `ffmpeg\ffmpeg.exe` à côté de l'exécutable, sinon le PATH.
pub fn find_ffmpeg() -> Option<PathBuf> {
    if let Some(path) = std::env::var_os("PROJECT_ON_FFMPEG").map(PathBuf::from).filter(|p| p.is_file()) {
        return Some(path);
    }
    let name = if cfg!(windows) { "ffmpeg.exe" } else { "ffmpeg" };
    if let Some(exe_dir) = std::env::current_exe().ok().and_then(|e| e.parent().map(PathBuf::from)) {
        for candidate in [exe_dir.join("ffmpeg").join(name), exe_dir.join(name)] {
            if candidate.is_file() {
                return Some(candidate);
            }
        }
    }
    std::env::var_os("PATH")
        .into_iter()
        .flat_map(|paths| std::env::split_paths(&paths).collect::<Vec<_>>())
        .map(|dir| dir.join(name))
        .find(|p| p.is_file())
}

fn command(ffmpeg: &Path) -> Command {
    let mut cmd = Command::new(ffmpeg);
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);
    cmd
}

/// Ce qu'on sait d'une vidéo avant de la lire.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Probe {
    pub width: u32,
    pub height: u32,
    pub has_audio: bool,
    pub duration_s: f64,
}

/// Lit la description d'un fichier (`ffmpeg -i`).
pub fn probe(ffmpeg: &Path, path: &Path) -> Result<Probe, String> {
    let output = command(ffmpeg)
        .args(["-hide_banner", "-nostdin", "-i"])
        .arg(path)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .output()
        .map_err(|e| format!("FFmpeg : {e}"))?;
    // Sans sortie demandée, FFmpeg s'arrête en erreur : la description des flux est dans stderr.
    let probe = parse_info(&String::from_utf8_lossy(&output.stderr));
    if probe.width == 0 { Err(format!("Vidéo illisible : {}", path.display())) } else { Ok(probe) }
}

/// `Duration: 00:00:06.00`, puis les flux (`Stream #0:0…: Video: h264 …, 1280x720 …`, `Audio`).
pub fn parse_info(text: &str) -> Probe {
    let mut probe = Probe { width: 0, height: 0, has_audio: false, duration_s: 0.0 };
    for line in text.lines() {
        let line = line.trim();
        if let Some(rest) = line.strip_prefix("Duration:") {
            let stamp = rest.trim().split(',').next().unwrap_or("");
            let parts: Vec<f64> = stamp.split(':').filter_map(|p| p.trim().parse().ok()).collect();
            if let [h, m, s] = parts[..] {
                probe.duration_s = h * 3600.0 + m * 60.0 + s;
            }
        } else if line.starts_with("Stream #") {
            if line.contains(": Audio:") {
                probe.has_audio = true;
            } else if line.contains(": Video:") && probe.width == 0 {
                let size = line
                    .split([' ', ','])
                    .filter_map(|t| t.split_once('x'))
                    .find_map(|(w, h)| Some((w.parse::<u32>().ok()?, h.parse::<u32>().ok()?)));
                if let Some((w, h)) = size {
                    probe.width = w;
                    probe.height = h;
                }
            }
        }
    }
    probe
}

/// La taille de décodage : la vidéo tient dans `max` (jamais agrandie), dimensions paires.
pub fn decode_size(source: (u32, u32), max: (u32, u32)) -> (u32, u32) {
    let (sw, sh) = (f64::from(source.0.max(2)), f64::from(source.1.max(2)));
    let factor = (f64::from(max.0) / sw).min(f64::from(max.1) / sh).min(1.0);
    let even = |v: f64| ((v.round() as u32) & !1).max(2);
    (even(sw * factor), even(sh * factor))
}

/// Les arguments de FFmpeg : l'image en RVBA sur sa sortie, le son (s'il y en a) en PCM 48 kHz
/// stéréo sur une connexion locale.
pub fn decode_args(path: &Path, start_s: f64, looping: bool, size: (u32, u32), audio_port: Option<u16>) -> Vec<String> {
    let mut args: Vec<String> =
        ["-hide_banner", "-loglevel", "error", "-nostats", "-nostdin"].map(String::from).to_vec();
    if looping {
        args.extend(["-stream_loop", "-1"].map(String::from));
    }
    if start_s > 0.0 {
        args.extend(["-ss".to_string(), format!("{start_s:.3}")]);
    }
    args.extend(["-i".to_string(), path.to_string_lossy().into_owned()]);
    let filter = format!("fps={FPS},scale={}:{}:flags=bilinear,format=rgba", size.0, size.1);
    args.extend(["-map", "0:v:0", "-vf", &filter, "-f", "rawvideo", "pipe:1"].map(String::from));
    if let Some(port) = audio_port {
        args.extend(
            ["-map", "0:a:0", "-ac", "2", "-ar", "48000", "-f", "f32le", &format!("tcp://127.0.0.1:{port}")]
                .map(String::from),
        );
    }
    args
}

/// L'état partagé entre le lecteur et la régie.
#[derive(Default)]
struct State {
    /// La dernière image (RVBA) et son numéro.
    frame: Option<Arc<Vec<u8>>>,
    seq: u64,
    /// Les images montrées depuis le départ.
    shown: u64,
    paused: bool,
    ended: bool,
    stop: bool,
}

/// Une vidéo en lecture.
pub struct Player {
    pub path: PathBuf,
    pub probe: Probe,
    pub size: (u32, u32),
    pub looping: bool,
    start_s: f64,
    state: Arc<(Mutex<State>, Condvar)>,
    volume: Arc<AtomicU32>,
    muted: Arc<AtomicBool>,
    child: Option<Child>,
    threads: Vec<JoinHandle<()>>,
    audio: Option<cpal::Stream>,
}

fn lock(state: &Mutex<State>) -> std::sync::MutexGuard<'_, State> {
    state.lock().unwrap_or_else(|e| e.into_inner())
}

impl Player {
    /// Lance la lecture de `path` à partir de `start_s`, l'image tenant dans `max`. `muted` : sans
    /// son (essais, aperçu).
    pub fn start(path: &Path, start_s: f64, looping: bool, max: (u32, u32), muted: bool) -> Result<Player, String> {
        let ffmpeg = find_ffmpeg().ok_or("FFmpeg introuvable : les vidéos ne peuvent pas être lues")?;
        let probe = probe(&ffmpeg, path)?;
        let size = decode_size((probe.width, probe.height), max);
        let listener = (probe.has_audio && !muted).then(|| TcpListener::bind("127.0.0.1:0").ok()).flatten();
        let port = listener.as_ref().and_then(|l| l.local_addr().ok()).map(|a| a.port());
        let mut child = command(&ffmpeg)
            .args(decode_args(path, start_s, looping, size, port))
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| format!("FFmpeg : {e}"))?;
        let stdout = child.stdout.take().ok_or("FFmpeg : pas de sortie")?;
        let state = Arc::new((Mutex::new(State::default()), Condvar::new()));
        let volume = Arc::new(AtomicU32::new(1.0f32.to_bits()));
        let muted_flag = Arc::new(AtomicBool::new(muted));
        let mut threads = Vec::new();
        // Les images, chacune à son heure (les pauses repoussent l'horloge).
        {
            let state = state.clone();
            let bytes = size.0 as usize * size.1 as usize * 4;
            threads.push(
                std::thread::Builder::new()
                    .name("po-video".into())
                    .spawn(move || video_loop(stdout, bytes, &state))
                    .map_err(|e| e.to_string())?,
            );
        }
        // Le son : lu sur la connexion locale, joué par la sortie audio de Windows.
        let mut audio = None;
        if let Some(listener) = listener {
            let buffer = Arc::new(Mutex::new(std::collections::VecDeque::<f32>::with_capacity(48_000 * 2)));
            {
                let (buffer, state) = (buffer.clone(), state.clone());
                threads.push(
                    std::thread::Builder::new()
                        .name("po-video-son".into())
                        .spawn(move || audio_loop(&listener, &buffer, &state))
                        .map_err(|e| e.to_string())?,
                );
            }
            audio = output_stream(buffer, volume.clone(), muted_flag.clone());
        }
        Ok(Player {
            path: path.to_path_buf(),
            probe,
            size,
            looping,
            start_s,
            state,
            volume,
            muted: muted_flag,
            child: Some(child),
            threads,
            audio,
        })
    }

    /// La dernière image (numéro, pixels RVBA), si elle est nouvelle depuis `after`.
    pub fn frame_after(&self, after: u64) -> Option<(u64, Arc<Vec<u8>>)> {
        let s = lock(&self.state.0);
        (s.seq > after).then(|| s.frame.clone().map(|f| (s.seq, f))).flatten()
    }

    /// La position, en secondes depuis le début de la vidéo.
    pub fn position(&self) -> f64 {
        let shown = lock(&self.state.0).shown as f64 / f64::from(FPS);
        let position = self.start_s + shown;
        if self.looping && self.probe.duration_s > 0.0 { position % self.probe.duration_s } else { position }
    }

    pub fn ended(&self) -> bool {
        lock(&self.state.0).ended
    }

    pub fn paused(&self) -> bool {
        lock(&self.state.0).paused
    }

    /// Pause ou reprise.
    pub fn set_paused(&self, paused: bool) {
        lock(&self.state.0).paused = paused;
        self.state.1.notify_all();
        if let Some(stream) = &self.audio {
            use cpal::traits::StreamTrait;
            let _ = if paused { stream.pause() } else { stream.play() };
        }
    }

    /// Le volume, de 0 à 1.
    pub fn set_volume(&self, volume: f32) {
        self.volume.store(volume.clamp(0.0, 1.0).to_bits(), Ordering::Relaxed);
    }

    pub fn volume(&self) -> f32 {
        f32::from_bits(self.volume.load(Ordering::Relaxed))
    }

    pub fn set_muted(&self, muted: bool) {
        self.muted.store(muted, Ordering::Relaxed);
    }
}

impl Drop for Player {
    fn drop(&mut self) {
        lock(&self.state.0).stop = true;
        self.state.1.notify_all();
        self.audio = None;
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        for thread in self.threads.drain(..) {
            let _ = thread.join();
        }
    }
}

fn video_loop(mut stdout: impl Read, bytes: usize, state: &(Mutex<State>, Condvar)) {
    let period = Duration::from_nanos(1_000_000_000 / u64::from(FPS));
    let mut clock = Instant::now();
    let mut index: u64 = 0;
    loop {
        let mut frame = vec![0u8; bytes];
        if stdout.read_exact(&mut frame).is_err() {
            lock(&state.0).ended = true;
            return;
        }
        // L'heure de cette image ; une pause repousse l'horloge d'autant.
        loop {
            let s = lock(&state.0);
            if s.stop {
                return;
            }
            if s.paused {
                let paused_at = Instant::now();
                let s = state.1.wait_while(s, |s| s.paused && !s.stop).unwrap_or_else(|e| e.into_inner());
                if s.stop {
                    return;
                }
                clock += paused_at.elapsed();
                continue;
            }
            drop(s);
            let due = clock + period * u32::try_from(index).unwrap_or(u32::MAX);
            let now = Instant::now();
            if due > now {
                std::thread::sleep((due - now).min(Duration::from_millis(50)));
                continue;
            }
            break;
        }
        let mut s = lock(&state.0);
        s.frame = Some(Arc::new(frame));
        s.seq += 1;
        s.shown += 1;
        index += 1;
    }
}

fn audio_loop(
    listener: &TcpListener,
    buffer: &Mutex<std::collections::VecDeque<f32>>,
    state: &(Mutex<State>, Condvar),
) {
    let _ = listener.set_nonblocking(false);
    let Ok((mut stream, _)) = listener.accept() else { return };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(200)));
    let mut raw = [0u8; 4096];
    // Les octets d'un échantillon coupé entre deux lectures : gardés pour la suivante, sinon tout
    // le son qui suit serait décalé (du bruit).
    let mut pending: Vec<u8> = Vec::with_capacity(4100);
    loop {
        if lock(&state.0).stop {
            return;
        }
        // Au plus une demi-seconde d'avance : FFmpeg attend, et le son suit l'image.
        if buffer.lock().map(|b| b.len()).unwrap_or(0) > 48_000 {
            std::thread::sleep(Duration::from_millis(10));
            continue;
        }
        match stream.read(&mut raw) {
            Ok(0) => return,
            Ok(n) => {
                pending.extend_from_slice(&raw[..n]);
                let whole = pending.len() - pending.len() % 4;
                if let Ok(mut b) = buffer.lock() {
                    b.extend(pending[..whole].as_chunks::<4>().0.iter().map(|c| f32::from_le_bytes(*c)));
                }
                pending.drain(..whole);
            }
            Err(e) if matches!(e.kind(), std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut) => {}
            Err(_) => return,
        }
    }
}

/// La sortie audio par défaut, en stéréo 48 kHz, tirée du tampon (silence s'il est vide).
fn output_stream(
    buffer: Arc<Mutex<std::collections::VecDeque<f32>>>,
    volume: Arc<AtomicU32>,
    muted: Arc<AtomicBool>,
) -> Option<cpal::Stream> {
    use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
    let device = cpal::default_host().default_output_device()?;
    let config = cpal::StreamConfig { channels: 2, sample_rate: 48_000, buffer_size: cpal::BufferSize::Default };
    let stream = device
        .build_output_stream(
            config,
            move |out: &mut [f32], _| {
                let gain =
                    if muted.load(Ordering::Relaxed) { 0.0 } else { f32::from_bits(volume.load(Ordering::Relaxed)) };
                let mut b = buffer.lock().unwrap_or_else(|e| e.into_inner());
                for sample in out.iter_mut() {
                    *sample = b.pop_front().unwrap_or(0.0) * gain;
                }
            },
            |e| po_core::journal::line(&format!("vidéo : son interrompu ({e})")),
            None,
        )
        .ok()?;
    stream.play().ok()?;
    Some(stream)
}

/// La vidéo au direct : son lecteur et sa texture (l'image affichée dans la régie et la projection).
pub struct LiveVideo {
    pub player: Player,
    texture: Option<egui::TextureHandle>,
    seq: u64,
}

impl LiveVideo {
    pub fn new(player: Player) -> Self {
        LiveVideo { player, texture: None, seq: 0 }
    }

    /// La dernière image devient la texture (à chaque image de la régie).
    pub fn upload(&mut self, ctx: &egui::Context) {
        if let Some((seq, pixels)) = self.player.frame_after(self.seq) {
            let (w, h) = self.player.size;
            if pixels.len() == (w * h * 4) as usize {
                let image = egui::ColorImage::from_rgba_unmultiplied([w as usize, h as usize], &pixels);
                match &mut self.texture {
                    Some(texture) => texture.set(image, egui::TextureOptions::LINEAR),
                    None => self.texture = Some(ctx.load_texture("video-direct", image, egui::TextureOptions::LINEAR)),
                }
            }
            self.seq = seq;
        }
    }

    pub fn texture(&self) -> Option<&egui::TextureHandle> {
        self.texture.as_ref()
    }
}

/// Pose l'image de la vidéo dans `area`, en entier, centrée.
pub fn paint(painter: &egui::Painter, area: egui::Rect, texture: &egui::TextureHandle) {
    let [w, h] = texture.size();
    let rect = crate::stage::fit(area, w as f32, h as f32);
    let uv = egui::Rect::from_min_max(egui::pos2(0.0, 0.0), egui::pos2(1.0, 1.0));
    painter.image(texture.id(), rect, uv, egui::Color32::WHITE);
}

/// « 1:02 » / « 1:02:03 ».
pub fn clock(seconds: f64) -> String {
    let s = seconds.max(0.0) as u64;
    if s >= 3600 {
        format!("{}:{:02}:{:02}", s / 3600, s % 3600 / 60, s % 60)
    } else {
        format!("{}:{:02}", s / 60, s % 60)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_description_of_a_video_is_read() {
        let text = "Input #0, mov,mp4, from 'x.mp4':\n  Duration: 00:01:02.48, start: 0.000000, bitrate: 1234 kb/s\n  \
                    Stream #0:0[0x1](und): Video: h264 (High), yuv420p(progressive), 1920x1080 [SAR 1:1 DAR 16:9], 25 fps\n  \
                    Stream #0:1[0x2](und): Audio: aac (LC), 48000 Hz, stereo, fltp, 128 kb/s";
        let p = parse_info(text);
        assert_eq!((p.width, p.height, p.has_audio), (1920, 1080, true));
        assert!((p.duration_s - 62.48).abs() < 1e-9);
        let silent = parse_info(
            "  Duration: N/A, bitrate: N/A\n  Stream #0:0: Video: vp9, yuv420p(tv), 640x360, SAR 1:1 DAR 16:9, 30 fps",
        );
        assert_eq!((silent.width, silent.height, silent.has_audio, silent.duration_s), (640, 360, false, 0.0));
    }

    #[test]
    fn sizes_args_and_clock() {
        assert_eq!(decode_size((3840, 2160), (1920, 1080)), (1920, 1080));
        assert_eq!(decode_size((640, 480), (1920, 1080)), (640, 480), "jamais agrandie");
        assert_eq!(decode_size((1081, 721), (1920, 1080)), (1080, 720), "dimensions paires");
        let a = decode_args(Path::new("C:/medias/clip.mp4"), 1.5, true, (1280, 720), Some(5000)).join(" ");
        assert!(a.contains("-stream_loop -1 -ss 1.500 -i C:/medias/clip.mp4"), "{a}");
        assert!(a.contains("-vf fps=30,scale=1280:720:flags=bilinear,format=rgba -f rawvideo pipe:1"));
        assert!(a.ends_with("-f f32le tcp://127.0.0.1:5000"));
        assert!(!decode_args(Path::new("a.mp4"), 0.0, false, (2, 2), None).join(" ").contains("-ss"));
        assert_eq!((clock(62.4), clock(3723.0)), ("1:02".to_string(), "1:02:03".to_string()));
        assert!(is_video_file("C:/x/Clip.MP4") && !is_video_file("photo.jpg"));
    }

    /// Une vraie lecture, si FFmpeg est là : une vidéo d'essai de 2 s (mire, sans son) fabriquée par
    /// FFmpeg, lue jusqu'au bout ; pause et reprise.
    #[test]
    fn a_real_video_plays_to_its_end_when_ffmpeg_is_installed() {
        let Some(ffmpeg) = find_ffmpeg() else {
            eprintln!("FFmpeg absent : essai sauté");
            return;
        };
        let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
        std::fs::create_dir_all(&dir).unwrap();
        let clip = dir.join(format!("essai-video-{}.mp4", std::process::id()));
        let made = command(&ffmpeg)
            .args([
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=320x240:rate=30:duration=2",
            ])
            .args(["-pix_fmt", "yuv420p"])
            .arg(&clip)
            .status()
            .unwrap();
        assert!(made.success());
        let player = Player::start(&clip, 0.0, false, (1920, 1080), true).unwrap();
        assert_eq!(player.size, (320, 240));
        assert!((player.probe.duration_s - 2.0).abs() < 0.1);
        let start = Instant::now();
        while player.frame_after(0).is_none() && start.elapsed() < Duration::from_secs(10) {
            std::thread::sleep(Duration::from_millis(10));
        }
        let (seq, pixels) = player.frame_after(0).expect("une première image");
        assert_eq!(pixels.len(), 320 * 240 * 4);
        // En pause, l'image ne change plus.
        player.set_paused(true);
        std::thread::sleep(Duration::from_millis(150));
        let held = player.frame_after(0).unwrap().0;
        std::thread::sleep(Duration::from_millis(300));
        assert_eq!(player.frame_after(0).unwrap().0, held, "pause");
        player.set_paused(false);
        while !player.ended() && start.elapsed() < Duration::from_secs(15) {
            std::thread::sleep(Duration::from_millis(20));
        }
        assert!(player.ended(), "la fin est signalée");
        assert!(player.frame_after(seq).is_some());
        assert!((player.position() - 2.0).abs() < 0.2, "position {}", player.position());
        drop(player);
        let _ = std::fs::remove_file(&clip);
    }
}
