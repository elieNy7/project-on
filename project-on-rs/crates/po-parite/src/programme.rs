//! La phase 3 : le programme (entrées préparées par les bibliothèques, découpage en slides, slide
//! montré) comparé à la 2.8, qui a écrit `programme.json` (`outils/references_programme_28.py`).
//!
//! Les entrées sont refaites par la 3.0 depuis la base ; les slides sont refaits depuis les entrées
//! de la 2.8 (pour qu'une différence d'entrée ne masque pas une différence de découpage).

use std::collections::BTreeMap;
use std::path::Path;

use anyhow::{Context, Result};
use po_db::{Database, Mode};
use po_design::SlideSource;
use po_program::{Entry, build_slides, presentation};
use po_settings::Settings;
use serde::Deserialize;
use serde_json::{Map, Value, json};

use crate::compare::Section;

#[derive(Deserialize)]
struct References {
    reglages: BTreeMap<String, Map<String, Value>>,
    cas: Vec<Case>,
}

#[derive(Deserialize)]
struct Programme {
    entrees: Vec<(String, String)>,
    slides: Vec<(String, String)>,
    starts: Vec<Option<usize>>,
    ecran: Vec<(String, String)>,
}

#[derive(Deserialize)]
struct Case {
    genre: String,
    /// Un entier, ou « int_6183 » pour les sermons de la 2.8.
    #[serde(default, deserialize_with = "id_of")]
    id: i64,
    #[serde(default)]
    date: String,
    #[serde(default)]
    titre: String,
    #[serde(default)]
    numero: String,
    #[serde(default)]
    titre_programme: String,
    #[serde(default)]
    clic: String,
    #[serde(default)]
    focus: usize,
    #[serde(default, deserialize_with = "id_of")]
    traduction: i64,
    #[serde(default, deserialize_with = "id_of")]
    livre: i64,
    #[serde(default, deserialize_with = "id_of")]
    chapitre: i64,
    #[serde(default)]
    cle: String,
    #[serde(default)]
    reference: String,
    programmes: BTreeMap<String, Programme>,
}

fn id_of<'de, D: serde::Deserializer<'de>>(d: D) -> Result<i64, D::Error> {
    Ok(match Value::deserialize(d)? {
        Value::Number(n) => n.as_i64().unwrap_or(0),
        Value::String(s) => s.trim_start_matches("int_").parse().unwrap_or(0),
        _ => 0,
    })
}

fn pairs(entries: &[Entry]) -> Value {
    json!(entries.iter().map(|e| [e.reference.as_str(), e.text.as_str()]).collect::<Vec<_>>())
}

fn expected_pairs(list: &[(String, String)]) -> Value {
    json!(list.iter().map(|(r, t)| [r.as_str(), t.as_str()]).collect::<Vec<_>>())
}

fn label(case: &Case) -> String {
    match case.genre.as_str() {
        "sermon" => format!("sermon {} {}", case.id, case.date),
        "hymn" => format!("cantique {} n° {}", case.id, case.numero),
        "bible" => format!("bible {}/{}/{}", case.traduction, case.livre, case.chapitre),
        _ => format!("livre {} chapitre {}", case.cle, case.chapitre),
    }
}

/// Les entrées de la 3.0 pour un cas et un réglage.
fn entries(db: &Database, case: &Case, split: &po_settings::SplitSettings) -> Result<Vec<Entry>> {
    Ok(match case.genre.as_str() {
        "sermon" => po_program::sermon_entries(&db.paragraphs(case.id)?, &case.date, &case.titre),
        "hymn" => {
            let hymn = db.hymn(case.id)?.context("cantique introuvable")?;
            let prepared =
                po_program::prepare_stanzas(&db.stanzas(case.id)?, hymn.number.as_deref().unwrap_or(""), &hymn.title);
            po_program::hymn_entries(&prepared, split.hymn_repeat_chorus)
        }
        "bible" => {
            let name = db
                .list_translation_books(case.traduction)?
                .into_iter()
                .find(|b| b.id == case.livre)
                .map(|b| b.name)
                .unwrap_or_default();
            let verses = db.list_translation_verses(case.traduction, case.livre, case.chapitre)?;
            po_program::bible_entries(&verses, &name, case.chapitre)
        }
        _ => {
            let full = book_reference(db, case)?;
            let mut rows = Vec::new();
            for page in db.list_expose_pages(case.chapitre)? {
                rows.extend(db.list_expose_page_paragraphs(case.chapitre, page)?);
            }
            po_program::book_entries(&rows, &full)
        }
    })
}

