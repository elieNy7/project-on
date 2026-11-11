//! Le fond d'un slide de salle (`SlideCanvas._paint_background` et `_paint_cinematic_scrim`) :
//! couleur ou dégradé, image recadrée ou entière, puis le voile qui garde le texte lisible.

use po_design::{Background, Look, Rgba};

use crate::display::{Item, Stop};

fn black(alpha: f32) -> Rgba {
    // `QColor(0, 0, 0, int(255 * a))` de la 2.8.
    Rgba::new(0, 0, 0, (255.0 * alpha.clamp(0.0, 1.0)) as u8)
}

fn stops(list: &[(f32, Rgba)]) -> Vec<Stop> {
    list.iter().map(|&(at, color)| Stop { at, color }).collect()
}

fn full(w: f32, h: f32, color: Rgba) -> Item {
    Item::Rect { x: 0.0, y: 0.0, w, h, radius: 0.0, color }
}

fn vertical(w: f32, h: f32, y0: f32, y1: f32, list: &[(f32, Rgba)]) -> Item {
    Item::LinearGradient { x: 0.0, y: 0.0, w, h, from: [0.0, y0], to: [0.0, y1], stops: stops(list) }
}

fn vignette(w: f32, h: f32, clear_until: f32, alpha: f32) -> Item {
    Item::RadialGradient {
        x: 0.0,
        y: 0.0,
        w,
        h,
        center: [w / 2.0, h / 2.0],
        radius: w.hypot(h) * 0.62,
        stops: stops(&[(0.0, black(0.0)), (clear_until, black(0.0)), (1.0, black(alpha))]),
    }
}

/// Le rectangle d'une image de `iw` × `ih` posée sur l'écran : recadrée (`cover`) ou entière.
pub fn fit_rect(iw: f32, ih: f32, w: f32, h: f32, contain: bool) -> [f32; 4] {
    if iw <= 0.0 || ih <= 0.0 {
        return [0.0, 0.0, w, h];
    }
    let scale = if contain { (w / iw).min(h / ih) } else { (w / iw).max(h / ih) };
    let (rw, rh) = (iw * scale, ih * scale);
    [w / 2.0 - rw / 2.0, h / 2.0 - rh / 2.0, rw, rh]
}

/// Le voile posé sur une image, selon le style (`cinematic`, `clean`, `split`).
fn scrim(look: Look, dimmer: f32, has_content: bool, w: f32, h: f32) -> Vec<Item> {
    match look {
        Look::Clean => vec![full(w, h, black(dimmer * if has_content { 0.55 } else { 0.20 }))],
        Look::Split => {
            let mut out = Vec::new();
            if has_content {
                // L'ombre ancrée côté texte (à gauche), qui s'efface vers la droite.
                out.push(Item::LinearGradient {
                    x: 0.0,
                    y: 0.0,
                    w,
                    h,
                    from: [0.0, 0.0],
                    to: [w * 0.78, 0.0],
                    stops: stops(&[(0.0, black(dimmer * 0.92)), (0.55, black(dimmer * 0.45)), (1.0, black(0.0))]),
                });
            } else {
                out.push(full(w, h, black(dimmer * 0.22)));
            }
            out.push(vignette(w, h, 0.74, 0.10 + 0.18 * dimmer));
            out
        }
        Look::Cinematic => {
            let mut out = Vec::new();
            if has_content {
                out.push(full(w, h, black(dimmer * 0.55)));
                out.push(vertical(w, h, h * 0.35, h, &[(0.0, black(0.0)), (1.0, black(dimmer * 0.85))]));
                out.push(vertical(w, h, 0.0, h * 0.42, &[(0.0, black(dimmer * 0.55)), (1.0, black(0.0))]));
            } else {
                out.push(full(w, h, black(dimmer * 0.25)));
            }
            out.push(vignette(w, h, 0.72, 0.16 + 0.30 * dimmer));
            out
        }
    }
}

/// La taille d'une image, lue dans son en-tête (sans la décoder).
fn image_size(path: &str) -> Option<(f32, f32)> {
    let size = imagesize::size(path).ok()?;
    Some((size.width as f32, size.height as f32))
}

