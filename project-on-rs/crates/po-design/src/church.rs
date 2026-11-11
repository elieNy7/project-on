//! Le profil de l'église (`ChurchProfile` de la 2.8, section `church` des réglages) : son nom, sa
//! devise, son logo, ses horaires, ses réseaux, son pasteur et l'orateur du jour. Il sert aux écrans
//! de l'église (accueil, orateur du jour, réseaux sociaux). Lu et réécrit au même format que la 2.x.

use serde_json::{Map, Value, json};

use crate::{Rgba, parse_color};

/// Un réseau social : clé, nom, couleur de la pastille, exemple.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SocialPlatform {
    pub key: &'static str,
    pub label: &'static str,
    pub color: &'static str,
    pub placeholder: &'static str,
}

/// Les réseaux, dans l'ordre de la 2.8.
pub const SOCIAL_PLATFORMS: [SocialPlatform; 10] = [
    SocialPlatform { key: "facebook", label: "Facebook", color: "#1877F2", placeholder: "facebook.com/monEglise" },
    SocialPlatform { key: "youtube", label: "YouTube", color: "#FF0000", placeholder: "youtube.com/@monEglise" },
    SocialPlatform { key: "instagram", label: "Instagram", color: "#E1306C", placeholder: "@monEglise" },
    SocialPlatform { key: "whatsapp", label: "WhatsApp", color: "#25D366", placeholder: "+243 81 000 0000" },
    SocialPlatform { key: "tiktok", label: "TikTok", color: "#161823", placeholder: "@monEglise" },
    SocialPlatform { key: "x", label: "X", color: "#14171A", placeholder: "@monEglise" },
    SocialPlatform { key: "telegram", label: "Telegram", color: "#229ED9", placeholder: "t.me/monEglise" },
    SocialPlatform { key: "website", label: "Site web", color: "#6B7280", placeholder: "www.monEglise.org" },
    SocialPlatform { key: "email", label: "E-mail", color: "#6B7280", placeholder: "contact@monEglise.org" },
    SocialPlatform { key: "phone", label: "Téléphone", color: "#6B7280", placeholder: "+243 99 000 0000" },
];

pub fn platform(key: &str) -> Option<&'static SocialPlatform> {
    SOCIAL_PLATFORMS.iter().find(|p| p.key == key)
}

/// Le fond des écrans de l'église.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ChurchBackground {
    Gradient,
    Solid,
    Image,
}

/// Le profil de l'église.
#[derive(Debug, Clone, PartialEq)]
pub struct ChurchProfile {
    pub name: String,
    pub motto: String,
    pub logo: String,
    pub contact: String,
    /// (clé du réseau, adresse ou @compte), dans l'ordre de [`SOCIAL_PLATFORMS`].
    pub socials: Vec<(String, String)>,
    pub primary_color: Rgba,
    pub accent_color: Rgba,
    pub text_color: Rgba,
    pub font_family: String,
    pub welcome_title: String,
    pub service_times: String,
    pub background: ChurchBackground,
    pub background_image: String,
    /// Assombrissement de l'image de fond, en % (0 à 85).
    pub background_dim: u8,
    pub show_socials_welcome: bool,
    /// Le réseau vers lequel pointe le QR code ; vide : aucun.
    pub qr_target: String,
    pub pastor_name: String,
    pub pastor_title: String,
    pub pastor_photo: String,
    pub speaker_name: String,
    pub speaker_title: String,
    pub speaker_photo: String,
    pub speaker_message: String,
    /// Le modèle des images de citation (voir [`QUOTE_STYLES`]).
    pub quote_style: String,
    /// Les réseaux en pied des images de citation.
    pub show_socials_quotes: bool,
    /// Les photos de l'église (fond du modèle « Photo »).
    pub photos: Vec<String>,
}

/// Les modèles des images de citation : clé, nom (`QUOTE_STYLES` de la 2.8).
pub const QUOTE_STYLES: [(&str, &str); 8] = [
    ("classic", "Classique (grand guillemet)"),
    ("minimal", "Minimal (aligné à gauche)"),
    ("framed", "Encadré"),
    ("elegant", "Élégant (police à empattements)"),
    ("card", "Carte claire"),
    ("poster", "Affiche (couleur d'accent)"),
    ("photo", "Photo de l'église en fond"),
    ("portrait", "Portrait du pasteur"),
];

