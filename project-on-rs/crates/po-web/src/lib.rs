//! La projection Web de Project-On : un serveur local qui envoie à chaque écran (navigateur, OBS,
//! téléviseur, tablette du chantre…) ce qu'il doit afficher.
//!
//! - **Plusieurs écrans** : la salle (le slide plein écran), la diffusion (le bandeau sur fond
//!   transparent pour OBS, vMix ou Pgraphics ; l'adresse `/obs` de la 2.8 y mène), les sous-titres
//!   et le retour de scène (slide au direct, suivant, heure, déroulé).
//! - **Lecture seule** : un écran reçoit des images, il ne peut rien piloter (comme le serveur local
//!   de Pgraphics, ADR-0002). Les seuls messages acceptés d'un client sont sa taille, un accusé de
//!   réception et la réponse au ping.
//! - **Une mise en page par écran** : chaque client annonce sa taille, et le serveur calcule la
//!   liste d'affichage pour elle (`po-layout`). Le navigateur ne fait que dessiner, avec les mêmes
//!   transitions que le vidéoprojecteur.
//! - **Fiable** : à la (re)connexion, le client reçoit aussitôt l'état courant ; pendant une coupure
//!   il garde sa dernière image et se reconnecte seul. La régie voit chaque écran : connecté, en
//!   retard, déconnecté.
//! - **Sûr** : ce poste seulement par défaut ; sur le réseau local, un jeton (QR code de la régie).

mod access;
mod protocol;
mod screens;
mod server;

pub use access::{Access, new_token, qr, qr_svg};
pub use protocol::{ClientMessage, PROTOCOL_VERSION, ServerMessage};
pub use screens::{DROPPED_FOR, PRESETS, ScreenInfo, ScreenKind, ScreenState};
pub use server::{Adjust, Context, Hub, Look, Overlay, OverlayFrame, Program, Server, start, start_near};

/// L'adresse de ce poste sur le réseau local (celle que les autres appareils utilisent), si le
/// poste est relié à un réseau. Aucun paquet n'est envoyé : la table de routage choisit l'interface.
pub fn lan_ip() -> Option<std::net::IpAddr> {
    let socket = std::net::UdpSocket::bind("0.0.0.0:0").ok()?;
    socket.connect("192.0.2.1:9").ok()?;
    let ip = socket.local_addr().ok()?.ip();
    (!ip.is_loopback() && !ip.is_unspecified()).then_some(ip)
}
