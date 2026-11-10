//! Les résultats de la 3.0 mis sous la forme des dictionnaires de la 2.8 (identifiants « int_12 »,
//! clés en double comme `para_id` / `marker` ou `ref` / `reference`), pour les comparer tels quels.

use po_db::{BookChapter, BookHit, MediaItem, Paragraph, ParagraphHit, Sermon};
use serde_json::{Value, json};

pub fn sermon(s: &Sermon) -> Value {
    json!({
        "id": format!("int_{}", s.id), "title": s.title, "original_title": s.original_title, "date": s.date,
        "date_code": s.date, "tradition": s.tradition, "language": s.language, "translator": s.tradition,
        "sort_key": s.date, "location": s.location, "printed_date": s.printed_date,
    })
}

pub fn paragraph(p: &Paragraph) -> Value {
    json!({"paragraph_no": p.paragraph_no, "para_id": p.marker, "marker": p.marker, "ref": p.raw_ref, "text": p.text})
}

pub fn hit(h: &ParagraphHit) -> Value {
    json!({
        "id": format!("int_p_{}_{}", h.sermon_id, h.paragraph_no), "sermon_id": format!("int_{}", h.sermon_id),
        "paragraph_no": h.paragraph_no, "para_id": h.marker, "marker": h.marker, "ref": h.reference,
        "reference": h.reference, "raw_ref": h.raw_ref, "text": h.text, "sermon_title": h.sermon_title,
        "original_title": h.original_title, "sermon_date": h.sermon_date, "sermon_tradition": h.sermon_tradition,
    })
}

pub fn chapter(c: &BookChapter) -> Value {
    json!({
        "id": format!("int_{}", c.id), "title": c.title, "original_title": c.original_title,
        "chapter_num": c.chapter_num, "date_code": c.date_code,
    })
}

pub fn book_hit(h: &BookHit) -> Value {
    json!({
        "id": format!("int_p_{}_{}", h.sermon_id, h.paragraph_no), "sermon_id": format!("int_{}", h.sermon_id),
        "paragraph_no": h.paragraph_no, "para_id": h.marker, "marker": h.marker, "ref": h.reference,
        "reference": h.reference, "raw_ref": h.raw_ref, "text": h.text, "title": h.title,
    })
}

/// `get_media` de la 2.8 ne rend pas le rang ni la date.
pub fn media_detail(m: &MediaItem) -> Value {
    json!({"id": m.id, "name": m.name, "path": m.path, "kind": m.kind, "loop": m.looped, "duration_seconds": m.duration_seconds})
}

pub fn list<T>(items: &[T], f: impl Fn(&T) -> Value) -> Value {
    Value::Array(items.iter().map(f).collect())
}

pub fn serde<T: serde::Serialize>(value: &T) -> Value {
    serde_json::to_value(value).unwrap_or(Value::Null)
}
