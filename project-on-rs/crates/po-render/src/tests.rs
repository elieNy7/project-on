//! Les essais du rendu, sans fenêtre.

use po_design::{
    Animation, AnimationKind, Direction, IdentificationStyle, ImageFit, ReferencePosition, RoomDesign, SlideSource,
    contrast_ratio,
};
use po_layout::{DisplayList, Fonts, Item, Slide, bundled_backgrounds_dir, bundled_fonts_dir, layout_room, transition};

use super::*;

fn fonts() -> Fonts {
    Fonts::from_dirs(&[bundled_fonts_dir()])
}

fn design(background: Option<&str>, color: Rgba) -> RoomDesign {
    let mut d = RoomDesign::default();
    d.text.family = "Passion One".into();
    d.text.size = 45.0;
    d.text.uppercase = true;
    d.reference.size = 33.0;
    d.reference.position = ReferencePosition::Top;
    d.shadow = None;
    d.background.color = color;
    d.background.image = background.map(|name| bundled_backgrounds_dir().join(name).to_string_lossy().into_owned());
    d.background.image_fit = ImageFit::Cover;
    d
}

fn lay(fonts: &mut Fonts, renderer: &mut Renderer, slide: &Slide, design: &RoomDesign, w: f32, h: f32) -> DisplayList {
    let mut probe = |list: &DisplayList, zone: [f32; 4]| renderer.backdrop_luminance(list, zone);
    layout_room(fonts, slide, design, w, h, &mut probe)
}

#[test]
fn draws_text_inside_the_safe_area() {
    let mut fonts = fonts();
    let mut renderer = Renderer::new();
    let d = design(None, Rgba::rgb(12, 15, 20));
    let slide = Slide::new("Car Dieu a tant aimé le monde", "Jean 3:16", SlideSource::Bible);
    let list = lay(&mut fonts, &mut renderer, &slide, &d, 960.0, 540.0);
    let pixmap = renderer.render(&mut fonts, &list, 960, 540).unwrap();
    let mut lit = 0usize;
    for (i, px) in pixmap.pixels().iter().enumerate() {
        let (x, y) = ((i % 960) as f32, (i / 960) as f32);
        if px.red() > 100 {
            lit += 1;
            assert!(
                (47.0..=913.0).contains(&x) && (26.0..=514.0).contains(&y),
                "pixel de texte hors zone en ({x}, {y})"
            );
        }
    }
    assert!(lit > 1000, "texte presque invisible ({lit} pixels)");
}

#[test]
fn background_image_and_scrim_are_drawn() {
    let mut fonts = fonts();
    let mut renderer = Renderer::new();
    let d = design(Some("bg-clair-ivoire_16x9.png"), Rgba::rgb(0, 0, 0));
    let slide = Slide::new("", "", SlideSource::Custom);
    let list = lay(&mut fonts, &mut renderer, &slide, &d, 480.0, 270.0);
    assert!(list.backdrop.iter().any(|i| matches!(i, Item::Image { .. })));
    let lum = renderer.backdrop_luminance(&list, [0.0, 0.0, 480.0, 270.0]);
    assert!(lum > 0.3, "un fond ivoire doit rester clair : {lum}");
}

/// Le contraste de l'identification rendue : l'encre contre le fond (halo compris) sous le texte.
fn identification_contrast(fonts: &mut Fonts, renderer: &mut Renderer, list: &DisplayList) -> f32 {
    let line = list.overlay_lines().next().expect("identification présente").clone();
    let (w, h) = (list.width as u32, list.height as u32);
    // Le fond sous le texte : la même image, l'encre rendue invisible (halo et bande gardés).
    let mut hidden = list.clone();
    for item in &mut hidden.overlay {
        if let Item::Text(t) = item {
            t.color = t.color.with_alpha(0.0);
        }
    }
    let under = renderer.render(fonts, &hidden, w, h).unwrap();
    let top = (line.baseline - line.size * 0.7).max(0.0) as u32;
    let bottom = (line.baseline as u32).min(h - 1);
    let left = (line.x - line.width / 2.0).max(0.0) as u32;
    let right = ((line.x + line.width / 2.0) as u32).min(w - 1);
    let mut sum = 0.0f64;
    let mut n = 0.0f64;
    for y in top..bottom {
        for x in left..right {
            let c = under.pixel(x, y).unwrap().demultiply();
            sum += f64::from(Rgba::new(c.red(), c.green(), c.blue(), 255).luminance());
            n += 1.0;
        }
    }
    let background = (sum / n.max(1.0)) as f32;
    // L'encre composée sur ce fond.
    let ink = line.color.luminance() * line.color.alpha() + background * (1.0 - line.color.alpha());
    contrast_ratio(ink, background)
}

