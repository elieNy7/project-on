//! Lire un recueil de cantiques en PDF (`hymn_pdf_parser.py` de la 2.8) : les lignes de texte de
//! chaque page dans l'ordre de lecture (pages en deux colonnes comprises), une ligne vide là où le
//! PDF laisse un espace entre deux strophes ; puis les cantiques ([`hymns`]).
//!
//! La 2.8 lisait le PDF avec PyMuPDF ; la 3.0 le lit en Rust (`pdf-extract`), caractère par
//! caractère avec sa position, et reforme les lignes. Les règles de mise en ordre sont celles de la
//! 2.8 (colonnes, en-têtes et numéros de page ignorés, écart entre strophes).

pub mod hymns;

use std::path::Path;

pub use hymns::{PdfHymn, hymns_from_lines};

/// Au-delà, l'import est refusé (la 2.8 : `MAX_PDF_PAGES`) plutôt que de rendre un résultat partiel.
pub const MAX_PAGES: u32 = 800;

/// Une ligne de texte placée : son cadre (origine en haut à gauche, en points) et son texte.
#[derive(Debug, Clone, PartialEq)]
pub struct PlacedLine {
    pub x0: f64,
    pub y0: f64,
    pub x1: f64,
    pub y1: f64,
    pub size: f64,
    pub text: String,
}

/// Une page : sa taille et ses lignes.
#[derive(Debug, Clone, Default)]
pub struct Page {
    pub width: f64,
    pub height: f64,
    pub lines: Vec<PlacedLine>,
}

/// Reforme les lignes à partir des caractères placés.
#[derive(Default)]
struct Collector {
    pages: Vec<Page>,
    flip: f64,
    /// La ligne en cours : début, ligne de base, taille, fin, texte.
    current: Option<(f64, f64, f64, f64, String)>,
}

impl Collector {
    fn close_line(&mut self) {
        if let Some((x0, base, size, end, text)) = self.current.take()
            && let Some(page) = self.pages.last_mut()
            && !text.trim().is_empty()
        {
            // Le cadre d'une ligne comme PyMuPDF le donne pour une police courante (hampes et
            // jambages compris).
            page.lines.push(PlacedLine { x0, y0: base - 0.89 * size, x1: end, y1: base + 0.22 * size, size, text });
        }
    }
}

impl pdf_extract::OutputDev for Collector {
    fn begin_page(
        &mut self,
        _page: u32,
        media: &pdf_extract::MediaBox,
        _art: Option<(f64, f64, f64, f64)>,
    ) -> Result<(), pdf_extract::OutputError> {
        self.close_line();
        self.flip = media.ury;
        self.pages.push(Page { width: media.urx - media.llx, height: media.ury - media.lly, lines: Vec::new() });
        Ok(())
    }

    fn end_page(&mut self) -> Result<(), pdf_extract::OutputError> {
        self.close_line();
        Ok(())
    }

    fn output_character(
        &mut self,
        trm: &pdf_extract::Transform,
        width: f64,
        _spacing: f64,
        font_size: f64,
        text: &str,
    ) -> Result<(), pdf_extract::OutputError> {
        // La taille réelle : la matrice du texte appliquée à un carré de la taille de la police.
        let (sx, sy) = (font_size * (trm.m11 + trm.m21), font_size * (trm.m12 + trm.m22));
        let size = (sx * sy).abs().sqrt().max(1.0);
        let (x, base) = (trm.m31, self.flip - trm.m32);
        let advance = width * size;
        let same_line = self.current.as_ref().is_some_and(|(_, b, s, end, _)| {
            (base - b).abs() < s.max(size) * 0.5 && x > end - s.max(size) * 1.0 && x < end + s.max(size) * 3.0
        });
        if !same_line {
            self.close_line();
        }
        match &mut self.current {
            Some((_, _, s, end, line)) => {
                if x > *end + s.max(size) * 0.1 && !line.ends_with(' ') && text != " " {
                    line.push(' ');
                }
                line.push_str(text);
                *end = (*end).max(x + advance);
                *s = s.max(size);
            }
            None => {
                if text.trim().is_empty() {
                    return Ok(());
                }
                self.current = Some((x, base, size, x + advance, text.to_string()));
            }
        }
        Ok(())
    }

    fn begin_word(&mut self) -> Result<(), pdf_extract::OutputError> {
        Ok(())
    }

    fn end_word(&mut self) -> Result<(), pdf_extract::OutputError> {
        Ok(())
    }

    fn end_line(&mut self) -> Result<(), pdf_extract::OutputError> {
        Ok(())
    }
}

/// Les opérateurs `'` (ligne suivante, puis le texte) et `"` (espacements, ligne suivante, texte),
/// que `pdf-extract` ignore, deviennent leurs équivalents `T*` puis `Tj` : sans cela, les lignes
/// écrites ainsi (des recueils entiers) manquent ou se mélangent.
fn expand_quote_operators(doc: &mut pdf_extract::Document) {
    use pdf_extract::content::{Content, Operation};
    let pages: Vec<pdf_extract::ObjectId> = doc.get_pages().into_values().collect();
    for page in pages {
        let Ok(content) = doc.get_and_decode_page_content(page) else { continue };
        if !content.operations.iter().any(|op| op.operator == "'" || op.operator == "\"") {
            continue;
        }
        let mut operations = Vec::with_capacity(content.operations.len() + 16);
        for op in content.operations {
            match (op.operator.as_str(), op.operands.as_slice()) {
                ("'", [text]) => {
                    operations.push(Operation::new("T*", Vec::new()));
                    operations.push(Operation::new("Tj", vec![text.clone()]));
                }
                ("\"", [word, character, text]) => {
                    operations.push(Operation::new("Tw", vec![word.clone()]));
                    operations.push(Operation::new("Tc", vec![character.clone()]));
                    operations.push(Operation::new("T*", Vec::new()));
                    operations.push(Operation::new("Tj", vec![text.clone()]));
                }
                _ => operations.push(op),
            }
        }
        if let Ok(bytes) = (Content { operations }).encode() {
            let _ = doc.change_page_content(page, bytes);
        }
    }
}

