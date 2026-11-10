//! Les requêtes sur la copie de la base, et les opérations d'écriture sur une base de travail.

use std::collections::BTreeMap;
use std::path::Path;
use std::time::Instant;

use anyhow::{Result, bail};
use po_db::{Database, ItemSnapshot, Mode, NewItem, ParagraphSearch, SermonFilter, SermonSort};
use serde_json::{Value, json};

use crate::compare::Section;
use crate::read_json;
use crate::v28;

fn int(v: &Value) -> i64 {
    match v {
        Value::String(s) => s.trim_start_matches("int_").parse().unwrap_or(0),
        other => other.as_i64().unwrap_or(0),
    }
}

fn opt_int(v: &Value) -> Option<i64> {
    if v.is_null() { None } else { Some(int(v)) }
}

fn text(v: &Value) -> &str {
    v.as_str().unwrap_or("")
}

fn opt_text(v: &Value) -> Option<&str> {
    v.as_str()
}

fn ints(v: &Value) -> Vec<i64> {
    v.as_array().into_iter().flatten().map(int).collect()
}

/// Un appel de la 2.8 refait par la 3.0.
fn call(db: &Database, name: &str, args: &[Value], kw: &serde_json::Map<String, Value>) -> Result<Value> {
    let arg = |i: usize| args.get(i).unwrap_or(&Value::Null);
    let k = |key: &str| kw.get(key).unwrap_or(&Value::Null);
    let no = &Value::Null;
    Ok(match name {
        "list_sermons" => {
            let filter = SermonFilter {
                translator: opt_text(k("translator")).or(opt_text(k("tradition"))),
                language: opt_text(k("language")),
                title: opt_text(k("title_query")),
                date_from: opt_text(k("date_from")),
                date_to: opt_text(k("date_to")),
                location: opt_text(k("location_query")),
                sort: match text(k("sort_by")) {
                    "title" => SermonSort::Title,
                    "location" => SermonSort::Location,
                    _ => SermonSort::Date,
                },
                limit: k("limit").as_u64().map(|l| l as usize),
            };
            v28::list(&db.list_sermons(&filter)?, v28::sermon)
        }
        "list_sermon_years" => json!(db.list_sermon_years(
            opt_text(k("translator")).or(opt_text(k("tradition"))),
            opt_text(k("language")),
            opt_text(k("title_query"))
        )?),
        "list_branham_translators" => json!(db.list_translators(text(arg(0)))?),
        "get_sermon" => db.sermon(int(arg(0)))?.as_ref().map_or(Value::Null, v28::sermon),
        "list_paragraphs" => v28::list(&db.paragraphs(int(arg(0)))?, v28::paragraph),
        "search_paragraphs" => {
            let search = ParagraphSearch {
                query: text(arg(0)),
                // La 2.8 cherche en anglais si on ne dit rien.
                language: if kw.contains_key("language") { opt_text(k("language")) } else { Some("en") },
                translator: opt_text(k("translator")),
                limit: k("limit").as_u64().unwrap_or(100) as usize,
                substring_fallback: k("substring_fallback").as_bool().unwrap_or(true),
            };
            v28::list(&db.search_paragraphs(&search)?, v28::hit)
        }
        "list_books" => v28::serde(&db.list_books()?),
        "list_book_chapters" => v28::list(&db.list_book_chapters(text(arg(0)))?, v28::chapter),
        "search_book" => {
            let limit = k("limit").as_u64().or(arg(2).as_u64()).unwrap_or(100) as usize;
            v28::list(&db.search_book(text(arg(0)), text(arg(1)), limit)?, v28::book_hit)
        }
        "book_of_chapter" => v28::serde(&db.book_of_chapter(int(arg(0)))?),
        "list_expose_chapters" => v28::list(&db.list_expose_chapters(text(arg(0)))?, v28::chapter),
        "list_expose_pages" => json!(db.list_expose_pages(int(arg(0)))?),
        "list_expose_page_paragraphs" => {
            v28::list(&db.list_expose_page_paragraphs(int(arg(0)), int(arg(1)) as u32)?, v28::paragraph)
        }
        "search_expose" => {
            let limit = arg(2).as_u64().unwrap_or(100) as usize;
            v28::list(&db.search_expose(text(arg(0)), text(arg(1)), limit)?, v28::book_hit)
        }
        "list_translations" => v28::serde(&db.list_translations()?),
        "list_translation_books" => v28::serde(&db.list_translation_books(int(arg(0)))?),
        "list_translation_chapters" => json!(db.list_translation_chapters(int(arg(0)), int(arg(1)))?),
        "list_translation_verses" => v28::serde(&db.list_translation_verses(int(arg(0)), int(arg(1)), int(arg(2)))?),
        "list_books_legacy" => v28::serde(&db.list_legacy_books()?),
        "list_chapters_legacy" => json!(db.list_legacy_chapters(int(arg(0)))?),
        "list_verses_legacy" => v28::serde(&db.list_legacy_verses(int(arg(0)), int(arg(1)))?),
        "list_hymns" => v28::serde(&db.list_hymns(
            opt_text(k("language")),
            k("limit").as_u64().map(|l| l as usize),
            opt_text(k("query")),
        )?),
        "get_hymn" => v28::serde(&db.hymn(int(arg(0)))?),
        "list_stanzas" => v28::serde(&db.stanzas(int(arg(0)))?),
        "search_stanzas" => {
            let limit = k("limit").as_u64().or(arg(1).as_u64()).unwrap_or(100) as usize;
            v28::serde(&db.search_stanzas(text(arg(0)), limit)?)
        }
        "list_folders" => v28::serde(&db.list_folders()?),
        "list_items" => v28::serde(&db.list_items(opt_int(arg(0)))?),
        "list_all_items" => v28::serde(&db.list_all_items()?),
        "list_sections" => v28::serde(&db.list_sections(int(arg(0)))?),
        "get_start_time" => json!(db.start_time(int(arg(0)))?),
        "list_media" => v28::serde(&db.list_media()?),
        "get_media" => db.media(int(arg(0)))?.as_ref().map_or(no.clone(), v28::media_detail),
        other => bail!("appel inconnu : {other}"),
    })
}

