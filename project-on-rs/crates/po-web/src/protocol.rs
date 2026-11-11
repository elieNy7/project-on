//! Le protocole entre Project-On et un écran Web : des messages JSON sur un WebSocket.

use po_design::Animation;
use po_layout::DisplayList;
use serde::{Deserialize, Serialize};

/// La version du protocole, annoncée dans `hello`. Un écran ouvert avec un client d'une autre
/// version se recharge de lui-même (après une mise à jour de Project-On).
pub const PROTOCOL_VERSION: u32 = 2;

/// Ce que le serveur envoie.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ServerMessage {
    /// À la connexion : la version, le nom de l'écran et son genre (`salle`, `diffusion`,
    /// `sous-titres`, `retour`). `transparent` : l'écran se pose sur une vidéo (OBS, vMix).
    Hello { version: u32, screen: String, kind: String, transparent: bool },
    /// Ce que l'écran doit afficher. `seq` augmente à chaque slide mis au direct : un `seq` nouveau
    /// s'anime avec `animation`, un `seq` inchangé (l'heure, le texte masqué, une autre taille)
    /// remplace l'image sans transition. `hidden` : le texte est masqué, le fond reste.
    Frame {
        seq: u64,
        list: DisplayList,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        animation: Option<Animation>,
        #[serde(default)]
        hidden: bool,
    },
    /// Toutes les 5 s : un écran qui ne répond plus est compté comme déconnecté.
    Ping,
}

/// Ce qu'un écran peut envoyer : rien qui pilote Project-On.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ClientMessage {
    /// La taille de l'écran, en pixels CSS (à la connexion et à chaque redimensionnement).
    Hello {
        width: f32,
        height: f32,
    },
    /// L'image `seq` est affichée.
    Ack {
        seq: u64,
    },
    Pong,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn messages_are_tagged_json() {
        let hello = serde_json::to_string(&ServerMessage::Hello {
            version: 2,
            screen: "salle".into(),
            kind: "salle".into(),
            transparent: false,
        })
        .unwrap();
        assert_eq!(hello, r#"{"type":"hello","version":2,"screen":"salle","kind":"salle","transparent":false}"#);
        let parsed: ClientMessage = serde_json::from_str(r#"{"type":"hello","width":1920,"height":1080}"#).unwrap();
        assert_eq!(parsed, ClientMessage::Hello { width: 1920.0, height: 1080.0 });
        // Un message inconnu (une tentative de commande) est refusé.
        assert!(serde_json::from_str::<ClientMessage>(r#"{"type":"take"}"#).is_err());
    }
}
