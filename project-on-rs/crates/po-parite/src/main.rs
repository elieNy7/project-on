//! Les tests dorés de la phase 1 : la 3.0 rejoue les références écrites par la 2.8
//! (`outils/references_28.py`) et compare tout, cas par cas.
//!
//! ```text
//! po-parite <dossier des références>       les fondations (phase 1)
//! po-parite projection <dossier>           la mise en page de la projection (phase 2)
//! po-parite comparer <a.db> <b.db>         deux bases
//! ```
//!
//! Sort avec le code 1 à la première différence, après avoir tout comparé ; le détail est dans
//! `rapport.json`, à côté des références.

mod compare;
mod projection;
mod requests;
mod v28;

use std::path::{Path, PathBuf};
use std::time::Instant;

use anyhow::{Context, Result, bail};
use po_db::{Database, InitOptions, Mode};
use serde_json::{Map, Value, json};

use crate::compare::{Section, same};

fn read_json(dir: &Path, name: &str) -> Result<Value> {
    let text = std::fs::read_to_string(dir.join(name)).with_context(|| format!("lecture de {name}"))?;
    Ok(serde_json::from_str(&text)?)
}

fn s(v: &Value) -> &str {
    v.as_str().unwrap_or("")
}

fn n(v: &Value) -> i64 {
    v.as_i64().unwrap_or(0)
}

/// Les fonctions de texte.
fn texts(dir: &Path) -> Result<Section> {
    let refs = read_json(dir, "textes.json")?;
    let mut section = Section::new("textes");
    let Some(functions) = refs.as_object() else { bail!("textes.json : objet attendu") };
    for (name, cases) in functions {
        if let Some(map) = cases.as_object() {
            for (input, expected) in map {
                let actual = match name.as_str() {
                    "unaccent" => json!(po_text::fold(input)),
                    "html_unescape" => json!(po_text::html_unescape(input)),
                    "clean_text" => json!(po_text::clean_text(input)),
                    "search_key" => json!(po_text::search_key(input)),
                    "fts_query" => json!(po_text::fts_query(input)),
                    "hymn_fts_query" => json!(po_text::hymn_fts_query(input)),
                    "plain_query" => json!(po_text::plain_query(input)),
                    "title_case_words" => json!(po_text::title_case_words(input)),
                    "display_location" => json!(po_text::display_location(input)),
                    "title_case_french" => json!(po_text::title_case_french(input)),
                    "mostly_uppercase" => json!(po_text::mostly_uppercase(input)),
                    "clean_sermon_title" => json!(po_text::clean_sermon_title_for_canonical(input)),
                    "clean_hymn_title" => json!(po_text::clean_hymn_title_for_canonical(input)),
                    "clean_expose_title" => json!(po_text::clean_expose_title(input)),
                    "normalize_filter_date" => json!(po_text::normalize_filter_date(input)),
                    "marker_from_ref" => json!(po_text::marker_from_ref(input, 7)),
                    "paragraph_marker" => json!(po_text::paragraph_marker(input, 7)),
                    "expose_ref_parts" => json!(po_text::expose_ref_parts(input)),
                    "strip_hymn_label" => json!(po_text::strip_hymn_projection_label(input)),
                    "is_chorus" => json!(po_text::is_chorus(input)),
                    other => bail!("fonction de texte inconnue : {other}"),
                };
                section.check(name, input, expected, &actual);
            }
        } else if let Some(list) = cases.as_array() {
            for case in list {
                let a = case.as_array().map(Vec::as_slice).unwrap_or_default();
                let (actual, expected, label) = match (name.as_str(), a) {
                    ("format_reference", [x, y, m, out]) => {
                        (json!(po_text::format_reference(s(x), s(y), s(m))), out, format!("{x} | {y} | {m}"))
                    }
                    ("expose_chapter_num", [d, t, tr, out]) => {
                        (json!(po_text::expose_chapter_num(s(d), s(t), s(tr))), out, format!("{d} | {t} | {tr}"))
                    }
                    ("split_text", [text, max, min, keep, out]) => (
                        json!(po_text::split_text_into_slides(
                            s(text),
                            n(max) as usize,
                            n(min) as usize,
                            keep.as_bool().unwrap_or(true)
                        )),
                        out,
                        format!("({max}, {min}, {keep}) {}", s(text)),
                    ),
                    ("split_stanza", [text, lines, max, couplets, out]) => (
                        json!(po_text::split_hymn_stanza(
                            s(text),
                            n(lines) as usize,
                            n(max) as usize,
                            couplets.as_bool().unwrap_or(true)
                        )),
                        out,
                        format!("({lines}, {max}, {couplets}) {}", s(text)),
                    ),
                    (other, _) => bail!("cas de texte inconnu : {other}"),
                };
                section.check(name, &label, expected, &actual);
            }
        }
    }
    Ok(section)
}

