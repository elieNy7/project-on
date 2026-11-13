//! Les icônes de l'interface : des tracés Lucide (licence ISC, `LICENSE-lucide.txt`), repris de
//! Pgraphics, rendus une fois au démarrage en textures blanches (resvg), puis teintés à
//! l'affichage. Elles ne dépendent d'aucune police.

use std::sync::OnceLock;

use egui::{Color32, Rect, TextureHandle, TextureId, Vec2};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Icon {
    Monitor,
    Settings,
    Eye,
    EyeOff,
    Plus,
    X,
    Search,
    Cast,
    Image,
    Mic,
    ChevronDown,
    ChevronUp,
    ChevronLeft,
    ChevronRight,
    Copy,
    Clock,
    Info,
    Alert,
    Check,
    Globe,
    SwatchBook,
    ListVideo,
    Refresh,
    Maximize,
    Presentation,
    CircleStop,
    BookOpen,
    Music,
    FileText,
    Library,
    Play,
    Star,
    /// L'étoile pleine (un favori).
    StarFilled,
    History,
}

pub const ALL: [Icon; 34] = [
    Icon::Monitor,
    Icon::Settings,
    Icon::Eye,
    Icon::EyeOff,
    Icon::Plus,
    Icon::X,
    Icon::Search,
    Icon::Cast,
    Icon::Image,
    Icon::Mic,
    Icon::ChevronDown,
    Icon::ChevronUp,
    Icon::ChevronLeft,
    Icon::ChevronRight,
    Icon::Copy,
    Icon::Clock,
    Icon::Info,
    Icon::Alert,
    Icon::Check,
    Icon::Globe,
    Icon::SwatchBook,
    Icon::ListVideo,
    Icon::Refresh,
    Icon::Maximize,
    Icon::Presentation,
    Icon::CircleStop,
    Icon::BookOpen,
    Icon::Music,
    Icon::FileText,
    Icon::Library,
    Icon::Play,
    Icon::Star,
    Icon::StarFilled,
    Icon::History,
];

/// Le contenu SVG (grille 24 × 24, trait de 2) de chaque icône.
fn body(icon: Icon) -> &'static str {
    match icon {
        Icon::Monitor => r#"<rect width="20" height="14" x="2" y="3" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/>"#,
        Icon::Settings => {
            r#"<path d="M20 7h-9"/><path d="M14 17H5"/><circle cx="17" cy="17" r="3"/><circle cx="7" cy="7" r="3"/>"#
        }
        Icon::Eye => {
            r#"<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>"#
        }
        Icon::EyeOff => {
            r#"<path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"/><path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"/><path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"/><path d="m2 2 20 20"/>"#
        }
        Icon::Plus => r#"<path d="M5 12h14"/><path d="M12 5v14"/>"#,
        Icon::X => r#"<path d="M18 6 6 18"/><path d="m6 6 12 12"/>"#,
        Icon::Search => r#"<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>"#,
        Icon::Cast => {
            r#"<path d="M2 8V6a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-6"/><path d="M2 12a9 9 0 0 1 8 8"/><path d="M2 16a5 5 0 0 1 4 4"/><path d="M2 20h.01"/>"#
        }
        Icon::Image => {
            r#"<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>"#
        }
        Icon::Mic => {
            r#"<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><path d="M12 19v3"/>"#
        }
        Icon::ChevronDown => r#"<path d="m6 9 6 6 6-6"/>"#,
        Icon::ChevronUp => r#"<path d="m18 15-6-6-6 6"/>"#,
        Icon::ChevronLeft => r#"<path d="m15 18-6-6 6-6"/>"#,
        Icon::ChevronRight => r#"<path d="m9 18 6-6-6-6"/>"#,
        Icon::Copy => {
            r#"<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>"#
        }
        Icon::Clock => r#"<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>"#,
        Icon::Info => r#"<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>"#,
        Icon::Alert => {
            r#"<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>"#
        }
        Icon::Check => r#"<path d="M20 6 9 17l-5-5"/>"#,
        Icon::Globe => {
            r#"<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>"#
        }
        Icon::SwatchBook => {
            r#"<path d="M11 17a4 4 0 0 1-8 0V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2Z"/><path d="M16.7 13H19a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H7"/><path d="M7 17h.01"/><path d="m11 8 2.3-2.3a2.4 2.4 0 0 1 3.404.004L18.6 7.6a2.4 2.4 0 0 1 .026 3.434L9.9 19.8"/>"#
        }
        Icon::ListVideo => {
            r#"<path d="M12 12H3"/><path d="M16 6H3"/><path d="M12 18H3"/><path d="m16 12 5 3-5 3v-6Z"/>"#
        }
        Icon::Refresh => {
            r#"<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>"#
        }
        Icon::Maximize => {
            r#"<path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>"#
        }
        Icon::Presentation => {
            r#"<path d="M2 3h20"/><path d="M21 3v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V3"/><path d="m7 21 5-5 5 5"/>"#
        }
        Icon::CircleStop => r#"<circle cx="12" cy="12" r="10"/><rect x="9" y="9" width="6" height="6" rx="1"/>"#,
        Icon::BookOpen => {
            r#"<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>"#
        }
        Icon::Music => r#"<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>"#,
        Icon::FileText => {
            r#"<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>"#
        }
        Icon::Library => r#"<path d="m16 6 4 14"/><path d="M12 6v14"/><path d="M8 8v12"/><path d="M4 4v16"/>"#,
        Icon::Play => r#"<polygon points="6 3 20 12 6 21 6 3"/>"#,
        Icon::Star => {
            r#"<path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"/>"#
        }
        Icon::StarFilled => {
            r##"<path fill="#ffffff" d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"/>"##
        }
        Icon::History => {
            r#"<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>"#
        }
    }
}

