//! Comparer : des valeurs JSON (en ignorant les dates de création), et deux bases entières.

use std::path::Path;

use anyhow::Result;
use rusqlite::types::Value as SqlValue;
use rusqlite::{Connection, OpenFlags};
use serde_json::{Value, json};

/// Les champs qui changent d'une exécution à l'autre.
const IGNORED_KEYS: [&str; 2] = ["created_at", "ms"];

/// Deux valeurs JSON égales, sans tenir compte des champs horodatés.
pub fn same(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Object(x), Value::Object(y)) => {
            let keys = |m: &serde_json::Map<String, Value>| {
                let mut k: Vec<String> = m.keys().filter(|k| !IGNORED_KEYS.contains(&k.as_str())).cloned().collect();
                k.sort();
                k
            };
            keys(x) == keys(y) && keys(x).iter().all(|k| same(&x[k], &y[k]))
        }
        (Value::Array(x), Value::Array(y)) => x.len() == y.len() && x.iter().zip(y).all(|(p, q)| same(p, q)),
        (Value::Number(x), Value::Number(y)) => match (x.as_i64(), y.as_i64()) {
            (Some(p), Some(q)) => p == q,
            _ => x.is_f64() == y.is_f64() && x.as_f64() == y.as_f64(),
        },
        _ => a == b,
    }
}

fn truncate(text: &str, max: usize) -> String {
    if text.chars().count() <= max {
        text.to_string()
    } else {
        format!("{}…", text.chars().take(max).collect::<String>())
    }
}

/// Les résultats d'une partie des comparaisons.
pub struct Section {
    pub name: String,
    pub cases: usize,
    pub failures: usize,
    examples: Vec<Value>,
    per_function: std::collections::BTreeMap<String, (usize, usize)>,
}

impl Section {
    pub fn new(name: &str) -> Self {
        Self { name: name.into(), cases: 0, failures: 0, examples: Vec::new(), per_function: Default::default() }
    }

    pub fn check(&mut self, function: &str, label: &str, expected: &Value, actual: &Value) {
        self.cases += 1;
        let entry = self.per_function.entry(function.to_string()).or_default();
        entry.0 += 1;
        if same(expected, actual) {
            return;
        }
        self.failures += 1;
        entry.1 += 1;
        if self.examples.len() < 40 {
            self.examples.push(json!({
                "fonction": function,
                "cas": truncate(label, 300),
                "attendu (2.8)": truncate(&expected.to_string(), 600),
                "obtenu (3.0)": truncate(&actual.to_string(), 600),
            }));
        }
    }

    pub fn summary(&self) -> String {
        let mut out = format!("{} : {} cas, {} différence(s)", self.name, self.cases, self.failures);
        for (function, (cases, failures)) in &self.per_function {
            if *failures > 0 {
                out.push_str(&format!("\n    {function} : {failures} / {cases}"));
            }
        }
        for example in self.examples.iter().take(5) {
            out.push_str(&format!("\n    ex. {example}"));
        }
        out
    }

    pub fn to_json(&self) -> Value {
        json!({
            "cas": self.cases,
            "differences": self.failures,
            "par_fonction": self.per_function.iter().map(|(k, (c, f))| (k.clone(), json!({"cas": c, "differences": f}))).collect::<serde_json::Map<_, _>>(),
            "exemples": self.examples,
        })
    }
}

fn open(path: &Path) -> Result<Connection> {
    Ok(Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX)?)
}

fn sql_json(v: SqlValue) -> Value {
    match v {
        SqlValue::Null => Value::Null,
        SqlValue::Integer(i) => json!(i),
        SqlValue::Real(f) => json!(f),
        SqlValue::Text(t) => json!(t),
        SqlValue::Blob(b) => json!(format!("<{} octets>", b.len())),
    }
}

fn collapse(sql: &str) -> String {
    sql.split_whitespace().collect::<Vec<_>>().join(" ")
}