/// Les lectures sur la copie de la base, avec le temps de chaque version.
pub fn queries(dir: &Path, db: &Database) -> Result<Section> {
    let refs = read_json(dir, "requetes.json")?;
    let mut section = Section::new("requêtes");
    let mut times: BTreeMap<String, (f64, f64)> = BTreeMap::new();
    let empty = serde_json::Map::new();
    for case in refs.as_array().into_iter().flatten() {
        let name = text(&case["fn"]);
        let args = case["args"].as_array().map(Vec::as_slice).unwrap_or_default();
        let kw = case["kwargs"].as_object().unwrap_or(&empty);
        let started = Instant::now();
        let actual = call(db, name, args, kw)?;
        let rust_ms = started.elapsed().as_secs_f64() * 1000.0;
        let entry = times.entry(name.to_string()).or_default();
        entry.0 += case["ms"].as_f64().unwrap_or(0.0);
        entry.1 += rust_ms;
        section.check(
            name,
            &format!("{} {}", Value::Array(args.to_vec()), Value::Object(kw.clone())),
            &case["out"],
            &actual,
        );
    }
    println!("Temps cumulés (2.8 → 3.0) :");
    for (name, (python, rust)) in &times {
        println!("    {name:30} {python:9.1} ms → {rust:9.1} ms");
    }
    Ok(section)
}

