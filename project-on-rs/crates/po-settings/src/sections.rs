//! Les sections typées des réglages, lues comme `AppSettings.load` de la 2.8 (`app.utils.settings`).
//!
//! L'ordre des champs est celui des classes Python : le JSON écrit a le même ordre.

use serde::Serialize;
use serde_json::{Map, Value};

use po_core::pyval::{py_max, py_min, round_half_even, to_float, to_int, to_str, truthy};

type Obj = Map<String, Value>;

/// `str.strip()` de Python.
fn py_strip(s: &str) -> &str {
    s.trim_matches(|c: char| c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c))
}

/// `_gs` : le texte, ou la valeur par défaut s'il est absent, nul ou vide.
fn gs(d: &Obj, key: &str, default: &str) -> String {
    match d.get(key) {
        Some(v) if !v.is_null() => {
            let s = to_str(v);
            if py_strip(&s).is_empty() { default.to_string() } else { s }
        }
        _ => default.to_string(),
    }
}

/// `_gi` : l'entier ; une taille (« size » dans le nom) vaut au moins 8, ou la valeur par défaut si
/// elle n'est pas positive.
fn gi(d: &Obj, key: &str, default: i64) -> i64 {
    let Some(v) = d.get(key).filter(|v| !v.is_null()) else { return default };
    let Some(val) = to_int(v) else { return default };
    if key.to_lowercase().contains("size") {
        return if val > 0 { val.max(8) } else { default };
    }
    val
}

/// `_gf` : le nombre ; une hauteur de ligne vaut au moins 0,5, une opacité est bornée à 0..1.
fn gf(d: &Obj, key: &str, default: f64) -> f64 {
    let Some(v) = d.get(key).filter(|v| !v.is_null()) else { return default };
    let Some(val) = to_float(v) else { return default };
    let key = key.to_lowercase();
    if key.contains("line_height") {
        return py_max(val, 0.5);
    }
    if key.contains("opacity") {
        return py_max(0.0, py_min(1.0, val));
    }
    val
}

/// `_gb` : `bool(valeur)` si la clé est là (même nulle), sinon la valeur par défaut.
fn gb(d: &Obj, key: &str, default: bool) -> bool {
    d.get(key).map_or(default, truthy)
}

/// L'affichage de la projection locale (`ProjectionSettings`).
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct ProjectionSettings {
    pub layout_mode: String,
    pub display_screen: String,
    pub safe_margin: i64,
    pub panel_side: String,
    pub font_family: String,
    pub text_size: i64,
    pub ref_size: i64,
    pub padding: i64,
    pub align: String,
    pub position: String,
    pub slide_style: String,
    pub content_width: i64,
    pub content_height: i64,
    pub show_reference: bool,
    pub reference_position: String,
    pub uppercase: bool,
    pub text_color: String,
    pub ref_color: String,
    pub bg_color: String,
    pub font_weight: String,
    pub line_height: f64,
    pub letter_spacing: i64,
    pub text_shadow: bool,
    pub shadow_color: String,
    pub shadow_blur: i64,
    pub max_width: i64,
    pub auto_fit: bool,
    pub uniform_text_size: bool,
    pub min_text_size: i64,
    pub max_lines: i64,
    pub background_dimmer: f64,
    pub panel_enabled: bool,
    pub panel_color: String,
    pub panel_opacity: f64,
    pub panel_radius: i64,
    pub bg_gradient_enabled: bool,
    pub bg_color_2: String,
    pub bg_gradient_angle: i64,
    pub bg_mode: String,
    pub bg_image: String,
    pub bg_image_fit: String,
    pub bg_video: String,
    pub media_fit: String,
    pub media_backdrop: String,
    pub media_backdrop_dim: f64,
    pub media_default_duration: i64,
    pub animation_enabled: bool,
    pub animation_type: String,
    pub animation_duration: i64,
    pub animation_direction: String,
    pub ken_burns: bool,
}

