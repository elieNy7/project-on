//! La projection Web de Project-On : un serveur local qui envoie à chaque écran (navigateur, OBS,
//! téléviseur…) ce qu'il doit afficher.
//!
//! - **Lecture seule** : un écran reçoit des images, il ne peut rien piloter (comme le serveur local
//!   de Pgraphics, ADR-0002). Les seuls messages acceptés d'un client sont sa taille, un accusé de
//!   réception et la réponse au ping.
//! - **Une mise en page par écran** : chaque client annonce sa taille, et le serveur calcule la
//!   liste d'affichage pour elle (`po-layout`). Le navigateur ne fait que dessiner.
//! - **Fiable** : à la (re)connexion, le client reçoit aussitôt l'état courant ; pendant une coupure
//!   il garde sa dernière image.

mod protocol;
mod server;

pub use protocol::{ClientMessage, PROTOCOL_VERSION, ServerMessage};
pub use server::{Hub, Program, Server, start};
