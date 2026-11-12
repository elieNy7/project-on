//! L'identité visuelle de Project-On, partie de celle de Pgraphics (ParaTech SARL) : en 3.0, bleu
//! nuit et or, Inter en quatre graisses, cartes et contrôles en relief doux.
//!
//! Origine : `pgraphics-rs/crates/pgraphics/src/theme.rs` (Pgraphics 0.4.0), repris le 2026-11-09 et
//! publié ici sous la licence MIT de Project-On (décision du 9 novembre 2026). Adaptations : les
//! polices viennent du dossier `assets/fonts` de Project-On, la hauteur des contrôles est fixée ici,
//! et le vert / rouge de l'Aperçu et du Direct portent les noms de Project-On.

use egui::{Color32, CornerRadius, FontFamily, FontId, Margin, Shadow, Stroke, TextStyle, Vec2};

const fn rgb(r: u8, g: u8, b: u8) -> Color32 {
    Color32::from_rgb(r, g, b)
}

/// Le logo de Project-On (1024 × 1024), intégré à l'exécutable : il ne peut pas manquer.
pub const LOGO_PNG: &[u8] = include_bytes!("../../../../assets/logo/app icon.png");

/// Le logo réduit à `side` pixels, en RVBA.
fn logo_rgba(side: u32) -> Option<([usize; 2], Vec<u8>)> {
    let image = image::load_from_memory(LOGO_PNG).ok()?;
    let small = image.resize(side, side, image::imageops::FilterType::Lanczos3).to_rgba8();
    Some(([small.width() as usize, small.height() as usize], small.into_raw()))
}

/// L'icône des fenêtres (régie, projection) : le logo, comme le raccourci du Bureau.
/// Décodée une seule fois (la fenêtre de projection la redonne à chaque image).
pub fn window_icon() -> Option<std::sync::Arc<egui::IconData>> {
    static ICON: std::sync::OnceLock<Option<std::sync::Arc<egui::IconData>>> = std::sync::OnceLock::new();
    ICON.get_or_init(|| {
        let ([w, h], rgba) = logo_rgba(256)?;
        Some(std::sync::Arc::new(egui::IconData { rgba, width: w as u32, height: h as u32 }))
    })
    .clone()
}

/// Le logo pour l'interface (barre du haut, accueil), gardé dans le contexte.
pub fn logo_texture(ctx: &egui::Context) -> Option<egui::TextureId> {
    let id = egui::Id::unique("po-logo");
    if let Some(handle) = ctx.data(|d| d.get_temp::<egui::TextureHandle>(id)) {
        return Some(handle.id());
    }
    let (size, rgba) = logo_rgba(192)?;
    let image = egui::ColorImage::from_rgba_unmultiplied(size, &rgba);
    let handle = ctx.load_texture("po-logo", image, egui::TextureOptions::LINEAR);
    let texture = handle.id();
    ctx.data_mut(|d| d.insert_temp(id, handle));
    Some(texture)
}

/// Le logo peint dans `rect`.
pub fn paint_logo(painter: &egui::Painter, rect: egui::Rect) {
    if let Some(texture) = logo_texture(painter.ctx()) {
        let uv = egui::Rect::from_min_max(egui::pos2(0.0, 0.0), egui::pos2(1.0, 1.0));
        painter.image(texture, rect, uv, Color32::WHITE);
    }
}

// La 3.0 : bleu nuit et or (choix de l'utilisateur du 12 novembre 2026), en relief doux.