impl Default for ProjectionSettings {
    fn default() -> Self {
        Self {
            layout_mode: "fullscreen".into(),
            display_screen: "auto".into(),
            safe_margin: 32,
            panel_side: "left".into(),
            font_family: "Poppins".into(),
            text_size: 56,
            ref_size: 24,
            padding: 0,
            align: "center".into(),
            position: "center".into(),
            slide_style: "cinematic".into(),
            content_width: 88,
            content_height: 82,
            show_reference: true,
            reference_position: "bottom".into(),
            uppercase: false,
            text_color: "rgba(255,255,255,0.96)".into(),
            ref_color: "rgba(255,244,214,0.82)".into(),
            bg_color: "#07111f".into(),
            font_weight: "bold".into(),
            line_height: 1.12,
            letter_spacing: 0,
            text_shadow: true,
            shadow_color: "rgba(0,0,0,0.88)".into(),
            shadow_blur: 18,
            max_width: 100,
            auto_fit: false,
            uniform_text_size: true,
            min_text_size: 18,
            max_lines: 8,
            background_dimmer: 0.34,
            panel_enabled: false,
            panel_color: "rgba(5,12,24,0.86)".into(),
            panel_opacity: 0.86,
            panel_radius: 24,
            bg_gradient_enabled: true,
            bg_color_2: "#0f2744".into(),
            bg_gradient_angle: 160,
            bg_mode: "color".into(),
            bg_image: String::new(),
            bg_image_fit: "cover".into(),
            bg_video: String::new(),
            media_fit: "contain".into(),
            media_backdrop: "blur".into(),
            media_backdrop_dim: 0.45,
            media_default_duration: 8,
            animation_enabled: true,
            animation_type: "fade".into(),
            animation_duration: 420,
            animation_direction: "up".into(),
            ken_burns: true,
        }
    }
}

impl ProjectionSettings {
    pub(crate) fn read(p: Option<&Obj>) -> Self {
        let d = Self::default();
        let Some(p) = p else { return d.guarded() };
        Self {
            layout_mode: gs(p, "layout_mode", &d.layout_mode),
            display_screen: gs(p, "display_screen", &d.display_screen),
            safe_margin: gi(p, "safe_margin", d.safe_margin),
            panel_side: gs(p, "panel_side", &d.panel_side),
            font_family: gs(p, "font_family", &d.font_family),
            text_size: gi(p, "text_size", d.text_size),
            ref_size: gi(p, "ref_size", d.ref_size),
            padding: gi(p, "padding", d.padding),
            align: gs(p, "align", &d.align),
            position: gs(p, "position", &d.position),
            slide_style: gs(p, "slide_style", &d.slide_style),
            content_width: gi(p, "content_width", d.content_width),
            content_height: gi(p, "content_height", d.content_height),
            show_reference: gb(p, "show_reference", d.show_reference),
            reference_position: gs(p, "reference_position", &d.reference_position),
            uppercase: gb(p, "uppercase", d.uppercase),
            text_color: gs(p, "text_color", &d.text_color),
            ref_color: gs(p, "ref_color", &d.ref_color),
            bg_color: gs(p, "bg_color", &d.bg_color),
            font_weight: gs(p, "font_weight", &d.font_weight),
            line_height: gf(p, "line_height", d.line_height),
            letter_spacing: gi(p, "letter_spacing", d.letter_spacing),
            text_shadow: gb(p, "text_shadow", d.text_shadow),
            shadow_color: gs(p, "shadow_color", &d.shadow_color),
            shadow_blur: gi(p, "shadow_blur", d.shadow_blur),
            max_width: gi(p, "max_width", d.max_width),
            // Depuis la 1.5.1, la projection locale ne grandit plus pour remplir : forcé.
            auto_fit: false,
            uniform_text_size: true,
            min_text_size: gi(p, "min_text_size", d.min_text_size),
            max_lines: gi(p, "max_lines", d.max_lines),
            background_dimmer: gf(p, "background_dimmer", d.background_dimmer),
            panel_enabled: gb(p, "panel_enabled", d.panel_enabled),
            panel_color: gs(p, "panel_color", &d.panel_color),
            panel_opacity: gf(p, "panel_opacity", d.panel_opacity),
            panel_radius: gi(p, "panel_radius", d.panel_radius),
            bg_gradient_enabled: gb(p, "bg_gradient_enabled", d.bg_gradient_enabled),
            bg_color_2: gs(p, "bg_color_2", &d.bg_color_2),
            bg_gradient_angle: gi(p, "bg_gradient_angle", d.bg_gradient_angle),
            bg_mode: gs(p, "bg_mode", &d.bg_mode),
            bg_image: gs(p, "bg_image", &d.bg_image),
            bg_image_fit: gs(p, "bg_image_fit", &d.bg_image_fit),
            bg_video: gs(p, "bg_video", &d.bg_video),
            media_fit: gs(p, "media_fit", &d.media_fit),
            media_backdrop: gs(p, "media_backdrop", &d.media_backdrop),
            media_backdrop_dim: gf(p, "media_backdrop_dim", d.media_backdrop_dim),
            media_default_duration: gi(p, "media_default_duration", d.media_default_duration),
            animation_enabled: gb(p, "animation_enabled", d.animation_enabled),
            animation_type: gs(p, "animation_type", &d.animation_type),
            animation_duration: gi(p, "animation_duration", d.animation_duration),
            animation_direction: gs(p, "animation_direction", &d.animation_direction),
            ken_burns: gb(p, "ken_burns", d.ken_burns),
        }
        .guarded()
    }

