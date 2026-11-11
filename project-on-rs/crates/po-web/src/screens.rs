//! Les écrans Web : leur genre (salle, diffusion, sous-titres, retour de scène) et le registre de
//! ceux qui sont connectés, que la régie affiche.

use std::net::SocketAddr;
use std::sync::Mutex;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant};

/// Ce qu'un écran montre. Le genre se déduit du nom de l'écran (`/ecran/diffusion`) : n'importe
/// quel autre nom (`/ecran/hall`) est un écran de salle de plus.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ScreenKind {
    /// Le slide plein écran, comme le vidéoprojecteur.
    Room,
    /// Le bandeau sur fond transparent, pour OBS, vMix ou Pgraphics (la page `/obs` de la 2.8).
    Broadcast,
    /// Les sous-titres : le texte seul, en bas, sur fond transparent.
    Subtitles,
    /// Le retour de scène : le slide au direct, le suivant, l'heure et le déroulé.
    Stage,
}

/// Les écrans proposés : nom dans l'adresse, genre, titre, usage.
pub const PRESETS: [(&str, ScreenKind, &str, &str); 4] = [
    (
        "salle",
        ScreenKind::Room,
        "Salle",
        "Le slide en plein écran, comme le vidéoprojecteur : téléviseurs, salle annexe.",
    ),
    (
        "diffusion",
        ScreenKind::Broadcast,
        "Diffusion",
        "Le bandeau sur fond transparent, à poser sur la vidéo (OBS, vMix, Pgraphics). L'ancienne adresse /obs y mène.",
    ),
    ("sous-titres", ScreenKind::Subtitles, "Sous-titres", "Le texte seul, en bas, sur fond transparent."),
    (
        "retour",
        ScreenKind::Stage,
        "Retour scène",
        "Pour les chanteurs et le prédicateur : le slide au direct, le suivant, l'heure, le déroulé.",
    ),
];

impl ScreenKind {
    /// Le genre d'un écran d'après son nom.
    pub fn of(name: &str) -> ScreenKind {
        let name = name.trim().to_lowercase();
        match name.as_str() {
            "diffusion" | "obs" | "bandeau" | "live" | "stream" | "lower-third" | "broadcast" => ScreenKind::Broadcast,
            "sous-titres" | "soustitres" | "subtitles" | "subtitle" | "st" => ScreenKind::Subtitles,
            "retour" | "scene" | "scène" | "stage" | "retour-scene" | "confidence" => ScreenKind::Stage,
            _ => ScreenKind::Room,
        }
    }

    /// Le nom court (celui des adresses et du protocole).
    pub fn slug(self) -> &'static str {
        match self {
            ScreenKind::Room => "salle",
            ScreenKind::Broadcast => "diffusion",
            ScreenKind::Subtitles => "sous-titres",
            ScreenKind::Stage => "retour",
        }
    }

    pub fn label(self) -> &'static str {
        match self {
            ScreenKind::Room => "Salle",
            ScreenKind::Broadcast => "Diffusion",
            ScreenKind::Subtitles => "Sous-titres",
            ScreenKind::Stage => "Retour scène",
        }
    }

    /// Un écran à poser sur une vidéo : fond transparent.
    pub fn transparent(self) -> bool {
        matches!(self, ScreenKind::Broadcast | ScreenKind::Subtitles)
    }
}

/// L'état d'un écran, pour la régie.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ScreenState {
    /// Connecté, à jour.
    Ok,
    /// Connecté, mais le dernier slide n'est pas affiché depuis plus de 3 s, ou il ne répond plus
    /// au ping.
    Late,
    /// Déconnecté il y a moins d'une minute.
    Dropped,
}

/// Un écran connu de la régie.
#[derive(Debug, Clone)]
pub struct ScreenInfo {
    pub id: u64,
    pub name: String,
    pub kind: ScreenKind,
    pub width: f32,
    pub height: f32,
    pub addr: SocketAddr,
    pub since: Instant,
    pub last_seen: Instant,
    /// Le dernier slide affiché (accusé de réception).
    pub acked: u64,
    pub dropped: Option<Instant>,
    pub state: ScreenState,
}

impl ScreenInfo {
    /// Sur ce poste (OBS, un navigateur de la régie) plutôt qu'un appareil du réseau.
    pub fn local(&self) -> bool {
        self.addr.ip().is_loopback()
    }
}

/// Combien de temps un écran déconnecté reste affiché (en orange) dans la régie.
pub const DROPPED_FOR: Duration = Duration::from_secs(60);
/// Un slide non affiché au bout de ce délai : l'écran est en retard.
const LATE_AFTER: Duration = Duration::from_secs(3);
/// Plus de nouvelles depuis ce délai (deux pings sans réponse) : l'écran est en retard.
const SILENT_AFTER: Duration = Duration::from_secs(12);

