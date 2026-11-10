//! L'ajustement du texte, porté de `SlideCanvas` (2.8) : la plus grande taille où le texte tient
//! dans sa zone, des lignes coupées sans jamais couper un mot, équilibrées, et les vers d'un
//! cantique gardés entiers quand c'est possible.
//!
//! Toutes les mesures sont celles de `QFontMetrics` (voir [`Fonts::qt_metrics`] et
//! [`Fonts::qt_advance`]) : la 3.0 choisit la même taille et les mêmes coupures que la 2.8.

use crate::fonts::Fonts;

/// La police d'un texte : famille, graisse, espacement des lettres (pixels).
#[derive(Debug, Clone, Copy)]
pub struct FontSpec<'a> {
    pub family: &'a str,
    pub weight: u16,
    pub letter_spacing: f32,
}

impl FontSpec<'_> {
    /// La largeur d'une ligne : la somme de ses mots et de ses espaces, chacun mesuré une fois. C'est
    /// exactement la mesure de Qt, qui additionne les avances arrondies de chaque lettre (seul un
    /// crénage de part et d'autre d'une espace pourrait l'en écarter).
    fn advance(&self, fonts: &mut Fonts, text: &str, size: f32) -> f32 {
        let mut total = 0.0;
        let mut spaces = 0usize;
        for (i, token) in text.split(' ').enumerate() {
            if i > 0 {
                spaces += 1;
            }
            if !token.is_empty() {
                total += fonts.qt_advance_cached(token, self.family, self.weight, size, self.letter_spacing);
            }
        }
        if spaces > 0 {
            total += spaces as f32 * fonts.qt_advance_cached(" ", self.family, self.weight, size, self.letter_spacing);
        }
        total
    }
}

/// `str.splitlines()` de Python : les fins de ligne de Python, sans élément final vide.
pub fn splitlines(text: &str) -> Vec<&str> {
    let mut out = Vec::new();
    let mut start = 0;
    let mut chars = text.char_indices().peekable();
    while let Some((i, c)) = chars.next() {
        let is_break = matches!(
            c,
            '\n' | '\r' | '\u{0b}' | '\u{0c}' | '\u{1c}' | '\u{1d}' | '\u{1e}' | '\u{85}' | '\u{2028}' | '\u{2029}'
        );
        if is_break {
            out.push(&text[start..i]);
            let mut end = i + c.len_utf8();
            if c == '\r'
                && let Some(&(j, '\n')) = chars.peek()
            {
                chars.next();
                end = j + 1;
            }
            start = end;
        }
    }
    if start < text.len() {
        out.push(&text[start..]);
    }
    out
}

/// `value.splitlines() or [value]`.
fn paragraphs(text: &str) -> Vec<&str> {
    let lines = splitlines(text);
    if lines.is_empty() { vec![text] } else { lines }
}

/// La découpe gloutonne (`_wrap_lines`) : chaque ligne est mesurée en entier.
pub fn wrap_lines(fonts: &mut Fonts, text: &str, spec: FontSpec<'_>, size: f32, width: f32) -> Vec<String> {
    let mut wrapped = Vec::new();
    for paragraph in paragraphs(text) {
        let words = po_text::words(paragraph);
        if words.is_empty() {
            wrapped.push(String::new());
            continue;
        }
        let mut current = String::new();
        for word in words {
            let candidate = if current.is_empty() {
                word.clone()
            } else {
                po_text::py::strip(&format!("{current} {word}")).to_string()
            };
            if current.is_empty() || spec.advance(fonts, &candidate, size) <= width {
                current = candidate;
                continue;
            }
            wrapped.push(std::mem::replace(&mut current, word));
        }
        if !current.is_empty() {
            wrapped.push(current);
        }
    }
    wrapped
}

