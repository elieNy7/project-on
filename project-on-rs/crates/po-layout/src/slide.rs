//! La mise en page d'un slide de texte : le texte remplit l'écran.
//!
//! Même règle que la projection de la 2.8 (`SlideCanvas._fit_text_size`) : la plus grande taille,
//! jusqu'à `fill_ceiling` fois la taille réglée, où le texte découpé tient entièrement dans la zone
//! de sécurité ; au pire le plancher de lisibilité, sans jamais couper un mot. Les lignes sont
//! ensuite équilibrées (pas de mot seul sur la dernière ligne) et la référence est épinglée en haut
//! ou en bas de l'écran, un peu éloignée du texte.

use crate::display::{Anchor, DisplayList, Item, Rgba, TextLine};
use crate::fonts::{Fonts, VerticalMetrics};

/// Où se place la référence.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ReferencePosition {
    Top,
    Bottom,
}

/// Le style d'un slide de salle (les réglages « Projection » de la 2.x).
#[derive(Debug, Clone, PartialEq)]
pub struct SlideStyle {
    pub family: String,
    pub weight: u16,
    pub uppercase: bool,
    /// La taille réglée, en pixels pour un écran de 1080 lignes.
    pub text_size: f32,
    /// Jusqu'où un texte court peut grandir (× la taille réglée).
    pub fill_ceiling: f32,
    /// Le plancher de lisibilité, en pixels pour 1080 lignes.
    pub min_size: f32,
    pub line_height: f32,
    pub text_color: Rgba,
    pub reference_family: String,
    pub reference_weight: u16,
    pub reference_size: f32,
    pub reference_color: Rgba,
    pub reference_position: ReferencePosition,
    /// La marge de sécurité sur chaque bord, en fraction de l'écran.
    pub safe_area: f32,
    pub background: Rgba,
}

impl Default for SlideStyle {
    /// Les réglages de projection de la 2.8 chez l'utilisateur (presentation/config.json).
    fn default() -> Self {
        SlideStyle {
            family: "Passion One".into(),
            weight: 700,
            uppercase: true,
            text_size: 45.0,
            fill_ceiling: 4.0,
            min_size: 18.0,
            line_height: 1.18,
            text_color: Rgba::new(255, 255, 255, 235),
            reference_family: "Passion One".into(),
            reference_weight: 700,
            reference_size: 33.0,
            reference_color: Rgba::new(255, 255, 255, 199),
            reference_position: ReferencePosition::Top,
            safe_area: 0.05,
            background: Rgba::rgb(0x0c, 0x0f, 0x14),
        }
    }
}

/// Le contenu d'un slide.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct SlideContent {
    pub text: String,
    pub reference: String,
}

/// La taille de référence à laquelle les mots sont mesurés une seule fois.
const MEASURE_SIZE: f32 = 100.0;
/// Réserve de hauteur (le rendu réel peut dépasser légèrement l'interligne théorique), comme la 2.x.
const HEIGHT_RESERVE: f32 = 1.08;

/// Un mot et sa largeur à `MEASURE_SIZE`.
struct Word {
    text: String,
    width: f32,
}

/// Les mots d'un paragraphe mesurés en une seule mise en forme.
struct Paragraph {
    words: Vec<Word>,
    space: f32,
}

fn measure_paragraph(fonts: &mut Fonts, paragraph: &str, family: &str, weight: u16) -> Paragraph {
    let words = po_text::words(paragraph);
    let mut joined = String::new();
    let mut ranges = Vec::with_capacity(words.len());
    for word in &words {
        if !joined.is_empty() {
            joined.push(' ');
        }
        let start = joined.len();
        joined.push_str(word);
        ranges.push(start..joined.len());
    }
    let mut widths = vec![0.0f32; words.len()];
    let mut spaces = (0.0f32, 0u32);
    let buffer = fonts.line(&joined, family, weight, MEASURE_SIZE);
    for run in buffer.layout_runs() {
        for glyph in run.glyphs {
            match ranges.iter().position(|r| r.contains(&glyph.start)) {
                Some(i) => widths[i] += glyph.w,
                None => {
                    spaces.0 += glyph.w;
                    spaces.1 += 1;
                }
            }
        }
    }
    let space = if spaces.1 > 0 { spaces.0 / spaces.1 as f32 } else { MEASURE_SIZE * 0.25 };
    Paragraph { words: words.into_iter().zip(widths).map(|(text, width)| Word { text, width }).collect(), space }
}

