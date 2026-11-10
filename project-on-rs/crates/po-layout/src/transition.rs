//! Les transitions entre deux slides (`ProjectionWindow._paint_transition`, 2.8) : fondu,
//! glissement, zoom, flou et balayage. Une image de transition est une liste d'affichage comme les
//! autres : le fond du nouveau slide, puis l'ancien et le nouveau contenu dans des groupes animés.

use po_design::{Animation, AnimationKind, Direction};

use crate::display::{DisplayList, Group, Item};

/// La courbe de la 2.8 : l'animation Qt suit `InOutCubic`, puis `_ease` (smootherstep) s'y ajoute.
pub fn ease(t: f32) -> f32 {
    let t = t.clamp(0.0, 1.0);
    let cubic = if t < 0.5 { 4.0 * t * t * t } else { 1.0 - (-2.0 * t + 2.0).powi(3) / 2.0 };
    let p = cubic.clamp(0.0, 1.0);
    p * p * p * (p * (p * 6.0 - 15.0) + 10.0)
}

fn vector(direction: Direction) -> (f32, f32) {
    match direction {
        Direction::Up => (0.0, -1.0),
        Direction::Down => (0.0, 1.0),
        Direction::Left => (-1.0, 0.0),
        Direction::Right => (1.0, 0.0),
    }
}

fn group(items: &[Item], opacity: f32) -> Group {
    Group { opacity, ..Group::plain(items.to_vec()) }
}

/// Le rectangle révélé par un balayage, depuis le côté opposé au sens (« monter » = apparaître depuis
/// le bas).
fn reveal_clip(rect: [f32; 4], dx: f32, dy: f32, e: f32) -> [f32; 4] {
    let [x, y, w, h] = rect;
    if dy < 0.0 {
        [x, y + h - h * e, w, h * e]
    } else if dy > 0.0 {
        [x, y, w, h * e]
    } else if dx < 0.0 {
        [x + w - w * e, y, w * e, h]
    } else {
        [x, y, w * e, h]
    }
}

/// La part de la scène pas encore révélée (le complément de [`reveal_clip`]).
fn hidden_clip(rect: [f32; 4], dx: f32, dy: f32, e: f32) -> [f32; 4] {
    let [x, y, w, h] = rect;
    if dy < 0.0 {
        [x, y, w, h - h * e]
    } else if dy > 0.0 {
        [x, y + h * e, w, h - h * e]
    } else if dx < 0.0 {
        [x, y, w - w * e, h]
    } else {
        [x + w * e, y, w - w * e, h]
    }
}

/// Le rayon du flou de la transition « flou » (`max(10, min(40, durée // 16))`).
pub fn blur_radius(animation: &Animation) -> f32 {
    (animation.duration_ms / 16).clamp(10, 40) as f32
}

