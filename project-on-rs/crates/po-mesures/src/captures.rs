//! Les captures de référence de la phase 2, rendues sans fenêtre par le moteur de la 3.0 :
//! l'identification de Branham (4 styles × 4 fonds), la 2.8 et la 3.0 côte à côte, les transitions.

use std::path::Path;

use po_design::{
    Animation, AnimationKind, Direction, IdentificationStyle, ImageFit, ReferencePosition, Rgba, RoomDesign,
    SlideSource,
};
use po_layout::{DisplayList, Fonts, Slide, bundled_backgrounds_dir, bundled_fonts_dir, layout_room, transition};
use po_render::Renderer;
use serde_json::Value;
use tiny_skia::{FilterQuality, Pixmap, PixmapPaint, Transform};

use crate::Result;

const PARAGRAPH: &str = "Et maintenant, la foi est une ferme assurance des choses qu'on espère, une démonstration \
    de celles qu'on ne voit pas. C'est par la foi qu'Abraham a obéi.";
const REFERENCE: &str = "47-0412 - La Foi Est une Ferme Assurance - ¶50";

fn base_design() -> RoomDesign {
    let mut d = RoomDesign::default();
    d.text.family = "Passion One".into();
    d.text.weight = 700;
    d.text.size = 45.0;
    d.text.uppercase = true;
    d.text.line_height = 1.18;
    d.text.color = Rgba::new(255, 255, 255, 234);
    d.reference.size = 33.0;
    d.reference.position = ReferencePosition::Top;
    d.reference.color = Rgba::new(255, 255, 255, 198);
    d.shadow = None;
    d.background.color = Rgba::rgb(12, 15, 20);
    d.background.gradient = None;
    d
}

fn lay(fonts: &mut Fonts, renderer: &mut Renderer, slide: &Slide, design: &RoomDesign, w: f32, h: f32) -> DisplayList {
    let mut probe = |list: &DisplayList, zone: [f32; 4]| renderer.backdrop_luminance(list, zone);
    layout_room(fonts, slide, design, w, h, &mut probe)
}

/// Une planche : les images posées en grille, chacune réduite à `cell` pixels.
fn sheet(images: &[Pixmap], columns: u32, cell: (u32, u32)) -> Result<Pixmap> {
    let rows = (images.len() as u32).div_ceil(columns);
    let mut out = Pixmap::new(columns * cell.0, rows * cell.1).ok_or("planche vide")?;
    out.fill(tiny_skia::Color::from_rgba8(30, 30, 30, 255));
    for (i, image) in images.iter().enumerate() {
        let (col, row) = (i as u32 % columns, i as u32 / columns);
        let scale = Transform::from_row(
            cell.0 as f32 / image.width() as f32,
            0.0,
            0.0,
            cell.1 as f32 / image.height() as f32,
            (col * cell.0) as f32,
            (row * cell.1) as f32,
        );
        let paint = PixmapPaint { quality: FilterQuality::Bicubic, ..PixmapPaint::default() };
        out.draw_pixmap(0, 0, image.as_ref(), &paint, scale, None);
    }
    Ok(out)
}

/// Les 4 styles d'identification sur 4 fonds : sombre, clair, photo claire, photo.
fn identification(fonts: &mut Fonts, renderer: &mut Renderer, out: &Path) -> Result<()> {
    let backgrounds: [(&str, Option<&str>, Rgba); 4] = [
        ("sombre", None, Rgba::rgb(12, 15, 20)),
        ("clair", None, Rgba::rgb(240, 236, 226)),
        ("photo-claire", Some("bg-clair-sable_16x9.png"), Rgba::BLACK),
        ("photo", Some("bg-photo-montagnes-aube_16x9.png"), Rgba::BLACK),
    ];
    let slide = Slide::new(PARAGRAPH, REFERENCE, SlideSource::Sermon);
    let dir = out.join("identification");
    std::fs::create_dir_all(&dir)?;
    let mut images = Vec::new();
    for (name, image, color) in backgrounds {
        for style in IdentificationStyle::ALL {
            let mut d = base_design();
            d.background.color = color;
            d.background.gradient = None;
            if color == Rgba::rgb(240, 236, 226) {
                // Sur un fond clair, un texte sombre (comme le réglerait une église).
                d.text.color = Rgba::new(20, 22, 28, 240);
                d.reference.color = Rgba::new(20, 22, 28, 200);
            }
            d.background.image = image.map(|f| bundled_backgrounds_dir().join(f).to_string_lossy().into_owned());
            d.background.image_fit = ImageFit::Cover;
            d.identification.style = style;
            let list = lay(fonts, renderer, &slide, &d, 1920.0, 1080.0);
            let pixmap = renderer.render(fonts, &list, 1920, 1080)?;
            let file = format!("{name}-{style:?}.png").to_lowercase();
            std::fs::write(dir.join(file), pixmap.encode_png()?)?;
            images.push(pixmap);
        }
    }
    std::fs::write(out.join("identification.png"), sheet(&images, 4, (480, 270))?.encode_png()?)?;
    Ok(())
}