    /// Les garde-fous de la 2.8 : un fond image ou vidéo dont le fichier a disparu redevient une
    /// couleur (l'écran n'est jamais vide) ; les réglages des médias sont bornés.
    fn guarded(mut self) -> Self {
        let is_file = |p: &str| !p.is_empty() && std::path::Path::new(p).is_file();
        if self.bg_mode == "image" && !is_file(&self.bg_image) {
            self.bg_mode = "color".into();
        }
        if self.bg_mode == "video" && !is_file(&self.bg_video) {
            self.bg_mode = "color".into();
        }
        self.media_fit = if self.media_fit == "cover" { "cover" } else { "contain" }.into();
        if !matches!(self.media_backdrop.as_str(), "blur" | "black" | "color") {
            self.media_backdrop = "blur".into();
        }
        self.media_backdrop_dim = py_max(0.0, py_min(0.9, self.media_backdrop_dim));
        self.media_default_duration = self.media_default_duration.clamp(0, 120);
        self
    }
}

/// L'apparence de la régie (`AppearanceSettings`).
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct AppearanceSettings {
    pub theme: String,
    pub language: String,
    pub mica: bool,
    pub rail_compact: bool,
    /// Mode PC modeste : sans animations, flou, Ken Burns, fond vidéo ni Mica.
    pub low_power: bool,
    /// Contrôle avant culte lancé à chaque démarrage.
    pub startup_check: bool,
    /// Recherche d'une nouvelle version au démarrage.
    pub check_updates: bool,
}

impl Default for AppearanceSettings {
    fn default() -> Self {
        Self {
            theme: "dark".into(),
            language: "fr".into(),
            mica: true,
            rail_compact: false,
            low_power: false,
            startup_check: true,
            check_updates: true,
        }
    }
}

impl AppearanceSettings {
    pub(crate) fn read(a: Option<&Obj>) -> Self {
        let d = Self::default();
        let Some(a) = a else { return d };
        let theme = gs(a, "theme", &d.theme).to_lowercase();
        let language = gs(a, "language", &d.language);
        let flag = |key: &str, default: bool| a.get(key).map_or(default, truthy);
        Self {
            theme: if matches!(theme.as_str(), "dark" | "light") { theme } else { "dark".into() },
            language: if matches!(language.as_str(), "fr" | "en") { language } else { "fr".into() },
            mica: flag("mica", d.mica),
            rail_compact: flag("rail_compact", d.rail_compact),
            low_power: flag("low_power", d.low_power),
            startup_check: flag("startup_check", d.startup_check),
            check_updates: flag("check_updates", d.check_updates),
        }
    }
}

