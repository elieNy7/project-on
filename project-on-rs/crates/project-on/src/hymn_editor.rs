//! L'éditeur de cantique (`hymn_editor_dialog.py` de la 2.8) : titre, numéro, langue, et les
//! strophes saisies dans une seule zone de texte, séparées par une ligne vide, comme sur une
//! feuille de chants. Une strophe dont la première ligne est « Refrain » (ou « Chœur », « Chorus »,
//! « Dernier chœur ») est un refrain ; le bouton « Refrain » bascule la strophe du curseur. Le
//! découpage reconnu se voit en direct.

use std::sync::LazyLock;

use po_db::{Hymn, Stanza};
use regex::Regex;

/// Les langues proposées (celles de la 2.8).
pub const LANGUAGES: [(&str, &str); 6] = [
    ("Français", "fr"),
    ("Lingala", "ln"),
    ("Kiswahili", "sw"),
    ("Tshiluba", "lua"),
    ("Kikongo", "kg"),
    ("English", "en"),
];

/// `_CHORUS_RE` de la 2.8.
static CHORUS: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)^\s*(?:dernier\s+)?(?:ch(?:oe|œ)urs?|refrain|chorus)\b\s*[:.\-–—]?\s*").unwrap_or_else(|_| {
        // Motif fixe, vérifié par les essais : ne peut pas échouer.
        Regex::new("$^").unwrap_or_else(|_| unreachable!())
    })
});

static BLANK_LINES: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\n\s*\n+").unwrap_or_else(|_| Regex::new("$^").unwrap_or_else(|_| unreachable!())));

/// Texte saisi → [(strophe sans son libellé, est un refrain)] (`parse_stanzas`).
pub fn parse_stanzas(text: &str) -> Vec<(String, bool)> {
    let text = text.replace('\r', "");
    let mut out = Vec::new();
    for block in BLANK_LINES.split(text.trim()) {
        let mut lines: Vec<String> =
            block.trim().split('\n').map(|l| l.trim_end().to_string()).filter(|l| !l.trim().is_empty()).collect();
        if lines.is_empty() {
            continue;
        }
        let chorus = CHORUS.is_match(&lines[0]);
        if chorus {
            let rest = CHORUS.replace(&lines[0], "").trim().to_string();
            lines.remove(0);
            if !rest.is_empty() {
                lines.insert(0, rest);
            }
        }
        let body = lines.iter().map(|l| l.trim()).collect::<Vec<_>>().join("\n").trim().to_string();
        if !body.is_empty() {
            out.push((body, chorus));
        }
    }
    out
}

/// [(strophe, est un refrain)] → texte éditable, le refrain précédé de « Refrain » (`compose_text`).
pub fn compose_text(stanzas: &[(String, bool)]) -> String {
    stanzas
        .iter()
        .map(|(body, chorus)| if *chorus { format!("Refrain\n{body}") } else { body.clone() })
        .collect::<Vec<_>>()
        .join("\n\n")
}

/// Ajoute ou retire « Refrain » en tête de la strophe où se trouve le curseur (`cursor` : rang du
/// caractère). Rend le nouveau texte et la nouvelle place du curseur.
pub fn toggle_chorus_at(text: &str, cursor: usize) -> (String, usize) {
    let text = text.replace('\r', "");
    let chars: Vec<char> = text.chars().collect();
    let cursor = cursor.min(chars.len());
    let byte_at = |c: usize| chars[..c].iter().map(|ch| ch.len_utf8()).sum::<usize>();
    let before = &text[..byte_at(cursor)];
    // Début de la strophe : après la dernière ligne vide avant le curseur.
    let mut start = BLANK_LINES.find_iter(before).last().map_or(0, |m| m.end());
    while text[start..].starts_with('\n') {
        start += 1;
    }
    let line_end = text[start..].find('\n').map(|i| start + i);
    let first_line = &text[start..line_end.unwrap_or(text.len())];
    let chars_until = |byte: usize| text[..byte].chars().count();
    if CHORUS.is_match(first_line) && CHORUS.replace(first_line, "").trim().is_empty() {
        // Une ligne « Refrain » seule : on la retire, avec son retour à la ligne.
        let end = line_end.map_or(text.len(), |e| e + 1);
        let new_text = format!("{}{}", &text[..start], &text[end..]);
        let removed = chars_until(end) - chars_until(start);
        let position = cursor.saturating_sub(removed).max(chars_until(start));
        (new_text, position)
    } else if CHORUS.is_match(first_line) {
        let stripped = CHORUS.replace(first_line, "").to_string();
        let new_text = format!("{}{}{}", &text[..start], stripped, &text[start + first_line.len()..]);
        (new_text, chars_until(start))
    } else {
        let new_text = format!("{}Refrain\n{}", &text[..start], &text[start..]);
        (new_text, cursor + "Refrain\n".chars().count())
    }
}

/// Le découpage reconnu, pour l'aperçu : « Strophe 2 · 4 ligne(s) » et la première ligne.
pub fn preview(stanzas: &[(String, bool)]) -> Vec<(String, String)> {
    let (mut verse, mut chorus) = (0, 0);
    stanzas
        .iter()
        .map(|(body, is_chorus)| {
            let label = if *is_chorus {
                chorus += 1;
                if chorus == 1 { "Refrain".to_string() } else { format!("Refrain {chorus}") }
            } else {
                verse += 1;
                format!("Strophe {verse}")
            };
            let lines = body.matches('\n').count() + 1;
            (format!("{label} · {lines} ligne(s)"), body.split('\n').next().unwrap_or("").to_string())
        })
        .collect()
}

