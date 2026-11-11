//! Les cantiques d'un recueil PDF (`hymn_pdf_parser.py` de la 2.8), à partir de ses lignes dans
//! l'ordre de lecture (une ligne vide entre deux strophes) : les en-têtes « numéro + titre en
//! capitales », puis les strophes, « Chœur » et « Refrain » compris. Les règles sont celles de la
//! 2.8, à l'identique : un même PDF donne les mêmes cantiques.

use std::sync::LazyLock;

use regex::Regex;

/// Les en-têtes et pieds de page des recueils connus.
const HEADER_PATTERNS: [&str; 6] = [
    "Petit Troupeau Tabernacle",
    "Un Evangile Eternel",
    "branhammessage",
    "TABLE DE MATIERES",
    "CHANTS CONVENTION",
    "Index",
];

#[allow(clippy::unwrap_used)]
static MUSIC_KEY: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)^(?:[A-G](?:b|#)?|[A-G](?:b|#)?m|Do|Re|Mi|Fa|Sol|La|Si)\.?$").unwrap());
#[allow(clippy::unwrap_used)]
static CHORUS: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)^(ch(?:oe|œ)urs?|refrain|dernier refrain)\s*[.:]?\s*(.*)$").unwrap());
#[allow(clippy::unwrap_used)]
static SPACES: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"[ \t]+").unwrap());
#[allow(clippy::unwrap_used)]
static EXO: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"(?i)\bEXO\b|Eclats|Éclats").unwrap());
#[allow(clippy::unwrap_used)]
static INLINE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^(\d{1,3})\.\s*(.+)$").unwrap());
#[allow(clippy::unwrap_used)]
static COMPACT: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^(\d{1,3})([A-ZÀ-ÖØ-Þ].+)$").unwrap());
#[allow(clippy::unwrap_used)]
static SPACED: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^(\d{1,3})\s+([A-ZÀ-ÖØ-Þ].+)$").unwrap());
#[allow(clippy::unwrap_used)]
static STANDALONE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"(?i)^(\d{1,3})(?:\s*([a-z]))?\.?$").unwrap());
#[allow(clippy::unwrap_used)]
static VERSE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^(\d{1,2})\.\s*(.*)$").unwrap());

/// Un cantique lu : numéro (« 12 », « 137B »), titre, strophes (un refrain commence par
/// « Choeur: »).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PdfHymn {
    pub number: String,
    pub title: String,
    pub stanzas: Vec<String>,
}

/// Apostrophes et guillemets droits, espaces simples (`normalize_text`).
pub fn normalize(value: &str) -> String {
    let value = value
        .replace(['\u{2019}', '\u{2018}'], "'")
        .replace(['\u{201c}', '\u{201d}'], "\"")
        .replace(['\u{a0}', '\u{202f}'], " ");
    SPACES.replace_all(&value, " ").trim().to_string()
}

/// Un en-tête ou un pied de page d'un recueil connu.
pub fn is_header_footer(text: &str) -> bool {
    let text = normalize(text).to_lowercase();
    HEADER_PATTERNS.iter().any(|p| text.contains(&p.to_lowercase()))
}

/// Le `strip(" .")` de Python.
fn strip_dots(text: &str) -> &str {
    text.trim_matches(|c| c == ' ' || c == '.')
}

fn strip_music_key(title: &str) -> String {
    let title = normalize(title);
    let parts: Vec<&str> = title.split_whitespace().collect();
    let title = match parts.last() {
        Some(last) if MUSIC_KEY.is_match(last) => parts[..parts.len() - 1].join(" "),
        _ => parts.join(" "),
    };
    strip_dots(&title).to_string()
}

fn upper_ratio(text: &str) -> f64 {
    let letters: Vec<char> = text.chars().filter(|c| c.is_alphabetic()).collect();
    if letters.is_empty() {
        return 0.0;
    }
    letters.iter().filter(|c| c.is_uppercase()).count() as f64 / letters.len() as f64
}

fn looks_like_title(text: &str) -> bool {
    let text = strip_music_key(text);
    if text.chars().count() < 3 || CHORUS.is_match(&text) || MUSIC_KEY.is_match(&text) {
        return false;
    }
    let leading = text.trim_start_matches(['"', '\'', '(', '[']);
    if !leading.chars().next().is_some_and(char::is_uppercase) {
        return false;
    }
    let first_part = text.split('(').next().unwrap_or("").trim_end();
    // `re.split(r"\s*\(")` : les espaces avant la parenthèse ne comptent pas.
    if upper_ratio(first_part.trim()) >= 0.70 {
        return true;
    }
    upper_ratio(&text) >= 0.62 && text.chars().count() <= 80
}