/// La couleur de fond et les éléments du fond. `image` remplace l'image du design (fond propre à
/// un élément de playlist) ; une image introuvable laisse la couleur, comme la 2.8.
pub fn backdrop(background: &Background, image: Option<&str>, has_content: bool, w: f32, h: f32) -> (Rgba, Vec<Item>) {
    let base = background.color.with_alpha(1.0);
    let mut items = Vec::new();
    if let Some((color2, angle)) = background.gradient {
        let rad = angle.to_radians();
        let (cx, cy) = (w / 2.0, h / 2.0);
        items.push(Item::LinearGradient {
            x: 0.0,
            y: 0.0,
            w,
            h,
            from: [cx - rad.sin() * h, cy + rad.cos() * h],
            to: [cx + rad.sin() * h, cy - rad.cos() * h],
            stops: stops(&[(0.0, base), (1.0, color2.with_alpha(1.0))]),
        });
    }
    let path = image.or(background.image.as_deref()).filter(|p| std::path::Path::new(p).is_file());
    match path.and_then(|p| image_size(p).map(|size| (p, size))) {
        Some((path, (iw, ih))) => {
            let [x, y, rw, rh] = fit_rect(iw, ih, w, h, background.image_fit == po_design::ImageFit::Contain);
            items.push(Item::Image { path: path.to_string(), x, y, w: rw, h: rh, opacity: 1.0 });
            items.extend(scrim(background.look, background.dimmer, has_content, w, h));
        }
        None if background.gradient.is_some() && background.look != Look::Clean => {
            // Vignette de profondeur sur un dégradé uni.
            items.push(Item::RadialGradient {
                x: 0.0,
                y: 0.0,
                w,
                h,
                center: [w / 2.0, h / 2.0],
                radius: w.hypot(h) * 0.62,
                stops: stops(&[(0.0, black(0.0)), (0.75, black(0.0)), (1.0, Rgba::new(0, 0, 0, 60))]),
            });
        }
        None => {}
    }
    (base, items)
}

/// Une image seule, en entier (« contenir »), centrée sur du noir. Introuvable : du noir.
pub fn image_alone(path: &str, w: f32, h: f32) -> (Rgba, Vec<Item>) {
    let mut items = Vec::new();
    if std::path::Path::new(path).is_file()
        && let Some((iw, ih)) = image_size(path)
    {
        let [x, y, rw, rh] = fit_rect(iw, ih, w, h, true);
        items.push(Item::Image { path: path.to_string(), x, y, w: rw, h: rh, opacity: 1.0 });
    }
    (Rgba::BLACK, items)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn an_image_alone_is_shown_whole_on_black() {
        let path = crate::bundled_backgrounds_dir().join("bg-ardoise_4x3.png");
        let (color, items) = image_alone(&path.to_string_lossy(), 1920.0, 1080.0);
        assert_eq!(color, Rgba::BLACK);
        match &items[..] {
            [Item::Image { x, y, w, h, .. }] => {
                assert_eq!((*y, *h), (0.0, 1080.0), "toute la hauteur");
                assert!((*x - 240.0).abs() < 0.5 && (*w - 1440.0).abs() < 0.5, "4:3 centré : {x} {w}");
            }
            other => panic!("{other:?}"),
        }
        assert!(image_alone("C:/introuvable.png", 1920.0, 1080.0).1.is_empty());
    }

    #[test]
    fn cover_and_contain() {
        assert_eq!(fit_rect(1000.0, 1000.0, 1920.0, 1080.0, false), [0.0, -420.0, 1920.0, 1920.0]);
        assert_eq!(fit_rect(1000.0, 1000.0, 1920.0, 1080.0, true), [420.0, 0.0, 1080.0, 1080.0]);
    }

    #[test]
    fn scrims_follow_the_2x_values() {
        let items = scrim(Look::Cinematic, 0.34, true, 1920.0, 1080.0);
        assert_eq!(items[0], full(1920.0, 1080.0, Rgba::new(0, 0, 0, 47)));
        assert_eq!(items.len(), 4);
        assert_eq!(scrim(Look::Clean, 0.34, false, 10.0, 10.0)[0], full(10.0, 10.0, Rgba::new(0, 0, 0, 17)));
    }
}