/// La 2.8 et la 3.0 côte à côte, sur les slides capturés par la 2.8 (réglages « utilisateur »).
fn comparison(fonts: &mut Fonts, renderer: &mut Renderer, refs: &Path, out: &Path) -> Result<()> {
    let text = std::fs::read_to_string(refs.join("projection.json"))?;
    let data: Value = serde_json::from_str(&text)?;
    let mut payload = serde_json::Map::new();
    payload.insert("projection".into(), data["configs"]["utilisateur"].clone());
    let mut design = RoomDesign::from_projection(&po_settings::Settings::from_payload(&payload).projection);
    design.identification.enabled = false; // la 2.8 n'en a pas : on compare le même écran
    let mut images = Vec::new();
    for case in data["cas"].as_array().into_iter().flatten().filter(|c| c["config"] == "utilisateur") {
        let index = case["index"].as_u64().unwrap_or(0);
        let capture = refs.join("captures").join(format!("28-{index:04}.png"));
        if !capture.is_file() || images.len() >= 12 {
            continue;
        }
        let Ok(ours) = image::open(&capture) else { continue };
        let rgba = ours.to_rgba8();
        let mut theirs = Pixmap::new(rgba.width(), rgba.height()).ok_or("capture vide")?;
        for (dst, src) in theirs.pixels_mut().iter_mut().zip(rgba.pixels()) {
            *dst = tiny_skia::ColorU8::from_rgba(src[0], src[1], src[2], src[3]).premultiply();
        }
        let source = match case["kind"].as_str() {
            Some("hymn") => SlideSource::Hymn,
            Some("bible") => SlideSource::Bible,
            Some("sermon") => SlideSource::Sermon,
            _ => SlideSource::Custom,
        };
        let slide = Slide::new(
            case["text"].as_str().unwrap_or_default(),
            case["reference"].as_str().unwrap_or_default(),
            source,
        );
        let list = lay(fonts, renderer, &slide, &design, 1920.0, 1080.0);
        images.push(theirs);
        images.push(renderer.render(fonts, &list, 1920, 1080)?);
    }
    std::fs::write(out.join("comparaison-28-30.png"), sheet(&images, 2, (960, 540))?.encode_png()?)?;
    Ok(())
}

/// Chaque transition à 0, 25, 50, 75 et 100 % de sa durée.
fn transitions(fonts: &mut Fonts, renderer: &mut Renderer, out: &Path) -> Result<()> {
    let mut d = base_design();
    d.background.image = Some(bundled_backgrounds_dir().join("bg-bleu-nuit_16x9.png").to_string_lossy().into_owned());
    let a = lay(fonts, renderer, &Slide::new(PARAGRAPH, REFERENCE, SlideSource::Sermon), &d, 960.0, 540.0);
    let b = lay(
        fonts,
        renderer,
        &Slide::new("Car Dieu a tant aimé le monde", "Jean 3:16", SlideSource::Bible),
        &d,
        960.0,
        540.0,
    );
    let mut images = Vec::new();
    for kind in
        [AnimationKind::Fade, AnimationKind::Slide, AnimationKind::Scale, AnimationKind::Blur, AnimationKind::Reveal]
    {
        let animation = Animation { kind, duration_ms: 420, direction: Direction::Up };
        for t in [0.0, 0.25, 0.5, 0.75, 1.0] {
            images.push(renderer.render(fonts, &transition::frame(&a, &b, &animation, t), 960, 540)?);
        }
    }
    std::fs::write(out.join("transitions.png"), sheet(&images, 5, (384, 216))?.encode_png()?)?;
    Ok(())
}

/// `po-mesures captures <références 2.8> <dossier>`.
pub fn run(refs: &Path, out: &Path) -> Result<()> {
    std::fs::create_dir_all(out)?;
    let mut fonts = Fonts::from_dirs(&[bundled_fonts_dir()]);
    let mut renderer = Renderer::new();
    identification(&mut fonts, &mut renderer, out)?;
    comparison(&mut fonts, &mut renderer, refs, out)?;
    transitions(&mut fonts, &mut renderer, out)?;
    println!("Captures écrites dans {}", out.display());
    Ok(())
}