/// Répartit les mots sur `count` lignes de largeur ≤ `width`, les plus égales possible
/// (`_even_split`) ; `None` si c'est impossible.
fn even_split(words: &[String], advances: &[f32], space: f32, width: f32, count: usize) -> Option<Vec<String>> {
    let n = words.len();
    if count == 0 {
        return None;
    }
    let mut prefix = vec![0.0f64];
    for a in advances {
        prefix.push(prefix[prefix.len() - 1] + f64::from(*a));
    }
    let space = f64::from(space);
    let line_width = |i: usize, j: usize| prefix[j] - prefix[i] + space * (j as f64 - i as f64 - 1.0);
    let target = line_width(0, n) / count as f64;
    let width = f64::from(width);
    let mut best = vec![vec![f64::INFINITY; n + 1]; count + 1];
    let mut cut = vec![vec![0usize; n + 1]; count + 1];
    best[0][0] = 0.0;
    for k in 1..=count {
        for j in k..=n {
            // `range(j - 1, k - 2, -1)` : de j - 1 jusqu'à k - 1 compris.
            for i in (k - 1..j).rev() {
                let w = line_width(i, j);
                if w > width {
                    break; // plus de mots ne ferait qu'élargir la ligne
                }
                let cost = best[k - 1][i] + (w - target).powi(2);
                if cost < best[k][j] {
                    best[k][j] = cost;
                    cut[k][j] = i;
                }
            }
        }
    }
    if best[count][n].is_infinite() {
        return None;
    }
    let mut lines = Vec::with_capacity(count);
    let mut j = n;
    for k in (1..=count).rev() {
        let i = cut[k][j];
        lines.push(words[i..j].join(" "));
        j = i;
    }
    lines.reverse();
    Some(lines)
}

/// Les lignes équilibrées (`_balanced_lines`) : le même nombre que la découpe gloutonne, de
/// longueurs voisines, si la vraie mesure les confirme.
pub fn balanced_lines(fonts: &mut Fonts, text: &str, spec: FontSpec<'_>, size: f32, width: f32) -> Vec<String> {
    let mut out = Vec::new();
    for paragraph in paragraphs(text) {
        let lines = wrap_lines(fonts, paragraph, spec, size, width);
        let words = po_text::words(paragraph);
        if lines.len() < 2 {
            out.extend(lines);
            continue;
        }
        let advances: Vec<f32> = words.iter().map(|w| spec.advance(fonts, w, size)).collect();
        let space = spec.advance(fonts, " ", size);
        match even_split(&words, &advances, space, width, lines.len()) {
            Some(even) if even.iter().all(|line| spec.advance(fonts, line, size) <= width) => out.extend(even),
            _ => out.extend(lines),
        }
    }
    out
}

/// La plus grande taille où chaque vers tient sur une ligne et où le bloc tient en hauteur
/// (`_largest_unbroken_size`) ; 0 si aucune.
pub fn largest_unbroken_size(
    fonts: &mut Fonts,
    lines: &[String],
    spec: FontSpec<'_>,
    wrap_width: f32,
    box_height: f32,
    ceiling: i32,
    floor: i32,
    line_height: f32,
) -> i32 {
    let mut fits = |size: i32| {
        let m = fonts.qt_metrics(spec.family, spec.weight, size as f32);
        let ls = f64::from(m.line_spacing);
        let step = ls * f64::from(line_height);
        let height = (ls + step * (lines.len() as f64 - 1.0)) * 1.08;
        height <= f64::from(box_height) && lines.iter().all(|line| spec.advance(fonts, line, size as f32) <= wrap_width)
    };
    let (mut lo, mut hi, mut best) = (floor, ceiling, 0);
    while lo <= hi {
        let mid = (lo + hi) / 2;
        if fits(mid) {
            best = mid;
            lo = mid + 1;
        } else {
            hi = mid - 1;
        }
    }
    best
}

/// La taille de mesure de l'estimation.
const MEASURE_SIZE: f32 = 100.0;

/// L'estimation de la hauteur du texte découpé à une taille (`_scaled_fit`) : les mots sont mesurés
/// une fois à 100 px puis mis à l'échelle.
struct Estimate {
    paragraphs: Vec<Vec<(f32, usize)>>,
    space: f32,
    spacing: f32,
    line_spacing: f32,
    limit: f32,
    line_height: f32,
}

impl Estimate {
    fn new(fonts: &mut Fonts, text: &str, spec: FontSpec<'_>, wrap_width: f32, line_height: f32) -> Self {
        let plain = FontSpec { letter_spacing: 0.0, ..spec };
        let paragraphs = paragraphs(text)
            .into_iter()
            .map(|p| {
                po_text::words(p)
                    .iter()
                    .map(|w| (plain.advance(fonts, w, MEASURE_SIZE), w.chars().count()))
                    .collect::<Vec<_>>()
            })
            .collect();
        Estimate {
            paragraphs,
            space: plain.advance(fonts, " ", MEASURE_SIZE),
            spacing: spec.letter_spacing,
            line_spacing: fonts.qt_metrics(spec.family, spec.weight, MEASURE_SIZE).line_spacing as f32,
            limit: wrap_width * 0.99,
            line_height,
        }
    }

