//! Le découpage des textes longs en parties équilibrées (`split_text_into_slides`) et des strophes
//! longues en groupes de vers (`split_hymn_stanza`), au caractère près comme la 2.8.

use std::sync::LazyLock;

use regex::Regex;

use crate::py;

/// La longueur maximale d'une partie, par défaut (caractères).
pub const MAX_CHARS_PER_SLIDE: usize = 280;
/// En dessous, une partie est « orpheline » (caractères).
pub const MIN_CHARS_PER_SLIDE: usize = 60;

#[allow(clippy::unwrap_used)] // expressions fixes, vérifiées par les tests
fn re(pattern: &str) -> Regex {
    Regex::new(pattern).unwrap()
}

static PARAGRAPH_BREAK: LazyLock<Regex> = LazyLock::new(|| re(r"\n[\s\x1C-\x1F]*\n+"));
static TABS_AND_SPACES: LazyLock<Regex> = LazyLock::new(|| re(r"[\t ]+"));
static INDENT: LazyLock<Regex> = LazyLock::new(|| re(r"\n[ \t]+"));
static TRAILING: LazyLock<Regex> = LazyLock::new(|| re(r"[ \t]+\n"));
static NEWLINE: LazyLock<Regex> = LazyLock::new(|| re(r"[\s\x1C-\x1F]*\n[\s\x1C-\x1F]*"));

/// La force d'une coupure : plus elle est haute, plus la coupure est naturelle.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
enum Break {
    Word = 0,
    Clause = 1,
    Sentence = 2,
    Line = 3,
    Paragraph = 4,
}

impl Break {
    /// On coupe entre deux paragraphes ou deux lignes avant de couper une phrase, et une phrase
    /// avant un mot.
    fn penalty(self) -> f64 {
        match self {
            Break::Paragraph => 0.0,
            Break::Line => 0.05,
            Break::Sentence => 0.15,
            Break::Clause => 0.6,
            Break::Word => 2.0,
        }
    }
}

/// Un morceau de texte et la force de la coupure qui le suit.
type Unit = (String, Break);

/// Les abréviations suivies d'un point qui ne terminent pas la phrase.
const ABBREVIATIONS: &[&str] = &[
    "m", "mm", "mme", "mlle", "dr", "st", "ste", "fr", "sr", "jr", "mr", "mrs", "rév", "rev", "frère", "soeur", "p",
    "pp", "v", "vv", "ch", "chap", "cf", "etc", "no", "n°", "env", "vol", "av", "apr", "j.-c", "c-à-d", "ex",
];

const CLOSERS: &[char] = &['»', '"', '”', '’', '\'', ')', ']'];

/// `token` termine-t-il une phrase (et non une abréviation ou une numérotation) ?
fn is_sentence_end(token: &str, next_token: &str) -> bool {
    let before_closers = token.trim_end_matches(CLOSERS);
    if !before_closers.ends_with(['.', '!', '?', '…']) {
        return false;
    }
    let word = token
        .trim_end_matches(['.', '!', '?', '…', '»', '"', '”', '’', '\'', ')', ']'])
        .to_lowercase()
        .trim_start_matches(['«', '"', '“', '‘', '('])
        .to_string();
    if before_closers.ends_with('.') && !token.ends_with("..") {
        if ABBREVIATIONS.contains(&word.as_str()) || (py::len(&word) == 1 && py::str_is_alpha(&word)) {
            return false;
        }
        // « 3. » suivi d'une minuscule : numérotation, pas une fin de phrase.
        if py::str_is_digit(&word) && next_token.chars().next().is_some_and(char::is_lowercase) {
            return false;
        }
    }
    true
}

fn ends_clause(word: &str) -> bool {
    word.ends_with([',', ';', ':', '—', '–'])
}

fn set_last(units: &mut [Unit], strength: Break) {
    if let Some(last) = units.last_mut() {
        last.1 = strength;
    }
}

