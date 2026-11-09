//! Le texte de Project-On : pliage sans accents, clés et requêtes de recherche, découpage en mots.
//!
//! Chaque fonction rend le même résultat que sa version Python de la 2.8
//! (`app.utils.text_utils`, `app.database.connection`, `app.database.dao_sermons`,
//! `app.ui.slide_canvas`), qu'elle remplacera.

use std::sync::OnceLock;

use unicode_general_category::{GeneralCategory, get_general_category};
use unicode_normalization::UnicodeNormalization;

fn is_kept(c: char) -> bool {
    get_general_category(c) != GeneralCategory::NonspacingMark
}

/// `unaccent()` : NFKD, retrait des marques non espaçantes (Mn), puis minuscules.
///
/// Même ordre qu'en Python : `lower()` vient après le filtre, donc les marques qu'il produit
/// lui-même sont conservées. Repris tel quel de `rust/project_on_core`.
pub fn fold(text: &str) -> String {
    if text.is_ascii() {
        return text.to_ascii_lowercase();
    }
    // Le sigma final (Σ → ς) dépend des lettres voisines : passage complet.
    if text.contains('Σ') {
        return fold_slow(text);
    }
    // Passage rapide : un caractère ASCII est stable en NFKD et la réorganisation canonique ne
    // franchit jamais un caractère de base, donc chaque suite non ASCII peut être normalisée à part.
    let bytes = text.as_bytes();
    let mut out = String::with_capacity(text.len());
    let mut i = 0;
    while i < bytes.len() {
        let start = i;
        if bytes[i].is_ascii() {
            while i < bytes.len() && bytes[i].is_ascii() {
                i += 1;
            }
            // Les octets ASCII sont des frontières de caractère.
            let run = &text[start..i];
            out.push_str(run);
            let len = out.len();
            out[len - run.len()..].make_ascii_lowercase();
        } else {
            while i < bytes.len() && !bytes[i].is_ascii() {
                i += 1;
            }
            let run = &text[start..i];
            if run.chars().all(|c| (c as u32) < LATIN_END) {
                // Aucune marque combinante avant U+0300 : rien à réordonner, chaque lettre se plie
                // seule.
                let table = latin_table();
                for c in run.chars() {
                    out.push_str(&table[c as usize]);
                }
            } else {
                for c in run.nfkd().filter(|&c| is_kept(c)) {
                    out.extend(c.to_lowercase());
                }
            }
        }
    }
    out
}

/// Fin du latin étendu ; les marques combinantes commencent en U+0300.
const LATIN_END: u32 = 0x300;

/// Pliage précalculé des lettres latines (é → e, Œ → œ, ß → ß…), qui sont l'essentiel des
/// caractères non ASCII des textes français.
fn latin_table() -> &'static [Box<str>] {
    static TABLE: OnceLock<Vec<Box<str>>> = OnceLock::new();
    TABLE.get_or_init(|| {
        (0..LATIN_END)
            .map(|cp| match char::from_u32(cp) {
                Some(c) => fold_slow(c.encode_utf8(&mut [0; 4])).into_boxed_str(),
                None => Box::from(""),
            })
            .collect()
    })
}

fn fold_slow(text: &str) -> String {
    let stripped: String = text.nfkd().filter(|&c| is_kept(c)).collect();
    stripped.to_lowercase()
}

/// Les guillemets français et anglais deviennent `"` dans les requêtes.
fn straight_quotes(value: &str) -> String {
    value.chars().map(|c| if matches!(c, '«' | '»' | '“' | '”' | '„') { '"' } else { c }).collect()
}

/// Nettoyage léger d'une saisie (espaces insécables, caractères invisibles), comme `clean_text`
/// pour ce qu'une requête peut contenir.
fn clean_query(value: &str) -> String {
    value
        .chars()
        .filter(|c| !matches!(c, '\u{feff}' | '\u{200b}' | '\u{fffd}' | '\r'))
        .map(|c| if matches!(c, '\u{a0}' | '\u{202f}' | '\t') { ' ' } else { c })
        .collect()
}

/// Clé de recherche (`Database._search_key`) : minuscules, sans accents, tout ce qui n'est ni
/// lettre ASCII ni chiffre devient une espace, espaces regroupées.
pub fn search_key(value: &str) -> String {
    let lowered = clean_query(value).to_lowercase();
    let mut out = String::with_capacity(lowered.len());
    let mut pending_space = false;
    for c in lowered.nfd().filter(|&c| is_kept(c)) {
        if c.is_ascii_lowercase() || c.is_ascii_digit() {
            if pending_space && !out.is_empty() {
                out.push(' ');
            }
            pending_space = false;
            out.push(c);
        } else {
            pending_space = true;
        }
    }
    out
}