fn book_reference(db: &Database, case: &Case) -> Result<String> {
    let title = db
        .list_book_chapters(&case.cle)?
        .into_iter()
        .find(|c| c.id == case.chapitre)
        .map(|c| c.title)
        .unwrap_or_default();
    Ok(po_program::book_reference(db.book_of_chapter(case.chapitre)?.as_ref(), &title))
}

fn source(genre: &str) -> SlideSource {
    match genre {
        "hymn" => SlideSource::Hymn,
        "bible" => SlideSource::Bible,
        _ => SlideSource::Sermon,
    }
}

/// Compare tout ; vrai si aucune différence.
pub fn compare(dir: &Path, db_path: &Path) -> Result<bool> {
    let text = std::fs::read_to_string(dir.join("programme.json")).context("lecture de programme.json")?;
    let refs: References = serde_json::from_str(&text)?;
    drop(text);
    let db = Database::open(db_path, Mode::ReadOnly)?;
    let mut section = Section::new("programme");
    let mut by_kind: BTreeMap<String, (usize, usize)> = BTreeMap::new();
    for case in &refs.cas {
        let label = label(case);
        let before = section.failures;
        // Ce que la 3.0 ajoute autour des entrées : titre du programme, entrée cliquée, référence d'ouvrage.
        match case.genre.as_str() {
            "sermon" => {
                section.check(
                    "titre du programme",
                    &label,
                    &json!(case.titre_programme),
                    &json!(po_program::program_title(&case.date, &case.titre)),
                );
                let ours = po_program::sermon_entries(&db.paragraphs(case.id)?, &case.date, &case.titre);
                section.check(
                    "entrée cliquée",
                    &label,
                    &json!(case.focus),
                    &json!(po_program::find_entry(&ours, &case.clic)),
                );
            }
            "hymn" => {
                let hymn = db.hymn(case.id)?.context("cantique introuvable")?;
                let title = po_program::program_title(hymn.number.as_deref().unwrap_or(""), &hymn.title);
                section.check("titre du programme", &label, &json!(case.titre_programme), &json!(title));
            }
            "livre" => {
                section.check(
                    "référence d'ouvrage",
                    &label,
                    &json!(case.reference),
                    &json!(book_reference(&db, case)?),
                );
            }
            _ => {}
        }
        for (variant, expected) in &case.programmes {
            let payload = refs.reglages.get(variant).cloned().unwrap_or_default();
            let mut settings = Map::new();
            settings.insert("split".into(), Value::Object(payload));
            let split = Settings::from_payload(&settings).split;
            let label = format!("{label} [{variant}]");
            let ours = entries(&db, case, &split)?;
            section.check("entrées", &label, &expected_pairs(&expected.entrees), &pairs(&ours));
            // Les slides, depuis les entrées de la 2.8.
            let theirs: Vec<Entry> = expected.entrees.iter().map(|(r, t)| Entry::new(r, t)).collect();
            let source = source(&case.genre);
            let (slides, starts) = build_slides(&source, &theirs, true, &split);
            let slide_pairs = json!(slides.iter().map(|s| [s.reference.as_str(), s.text.as_str()]).collect::<Vec<_>>());
            section.check("slides", &label, &expected_pairs(&expected.slides), &slide_pairs);
            section.check("premier slide de chaque entrée", &label, &json!(expected.starts), &json!(starts));
            let shown: Vec<[String; 2]> = slides
                .iter()
                .map(|s| {
                    let slide = presentation(&source, s);
                    [slide.reference, slide.text]
                })
                .collect();
            section.check("slide à l'écran", &label, &expected_pairs(&expected.ecran), &json!(shown));
        }
        let entry = by_kind.entry(case.genre.clone()).or_default();
        entry.0 += 1;
        entry.1 += usize::from(section.failures > before);
    }
    println!("{}", section.summary());
    for (kind, (n, failed)) in &by_kind {
        println!("  {kind:8} {n:4} programmes, {failed} avec une différence");
    }
    let slides: usize = refs.cas.iter().flat_map(|c| c.programmes.values()).map(|p| p.slides.len()).sum();
    println!("{} programmes, {slides} slides comparés : {} différence(s).", refs.cas.len(), section.failures);
    let report = json!({
        "programmes": refs.cas.len(),
        "slides": slides,
        "comparaisons": section.cases,
        "differences": section.failures,
        "par_genre": by_kind.iter().map(|(k, (n, f))| (k.clone(), json!({"programmes": n, "avec_difference": f}))).collect::<Map<_, _>>(),
        "reglages": refs.reglages.keys().collect::<Vec<_>>(),
    });
    std::fs::write(dir.join("programme-rapport.json"), serde_json::to_string_pretty(&report)?)?;
    std::fs::write(dir.join("programme-details.json"), serde_json::to_string_pretty(&section.to_json())?)?;
    Ok(section.failures == 0)
}
