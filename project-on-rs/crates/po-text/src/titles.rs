//! Les titres, lieux et repères affichés : casse des titres imprimés en capitales, titre commun à
//! toutes les traductions d'une prédication, repère d'un paragraphe (« ¶12 », « E-76 », « 3-14 »),
//! chapitres de l'Exposé (`app.database.connection`, `app.database.dao_sermons`).

use std::sync::LazyLock;

use regex::Regex;

use crate::clean::clean_text;
use crate::py;

#[allow(clippy::unwrap_used)] // expressions fixes, vérifiées par les tests
fn re(pattern: &str) -> Regex {
    Regex::new(pattern).unwrap()
}

/// Les petits mots laissés en minuscules dans un titre tout en capitales.
const SMALL_WORDS: &[&str] = &[
    "a", "au", "aux", "avec", "ce", "ces", "de", "des", "du", "en", "et", "la", "le", "les", "pour", "que", "qui",
    "sur", "un", "une",
];

/// Les pronoms et particules en fin de mot composé : « Est-ce », « A-t-il ».
const HYPHEN_SUFFIXES: &[&str] =
    &["t", "il", "ils", "elle", "elles", "on", "je", "tu", "nous", "vous", "ce", "ci", "là"];

/// Les élisions : la lettre qui suit l'apostrophe prend une capitale (« L’Ange », « Qu’Il »).
const ELISIONS: &[&str] = &["l", "d", "j", "m", "n", "s", "t", "c", "qu", "jusqu", "lorsqu", "puisqu", "quoiqu"];

static ROMAN: LazyLock<Regex> = LazyLock::new(|| re(r"^C{0,3}(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})$"));
static APOSTROPHE: LazyLock<Regex> = LazyLock::new(|| re(r"[’']"));
static PLACE_WITH_STATE_USA: LazyLock<Regex> = LazyLock::new(|| {
    re(r"[\s\x1C-\x1F]*-[\s\x1C-\x1F]*[A-Z][A-Z' .-]+(?:[\s\x1C-\x1F]+[A-Z]{2})?[\s\x1C-\x1F]+USA[\s\x1C-\x1F]*$")
});
static PLACE_WITH_COUNTRY: LazyLock<Regex> =
    LazyLock::new(|| re(r"[\s\x1C-\x1F]*-[\s\x1C-\x1F]*[A-Z][A-Z' .-]+[\s\x1C-\x1F]+[A-Z]{2,}[\s\x1C-\x1F]*$"));
static GENERIC_TITLE: LazyLock<Regex> = LazyLock::new(|| re(r"(?i)^(SERMON|MESSAGE)[\s\x1C-\x1F]+\d+"));
static MARKER_BSS: LazyLock<Regex> = LazyLock::new(|| re(r"([A-Z]-[A-Z0-9]+)[\s\x1C-\x1F]*$"));
static MARKER_PILCROW: LazyLock<Regex> = LazyLock::new(|| re(r"([¶§][\s\x1C-\x1F]*\d+)[\s\x1C-\x1F]*$"));
static MARKER_PAGE: LazyLock<Regex> = LazyLock::new(|| re(r"(\d+)-(\d+)[\s\x1C-\x1F]*$"));
static EXPOSE_CHAPTER_PREFIX: LazyLock<Regex> = LazyLock::new(|| re(r"(?i)^CHAPITRE[\s\x1C-\x1F]+\d+[\s\x1C-\x1F]+"));
static EXPOSE_CHAPTER_CODE: LazyLock<Regex> = LazyLock::new(|| re(r"CH(\d+)"));

/// Regroupe les espaces (`re.sub(r"\s+", " ", text)`).
fn collapse_spaces(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    let mut in_space = false;
    for c in text.chars() {
        if py::is_space(c) {
            if !in_space {
                out.push(' ');
            }
            in_space = true;
        } else {
            out.push(c);
            in_space = false;
        }
    }
    out
}

/// Un titre TOUT EN MAJUSCULES : capitale à chaque mot, sauf les petits mots français.
pub fn title_case_french(text: &str) -> String {
    if !py::str_is_upper(text) {
        return text.to_string();
    }
    let lower = text.to_lowercase();
    py::split(&lower)
        .enumerate()
        .map(|(i, word)| if i > 0 && SMALL_WORDS.contains(&word) { word.to_string() } else { py::capitalize(word) })
        .collect::<Vec<_>>()
        .join(" ")
}

