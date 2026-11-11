//! Le programme : ce que l'opérateur prépare dans l'Aperçu, puis envoie au direct.
//!
//! Un clic dans une bibliothèque prépare un **programme** entier : tout le sermon, tout le chapitre
//! de la Bible, tout le cantique, tout le chapitre de l'Exposé, à partir de l'entrée cliquée. Chaque
//! entrée (référence, texte) devient un ou plusieurs slides : les textes longs sont découpés en
//! parties « réf (i/n) », que les touches suivant / précédent parcourent pendant la projection.
//!
//! C'est la logique de la 2.8 (`ProjectOnController.build_slides`, `presentation_slide`, et les
//! entrées préparées par `LibraryController`), vérifiée contre elle par `po-parite programme`.

use po_db::{Book, Paragraph, Stanza, Verse};
use po_design::SlideSource;
use po_layout::Slide;
use po_settings::SplitSettings;
use po_text::{
    MIN_CHARS_PER_SLIDE, clean_text, split_hymn_stanza, split_text_into_slides, strip_hymn_projection_label,
};

/// Une entrée d'un programme : un verset, une strophe, un paragraphe.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Entry {
    pub reference: String,
    pub text: String,
}

impl Entry {
    pub fn new(reference: impl Into<String>, text: impl Into<String>) -> Self {
        Entry { reference: reference.into(), text: text.into() }
    }
}

/// Un programme préparé (l'Aperçu), pas encore projeté. Tout ce qu'il faut pour le projeter est
/// pris au moment du clic : l'envoyer au direct plus tard projette exactement ce qui a été préparé,
/// quoi que montre alors la bibliothèque.
#[derive(Debug, Clone, PartialEq)]
pub struct Cue {
    pub source: SlideSource,
    pub title: String,
    pub entries: Vec<Entry>,
    /// L'entrée cliquée : le programme commence là.
    pub focus: usize,
    /// Découper les textes longs (toujours, sauf cas particuliers).
    pub split: bool,
    /// Le genre de chaque entrée, quand il diffère d'une entrée à l'autre (une playlist) : il
    /// décide de l'identification et du filet ; le découpage, lui, suit `source`. Vide : `source`.
    pub kinds: Vec<SlideSource>,
}

impl Cue {
    pub fn new(source: SlideSource, title: impl Into<String>, entries: Vec<Entry>, focus: usize) -> Self {
        Cue { source, title: title.into(), entries, focus, split: true, kinds: Vec::new() }
    }
}

/// Un slide d'un programme, tel que stocké (avant sa présentation à l'écran).
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct ProgramSlide {
    pub reference: String,
    pub text: String,
    /// L'entrée d'où il vient.
    pub entry: usize,
}

/// `_clean_chunk` : chaque ligne nettoyée, les lignes vides retirées.
fn clean_chunk(value: &str) -> String {
    value.split('\n').map(clean_text).filter(|l| !l.is_empty()).collect::<Vec<_>>().join("\n")
}

fn to_usize(v: i64) -> usize {
    usize::try_from(v).unwrap_or(0)
}

/// `_split_entry` : les parties d'une entrée selon sa source et les réglages de découpage. Le texte
/// est nettoyé (les retours à la ligne restent : alinéas, vers), puis découpé.
fn split_entry(source: &SlideSource, text: &str, split: &SplitSettings) -> Vec<String> {
    let mut cleaned = clean_text(text);
    if *source == SlideSource::Hymn {
        cleaned = strip_hymn_projection_label(&cleaned);
        if cleaned.is_empty() {
            return Vec::new();
        }
        if !split.hymn_enabled {
            return vec![cleaned];
        }
        return split_hymn_stanza(
            &cleaned,
            to_usize(split.hymn_max_lines),
            to_usize(split.max_chars.max(120)),
            split.hymn_keep_couplets,
        );
    }
    if cleaned.is_empty() {
        return Vec::new();
    }
    if !split.text_enabled {
        return vec![cleaned];
    }
    split_text_into_slides(&cleaned, to_usize(split.max_chars), MIN_CHARS_PER_SLIDE, split.keep_line_breaks)
}

