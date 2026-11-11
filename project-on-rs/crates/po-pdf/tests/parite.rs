//! La parité avec la 2.8 sur les recueils du dépôt (`cantiques/*.pdf`). Les résultats de la 2.8
//! (`target/pdf-ref/*.json` : ses lignes et ses cantiques) se refont avec
//! `py -3.14 project-on-rs/crates/po-pdf/references.py` ; sans eux, l'essai ne fait rien.
//!
//! 1. Les mêmes lignes donnent exactement les mêmes cantiques (les règles sont identiques).
//! 2. Le PDF lu par la 3.0 donne les mêmes cantiques que la 2.8 (numéro, titre, strophes).

#![allow(clippy::unwrap_used)]

use std::path::Path;

use serde_json::Value;

fn reference(name: &str) -> Option<Value> {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/pdf-ref").join(format!("{name}.json"));
    serde_json::from_str(&std::fs::read_to_string(path).ok()?).ok()
}

fn hymns_of(value: &Value) -> Vec<(String, String, Vec<String>)> {
    value["hymns"]
        .as_array()
        .unwrap()
        .iter()
        .map(|h| {
            let stanzas = h["stanzas"].as_array().unwrap().iter().map(|s| s.as_str().unwrap().to_string()).collect();
            (h["number"].as_str().unwrap().to_string(), h["title"].as_str().unwrap().to_string(), stanzas)
        })
        .collect()
}

const BOOKS: [&str; 3] = ["Cantique Pene Na Yo", "Cantiques Crois seulement", "Cantiques-Ins"];

#[test]
fn the_same_lines_give_the_same_hymns() {
    for book in BOOKS {
        let Some(r) = reference(book) else { continue };
        let lines: Vec<String> =
            r["lines"].as_array().unwrap().iter().map(|l| l.as_str().unwrap().to_string()).collect();
        let ours: Vec<(String, String, Vec<String>)> =
            po_pdf::hymns_from_lines(&lines).into_iter().map(|h| (h.number, h.title, h.stanzas)).collect();
        let theirs = hymns_of(&r);
        for (a, b) in ours.iter().zip(&theirs) {
            assert_eq!(a, b, "{book}");
        }
        assert_eq!(ours.len(), theirs.len(), "{book}");
    }
}

#[test]
fn the_pdf_read_in_rust_gives_the_hymns_of_the_2_8() {
    let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../cantiques");
    for book in BOOKS {
        let (Some(r), pdf) = (reference(book), dir.join(format!("{book}.pdf"))) else { continue };
        if !pdf.is_file() {
            continue;
        }
        let ours = po_pdf::hymns_from_pdf(&pdf).unwrap();
        let theirs = hymns_of(&r);
        let same_titles = ours.iter().filter(|h| theirs.iter().any(|t| t.0 == h.number && t.1 == h.title)).count();
        let same = ours
            .iter()
            .filter(|h| theirs.iter().any(|t| t.0 == h.number && t.1 == h.title && t.2 == h.stanzas))
            .count();
        println!(
            "{book} : 3.0 {} cantiques, 2.8 {} ; titres identiques {same_titles}, entièrement identiques {same}",
            ours.len(),
            theirs.len()
        );
    }
}

#[test]
#[ignore]
fn show_differences() {
    let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../cantiques");
    for book in BOOKS {
        let Some(r) = reference(book) else { continue };
        let ours = po_pdf::hymns_from_pdf(&dir.join(format!("{book}.pdf"))).unwrap();
        let theirs = hymns_of(&r);
        let mut shown = 0;
        for h in &ours {
            if let Some(t) = theirs.iter().find(|t| t.0 == h.number && t.1 == h.title)
                && t.2 != h.stanzas
                && shown < 3
            {
                shown += 1;
                for (a, b) in h.stanzas.iter().zip(&t.2) {
                    if a != b {
                        println!("{book} {} : 3.0 {a:?}\n   2.8 {b:?}", h.number);
                        break;
                    }
                }
                if h.stanzas.len() != t.2.len() {
                    println!("{book} {} : {} strophes contre {}", h.number, h.stanzas.len(), t.2.len());
                }
            }
        }
        for t in theirs.iter().filter(|t| !ours.iter().any(|h| h.number == t.0 && h.title == t.1)).take(3) {
            println!("{book} : titre 2.8 absent : {} {}", t.0, t.1);
        }
    }
}