/// Une ligne en unités : la phrase entière si elle tient, sinon ses propositions, sinon ses mots.
fn units_of_line(line: &str, limit: usize) -> Vec<Unit> {
    let tokens: Vec<&str> = py::split(line).collect();
    if tokens.is_empty() {
        return Vec::new();
    }
    let mut sentences: Vec<Vec<&str>> = vec![Vec::new()];
    for (index, token) in tokens.iter().enumerate() {
        if let Some(current) = sentences.last_mut() {
            current.push(token);
        }
        let following = tokens.get(index + 1).copied().unwrap_or("");
        if !following.is_empty() && is_sentence_end(token, following) {
            sentences.push(Vec::new());
        }
    }
    sentences.retain(|words| !words.is_empty());

    let mut units: Vec<Unit> = Vec::new();
    for words in sentences {
        let sentence = words.join(" ");
        if py::len(&sentence) <= limit {
            units.push((sentence, Break::Sentence));
            continue;
        }
        let mut clauses: Vec<Vec<&str>> = vec![Vec::new()];
        for (index, word) in words.iter().enumerate() {
            if let Some(current) = clauses.last_mut() {
                current.push(word);
            }
            if index + 1 < words.len() && ends_clause(word) {
                clauses.push(Vec::new());
            }
        }
        for clause_words in clauses {
            let clause = clause_words.join(" ");
            if py::len(&clause) <= limit {
                units.push((clause, Break::Clause));
                continue;
            }
            for word in clause_words {
                let chars: Vec<char> = word.chars().collect();
                if chars.len() > limit {
                    // Une adresse, un mot démesuré : coupe brute.
                    units.extend(chars.chunks(limit).map(|chunk| (chunk.iter().collect(), Break::Word)));
                } else {
                    units.push((word.to_string(), Break::Word));
                }
            }
            set_last(&mut units, Break::Clause);
        }
        set_last(&mut units, Break::Sentence);
    }
    units
}

fn text_units(raw: &str, limit: usize) -> Vec<Unit> {
    let mut units: Vec<Unit> = Vec::new();
    for paragraph in PARAGRAPH_BREAK.split(raw).filter(|p| !py::strip(p).is_empty()) {
        let lines: Vec<&str> = paragraph.split('\n').map(py::strip).filter(|l| !l.is_empty()).collect();
        for (index, line) in lines.iter().enumerate() {
            let mut line_units = units_of_line(line, limit);
            if line_units.is_empty() {
                continue;
            }
            let strength = if index == lines.len() - 1 { Break::Paragraph } else { Break::Line };
            set_last(&mut line_units, strength);
            units.extend(line_units);
        }
    }
    set_last(&mut units, Break::Paragraph);
    units
}

fn join_units(units: &[Unit], keep_line_breaks: bool) -> String {
    let mut out = String::new();
    for (index, (chunk, strength)) in units.iter().enumerate() {
        out.push_str(chunk);
        if index + 1 < units.len() {
            out.push(if keep_line_breaks && *strength >= Break::Line { '\n' } else { ' ' });
        }
    }
    out
}

/// La longueur des unités `[i, j)` jointes (un séparateur entre chacune).
fn span_length(prefix: &[usize], i: usize, j: usize) -> usize {
    prefix[j] - prefix[i] + (j - i - 1)
}

