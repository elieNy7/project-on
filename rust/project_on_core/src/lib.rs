//! Fonctions natives de Project-On.
//!
//! Le module remplace les boucles Python les plus chaudes. Chaque fonction
//! rend EXACTEMENT le même résultat que sa version Python
//! (`app.utils.text_utils`), qui reste le repli quand le module manque.
//!
//! Depuis la phase 1 de la refonte 3.0, ce module n'est plus qu'une enveloppe :
//! le texte vient de `project-on-rs/crates/po-text`, partagé avec la 3.0.

mod image_ops;
mod sqlite_ext;

use pyo3::prelude::*;
use pyo3::types::{PyList, PyString};

/// Le pliage sans accents vient de `po-text`, le même code que la 3.0 (phase 1 de la refonte) :
/// NFKD, retrait des marques non espaçantes (Mn), puis minuscules, exactement comme `unaccent()`
/// en Python.
pub(crate) use po_text::fold;

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
    m.add_function(wrap_pyfunction!(image_ops::resize_lanczos, m)?)?;
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