/// Découpe gloutonne d'un paragraphe à la taille `size` : les indices de début de chaque ligne.
/// `None` si un mot seul dépasse la largeur.
fn greedy_breaks(paragraph: &Paragraph, size: f32, limit: f32) -> Option<Vec<usize>> {
    let k = size / MEASURE_SIZE;
    let mut starts = Vec::new();
    let mut current = -1.0f32;
    for (i, word) in paragraph.words.iter().enumerate() {
        let width = word.width * k;
        if width > limit {
            return None;
        }
        if current < 0.0 {
            starts.push(i);
            current = width;
        } else if current + paragraph.space * k + width <= limit {
            current += paragraph.space * k + width;
        } else {
            starts.push(i);
            current = width;
        }
    }
    if starts.is_empty() {
        starts.push(0);
    }
    Some(starts)
}

/// Répartit les mots sur `count` lignes de largeur ≤ `limit`, les plus égales possible (écarts à la
/// largeur moyenne au carré) — `SlideCanvas._even_split`. `None` si c'est impossible.
fn even_split(paragraph: &Paragraph, size: f32, limit: f32, count: usize) -> Option<Vec<usize>> {
    let k = size / MEASURE_SIZE;
    let n = paragraph.words.len();
    if count == 0 || count > n {
        return None;
    }
    let mut prefix = vec![0.0f64; n + 1];
    for (i, word) in paragraph.words.iter().enumerate() {
        prefix[i + 1] = prefix[i] + f64::from(word.width * k);
    }
    let space = f64::from(paragraph.space * k);
    let line_width = |i: usize, j: usize| prefix[j] - prefix[i] + space * (j - i - 1) as f64;
    let target = line_width(0, n) / count as f64;
    let limit = f64::from(limit);
    let mut best = vec![vec![f64::INFINITY; n + 1]; count + 1];
    let mut cut = vec![vec![0usize; n + 1]; count + 1];
    best[0][0] = 0.0;
    for lines in 1..=count {
        for j in lines..=n {
            for i in (lines - 1..j).rev() {
                let w = line_width(i, j);
                if w > limit {
                    break; // plus de mots ne ferait qu'élargir la ligne
                }
                let cost = best[lines - 1][i] + (w - target).powi(2);
                if cost < best[lines][j] {
                    best[lines][j] = cost;
                    cut[lines][j] = i;
                }
            }
        }
    }
    if best[count][n].is_infinite() {
        return None;
    }
    let mut starts = vec![0usize; count];
    let mut j = n;
    for lines in (1..=count).rev() {
        let i = cut[lines][j];
        starts[lines - 1] = i;
        j = i;
    }
    Some(starts)
}

fn lines_from(paragraph: &Paragraph, starts: &[usize]) -> Vec<String> {
    let n = paragraph.words.len();
    starts
        .iter()
        .enumerate()
        .map(|(idx, &start)| {
            let end = starts.get(idx + 1).copied().unwrap_or(n);
            paragraph.words[start..end].iter().map(|w| w.text.as_str()).collect::<Vec<_>>().join(" ")
        })
        .collect()
}

/// Hauteur estimée du texte à la taille `size` (trop grande si un mot dépasse) : `_scaled_fit`.
fn estimated_height(paragraphs: &[Paragraph], size: f32, limit: f32, v: VerticalMetrics, line_height: f32) -> f32 {
    let mut count = 0usize;
    for paragraph in paragraphs {
        match greedy_breaks(paragraph, size, limit) {
            Some(starts) => count += starts.len(),
            None => return f32::INFINITY,
        }
    }
    let step = v.line_spacing() * size;
    (step + step * line_height * (count.saturating_sub(1)) as f32) * HEIGHT_RESERVE
}

/// Le résultat de l'ajustement : la taille retenue et les lignes.
#[derive(Debug, Clone, PartialEq)]
pub struct Fitted {
    pub size: f32,
    pub lines: Vec<String>,
}