/// Le découpage optimal (programmation dynamique) : le moins de parties possible, puis les parties
/// les plus égales et les coupures les plus naturelles, sans partie orpheline évitable.
fn partition_units(units: &[Unit], limit: usize, min_chars: usize) -> Vec<(usize, usize)> {
    let n = units.len();
    let mut prefix = vec![0usize];
    for (chunk, _) in units {
        prefix.push(prefix[prefix.len() - 1] + py::len(chunk));
    }

    // Le nombre minimal de parties (le glouton est optimal pour ce critère).
    let mut k_min = 0;
    let mut i = 0;
    while i < n {
        let mut j = i + 1;
        while j < n && span_length(&prefix, i, j + 1) <= limit {
            j += 1;
        }
        k_min += 1;
        i = j;
    }

    let total = span_length(&prefix, 0, n) as f64;
    let target = total / k_min.max(1) as f64;
    let mut best = vec![vec![f64::INFINITY; n + 1]; k_min + 1];
    let mut back = vec![vec![usize::MAX; n + 1]; k_min + 1];
    best[0][0] = 0.0;
    for k in 1..=k_min {
        for j in 1..=n {
            for i in (0..j).rev() {
                let length = span_length(&prefix, i, j);
                if length > limit && j - i > 1 {
                    break;
                }
                let previous = best[k - 1][i];
                if previous == f64::INFINITY {
                    continue;
                }
                let gap = (length as f64 - target) / target.max(1.0);
                let mut cost = gap * gap;
                if length < min_chars && k_min > 1 {
                    cost += 4.0;
                }
                if j < n {
                    cost += units[j - 1].1.penalty();
                }
                if previous + cost < best[k][j] {
                    best[k][j] = previous + cost;
                    back[k][j] = i;
                }
            }
        }
    }
    if best[k_min][n] == f64::INFINITY {
        return vec![(0, n)]; // sécurité : ne devrait pas arriver
    }
    let mut spans = Vec::with_capacity(k_min);
    let mut j = n;
    for k in (1..=k_min).rev() {
        let i = back[k][j];
        spans.push((i, j));
        j = i;
    }
    spans.reverse();
    spans
}

/// Découpe un texte long en parties équilibrées et lisibles.
///
/// Coupe d'abord entre paragraphes, puis entre lignes (alinéas, vers), puis en fin de phrase (sans
/// couper après « M. », « St. », « v. »…), puis aux virgules, et en dernier recours entre deux
/// mots. Les parties ont une longueur proche ; les retours à la ligne sont gardés
/// (`keep_line_breaks`).
pub fn split_text_into_slides(text: &str, max_chars: usize, min_chars: usize, keep_line_breaks: bool) -> Vec<String> {
    let raw = py::strip(text);
    if raw.is_empty() {
        return Vec::new();
    }
    let raw = raw.replace('\r', "");
    let raw = TABS_AND_SPACES.replace_all(&raw, " ");
    let raw = INDENT.replace_all(&raw, "\n");
    let raw = TRAILING.replace_all(&raw, "\n");
    let max_chars = max_chars.max(40);
    let min_chars = min_chars.min(max_chars / 2);

    let raw = if keep_line_breaks { raw.into_owned() } else { NEWLINE.replace_all(&raw, " ").into_owned() };
    if py::len(&raw) <= max_chars {
        return vec![raw];
    }

    let units = text_units(&raw, max_chars);
    if units.is_empty() {
        return vec![raw];
    }
    let spans = if units.len() > 600 {
        // Texte démesuré : regroupement glouton (évite un calcul trop long).
        let mut spans = Vec::new();
        let (mut start, mut length) = (0, 0);
        for (index, (chunk, _)) in units.iter().enumerate() {
            let extra = py::len(chunk) + usize::from(index > start);
            if index > start && length + extra > max_chars {
                spans.push((start, index));
                start = index;
                length = py::len(chunk);
            } else {
                length += extra;
            }
        }
        spans.push((start, units.len()));
        spans
    } else {
        partition_units(&units, max_chars, min_chars)
    };
    spans.into_iter().filter(|(i, j)| i < j).map(|(i, j)| join_units(&units[i..j], keep_line_breaks)).collect()
}