/// Le fond de l'espace de travail, sous les cartes (un dégradé part de `BG_TOP`).
pub const BG: Color32 = rgb(0x05, 0x0a, 0x16);
pub const BG_TOP: Color32 = rgb(0x0e, 0x1a, 0x36);
/// Les cartes principales (rail, bibliothèque, moniteurs) et les barres.
pub const PANEL: Color32 = rgb(0x0b, 0x14, 0x29);
/// Les cartes posées sur un panneau.
pub const SURFACE: Color32 = rgb(0x12, 0x1d, 0x38);
/// Les contrôles (boutons, champs) et le survol des lignes.
pub const RAISED: Color32 = rgb(0x19, 0x26, 0x46);
pub const HOVER: Color32 = rgb(0x22, 0x33, 0x5c);
/// Le creux des champs de saisie et des pistes.
pub const WELL: Color32 = rgb(0x07, 0x0e, 0x1e);
pub const BORDER: Color32 = rgb(0x1d, 0x2b, 0x4c);
pub const BORDER_STRONG: Color32 = rgb(0x2c, 0x3e, 0x68);
pub const TEXT: Color32 = rgb(0xf4, 0xf0, 0xe6);
pub const MUTED: Color32 = rgb(0x98, 0xa4, 0xc0);
pub const FAINT: Color32 = rgb(0x5f, 0x6c, 0x8e);
/// L'or de la marque : sélection, actions principales.
pub const ACCENT: Color32 = rgb(0xe8, 0xb5, 0x4f);
pub const PVW: Color32 = rgb(0x3a, 0xd0, 0x8c);
pub const PGM: Color32 = rgb(0xf0, 0x4e, 0x5a);
pub const STREAM: Color32 = rgb(0x9b, 0x7b, 0xf7);
pub const WARN: Color32 = rgb(0xf7, 0xa8, 0x3e);
/// L'arrondi des cartes principales.
pub const CARD_RADIUS: u8 = 14;
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

/// La couleur du texte posé sur un fond plein : sombre sur l'or, blanc sur le rouge ou le vert foncé.
pub fn on_color(fill: Color32) -> Color32 {
    let luma = 0.299 * f32::from(fill.r()) + 0.587 * f32::from(fill.g()) + 0.114 * f32::from(fill.b());
    if luma > 150.0 { rgb(0x16, 0x12, 0x08) } else { Color32::WHITE }
}

/// Un dégradé vertical de 64 pixels (blanc opaque en haut, transparent en bas, ou l'inverse),
/// gardé dans le contexte : teinté, il donne le reflet du haut d'un relief ou l'ombre du bas.
fn gradient(ctx: &egui::Context, downward: bool) -> egui::TextureId {
    let id = egui::Id::unique(("po-degrade", downward));
    if let Some(handle) = ctx.data(|d| d.get_temp::<egui::TextureHandle>(id)) {
        return handle.id();
    }
    let pixels: Vec<Color32> = (0..64u32)
        .map(|y| {
            let t = y as f32 / 63.0;
            let a = if downward { 1.0 - t } else { t };
            // Une courbe douce : le reflet se concentre près du bord.
            Color32::from_white_alpha((a * a * 255.0).round() as u8)
        })
        .collect();
    let image = egui::ColorImage::new([1, 64], pixels);
    let handle = ctx.load_texture("po-degrade", image, egui::TextureOptions::LINEAR);
    let texture = handle.id();
    ctx.data_mut(|d| d.insert_temp(id, handle));
    texture
}

fn gradient_shape(
    ctx: &egui::Context,
    rect: egui::Rect,
    radius: CornerRadius,
    tint: Color32,
    top: bool,
) -> egui::Shape {
    let uv = egui::Rect::from_min_max(egui::pos2(0.0, 0.0), egui::pos2(1.0, 1.0));
    egui::epaint::RectShape::filled(rect, radius, tint).with_texture(gradient(ctx, top), uv).into()
}

/// Le relief d'une surface : un reflet clair en haut et une ombre légère en bas.
pub fn paint_relief(painter: &egui::Painter, rect: egui::Rect, radius: CornerRadius, strength: f32) {
    let ctx = painter.ctx();
    let light = Color32::from_white_alpha((20.0 * strength).round().clamp(0.0, 255.0) as u8);
    let dark = Color32::from_black_alpha((55.0 * strength).round().clamp(0.0, 255.0) as u8);
    painter.add(gradient_shape(ctx, rect, radius, light, true));
    painter.add(gradient_shape(ctx, rect, radius, dark, false));
}

