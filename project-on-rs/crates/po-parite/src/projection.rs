//! La mise en page de la projection : la 3.0 refait les slides mis en page par la 2.8
//! (`outils/references_projection_28.py`) et compare la taille, les lignes et les positions.

use std::collections::BTreeMap;
use std::path::Path;

use anyhow::{Context, Result};
use po_design::{RoomDesign, SlideSource};
use po_layout::{DisplayList, Fonts, Item, Slide, bundled_fonts_dir, layout_room};
use serde_json::{Map, Value, json};

/// Les écarts tolérés sur les positions, en pixels (les deux moteurs arrondissent différemment).
const TOLERANCE: f64 = 2.0;

#[derive(Default)]
struct Tally {
    cases: usize,
    size: usize,
    lines: usize,
    baseline: usize,
    reference: usize,
    accent: usize,
    /// Le plus grand écart de position (ligne de base du texte), en pixels.
    max_shift: f64,
}

impl Tally {
    fn json(&self) -> Value {
        let pct = |n: usize| (n as f64 * 1000.0 / self.cases.max(1) as f64).round() / 10.0;
        json!({
            "cas": self.cases,
            "meme_taille_pct": pct(self.size),
            "memes_lignes_pct": pct(self.lines),
            "meme_place_pct": pct(self.baseline),
            "meme_reference_pct": pct(self.reference),
            "meme_filet_pct": pct(self.accent),
            "ecart_max_px": (self.max_shift * 100.0).round() / 100.0,
        })
    }
}

fn source(kind: &str) -> SlideSource {
    match kind {
        "sermon" => SlideSource::Sermon,
        "hymn" => SlideSource::Hymn,
        "bible" => SlideSource::Bible,
        _ => SlideSource::Custom,
    }
}

fn design(config: &Value) -> RoomDesign {
    let mut payload = Map::new();
    payload.insert("projection".into(), config.clone());
    let settings = po_settings::Settings::from_payload(&payload);
    let mut design = RoomDesign::from_projection(&settings.projection);
    // La 2.8 n'a pas d'identification : la comparer serait comparer deux écrans différents.
    design.identification.enabled = false;
    design
}

struct Placed {
    size: f64,
    lines: Vec<String>,
    baseline: f64,
}

fn placed(list: &DisplayList, reference: bool) -> Option<Placed> {
    let lines: Vec<_> = list.text_lines().filter(|l| ((l.advance_scale - 1.12).abs() < 0.01) == reference).collect();
    let first = lines.first()?;
    Some(Placed {
        size: f64::from(first.size),
        lines: lines.iter().map(|l| l.text.clone()).collect(),
        baseline: f64::from(first.baseline),
    })
}

fn accent(list: &DisplayList) -> Option<[f64; 4]> {
    list.items.iter().find_map(|item| match item {
        Item::LinearGradient { x, y, w, h, .. } => Some([f64::from(*x), f64::from(*y), f64::from(*w), f64::from(*h)]),
        _ => None,
    })
}

fn close(a: f64, b: f64) -> bool {
    (a - b).abs() <= TOLERANCE
}