/// Découpe une strophe longue en parties de quelques vers.
///
/// Les vers ne sont jamais coupés (sauf un vers plus long que `max_chars`). Les parties sont
/// équilibrées : 8 vers en 4 + 4, 6 vers en 4 + 2 avec les couplets (vers 1-2, 3-4, 5-6 restent
/// ensemble) ou 3 + 3 sans. Une strophe sans retours à la ligne est découpée comme un texte.
pub fn split_hymn_stanza(text: &str, max_lines: usize, max_chars: usize, keep_couplets: bool) -> Vec<String> {
    let raw = text.replace('\r', "");
    let raw = py::strip(&raw);
    if raw.is_empty() {
        return Vec::new();
    }
    let lines: Vec<String> = raw
        .split('\n')
        .map(|line| py::strip(&TABS_AND_SPACES.replace_all(line, " ")).to_string())
        .filter(|line| !line.is_empty())
        .collect();
    let max_lines = max_lines.max(1);
    let max_chars = max_chars.max(40);

    if lines.len() <= 1 {
        return split_text_into_slides(raw, max_chars, 0, true);
    }

    // Un vers démesuré est d'abord découpé pour respecter la limite.
    let mut verses: Vec<String> = Vec::new();
    for line in lines {
        if py::len(&line) > max_chars {
            verses.extend(
                split_text_into_slides(&line, max_chars, 0, true).into_iter().map(|part| part.replace('\n', " ")),
            );
        } else {
            verses.push(line);
        }
    }

    let span_len = |group: &[&String]| -> usize {
        group.iter().map(|v| py::len(v)).sum::<usize>() + group.len().saturating_sub(1)
    };
    let all: Vec<&String> = verses.iter().collect();
    if verses.len() <= max_lines && span_len(&all) <= max_chars {
        return vec![verses.join("\n")];
    }

    // Blocs insécables : couplets (deux vers) ou vers seuls.
    let mut block = if keep_couplets && max_lines >= 2 { 2 } else { 1 };
    let mut blocks: Vec<Vec<&String>> = all.chunks(block).map(<[&String]>::to_vec).collect();
    let mut parts_count = verses.len().div_ceil(max_lines).max(span_len(&all).div_ceil(max_chars)).max(1);
    loop {
        parts_count = parts_count.min(blocks.len());
        let (base, extra) = (blocks.len() / parts_count, blocks.len() % parts_count);
        let mut groups: Vec<Vec<&String>> = Vec::with_capacity(parts_count);
        let mut pos = 0;
        for index in 0..parts_count {
            let size = base + usize::from(index < extra);
            groups.push(blocks[pos..pos + size].iter().flatten().copied().collect());
            pos += size;
        }
        let too_big = groups.iter().any(|g| g.len() > max_lines || span_len(g) > max_chars);
        if !too_big || parts_count >= blocks.len() {
            if too_big && block == 2 {
                // Couplets trop longs pour la limite : vers par vers.
                block = 1;
                blocks = all.iter().map(|v| vec![*v]).collect();
                continue;
            }
            return groups
                .into_iter()
                .filter(|g| !g.is_empty())
                .map(|g| g.iter().map(|v| v.as_str()).collect::<Vec<_>>().join("\n"))
                .collect();
        }
        parts_count += 1;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // Valeurs attendues données par `app.utils.text_utils` (2.8).
    #[test]
    fn short_text_is_kept_whole() {
        assert_eq!(split_text_into_slides("  Amen.\r\n  Gloire  ", 280, 60, true), ["Amen.\nGloire"]);
        assert!(split_text_into_slides(" \n ", 280, 60, true).is_empty());
    }

    #[test]
    fn sentences_are_not_cut_after_abbreviations() {
        let text = "Le Fr. Branham a dit ceci à St. Louis. Puis il a continué longtemps. ".repeat(4);
        let one = "Le Fr. Branham a dit ceci à St. Louis.";
        let two = "Puis il a continué longtemps.";
        assert_eq!(
            split_text_into_slides(&text, 120, 60, true),
            [format!("{one} {two} {one}"), format!("{two} {one} {two}"), format!("{one} {two}")]
        );
    }

    #[test]
    fn stanzas_keep_couplets() {
        let stanza = "v1\nv2\nv3\nv4\nv5\nv6";
        assert_eq!(split_hymn_stanza(stanza, 4, 280, true), ["v1\nv2\nv3\nv4", "v5\nv6"]);
        assert_eq!(split_hymn_stanza(stanza, 4, 280, false), ["v1\nv2\nv3", "v4\nv5\nv6"]);
        assert_eq!(split_hymn_stanza(stanza, 2, 280, true), ["v1\nv2", "v3\nv4", "v5\nv6"]);
    }
}
