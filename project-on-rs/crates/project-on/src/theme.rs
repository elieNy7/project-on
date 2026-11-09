//! L'identité visuelle de Project-On, reprise de Pgraphics (ParaTech SARL) : palette ardoise et
//! ambre, Inter en quatre graisses, contrôles à plat.
//!
//! Origine : `pgraphics-rs/crates/pgraphics/src/theme.rs` (Pgraphics 0.4.0), repris le 2026-11-09 et
//! publié ici sous la licence MIT de Project-On (décision du 9 novembre 2026). Adaptations : les
//! polices viennent du dossier `assets/fonts` de Project-On, la hauteur des contrôles est fixée ici,
//! et le vert / rouge de l'Aperçu et du Direct portent les noms de Project-On.

use egui::{Color32, CornerRadius, FontFamily, FontId, Margin, Shadow, Stroke, TextStyle, Vec2};

const fn rgb(r: u8, g: u8, b: u8) -> Color32 {
    Color32::from_rgb(r, g, b)
}

/// Le fond de l'espace de travail (autour des moniteurs).
pub const BG: Color32 = rgb(0x0b, 0x12, 0x17);
/// Les panneaux latéraux et les barres.
pub const PANEL: Color32 = rgb(0x11, 0x1a, 0x21);
/// Les cartes posées sur un panneau.
pub const SURFACE: Color32 = rgb(0x17, 0x23, 0x2c);
/// Les contrôles (boutons, champs) et le survol des lignes.
pub const RAISED: Color32 = rgb(0x1f, 0x2e, 0x38);
pub const HOVER: Color32 = rgb(0x27, 0x39, 0x45);
/// Le creux des champs de saisie et des pistes.
pub const WELL: Color32 = rgb(0x0d, 0x15, 0x1b);
pub const BORDER: Color32 = rgb(0x25, 0x34, 0x3e);
pub const BORDER_STRONG: Color32 = rgb(0x34, 0x43, 0x4c);
pub const TEXT: Color32 = rgb(0xf2, 0xf0, 0xe9);
pub const MUTED: Color32 = rgb(0x93, 0xa3, 0xad);
pub const FAINT: Color32 = rgb(0x5f, 0x71, 0x7c);
/// L'ambre de la marque : sélection, actions principales.
pub const ACCENT: Color32 = rgb(0xf2, 0x8c, 0x45);
pub const PVW: Color32 = rgb(0x34, 0xc7, 0x7b);
pub const PGM: Color32 = rgb(0xef, 0x4f, 0x4f);
pub const STREAM: Color32 = rgb(0x9b, 0x7b, 0xf7);
pub const WARN: Color32 = rgb(0xf5, 0xb7, 0x3b);
/// L'Aperçu (ce qu'on prépare) et le Direct (ce que voit l'assemblée), sous les noms de Project-On.
pub const PREVIEW: Color32 = PVW;
pub const LIVE: Color32 = PGM;
/// La hauteur des contrôles ordinaires (le bouton « Normal » de Pgraphics).
pub const CONTROL_HEIGHT: f32 = 26.0;

pub fn regular(size: f32) -> FontId {
    FontId::new(size, FontFamily::Proportional)
}

pub fn medium(size: f32) -> FontId {
    FontId::new(size, FontFamily::Name("medium".into()))
}

pub fn semibold(size: f32) -> FontId {
    FontId::new(size, FontFamily::Name("semibold".into()))
}

pub fn bold(size: f32) -> FontId {
    FontId::new(size, FontFamily::Name("bold".into()))
}

/// Les polices de l'interface : Inter en quatre graisses, et les symboles de Windows.
pub fn font_definitions(fonts_dir: &std::path::Path) -> egui::FontDefinitions {
    let mut fonts = egui::FontDefinitions::default();
    let inter = fonts_dir.join("Inter");
    let data = std::fs::read_dir(&inter)
        .ok()
        .and_then(|d| d.filter_map(Result::ok).find(|e| e.path().extension().is_some_and(|x| x == "ttf")))
        .and_then(|file| std::fs::read(file.path()).ok());
    if let Some(data) = data {
        let data = std::sync::Arc::new(data);
        for (name, weight) in
            [("Inter", 430.0), ("Inter-Medium", 520.0), ("Inter-SemiBold", 610.0), ("Inter-Bold", 720.0)]
        {
            let tweak = egui::FontTweak {
                coords: egui::epaint::text::VariationCoords::new([(b"wght", weight)]),
                ..Default::default()
            };
            fonts.font_data.insert(
                name.into(),
                std::sync::Arc::new(egui::FontData::from_owned(data.as_ref().clone()).tweak(tweak)),
            );
        }
        let fallback = fonts.families.get(&FontFamily::Proportional).cloned().unwrap_or_default();
        if let Some(list) = fonts.families.get_mut(&FontFamily::Proportional) {
            list.insert(0, "Inter".into());
        }
        for (family, font) in [("medium", "Inter-Medium"), ("semibold", "Inter-SemiBold"), ("bold", "Inter-Bold")] {
            let mut list = vec![font.to_string()];
            list.extend(fallback.iter().cloned());
            fonts.families.insert(FontFamily::Name(family.into()), list);
        }
    } else {
        for family in ["medium", "semibold", "bold"] {
            let list = fonts.families.get(&FontFamily::Proportional).cloned().unwrap_or_default();
            fonts.families.insert(FontFamily::Name(family.into()), list);
        }
    }
    // Les symboles qu'Inter n'a pas (flèches, ◀ ▶, coches…) : la police de symboles de Windows, en
    // dernier recours ; sans elle, ils s'affichaient en carrés.
    if let Some(windir) = std::env::var_os("WINDIR")
        && let Ok(bytes) = std::fs::read(std::path::Path::new(&windir).join("Fonts").join("seguisym.ttf"))
    {
        fonts.font_data.insert("symboles".into(), std::sync::Arc::new(egui::FontData::from_owned(bytes)));
        for list in fonts.families.values_mut() {
            list.push("symboles".into());
        }
    }
    fonts
}