#[test]
fn identification_is_readable_on_every_background() {
    let mut fonts = fonts();
    let mut renderer = Renderer::new();
    // (nom, image, couleur, dégradé, luminance attendue sous l'identification)
    type Case<'a> = (&'a str, Option<&'a str>, Rgba, bool, std::ops::RangeInclusive<f32>);
    let backgrounds: [Case; 6] = [
        ("sombre", None, Rgba::rgb(12, 15, 20), false, 0.0..=0.05),
        ("clair", None, Rgba::rgb(240, 236, 226), false, 0.7..=1.0),
        ("gris moyen", None, Rgba::rgb(128, 128, 128), false, 0.15..=0.3),
        ("clair avec dégradé", None, Rgba::rgb(240, 236, 226), true, 0.0..=1.0),
        ("photo claire", Some("bg-clair-sable_16x9.png"), Rgba::BLACK, true, 0.0..=1.0),
        ("photo", Some("bg-photo-montagnes-aube_16x9.png"), Rgba::BLACK, true, 0.0..=1.0),
    ];
    let slide = Slide::new("La foi est une ferme assurance.", "47-0412 - La Foi - ¶12", SlideSource::Sermon);
    for (name, image, color, gradient, expected) in backgrounds {
        for style in IdentificationStyle::ALL {
            let mut d = design(image, color);
            if !gradient {
                d.background.gradient = None;
            }
            d.identification.style = style;
            let list = lay(&mut fonts, &mut renderer, &slide, &d, 960.0, 540.0);
            let ratio = identification_contrast(&mut fonts, &mut renderer, &list);
            let zone = po_layout::identification::probe_zone(960.0, 540.0, 27.0);
            let lum = renderer.backdrop_luminance(&list, zone);
            eprintln!("contraste {name} / {style:?} : {ratio:.2} (fond {lum:.2})");
            assert!(expected.contains(&lum), "{name} : fond de luminance {lum:.2}, hors de {expected:?}");
            assert!(ratio >= 4.5, "{name} / {style:?} : contraste {ratio:.2} (fond {lum:.2})");
        }
    }
}

#[test]
fn transitions_blend_the_two_slides() {
    let mut fonts = fonts();
    let mut renderer = Renderer::new();
    let d = design(None, Rgba::BLACK);
    let a = lay(&mut fonts, &mut renderer, &Slide::new("Gloire", "", SlideSource::Custom), &d, 480.0, 270.0);
    let b = lay(&mut fonts, &mut renderer, &Slide::new("Amen", "", SlideSource::Custom), &d, 480.0, 270.0);
    for kind in
        [AnimationKind::Fade, AnimationKind::Slide, AnimationKind::Scale, AnimationKind::Blur, AnimationKind::Reveal]
    {
        let animation = Animation { kind, duration_ms: 420, direction: Direction::Up };
        let start = renderer.render(&mut fonts, &transition::frame(&a, &b, &animation, 0.0), 480, 270).unwrap();
        let end = renderer.render(&mut fonts, &transition::frame(&a, &b, &animation, 1.0), 480, 270).unwrap();
        let alone_a = renderer.render(&mut fonts, &a, 480, 270).unwrap();
        let alone_b = renderer.render(&mut fonts, &b, 480, 270).unwrap();
        // Passer par un calque arrondit d'un niveau les bords des lettres : seuls les écarts visibles
        // comptent (plus de 3 niveaux sur 255).
        let differ = |x: &Pixmap, y: &Pixmap| {
            x.pixels()
                .iter()
                .zip(y.pixels())
                .filter(|(p, q)| {
                    [(p.red(), q.red()), (p.green(), q.green()), (p.blue(), q.blue())]
                        .iter()
                        .any(|(a, b)| a.abs_diff(*b) > 3)
                })
                .count()
        };
        assert!(differ(&start, &alone_a) < 50, "{kind:?} : le début n'est pas l'ancien slide");
        assert!(differ(&end, &alone_b) < 50, "{kind:?} : la fin n'est pas le nouveau slide");
        let middle = renderer.render(&mut fonts, &transition::frame(&a, &b, &animation, 0.5), 480, 270).unwrap();
        assert!(differ(&middle, &alone_b) > 50, "{kind:?} : rien ne bouge au milieu");
    }
}