/// Le découpage des textes longs et des strophes (`SplitSettings`).
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct SplitSettings {
    pub text_enabled: bool,
    /// 120 à 800 caractères par partie.
    pub max_chars: i64,
    pub keep_line_breaks: bool,
    pub hymn_enabled: bool,
    /// 1 à 12 vers par slide.
    pub hymn_max_lines: i64,
    pub hymn_keep_couplets: bool,
    pub hymn_repeat_chorus: bool,
    /// « (1/2) » dans la référence.
    pub show_part_counter: bool,
}

impl Default for SplitSettings {
    fn default() -> Self {
        Self {
            text_enabled: true,
            max_chars: 280,
            keep_line_breaks: true,
            hymn_enabled: true,
            hymn_max_lines: 2,
            hymn_keep_couplets: true,
            hymn_repeat_chorus: true,
            show_part_counter: true,
        }
    }
}

/// La valeur de la clé si elle est là et non nulle (`from_payload` des classes Python).
fn given<'a>(p: Option<&'a Obj>, key: &str) -> Option<&'a Value> {
    p.and_then(|p| p.get(key)).filter(|v| !v.is_null())
}

impl SplitSettings {
    pub(crate) fn read(p: Option<&Obj>) -> Self {
        let d = Self::default();
        let flag = |key: &str, default: bool| given(p, key).map_or(default, truthy);
        let int = |key: &str, default: i64, low: i64, high: i64| match given(p, key) {
            None => default,
            Some(v) => to_int(v).map_or(default, |i| i.clamp(low, high)),
        };
        Self {
            text_enabled: flag("text_enabled", d.text_enabled),
            max_chars: int("max_chars", 280, 120, 800),
            keep_line_breaks: flag("keep_line_breaks", d.keep_line_breaks),
            hymn_enabled: flag("hymn_enabled", d.hymn_enabled),
            hymn_max_lines: int("hymn_max_lines", 2, 1, 12),
            hymn_keep_couplets: flag("hymn_keep_couplets", d.hymn_keep_couplets),
            hymn_repeat_chorus: flag("hymn_repeat_chorus", d.hymn_repeat_chorus),
            show_part_counter: flag("show_part_counter", d.show_part_counter),
        }
    }
}

/// Le style propre à la sortie HDMI (`HdmiStyle`).
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct HdmiStyle {
    pub font_family: String,
    pub font_weight: String,
    pub text_transform: String,
    pub letter_spacing: i64,
    pub line_height: f64,
    pub text_size: i64,
    pub ref_size: i64,
    pub show_reference: bool,
    pub reference_style: String,
    pub auto_fit: bool,
    pub max_lines: i64,
    pub position: String,
    pub align: String,
    pub edge_margin: i64,
    pub max_width: i64,
    pub bg_enabled: bool,
    pub bg_color: String,
    pub bg_gradient_enabled: bool,
    pub bg_color_2: String,
    pub border_radius: i64,
    pub text_color: String,
    pub ref_color: String,
    pub text_shadow: bool,
    pub shadow_color: String,
    pub shadow_blur: i64,
    pub text_stroke: bool,
    pub stroke_color: String,
    pub stroke_width: i64,
    pub show_kicker: bool,
    pub show_accent_bar: bool,
    pub accent_mode: String,
    pub accent_color: String,
    pub animation_enabled: bool,
    pub animation_type: String,
    pub animation_style: String,
    pub animation_direction: String,
    pub animation_duration: i64,
}