/// Les formats des images de citation : clé, nom, largeur, hauteur (`FORMATS` de la 2.8).
pub const QUOTE_FORMATS: [(&str, &str, u32, u32); 3] = [
    ("square", "Carré 1080×1080 (Instagram, Facebook)", 1080, 1080),
    ("story", "Story 1080×1920 (WhatsApp, Instagram)", 1080, 1920),
    ("landscape", "Paysage 1920×1080 (YouTube, écran)", 1920, 1080),
];

impl Default for ChurchProfile {
    fn default() -> Self {
        ChurchProfile {
            name: String::new(),
            motto: String::new(),
            logo: String::new(),
            contact: String::new(),
            socials: Vec::new(),
            primary_color: Rgba::rgb(0x0B, 0x1E, 0x3F),
            accent_color: Rgba::rgb(0xF0, 0xBE, 0x64),
            text_color: Rgba::WHITE,
            font_family: "Poppins".into(),
            welcome_title: "Bienvenue".into(),
            service_times: String::new(),
            background: ChurchBackground::Gradient,
            background_image: String::new(),
            background_dim: 45,
            show_socials_welcome: true,
            qr_target: String::new(),
            pastor_name: String::new(),
            pastor_title: "Pasteur".into(),
            pastor_photo: String::new(),
            speaker_name: String::new(),
            speaker_title: String::new(),
            speaker_photo: String::new(),
            speaker_message: String::new(),
            quote_style: "classic".into(),
            show_socials_quotes: true,
            photos: Vec::new(),
        }
    }
}

fn text(v: &Value, key: &str) -> Option<String> {
    v.get(key).and_then(|x| match x {
        Value::String(s) => Some(s.trim().to_string()),
        Value::Number(n) => Some(n.to_string()),
        _ => None,
    })
}

/// Une couleur lisible (`#rrggbb`, `rgb()`…), sinon celle par défaut (`_parse_color`).
fn color(v: &Value, key: &str, fallback: Rgba) -> Rgba {
    match text(v, key) {
        Some(s) if !s.is_empty() && (s.starts_with('#') || s.starts_with("rgb")) => parse_color(&s).with_alpha(1.0),
        _ => fallback,
    }
}

impl ChurchProfile {
    /// Le profil des réglages de la 2.x (`from_payload` puis `sanitized`).
    pub fn from_settings(church: Option<&Value>) -> Self {
        let d = ChurchProfile::default();
        let Some(v) = church.filter(|v| v.is_object()) else { return d };
        let get = |key: &str, default: &str| text(v, key).unwrap_or_else(|| default.to_string());
        let socials_map = v.get("socials").and_then(Value::as_object);
        let socials: Vec<(String, String)> = SOCIAL_PLATFORMS
            .iter()
            .filter_map(|p| {
                let value = socials_map?.get(p.key)?.as_str()?.trim().to_string();
                (!value.is_empty()).then(|| (p.key.to_string(), value))
            })
            .collect();
        let qr = get("qr_target", "");
        let mut profile = ChurchProfile {
            name: get("name", ""),
            motto: get("motto", ""),
            logo: get("logo", ""),
            contact: get("contact", ""),
            primary_color: color(v, "primary_color", d.primary_color),
            accent_color: color(v, "accent_color", d.accent_color),
            text_color: color(v, "text_color", d.text_color),
            font_family: Some(get("font_family", "")).filter(|f| !f.is_empty()).unwrap_or(d.font_family),
            welcome_title: get("welcome_title", "Bienvenue"),
            service_times: get("service_times", ""),
            background: match get("background_mode", "gradient").as_str() {
                "solid" => ChurchBackground::Solid,
                "image" => ChurchBackground::Image,
                _ => ChurchBackground::Gradient,
            },
            background_image: get("background_image", ""),
            background_dim: v.get("background_dim").and_then(Value::as_i64).map_or(45, |d| d.clamp(0, 85) as u8),
            show_socials_welcome: v.get("show_socials_welcome").and_then(Value::as_bool).unwrap_or(true),
            qr_target: if socials.iter().any(|(k, _)| *k == qr) { qr } else { String::new() },
            pastor_name: get("pastor_name", ""),
            pastor_title: get("pastor_title", "Pasteur"),
            pastor_photo: get("pastor_photo", ""),
            speaker_name: get("speaker_name", ""),
            speaker_title: get("speaker_title", ""),
            speaker_photo: get("speaker_photo", ""),
            speaker_message: get("speaker_message", ""),
            quote_style: Some(get("quote_style", "classic"))
                .filter(|s| QUOTE_STYLES.iter().any(|(k, _)| k == s))
                .unwrap_or_else(|| "classic".into()),
            show_socials_quotes: v.get("show_socials_quotes").and_then(Value::as_bool).unwrap_or(true),
            photos: v
                .get("photos")
                .and_then(Value::as_array)
                .map(|a| a.iter().filter_map(Value::as_str).map(str::to_string).filter(|p| !p.is_empty()).collect())
                .unwrap_or_default(),
            socials,
        };
        // 2.7 préversion : « message du jour » rattaché au pasteur.
        if profile.speaker_message.is_empty() {
            profile.speaker_message = get("pastor_message", "");
        }
        profile
    }

