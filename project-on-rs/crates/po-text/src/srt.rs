//! Les sous-titres SRT : lecture (fichiers de la 2.x, d'un logiciel de montage, d'Internet),
//! écriture (`to_srt` de la 2.8 : `HH:MM:SS,mmm`, blocs séparés d'une ligne vide) et recherche du
//! sous-titre à un instant d'une vidéo.

/// Un sous-titre : de `start_ms` à `end_ms` (exclu), son texte (une ou plusieurs lignes).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Cue {
    pub start_ms: u64,
    pub end_ms: u64,
    pub text: String,
}

/// `00:01:02,345` (ou `00:01:02.345`, ou sans heures `01:02,345`) → millisecondes.
fn parse_time(text: &str) -> Option<u64> {
    let text = text.trim();
    let (clock, millis) = match text.rsplit_once([',', '.']) {
        Some((c, m)) => (c, m),
        None => (text, "0"),
    };
    let millis: u64 = {
        let digits: String = millis.chars().take_while(char::is_ascii_digit).collect();
        if digits.is_empty() {
            return None;
        }
        // « ,5 » vaut 500 ms, « ,05 » 50 ms.
        let value: u64 = digits.parse().ok()?;
        match digits.len() {
            1 => value * 100,
            2 => value * 10,
            3 => value,
            n => value / 10u64.pow(n as u32 - 3),
        }
    };
    let parts: Vec<u64> = clock.split(':').map(|p| p.trim().parse().ok()).collect::<Option<_>>()?;
    let seconds = match parts.as_slice() {
        [h, m, s] => h * 3600 + m * 60 + s,
        [m, s] => m * 60 + s,
        [s] => *s,
        _ => return None,
    };
    Some(seconds * 1000 + millis)
}

/// `HH:MM:SS,mmm` (`_srt_time` de la 2.8).
pub fn format_time(ms: u64) -> String {
    let (hours, rest) = (ms / 3_600_000, ms % 3_600_000);
    let (minutes, rest) = (rest / 60_000, rest % 60_000);
    let (seconds, millis) = (rest / 1000, rest % 1000);
    format!("{hours:02}:{minutes:02}:{seconds:02},{millis:03}")
}

/// Lit un fichier SRT. Tolère : BOM, fins de ligne Windows, numéros absents ou faux, lignes vides
/// en trop, balises `<i>` / `{\an8}`. Les blocs illisibles sont sautés. Les sous-titres sont rendus
/// dans l'ordre du temps.
pub fn parse(text: &str) -> Vec<Cue> {
    let text = text.trim_start_matches('\u{feff}').replace("\r\n", "\n").replace('\r', "\n");
    let mut cues = Vec::new();
    let lines: Vec<&str> = text.lines().collect();
    let mut i = 0;
    while i < lines.len() {
        // Le prochain horaire « début --> fin ».
        let Some((start, end)) = lines[i].split_once("-->") else {
            i += 1;
            continue;
        };
        let end = end.split_whitespace().next().unwrap_or("");
        let (Some(start_ms), Some(end_ms)) = (parse_time(start), parse_time(end)) else {
            i += 1;
            continue;
        };
        i += 1;
        let mut body = Vec::new();
        while i < lines.len() && !lines[i].trim().is_empty() {
            // Un horaire sans ligne vide avant : un nouveau bloc commence (le numéro est déjà lu).
            if lines[i].contains("-->") {
                if body.last().is_some_and(|l: &String| l.trim().chars().all(|c| c.is_ascii_digit())) {
                    body.pop();
                }
                break;
            }
            body.push(strip_tags(lines[i]));
            i += 1;
        }
        let text = body.join("\n").trim().to_string();
        if end_ms > start_ms && !text.is_empty() {
            cues.push(Cue { start_ms, end_ms, text });
        }
    }
    cues.sort_by_key(|c| c.start_ms);
    cues
}

