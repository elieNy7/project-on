//! Les mots d'une requête et leur repérage dans un texte (sans accents ni majuscules) : ce que la
//! page Recherche de Project-On et l'onglet Recherche de MEDITATION surlignent, et l'extrait
//! montré autour du premier mot trouvé.

use po_text::{fold, looks_like_reference};

use crate::{MIN_TEXT_QUERY, one_line};

/// Les mots à repérer d'une requête, pliés (sans accents ni majuscules) : chaque expression
/// entre guillemets, chaque mot d'au moins trois lettres, et la phrase entière. Aucun pour une
/// référence. Les plus longs d'abord : une expression passe avant ses mots.
pub fn highlights(query: &str) -> Vec<String> {
    let q = query.trim();
    let mut out = required(q);
    let phrase = fold(q.split_whitespace().collect::<Vec<_>>().join(" ").as_str());
    if !out.is_empty() && !q.contains('"') && q.split_whitespace().nth(1).is_some() && !out.contains(&phrase) {
        out.push(phrase);
    }
    out.sort_by_key(|m| std::cmp::Reverse(m.len()));
    out
}

/// Ce que le texte d'un résultat doit contenir (plié) : chaque expression entre guillemets, et
/// chaque mot d'au moins trois lettres. Aucun pour une référence.
pub fn required(query: &str) -> Vec<String> {
    let q = query.trim();
    if q.chars().count() < MIN_TEXT_QUERY || looks_like_reference(q) {
        return Vec::new();
    }
    let mut out: Vec<String> = Vec::new();
    let mut keep = |m: String| {
        if !m.is_empty() && !out.contains(&m) {
            out.push(m);
        }
    };
    for (i, part) in q.split('"').enumerate() {
        if i % 2 == 1 {
            keep(fold(part.split_whitespace().collect::<Vec<_>>().join(" ").as_str()));
            continue;
        }
        for word in part.split(|c: char| !c.is_alphanumeric()) {
            if word.chars().count() >= 3 {
                keep(fold(word));
            }
        }
    }
    out
}

/// Le texte contient-il ce qui est cherché ? L'index plein texte connaît aussi le titre du sermon :
/// un paragraphe y serait trouvé par son seul titre. Seul le texte compte.
pub fn in_text(text: &str, query: &str) -> bool {
    let needed = required(query);
    if needed.is_empty() {
        return true;
    }
    let folded = fold(text);
    needed.iter().all(|m| folded.contains(m.as_str()))
}

/// Les passages de `text` (en lettres, de..à) où paraît l'un des `words`, dans l'ordre, sans
/// chevauchement.
pub fn occurrences(text: &str, words: &[String]) -> Vec<(usize, usize)> {
    if words.is_empty() {
        return Vec::new();
    }
    // Le texte plié, lettre par lettre ; pour chaque octet plié, la lettre d'origine.
    let mut folded = String::with_capacity(text.len());
    let mut origin = Vec::with_capacity(text.len());
    for (i, c) in text.chars().enumerate() {
        let before = folded.len();
        if c.is_ascii() {
            folded.push(c.to_ascii_lowercase());
        } else {
            let mut buf = [0u8; 4];
            folded.push_str(&fold(c.encode_utf8(&mut buf)));
        }
        origin.extend(std::iter::repeat_n(i, folded.len() - before));
    }
    let mut found = Vec::new();
    for m in words.iter().filter(|m| !m.is_empty()) {
        let mut from = 0;
        while let Some(at) = folded[from..].find(m.as_str()) {
            let (a, b) = (from + at, from + at + m.len());
            found.push((origin[a], origin[b - 1] + 1));
            from = b;
        }
    }
    found.sort_unstable();
    let mut out: Vec<(usize, usize)> = Vec::with_capacity(found.len());
    for (a, b) in found {
        match out.last_mut() {
            Some(last) if a <= last.1 => last.1 = last.1.max(b),
            _ => out.push((a, b)),
        }
    }
    out
}

/// `text` sur une ligne, commencé un peu avant le premier mot trouvé, coupé à `limit` lettres.
pub fn around(text: &str, words: &[String], limit: usize) -> String {
    let flat = text.split_whitespace().collect::<Vec<_>>().join(" ");
    let start = occurrences(&flat, words).first().map_or(0, |(a, _)| *a);
    if start <= 60 {
        return one_line(&flat, limit);
    }
    // Quarante lettres avant le mot, à partir d'un début de mot.
    let chars: Vec<char> = flat.chars().collect();
    let mut from = start - 40;
    while from < start && !chars[from - 1].is_whitespace() {
        from += 1;
    }
    let rest: String = chars[from..].iter().collect();
    format!("…{}", one_line(&rest, limit.saturating_sub(1)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn words_and_expressions_are_folded_and_references_have_none() {
        assert_eq!(highlights("Grâce de Dieu"), vec!["grace de dieu", "grace", "dieu"]);
        assert_eq!(highlights("\"colonne de feu\" Moïse"), vec!["colonne de feu", "moise"]);
        assert!(highlights("Jean 3:16").is_empty());
        assert!(highlights("de").is_empty());
    }

    #[test]
    fn only_the_text_counts_never_the_title() {
        assert!(in_text("La colonne de nuée, la colonne de feu.", "colonne de feu"));
        assert!(!in_text("« Oui. »", "colonne de feu"));
        assert!(!in_text("la colonne, puis le feu", "\"colonne de feu\""));
    }

    #[test]
    fn occurrences_ignore_accents_and_case_and_merge() {
        let text = "La GRÂCE de Dieu, la grâce !";
        let found = occurrences(text, &highlights("grace"));
        let parts: Vec<String> = found.iter().map(|(a, b)| text.chars().skip(*a).take(b - a).collect()).collect();
        assert_eq!(parts, vec!["GRÂCE", "grâce"]);
    }

    #[test]
    fn the_excerpt_starts_near_the_first_word_found() {
        let text = format!("{} la colonne de feu les conduisait.", "mot ".repeat(40));
        let e = around(&text, &highlights("colonne"), 120);
        assert!(e.starts_with('…') && e.contains("colonne de feu"), "{e}");
        assert_eq!(around("Court texte.", &highlights("texte"), 120), "Court texte.");
    }
}
