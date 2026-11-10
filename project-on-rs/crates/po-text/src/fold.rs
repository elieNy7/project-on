//! Le pliage sans accents (`unaccent()` de la 2.8), repris de `rust/project_on_core`.

use std::sync::OnceLock;

use unicode_general_category::{GeneralCategory, get_general_category};
use unicode_normalization::UnicodeNormalization;

pub(crate) fn is_kept(c: char) -> bool {
    get_general_category(c) != GeneralCategory::NonspacingMark
}

/// `unaccent()` : NFKD, retrait des marques non espaçantes (Mn), puis minuscules.
///
/// Même ordre qu'en Python : `lower()` vient après le filtre, donc les marques qu'il produit
/// lui-même sont conservées.
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
}