/// Retire les balises HTML (`<i>`, `<font …>`) et de position (`{\an8}`) d'une ligne.
fn strip_tags(line: &str) -> String {
    let mut out = String::new();
    let mut depth_angle = false;
    let mut depth_brace = false;
    for c in line.chars() {
        match c {
            '<' => depth_angle = true,
            '>' if depth_angle => depth_angle = false,
            '{' => depth_brace = true,
            '}' if depth_brace => depth_brace = false,
            _ if depth_angle || depth_brace => {}
            _ => out.push(c),
        }
    }
    out.trim_end().to_string()
}

/// Écrit des sous-titres en SRT, numérotés à partir de 1.
pub fn format(cues: &[Cue]) -> String {
    cues.iter()
        .enumerate()
        .map(|(i, c)| {
            format!("{}\n{} --> {}\n{}\n", i + 1, format_time(c.start_ms), format_time(c.end_ms), c.text.trim())
        })
        .collect::<Vec<_>>()
        .join("\n")
}

/// Le sous-titre affiché à `ms` (le dernier commencé, s'il n'est pas fini).
pub fn cue_at(cues: &[Cue], ms: u64) -> Option<&Cue> {
    let after = cues.partition_point(|c| c.start_ms <= ms);
    cues[..after].iter().rev().find(|c| ms < c.end_ms)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_what_the_2x_writes() {
        // La forme exacte de `to_srt` (service_log.py) : numéro, horaire, texte, « — référence ».
        let srt = "1\n00:00:00,000 --> 00:00:12,500\nCar Dieu a tant aimé le monde\n— Jean 3:16\n\n\
                   2\n00:00:12,500 --> 00:01:03,040\nLa foi est une ferme assurance\n— Hébreux 11:1\n";
        let cues = parse(srt);
        assert_eq!(cues.len(), 2);
        assert_eq!(
            cues[0],
            Cue { start_ms: 0, end_ms: 12_500, text: "Car Dieu a tant aimé le monde\n— Jean 3:16".into() }
        );
        assert_eq!(cues[1].end_ms, 63_040);
        // Écrire puis relire redonne la même chose, au caractère près.
        assert_eq!(format(&cues), srt.trim_end_matches('\n').to_string() + "\n");
        assert_eq!(parse(&format(&cues)), cues);
    }

    #[test]
    fn tolerates_real_world_files() {
        let srt = "\u{feff}5\r\n00:00:01.5 --> 00:00:03,25 X1:0\r\n<i>Bonjour</i> {\\an8}à tous\r\n\r\n\r\n\
                   00:00:04,000 --> 00:00:05,000\r\nSans numéro\r\n7\r\n00:00:06,000 --> 00:00:07,000\r\nCollé\r\n\r\n\
                   x\n99:99 --> faux\nignoré\n\n00:00:09,000 --> 00:00:08,000\nà l'envers\n";
        let cues = parse(srt);
        let texts: Vec<_> = cues.iter().map(|c| c.text.as_str()).collect();
        assert_eq!(texts, ["Bonjour à tous", "Sans numéro", "Collé"]);
        assert_eq!((cues[0].start_ms, cues[0].end_ms), (1500, 3250));
        assert_eq!(format_time(3_723_004), "01:02:03,004");
    }

    #[test]
    fn finds_the_cue_at_a_time() {
        let cues = parse("1\n00:00:01,000 --> 00:00:02,000\nA\n\n2\n00:00:03,000 --> 00:00:05,000\nB\n");
        assert_eq!(cue_at(&cues, 500), None);
        assert_eq!(cue_at(&cues, 1000).map(|c| c.text.as_str()), Some("A"));
        assert_eq!(cue_at(&cues, 2500), None, "entre deux sous-titres : rien");
        assert_eq!(cue_at(&cues, 4999).map(|c| c.text.as_str()), Some("B"));
        assert_eq!(cue_at(&cues, 5000), None);
    }
}