/// Les références bibliques tapées, avec les livres de chaque traduction.
fn bible_references(dir: &Path, db: &Database) -> Result<Section> {
    let refs = read_json(dir, "references_bibliques.json")?;
    let mut section = Section::new("références bibliques");
    let mut books: std::collections::HashMap<i64, Vec<po_text::Book>> = Default::default();
    for case in refs.as_array().into_iter().flatten() {
        let [tid, query, expected] = case.as_array().map(Vec::as_slice).unwrap_or_default() else { continue };
        let tid = n(tid);
        let list = match books.entry(tid) {
            std::collections::hash_map::Entry::Occupied(e) => e.into_mut(),
            std::collections::hash_map::Entry::Vacant(e) => e.insert(
                db.list_translation_books(tid)?.into_iter().map(|b| po_text::Book { id: b.id, name: b.name }).collect(),
            ),
        };
        let actual = match po_text::parse_reference(s(query), list) {
            Some(r) => json!([r.book_id, r.book_name, r.chapter, r.verse, r.label()]),
            None => Value::Null,
        };
        section.check("parse_reference", &format!("{tid} | {}", s(query)), expected, &actual);
    }
    Ok(section)
}

/// Les réglages lus par la 2.8 et par la 3.0.
fn settings(dir: &Path) -> Result<Section> {
    let refs = read_json(dir, "reglages.json")?;
    let mut section = Section::new("réglages");
    for case in refs.as_array().into_iter().flatten() {
        let path = PathBuf::from(s(&case["chemin"]));
        let loaded = po_settings::Settings::load(&path);
        let payload = loaded.settings.to_payload();
        let label =
            format!("{} {}", s(&case["cas"]), path.file_name().map(|f| f.to_string_lossy()).unwrap_or_default());
        for key in ["projection", "appearance", "hdmi", "split"] {
            section.check(key, &label, &case[key], payload.get(key).unwrap_or(&Value::Null));
        }
        section.check("avertissement", &label, &case["warning"], &json!(loaded.warning.unwrap_or("")));
    }
    Ok(section)
}

fn remove_database(path: &Path) {
    for suffix in ["", "-wal", "-shm"] {
        let _ = std::fs::remove_file(format!("{}{suffix}", path.display()));
    }
}

/// Une copie de travail d'une base d'entrée : l'entrée reste intacte et l'outil peut être relancé.
fn working_copy(dir: &Path, name: &str) -> Result<PathBuf> {
    let copy = dir.join(name.replace(".db", "-travail.db"));
    remove_database(&copy);
    std::fs::copy(dir.join(name), &copy).with_context(|| format!("copie de {name}"))?;
    Ok(copy)
}

fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    // `po-parite comparer <a.db> <b.db>` : seulement la comparaison de deux bases (sert aussi à
    // vérifier que l'outil voit bien une différence).
    if let [command, a, b] = args.as_slice()
        && command == "comparer"
    {
        let section = compare::databases("comparaison", Path::new(a), Path::new(b))?;
        println!("{}", section.summary());
        std::process::exit(i32::from(section.failures > 0));
    }
    // `po-parite projection <dossier>` : la mise en page de la projection (phase 2).
    if let [command, dir] = args.as_slice()
        && command == "projection"
    {
        let identical = projection::compare(Path::new(dir))?;
        std::process::exit(i32::from(!identical));
    }
    let dir = PathBuf::from(
        args.first()
            .context("usage : po-parite <dossier des références> | comparer <a.db> <b.db> | projection <dossier>")?,
    );
    let manifest = read_json(&dir, "manifeste.json")?;
    let bible_json = PathBuf::from(s(&manifest["bible_json"]));
    println!(
        "Références : Python {}, SQLite {}, module natif : {}",
        s(&manifest["python"]),
        s(&manifest["sqlite"]),
        manifest["natif"]
    );

    let mut sections = Vec::new();
    let started = Instant::now();
    sections.push(texts(&dir)?);
    let copy = Database::open(Path::new(s(&manifest["copie"])), Mode::ReadOnly)?;
    sections.push(bible_references(&dir, &copy)?);
    sections.push(requests::queries(&dir, &copy)?);
    drop(copy);

    let options = InitOptions { bible_json_dir: Some(bible_json) };
    let t = Instant::now();
    let maintained = working_copy(&dir, "maintenance-30.db")?;
    let (_, report) = Database::open_and_initialize(&maintained, &options)?;
    println!("maintenance 3.0 : {:.1} s ({report:?})", t.elapsed().as_secs_f64());
    sections.push(compare::databases("maintenance", &dir.join("maintenance-28.db"), &maintained)?);

    let fresh = dir.join("neuve-30.db");
    remove_database(&fresh);
    Database::open_and_initialize(&fresh, &options)?;
    sections.push(compare::databases("base neuve", &dir.join("neuve-28.db"), &fresh)?);

    let operated = working_copy(&dir, "operations-30.db")?;
    sections.push(requests::operations(&dir, &operated)?);
    sections.push(compare::databases("opérations", &dir.join("operations-28.db"), &operated)?);
    sections.push(settings(&dir)?);

    let mut total = 0;
    let mut failed = 0;
    let mut report = Map::new();
    for section in &sections {
        println!("{}", section.summary());
        total += section.cases;
        failed += section.failures;
        report.insert(section.name.clone(), section.to_json());
    }
    println!("{total} cas comparés en {:.0} s : {failed} différence(s).", started.elapsed().as_secs_f64());
    std::fs::write(dir.join("rapport.json"), serde_json::to_string_pretty(&Value::Object(report))?)?;
    if failed > 0 {
        std::process::exit(1);
    }
    let _ = same; // utilisé par les modules
    Ok(())
}
