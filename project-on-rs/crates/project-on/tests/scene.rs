//! La projection native pose les couches d'un slide sur la carte graphique ; le rendu par le
//! processeur (`po-render`, celui des captures et des sorties NDI / HDMI) dessine la même image
//! d'une transition. Les deux doivent se ressembler à quelques niveaux près, à chaque instant.
//! Rendu hors écran (egui_kittest + wgpu) : aucune fenêtre ne s'ouvre.

// Un essai qui échoue s'arrête : `unwrap` y est permis, aussi dans les fonctions d'aide.
#![allow(clippy::unwrap_used)]

use egui_kittest::Harness;
use po_design::{Animation, AnimationKind, Direction, RoomDesign, SlideSource};
use po_layout::transition::{blur_radius, frame};
use po_layout::{Fonts, Slide, bundled_fonts_dir};
use po_render::Renderer;
use project_on::stage::{Frame, Stage};
use project_on::worker::{Done, Job, Target, render};

const W: u32 = 960;
const H: u32 = 540;

struct Scene {
    stage: Stage,
    from: Option<Done>,
    to: Option<Done>,
    animation: Animation,
    /// Le temps de la transition (0 à 1).
    t: f64,
}

/// L'image posée par la carte graphique au temps `t` de la transition `from` → `to`.
fn gpu(from: &Done, to: &Done, animation: Animation, t: f64) -> image::RgbaImage {
    let scene = Scene { stage: Stage::default(), from: Some(from.clone()), to: Some(to.clone()), animation, t };
    let mut h = Harness::builder().with_size([W as f32, H as f32]).with_pixels_per_point(1.0).wgpu().build_ui_state(
        |ui, scene: &mut Scene| {
            let ctx = ui.ctx().clone();
            if let (Some(a), Some(b)) = (scene.from.take(), scene.to.take()) {
                let a = Frame::upload(&ctx, "a", Slide::new("", "", SlideSource::Custom), a);
                let b = Frame::upload(&ctx, "b", Slide::new("", "", SlideSource::Custom), b);
                scene.stage.show(a, scene.animation, 0.0);
                scene.stage.show(b, scene.animation, 10.0);
            }
            let now = 10.0 + scene.t * f64::from(scene.animation.duration_ms) / 1000.0;
            let full = ctx.content_rect();
            let painter = egui::Painter::new(ctx.clone(), egui::LayerId::background(), full);
            scene.stage.paint(&painter, full, now);
        },
        scene,
    );
    h.run_steps(2);
    h.render().expect("rendu hors écran")
}

/// L'écart moyen (niveaux sur 255) et la part de pixels qui s'écartent de plus de 24 niveaux.
fn compare(gpu: &image::RgbaImage, cpu: &tiny_skia::Pixmap) -> (f64, f64) {
    let mut sum = 0u64;
    let mut far = 0usize;
    for (g, c) in gpu.pixels().zip(cpu.pixels()) {
        let c = c.demultiply();
        let d = [g[0].abs_diff(c.red()), g[1].abs_diff(c.green()), g[2].abs_diff(c.blue())];
        sum += d.iter().map(|v| u64::from(*v)).sum::<u64>();
        if d.iter().any(|v| *v > 24) {
            far += 1;
        }
    }
    let n = (W * H) as f64;
    (sum as f64 / (3.0 * n), far as f64 / n)
}

#[test]
fn the_gpu_draws_each_transition_like_the_cpu() {
    let mut fonts = Fonts::from_dirs(&[bundled_fonts_dir()]);
    let mut renderer = Renderer::new();
    // Les réglages par défaut de la 2.x : ombre portée, dégradé, voile, identification.
    let design = RoomDesign::default();
    let slide = |text: &str, reference: &str| Slide::new(text, reference, SlideSource::Sermon);
    for kind in
        [AnimationKind::Fade, AnimationKind::Slide, AnimationKind::Scale, AnimationKind::Blur, AnimationKind::Reveal]
    {
        let animation = Animation { kind, duration_ms: 420, direction: Direction::Up };
        let job = |s: Slide| Job {
            target: Target::Live,
            id: 1,
            slide: s,
            design: design.clone(),
            width: W,
            height: H,
            blur: Some(blur_radius(&animation)),
        };
        let a =
            render(&mut fonts, &mut renderer, job(slide("La foi est une ferme assurance.", "Hébreux 11:1"))).unwrap();
        let b = render(&mut fonts, &mut renderer, job(slide("Par la foi, Abraham obéit.", "Hébreux 11:8"))).unwrap();
        for t in [0.0, 0.3, 0.5, 0.8, 1.0] {
            let cpu = renderer.render(&mut fonts, &frame(&a.list, &b.list, &animation, t as f32), W, H).unwrap();
            let image = gpu(&a, &b, animation, t);
            let (mean, far) = compare(&image, &cpu);
            if std::env::var_os("SCENE_DEBUG").is_some() {
                let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
                image.save(dir.join(format!("scene-gpu-{kind:?}-{t}.png"))).unwrap();
                cpu.save_png(dir.join(format!("scene-cpu-{kind:?}-{t}.png"))).unwrap();
            }
            eprintln!("{kind:?} t={t} : écart moyen {mean:.2}, pixels éloignés {:.3} %", far * 100.0);
            assert!(
                mean < 3.0 && far < 0.01,
                "{kind:?} à t={t} : écart moyen {mean:.2}, {:.2} % de pixels éloignés",
                far * 100.0
            );
        }
    }
}