fn should_continue_title(line: &str, parts: &[String]) -> bool {
    let clean = strip_music_key(line);
    if clean.is_empty() || MUSIC_KEY.is_match(&clean) {
        return false;
    }
    if parts.last().is_some_and(|p| p.trim_end().ends_with('-')) {
        return true;
    }
    let previous = parts.last().map_or("", String::as_str);
    if EXO.is_match(&clean) {
        return clean.chars().count() <= 55;
    }
    if EXO.is_match(previous) {
        let lower = clean.to_lowercase();
        return lower.starts_with("d'") || lower.starts_with("d\u{2019}");
    }
    looks_like_title(&clean) && clean.chars().count() <= 70
}

/// `str.title()` de Python : une capitale au début de chaque suite de lettres.
fn python_title(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    let mut previous_cased = false;
    for c in text.chars() {
        if previous_cased {
            out.extend(c.to_lowercase());
        } else {
            out.extend(c.to_uppercase());
        }
        previous_cased = c.is_alphabetic();
    }
    out
}

fn clean_title(title: &str) -> String {
    let title = strip_music_key(title);
    let title = title.split_whitespace().collect::<Vec<_>>().join(" ");
    let title = title.replace(" .", ".");
    let title = python_title(strip_dots(&title));
    // `str.title()` met une capitale après l'apostrophe (« D'Amour » → « D'amour » n'est pas
    // voulu) : la 2.8 ne corrige que les formes qu'elle liste, à l'identique.
    let title = title.replace("Jesus", "Jésus");
    title.trim().to_string()
}

fn clean_body_line(line: &str) -> String {
    let line = normalize(line);
    if MUSIC_KEY.is_match(&line) { String::new() } else { line }
}

