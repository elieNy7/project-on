//! Le protocole entre Project-On et un écran Web : des messages JSON sur un WebSocket.

use po_layout::DisplayList;
use serde::{Deserialize, Serialize};

/// La version du protocole, annoncée dans `hello`.
pub const PROTOCOL_VERSION: u32 = 1;

/// Ce que le serveur envoie.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ServerMessage {
    /// À la connexion.
    Hello { version: u32, screen: String },
    /// Ce que l'écran doit afficher. `seq` augmente à chaque changement du direct.
    Frame { seq: u64, list: DisplayList },
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
        let hello = serde_json::to_string(&ServerMessage::Hello { version: 1, screen: "salle".into() }).unwrap();
        assert_eq!(hello, r#"{"type":"hello","version":1,"screen":"salle"}"#);
        let parsed: ClientMessage = serde_json::from_str(r#"{"type":"hello","width":1920,"height":1080}"#).unwrap();
        assert_eq!(parsed, ClientMessage::Hello { width: 1920.0, height: 1080.0 });
        // Un message inconnu (une tentative de commande) est refusé.
        assert!(serde_json::from_str::<ClientMessage>(r#"{"type":"take"}"#).is_err());
    }
}