/// La taille de rendu : nette jusqu'à 24 points sur un écran 200 %.
const RASTER: u32 = 64;

static TEXTURES: OnceLock<Vec<TextureHandle>> = OnceLock::new();

fn rasterize(svg_body: &str) -> Option<egui::ColorImage> {
    let svg = format!(
        r##"<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{svg_body}</svg>"##
    );
    let tree = resvg::usvg::Tree::from_str(&svg, &resvg::usvg::Options::default()).ok()?;
    let mut pixmap = resvg::tiny_skia::Pixmap::new(RASTER, RASTER)?;
    let scale = RASTER as f32 / 24.0;
    resvg::render(&tree, resvg::tiny_skia::Transform::from_scale(scale, scale), &mut pixmap.as_mut());
    // tiny-skia rend en alpha prémultiplié, comme egui l'attend.
    Some(egui::ColorImage::from_rgba_premultiplied([RASTER as usize, RASTER as usize], pixmap.data()))
}

/// Rend toutes les icônes (une fois, au démarrage).
pub fn load(ctx: &egui::Context) {
    if TEXTURES.get().is_some() {
        return;
    }
    let options = egui::TextureOptions {
        magnification: egui::TextureFilter::Linear,
        minification: egui::TextureFilter::Linear,
        mipmap_mode: Some(egui::TextureFilter::Linear),
        ..Default::default()
    };
    let textures = ALL
        .iter()
        .map(|icon| {
            let image =
                rasterize(body(*icon)).unwrap_or_else(|| egui::ColorImage::filled([2, 2], Color32::TRANSPARENT));
            ctx.load_texture(format!("icone-{icon:?}"), image, options)
        })
        .collect();
    let _ = TEXTURES.set(textures);
}

pub fn texture(icon: Icon) -> Option<TextureId> {
    let index = ALL.iter().position(|i| *i == icon)?;
    TEXTURES.get().and_then(|t| t.get(index)).map(TextureHandle::id)
}

/// L'icône comme image egui.
pub fn image(icon: Icon, size: f32, color: Color32) -> egui::Image<'static> {
    let id = texture(icon).unwrap_or_default();
    egui::Image::new(egui::load::SizedTexture::new(id, Vec2::splat(size))).tint(color)
}

/// Peint l'icône dans `rect`, teintée.
pub fn paint(painter: &egui::Painter, rect: Rect, icon: Icon, color: Color32) {
    if let Some(id) = texture(icon) {
        let uv = Rect::from_min_max(egui::pos2(0.0, 0.0), egui::pos2(1.0, 1.0));
        painter.image(id, rect, uv, color);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_icon_draws() {
        for icon in ALL {
            let image = rasterize(body(icon)).unwrap_or_else(|| panic!("{icon:?} : SVG illisible"));
            let ink = image.pixels.iter().filter(|p| p.a() > 0).count();
            assert!(ink > 40, "{icon:?} : presque vide ({ink} pixels)");
        }
    }
}