/// Un texte imprimé en capitales (tolère une coquille : « A-T-Il »).
pub fn mostly_uppercase(value: &str) -> bool {
    let letters: Vec<char> = value.chars().filter(|&c| py::is_alpha(c)).collect();
    if letters.is_empty() {
        return false;
    }
    let upper = letters.iter().filter(|&&c| py::is_upper(c)).count();
    upper as f64 / letters.len() as f64 >= 0.6
}

fn is_roman(token: &str) -> bool {
    // `$` de Python accepte un retour à la ligne final.
    let token = token.strip_suffix('\n').unwrap_or(token);
    !token.is_empty() && token.chars().all(|c| matches!(c, 'I' | 'V' | 'X' | 'L' | 'C')) && ROMAN.is_match(token)
}

/// Capitale après une élision : « L’ANGE » → « L’Ange », « QU’IL » → « Qu’Il », mais
/// « AUJOURD’HUI » → « Aujourd’hui ».
fn capitalize_piece(piece: &str) -> String {
    let lower = piece.to_lowercase();
    // `re.split(r"([’'])", …)` : les morceaux et les apostrophes, en alternance.
    let mut parts: Vec<&str> = Vec::new();
    let mut last = 0;
    for m in APOSTROPHE.find_iter(&lower) {
        parts.push(&lower[last..m.start()]);
        parts.push(m.as_str());
        last = m.end();
    }
    parts.push(&lower[last..]);
    let mut out = String::with_capacity(lower.len());
    for (index, part) in parts.iter().enumerate() {
        let previous = if index >= 2 { parts[index - 2] } else { "" };
        if index == 0 || ELISIONS.contains(&previous) {
            out.push_str(&py::upper_first(part));
        } else {
            out.push_str(part);
        }
    }
    out
}

fn title_case_word(token: &str) -> String {
    if is_roman(token) {
        return token.to_string();
    }
    let mut pieces = token.split('-');
    let mut out = capitalize_piece(pieces.next().unwrap_or(""));
    for piece in pieces {
        out.push('-');
        let lower = piece.to_lowercase();
        if HYPHEN_SUFFIXES.contains(&lower.as_str()) {
            out.push_str(&lower);
        } else {
            out.push_str(&capitalize_piece(piece));
        }
    }
    out
}

/// Capitale à chaque mot d'un titre imprimé TOUT EN MAJUSCULES ; les mots et la ponctuation
/// restent ceux de la source (« L’ANGE DE DIEU » → « L’Ange De Dieu »). Un texte surtout en
/// minuscules est rendu tel quel (nettoyé).
pub fn title_case_words(text: &str) -> String {
    let value = clean_text(text);
    if !mostly_uppercase(&value) {
        return value;
    }
    value.split(' ').map(title_case_word).collect::<Vec<_>>().join(" ")
}

