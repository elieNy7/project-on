//! L'habillage du direct : le **lower third** (touche L), affiché à la main ou automatiquement avec
//! le contenu du direct, et les **sous-titres** (touche S), un long paragraphe découpé en morceaux
//! que l'on fait avancer avec ← et →. Ils partent vers la diffusion (Web, NDI) et la sortie HDMI ;
//! la salle garde le slide entier.

use std::time::Instant;

use po_design::SlideSource;
use po_design::graphics::{LowerThirdStyle, LowerThirdText, Purpose, SubtitleStyle};
use po_layout::Slide;

/// Le lower third.
#[derive(Debug, Clone)]
pub struct LowerThird {
    pub id: String,
    pub name: String,
    pub style: LowerThirdStyle,
    /// Le texte saisi (mode manuel).
    pub text: LowerThirdText,
    /// Le texte suit le direct (référence biblique, sermon, cantique).
    pub auto: bool,
    /// Affiché (ou en train d'entrer), sinon masqué (ou en train de sortir).
    pub shown: bool,
    /// Depuis quand il entre ou sort.
    pub since: Instant,
    /// Déjà affiché une fois (avant : rien ne sort).
    toggled: bool,
}

impl LowerThird {
    pub fn new(id: &str, name: &str, style: LowerThirdStyle) -> Self {
        LowerThird {
            id: id.into(),
            name: name.into(),
            style,
            text: LowerThirdText::default(),
            auto: false,
            shown: false,
            since: Instant::now(),
            toggled: false,
        }
    }

    /// Affiche ou masque (touche L).
    pub fn toggle(&mut self) {
        self.shown = !self.shown;
        self.since = Instant::now();
        self.toggled = true;
    }

    pub fn set_shown(&mut self, shown: bool) {
        if self.shown != shown {
            self.toggle();
        }
    }

    /// Le texte à montrer : celui saisi, ou celui du direct.
    pub fn current_text(&self, live: Option<(&Slide, &str)>) -> LowerThirdText {
        if !self.auto {
            return self.text.clone();
        }
        live.map(|(slide, title)| auto_text(slide, title, self.style.purpose)).unwrap_or_default()
    }

    /// Encore visible (affiché, ou en train de sortir) ?
    pub fn visible(&self, now: Instant) -> bool {
        self.shown
            || (self.toggled && now.duration_since(self.since).as_millis() < u128::from(self.style.motion.duration_ms))
    }
}

/// La référence sans son « (2/5) » de découpage.
fn bare_reference(reference: &str) -> String {
    let first = reference.lines().next().unwrap_or("").trim();
    match first.rfind(" (") {
        Some(i) if first.ends_with(')') && first[i + 2..first.len() - 1].contains('/') => first[..i].trim().to_string(),
        _ => first.to_string(),
    }
}

/// Le texte automatique d'un lower third, d'après le slide au direct et le titre de son programme.
pub fn auto_text(slide: &Slide, program_title: &str, purpose: Purpose) -> LowerThirdText {
    let reference = bare_reference(&slide.reference);
    match slide.source {
        SlideSource::Bible => LowerThirdText::new(reference, if purpose == Purpose::Bible { "Bible" } else { "" }),
        SlideSource::Sermon | SlideSource::Expose | SlideSource::Brochure | SlideSource::Book => {
            // « 1953-09-12 - La Foi » : le titre en grand, la date dessous.
            match program_title.split_once(" - ") {
                Some((date, title)) => LowerThirdText::new(title.trim(), date.trim()),
                None => LowerThirdText::new(program_title.trim(), ""),
            }
        }
        SlideSource::Hymn => match reference.split_once(" - ") {
            Some((number, title)) => LowerThirdText::new(title.trim(), format!("Cantique {}", number.trim())),
            None => LowerThirdText::new(reference, "Cantique"),
        },
        SlideSource::Custom => LowerThirdText::new(reference, ""),
    }
}

/// Les sous-titres.
#[derive(Debug, Clone)]
pub struct Subtitles {
    pub id: String,
    pub name: String,
    pub style: SubtitleStyle,
    /// Affichés : d'office (l'écran « sous-titres » montre le direct dès qu'on l'ouvre, demande
    /// du 12 novembre 2026) ; la touche S les masque et les réaffiche.
    pub shown: bool,
    /// Les morceaux du slide au direct, et celui affiché.
    pub chunks: Vec<String>,
    pub index: usize,
    /// Le slide découpé (pour ne le redécouper que s'il change).
    pub cut_for: Option<(String, String)>,
}