/// Les polices (Inter en quatre graisses) et le style de toute l'interface.
pub fn install(ctx: &egui::Context, fonts_dir: &std::path::Path) {
    ctx.set_fonts(font_definitions(fonts_dir));

    let radius = CornerRadius::same(7);
    let mut v = egui::Visuals::dark();
    v.panel_fill = PANEL;
    v.window_fill = SURFACE;
    v.window_stroke = Stroke::new(1.0, BORDER_STRONG);
    v.window_corner_radius = CornerRadius::same(10);
    v.window_shadow = Shadow { offset: [0, 8], blur: 24, spread: 0, color: Color32::from_black_alpha(110) };
    v.popup_shadow = Shadow { offset: [0, 6], blur: 18, spread: 0, color: Color32::from_black_alpha(100) };
    v.menu_corner_radius = CornerRadius::same(8);
    v.extreme_bg_color = WELL;
    v.faint_bg_color = SURFACE;
    v.code_bg_color = WELL;
    v.hyperlink_color = ACCENT;
    v.warn_fg_color = WARN;
    v.error_fg_color = PGM;
    v.selection.bg_fill = ACCENT.gamma_multiply(0.22);
    v.selection.stroke = Stroke::new(1.0, ACCENT);
    v.text_cursor.stroke = Stroke::new(2.0, ACCENT);
    v.slider_trailing_fill = true;
    v.handle_shape = egui::style::HandleShape::Circle;
    v.striped = false;

    let w = &mut v.widgets;
    w.noninteractive.bg_fill = PANEL;
    w.noninteractive.weak_bg_fill = PANEL;
    w.noninteractive.bg_stroke = Stroke::new(1.0, BORDER);
    w.noninteractive.fg_stroke = Stroke::new(1.0, TEXT);
    w.noninteractive.corner_radius = radius;

    w.inactive.bg_fill = RAISED;
    w.inactive.weak_bg_fill = RAISED;
    w.inactive.bg_stroke = Stroke::new(1.0, BORDER);
    w.inactive.fg_stroke = Stroke::new(1.0, TEXT);
    w.inactive.corner_radius = radius;
    w.inactive.expansion = 0.0;

    w.hovered.bg_fill = HOVER;
    w.hovered.weak_bg_fill = HOVER;
    w.hovered.bg_stroke = Stroke::new(1.0, BORDER_STRONG);
    w.hovered.fg_stroke = Stroke::new(1.5, Color32::WHITE);
    w.hovered.corner_radius = radius;
    w.hovered.expansion = 0.0;

    w.active.bg_fill = rgb(0x2d, 0x42, 0x4f);
    w.active.weak_bg_fill = rgb(0x2d, 0x42, 0x4f);
    w.active.bg_stroke = Stroke::new(1.0, ACCENT);
    w.active.fg_stroke = Stroke::new(1.5, Color32::WHITE);
    w.active.corner_radius = radius;
    w.active.expansion = 0.0;

    w.open = w.hovered;

    // Un seul thème, sombre, quel que soit celui de Windows : une régie se lit dans le noir.
    ctx.set_theme(egui::Theme::Dark);
    ctx.all_styles_mut(|s| {
        s.visuals = v.clone();
        s.text_styles = [
            (TextStyle::Small, regular(11.5)),
            (TextStyle::Body, regular(13.5)),
            (TextStyle::Button, medium(13.0)),
            (TextStyle::Heading, semibold(17.0)),
            (TextStyle::Monospace, FontId::monospace(12.5)),
        ]
        .into();
        let sp = &mut s.spacing;
        sp.item_spacing = Vec2::new(8.0, 6.0);
        // Les contrôles d'egui (listes, champs, valeurs) à la hauteur du bouton ordinaire (`widgets::Size`).
        sp.button_padding = Vec2::new(10.0, 4.0);
        sp.interact_size = Vec2::new(36.0, CONTROL_HEIGHT);
        sp.slider_width = 150.0;
        sp.slider_rail_height = 4.0;
        sp.combo_width = 160.0;
        sp.icon_width = 16.0;
        sp.icon_width_inner = 9.0;
        sp.icon_spacing = 6.0;
        sp.menu_margin = Margin::same(6);
        sp.window_margin = Margin::same(12);
        sp.indent = 16.0;
        sp.scroll.bar_width = 6.0;
        sp.scroll.floating = true;
        s.interaction.tooltip_delay = 0.35;
    });
}
