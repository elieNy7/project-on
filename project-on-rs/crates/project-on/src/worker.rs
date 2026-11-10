//! Le rendu des slides, sur un fil à part : la mise en page (2.8 au pixel près) et le dessin des
//! trois couches (fond, contenu, identification) prennent de 20 à 100 ms. L'interface ne les attend
//! jamais : elle reçoit les couches quand elles sont prêtes, les envoie à la carte graphique, et la
//! transition commence.
//!
//! Seul le dernier travail de chaque cible compte : si l'opérateur appuie trois fois sur « suivant »
//! pendant un rendu, seul le troisième slide est dessiné.

use std::path::PathBuf;
use std::sync::mpsc::{Receiver, Sender, channel};
use std::time::Instant;

use po_design::RoomDesign;
use po_layout::{DisplayList, Fonts, Slide, layout_room};
use po_render::{Layers, Renderer};
use tiny_skia::Pixmap;

/// Pour quel moniteur.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Target {
    Preview,
    Live,
}

/// Un slide à dessiner.
pub struct Job {
    pub target: Target,
    /// Numéro croissant : une réponse plus ancienne que le dernier envoi est ignorée.
    pub id: u64,
    pub slide: Slide,
    pub design: RoomDesign,
    pub width: u32,
    pub height: u32,
    /// Le rayon du flou de la transition (une copie floutée du contenu est préparée), en pixels de
    /// la mise en page.
    pub blur: Option<f32>,
}

/// Un slide dessiné.
#[derive(Clone)]
pub struct Done {
    pub target: Target,
    pub id: u64,
    pub list: DisplayList,
    pub layers: Layers,
    pub blurred: Option<Pixmap>,
    /// Durée du travail, en millisecondes.
    pub ms: f64,
}

/// Le fil de rendu.
pub struct Worker {
    jobs: Sender<Job>,
    done: Receiver<Done>,
}

/// Les polices de la projection, depuis un dossier.
pub fn fonts_from(dir: &std::path::Path) -> Fonts {
    Fonts::from_dirs(&[dir])
}

/// Dessine un slide (sur le fil appelant).
pub fn render(fonts: &mut Fonts, renderer: &mut Renderer, job: Job) -> Option<Done> {
    let started = Instant::now();
    let list = {
        let renderer = &mut *renderer;
        let mut probe = |list: &DisplayList, zone: [f32; 4]| renderer.backdrop_luminance(list, zone);
        layout_room(fonts, &job.slide, &job.design, job.width as f32, job.height as f32, &mut probe)
    };
    let layers = renderer.render_layers(fonts, &list, job.width, job.height).ok()?;
    let scale = job.width as f32 / list.width.max(1.0);
    let blurred = job.blur.map(|r| po_render::blurred(&layers.content, r * scale));
    Some(Done { target: job.target, id: job.id, list, layers, blurred, ms: started.elapsed().as_secs_f64() * 1000.0 })
}

impl Worker {
    /// Démarre le fil ; `wake` est appelé après chaque slide dessiné (pour repeindre l'interface).
    pub fn spawn(fonts_dir: PathBuf, wake: impl Fn() + Send + 'static) -> Self {
        let (jobs, inbox) = channel::<Job>();
        let (outbox, done) = channel::<Done>();
        let spawned = std::thread::Builder::new().name("rendu-des-slides".into()).spawn(move || {
            let mut fonts = fonts_from(&fonts_dir);
            let mut renderer = Renderer::new();
            while let Ok(first) = inbox.recv() {
                // Les travaux en attente : seul le dernier de chaque cible.
                let mut pending = vec![first];
                pending.extend(inbox.try_iter());
                let mut latest: Vec<Job> = Vec::new();
                for job in pending {
                    latest.retain(|j| j.target != job.target);
                    latest.push(job);
                }
                // Le direct d'abord : c'est ce que voit l'assemblée.
                latest.sort_by_key(|j| j.target != Target::Live);
                for job in latest {
                    if let Some(done) = render(&mut fonts, &mut renderer, job)
                        && outbox.send(done).is_err()
                    {
                        return;
                    }
                    wake();
                }
            }
        });
        if let Err(e) = spawned {
            po_core::journal::line(&format!("fil de rendu impossible : {e}"));
        }
        Worker { jobs, done }
    }

    pub fn submit(&self, job: Job) {
        let _ = self.jobs.send(job);
    }

    /// Les slides dessinés depuis le dernier appel.
    pub fn finished(&self) -> Vec<Done> {
        self.done.try_iter().collect()
    }
}