/// Les lignes d'une requête, en JSON.
fn rows(conn: &Connection, sql: &str) -> Result<Vec<Value>> {
    let mut stmt = conn.prepare(sql)?;
    let count = stmt.column_count();
    let names: Vec<String> = stmt.column_names().map(str::to_string).collect();
    let mapped = stmt.query_map([], |r| {
        let mut row = serde_json::Map::new();
        for (i, name) in names.iter().enumerate().take(count) {
            row.insert(name.clone(), sql_json(r.get::<_, SqlValue>(i)?));
        }
        Ok(Value::Object(row))
    })?;
    Ok(mapped.collect::<rusqlite::Result<Vec<_>>>()?)
}

/// Compare deux bases : version, schéma (texte SQL aux espaces près), toutes les lignes de toutes
/// les tables (sauf les dates de création et les tables internes des index), et les résultats de
/// quelques recherches dans chaque index.
pub fn databases(name: &str, expected: &Path, actual: &Path) -> Result<Section> {
    let (a, b) = (open(expected)?, open(actual)?);
    let mut section = Section::new(name);
    let version = |c: &Connection| c.query_row("PRAGMA user_version", [], |r| r.get::<_, i64>(0));
    section.check("user_version", "", &json!(version(&a)?), &json!(version(&b)?));

    let schema_sql = "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name";
    let schema = |c: &Connection| -> Result<Vec<Value>> {
        Ok(rows(c, schema_sql)?
            .into_iter()
            .map(|mut r| {
                if let Some(sql) = r["sql"].as_str() {
                    r["sql"] = json!(collapse(sql));
                }
                r
            })
            .collect())
    };
    let (schema_a, schema_b) = (schema(&a)?, schema(&b)?);
    section.check("schéma", "sqlite_master", &json!(schema_a), &json!(schema_b));

    let tables: Vec<String> = schema_a
        .iter()
        .filter(|r| r["type"] == "table")
        .filter(|r| !r["sql"].as_str().unwrap_or("").to_uppercase().starts_with("CREATE VIRTUAL"))
        .map(|r| r["name"].as_str().unwrap_or("").to_string())
        .filter(|t| !t.contains("_fts_") && !t.starts_with("sqlite_"))
        .collect();
    for table in tables {
        let sql = format!("SELECT * FROM \"{table}\" ORDER BY rowid");
        let (left, right) = (rows(&a, &sql), rows(&b, &sql));
        let (Ok(left), Ok(right)) = (left, right) else {
            section.check(&table, "lecture", &json!("lisible"), &json!("illisible"));
            continue;
        };
        section.check(&format!("{table} (lignes)"), "nombre", &json!(left.len()), &json!(right.len()));
        for (index, (x, y)) in left.iter().zip(&right).enumerate() {
            section.check(&table, &format!("ligne {index}"), x, y);
        }
    }

    for (fts, terms) in
        [("sermon_paragraph_fts", ["foi", "ange", "dieu"]), ("hymn_stanza_fts", ["gloire", "refrain", "jesus"])]
    {
        for term in terms {
            let sql = format!("SELECT rowid FROM {fts} WHERE {fts} MATCH '{term}*' ORDER BY rowid");
            let found = |c: &Connection| rows(c, &sql).map(|r| json!(r)).unwrap_or(json!("absent"));
            section.check(fts, term, &found(&a), &found(&b));
        }
    }
    Ok(section)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn creation_dates_are_ignored_but_nothing_else() {
        assert!(same(&json!({"id": 1, "created_at": "2026-11-09 21:00"}), &json!({"id": 1, "created_at": "autre"})));
        assert!(!same(&json!({"id": 1}), &json!({"id": 2})));
        assert!(!same(&json!({"id": 1}), &json!({"id": 1, "nom": "x"})));
        assert!(!same(&json!([1, 2]), &json!([2, 1])));
        // Un entier n'est pas un nombre à virgule : `120` n'est pas `120.0`.
        assert!(!same(&json!(120), &json!(120.0)));
        assert!(same(&json!(0.5), &json!(0.5)));
        assert!(!same(&Value::Null, &json!("")));
    }

    #[test]
    fn a_section_counts_every_case() {
        let mut section = Section::new("essai");
        section.check("f", "a", &json!(1), &json!(1));
        section.check("f", "b", &json!(1), &json!(2));
        assert_eq!((section.cases, section.failures), (2, 1));
        assert!(section.summary().contains("f : 1 / 2"));
    }
}