    fn height(&self, size: i32) -> f64 {
        let k = size as f32 / MEASURE_SIZE;
        let mut count = 0usize;
        for words in &self.paragraphs {
            count += 1;
            let mut current = -1.0f32;
            for &(advance, letters) in words {
                let width = advance * k + self.spacing * letters as f32;
                if width > self.limit {
                    return f64::INFINITY;
                }
                if current < 0.0 {
                    current = width;
                } else if current + self.space * k + self.spacing + width <= self.limit {
                    current += self.space * k + self.spacing + width;
                } else {
                    count += 1;
                    current = width;
                }
            }
        }
        let step = f64::from(self.line_spacing * k);
        (step + step * f64::from(self.line_height) * (count as f64 - 1.0)) * 1.08
    }
}

/// L'ajustement façon PowerPoint (`_fit_text_size`) : la plus grande taille ≤ `ceiling` où le texte
/// découpé tient entièrement dans la zone ; au pire `floor`, sans jamais couper un mot. Rend la
/// taille et les lignes gloutonnes.
pub fn fit_text_size(
    fonts: &mut Fonts,
    text: &str,
    spec: FontSpec<'_>,
    wrap_width: f32,
    box_height: i32,
    ceiling: i32,
    floor: i32,
    line_height: f32,
) -> (i32, Vec<String>) {
    if po_text::py::strip(text).is_empty() {
        return (ceiling, splitlines(text).iter().map(|s| s.to_string()).collect());
    }
    let estimate = Estimate::new(fonts, text, spec, wrap_width, line_height);
    let floor = floor.min(ceiling);
    let (mut lo, mut hi, mut best) = (floor, ceiling, floor);
    while lo <= hi {
        let mid = (lo + hi) / 2;
        if estimate.height(mid) <= f64::from(box_height) {
            best = mid;
            lo = mid + 1;
        } else {
            hi = mid - 1;
        }
    }
    // Vérification avec la vraie mesure ; au moindre dépassement, on descend un peu.
    loop {
        let size = best as f32;
        let lines = wrap_lines(fonts, text, spec, size, wrap_width);
        let ls = f64::from(fonts.qt_metrics(spec.family, spec.weight, size).line_spacing);
        let step = ls * f64::from(line_height);
        let mut height = ((ls + step * (lines.len() as f64 - 1.0)) * 1.08) as i64;
        if lines.iter().any(|line| spec.advance(fonts, line, size) > wrap_width) {
            height = i64::from(box_height) + 1;
        }
        if height <= i64::from(box_height) || best <= floor {
            return (best, lines);
        }
        best = floor.max((best - 1).min((best as f32 * 0.98) as i32));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::bundled_fonts_dir;

    #[test]
    fn python_splitlines() {
        assert_eq!(splitlines("a\nb\r\nc\rd\u{2028}e\n"), ["a", "b", "c", "d", "e"]);
        assert_eq!(splitlines("\nAMEN"), ["", "AMEN"]);
        assert!(splitlines("").is_empty());
    }

    #[test]
    fn verses_and_balance() {
        let dir = bundled_fonts_dir();
        let mut fonts = Fonts::from_files(&[dir.join("Passion One/PassionOne-Bold.ttf")]);
        let spec = FontSpec { family: "Passion One", weight: 700, letter_spacing: 0.0 };
        // Un mot plus large que la zone fait baisser la taille jusqu'au plancher.
        let (size, _) = fit_text_size(&mut fonts, "ANTICONSTITUTIONNELLEMENT", spec, 300.0, 800, 180, 18, 1.18);
        assert!(size < 180);
        assert!(spec.advance(&mut fonts, "ANTICONSTITUTIONNELLEMENT", size as f32) <= 300.0 || size == 18);
        let text = "UN DEUX TROIS QUATRE CINQ SIX SEPT HUIT NEUF DIX ONZE";
        let lines = balanced_lines(&mut fonts, text, spec, 100.0, 900.0);
        let widths: Vec<f32> = lines.iter().map(|l| spec.advance(&mut fonts, l, 100.0)).collect();
        let (min, max) = widths.iter().fold((f32::MAX, 0.0f32), |(a, b), &w| (a.min(w), b.max(w)));
        assert!(lines.len() >= 2 && max - min < max * 0.4, "{lines:?}");
    }
}