impl Default for HdmiStyle {
    fn default() -> Self {
        Self {
            font_family: "Google Sans".into(),
            font_weight: "bold".into(),
            text_transform: "none".into(),
            letter_spacing: 0,
            line_height: 1.2,
            text_size: 44,
            ref_size: 22,
            show_reference: true,
            reference_style: "badge".into(),
            auto_fit: true,
            max_lines: 3,
            position: "bottom".into(),
            align: "center".into(),
            edge_margin: 54,
            max_width: 84,
            bg_enabled: true,
            bg_color: "rgba(10, 14, 22, 0.94)".into(),
            bg_gradient_enabled: false,
            bg_color_2: "rgba(10, 14, 22, 0.94)".into(),
            border_radius: 14,
            text_color: "#ffffff".into(),
            ref_color: "#e7c07e".into(),
            text_shadow: true,
            shadow_color: "rgba(0, 0, 0, 0.70)".into(),
            shadow_blur: 12,
            text_stroke: false,
            stroke_color: "rgba(0, 0, 0, 0.90)".into(),
            stroke_width: 2,
            show_kicker: false,
            show_accent_bar: true,
            accent_mode: "custom".into(),
            accent_color: "#e7c07e".into(),
            animation_enabled: true,
            animation_type: "fade".into(),
            animation_style: "block".into(),
            animation_direction: "up".into(),
            animation_duration: 420,
        }
    }
}

/// Un champ de `HdmiStyle.sanitized` : la valeur donnée, convertie au type du défaut, bornée, ou
/// choisie dans une liste (la première valeur est le repli).
struct StyleReader<'a> {
    p: Option<&'a Obj>,
}

impl StyleReader<'_> {
    fn flag(&self, key: &str, default: bool) -> bool {
        given(self.p, key).map_or(default, truthy)
    }

    fn int(&self, key: &str, default: i64, range: Option<(i64, i64)>) -> i64 {
        let value = match given(self.p, key) {
            None => default,
            Some(v) => to_float(v).map(round_half_even).filter(|f| f.is_finite()).map_or(default, |f| f as i64),
        };
        match range {
            Some((low, high)) => py_max(low, py_min(high, value)),
            None => value,
        }
    }

    fn float(&self, key: &str, default: f64, range: (f64, f64)) -> f64 {
        let value = given(self.p, key).and_then(to_float).unwrap_or(default);
        py_max(range.0, py_min(range.1, value))
    }

    fn text(&self, key: &str, default: &str, may_be_empty: bool) -> String {
        let value = match given(self.p, key) {
            None => default.to_string(),
            Some(v) => py_strip(&to_str(v)).to_string(),
        };
        if value.is_empty() && !may_be_empty { default.to_string() } else { value }
    }

    fn choice(&self, key: &str, default: &str, choices: &[&str]) -> String {
        let value = self.text(key, default, false).to_lowercase();
        if choices.contains(&value.as_str()) { value } else { choices[0].to_string() }
    }
}