/// Les en-têtes de cantiques : (ligne de l'en-tête, numéro, titre, première ligne du texte).
pub fn headers(lines: &[String]) -> Vec<(usize, String, String, usize)> {
    let mut out = Vec::new();
    let mut i = 0;
    while i < lines.len() {
        let line = normalize(&lines[i]);
        if line.is_empty() {
            i += 1;
            continue;
        }
        let mut number: Option<String> = None;
        let mut parts: Vec<String> = Vec::new();
        let mut body_start = i + 1;
        let title_of = |re: &Regex| {
            re.captures(&line).filter(|c| looks_like_title(&c[2])).map(|c| (c[1].to_string(), c[2].to_string()))
        };
        if let Some((n, t)) = title_of(&INLINE).or_else(|| title_of(&COMPACT)).or_else(|| title_of(&SPACED)) {
            number = Some(n);
            parts.push(t);
        } else if let Some(c) = STANDALONE.captures(&line) {
            let mut j = i + 1;
            while j < lines.len() && normalize(&lines[j]).is_empty() {
                j += 1;
            }
            if j < lines.len() && looks_like_title(&lines[j]) {
                number = Some(format!("{}{}", &c[1], c.get(2).map_or(String::new(), |m| m.as_str().to_uppercase())));
                parts.push(lines[j].clone());
                body_start = j + 1;
            }
        }
        let Some(number) = number else {
            i += 1;
            continue;
        };
        let mut j = body_start;
        while j < lines.len() {
            let candidate = normalize(&lines[j]);
            if candidate.is_empty() {
                break;
            }
            if should_continue_title(&candidate, &parts) {
                parts.push(candidate);
                j += 1;
                body_start = j;
                continue;
            }
            break;
        }
        let title = clean_title(&parts.join(" "));
        if title.chars().count() >= 3 {
            out.push((i, number, title, body_start));
            i = body_start.max(i + 1);
        } else {
            i += 1;
        }
    }
    out
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Label {
    Verse,
    Chorus,
    FinalChorus,
}

/// Les strophes d'un cantique (`parse_stanzas`) ; un refrain unique est répété après chaque
/// couplet.
pub fn stanzas(lines: &[String]) -> Vec<String> {
    let mut parts: Vec<(Label, String)> = Vec::new();
    let mut label = Label::Verse;
    let mut current: Vec<String> = Vec::new();
    let mut pending_blank = false;
    let flush = |parts: &mut Vec<(Label, String)>, current: &mut Vec<String>, label: Label| {
        let text = current.iter().filter(|l| !l.is_empty()).cloned().collect::<Vec<_>>().join("\n");
        let text = text.trim().to_string();
        if !text.is_empty() {
            parts.push((label, text));
        }
        current.clear();
    };
    for raw in lines {
        if raw.is_empty() {
            if matches!(label, Label::Chorus | Label::FinalChorus) && current.is_empty() {
                continue;
            }
            if label == Label::Chorus && !current.is_empty() {
                pending_blank = true;
                continue;
            }
            flush(&mut parts, &mut current, label);
            pending_blank = false;
            label = Label::Verse;
            continue;
        }
        let line = clean_body_line(raw);
        if line.is_empty() {
            continue;
        }
        if pending_blank {
            if line.starts_with('(') {
                current.push(line);
                pending_blank = false;
                continue;
            }
            flush(&mut parts, &mut current, label);
            pending_blank = false;
            label = Label::Verse;
        }
        if let Some(c) = CHORUS.captures(&line) {
            flush(&mut parts, &mut current, label);
            pending_blank = false;
            label = if c[1].to_lowercase().starts_with("dernier") { Label::FinalChorus } else { Label::Chorus };
            let rest = c[2].trim();
            if !rest.is_empty() {
                current.push(rest.to_string());
            }
            continue;
        }
        if let Some(c) = VERSE.captures(&line)
            && !looks_like_title(&c[2])
        {
            flush(&mut parts, &mut current, label);
            pending_blank = false;
            label = Label::Verse;
            let rest = c[2].trim();
            if !rest.is_empty() {
                current.push(rest.to_string());
            }
            continue;
        }
        current.push(line);
    }
    flush(&mut parts, &mut current, label);

    let choruses: Vec<&String> = parts.iter().filter(|(l, _)| *l == Label::Chorus).map(|(_, t)| t).collect();
    let finals = parts.iter().filter(|(l, _)| *l == Label::FinalChorus).count();
    let verses: Vec<&String> = parts.iter().filter(|(l, _)| *l == Label::Verse).map(|(_, t)| t).collect();
    if choruses.len() == 1 && finals == 0 && verses.len() > 1 {
        return verses.iter().flat_map(|v| [(*v).clone(), format!("Choeur:\n{}", choruses[0])]).collect();
    }
    parts
        .into_iter()
        .map(|(l, t)| match l {
            Label::Chorus => format!("Choeur:\n{t}"),
            Label::FinalChorus => format!("Dernier refrain:\n{t}"),
            Label::Verse => t,
        })
        .collect()
}

/// Les cantiques d'un recueil, à partir de ses lignes (`parse_hymns_for_import`).
pub fn hymns_from_lines(lines: &[String]) -> Vec<PdfHymn> {
    let found = headers(lines);
    let mut out = Vec::new();
    for (index, (_, number, title, body_start)) in found.iter().enumerate() {
        let next = found.get(index + 1).map_or(lines.len(), |h| h.0);
        let body = lines.get(*body_start..next.max(*body_start)).unwrap_or(&[]);
        let stanzas = stanzas(body);
        if !stanzas.is_empty() {
            out.push(PdfHymn { number: number.clone(), title: title.clone(), stanzas });
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lines(text: &str) -> Vec<String> {
        text.lines().map(str::to_string).collect()
    }

    #[test]
    fn a_numbered_hymn_with_a_single_chorus_repeats_it() {
        let hymns = hymns_from_lines(&lines(
            "12. GRÂCE INFINIE Do\nQuelle grâce, ô mon Dieu\nTu m'as sauvé\n\nChoeur :\nGloire à Dieu\nAlléluia\n\nTon amour me suit\nChaque jour\n\n13\nA LA CROIX\nJe viens à toi\n",
        ));
        assert_eq!(hymns.len(), 2);
        assert_eq!(hymns[0].number, "12");
        assert_eq!(hymns[0].title, "Grâce Infinie");
        assert_eq!(
            hymns[0].stanzas,
            [
                "Quelle grâce, ô mon Dieu\nTu m'as sauvé",
                "Choeur:\nGloire à Dieu\nAlléluia",
                "Ton amour me suit\nChaque jour",
                "Choeur:\nGloire à Dieu\nAlléluia"
            ]
        );
        assert_eq!((hymns[1].number.as_str(), hymns[1].title.as_str()), ("13", "A La Croix"));
    }

    #[test]
    fn python_title_case_is_reproduced() {
        assert_eq!(python_title("L'AMOUR DE DIEU"), "L'Amour De Dieu");
        assert_eq!(clean_title("JESUS EST LÀ  Sol"), "Jésus Est Là");
    }
}
