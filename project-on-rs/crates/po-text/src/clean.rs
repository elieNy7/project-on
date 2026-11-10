//! Le nettoyage des textes importés (`clean_text` de la 2.8) et le décodage HTML
//! (`html.unescape` de Python).

use std::borrow::Cow;
use std::sync::LazyLock;

use regex::{Captures, Regex};

use crate::entities::ENTITIES;
use crate::py;

#[allow(clippy::unwrap_used)] // expressions fixes, vérifiées par les tests
fn re(pattern: &str) -> Regex {
    Regex::new(pattern).unwrap()
}

static CHARREF: LazyLock<Regex> = LazyLock::new(|| re(r"&(#[0-9]+;?|#[xX][0-9a-fA-F]+;?|[^\t\n\x0C <&#;]{1,32};?)"));
static HTML_TAG: LazyLock<Regex> = LazyLock::new(|| re(r"<[^>]+>"));
static PILCROW_LINE: LazyLock<Regex> = LazyLock::new(|| re(r"(^|\n)[\s\x1C-\x1F]*¶[\s\x1C-\x1F]*"));
static CONTROL_CHARS: LazyLock<Regex> = LazyLock::new(|| re(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]"));
static SPACES: LazyLock<Regex> = LazyLock::new(|| re(r"[\t ]+"));

fn entity(name: &str) -> Option<&'static str> {
    ENTITIES.binary_search_by(|(n, _)| n.cmp(&name)).ok().map(|i| ENTITIES[i].1)
}

/// Les références numériques que HTML5 remplace (`_invalid_charrefs` de Python).
fn invalid_charref(n: u64) -> Option<&'static str> {
    Some(match n {
        0x00 => "\u{fffd}",
        0x0d => "\r",
        0x80 => "\u{20ac}",
        0x81 => "\u{81}",
        0x82 => "\u{201a}",
        0x83 => "\u{192}",
        0x84 => "\u{201e}",
        0x85 => "\u{2026}",
        0x86 => "\u{2020}",
        0x87 => "\u{2021}",
        0x88 => "\u{2c6}",
        0x89 => "\u{2030}",
        0x8a => "\u{160}",
        0x8b => "\u{2039}",
        0x8c => "\u{152}",
        0x8d => "\u{8d}",
        0x8e => "\u{17d}",
        0x8f => "\u{8f}",
        0x90 => "\u{90}",
        0x91 => "\u{2018}",
        0x92 => "\u{2019}",
        0x93 => "\u{201c}",
        0x94 => "\u{201d}",
        0x95 => "\u{2022}",
        0x96 => "\u{2013}",
        0x97 => "\u{2014}",
        0x98 => "\u{2dc}",
        0x99 => "\u{2122}",
        0x9a => "\u{161}",
        0x9b => "\u{203a}",
        0x9c => "\u{153}",
        0x9d => "\u{9d}",
        0x9e => "\u{17e}",
        0x9f => "\u{178}",
        _ => return None,
    })
}

/// Les points de code que HTML5 supprime (`_invalid_codepoints` de Python).
fn invalid_codepoint(n: u64) -> bool {
    matches!(n, 0x1..=0x8 | 0xb | 0xe..=0x1f | 0x7f..=0x9f | 0xfdd0..=0xfdef) || (n <= 0x10ffff && n & 0xfffe == 0xfffe)
}

fn replace_charref(reference: &str) -> String {
    if let Some(number) = reference.strip_prefix('#') {
        let (digits, radix) = match number.strip_prefix(['x', 'X']) {
            Some(hex) => (hex, 16),
            None => (number, 10),
        };
        let n = digits
            .trim_end_matches(';')
            .chars()
            .filter_map(|c| c.to_digit(radix))
            .fold(0u64, |n, d| n.saturating_mul(u64::from(radix)).saturating_add(u64::from(d)));
        if let Some(text) = invalid_charref(n) {
            return text.to_string();
        }
        if (0xd800..=0xdfff).contains(&n) || n > 0x10ffff {
            return "\u{fffd}".to_string();
        }
        if invalid_codepoint(n) {
            return String::new();
        }
        return u32::try_from(n).ok().and_then(char::from_u32).map(String::from).unwrap_or_default();
    }
    if let Some(text) = entity(reference) {
        return text.to_string();
    }
    // Le plus long nom connu au début (règle de HTML5), d'au moins deux caractères.
    let starts: Vec<usize> = reference.char_indices().map(|(at, _)| at).collect();
    for x in (2..starts.len()).rev() {
        let (name, rest) = reference.split_at(starts[x]);
        if let Some(text) = entity(name) {
            return format!("{text}{rest}");
        }
    }
    format!("&{reference}")
}

/// `html.unescape` : les références nommées et numériques de HTML5, avec les mêmes règles que
/// Python pour les références invalides ou sans point-virgule.
pub fn html_unescape(s: &str) -> Cow<'_, str> {
    if !s.contains('&') {
        return Cow::Borrowed(s);
    }
    CHARREF.replace_all(s, |caps: &Captures<'_>| replace_charref(&caps[1]))
}

/// `clean_text` : décode le HTML et retire balises, caractères invisibles et de contrôle, marques
/// de paragraphe (¶) et espaces en trop.
pub fn clean_text(value: &str) -> String {
    let s = html_unescape(value)
        .replace(['\u{feff}', '\u{200b}', '\u{fffd}'], "")
        .replace(['\u{a0}', '\u{202f}'], " ")
        .replace("\u{c2} ", " ")
        .replace('\r', "")
        .replace("<br/>", "\n")
        .replace("<br />", "\n")
        .replace("<br>", "\n")
        .replace("&nbsp;", " ");
    let s = HTML_TAG.replace_all(&s, "");
    let s = PILCROW_LINE.replace_all(&s, "$1");
    let s = s.replace('¶', "");
    let s = CONTROL_CHARS.replace_all(&s, "");
    let s = SPACES.replace_all(&s, " ");
    py::strip(&s).to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    // Valeurs attendues relevées avec Python 3.14 (html.unescape, text_utils.clean_text).
    #[test]
    fn unescapes_like_python() {
        assert_eq!(html_unescape("&eacute;&amp;&#233;&#xE9;&#X41;"), "é&éé\u{41}");
        assert_eq!(html_unescape("&notit; &amp &ampx &zzz; &#;"), "¬it; & &x &zzz; &#;");
        assert_eq!(html_unescape("&#150;&#0;&#xD800;&#1114112;&#11;&#65534;"), "\u{2013}\u{fffd}\u{fffd}\u{fffd}");
        assert_eq!(html_unescape("a & b"), "a & b");
    }

    #[test]
    fn cleans_like_python() {
        assert_eq!(clean_text("  <b>Grâce</b>&nbsp;infinie\u{a0}\r\n¶ 12 Amen\u{7}  "), "Grâce infinie \n12 Amen");
        assert_eq!(clean_text("L&#39;Ange<br/>de\tDieu"), "L'Ange\nde Dieu");
        assert_eq!(clean_text("¶¶ a ¶ b"), "a b");
        assert_eq!(clean_text("Â x &amp;nbsp;y"), "x y");
    }
}