/// La plus grande taille (entière, en pixels) entre `floor` et `ceiling` où le texte tient dans la
/// boîte, et ses lignes équilibrées, vérifiées par une vraie mise en forme.
pub fn fit_text(
    fonts: &mut Fonts,
    text: &str,
    family: &str,
    weight: u16,
    box_w: f32,
    box_h: f32,
    floor: f32,
    ceiling: f32,
    line_height: f32,
) -> Fitted {
    let v = fonts.vertical(family, weight);
    let paragraphs: Vec<Paragraph> =
        text.lines().filter(|p| !p.trim().is_empty()).map(|p| measure_paragraph(fonts, p, family, weight)).collect();
    let floor = floor.min(ceiling).max(1.0).round() as i32;
    let ceiling = ceiling.max(1.0).round() as i32;
    let limit = box_w * 0.99; // marge pour l'écart estimation / mesure, comme la 2.x
    let (mut lo, mut hi, mut best) = (floor, ceiling, floor);
    while lo <= hi {
        let mid = (lo + hi) / 2;
        if estimated_height(&paragraphs, mid as f32, limit, v, line_height) <= box_h {
            best = mid;
            lo = mid + 1;
        } else {
            hi = mid - 1;
        }
    }
    // Vérification avec la vraie mise en forme ; au moindre dépassement, on descend un peu.
    let mut size = best;
    loop {
        let s = size as f32;
        let mut lines = Vec::new();
        for paragraph in &paragraphs {
            let greedy = greedy_breaks(paragraph, s, limit).unwrap_or_else(|| (0..paragraph.words.len()).collect());
            let greedy_lines = lines_from(paragraph, &greedy);
            let balanced = if greedy.len() >= 2 {
                even_split(paragraph, s, limit, greedy.len()).map(|starts| lines_from(paragraph, &starts))
            } else {
                None
            };
            // Les lignes équilibrées seulement si la vraie mesure les confirme.
            match balanced {
                Some(even) if even.iter().all(|line| fonts.width(line, family, weight, s) <= box_w) => {
                    lines.extend(even);
                }
                _ => lines.extend(greedy_lines),
            }
        }
        let widest = lines.iter().map(|line| fonts.width(line, family, weight, s)).fold(0.0, f32::max);
        let step = v.line_spacing() * s;
        let height = (step + step * line_height * lines.len().saturating_sub(1) as f32) * HEIGHT_RESERVE;
        if (widest <= box_w && height <= box_h) || size <= floor {
            return Fitted { size: s, lines };
        }
        size = floor.max((size - 1).min((s * 0.98) as i32));
    }
}

/// Met un slide en page pour un écran de `width` × `height` pixels.
pub fn layout_slide(
    fonts: &mut Fonts,
    content: &SlideContent,
    style: &SlideStyle,
    width: f32,
    height: f32,
) -> DisplayList {
    let scale = height / 1080.0;
    let guard_x = (width * style.safe_area).round();
    let guard_y = (height * style.safe_area).round();
    let inner_w = width - 2.0 * guard_x;
    let mut items = Vec::new();

    // La référence, épinglée en haut ou en bas de la zone de sécurité.
    let mut top = guard_y;
    let mut bottom = height - guard_y;
    let reference = content.reference.trim();
    if !reference.is_empty() {
        let (family, weight) = (style.reference_family.as_str(), style.reference_weight);
        let mut size = style.reference_size * scale;
        let measured = fonts.width(reference, family, weight, size);
        if measured > inner_w {
            size *= inner_w / measured; // une référence longue rétrécit au lieu de déborder
        }
        let v = fonts.vertical(family, weight);
        let line_h = (v.ascent + v.descent) * size;
        let gap = (size * 0.9).max(height * 0.02);
        let baseline = match style.reference_position {
            ReferencePosition::Top => {
                top += line_h + gap;
                guard_y + v.ascent * size
            }
            ReferencePosition::Bottom => {
                bottom -= line_h + gap;
                height - guard_y - v.descent * size
            }
        };
        items.push(Item::Text(TextLine {
            text: reference.to_string(),
            x: width / 2.0,
            baseline,
            anchor: Anchor::Middle,
            size,
            family: family.to_string(),
            weight,
            color: style.reference_color,
            width: fonts.width(reference, family, weight, size),
        }));
    }

    let text = if style.uppercase { content.text.to_uppercase() } else { content.text.clone() };
    if !text.trim().is_empty() {
        let (family, weight) = (style.family.as_str(), style.weight);
        let box_h = (bottom - top).max(1.0);
        let ceiling = style.text_size * scale * style.fill_ceiling;
        let floor = style.min_size * scale;
        let fitted = fit_text(fonts, &text, family, weight, inner_w, box_h, floor, ceiling, style.line_height);
        let v = fonts.vertical(family, weight);
        let step = v.line_spacing() * fitted.size;
        let block_h = step + step * style.line_height * fitted.lines.len().saturating_sub(1) as f32;
        let first_top = top + (box_h - block_h) / 2.0;
        for (i, line) in fitted.lines.iter().enumerate() {
            let baseline = first_top + v.ascent * fitted.size + i as f32 * step * style.line_height;
            items.push(Item::Text(TextLine {
                text: line.clone(),
                x: width / 2.0,
                baseline,
                anchor: Anchor::Middle,
                size: fitted.size,
                family: family.to_string(),
                weight,
                color: style.text_color,
                width: fonts.width(line, family, weight, fitted.size),
            }));
        }
    }

    DisplayList { width, height, background: style.background, items }
}
