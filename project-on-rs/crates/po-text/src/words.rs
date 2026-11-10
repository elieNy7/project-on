//! Les mots d'un paragraphe pour la mise en page (`SlideCanvas._words`).

/// La ponctuation qui reste collée au mot précédent : `; : ! ? » …` (suivie au plus d'un point
/// ou d'une virgule).
fn glues_to_previous(token: &str) -> bool {
    let body = token.strip_suffix(['.', ',']).unwrap_or(token);
    !body.is_empty() && body.chars().all(|c| matches!(c, ';' | ':' | '!' | '?' | '»' | '…'))
}

/// Les mots d'un paragraphe, la ponctuation française restant collée : « Amen ! » ne se coupe
/// jamais avant le point d'exclamation, ni après un guillemet ouvrant.
pub fn words(paragraph: &str) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    let mut opening: Option<String> = None;
    for raw in paragraph.split_whitespace() {
        let token = match opening.take() {
            Some(open) => format!("{open} {raw}"),
            None => raw.to_string(),
        };
        if token == "«" {
            opening = Some(token);
        } else if let Some(last) = out.last_mut().filter(|_| glues_to_previous(&token)) {
            last.push(' ');
            last.push_str(&token);
        } else {
            out.push(token);
        }
    }
    if let Some(open) = opening {
        out.push(open);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn french_punctuation_stays_glued() {
        assert_eq!(words("Il a dit : « Amen ! » Et voilà…"), ["Il", "a", "dit :", "« Amen ! »", "Et", "voilà…"]);
        assert_eq!(words("Gloire ! ?."), ["Gloire ! ?."]);
        assert_eq!(words("«"), ["«"]);
    }
}