/// Requête FTS5 (`SermonDAO._fts_query`) : mots en préfixe, « expression exacte » entre
/// guillemets. `foi "ferme assurance"` → `foi* "ferme assurance"`.
pub fn fts_query(value: &str) -> String {
    let text = straight_quotes(value);
    let mut parts: Vec<String> = Vec::new();
    let mut rest = text.as_str();
    loop {
        rest = rest.trim_start();
        if rest.is_empty() {
            break;
        }
        if let Some(after) = rest.strip_prefix('"')
            && let Some(end) = after.find('"')
        {
            let key = search_key(&after[..end]);
            if !key.is_empty() {
                parts.push(format!("\"{key}\""));
            }
            rest = &after[end + 1..];
            continue;
        }
        // Un mot : jusqu'à la prochaine espace (un guillemet seul en fait partie, comme en Python).
        let end = rest.find(char::is_whitespace).unwrap_or(rest.len());
        let token = &rest[..end];
        parts.extend(search_key(token).split(' ').filter(|t| !t.is_empty()).map(|t| format!("{t}*")));
        rest = &rest[end..];
    }
    parts.join(" ")
}

/// Texte recherché par sous-chaîne (`SermonDAO._plain_query`) : sans guillemets, espaces
/// regroupées.
pub fn plain_query(value: &str) -> String {
    straight_quotes(value).replace('"', " ").split_whitespace().collect::<Vec<_>>().join(" ")
}

/// La ponctuation qui reste collée au mot précédent : `; : ! ? » …` (suivie au plus d'un point
/// ou d'une virgule).
fn glues_to_previous(token: &str) -> bool {
    let body = token.strip_suffix(['.', ',']).unwrap_or(token);
    !body.is_empty() && body.chars().all(|c| matches!(c, ';' | ':' | '!' | '?' | '»' | '…'))
}

/// Les mots d'un paragraphe, la ponctuation française restant collée (`SlideCanvas._words`) :
/// « Amen ! » ne se coupe jamais avant le point d'exclamation, ni après un guillemet ouvrant.
pub fn words(paragraph: &str) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    let mut opening: Option<String> = None;
    for raw in paragraph.split_whitespace() {
        let token = match opening.take() {
            Some(open) => format!("{open} {raw}"),
            None => raw.to_string(),
        };
        if token == "«" {
            opening = Some(token);
        } else if let Some(last) = out.last_mut().filter(|_| glues_to_previous(&token)) {
            last.push(' ');
            last.push_str(&token);
        } else {
            out.push(token);
        }
    }
    if let Some(open) = opening {
        out.push(open);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strips_french_accents() {
        assert_eq!(fold("Éternel Dieu, ô Père"), "eternel dieu, o pere");
        assert_eq!(fold("Cœur ça déjà"), "cœur ca deja");
    }

    #[test]
    fn ascii_fast_path() {
        assert_eq!(fold("Colonne de FEU"), "colonne de feu");
    }

    #[test]
    fn compatibility_forms() {
        assert_eq!(fold("ﬁn²"), "fin2");
    }

    #[test]
    fn decomposed_input() {
        assert_eq!(fold("Cafe\u{301} DÉJÀ"), "cafe deja");
    }

    #[test]
    fn final_sigma() {
        assert_eq!(fold("ΟΔΟΣ"), "οδος");
    }

    #[test]
    fn search_keys() {
        assert_eq!(search_key("  La Foi est une FERME assurance !"), "la foi est une ferme assurance");
        assert_eq!(search_key("Jésus-Christ, l'Agneau"), "jesus christ l agneau");
        assert_eq!(search_key("63-0317M"), "63 0317m");
        assert_eq!(search_key("«»"), "");
    }

    #[test]
    fn fts_queries() {
        assert_eq!(fts_query(r#"foi "ferme assurance""#), r#"foi* "ferme assurance""#);
        assert_eq!(fts_query("« Grâce infinie »"), r#""grace infinie""#);
        assert_eq!(fts_query("l'Éternel"), "l* eternel*");
        assert_eq!(fts_query("   "), "");
        // Valeurs de référence données par la version Python.
        assert_eq!(fts_query(r#"a"b c"d"#), "a* b* c* d*");
        assert_eq!(fts_query(r#""ouvert sans fin"#), "ouvert* sans* fin*");
    }

    #[test]
    fn plain_queries() {
        assert_eq!(plain_query("  « foi   ferme »  "), "foi ferme");
    }

    #[test]
    fn french_punctuation_stays_glued() {
        assert_eq!(words("Il a dit : « Amen ! » Et voilà…"), ["Il", "a", "dit :", "« Amen ! »", "Et", "voilà…"]);
        assert_eq!(words("Gloire ! ?."), ["Gloire ! ?."]);
        assert_eq!(words("«"), ["«"]);
    }
}
