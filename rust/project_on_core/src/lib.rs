//! Fonctions natives de Project-On.
//!
//! Le module remplace les boucles Python les plus chaudes. Chaque fonction
//! rend EXACTEMENT le même résultat que sa version Python
//! (`app.utils.text_utils`), qui reste le repli quand le module manque.

mod sqlite_ext;

use std::sync::OnceLock;

use pyo3::prelude::*;
use pyo3::types::{PyList, PyString};
use unicode_general_category::{GeneralCategory, get_general_category};
use unicode_normalization::UnicodeNormalization;

fn is_kept(c: char) -> bool {
    get_general_category(c) != GeneralCategory::NonspacingMark
}

/// NFKD, retrait des marques non espaçantes (Mn), puis minuscules.
///
/// Même ordre que `unaccent()` en Python : `lower()` vient après le filtre,
/// donc les marques qu'il produit lui-même sont conservées.
fn fold(text: &str) -> String {
    if text.is_ascii() {
        return text.to_ascii_lowercase();
    }
    // Le sigma final (Σ → ς) dépend des lettres voisines : passage complet.
    if text.contains('Σ') {
        return fold_slow(text);
    }
    // Passage rapide : un caractère ASCII est stable en NFKD et la
    // réorganisation canonique ne franchit jamais un caractère de base,
    // donc chaque suite non ASCII peut être normalisée à part.
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
                // Aucune marque combinante avant U+0300 : rien à réordonner,
                // chaque lettre se plie seule.
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

/// Pliage précalculé des lettres latines (é → e, Œ → œ, ß → ß…), qui sont
/// l'essentiel des caractères non ASCII des textes français.
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

/// Texte d'un objet Python comme le fait `unaccent()` : « vide » pour une
/// valeur fausse (None, "", 0), `str(obj)` pour ce qui n'est pas une chaîne.
fn fold_object(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    if let Ok(s) = obj.cast::<PyString>() {
        return Ok(fold(s.to_str()?));
    }
    if obj.is_none() || !obj.is_truthy()? {
        return Ok(String::new());
    }
    Ok(fold(obj.str()?.to_str()?))
}

/// Version native de `app.utils.text_utils.unaccent`.
#[pyfunction]
fn unaccent(text: &Bound<'_, PyAny>) -> PyResult<String> {
    fold_object(text)
}

/// `[unaccent(t) for t in texts]`, sans repasser par Python à chaque texte.
#[pyfunction]
fn fold_many(py: Python<'_>, texts: &Bound<'_, PyList>) -> PyResult<Vec<String>> {
    // (texte, déjà plié) : les valeurs rares (None, nombre) passent tout de
    // suite par `fold_object`, et on ne les replie pas : plier deux fois
    // n'est pas garanti identique à plier une fois.
    let mut owned: Vec<(String, bool)> = Vec::with_capacity(texts.len());
    for item in texts.iter() {
        match item.cast::<PyString>() {
            Ok(s) => owned.push((s.to_str()?.to_owned(), false)),
            Err(_) => owned.push((fold_object(&item)?, true)),
        }
    }
    Ok(py.detach(|| {
        owned
            .into_iter()
            .map(|(t, done)| if done { t } else { fold(&t) })
            .collect()
    }))
}

#[pymodule]
fn project_on_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(unaccent, m)?)?;
    m.add_function(wrap_pyfunction!(fold_many, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::fold;

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
        // NFKD : ligature « ﬁ » et exposant « ² ».
        assert_eq!(fold("ﬁn²"), "fin2");
    }

    #[test]
    fn decomposed_input() {
        // « e » + accent aigu combinant, coupé entre deux suites.
        assert_eq!(fold("Cafe\u{301} DÉJÀ"), "cafe deja");
    }

    #[test]
    fn final_sigma() {
        assert_eq!(fold("ΟΔΟΣ"), "οδος");
    }
}