/// `build_slides` : les slides d'un programme et le premier slide de chaque entrée (`None` quand
/// une entrée n'en donne aucun).
pub fn build_slides(
    source: &SlideSource,
    entries: &[Entry],
    split_long: bool,
    split: &SplitSettings,
) -> (Vec<ProgramSlide>, Vec<Option<usize>>) {
    let mut slides = Vec::new();
    let mut starts = Vec::with_capacity(entries.len());
    for (index, entry) in entries.iter().enumerate() {
        let reference = clean_text(&entry.reference);
        let mut text = clean_text(&entry.text);
        if *source == SlideSource::Hymn {
            text = strip_hymn_projection_label(&text);
        }
        let chunks = if split_long {
            split_entry(source, &entry.text, split)
        } else if text.is_empty() {
            Vec::new()
        } else {
            vec![text]
        };
        let total = chunks.len();
        let mut start = None;
        for (i, chunk) in chunks.iter().enumerate() {
            let chunk = clean_chunk(chunk);
            if chunk.is_empty() {
                continue;
            }
            let reference = if total > 1 && split.show_part_counter {
                format!("{reference} ({}/{total})", i + 1)
            } else {
                reference.clone()
            };
            start.get_or_insert(slides.len());
            slides.push(ProgramSlide { reference, text: chunk, entry: index });
        }
        starts.push(start);
    }
    (slides, starts)
}

/// `presentation_slide` : le slide tel que les écrans le montrent. Pour un cantique, le titre passe
/// sur sa propre ligne et l'étiquette de strophe quitte le texte.
pub fn presentation(source: &SlideSource, slide: &ProgramSlide) -> Slide {
    if *source != SlideSource::Hymn {
        return Slide::new(slide.text.clone(), slide.reference.clone(), source.clone());
    }
    let reference = slide.reference.replacen(" - ", "\n", 1);
    Slide::new(strip_hymn_projection_label(&slide.text), reference, source.clone())
}

/// Un programme au direct (ou dans l'Aperçu) : ses slides et le slide montré.
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct Program {
    pub source: SlideSource,
    pub title: String,
    pub slides: Vec<ProgramSlide>,
    /// Le premier slide de chaque entrée.
    pub starts: Vec<Option<usize>>,
    /// Le genre de chaque entrée (vide : `source`).
    pub kinds: Vec<SlideSource>,
    current: usize,
}

impl Program {
    /// Le programme d'un `Cue`, placé sur la première partie de l'entrée cliquée. `None` si rien
    /// n'est projetable (entrées vides).
    pub fn from_cue(cue: &Cue, split: &SplitSettings) -> Option<Program> {
        let (slides, starts) = build_slides(&cue.source, &cue.entries, cue.split, split);
        if slides.is_empty() {
            return None;
        }
        let current = starts.get(cue.focus).copied().flatten().or_else(|| starts.iter().flatten().next().copied())?;
        Some(Program {
            source: cue.source.clone(),
            title: clean_text(&cue.title),
            slides,
            starts,
            kinds: cue.kinds.clone(),
            current,
        })
    }

    pub fn len(&self) -> usize {
        self.slides.len()
    }

    pub fn is_empty(&self) -> bool {
        self.slides.is_empty()
    }

    /// Le rang du slide montré.
    pub fn current(&self) -> usize {
        self.current
    }

    /// Le slide montré, tel que les écrans le dessinent.
    pub fn slide(&self) -> Slide {
        self.slide_at(self.current).unwrap_or_else(|| Slide::new("", "", self.source.clone()))
    }

    pub fn slide_at(&self, row: usize) -> Option<Slide> {
        self.slides.get(row).map(|s| {
            let mut slide = presentation(&self.source, s);
            if let Some(kind) = self.kinds.get(s.entry) {
                slide.source = kind.clone();
            }
            slide
        })
    }

    /// L'entrée du slide montré (le paragraphe, le verset…), pour la suivre dans la bibliothèque.
    pub fn current_entry(&self) -> usize {
        self.slides.get(self.current).map_or(0, |s| s.entry)
    }

    /// Va au rang `row` (borné). Vrai si le slide montré change.
    pub fn set(&mut self, row: usize) -> bool {
        let row = row.min(self.slides.len().saturating_sub(1));
        let changed = row != self.current;
        self.current = row;
        changed
    }