/// Les opérations d'écriture, rejouées sur la copie de travail de la 3.0.
pub fn operations(dir: &Path, database: &Path) -> Result<Section> {
    let refs = read_json(dir, "operations.json")?;
    let mut db = Database::open(database, Mode::ReadWrite)?;
    let mut section = Section::new("opérations (résultats)");
    let mut snapshot: Vec<(i64, Vec<ItemSnapshot>)> = Vec::new();
    let ops = refs["operations"].as_array().cloned().unwrap_or_default();
    let expected = refs["resultats"].as_array().cloned().unwrap_or_default();
    let empty = serde_json::Map::new();
    for (op, expected) in ops.iter().zip(&expected) {
        let Some((name, args)) = op.as_array().and_then(|a| a.split_first()) else { continue };
        let name = text(name);
        let a = |i: usize| args.get(i).unwrap_or(&Value::Null);
        let actual = match name {
            "create_folder" => json!(db.create_folder(text(a(0)))?),
            "add_item" => json!(db.add_item(text(a(0)), text(a(1)), text(a(2)), opt_int(a(3)), text(a(4)))?),
            "add_items" => {
                let items: Vec<(String, String, String)> = a(0)
                    .as_array()
                    .into_iter()
                    .flatten()
                    .map(|i| (text(&i[0]).to_string(), text(&i[1]).to_string(), text(&i[2]).to_string()))
                    .collect();
                json!(db.add_items(&items, opt_int(a(1)))?)
            }
            "move_item" => json!(db.move_item(int(a(0)), int(a(1)), opt_int(a(2)))?),
            "snapshot_folders" => {
                snapshot = db.snapshot_folders(&ints(a(0)))?;
                Value::Object(snapshot.iter().map(|(id, rows)| (id.to_string(), v28::serde(rows))).collect())
            }
            "restore_folders" => json!(db.restore_folders(&snapshot)?),
            "duplicate_items" => json!(db.duplicate_items(&ints(a(0)))?),
            "reorder_items" => json!(db.reorder_items(int(a(0)), &ints(a(1)))?),
            "copy_items" => json!(db.copy_items(&ints(a(0)), int(a(1)))?),
            "move_items_to_folder" => json!(db.move_items_to_folder(&ints(a(0)), int(a(1)))?),
            "update_item" => json!(db.update_item(int(a(0)), text(a(1)), text(a(2)))?),
            "update_item_background" => json!(db.update_item_background(int(a(0)), text(a(1)))?),
            "update_item_sort_order" => json!(db.update_item_sort_order(int(a(0)), int(a(1)), opt_int(a(2)))?),
            "delete_item" => json!(db.delete_item(int(a(0)))?),
            "delete_items" => json!(db.delete_items(&ints(a(0)))?),
            "import_folder" => {
                let items: Vec<NewItem> = a(1)
                    .as_array()
                    .into_iter()
                    .flatten()
                    .map(|i| NewItem {
                        source: i.get("source").and_then(Value::as_str).unwrap_or("custom").into(),
                        reference: text(&i["reference"]).into(),
                        text: text(&i["text"]).into(),
                        background: text(&i["background"]).into(),
                    })
                    .collect();
                json!(db.import_folder(text(a(0)), &items)?)
            }
            "rename_folder" => json!(db.rename_folder(int(a(0)), text(a(1)))?),
            "delete_folder" => json!(db.delete_folder(int(a(0)))?),
            "set_start_time" => {
                db.set_start_time(int(a(0)), text(a(1)))?;
                Value::Null
            }
            "get_start_time" => json!(db.start_time(int(a(0)))?),
            "add_section" => json!(db.add_section(int(a(0)), text(a(1)), int(a(2)), opt_int(a(3)))?),
            "move_section" => json!(db.move_section(int(a(0)), int(a(1)))?),
            "update_section" => {
                db.update_section(int(a(0)), text(a(1)), int(a(2)), opt_int(a(3)))?;
                Value::Null
            }
            "delete_section" => {
                db.delete_section(int(a(0)))?;
                Value::Null
            }
            "add_media" => json!(db.add_media(text(a(0)), text(a(1)), text(a(2)))?),
            "set_loop" => json!(db.set_media_loop(int(a(0)), a(1).as_bool().unwrap_or(false))?),
            "set_duration" => json!(db.set_media_duration(int(a(0)), int(a(1)))?),
            "rename_media" => json!(db.rename_media(int(a(0)), text(a(1)))?),
            "purge_web_media" => json!(db.purge_web_media()?),
            "import_hymn" => {
                let stanzas: Vec<String> = a(1).as_array().into_iter().flatten().map(|s| text(s).to_string()).collect();
                json!(db.import_hymn(text(a(0)), &stanzas, opt_text(a(2)), text(a(3)))?)
            }
            "save_hymn" => {
                let stanzas: Vec<(String, bool)> = a(2)
                    .as_array()
                    .into_iter()
                    .flatten()
                    .map(|s| (text(&s[0]).to_string(), s[1].as_bool().unwrap_or(false)))
                    .collect();
                json!(db.save_hymn(opt_int(a(0)), text(a(1)), &stanzas, opt_text(a(3)), text(a(4)))?)
            }
            "hymn_exists" => json!(db.hymn_exists(text(a(0)))?),
            "exact_duplicate_exists" => {
                let stanzas: Vec<String> = a(1).as_array().into_iter().flatten().map(|s| text(s).to_string()).collect();
                json!(db.exact_duplicate_exists(text(a(0)), &stanzas)?)
            }
            "delete_hymn" => {
                db.delete_hymn(int(a(0)))?;
                Value::Null
            }
            other => call(&db, other, args, &empty)?,
        };
        section.check(name, &op.to_string(), expected, &actual);
    }
    Ok(section)
}
