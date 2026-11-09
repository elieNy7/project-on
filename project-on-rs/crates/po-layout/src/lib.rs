//! La mise en page de Project-On : un seul moteur, une liste d'affichage dessinée par tous les
//! écrans (fenêtre de projection, projection Web, NDI, HDMI).

mod display;
mod fonts;
mod slide;

/// La base de polices de cosmic-text (pour lister les fichiers à servir aux navigateurs).
pub use cosmic_text::fontdb;
pub use display::{Anchor, DisplayList, Item, Rgba, TextLine};
pub use fonts::{Fonts, VerticalMetrics};
pub use slide::{Fitted, ReferencePosition, SlideContent, SlideStyle, fit_text, layout_slide};

/// Le dossier des polices livrées avec Project-On (`assets/fonts` à la racine du dépôt).
pub fn bundled_fonts_dir() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../assets/fonts")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fonts() -> Fonts {
        let dir = bundled_fonts_dir();
        Fonts::from_files(&[
            dir.join("Passion One/PassionOne-Bold.ttf"),
            dir.join("Passion One/PassionOne-Regular.ttf"),
        ])
    }

    const LONG: &str = "Et maintenant, frère, la foi est une ferme assurance des choses qu'on espère, une \
        démonstration de celles qu'on ne voit pas. Abraham a cru Dieu, et cela lui fut imputé à justice ; il \
        appelait les choses qui n'étaient pas comme si elles étaient, parce que Dieu l'avait dit.";

    fn box_of(list: &DisplayList) -> (f32, f32) {
        let lines: Vec<_> = list.text_lines().collect();
        let widest = lines.iter().map(|l| l.width).fold(0.0, f32::max);
        (widest, lines.len() as f32)
    }

    #[test]
    fn short_text_grows_up_to_the_ceiling() {
        let mut f = fonts();
        let style = SlideStyle::default();
        let list = layout_slide(
            &mut f,
            &SlideContent { text: "Amen".into(), reference: String::new() },
            &style,
            1920.0,
            1080.0,
        );
        let line = list.text_lines().next().unwrap();
        assert_eq!(line.text, "AMEN");
        assert!((line.size - 45.0 * 4.0).abs() < 0.5, "taille {}", line.size);
    }

    #[test]
    fn long_text_stays_inside_the_safe_area() {
        let mut f = fonts();
        let style = SlideStyle::default();
        for (w, h) in [(1920.0, 1080.0), (1280.0, 720.0), (1024.0, 768.0), (3840.0, 2160.0)] {
            let content =
                SlideContent { text: LONG.into(), reference: "47-0412 - La foi est une ferme assurance - ¶12".into() };
            let list = layout_slide(&mut f, &content, &style, w, h);
            let (widest, lines) = box_of(&list);
            assert!(widest <= w * 0.9 + 0.5, "{w}×{h} : ligne de {widest}");
            assert!(lines >= 3.0);
            let v = f.vertical("Passion One", 700);
            for line in list.text_lines() {
                assert!(line.baseline - v.ascent * line.size >= h * 0.05 - 0.5, "{w}×{h} : dépasse en haut");
                assert!(line.baseline + v.descent * line.size <= h * 0.95 + 0.5, "{w}×{h} : dépasse en bas");
            }
        }
    }

    #[test]
    fn lines_are_balanced() {
        let mut f = fonts();
        let fitted = fit_text(
            &mut f,
            "UN DEUX TROIS QUATRE CINQ SIX SEPT HUIT NEUF DIX ONZE",
            "Passion One",
            700,
            900.0,
            2000.0,
            100.0,
            100.0,
            1.18,
        );
        let widths: Vec<f32> = fitted.lines.iter().map(|l| f.width(l, "Passion One", 700, fitted.size)).collect();
        let (min, max) = widths.iter().fold((f32::MAX, 0.0f32), |(a, b), &w| (a.min(w), b.max(w)));
        assert!(fitted.lines.len() >= 2);
        assert!(max - min < max * 0.4, "lignes déséquilibrées : {widths:?}");
    }

    #[test]
    fn display_list_round_trips_in_json() {
        let mut f = fonts();
        let list = layout_slide(
            &mut f,
            &SlideContent { text: LONG.into(), reference: "Jean 3:16".into() },
            &SlideStyle::default(),
            1920.0,
            1080.0,
        );
        let json = serde_json::to_string(&list).unwrap();
        assert!(json.contains("\"kind\":\"text\""));
        let back: DisplayList = serde_json::from_str(&json).unwrap();
        assert_eq!(back, list);
    }
}
