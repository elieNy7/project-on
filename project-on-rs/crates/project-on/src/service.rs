//! Le déroulé du culte (`app/utils/service_plan.py` de la 2.8) : les sections d'une playlist avec
//! leur durée, l'heure de début prévue, la section en cours, l'avance ou le retard en direct et la
//! fin estimée. Une section liée à un slide démarre toute seule quand ce slide passe au direct.
//!
//! Les heures sont des secondes depuis minuit (un culte ne passe pas minuit).

use std::collections::HashMap;

/// Une section du déroulé.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PlanSection {
    pub id: i64,
    pub name: String,
    pub duration_min: i64,
    /// Le slide de la playlist qui la commence.
    pub item_id: Option<i64>,
}

/// « 9h30 », « 09:30 », « 9 » → (9, 30) ; `None` si vide ou invalide (`parse_start_time`).
pub fn parse_start_time(value: &str) -> Option<(u32, u32)> {
    let v = value.trim();
    let digits_end = v.find(|c: char| !c.is_ascii_digit()).unwrap_or(v.len());
    let (h, rest) = v.split_at(digits_end);
    if h.is_empty() || h.len() > 2 {
        return None;
    }
    let rest = rest.trim();
    let minutes = if rest.is_empty() {
        0
    } else {
        let mut chars = rest.chars();
        let sep = chars.next()?;
        if !matches!(sep, ':' | 'h' | 'H' | '.') {
            return None;
        }
        let m = chars.as_str().trim();
        if m.is_empty() {
            0
        } else if m.len() <= 2 && m.chars().all(|c| c.is_ascii_digit()) {
            m.parse().ok()?
        } else {
            return None;
        }
    };
    let hours: u32 = h.parse().ok()?;
    (hours <= 23 && minutes <= 59).then_some((hours, minutes))
}

/// « 5:00 », « 1:02:03 » (`format_duration`).
pub fn format_duration(seconds: f64) -> String {
    let s = seconds.abs().round() as i64;
    let (hours, rest) = (s / 3600, s % 3600);
    let (minutes, secs) = (rest / 60, rest % 60);
    if hours > 0 { format!("{hours}:{minutes:02}:{secs:02}") } else { format!("{minutes}:{secs:02}") }
}

/// « à l'heure », « 5:00 de retard », « 2:30 d'avance » (`describe_delay`).
pub fn describe_delay(delay: f64) -> String {
    if delay.abs() < 60.0 {
        return "à l'heure".into();
    }
    let text = format_duration(delay);
    if delay > 0.0 { format!("{text} de retard") } else { format!("{text} d'avance") }
}

/// « 10:00 » pour une heure en secondes depuis minuit.
pub fn clock(seconds: f64) -> String {
    let s = seconds.max(0.0).round() as i64;
    format!("{:02}:{:02}", (s / 3600) % 24, (s % 3600) / 60)
}

/// L'état du déroulé à un instant.
#[derive(Debug, Clone, PartialEq)]
pub struct Status {
    pub index: usize,
    pub name: String,
    pub elapsed: f64,
    /// Négatif : la section déborde.
    pub remaining: f64,
    /// Positif : du retard ; négatif : de l'avance.
    pub delay: f64,
    pub expected_end: f64,
}

/// La section en cours et l'écart au programme (`ServiceTracker`).
#[derive(Debug, Clone, Default)]
pub struct Tracker {
    pub sections: Vec<PlanSection>,
    pub started_at: Option<f64>,
    pub current: Option<usize>,
    entered_at: Option<f64>,
    pub actual_starts: HashMap<usize, f64>,
}

impl Tracker {
    pub fn new(sections: Vec<PlanSection>) -> Self {
        Tracker { sections, ..Tracker::default() }
    }

    /// La minute de début prévue de la section `index`, depuis le début du culte.
    pub fn planned_offset_min(&self, index: usize) -> i64 {
        self.sections.iter().take(index).map(|s| s.duration_min).sum()
    }

    pub fn planned_start(&self, index: usize, start: f64) -> f64 {
        start + self.planned_offset_min(index) as f64 * 60.0
    }

    pub fn total_min(&self) -> i64 {
        self.sections.iter().map(|s| s.duration_min).sum()
    }

    pub fn running(&self) -> bool {
        self.started_at.is_some() && self.current.is_some_and(|c| c < self.sections.len())
    }

    pub fn start(&mut self, now: f64) {
        self.started_at = Some(now);
        self.actual_starts.clear();
        self.current = None;
        if !self.sections.is_empty() {
            self.enter(0, now);
        }
    }

    pub fn stop(&mut self) {
        self.started_at = None;
        self.current = None;
        self.entered_at = None;
    }

    pub fn enter(&mut self, index: usize, now: f64) -> bool {
        if index >= self.sections.len() {
            return false;
        }
        self.started_at.get_or_insert(now);
        self.current = Some(index);
        self.entered_at = Some(now);
        self.actual_starts.entry(index).or_insert(now);
        true
    }