/// L'image de la transition de `from` vers `to` au temps `t` (0 = début, 1 = fin).
pub fn frame(from: &DisplayList, to: &DisplayList, animation: &Animation, t: f32) -> DisplayList {
    let mut out = DisplayList { items: Vec::new(), overlay: Vec::new(), ..to.clone() };
    let e = ease(t);
    let (dx, dy) = vector(animation.direction);
    let (w, h) = (to.width, to.height);
    let stage = to.stage;
    let center = [stage[0] + stage[2] / 2.0, stage[1] + stage[3] / 2.0];
    let groups: Vec<Group> = match animation.kind {
        AnimationKind::None => vec![group(&to.items, 1.0)],
        AnimationKind::Fade => vec![group(&from.items, 1.0 - e), group(&to.items, e)],
        AnimationKind::Slide => vec![
            Group { dx: dx * w * e, dy: dy * h * e, ..group(&from.items, 1.0) },
            Group { dx: -dx * w * (1.0 - e), dy: -dy * h * (1.0 - e), ..group(&to.items, 1.0) },
        ],
        AnimationKind::Scale => vec![
            Group { scale: 1.0 + 0.06 * e, origin: center, ..group(&from.items, 1.0 - e) },
            Group { scale: 0.94 + 0.06 * e, origin: center, ..group(&to.items, e) },
        ],
        AnimationKind::Blur => {
            let radius = blur_radius(animation);
            if e < 0.5 {
                let p = e / 0.5;
                vec![group(&from.items, 1.0 - p), Group { blur: radius, ..group(&from.items, p) }]
            } else {
                let p = (e - 0.5) / 0.5;
                vec![Group { blur: radius, ..group(&to.items, 1.0 - p) }, group(&to.items, p)]
            }
        }
        // Le balayage : l'ancien texte s'efface là où le nouveau apparaît (la 2.8 le laissait
        // dessous jusqu'à la fin de l'animation).
        AnimationKind::Reveal => vec![
            Group { clip: Some(hidden_clip(stage, dx, dy, e)), ..group(&from.items, 1.0) },
            Group { clip: Some(reveal_clip(stage, dx, dy, e)), ..group(&to.items, 1.0) },
        ],
    };
    out.items = groups.into_iter().filter(|g| g.opacity > 0.004 && !g.items.is_empty()).map(Item::Group).collect();
    // L'identification ne bouge pas ; elle ne passe en fondu que si elle change (de la Bible à une
    // prédication, par exemple).
    out.overlay = if from.overlay == to.overlay || animation.kind == AnimationKind::None {
        to.overlay.clone()
    } else {
        [group(&from.overlay, 1.0 - e), group(&to.overlay, e)]
            .into_iter()
            .filter(|g| g.opacity > 0.004 && !g.items.is_empty())
            .map(Item::Group)
            .collect()
    };
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::display::Rgba;

    fn list(text: &str) -> DisplayList {
        let mut l = DisplayList::blank(1920.0, 1080.0, Rgba::BLACK);
        l.stage = [96.0, 54.0, 1728.0, 972.0];
        l.items = vec![Item::Rect { x: 0.0, y: 0.0, w: 10.0, h: 10.0, radius: 0.0, color: Rgba::WHITE }];
        l.overlay = if text.is_empty() { Vec::new() } else { l.items.clone() };
        l
    }

    #[test]
    fn easing_like_the_2x() {
        assert_eq!(ease(0.0), 0.0);
        assert_eq!(ease(1.0), 1.0);
        assert!((ease(0.5) - 0.5).abs() < 1e-6);
        assert!(ease(0.25) < 0.1, "démarrage doux : {}", ease(0.25));
    }

    #[test]
    fn every_kind_starts_on_the_old_slide_and_ends_on_the_new() {
        let (a, b) = (list("a"), list(""));
        for kind in [
            AnimationKind::Fade,
            AnimationKind::Slide,
            AnimationKind::Scale,
            AnimationKind::Blur,
            AnimationKind::Reveal,
        ] {
            let anim = Animation { kind, duration_ms: 420, direction: Direction::Up };
            let start = frame(&a, &b, &anim, 0.0);
            let end = frame(&a, &b, &anim, 1.0);
            let Item::Group(first) = &start.items[0] else { panic!() };
            assert_eq!(first.opacity, 1.0, "{kind:?}");
            let Item::Group(last) = end.items.last().unwrap() else { panic!() };
            assert_eq!((last.opacity, last.dx, last.dy, last.scale, last.blur), (1.0, 0.0, 0.0, 1.0, 0.0), "{kind:?}");
            // L'identification de l'ancien slide s'efface.
            assert!(end.overlay.is_empty() || matches!(&end.overlay[0], Item::Group(g) if g.items.is_empty()));
        }
        let reveal =
            frame(&a, &b, &Animation { kind: AnimationKind::Reveal, duration_ms: 420, direction: Direction::Up }, 0.5);
        let Item::Group(g) = &reveal.items[1] else { panic!() };
        let clip = g.clip.unwrap();
        assert!((clip[1] - (54.0 + 972.0 / 2.0)).abs() < 1.0);
    }
}
