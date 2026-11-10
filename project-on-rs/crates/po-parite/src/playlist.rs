//! La phase 4 : le programme d'une playlist et le genre de ses éléments, comparés à la 2.8, qui a
//! écrit `playlist.json` et ses playlists dans `playlist-28.db` (`outils/references_playlist_28.py`).
//!
//! Une différence est voulue : les médias (images, vidéos) ne sont projetés qu'à partir de la
//! phase 7 ; la 3.0 les saute. La comparaison retire donc les entrées à visuel de la 2.8 et, quand
//! la 2.8 commençait sur un média, attend le premier slide.

use std::path::Path;

use anyhow::{Context, Result};
use po_db::{Database, Mode};
use serde::Deserialize;
use serde_json::{Map, Value, json};

use crate::compare::Section;

#[derive(Deserialize)]
struct References {
    cas: Vec<Case>,
}

#[derive(Deserialize)]
struct Programme {
    titre: String,
    entrees: Vec<(String, String)>,
    focus: usize,
    visuels: Vec<String>,
}

#[derive(Deserialize)]
struct Case {
    dossier: i64,
    nom: String,
    depart: Option<i64>,
    programme: Option<Programme>,
    #[serde(default)]
    genres: Map<String, Value>,
}

fn kind_name(kind: project_on::playlist::Kind) -> &'static str {
    use project_on::playlist::Kind;
    match kind {
        Kind::Bible => "bible",
        Kind::Hymn => "hymn",
        Kind::Sermon => "sermon",
        Kind::Expose => "expose",
        Kind::Image => "image",
        Kind::Video => "video",
        Kind::PowerPoint => "powerpoint",
        Kind::Custom => "custom",
    }
}

/// Compare tout ; vrai si aucune différence.
pub fn compare(dir: &Path) -> Result<bool> {
    let text = std::fs::read_to_string(dir.join("playlist.json")).context("lecture de playlist.json")?;
    let refs: References = serde_json::from_str(&text)?;
    let db = Database::open(&dir.join("playlist-28.db"), Mode::ReadOnly)?;
    let mut section = Section::new("playlist");
    let mut slides = 0usize;
    for case in &refs.cas {
        let label = format!("{} (départ {:?})", case.nom, case.depart);
        let items = db.list_items(Some(case.dossier))?;
        let ours = project_on::playlist::program(&case.nom, &items, case.depart, &[]);
        let expected = case.programme.as_ref().map(|p| {
            // Les entrées sans visuel ; le départ sur un média revient au premier slide.
            let keep: Vec<usize> =
                (0..p.entrees.len()).filter(|&i| p.visuels.get(i).is_none_or(String::is_empty)).collect();
            let entries: Vec<&(String, String)> = keep.iter().map(|&i| &p.entrees[i]).collect();
            let focus = keep.iter().position(|&i| i == p.focus).unwrap_or(0);
            json!({ "titre": p.titre, "entrees": entries, "focus": focus })
        });
        let actual = ours.as_ref().map(|p| {
            let entries: Vec<(&str, &str)> =
                p.cue.entries.iter().map(|e| (e.reference.as_str(), e.text.as_str())).collect();
            json!({ "titre": p.cue.title, "entrees": entries, "focus": p.cue.focus })
        });
        section.check("programme", &label, &json!(expected), &json!(actual));
        // Les slides de ce programme (découpage d'un texte saisi, comme la 2.8).
        if let Some(p) = &ours {
            let split = po_settings::SplitSettings::default();
            slides += po_program::build_slides(&p.cue.source, &p.cue.entries, true, &split).0.len();
        }
        for (id, kind) in &case.genres {
            let item = items.iter().find(|i| i.id.to_string() == *id);
            let ours = item.map(|i| kind_name(project_on::playlist::item_kind(&i.source, &i.reference, &i.background)));
            section.check("genre", &format!("{} élément {id}", case.nom), kind, &json!(ours));
        }
    }
    println!("{}", section.summary());
    println!(
        "{} programmes de playlist ({slides} slides), {} comparaisons : {} différence(s).",
        refs.cas.len(),
        section.cases,
        section.failures
    );
    let report = json!({
        "programmes": refs.cas.len(),
        "slides": slides,
        "comparaisons": section.cases,
        "differences": section.failures,
    });
    std::fs::write(dir.join("playlist-rapport.json"), serde_json::to_string_pretty(&report)?)?;
    std::fs::write(dir.join("playlist-details.json"), serde_json::to_string_pretty(&section.to_json())?)?;
    Ok(section.failures == 0)
}
