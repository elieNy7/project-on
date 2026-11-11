//! L'historique du culte (`service_log.py` de la 2.8, Ctrl+H) : chaque slide mis au direct est noté
//! avec son heure, un fichier par jour (`data\historique\AAAA-MM-JJ.jsonl`, une ligne par slide,
//! ajoutée sans réécrire le reste). On le relit, et on l'exporte en tableur (CSV) ou en sous-titres
//! (SRT, calés sur le début de l'enregistrement vidéo), comme la 2.8.

use std::io::Write;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

/// Un slide passé au direct.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Event {
    /// Secondes depuis minuit (heure locale).
    pub at: f64,
    pub reference: String,
    pub text: String,
    /// `bible`, `hymn`, `sermon`…
    pub kind: String,
}

/// Le fichier du jour (`date` : « 2026-11-11 »).
pub fn file(data_dir: &Path, date: &str) -> PathBuf {
    data_dir.join("historique").join(format!("{date}.jsonl"))
}

/// Ajoute un slide au fichier du jour. Le même slide deux fois de suite n'est noté qu'une fois.
pub fn record(path: &Path, event: &Event) -> std::io::Result<()> {
    if read(path).last().is_some_and(|last| last.reference == event.reference && last.text == event.text) {
        return Ok(());
    }
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let line = serde_json::to_string(event).map_err(std::io::Error::other)?;
    let mut f = std::fs::OpenOptions::new().create(true).append(true).open(path)?;
    writeln!(f, "{line}")
}

/// Les slides du jour, dans l'ordre (une ligne abîmée est sautée).
pub fn read(path: &Path) -> Vec<Event> {
    std::fs::read_to_string(path)
        .map(|t| t.lines().filter_map(|l| serde_json::from_str(l).ok()).collect())
        .unwrap_or_default()
}

/// « 10:42:05 ».
pub fn clock(seconds: f64) -> String {
    let s = seconds.max(0.0) as u64;
    format!("{:02}:{:02}:{:02}", s / 3600 % 24, s % 3600 / 60, s % 60)
}

fn csv_field(value: &str) -> String {
    if value.contains([';', '"', '\n', '\r']) {
        format!("\"{}\"", value.replace('"', "\"\""))
    } else {
        value.to_string()
    }
}

/// Le tableur : heure, durée, genre, référence, texte (séparateur « ; » pour Excel en français).
pub fn to_csv(events: &[Event]) -> String {
    let mut out = String::from("\u{feff}Heure;Durée (s);Genre;Référence;Texte\r\n");
    for (i, e) in events.iter().enumerate() {
        let duration =
            events.get(i + 1).map_or(String::new(), |next| ((next.at - e.at).max(0.0).round() as u64).to_string());
        out.push_str(&format!(
            "{};{};{};{};{}\r\n",
            clock(e.at),
            duration,
            csv_field(&e.kind),
            csv_field(&e.reference.replace('\n', " — ")),
            csv_field(&e.text.replace('\n', " "))
        ));
    }
    out
}

/// Les sous-titres d'une vidéo commencée à `origin` (secondes depuis minuit) : chaque slide dure
/// jusqu'au suivant, 30 s au plus (`to_srt` de la 2.8 : texte, puis « — référence »).
pub fn to_srt(events: &[Event], origin: f64) -> String {
    const MAX: f64 = 30.0;
    let mut cues = Vec::new();
    for (i, e) in events.iter().enumerate() {
        let next = events.get(i + 1).map_or(e.at + MAX, |n| n.at);
        let (start, stop) = (e.at.max(origin), next.min(e.at + MAX));
        if stop <= origin || stop <= start {
            continue;
        }
        let text = e.text.trim();
        let reference = e.reference.replace('\n', " — ");
        let reference = reference.trim();
        let body = match (text.is_empty(), reference.is_empty()) {
            (false, false) => format!("{text}\n— {reference}"),
            (false, true) => text.to_string(),
            (true, _) => reference.to_string(),
        };
        if body.is_empty() {
            continue;
        }
        cues.push(po_text::srt::Cue {
            start_ms: ((start - origin) * 1000.0).round() as u64,
            end_ms: ((stop - origin) * 1000.0).round() as u64,
            text: body,
        });
    }
    po_text::srt::format(&cues)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn event(at: f64, reference: &str, text: &str) -> Event {
        Event { at, reference: reference.into(), text: text.into(), kind: "bible".into() }
    }

    #[test]
    fn the_day_is_recorded_line_by_line_and_exported() {
        let dir = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/tmp")
            .join(format!("historique-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let path = file(&dir, "2026-11-11");
        record(&path, &event(36_000.0, "Jean 3:16", "Car Dieu a tant aimé le monde")).unwrap();
        record(&path, &event(36_001.0, "Jean 3:16", "Car Dieu a tant aimé le monde")).unwrap();
        record(&path, &event(36_012.5, "Jean 3:17", "Dieu, en effet; n'a pas envoyé \"son\" Fils")).unwrap();
        let events = read(&path);
        assert_eq!(events.len(), 2, "le même slide deux fois de suite : une ligne");
        let csv = to_csv(&events);
        assert!(csv.starts_with("\u{feff}Heure;"));
        assert!(csv.contains("10:00:00;13;bible;Jean 3:16;Car Dieu a tant aimé le monde\r\n"));
        assert!(csv.contains("\"Dieu, en effet; n'a pas envoyé \"\"son\"\" Fils\""));
        // Une vidéo commencée à 10:00:05 : le premier slide commence à 0, le second à 7,5 s.
        let srt = to_srt(&events, 36_005.0);
        let cues = po_text::srt::parse(&srt);
        assert_eq!(cues.len(), 2);
        assert_eq!((cues[0].start_ms, cues[0].end_ms), (0, 7_500));
        assert_eq!(cues[0].text, "Car Dieu a tant aimé le monde\n— Jean 3:16");
        assert_eq!((cues[1].start_ms, cues[1].end_ms), (7_500, 37_500), "30 s au plus");
        let _ = std::fs::remove_dir_all(&dir);
    }
}
