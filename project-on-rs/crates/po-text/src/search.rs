//! Les clés et requêtes de recherche (`Database._search_key`, `SermonsDao._fts_query`,
//! `HymnsDao._fts_query`, `SermonsDao._plain_query`).

use unicode_normalization::UnicodeNormalization;

use crate::clean::clean_text;
use crate::fold::is_kept;
use crate::py;

/// Clé de recherche : texte nettoyé, minuscules, sans accents ; tout ce qui n'est ni lettre ASCII
/// ni chiffre devient une espace, espaces regroupées.
pub fn search_key(value: &str) -> String {
    let lowered = clean_text(value).to_lowercase();
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

/// Les guillemets français et anglais deviennent `"` dans les requêtes.
fn straight_quotes(value: &str) -> String {
    value.chars().map(|c| if matches!(c, '«' | '»' | '“' | '”' | '„') { '"' } else { c }).collect()
}

/// Requête FTS5 des prédications : mots en préfixe, « expression exacte » entre guillemets.
/// `foi "ferme assurance"` → `foi* "ferme assurance"`.
pub fn fts_query(value: &str) -> String {
    let text = straight_quotes(value);
    let mut parts: Vec<String> = Vec::new();
    let mut rest = text.as_str();
    loop {
        rest = rest.trim_start_matches(py::is_space);
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
        let end = rest.find(py::is_space).unwrap_or(rest.len());
        parts.extend(search_key(&rest[..end]).split(' ').filter(|t| !t.is_empty()).map(|t| format!("{t}*")));
        rest = &rest[end..];
    }
    parts.join(" ")
}

/// Requête FTS5 des cantiques : chaque mot de la clé, en préfixe (pas d'expression exacte).
pub fn hymn_fts_query(value: &str) -> String {
    search_key(value).split(' ').filter(|t| !t.is_empty()).map(|t| format!("{t}*")).collect::<Vec<_>>().join(" ")
}

/// Texte recherché par sous-chaîne : sans guillemets, espaces regroupées.
pub fn plain_query(value: &str) -> String {
    py::split(&straight_quotes(value).replace('"', " ")).collect::<Vec<_>>().join(" ")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn search_keys() {
        assert_eq!(search_key("  La Foi est une FERME assurance !"), "la foi est une ferme assurance");
        assert_eq!(search_key("Jésus-Christ, l'Agneau"), "jesus christ l agneau");
        assert_eq!(search_key("63-0317M"), "63 0317m");
        assert_eq!(search_key("«»"), "");
        assert_eq!(search_key("L&#39;&Eacute;ternel<br>"), "l eternel");
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
        assert_eq!(hymn_fts_query(r#"« Grâce » infinie"#), "grace* infinie*");
    }

    #[test]
    fn plain_queries() {
        assert_eq!(plain_query("  « foi   ferme »  "), "foi ferme");
    }
}
