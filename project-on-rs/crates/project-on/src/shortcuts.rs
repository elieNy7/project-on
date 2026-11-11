//! Les raccourcis clavier, ceux de la 2.8 (`app/utils/shortcuts.py`) : chaque action de la régie a
//! un raccourci par défaut, que l'opérateur a pu changer (`settings.json`, section `shortcuts`). Une
//! télécommande de présentation (Page suivante / précédente, B, F5) ou un Stream Deck pilote ainsi
//! Project-On sans logiciel de plus.
//!
//! Les touches fixes (flèches, Début, Fin, Échap, Ctrl+1 à Ctrl+5) suivent les conventions de
//! Windows et de PowerPoint et ne se changent pas.

use egui::{Key, KeyboardShortcut, Modifiers};
use serde_json::{Map, Value};

/// Une action de la régie.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Action {
    Take,
    NextSlide,
    PrevSlide,
    Hide,
    Projection,
    GlobalSearch,
    Search,
    ParagraphSearch,
    Help,
    LowerThird,
    Subtitles,
    HdmiPattern,
    NextSection,
    Preflight,
    History,
}

/// (action, identifiant de la 2.8, libellé, touche par défaut).
pub const ACTIONS: [(Action, &str, &str, &str); 15] = [
    (Action::Take, "take", "Envoyer l'aperçu au direct", "F2"),
    (Action::NextSlide, "next_slide", "Slide suivant (télécommande)", "PgDown"),
    (Action::PrevSlide, "prev_slide", "Slide précédent (télécommande)", "PgUp"),
    (Action::Hide, "hide", "Masquer / afficher le texte", "B"),
    (Action::Projection, "projection", "Ouvrir / fermer la projection", "F5"),
    (Action::GlobalSearch, "global_search", "Recherche globale", "Ctrl+K"),
    (Action::Search, "search", "Rechercher dans la bibliothèque", "Ctrl+F"),
    (Action::ParagraphSearch, "paragraph_search", "Rechercher un paragraphe", "Ctrl+G"),
    (Action::Help, "help", "Aide des raccourcis", "F1"),
    (Action::LowerThird, "lower_third", "Afficher / masquer le lower third", "L"),
    (Action::Subtitles, "subtitles", "Afficher / masquer les sous-titres", "S"),
    (Action::HdmiPattern, "hdmi_mire", "Mire de la sortie HDMI", "F8"),
    (Action::NextSection, "next_section", "Déroulé : section suivante", "Ctrl+Alt+N"),
    (Action::Preflight, "preflight", "Contrôle avant culte", "Ctrl+Shift+D"),
    (Action::History, "history", "Historique du culte", "Ctrl+H"),
];

/// Les actions de la 2.8 qui arrivent dans une phase suivante (montrées dans l'aide).
pub const LATER: [(&str, &str); 5] = [
    ("Écran d'accueil (Ctrl+Shift+W)", "phase 7"),
    ("Écran de l'orateur du jour (Ctrl+Shift+P)", "phase 7"),
    ("Écran « Réseaux sociaux » (Ctrl+Shift+R)", "phase 7"),
    ("Image de citation du direct (Ctrl+Shift+I)", "phase 7"),
    ("Miniature YouTube (Ctrl+Shift+Y)", "retirée (couche 1)"),
];

/// La touche nommée comme dans la 2.8 (`QKeySequence` : « F2 », « PgDown », « B », « Space »…).
fn key(name: &str) -> Option<Key> {
    let lower = name.to_ascii_lowercase();
    Some(match lower.as_str() {
        "pgdown" | "pagedown" => Key::PageDown,
        "pgup" | "pageup" => Key::PageUp,
        "space" => Key::Space,
        "return" | "enter" => Key::Enter,
        "tab" => Key::Tab,
        "backspace" => Key::Backspace,
        "del" | "delete" => Key::Delete,
        "ins" | "insert" => Key::Insert,
        "home" => Key::Home,
        "end" => Key::End,
        "left" => Key::ArrowLeft,
        "right" => Key::ArrowRight,
        "up" => Key::ArrowUp,
        "down" => Key::ArrowDown,
        "esc" | "escape" => Key::Escape,
        "." | "period" => Key::Period,
        "," | "comma" => Key::Comma,
        _ => return Key::from_name(name).or_else(|| Key::from_name(&name.to_ascii_uppercase())),
    })
}

