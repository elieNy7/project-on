//! Les sorties de diffusion rendues par Project-On : la source **NDI** « Project-On Diffusion »
//! (bandeau et lower third, avec transparence) et les sorties **HDMI** (une fenêtre plein écran
//! sur un écran branché au mélangeur : bandeau ou sous-titres sur une couleur de clé, ou retour de
//! scène). Elles montrent ce que montrent les écrans Web du même genre (`po_web::Hub`), avec le
//! même moteur de rendu. Le rendu se fait dans un fil à part, seulement quand l'image change
//! (30 fois par seconde pendant l'entrée ou la sortie d'un lower third).

use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use po_design::Rgba;
use po_web::{Hub, ScreenKind};

/// Ce que les sorties doivent montrer.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Wanted {
    pub ndi: bool,
    /// Les sorties HDMI : genre et taille.
    pub hdmi: Vec<(ScreenKind, (u32, u32))>,
    /// La couleur de clé des sorties HDMI (bandeau, sous-titres).
    pub key: Option<Rgba>,
    /// La mire (F8) à la place des sorties HDMI.
    pub pattern: bool,
}

/// L'état partagé avec le fil de rendu.
#[derive(Default)]
struct Shared {
    wanted: Wanted,
    stop: bool,
    /// Les images HDMI prêtes, par genre (RVBA prémultiplié).
    frames: HashMap<ScreenKind, ((u32, u32), Vec<u8>)>,
    ndi_status: Option<Result<String, String>>,
    ndi_receivers: i32,
}

/// Les sorties NDI et HDMI.
pub struct Outputs {
    shared: Arc<Mutex<Shared>>,
    thread: Option<JoinHandle<()>>,
    textures: HashMap<ScreenKind, egui::TextureHandle>,
}

fn lock(shared: &Mutex<Shared>) -> std::sync::MutexGuard<'_, Shared> {
    shared.lock().unwrap_or_else(|e| e.into_inner())
}

impl Outputs {
    pub fn start(hub: Arc<Hub>, wake: impl Fn() + Send + 'static) -> Outputs {
        let shared = Arc::new(Mutex::new(Shared::default()));
        let state = shared.clone();
        let thread =
            std::thread::Builder::new().name("po-sorties".into()).spawn(move || render_loop(&hub, &state, &wake)).ok();
        Outputs { shared, thread, textures: HashMap::new() }
    }

    /// Change ce que les sorties montrent.
    pub fn want(&self, wanted: Wanted) {
        let mut shared = lock(&self.shared);
        if shared.wanted != wanted {
            if !wanted.ndi {
                shared.ndi_status = None;
            }
            shared.wanted = wanted;
        }
    }

    pub fn wanted(&self) -> Wanted {
        lock(&self.shared).wanted.clone()
    }

    /// L'état de la source NDI : `Ok(chemin de la bibliothèque)`, ou l'erreur ; `None` : arrêtée.
    pub fn ndi_status(&self) -> Option<Result<String, String>> {
        lock(&self.shared).ndi_status.clone()
    }

    pub fn ndi_receivers(&self) -> i32 {
        lock(&self.shared).ndi_receivers
    }

    /// Les images HDMI prêtes deviennent des textures (à appeler à chaque image de la régie).
    pub fn upload(&mut self, ctx: &egui::Context) {
        let ready: Vec<_> = lock(&self.shared).frames.drain().collect();
        for (kind, ((w, h), pixels)) in ready {
            if pixels.len() != (w * h * 4) as usize {
                continue;
            }
            let image = egui::ColorImage::from_rgba_premultiplied([w as usize, h as usize], &pixels);
            match self.textures.get_mut(&kind) {
                Some(texture) => texture.set(image, egui::TextureOptions::LINEAR),
                None => {
                    let texture =
                        ctx.load_texture(format!("sortie-{}", kind.slug()), image, egui::TextureOptions::LINEAR);
                    self.textures.insert(kind, texture);
                }
            }
        }
    }

    /// La texture d'une sortie HDMI de ce genre.
    pub fn texture(&self, kind: ScreenKind) -> Option<&egui::TextureHandle> {
        self.textures.get(&kind)
    }
}