impl Subtitles {
    pub fn new(id: &str, name: &str, style: SubtitleStyle) -> Self {
        Subtitles { id: id.into(), name: name.into(), style, shown: true, chunks: Vec::new(), index: 0, cut_for: None }
    }

    /// Le morceau affiché.
    pub fn current(&self) -> Option<&str> {
        self.shown.then(|| self.chunks.get(self.index).map(String::as_str)).flatten()
    }

    /// Avance (`+1`) ou recule (`-1`) d'un morceau ; `false` au bord (le slide change alors).
    pub fn step(&mut self, delta: i32) -> bool {
        if !self.shown {
            return false;
        }
        if delta > 0 && self.index + 1 < self.chunks.len() {
            self.index += 1;
            true
        } else if delta < 0 && self.index > 0 {
            self.index -= 1;
            true
        } else {
            false
        }
    }

    /// Un nouveau slide au direct : ses morceaux, depuis le premier (ou le dernier si l'on recule).
    pub fn cut(&mut self, slide: &Slide, chunks: Vec<String>, from_end: bool) {
        self.cut_for = Some((slide.text.clone(), slide.reference.clone()));
        self.index = if from_end { chunks.len().saturating_sub(1) } else { 0 };
        self.chunks = chunks;
    }

    pub fn needs_cut(&self, slide: &Slide) -> bool {
        self.cut_for.as_ref().is_none_or(|(text, reference)| *text != slide.text || *reference != slide.reference)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use po_design::graphics::{SubtitleLook, builtin_lower_thirds};

    #[test]
    fn the_automatic_text_follows_the_live_content() {
        let verse = Slide::new("Car Dieu a tant aimé…", "Jean 3:16 (1/2)", SlideSource::Bible);
        assert_eq!(auto_text(&verse, "Jean 3", Purpose::Bible), LowerThirdText::new("Jean 3:16", "Bible"));
        let paragraph = Slide::new("…", "1953-09-12 - La Foi - 2", SlideSource::Sermon);
        assert_eq!(
            auto_text(&paragraph, "1953-09-12 - La Foi", Purpose::Sermon),
            LowerThirdText::new("La Foi", "1953-09-12")
        );
        let stanza = Slide::new("…", "12 - À toi la gloire\nRefrain", SlideSource::Hymn);
        assert_eq!(auto_text(&stanza, "", Purpose::Generic), LowerThirdText::new("À toi la gloire", "Cantique 12"));
    }

    #[test]
    fn showing_and_hiding_animates_then_disappears() {
        let (_, _, _, style) = builtin_lower_thirds().remove(1);
        let mut lt = LowerThird::new("lt", "Essai", style);
        let now = Instant::now();
        assert!(!lt.visible(now));
        lt.toggle();
        assert!(lt.shown && lt.visible(now));
        lt.toggle();
        assert!(lt.visible(Instant::now()), "il sort en douceur");
        assert!(!lt.visible(Instant::now() + std::time::Duration::from_secs(5)));
        lt.text = LowerThirdText::new("Frère Paul", "Ancien");
        assert_eq!(lt.current_text(None), LowerThirdText::new("Frère Paul", "Ancien"));
    }

    #[test]
    fn subtitles_step_through_chunks_before_the_slide_changes() {
        let mut st = Subtitles::new("st", "Essai", SubtitleStyle::new(SubtitleLook::Translucent));
        let slide = Slide::new("a b c", "Réf", SlideSource::Custom);
        st.cut(&slide, vec!["a".into(), "b".into(), "c".into()], false);
        assert_eq!(st.current(), Some("a"), "affichés d'office");
        st.shown = false;
        assert_eq!(st.current(), None, "masqués (S)");
        assert!(!st.step(1), "masqués : le slide change");
        st.shown = true;
        assert_eq!(st.current(), Some("a"));
        assert!(st.step(1) && st.step(1));
        assert_eq!(st.current(), Some("c"));
        assert!(!st.step(1), "au dernier morceau, → change de slide");
        assert!(st.step(-1));
        assert!(!st.needs_cut(&slide));
        st.cut(&slide, vec!["x".into(), "y".into()], true);
        assert_eq!(st.current(), Some("y"), "en reculant, on arrive au dernier morceau");
    }
}