    /// Section suivante ; rien après la dernière.
    pub fn next(&mut self, now: f64) -> bool {
        let next = self.current.map_or(0, |c| c + 1);
        self.enter(next, now)
    }

    /// Un slide passe au direct : la section qui commence par lui démarre (pas deux fois).
    pub fn enter_item(&mut self, item_id: i64, now: f64) -> bool {
        let Some(index) = self.sections.iter().position(|s| s.item_id == Some(item_id)) else { return false };
        if Some(index) == self.current {
            return false;
        }
        self.enter(index, now)
    }

    /// L'état lisible à `now` ; l'écart compare l'entrée réelle dans la section à son heure prévue
    /// (depuis `reference_start`, l'heure de début prévue, sinon le démarrage), puis compte son
    /// dépassement : un retard grandit en direct quand la section déborde.
    pub fn status(&self, now: f64, reference_start: Option<f64>) -> Option<Status> {
        let base = reference_start.or(self.started_at)?;
        if !self.running() {
            return None;
        }
        let index = self.current?;
        let entered = self.entered_at?;
        let section = &self.sections[index];
        let elapsed = now - entered;
        let planned = section.duration_min as f64 * 60.0;
        let late_entry = entered - self.planned_start(index, base);
        let delay = late_entry + (elapsed - planned).max(0.0);
        let expected_end = self.planned_start(self.sections.len(), base) + delay.max(0.0);
        Some(Status { index, name: section.name.clone(), elapsed, remaining: planned - elapsed, delay, expected_end })
    }
}

/// L'heure locale, en secondes depuis minuit.
pub fn now_seconds() -> f64 {
    #[cfg(windows)]
    {
        use windows::Win32::System::SystemInformation::GetLocalTime;
        // SAFETY : GetLocalTime remplit une structure qu'on lui donne, sans autre effet.
        #[allow(unsafe_code)]
        let t = unsafe { GetLocalTime() };
        f64::from(t.wHour) * 3600.0
            + f64::from(t.wMinute) * 60.0
            + f64::from(t.wSecond)
            + f64::from(t.wMilliseconds) / 1000.0
    }
    #[cfg(not(windows))]
    {
        0.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn t(h: u32, m: u32) -> f64 {
        f64::from(h * 3600 + m * 60)
    }

    #[test]
    fn start_times_like_the_2x() {
        assert_eq!(parse_start_time("9:30"), Some((9, 30)));
        assert_eq!(parse_start_time("09h30"), Some((9, 30)));
        assert_eq!(parse_start_time("10"), Some((10, 0)));
        assert_eq!(parse_start_time(" 9 h "), Some((9, 0)));
        assert_eq!(parse_start_time("25:00"), None);
        assert_eq!(parse_start_time("9:75"), None);
        assert_eq!(parse_start_time(""), None);
        assert_eq!(parse_start_time("midi"), None);
    }

    /// `test_tracker_delay_and_overrun` de la 2.8, valeur pour valeur.
    #[test]
    fn delay_and_overrun_like_the_2x() {
        let mut tracker = Tracker::new(vec![
            PlanSection { id: 1, name: "Louange".into(), duration_min: 30, item_id: None },
            PlanSection { id: 2, name: "Annonces".into(), duration_min: 10, item_id: Some(7) },
            PlanSection { id: 3, name: "Prédication".into(), duration_min: 45, item_id: None },
        ]);
        let start = Some(t(9, 30));
        tracker.start(t(9, 32));
        let s = tracker.status(t(9, 40), start).unwrap();
        assert_eq!(s.name, "Louange");
        assert_eq!(s.delay, 120.0, "commencé 2 min en retard");
        // La louange déborde : le retard grandit en direct.
        let s = tracker.status(t(10, 5), start).unwrap();
        assert_eq!(s.delay, 120.0 + 3.0 * 60.0);
        assert!(s.remaining < 0.0);
        // Le slide lié aux annonces passe au direct : section suivante.
        assert!(tracker.enter_item(7, t(10, 5)));
        assert!(!tracker.enter_item(7, t(10, 6)), "déjà en cours");
        let s = tracker.status(t(10, 6), start).unwrap();
        assert_eq!((s.name.as_str(), s.delay), ("Annonces", 5.0 * 60.0));
        assert_eq!(s.expected_end, t(11, 0), "10:55 prévu + 5 min");
        assert!(tracker.next(t(10, 5)), "annonces écourtées");
        let s = tracker.status(t(10, 5), start).unwrap();
        assert_eq!((s.name.as_str(), s.delay), ("Prédication", -5.0 * 60.0));
        assert_eq!(describe_delay(s.delay), "5:00 d'avance");
        assert!(!tracker.next(t(11, 0)), "dernière section");
        assert_eq!(clock(tracker.planned_start(2, t(9, 30))), "10:10");
        assert_eq!(format_duration(3723.0), "1:02:03");
    }
}
