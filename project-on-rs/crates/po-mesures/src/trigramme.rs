//! L'essai d'un index trigramme pour la recherche par sous-chaîne (« ernel Die »), qui parcourt
//! aujourd'hui les 568 000 paragraphes (2 à 3 s, en 2.8 comme en 3.0).
//!
//! Sur une COPIE de la base : l'index FTS5 `trigram` reçoit le texte déjà plié (sans accents, en
//! minuscules, par `po_text::fold`, comme `unaccent()`), si bien qu'une expression de trigrammes
//! trouve exactement les paragraphes dont le texte plié contient la recherche pliée. On mesure la
//! taille de l'index, le temps de construction, la vitesse, et on compare les résultats à ceux du
//! parcours de la 2.8.

use std::path::Path;
use std::time::Instant;

use po_db::{Database, Mode};
use rusqlite::params;
use serde_json::{Value, json};

use crate::{Result, ms};

const QUERIES: [&str; 10] = [
    "ernel Die",
    "zzqxw",
    "ait là, d",
    "esprit de dieu",
    "seigneur jésus-christ",
    "œuvre",
    "l'Éternel",
    "100%",
    "foi_",
    "ab",
];

const FILTERS: &str = "AND s.date NOT LIKE 'BK-%' AND s.date NOT LIKE 'TR-%' AND s.language = 'fr'";
/// L'ordre et la limite de la recherche réelle. Les traductions d'un sermon ont la même date et les
/// mêmes numéros de paragraphe : à égalité, la limite garde l'un ou l'autre selon le plan de
/// SQLite. Les résultats se comparent donc en entier, sans limite.
const ORDER: &str = "ORDER BY s.date, p.paragraph_no LIMIT 100";

fn ids(db: &Database, sql: &str, param: &str) -> rusqlite::Result<Vec<i64>> {
    let mut stmt = db.connection().prepare_cached(sql)?;
    let rows = stmt.query_map([param], |r| r.get(0))?;
    rows.collect()
}

fn file_size(path: &Path) -> u64 {
    std::fs::metadata(path).map(|m| m.len()).unwrap_or(0)
}

pub fn evaluate(source: &Path, out_dir: &Path) -> Result<Value> {
    std::fs::create_dir_all(out_dir)?;
    let work = out_dir.join("trigramme.db");
    for suffix in ["", "-wal", "-shm"] {
        let _ = std::fs::remove_file(format!("{}{suffix}", work.display()));
    }
    po_db::copy_database(source, &work)?;
    let before = file_size(&work);
    let mut db = Database::open(&work, Mode::ReadWrite)?;

    let built = Instant::now();
    {
        let conn = db.connection();
        conn.execute_batch(
            "CREATE VIRTUAL TABLE sermon_paragraph_tri USING fts5(text, content='', detail=full, tokenize='trigram')",
        )?;
    }
    let paragraphs: Vec<(i64, String)> = {
        let mut stmt = db.connection().prepare("SELECT id, text FROM sermon_paragraph")?;
        let rows = stmt.query_map([], |r| Ok((r.get(0)?, r.get(1)?)))?;
        rows.collect::<rusqlite::Result<_>>()?
    };
    {
        let conn = db.connection();
        conn.execute_batch("BEGIN")?;
        {
            let mut insert = conn.prepare("INSERT INTO sermon_paragraph_tri (rowid, text) VALUES (?, ?)")?;
            for (id, text) in &paragraphs {
                insert.execute(params![id, po_text::fold(text)])?;
            }
        }
        conn.execute_batch("COMMIT; PRAGMA wal_checkpoint(TRUNCATE);")?;
    }
    let build_s = built.elapsed().as_secs_f64();
    let after = file_size(&work);
    println!(
        "Index trigramme : {} paragraphes en {build_s:.1} s, +{:.0} Mo",
        paragraphs.len(),
        (after - before) as f64 / 1e6
    );
    drop(paragraphs);
    db = Database::open(&work, Mode::ReadOnly)?;

    let scan_all = format!(
        "SELECT p.id FROM sermon_paragraph p JOIN sermon s ON s.id = p.sermon_id
         WHERE unaccent(p.text) LIKE unaccent(?) {FILTERS} ORDER BY p.id"
    );
    let tri_all = format!(
        "SELECT p.id FROM sermon_paragraph_tri t
         JOIN sermon_paragraph p ON p.id = t.rowid
         JOIN sermon s ON s.id = p.sermon_id
         WHERE sermon_paragraph_tri MATCH ? {FILTERS} ORDER BY p.id"
    );
    let scan_sql = scan_all.replace("ORDER BY p.id", ORDER);
    let tri_sql = tri_all.replace("ORDER BY p.id", ORDER);
    let mut results = Vec::new();
    for query in QUERIES {
        let plain = po_text::plain_query(query);
        let started = Instant::now();
        let shown = ids(&db, &scan_sql, &format!("%{plain}%"))?;
        let scan_ms = ms(started.elapsed());
        let scanned = ids(&db, &scan_all, &format!("%{plain}%"))?;
        let folded = po_text::fold(&plain);
        let (tri_ms, tri_result) = if folded.chars().count() < 3 {
            (None, None)
        } else {
            let phrase = format!("\"{}\"", folded.replace('"', "\"\""));
            let mut times = Vec::new();
            let mut found = Vec::new();
            for _ in 0..3 {
                let started = Instant::now();
                found = ids(&db, &tri_sql, &phrase)?;
                times.push(ms(started.elapsed()));
            }
            debug_assert!(found.len() <= 100);
            (Some(times.iter().copied().fold(f64::MAX, f64::min)), Some(ids(&db, &tri_all, &phrase)?))
        };
        let same = tri_result.as_ref().map(|found| found == &scanned);
        println!(
            "  {query:24} parcours {scan_ms:8.1} ms ({} affichés sur {})   trigramme {}   {}",
            shown.len(),
            scanned.len(),
            tri_ms.map_or("   —     ".to_string(), |t| format!("{t:7.1} ms")),
            match same {
                Some(true) => "mêmes résultats",
                Some(false) => "RÉSULTATS DIFFÉRENTS",
                None => "trop court pour l'index (parcours gardé)",
            }
        );
        results.push(json!({
            "requete": query,
            "parcours_ms": scan_ms,
            "parcours_resultats": scanned.len(),
            "parcours_affiches": shown.len(),
            "trigramme_ms": tri_ms,
            "trigramme_resultats": tri_result.as_ref().map(Vec::len),
            "memes_resultats": same,
        }));
    }
    drop(db);
    let _ = std::fs::remove_file(&work);
    Ok(json!({
        "paragraphes": 568_000,
        "construction_s": (build_s * 10.0).round() / 10.0,
        "taille_avant_mo": before as f64 / 1e6,
        "taille_apres_mo": after as f64 / 1e6,
        "index_mo": (after - before) as f64 / 1e6,
        "requetes": results,
    }))
}