impl Drop for Outputs {
    fn drop(&mut self) {
        lock(&self.shared).stop = true;
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

fn render_loop(hub: &Hub, shared: &Mutex<Shared>, wake: &dyn Fn()) {
    let mut program = hub.subscribe();
    let mut ndi: Option<po_ndi::Sender> = None;
    let mut done: Option<(Wanted, u64, Option<Instant>)> = None;
    let mut redraw: Option<Instant> = None;
    loop {
        std::thread::sleep(Duration::from_millis(15));
        let wanted = {
            let shared = lock(shared);
            if shared.stop {
                break;
            }
            shared.wanted.clone()
        };
        // La source NDI s'ouvre et se ferme avec le choix de l'opérateur.
        if wanted.ndi && ndi.is_none() {
            let status = po_ndi::Sender::start("Project-On Diffusion", &[])
                .map(|sender| {
                    ndi = Some(sender);
                    po_ndi::available(&[]).map(|p| p.display().to_string()).unwrap_or_default()
                })
                .map_err(|e| {
                    po_core::journal::line(&format!("NDI : {e}"));
                    e
                });
            lock(shared).ndi_status = Some(status);
            done = None;
        } else if !wanted.ndi && ndi.is_some() {
            ndi = None;
        }
        if let Some(sender) = &ndi {
            lock(shared).ndi_receivers = sender.connections();
        }
        let changed = program.has_changed().unwrap_or(false);
        let current = program.borrow_and_update().clone();
        let due = redraw.is_some_and(|at| Instant::now() >= at);
        let same = done.as_ref().is_some_and(|(w, seq, _)| *w == wanted && *seq == current.seq) && !changed && !due;
        if same || (!wanted.ndi && wanted.hdmi.is_empty()) {
            continue;
        }
        let mut next: Option<Duration> = None;
        if let Some(sender) = &ndi {
            let (pixels, again) = hub.render_rgba(&current, ScreenKind::Broadcast, 1920, 1080, None, false);
            if !pixels.is_empty() {
                sender.send(Arc::new(po_ndi::Image::from_premultiplied_rgba(1920, 1080, &pixels)));
            }
            next = again;
        }
        for (kind, (w, h)) in &wanted.hdmi {
            let key = if kind.transparent() { wanted.key.or(Some(Rgba::rgb(0, 255, 0))) } else { None };
            let (pixels, again) = hub.render_rgba(&current, *kind, *w, *h, key, wanted.pattern);
            next = match (next, again) {
                (Some(a), Some(b)) => Some(a.min(b)),
                (a, b) => a.or(b),
            };
            lock(shared).frames.insert(*kind, ((*w, *h), pixels));
        }
        if !wanted.hdmi.is_empty() {
            wake();
        }
        redraw = next.map(|d| Instant::now() + d);
        done = Some((wanted, current.seq, redraw));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hdmi_outputs_are_rendered_on_the_key_color() {
        let hub = Hub::new(po_layout::Fonts::from_files(&[
            po_layout::bundled_fonts_dir().join("Passion One/PassionOne-Bold.ttf")
        ]));
        hub.update(
            Some(po_layout::Slide::new("Car Dieu a tant aimé le monde", "Jean 3:16", po_design::SlideSource::Bible)),
            po_web::Context::default(),
        );
        let ctx = egui::Context::default();
        let mut outputs = Outputs::start(hub, || {});
        outputs.want(Wanted {
            hdmi: vec![(ScreenKind::Broadcast, (320, 180)), (ScreenKind::Stage, (320, 180))],
            key: Some(Rgba::rgb(255, 0, 255)),
            ..Wanted::default()
        });
        let start = Instant::now();
        while (outputs.texture(ScreenKind::Broadcast).is_none() || outputs.texture(ScreenKind::Stage).is_none())
            && start.elapsed() < Duration::from_secs(10)
        {
            std::thread::sleep(Duration::from_millis(20));
            outputs.upload(&ctx);
        }
        assert_eq!(outputs.texture(ScreenKind::Broadcast).unwrap().size(), [320, 180]);
        assert!(outputs.texture(ScreenKind::Stage).is_some());
        assert_eq!(outputs.ndi_status(), None, "NDI arrêtée tant qu'on ne la demande pas");
    }
}