/// Un cantique en cours d'édition.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Draft {
    /// `None` : un nouveau cantique.
    pub id: Option<i64>,
    pub title: String,
    pub number: String,
    pub language: String,
    pub text: String,
}

impl Default for Draft {
    fn default() -> Self {
        Draft { id: None, title: String::new(), number: String::new(), language: "fr".into(), text: String::new() }
    }
}

impl Draft {
    /// Un cantique existant, comme la 2.8 l'ouvre : le titre d'origine, le refrain sans son
    /// libellé de projection.
    pub fn of(hymn: &Hymn, stanzas: &[Stanza]) -> Self {
        let pieces: Vec<(String, bool)> = stanzas
            .iter()
            .map(|s| {
                let text = if s.is_chorus { po_text::strip_hymn_projection_label(&s.text) } else { s.text.clone() };
                (text, s.is_chorus)
            })
            .collect();
        Draft {
            id: Some(hymn.id),
            title: if hymn.original_title.is_empty() { hymn.title.clone() } else { hymn.original_title.clone() },
            number: hymn.number.clone().unwrap_or_default(),
            language: hymn.language.clone().filter(|l| !l.is_empty()).unwrap_or_else(|| "fr".into()),
            text: compose_text(&pieces),
        }
    }

    /// Les strophes à enregistrer, ou ce qui manque (`_on_accept`).
    pub fn check(&self) -> Result<Vec<(String, bool)>, &'static str> {
        if self.title.trim().is_empty() {
            return Err("Donnez un titre au cantique.");
        }
        let stanzas = parse_stanzas(&self.text);
        if stanzas.is_empty() {
            return Err("Saisissez au moins une strophe.");
        }
        Ok(stanzas)
    }

    pub fn number(&self) -> Option<&str> {
        Some(self.number.trim()).filter(|n| !n.is_empty())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn s(body: &str, chorus: bool) -> (String, bool) {
        (body.to_string(), chorus)
    }

    /// Les valeurs rendues par les fonctions de la 2.8 (`hymn_editor_dialog.py`), sur les mêmes textes.
    #[test]
    fn stanzas_are_recognised_like_the_2_8() {
        assert_eq!(
            parse_stanzas("À toi la gloire\nÔ Ressuscité\n\nRefrain\nÀ toi la victoire\n\nVois-le paraître"),
            [s("À toi la gloire\nÔ Ressuscité", false), s("À toi la victoire", true), s("Vois-le paraître", false)]
        );
        assert_eq!(
            parse_stanzas("  Strophe une  \n\n\n\nChœur : Gloire à Dieu\nAlléluia\n\nDernier chœur\nAmen\n\n"),
            [s("Strophe une", false), s("Gloire à Dieu\nAlléluia", true), s("Amen", true)]
        );
        assert_eq!(
            parse_stanzas("chorus - He lives\n\nREFRAIN.\n\nrefrain\nTexte"),
            [s("He lives", true), s("Texte", true)]
        );
        assert_eq!(
            parse_stanzas("Une seule strophe\r\nsur deux lignes"),
            [s("Une seule strophe\nsur deux lignes", false)]
        );
        assert!(parse_stanzas("").is_empty());
        assert!(parse_stanzas("Refrain").is_empty());
        assert_eq!(
            compose_text(&[s("Ligne 1\nLigne 2", false), s("Gloire", true), s("Fin", false)]),
            "Ligne 1\nLigne 2\n\nRefrain\nGloire\n\nFin"
        );
    }

    #[test]
    fn the_chorus_button_toggles_the_stanza_under_the_cursor() {
        let text = "Strophe un\n\nGloire à Dieu\nAlléluia\n\nFin";
        // Le curseur dans « Alléluia » : la deuxième strophe devient le refrain.
        let cursor = text.find("Alléluia").map(|b| text[..b].chars().count()).unwrap();
        let (with, at) = toggle_chorus_at(text, cursor);
        assert_eq!(with, "Strophe un\n\nRefrain\nGloire à Dieu\nAlléluia\n\nFin");
        assert_eq!(at, cursor + 8);
        assert_eq!(parse_stanzas(&with)[1], s("Gloire à Dieu\nAlléluia", true));
        // De nouveau : la ligne « Refrain » part.
        let (back, _) = toggle_chorus_at(&with, at);
        assert_eq!(back, text);
        // « Chœur : Gloire » sur une ligne : seul le libellé part.
        let (plain, _) = toggle_chorus_at("Chœur : Gloire\nAmen", 3);
        assert_eq!(plain, "Gloire\nAmen");
        // Au tout début.
        assert_eq!(toggle_chorus_at("Un", 0).0, "Refrain\nUn");
    }

    #[test]
    fn a_draft_checks_its_title_and_stanzas() {
        let mut draft = Draft { text: "Refrain\nGloire".into(), ..Draft::default() };
        assert_eq!(draft.check(), Err("Donnez un titre au cantique."));
        draft.title = "À toi la gloire".into();
        assert_eq!(draft.check(), Ok(vec![s("Gloire", true)]));
        draft.text = "Refrain".into();
        assert_eq!(draft.check(), Err("Saisissez au moins une strophe."));
        assert_eq!(Draft { number: "  ".into(), ..Draft::default() }.number(), None);
        assert_eq!(
            preview(&[s("a\nb", false), s("c", true), s("d", true)]),
            [
                ("Strophe 1 · 2 ligne(s)".into(), "a".into()),
                ("Refrain · 1 ligne(s)".into(), "c".into()),
                ("Refrain 2 · 1 ligne(s)".into(), "d".into())
            ]
        );
    }
}