/// Un lieu imprimé en capitales → « Phoenix AZ USA », « Afrique Du Sud ».
pub fn display_location(location: &str) -> String {
    let value = clean_text(location);
    if !mostly_uppercase(&value) {
        return value;
    }
    let tokens: Vec<&str> = value.split(' ').collect();
    tokens
        .iter()
        .enumerate()
        .map(|(index, token)| {
            let following = tokens.get(index + 1).copied().unwrap_or("");
            if *token == "USA"
                || (py::len(token) == 2 && py::str_is_alpha(token) && matches!(following, "USA" | "CANADA"))
            {
                token.to_string()
            } else {
                title_case_words(token)
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

/// Le titre d'une prédication sans le lieu final (« … - JEFFERSONVILLE IN USA »), en casse de
/// titre s'il est tout en capitales.
pub fn clean_sermon_title_for_canonical(title: &str) -> String {
    let text = clean_text(title);
    let text = PLACE_WITH_STATE_USA.replace(&text, "");
    let text = PLACE_WITH_COUNTRY.replace(&text, "");
    let text = collapse_spaces(&text);
    title_case_french(text.trim_matches([' ', '-']))
}

/// Le titre d'un cantique, nettoyé, en casse de titre s'il est tout en capitales.
pub fn clean_hymn_title_for_canonical(title: &str) -> String {
    let text = collapse_spaces(&clean_text(title));
    title_case_french(text.trim_matches([' ', '-']))
}

/// Une traduction d'une prédication, pour choisir le titre commun.
#[derive(Debug, Clone, Copy)]
pub struct TitleCandidate<'a> {
    pub title: &'a str,
    pub tradition: &'a str,
}

/// Le titre commun des traductions d'une prédication : un vrai titre plutôt que « Sermon 12 »,
/// puis VGR, BSS, SHP, puis le plus court. Le premier l'emporte à égalité.
pub fn choose_canonical_title(candidates: &[TitleCandidate<'_>]) -> String {
    let scored = candidates.iter().map(|c| {
        let title = clean_sermon_title_for_canonical(c.title);
        let generic = u8::from(GENERIC_TITLE.is_match(&title));
        let priority = match c.tradition.to_uppercase().as_str() {
            "VGR" => 0,
            "BSS" => 1,
            "SHP" => 2,
            _ => 3,
        };
        let length = py::len(&title);
        ((generic, priority, length), title)
    });
    scored.min_by(|(a, _), (b, _)| a.cmp(b)).map(|(_, title)| title).unwrap_or_default()
}

fn marker_from_value(value: &str, paragraph_no: i64) -> String {
    if let Some(caps) = MARKER_BSS.captures(value) {
        return caps[1].replace('O', "0");
    }
    if let Some(caps) = MARKER_PILCROW.captures(value) {
        return caps[1].chars().filter(|&c| !py::is_space(c)).collect();
    }
    if let Some(caps) = MARKER_PAGE.captures(value) {
        return format!("{}-{}", &caps[1], &caps[2]);
    }
    format!("¶{paragraph_no}")
}

/// Le repère d'un paragraphe tiré de sa référence, gardé dans la base (`_marker_from_ref`).
pub fn marker_from_ref(reference: &str, paragraph_no: i64) -> String {
    let value = reference.replace("Â¶", "¶").replace("Â§", "§");
    marker_from_value(py::strip(&value), paragraph_no)
}

/// Le repère d'un paragraphe affiché quand la base n'en a pas (`SermonsDao._get_marker`) : répare
/// aussi les références doublement mal encodées.
pub fn paragraph_marker(reference: &str, paragraph_no: i64) -> String {
    let value = reference.replace("Ã‚Â¶", "¶").replace("Ã‚Â§", "§").replace("Â¶", "¶").replace("Â§", "§");
    let value = py::strip(&value);
    if value.is_empty() {
        return format!("¶{paragraph_no}");
    }
    marker_from_value(value, paragraph_no)
}

/// « 47-0412 - La Foi Est une Ferme Assurance - ¶50 » : les parties non vides.
pub fn format_reference(date_code: &str, title: &str, marker: &str) -> String {
    [date_code, title, marker].iter().map(|p| py::strip(p)).filter(|p| !p.is_empty()).collect::<Vec<_>>().join(" - ")
}

/// La page et le paragraphe d'une référence de l'Exposé (« … 112-3 » → (112, 3)).
pub fn expose_ref_parts(value: &str) -> Option<(u32, u32)> {
    let caps = MARKER_PAGE.captures(py::strip(value))?;
    Some((py::ascii_int(&caps[1])?, py::ascii_int(&caps[2])?))
}

/// Le titre d'un chapitre de l'Exposé, sans « CHAPITRE 3 » en tête.
pub fn clean_expose_title(value: &str) -> String {
    let title = collapse_spaces(py::strip(value));
    py::strip(&EXPOSE_CHAPTER_PREFIX.replace(&title, "")).to_string()
}

/// Le numéro d'un chapitre de l'Exposé (0 pour l'introduction). Les chapitres SHP sont décalés
/// d'un cran : leur introduction est le chapitre 1 de la source.
pub fn expose_chapter_num(date_code: &str, title: &str, translator: &str) -> u32 {
    let raw = EXPOSE_CHAPTER_CODE.captures(date_code).and_then(|caps| py::ascii_int(&caps[1])).unwrap_or(0);
    if translator.eq_ignore_ascii_case("SHP") {
        if clean_expose_title(title).to_uppercase().starts_with("INTRODUCTION") {
            return 0;
        }
        if raw > 0 {
            return raw - 1;
        }
    }
    raw
}

/// Une date de filtre « 1965-12-31 » devient le code des prédications « 65-1231 » ; `__NODATE__`
/// (sans date) reste tel quel.
pub fn normalize_filter_date(value: &str) -> Option<String> {
    let v = py::strip(value);
    if v.is_empty() {
        return None;
    }
    let chars: Vec<char> = v.chars().collect();
    if chars.len() == 10 && chars[4] == '-' && chars[7] == '-' {
        let s = |a: usize, b: usize| chars[a..b].iter().collect::<String>();
        return Some(format!("{}-{}{}", s(2, 4), s(5, 7), s(8, 10)));
    }
    Some(v.to_string())
}

/// L'année d'un code de prédication : « 65-1231 » → 1965, « 03-0101 » → 2003, « 1953-09-12 » → 1953.
pub fn sermon_year(date: &str) -> Option<i32> {
    let chars: Vec<char> = date.chars().collect();
    if chars.len() < 2 {
        return None;
    }
    if chars.len() >= 10 && chars[4] == '-' && chars[7] == '-' {
        return chars[..4].iter().collect::<String>().parse().ok();
    }
    let yy: String = chars[..2].iter().collect();
    if !py::str_is_digit(&yy) {
        return None;
    }
    let y: i32 = py::ascii_int(&yy)?.try_into().ok()?;
    Some(if y >= 47 { 1900 + y } else { 2000 + y })
}

#[cfg(test)]
mod tests {
    use super::*;

    // Valeurs attendues données par la 2.8.
    #[test]
    fn printed_titles_get_title_case() {
        assert_eq!(title_case_words("L’ANGE DE DIEU"), "L’Ange De Dieu");
        assert_eq!(title_case_words("QU’IL VIENNE AUJOURD’HUI"), "Qu’Il Vienne Aujourd’hui");
        assert_eq!(title_case_words("EST-CE LE SCEAU II ?"), "Est-ce Le Sceau II ?");
        assert_eq!(title_case_words("La Foi"), "La Foi");
        assert_eq!(display_location("PHOENIX AZ USA"), "Phoenix AZ USA");
        assert_eq!(display_location("AFRIQUE DU SUD"), "Afrique Du Sud");
    }

    #[test]
    fn canonical_titles() {
        assert_eq!(clean_sermon_title_for_canonical("LA FOI - JEFFERSONVILLE IN USA"), "La Foi");
        // Particularité de la 2.8, gardée : le lieu final emporte aussi « -LE ».
        assert_eq!(clean_sermon_title_for_canonical("ECOUTEZ-LE - DURBAN AFRIQUE"), "Ecoutez");
        let candidates = [
            TitleCandidate { title: "Sermon 12", tradition: "VGR" },
            TitleCandidate { title: "LA FOI EST UNE FERME ASSURANCE", tradition: "SHP" },
            TitleCandidate { title: "La Foi est une ferme assurance", tradition: "BSS" },
        ];
        assert_eq!(choose_canonical_title(&candidates), "La Foi est une ferme assurance");
    }

    #[test]
    fn paragraph_markers() {
        assert_eq!(marker_from_ref("47-1123 Les enfants E-7O", 3), "E-70");
        assert_eq!(marker_from_ref("La Foi Â¶ 12", 3), "¶12");
        assert_eq!(marker_from_ref("Exposé 112-3 ", 3), "112-3");
        assert_eq!(marker_from_ref("", 4), "¶4");
        assert_eq!(paragraph_marker("La Foi Ã‚Â§5", 1), "§5");
        assert_eq!(format_reference(" 47-0412", "La Foi", ""), "47-0412 - La Foi");
    }

    #[test]
    fn expose_and_dates() {
        assert_eq!(expose_ref_parts("BK 112-3"), Some((112, 3)));
        assert_eq!(clean_expose_title("CHAPITRE 3  L'âge   d'Éphèse"), "L'âge d'Éphèse");
        assert_eq!(expose_chapter_num("BK-AGES-SHP-CH04", "L'âge d'Éphèse", "SHP"), 3);
        assert_eq!(expose_chapter_num("BK-AGES-SHP-CH01", "INTRODUCTION", "SHP"), 0);
        assert_eq!(normalize_filter_date("1965-12-31").as_deref(), Some("65-1231"));
        assert_eq!(sermon_year("65-1231"), Some(1965));
        assert_eq!(sermon_year("03-0101"), Some(2003));
        assert_eq!(sermon_year("BK-AGES"), None);
    }
}