/// Les pages d'un PDF et leurs lignes placées.
pub fn pages(path: &Path) -> Result<Vec<Page>, String> {
    let mut doc = pdf_extract::Document::load(path).map_err(|e| format!("PDF illisible : {e}"))?;
    if doc.is_encrypted() {
        return Err("PDF protégé par un mot de passe".into());
    }
    expand_quote_operators(&mut doc);
    let count = doc.get_pages().len() as u32;
    if count > MAX_PAGES {
        return Err(format!("PDF trop grand : {count} pages (au plus {MAX_PAGES})"));
    }
    let mut collector = Collector::default();
    // Une page qui ne se lit pas n'arrête pas tout : elle reste vide (et se voit au bilan).
    for number in 1..=count {
        let before = collector.pages.len();
        if pdf_extract::output_doc_page(&doc, &mut collector, number).is_err() {
            collector.close_line();
            if collector.pages.len() == before {
                collector.pages.push(Page::default());
            }
        }
    }
    collector.close_line();
    Ok(collector.pages)
}

/// Les lignes d'une colonne, de haut en bas, une ligne vide pour un écart (`lines_to_text_lines`).
///
/// La 2.8 voyait un écart quand le haut d'une ligne descend de plus de 2 points sous le bas de la
/// précédente, avec les hampes et jambages de la vraie police (PyMuPDF). Ici, la hauteur d'une
/// ligne est l'interligne le plus courant de la colonne : un écart, c'est 2 points de plus.
fn column_lines(mut lines: Vec<&PlacedLine>) -> Vec<String> {
    lines.sort_by(|a, b| a.y0.total_cmp(&b.y0).then(a.x0.total_cmp(&b.x0)));
    let base = |l: &PlacedLine| l.y1 - 0.22 * l.size;
    // L'interligne le plus courant (au quart de point près), entre lignes de même taille.
    let mut counts: std::collections::HashMap<i64, usize> = std::collections::HashMap::new();
    for pair in lines.windows(2) {
        let (a, b) = (pair[0], pair[1]);
        let delta = base(b) - base(a);
        if (a.size - b.size).abs() < 0.5 && delta > a.size * 0.5 && delta < a.size * 3.0 {
            *counts.entry((delta * 4.0).round() as i64).or_default() += 1;
        }
    }
    let pitch = counts.into_iter().max_by_key(|(d, n)| (*n, -*d)).map(|(d, _)| d as f64 / 4.0);
    let mut out: Vec<String> = Vec::new();
    let mut previous: Option<&PlacedLine> = None;
    for line in lines {
        if let Some(p) = previous {
            let normal = pitch.unwrap_or(p.size * 1.2).max(p.size * 0.9);
            let gap = (base(line) - base(p)) - normal;
            if gap > 2.0 && out.last().is_some_and(|l| !l.is_empty()) {
                out.push(String::new());
            }
        }
        out.push(line.text.clone());
        previous = Some(line);
    }
    out
}

/// Les lignes d'un recueil dans l'ordre de lecture (`ordered_pdf_lines` avec `column_break`).
pub fn ordered_lines(pages: &[Page]) -> Vec<String> {
    let mut all = Vec::new();
    for page in pages {
        let kept: Vec<PlacedLine> = page
            .lines
            .iter()
            .filter_map(|l| {
                let text = hymns::normalize(&l.text);
                if text.is_empty() || hymns::is_header_footer(&text) {
                    return None;
                }
                // Les numéros de page, pas ceux des cantiques.
                let digits = !text.is_empty() && text.len() <= 4 && text.chars().all(|c| c.is_ascii_digit());
                if digits && (l.y0 > page.height * 0.92 || l.size >= 18.0 || l.x0 > page.width * 0.85) {
                    return None;
                }
                Some(PlacedLine { text, ..l.clone() })
            })
            .collect();
        let mid = page.width / 2.0;
        let (left, right): (Vec<&PlacedLine>, Vec<&PlacedLine>) = kept.iter().partition(|l| (l.x0 + l.x1) / 2.0 < mid);
        if left.len() >= 6 && right.len() >= 6 {
            let (l, r) = (column_lines(left), column_lines(right));
            let both = !l.is_empty() && !r.is_empty();
            all.extend(l);
            if both {
                all.push(String::new());
            }
            all.extend(r);
        } else {
            all.extend(column_lines(kept.iter().collect()));
        }
    }
    all
}

/// Les cantiques d'un recueil PDF.
pub fn hymns_from_pdf(path: &Path) -> Result<Vec<PdfHymn>, String> {
    let pages = pages(path)?;
    if pages.iter().all(|p| p.lines.is_empty()) {
        return Err("Aucun texte dans ce PDF (un PDF scanné, en images, ne se lit pas)".into());
    }
    Ok(hymns_from_lines(&ordered_lines(&pages)))
}