impl HdmiStyle {
    pub(crate) fn read(p: Option<&Obj>) -> Self {
        let d = Self::default();
        let r = StyleReader { p };
        Self {
            font_family: r.text("font_family", &d.font_family, false),
            font_weight: r.choice("font_weight", &d.font_weight, &["bold", "normal", "light"]),
            text_transform: r.choice("text_transform", &d.text_transform, &["none", "uppercase", "capitalize"]),
            letter_spacing: r.int("letter_spacing", d.letter_spacing, Some((-5, 20))),
            line_height: r.float("line_height", d.line_height, (1.0, 2.0)),
            text_size: r.int("text_size", d.text_size, Some((16, 120))),
            ref_size: r.int("ref_size", d.ref_size, Some((10, 60))),
            show_reference: r.flag("show_reference", d.show_reference),
            reference_style: r.choice("reference_style", &d.reference_style, &["badge", "plain", "inline"]),
            auto_fit: r.flag("auto_fit", d.auto_fit),
            max_lines: r.int("max_lines", d.max_lines, Some((1, 8))),
            position: r.choice("position", &d.position, &["bottom", "top", "center"]),
            align: r.choice("align", &d.align, &["center", "left", "right"]),
            edge_margin: r.int("edge_margin", d.edge_margin, Some((0, 300))),
            max_width: r.int("max_width", d.max_width, Some((30, 100))),
            bg_enabled: r.flag("bg_enabled", d.bg_enabled),
            bg_color: r.text("bg_color", &d.bg_color, false),
            bg_gradient_enabled: r.flag("bg_gradient_enabled", d.bg_gradient_enabled),
            bg_color_2: r.text("bg_color_2", &d.bg_color_2, true),
            border_radius: r.int("border_radius", d.border_radius, Some((0, 60))),
            text_color: r.text("text_color", &d.text_color, false),
            ref_color: r.text("ref_color", &d.ref_color, false),
            text_shadow: r.flag("text_shadow", d.text_shadow),
            shadow_color: r.text("shadow_color", &d.shadow_color, false),
            shadow_blur: r.int("shadow_blur", d.shadow_blur, Some((0, 30))),
            text_stroke: r.flag("text_stroke", d.text_stroke),
            stroke_color: r.text("stroke_color", &d.stroke_color, false),
            stroke_width: r.int("stroke_width", d.stroke_width, Some((1, 8))),
            show_kicker: r.flag("show_kicker", d.show_kicker),
            show_accent_bar: r.flag("show_accent_bar", d.show_accent_bar),
            accent_mode: r.choice("accent_mode", &d.accent_mode, &["auto", "custom"]),
            accent_color: r.text("accent_color", &d.accent_color, false),
            animation_enabled: r.flag("animation_enabled", d.animation_enabled),
            animation_type: r.choice(
                "animation_type",
                &d.animation_type,
                &["fade", "none", "slide", "scale", "blur", "reveal", "auto"],
            ),
            animation_style: r.choice("animation_style", &d.animation_style, &["block", "words"]),
            animation_direction: r.choice(
                "animation_direction",
                &d.animation_direction,
                &["up", "down", "left", "right"],
            ),
            animation_duration: r.int("animation_duration", d.animation_duration, Some((0, 2000))),
        }
    }
}

/// La sortie HDMI vers un mélangeur vidéo (`HdmiSettings`).
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct HdmiSettings {
    pub enabled: bool,
    pub screen: String,
    pub letterbox: bool,
    /// green, magenta ou blue.
    pub key_color: String,
    /// 60 à 180 %.
    pub text_scale: i64,
    /// -300 à 300 px (en 1080p).
    pub offset_y: i64,
    pub layout: String,
    pub use_obs_style: bool,
    pub style: HdmiStyle,
}

impl Default for HdmiSettings {
    fn default() -> Self {
        Self {
            enabled: false,
            screen: "auto".into(),
            letterbox: true,
            key_color: "green".into(),
            text_scale: 100,
            offset_y: 0,
            layout: "subtitle".into(),
            use_obs_style: true,
            style: HdmiStyle::default(),
        }
    }
}

/// Les dispositions admises de la sortie HDMI.
const HDMI_LAYOUTS: &[&str] = &["subtitle", "obs", "lower_third", "side_panel", "focus_card"];

impl HdmiSettings {
    pub(crate) fn read(h: Option<&Obj>) -> Self {
        let d = Self::default();
        let Some(h) = h else { return d };
        let key_color = py_strip(&gs(h, "key_color", &d.key_color)).to_lowercase();
        let layout = py_strip(&gs(h, "layout", &d.layout)).to_lowercase();
        let screen = py_strip(&gs(h, "screen", &d.screen)).to_string();
        let text_scale = gi(h, "text_scale", d.text_scale);
        Self {
            enabled: gb(h, "enabled", d.enabled),
            screen: if screen.is_empty() { "auto".into() } else { screen },
            letterbox: gb(h, "letterbox", d.letterbox),
            key_color: if matches!(key_color.as_str(), "green" | "magenta" | "blue") {
                key_color
            } else {
                "green".into()
            },
            text_scale: (if text_scale == 0 { 100 } else { text_scale }).clamp(60, 180),
            offset_y: gi(h, "offset_y", d.offset_y).clamp(-300, 300),
            layout: if HDMI_LAYOUTS.contains(&layout.as_str()) { layout } else { "subtitle".into() },
            use_obs_style: gb(h, "use_obs_style", d.use_obs_style),
            style: HdmiStyle::read(h.get("style").and_then(Value::as_object)),
        }
    }
}