/// Une ombre portée douce sous `rect`.
pub fn paint_shadow(
    painter: &egui::Painter,
    rect: egui::Rect,
    radius: CornerRadius,
    offset: i8,
    blur: u8,
    color: Color32,
) {
    let shadow = Shadow { offset: [0, offset], blur, spread: 0, color };
    painter.add(shadow.as_shape(rect, radius));
}

/// Une lueur colorée autour de `rect` (l'Aperçu en vert, le Direct en rouge, l'or d'une sélection).
pub fn paint_glow(painter: &egui::Painter, rect: egui::Rect, radius: CornerRadius, color: Color32, strength: f32) {
    let alpha = (strength * 255.0).round().clamp(0.0, 255.0) as u8;
    let shadow = Shadow { offset: [0, 0], blur: 22, spread: 1, color: color.gamma_multiply_u8(alpha) };
    painter.add(shadow.as_shape(rect, radius));
}

/// Le fond de la fenêtre : bleu nuit, plus clair en haut.
pub fn paint_backdrop(painter: &egui::Painter, rect: egui::Rect) {
    painter.rect_filled(rect, CornerRadius::ZERO, BG);
    let tint = Color32::from_rgba_unmultiplied(BG_TOP.r(), BG_TOP.g(), BG_TOP.b(), 255);
    let uv = egui::Rect::from_min_max(egui::pos2(0.0, 0.0), egui::pos2(1.0, 1.0));
    painter.add(
        egui::epaint::RectShape::filled(rect, CornerRadius::ZERO, tint).with_texture(gradient(painter.ctx(), true), uv),
    );
}

/// Une carte principale de la régie : surface bleu nuit, bord fin, ombre douce, posée sur le fond
/// avec un espace autour (`outer`).
pub fn card_frame(inner: i8, outer: Margin) -> egui::Frame {
    egui::Frame::new()
        .fill(PANEL)
        .stroke(Stroke::new(1.0, BORDER))
        .corner_radius(CornerRadius::same(CARD_RADIUS))
        .inner_margin(Margin::same(inner))
        .outer_margin(outer)
        .shadow(Shadow { offset: [0, 6], blur: 22, spread: 0, color: Color32::from_black_alpha(120) })
}

/// Le reflet du haut d'une carte principale (à peindre en premier dans la carte).
pub fn card_sheen(ui: &egui::Ui, inner: f32) {
    let rect = ui.max_rect().expand(inner);
    let top = egui::Rect::from_min_size(rect.min, egui::vec2(rect.width(), rect.height().min(180.0)));
    let radius = CornerRadius { nw: CARD_RADIUS, ne: CARD_RADIUS, sw: 0, se: 0 };
    let tint = Color32::from_white_alpha(9);
    ui.painter().add(gradient_shape(ui.ctx(), top, radius, tint, true));
}

/// Les polices (Inter en quatre graisses) et le style de toute l'interface.
pub fn install(ctx: &egui::Context, fonts_dir: &std::path::Path) {
    ctx.set_fonts(font_definitions(fonts_dir));

    let radius = CornerRadius::same(8);
    let mut v = egui::Visuals::dark();
    v.panel_fill = PANEL;
    v.window_fill = SURFACE;
    v.window_stroke = Stroke::new(1.0, BORDER_STRONG);
    v.window_corner_radius = CornerRadius::same(CARD_RADIUS);
    v.window_shadow = Shadow { offset: [0, 14], blur: 40, spread: 0, color: Color32::from_black_alpha(150) };
    v.popup_shadow = Shadow { offset: [0, 8], blur: 24, spread: 0, color: Color32::from_black_alpha(130) };
    v.menu_corner_radius = CornerRadius::same(10);
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

    w.active.bg_fill = rgb(0x2a, 0x3e, 0x6c);
    w.active.weak_bg_fill = rgb(0x2a, 0x3e, 0x6c);
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