#[test]
fn fast_shadow_looks_like_the_full_screen_layer() {
    let mut fonts = fonts();
    let mut renderer = Renderer::new();
    // Les réglages par défaut de la 2.x : ombre portée de 18 px.
    let d = RoomDesign::default();
    let slide = Slide::new("Car Dieu a tant aimé le monde qu'il a donné son Fils", "Jean 3:16", SlideSource::Bible);
    let list = lay(&mut fonts, &mut renderer, &slide, &d, 1920.0, 1080.0);
    let lines: Vec<_> = list.text_lines().filter(|l| l.shadow.is_some()).cloned().collect();
    assert!(!lines.is_empty(), "les réglages par défaut ont une ombre");
    for (w, h) in [(1920u32, 1080u32), (960, 540)] {
        let transform = Transform::from_scale(w as f32 / 1920.0, h as f32 / 1080.0);
        for line in &lines {
            let Some(shadow) = line.shadow else { continue };
            let path = renderer.line_path(&mut fonts, line).unwrap();
            let mut cropped = Pixmap::new(w, h).unwrap();
            draw_shadowed(&mut cropped, &path, shadow, None, transform);
            // L'ancienne façon : un calque de la taille de l'écran.
            let mut full = Pixmap::new(w, h).unwrap();
            let mut layer = Pixmap::new(w, h).unwrap();
            layer.fill_path(&path, &paint(shadow.color), FillRule::Winding, transform, None);
            blur::blur_region(&mut layer, path.bounds().transform(transform).unwrap(), shadow.blur * transform.sx);
            let offset = Transform::from_translate(shadow.dx * transform.sx, shadow.dy * transform.sy);
            full.draw_pixmap(0, 0, layer.as_ref(), &PixmapPaint::default(), offset, None);
            assert!(full.pixels().iter().any(|p| p.alpha() > 0), "ombre invisible");
            // Seule l'opacité est floutée maintenant : les arrondis diffèrent d'un ou deux niveaux.
            let worst = cropped.data().iter().zip(full.data()).map(|(a, b)| a.abs_diff(*b)).max().unwrap_or(0);
            assert!(worst <= 2, "{w}×{h} : « {} » s'écarte de {worst} niveaux", line.text);
            // Le texte posé depuis la même couverture que l'ombre : comme un remplissage direct.
            let invisible = TextShadow { color: Rgba::TRANSPARENT, ..shadow };
            let mut ours = Pixmap::new(w, h).unwrap();
            ours.fill(Color::from_rgba8(30, 60, 90, 255));
            let mut direct = ours.clone();
            draw_shadowed(&mut ours, &path, invisible, Some(line.color), transform);
            direct.fill_path(&path, &paint(line.color), FillRule::Winding, transform, None);
            let worst = ours.data().iter().zip(direct.data()).map(|(a, b)| a.abs_diff(*b)).max().unwrap_or(0);
            assert!(worst <= 2, "{w}×{h} : le texte « {} » s'écarte de {worst} niveaux", line.text);
        }
    }
}

#[test]
fn outlined_subtitles_are_ringed_with_their_outline_color() {
    use po_design::graphics::{SubtitleLook, SubtitleStyle};
    let mut fonts = fonts();
    let mut renderer = Renderer::new();
    let mut style = SubtitleStyle::new(SubtitleLook::Outline);
    style.font.outline = Some((Rgba::rgb(255, 0, 0), 4.0));
    let graphic = po_layout::graphics::layout_subtitle(&mut fonts, "Que ton règne vienne", &style, 960.0, 540.0);
    let mut list = DisplayList::blank(960.0, 540.0, Rgba::TRANSPARENT);
    list.items = graphic.items();
    let pixmap = renderer.render(&mut fonts, &list, 960, 540).unwrap();
    let (mut red, mut white) = (0, 0);
    for p in pixmap.pixels() {
        if p.alpha() == 255 && p.red() > 200 && p.green() < 60 {
            red += 1;
        }
        if p.alpha() == 255 && p.red() > 240 && p.green() > 240 && p.blue() > 240 {
            white += 1;
        }
    }
    assert!(red > 500 && white > 500, "contour {red}, lettres {white}");
    // Le fond reste transparent autour.
    assert_eq!(pixmap.pixel(5, 5).unwrap().alpha(), 0);
}