    /// Écrit le profil dans la section `church` des réglages, en gardant les champs que la 3.0 ne
    /// connaît pas (le style des citations, l'orateur sur les slides, les photos…).
    pub fn write_into(&self, church: &mut Map<String, Value>) {
        let hex = |c: Rgba| format!("#{:02X}{:02X}{:02X}", c.0[0], c.0[1], c.0[2]);
        let mut socials = Map::new();
        for (k, v) in &self.socials {
            socials.insert(k.clone(), json!(v));
        }
        let fields = [
            ("name", json!(self.name)),
            ("motto", json!(self.motto)),
            ("logo", json!(self.logo)),
            ("contact", json!(self.contact)),
            ("socials", Value::Object(socials)),
            ("primary_color", json!(hex(self.primary_color))),
            ("accent_color", json!(hex(self.accent_color))),
            ("text_color", json!(hex(self.text_color))),
            ("font_family", json!(self.font_family)),
            ("welcome_title", json!(self.welcome_title)),
            ("service_times", json!(self.service_times)),
            (
                "background_mode",
                json!(match self.background {
                    ChurchBackground::Gradient => "gradient",
                    ChurchBackground::Solid => "solid",
                    ChurchBackground::Image => "image",
                }),
            ),
            ("background_image", json!(self.background_image)),
            ("background_dim", json!(self.background_dim)),
            ("show_socials_welcome", json!(self.show_socials_welcome)),
            ("qr_target", json!(self.qr_target)),
            ("pastor_name", json!(self.pastor_name)),
            ("pastor_title", json!(self.pastor_title)),
            ("pastor_photo", json!(self.pastor_photo)),
            ("speaker_name", json!(self.speaker_name)),
            ("speaker_title", json!(self.speaker_title)),
            ("speaker_photo", json!(self.speaker_photo)),
            ("speaker_message", json!(self.speaker_message)),
            ("quote_style", json!(self.quote_style)),
            ("show_socials_quotes", json!(self.show_socials_quotes)),
            ("photos", json!(self.photos)),
        ];
        for (key, value) in fields {
            church.insert(key.to_string(), value);
        }
    }

    /// Les comptes renseignés.
    pub fn social_items(&self) -> Vec<(&'static SocialPlatform, &str)> {
        self.socials.iter().filter_map(|(k, v)| Some((platform(k)?, v.as_str()))).collect()
    }

    pub fn social(&self, key: &str) -> Option<&str> {
        self.socials.iter().find(|(k, _)| k == key).map(|(_, v)| v.as_str())
    }

    /// Un orateur invité (sinon, c'est le pasteur qui prêche).
    pub fn has_guest_speaker(&self) -> bool {
        !self.speaker_name.trim().is_empty()
    }

    /// (titre, nom, photo) de l'orateur du jour, le pasteur par défaut.
    pub fn speaker_info(&self) -> (&str, &str, &str) {
        if self.has_guest_speaker() {
            (&self.speaker_title, &self.speaker_name, &self.speaker_photo)
        } else {
            (&self.pastor_title, &self.pastor_name, &self.pastor_photo)
        }
    }

    /// « Révérend Joseph Nyembo ».
    pub fn speaker_label(&self) -> String {
        let (title, name, _) = self.speaker_info();
        [title, name].iter().filter(|s| !s.is_empty()).copied().collect::<Vec<_>>().join(" ")
    }

    pub fn pastor_label(&self) -> String {
        [self.pastor_title.as_str(), self.pastor_name.as_str()]
            .iter()
            .filter(|s| !s.is_empty())
            .copied()
            .collect::<Vec<_>>()
            .join(" ")
    }

    /// Les horaires des cultes, une ligne chacun (4 au plus).
    pub fn times(&self) -> Vec<&str> {
        self.service_times.lines().map(str::trim).filter(|l| !l.is_empty()).take(4).collect()
    }
}