#[derive(Debug)]
struct Entry {
    info: ScreenInfo,
}

/// Le registre des écrans.
#[derive(Debug, Default)]
pub(crate) struct Registry {
    next: AtomicU64,
    entries: Mutex<Vec<Entry>>,
}

impl Registry {
    fn lock(&self) -> std::sync::MutexGuard<'_, Vec<Entry>> {
        self.entries.lock().unwrap_or_else(|e| e.into_inner())
    }

    pub(crate) fn join(&self, id: u64, name: &str, addr: SocketAddr) {
        let now = Instant::now();
        let mut entries = self.lock();
        // Un écran qui revient remplace sa trace orange.
        entries.retain(|e| !(e.info.dropped.is_some() && e.info.name == name && e.info.addr.ip() == addr.ip()));
        entries.push(Entry {
            info: ScreenInfo {
                id,
                name: name.to_string(),
                kind: ScreenKind::of(name),
                width: 0.0,
                height: 0.0,
                addr,
                since: now,
                last_seen: now,
                acked: 0,
                dropped: None,
                state: ScreenState::Ok,
            },
        });
    }

    pub(crate) fn next_id(&self) -> u64 {
        self.next.fetch_add(1, Ordering::Relaxed) + 1
    }

    pub(crate) fn touch(&self, id: u64, update: impl FnOnce(&mut ScreenInfo)) {
        if let Some(e) = self.lock().iter_mut().find(|e| e.info.id == id) {
            e.info.last_seen = Instant::now();
            update(&mut e.info);
        }
    }

    pub(crate) fn leave(&self, id: u64) {
        if let Some(e) = self.lock().iter_mut().find(|e| e.info.id == id) {
            e.info.dropped = Some(Instant::now());
        }
    }

    /// Les écrans connectés et ceux déconnectés depuis moins d'une minute. `seq` et `published` :
    /// le dernier slide mis au direct et quand.
    pub(crate) fn list(&self, seq: u64, published: Instant) -> Vec<ScreenInfo> {
        let now = Instant::now();
        let mut entries = self.lock();
        entries.retain(|e| e.info.dropped.is_none_or(|t| now.duration_since(t) < DROPPED_FOR));
        entries
            .iter()
            .map(|e| {
                let mut info = e.info.clone();
                info.state = if info.dropped.is_some() {
                    ScreenState::Dropped
                } else if now.duration_since(info.last_seen) > SILENT_AFTER
                    || (info.acked < seq && now.duration_since(published) > LATE_AFTER)
                {
                    ScreenState::Late
                } else {
                    ScreenState::Ok
                };
                info
            })
            .collect()
    }

    pub(crate) fn connected(&self) -> usize {
        self.lock().iter().filter(|e| e.info.dropped.is_none()).count()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_kind_of_a_screen_comes_from_its_name() {
        assert_eq!(ScreenKind::of("Diffusion"), ScreenKind::Broadcast);
        assert_eq!(ScreenKind::of("obs"), ScreenKind::Broadcast);
        assert_eq!(ScreenKind::of("sous-titres"), ScreenKind::Subtitles);
        assert_eq!(ScreenKind::of("retour"), ScreenKind::Stage);
        assert_eq!(ScreenKind::of("hall"), ScreenKind::Room);
        for (name, kind, _, _) in PRESETS {
            assert_eq!(ScreenKind::of(name), kind);
            assert_eq!(kind.slug(), name);
        }
        assert!(ScreenKind::Broadcast.transparent() && !ScreenKind::Stage.transparent());
    }

    #[test]
    fn a_screen_that_does_not_show_the_slide_is_late_then_dropped() {
        let registry = Registry::default();
        let addr: SocketAddr = "192.168.1.20:5000".parse().unwrap();
        let id = registry.next_id();
        registry.join(id, "salle", addr);
        let published = Instant::now();
        assert_eq!(registry.list(0, published)[0].state, ScreenState::Ok);
        // Un slide au direct depuis 4 s, pas encore affiché : en retard.
        let long_ago = Instant::now() - Duration::from_secs(4);
        assert_eq!(registry.list(1, long_ago)[0].state, ScreenState::Late);
        registry.touch(id, |s| s.acked = 1);
        assert_eq!(registry.list(1, long_ago)[0].state, ScreenState::Ok);
        registry.leave(id);
        assert_eq!(registry.list(1, long_ago)[0].state, ScreenState::Dropped);
        assert_eq!(registry.connected(), 0);
        // Il revient : une seule ligne, connectée.
        let again = registry.next_id();
        registry.join(again, "salle", addr);
        let list = registry.list(1, long_ago);
        assert_eq!(list.len(), 1);
        assert_eq!(list[0].dropped, None);
    }
}
