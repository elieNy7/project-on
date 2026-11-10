//! Le comportement des chaînes de Python, là où il diffère de celui de Rust.
//!
//! La 3.0 doit couper, comparer et mettre en forme exactement comme la 2.8 : mêmes espaces, mêmes
//! longueurs (en caractères, pas en octets), mêmes majuscules.

use unicode_general_category::{GeneralCategory as G, get_general_category};

/// `str.isspace()` : les espaces Unicode, plus les séparateurs ASCII U+001C à U+001F (que Rust ne
/// compte pas comme espaces).
pub fn is_space(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}

/// `str.split()` sans argument.
pub fn split(s: &str) -> impl Iterator<Item = &str> {
    s.split(is_space).filter(|t| !t.is_empty())
}

/// `str.strip()` sans argument.
pub fn strip(s: &str) -> &str {
    s.trim_matches(is_space)
}

/// `len(s)` : le nombre de caractères.
pub fn len(s: &str) -> usize {
    s.chars().count()
}

/// `s[:n]` : les `n` premiers caractères.
pub fn prefix(s: &str, n: usize) -> &str {
    match s.char_indices().nth(n) {
        Some((at, _)) => &s[..at],
        None => s,
    }
}

/// `c.isalpha()` : les lettres (catégories L*).
pub fn is_alpha(c: char) -> bool {
    matches!(
        get_general_category(c),
        G::UppercaseLetter | G::LowercaseLetter | G::TitlecaseLetter | G::ModifierLetter | G::OtherLetter
    )
}

/// `c.isdigit()` : les chiffres décimaux (Nd) et les chiffres en exposant ou en indice.
///
/// Python compte aussi quelques chiffres cerclés ou entre parenthèses ; ils n'apparaissent pas dans
/// les textes de Project-On.
pub fn is_digit(c: char) -> bool {
    get_general_category(c) == G::DecimalNumber
        || matches!(c, '¹' | '²' | '³' | '⁰' | '⁴'..='⁹' | '₀'..='₉' | '①'..='⑨')
}

/// `s.isalpha()`.
pub fn str_is_alpha(s: &str) -> bool {
    !s.is_empty() && s.chars().all(is_alpha)
}

/// `s.isdigit()`.
pub fn str_is_digit(s: &str) -> bool {
    !s.is_empty() && s.chars().all(is_digit)
}

/// `s.isupper()` : au moins une lettre à casse, et aucune en minuscule ou en casse de titre.
pub fn str_is_upper(s: &str) -> bool {
    let mut cased = false;
    for c in s.chars() {
        if c.is_lowercase() || get_general_category(c) == G::TitlecaseLetter {
            return false;
        }
        if c.is_uppercase() {
            cased = true;
        }
    }
    cased
}

/// `c.isupper()` pour un seul caractère.
pub fn is_upper(c: char) -> bool {
    c.is_uppercase()
}

/// La casse de titre d'un caractère (la première lettre de `str.capitalize()`). Elle diffère des
/// majuscules pour les digrammes et les ligatures : « ǆ » → « ǅ », « ß » → « Ss », « ﬁ » → « Fi ».
fn title_char(c: char, out: &mut String) {
    let special = match c {
        'Ǆ' | 'ǅ' | 'ǆ' => "ǅ",
        'Ǉ' | 'ǈ' | 'ǉ' => "ǈ",
        'Ǌ' | 'ǋ' | 'ǌ' => "ǋ",
        'Ǳ' | 'ǲ' | 'ǳ' => "ǲ",
        'ß' => "Ss",
        'ﬀ' => "Ff",
        'ﬁ' => "Fi",
        'ﬂ' => "Fl",
        'ﬃ' => "Ffi",
        'ﬄ' => "Ffl",
        'ﬅ' | 'ﬆ' => "St",
        _ => {
            out.extend(c.to_uppercase());
            return;
        }
    };
    out.push_str(special);
}

/// `s.capitalize()` : première lettre en casse de titre, le reste en minuscules.
pub fn capitalize(s: &str) -> String {
    let mut chars = s.chars();
    let mut out = String::with_capacity(s.len());
    if let Some(first) = chars.next() {
        title_char(first, &mut out);
        out.push_str(&chars.as_str().to_lowercase());
    }
    out
}

/// `s[:1].upper() + s[1:]`.
pub fn upper_first(s: &str) -> String {
    let mut chars = s.chars();
    match chars.next() {
        Some(first) => {
            let mut out: String = first.to_uppercase().collect();
            out.push_str(chars.as_str());
            out
        }
        None => String::new(),
    }
}

/// `s.casefold()` : les minuscules, plus les pliages qui ne sont pas des minuscules (« ß » → « ss »,
/// « ſ » → « s », « ς » → « σ », ligatures latines).
pub fn casefold(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            'ß' | 'ẞ' => out.push_str("ss"),
            'ſ' => out.push('s'),
            'ς' => out.push('σ'),
            'µ' => out.push('μ'),
            'ﬀ' => out.push_str("ff"),
            'ﬁ' => out.push_str("fi"),
            'ﬂ' => out.push_str("fl"),
            'ﬃ' => out.push_str("ffi"),
            'ﬄ' => out.push_str("ffl"),
            'ﬅ' | 'ﬆ' => out.push_str("st"),
            'ŉ' => out.push_str("ʼn"),
            _ => out.extend(c.to_lowercase()),
        }
    }
    out
}

/// `int(s)` pour une suite de chiffres ASCII (`\d+` d'une expression) ; `None` au-delà de `u32` ou
/// pour des chiffres non ASCII (que Python accepte, mais qu'aucun texte de Project-On ne contient).
pub fn ascii_int(s: &str) -> Option<u32> {
    if s.is_empty() || !s.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    s.parse().ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn python_whitespace() {
        assert_eq!(split(" a\u{1c}b\u{a0}c ").collect::<Vec<_>>(), ["a", "b", "c"]);
        assert_eq!(strip("\u{1f} x \n"), "x");
    }

    #[test]
    fn python_case() {
        assert!(str_is_upper("L’ANGE DE DIEU"));
        assert!(!str_is_upper("123"));
        assert!(!str_is_upper("ǅA"));
        assert_eq!(capitalize("éTERNEL"), "Éternel");
        assert_eq!(capitalize("ßa"), "Ssa");
        assert_eq!(upper_first("ßa"), "SSa");
        assert_eq!(casefold("Straße"), "strasse");
    }

    #[test]
    fn python_lengths() {
        assert_eq!(len("Éternel"), 7);
        assert_eq!(prefix("Éternel", 2), "Ét");
        assert_eq!(prefix("ab", 5), "ab");
    }
}