/// « Ctrl+Shift+D » → raccourci egui. `None` si la touche est inconnue ou vide (désactivée).
pub fn parse(text: &str) -> Option<KeyboardShortcut> {
    let text = text.trim();
    if text.is_empty() {
        return None;
    }
    let mut modifiers = Modifiers::NONE;
    let parts: Vec<&str> = text.split('+').map(str::trim).collect();
    let (last, mods) = parts.split_last()?;
    for m in mods {
        match m.to_ascii_lowercase().as_str() {
            "ctrl" | "control" => modifiers |= Modifiers::COMMAND,
            "shift" => modifiers |= Modifiers::SHIFT,
            "alt" => modifiers |= Modifiers::ALT,
            "meta" => modifiers |= Modifiers::MAC_CMD,
            _ => return None,
        }
    }
    Some(KeyboardShortcut::new(modifiers, key(last)?))
}

/// Les raccourcis effectifs : ceux de l'opérateur, sinon ceux par défaut.
#[derive(Debug, Clone)]
pub struct Shortcuts {
    pub keys: Vec<(Action, String, Option<KeyboardShortcut>)>,
}

impl Shortcuts {
    /// Depuis la section `shortcuts` de `settings.json` (`{"keys": {"take": "F3"}}`).
    pub fn from_settings(section: Option<&Value>) -> Self {
        let custom: Map<String, Value> =
            section.and_then(|s| s.get("keys")).and_then(Value::as_object).cloned().unwrap_or_default();
        let keys = ACTIONS
            .iter()
            .map(|(action, id, _, default)| {
                let text = match custom.get(*id) {
                    Some(Value::String(s)) => s.trim().to_string(),
                    Some(Value::Null) => String::new(),
                    _ => (*default).to_string(),
                };
                let shortcut = parse(&text);
                (*action, text, shortcut)
            })
            .collect();
        Shortcuts { keys }
    }

    pub fn text(&self, action: Action) -> &str {
        self.keys.iter().find(|(a, _, _)| *a == action).map_or("", |(_, t, _)| t.as_str())
    }

    /// Les actions demandées au clavier pendant cette image. Une touche sans modificateur (B, Page
    /// suivante) ne compte pas pendant une saisie : taper « Bible » ne masque pas le texte.
    pub fn pressed(&self, ctx: &egui::Context) -> Vec<Action> {
        let typing = ctx.egui_wants_keyboard_input();
        let mut out = Vec::new();
        for (action, _, shortcut) in &self.keys {
            let Some(shortcut) = shortcut else { continue };
            let plain = shortcut.modifiers.is_none() && !is_function_key(shortcut.logical_key);
            if typing && plain {
                continue;
            }
            if ctx.input_mut(|i| i.consume_shortcut(shortcut)) {
                out.push(*action);
            }
        }
        out
    }
}

fn is_function_key(key: Key) -> bool {
    matches!(
        key,
        Key::F1
            | Key::F2
            | Key::F3
            | Key::F4
            | Key::F5
            | Key::F6
            | Key::F7
            | Key::F8
            | Key::F9
            | Key::F10
            | Key::F11
            | Key::F12
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn keys_written_by_the_2x() {
        assert_eq!(parse("F2"), Some(KeyboardShortcut::new(Modifiers::NONE, Key::F2)));
        assert_eq!(parse("PgDown"), Some(KeyboardShortcut::new(Modifiers::NONE, Key::PageDown)));
        assert_eq!(parse("Ctrl+K"), Some(KeyboardShortcut::new(Modifiers::COMMAND, Key::K)));
        assert_eq!(parse("Ctrl+Shift+D"), Some(KeyboardShortcut::new(Modifiers::COMMAND | Modifiers::SHIFT, Key::D)));
        assert_eq!(parse("b"), Some(KeyboardShortcut::new(Modifiers::NONE, Key::B)));
        assert_eq!(parse(""), None);
        assert_eq!(parse("Hyper+Q"), None);
    }

    #[test]
    fn the_operator_keys_win() {
        let s = Shortcuts::from_settings(Some(&json!({"keys": {"take": "F3", "hide": ""}})));
        assert_eq!(s.text(Action::Take), "F3");
        assert_eq!(s.text(Action::Hide), "", "désactivé");
        assert_eq!(s.text(Action::Projection), "F5", "par défaut");
        let defaults = Shortcuts::from_settings(None);
        assert_eq!(defaults.text(Action::GlobalSearch), "Ctrl+K");
    }
}
