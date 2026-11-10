//! Les strophes de cantiques : refrains, étiquettes, texte projeté.

use std::sync::LazyLock;

use regex::Regex;

use crate::clean::clean_text;
use crate::py;

#[allow(clippy::unwrap_used)] // expressions fixes, vérifiées par les tests
fn re(pattern: &str) -> Regex {
    Regex::new(pattern).unwrap()
}

/// L'étiquette en tête d'une strophe (« Refrain : », « 2. Chœur », « [Chorus] »…), retirée à la
/// projection (`_HYMN_SECTION_LABEL_RE`).
static SECTION_LABEL: LazyLock<Regex> = LazyLock::new(|| {
    re(
        r"(?i)\A[\s\x1C-\x1F]*(?:[\[(][\s\x1C-\x1F]*)?(?:\d{1,2}[\s\x1C-\x1F]*[.)-][\s\x1C-\x1F]*|[-*•][\s\x1C-\x1F]*)?(?:dernier[\s\x1C-\x1F]+refrain|dernier[\s\x1C-\x1F]+ch(?:oe|œ)ur|ch(?:oe|œ)ur|refrain|chorus)(?:[\s\x1C-\x1F]*[\])])?(?:[\s\x1C-\x1F]*[:.;,\-–—][\s\x1C-\x1F]*|[\s\x1C-\x1F]+|[\s\x1C-\x1F]*\n+|[\s\x1C-\x1F]*\z)",
    )
});

/// Une strophe qui commence par « Refrain », « Chœur », « Chorus » (`_detect_hymn_chorus`).
static CHORUS: LazyLock<Regex> =
    LazyLock::new(|| re(r"(?i)^(?:Dernier[\s\x1C-\x1F]+)?(?:Ch(?:oe|œ)urs?|Refrain|Chorus)"));

/// Le texte projeté d'une strophe : nettoyé, sans les étiquettes de refrain en tête
/// (`strip_hymn_projection_label`).
pub fn strip_hymn_projection_label(value: &str) -> String {
    let mut text = clean_text(value);
    let mut previous: Option<String> = None;
    while !text.is_empty() && previous.as_deref() != Some(text.as_str()) {
        let next = py::strip(&SECTION_LABEL.replace(&text, "")).to_string();
        previous = Some(std::mem::replace(&mut text, next));
    }
    text
}

/// La strophe est-elle un refrain ?
pub fn is_chorus(text: &str) -> bool {
    CHORUS.is_match(py::strip(text))
}

/// Les étiquettes des strophes d'un cantique, dans l'ordre : « Strophe 1 », « Refrain »,
/// « Strophe 2 », « Refrain 2 »… (le refrain est reconnu à son texte).
pub fn stanza_labels<'a>(texts: impl IntoIterator<Item = &'a str>) -> Vec<(String, bool)> {
    let (mut verse_no, mut chorus_no) = (0, 0);
    texts
        .into_iter()
        .map(|text| {
            if is_chorus(text) {
                chorus_no += 1;
                (if chorus_no <= 1 { "Refrain".to_string() } else { format!("Refrain {chorus_no}") }, true)
            } else {
                verse_no += 1;
                (format!("Strophe {verse_no}"), false)
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    // Valeurs attendues données par la 2.8.
    #[test]
    fn labels_are_removed_before_projection() {
        assert_eq!(strip_hymn_projection_label("Refrain :\nGloire à Dieu"), "Gloire à Dieu");
        assert_eq!(strip_hymn_projection_label("[Chœur] Gloire"), "Gloire");
        assert_eq!(strip_hymn_projection_label("2. Refrain - Refrain\nAmen"), "Amen");
        assert_eq!(strip_hymn_projection_label("Refrains d'été"), "Refrains d'été");
        assert_eq!(strip_hymn_projection_label("Refrain"), "");
    }

    #[test]
    fn choruses_are_numbered() {
        let labels = stanza_labels(["Il vient", "Refrain\nGloire", "Il règne", "CHOEUR Amen"]);
        assert_eq!(
            labels,
            [
                ("Strophe 1".to_string(), false),
                ("Refrain".to_string(), true),
                ("Strophe 2".to_string(), false),
                ("Refrain 2".to_string(), true)
            ]
        );
    }
}