/// L'adresse lisible à l'écran : sans « https:// » ni « www. » (`display_handle`).
pub fn display_handle(key: &str, value: &str) -> String {
    let mut text = value.trim().to_string();
    for prefix in ["https://", "http://", "HTTPS://", "HTTP://"] {
        if let Some(rest) = text.strip_prefix(prefix) {
            text = rest.to_string();
        }
    }
    if text.to_lowercase().starts_with("www.") {
        text = text[4..].to_string();
    }
    let text = text.trim_end_matches('/').to_string();
    if key == "email" && text.to_lowercase().starts_with("mailto:") {
        return text[7..].to_string();
    }
    text
}

/// Le lien complet d'un compte (pour le QR code) (`link_url`).
pub fn link_url(key: &str, value: &str) -> String {
    let value = value.trim();
    if value.is_empty() {
        return String::new();
    }
    let lower = value.to_lowercase();
    if lower.starts_with("http://")
        || lower.starts_with("https://")
        || lower.starts_with("mailto:")
        || lower.starts_with("tel:")
    {
        return value.to_string();
    }
    let handle = value.trim_start_matches(['@', '/']);
    let digits: String = value.chars().filter(|c| c.is_ascii_digit() || *c == '+').collect();
    match key {
        "whatsapp" => format!("https://wa.me/{}", digits.trim_start_matches('+')),
        "phone" => format!("tel:{digits}"),
        "email" => format!("mailto:{value}"),
        _ if (handle.contains('.') && handle.contains('/')) || key == "website" => format!("https://{handle}"),
        "facebook" => format!("https://facebook.com/{handle}"),
        "youtube" => format!("https://youtube.com/@{handle}"),
        "instagram" => format!("https://instagram.com/{handle}"),
        "tiktok" => format!("https://tiktok.com/@{handle}"),
        "x" => format!("https://x.com/{handle}"),
        "telegram" => format!("https://t.me/{handle}"),
        _ => format!("https://{handle}"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_2x_profile_is_read_and_written_back() {
        let church = json!({
            "name": "OUVRIERS DE LA ONZIÈME HEURE", "motto": "Tenez-vous tranquilles", "logo": "C:/logo.png",
            "socials": {"facebook": "@Eglise", "whatsapp": "+243 81 243 6993", "inconnu": "x", "x": "  "},
            "primary_color": "#0B1E3F", "accent_color": "pas une couleur", "service_times": "Mercredi : 16H00\n\nDimanche : 9H30",
            "background_mode": "image", "background_dim": 300, "qr_target": "youtube", "pastor_title": "Révérend",
            "quote_style": "minimal"
        });
        let p = ChurchProfile::from_settings(Some(&church));
        assert_eq!(p.name, "OUVRIERS DE LA ONZIÈME HEURE");
        assert_eq!(
            p.socials,
            [("facebook".to_string(), "@Eglise".to_string()), ("whatsapp".into(), "+243 81 243 6993".into())]
        );
        assert_eq!(p.accent_color, Rgba::rgb(0xF0, 0xBE, 0x64), "une couleur illisible : celle par défaut");
        assert_eq!((p.background, p.background_dim), (ChurchBackground::Image, 85));
        assert_eq!(p.qr_target, "", "le QR vise un réseau renseigné, sinon aucun");
        assert_eq!(p.times(), ["Mercredi : 16H00", "Dimanche : 9H30"]);
        assert_eq!(p.speaker_label(), "Révérend", "sans invité : le pasteur");
        // Réécrit, il garde les champs que la 3.0 ne connaît pas.
        let mut map = church.as_object().unwrap().clone();
        p.write_into(&mut map);
        assert_eq!(map["quote_style"], "minimal");
        assert_eq!(map["socials"]["whatsapp"], "+243 81 243 6993");
        assert_eq!(ChurchProfile::from_settings(Some(&Value::Object(map))), p);
        assert_eq!(ChurchProfile::from_settings(None), ChurchProfile::default());
    }

    #[test]
    fn links_and_handles_like_the_2x() {
        assert_eq!(link_url("whatsapp", "+243 81 243 6993"), "https://wa.me/243812436993");
        assert_eq!(link_url("youtube", "@PasteurJoseph"), "https://youtube.com/@PasteurJoseph");
        assert_eq!(link_url("phone", "+243 99"), "tel:+24399");
        assert_eq!(link_url("website", "www.eglise.org"), "https://www.eglise.org");
        assert_eq!(link_url("facebook", "https://facebook.com/x"), "https://facebook.com/x");
        assert_eq!(display_handle("website", "https://www.eglise.org/"), "eglise.org");
        assert_eq!(display_handle("email", "mailto:a@b.c"), "a@b.c");
    }
}