    /// Slide suivant ; rien au dernier. Vrai si le slide change.
    pub fn next_slide(&mut self) -> bool {
        self.current + 1 < self.slides.len() && self.set(self.current + 1)
    }

    /// Slide précédent ; rien au premier. Vrai si le slide change.
    pub fn prev_slide(&mut self) -> bool {
        self.current > 0 && self.set(self.current - 1)
    }

    /// Premier ou dernier slide (Début / Fin).
    pub fn edge(&mut self, to_start: bool) -> bool {
        self.set(if to_start { 0 } else { self.slides.len().saturating_sub(1) })
    }
}

// ── Les entrées préparées par chaque bibliothèque ───────────────────────────────────────────────

/// « date - titre - repère », sans les morceaux vides (`_format_sermon_reference`).
pub fn sermon_reference(date: &str, title: &str, marker: &str) -> String {
    [date.trim(), title.trim(), marker.trim()].into_iter().filter(|p| !p.is_empty()).collect::<Vec<_>>().join(" - ")
}

/// « numéro - titre - étiquette » (`_format_hymn_reference`).
pub fn hymn_reference(number: &str, title: &str, label: &str) -> String {
    sermon_reference(number, title, label)
}

/// Le titre d'un programme : la référence sans repère, sans tiret au bout.
pub fn program_title(date: &str, title: &str) -> String {
    sermon_reference(date, title, "").trim_matches(|c| c == ' ' || c == '-').to_string()
}

/// Les entrées d'un sermon : un paragraphe par entrée, les alinéas d'un même paragraphe numéroté
/// (même référence) réunis, un alinéa par ligne (`_prepare_sermon_entries` + `_group_alineas`).
pub fn sermon_entries(paragraphs: &[Paragraph], date: &str, title: &str) -> Vec<Entry> {
    let mut out: Vec<Entry> = Vec::new();
    for p in paragraphs {
        // `str(marker or f"¶{no}").strip()` : un repère fait d'espaces reste vide.
        let marker = if p.marker.is_empty() { format!("¶{}", p.paragraph_no) } else { p.marker.trim().to_string() };
        let reference = sermon_reference(date, title, &marker);
        let text = clean_text(&p.text);
        match out.last_mut() {
            Some(last) if last.reference == reference => {
                last.text = format!("{}\n{text}", last.text);
            }
            _ => out.push(Entry { reference, text }),
        }
    }
    out
}

/// Les entrées d'un chapitre de la Bible : « Livre chapitre:verset ».
pub fn bible_entries(verses: &[Verse], book: &str, chapter: i64) -> Vec<Entry> {
    verses
        .iter()
        .map(|v| Entry {
            reference: format!("{book} {chapter}:{}", v.verse).trim().to_string(),
            text: clean_text(&v.text),
        })
        .collect()
}

/// Le titre d'un programme biblique : « Livre chapitre ».
pub fn bible_title(book: &str, chapter: i64) -> String {
    format!("{book} {chapter}").trim().to_string()
}

/// Une strophe préparée : sa référence et si c'est un refrain.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PreparedStanza {
    pub reference: String,
    pub label: String,
    pub is_chorus: bool,
    pub text: String,
}

/// Les strophes d'un cantique avec leur étiquette (« Strophe 2 », « Refrain ») quand la base n'en
/// donne pas (`_prepare_hymn_stanzas`).
pub fn prepare_stanzas(stanzas: &[Stanza], number: &str, title: &str) -> Vec<PreparedStanza> {
    let (mut verse_no, mut chorus_no) = (0, 0);
    stanzas
        .iter()
        .map(|s| {
            let mut label = s.label.clone();
            if s.is_chorus {
                chorus_no += 1;
            } else {
                verse_no += 1;
            }
            if label.is_empty() {
                label = if s.is_chorus {
                    if chorus_no == 1 { "Refrain".into() } else { format!("Refrain {chorus_no}") }
                } else {
                    format!("Strophe {verse_no}")
                };
            }
            PreparedStanza {
                reference: hymn_reference(number, title, &label),
                label,
                is_chorus: s.is_chorus,
                text: s.text.clone(),
            }
        })
        .collect()
}