/// Compare et écrit `projection-rapport.json` à côté des références.
pub fn compare(dir: &Path) -> Result<bool> {
    let text = std::fs::read_to_string(dir.join("projection.json")).context("lecture de projection.json")?;
    let refs: Value = serde_json::from_str(&text)?;
    let mut fonts = Fonts::from_dirs(&[bundled_fonts_dir()]);
    let mut designs = BTreeMap::new();
    for (name, config) in refs["configs"].as_object().into_iter().flatten() {
        designs.insert(name.clone(), design(config));
    }
    let mut tallies: BTreeMap<String, Tally> = BTreeMap::new();
    let mut examples = Vec::new();
    let mut probe = |_: &DisplayList, _: [f32; 4]| 0.0f32;
    let mut total = Tally::default();
    for case in refs["cas"].as_array().into_iter().flatten() {
        let config = case["config"].as_str().unwrap_or_default();
        let kind = case["kind"].as_str().unwrap_or_default();
        let Some(design) = designs.get(config) else { continue };
        let slide = Slide::new(
            case["text"].as_str().unwrap_or_default(),
            case["reference"].as_str().unwrap_or_default(),
            source(kind),
        );
        let list = layout_room(&mut fonts, &slide, design, 1920.0, 1080.0, &mut probe);
        let ours = placed(&list, false);
        let ours_ref = placed(&list, true);
        let theirs = &case["texte"];
        let theirs_ref = &case["reference_posee"];
        let lines28: Vec<String> = theirs["lines"]
            .as_array()
            .into_iter()
            .flatten()
            .map(|l| l.as_str().unwrap_or_default().to_string())
            .collect();
        let same_size = ours.as_ref().map(|p| p.size) == theirs["size"].as_f64();
        let same_lines = ours.as_ref().map(|p| p.lines.clone()).unwrap_or_default() == lines28;
        let shift = match (&ours, theirs["baseline"].as_f64()) {
            (Some(p), Some(b)) => (p.baseline - b).abs(),
            _ => 0.0,
        };
        let same_place = match (&ours, theirs["baseline"].as_f64()) {
            (Some(p), Some(b)) => close(p.baseline, b),
            (None, None) => true,
            _ => false,
        };
        let same_ref = match (&ours_ref, theirs_ref.is_null()) {
            (None, true) => true,
            (Some(p), false) => {
                Some(p.size) == theirs_ref["size"].as_f64()
                    && theirs_ref["baseline"].as_f64().is_some_and(|b| close(p.baseline, b))
            }
            _ => false,
        };
        let theirs_accent: Option<[f64; 4]> = case["filet"].as_array().map(|a| {
            let v = |i: usize| a.get(i).and_then(Value::as_f64).unwrap_or(0.0);
            [v(0), v(1), v(2), v(3)]
        });
        let same_accent = match (accent(&list), theirs_accent) {
            (Some(a), Some(b)) => a.iter().zip(b).all(|(x, y)| close(*x, y)),
            (None, None) => true,
            _ => false,
        };
        for tally in [tallies.entry(format!("{config} / {kind}")).or_default(), &mut total] {
            tally.cases += 1;
            tally.size += usize::from(same_size);
            tally.lines += usize::from(same_lines);
            tally.baseline += usize::from(same_place);
            tally.reference += usize::from(same_ref);
            tally.accent += usize::from(same_accent);
            tally.max_shift = tally.max_shift.max(shift);
        }
        if !(same_size && same_lines && same_place && same_ref && same_accent) && examples.len() < 60 {
            examples.push(json!({
                "config": config, "kind": kind, "index": case["index"].clone(),
                "lignes_30_toutes": list.text_lines().map(|l| (l.text.clone(), l.baseline, l.size)).collect::<Vec<_>>(),
                "taille": [theirs["size"].clone(), ours.as_ref().map(|p| p.size)],
                "lignes_28": lines28.len(), "lignes_30": ours.as_ref().map_or(0, |p| p.lines.len()),
                "premiere_ligne": [lines28.first(), ours.as_ref().and_then(|p| p.lines.first())],
                "base": [theirs["baseline"].clone(), ours.as_ref().map(|p| p.baseline)],
                "reference": [theirs_ref["size"].clone(), theirs_ref["baseline"].clone(),
                              ours_ref.as_ref().map(|p| (p.size, p.baseline))],
                "filet": [case["filet"].clone(), accent(&list)],
            }));
        }
    }
    println!("Mise en page de la projection, 2.8 → 3.0 ({} slides) :", total.cases);
    for (name, tally) in tallies.iter().chain(std::iter::once((&"total".to_string(), &total))) {
        let j = tally.json();
        println!(
            "  {name:32} taille {:5.1} %  lignes {:5.1} %  place {:5.1} %  référence {:5.1} %  filet {:5.1} %  écart max {:.2} px",
            j["meme_taille_pct"].as_f64().unwrap_or(0.0),
            j["memes_lignes_pct"].as_f64().unwrap_or(0.0),
            j["meme_place_pct"].as_f64().unwrap_or(0.0),
            j["meme_reference_pct"].as_f64().unwrap_or(0.0),
            j["meme_filet_pct"].as_f64().unwrap_or(0.0),
            j["ecart_max_px"].as_f64().unwrap_or(0.0),
        );
    }
    let report = json!({
        "par_groupe": tallies.iter().map(|(k, t)| (k.clone(), t.json())).collect::<Map<_, _>>(),
        "total": total.json(),
        "exemples": examples,
    });
    std::fs::write(dir.join("projection-rapport.json"), serde_json::to_string_pretty(&report)?)?;
    Ok(total.size == total.cases && total.lines == total.cases)
}