/// Le refrain répété après chaque strophe (`expand_hymn_chorus`) : seulement pour un cantique au
/// refrain unique écrit une seule fois, avec au moins deux strophes. Un refrain placé avant la
/// première strophe ouvre aussi le chant.
pub fn expand_chorus(prepared: &[PreparedStanza]) -> Vec<PreparedStanza> {
    let choruses: Vec<usize> = prepared.iter().enumerate().filter(|(_, p)| p.is_chorus).map(|(i, _)| i).collect();
    let verses: Vec<&PreparedStanza> = prepared.iter().filter(|p| !p.is_chorus).collect();
    if choruses.len() != 1 || verses.len() < 2 {
        return prepared.to_vec();
    }
    let chorus = &prepared[choruses[0]];
    let mut out = Vec::new();
    if choruses[0] == 0 {
        out.push(chorus.clone());
    }
    for verse in verses {
        out.push(verse.clone());
        out.push(chorus.clone());
    }
    out
}

/// Les entrées projetées d'un cantique (`_hymn_program_entries`).
pub fn hymn_entries(prepared: &[PreparedStanza], repeat_chorus: bool) -> Vec<Entry> {
    let list = if repeat_chorus { expand_chorus(prepared) } else { prepared.to_vec() };
    list.iter().map(|p| Entry { reference: p.reference.clone(), text: clean_text(&p.text) }).collect()
}

/// Le titre d'un ouvrage en tête de la référence projetée (`_expose_book_prefix`).
pub fn book_prefix(book: Option<&Book>) -> String {
    match book {
        None => "Exposé des Sept Âges".into(),
        Some(b) => match b.key.as_str() {
            "ages-vgr" => "Exposé des Sept Âges".into(),
            "ages-shp" => "Exposé SHP".into(),
            "brochures" => String::new(),
            _ => b.title.clone(),
        },
    }
}

/// « ouvrage — chapitre » (une brochure : son titre seul) (`_expose_full_reference`).
pub fn book_reference(book: Option<&Book>, chapter_title: &str) -> String {
    let prefix = book_prefix(book);
    let chapter = chapter_title.trim();
    if !prefix.is_empty() && !chapter.is_empty() {
        format!("{prefix} — {chapter}")
    } else if chapter.is_empty() {
        prefix
    } else {
        chapter.to_string()
    }
}

/// Les entrées d'un chapitre d'ouvrage : « ouvrage — chapitre · Page p §n » quand la référence de
/// la source donne la page et le paragraphe (« ¶ » serait retiré par le nettoyage : « § »).
pub fn book_entries(paragraphs: &[Paragraph], full_reference: &str) -> Vec<Entry> {
    paragraphs
        .iter()
        .map(|p| {
            let raw = p.raw_ref.as_deref().unwrap_or("");
            let reference = match page_and_paragraph(raw) {
                Some((page, n)) => format!("{full_reference} · Page {page} §{n}"),
                None => full_reference.to_string(),
            };
            Entry { reference, text: clean_text(&p.text) }
        })
        .collect()
}

/// `re.search(r"(\d+)-(\d+)", raw_ref)`.
fn page_and_paragraph(raw: &str) -> Option<(String, String)> {
    static PATTERN: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    let re = PATTERN.get_or_init(|| regex::Regex::new(r"(\d+)-(\d+)").unwrap_or_else(|_| unreachable!()));
    let c = re.captures(raw)?;
    Some((c[1].to_string(), c[2].to_string()))
}

/// L'entrée correspondant à la référence cliquée ; à défaut, au repère seul (dernier morceau après
/// « - »), puis la première (`_find_entry_index`).
pub fn find_entry(entries: &[Entry], reference: &str) -> usize {
    if let Some(i) = entries.iter().position(|e| e.reference == reference) {
        return i;
    }
    let marker = |r: &str| r.rsplit(" - ").next().unwrap_or("").trim().to_string();
    let wanted = marker(reference);
    entries.iter().position(|e| marker(&e.reference) == wanted).unwrap_or(0)
}

#[cfg(test)]
mod tests;
