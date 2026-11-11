//! Les trois écrans de l'église avec le profil des réglages de la 2.x (lus sans rien écrire), en
//! une planche PNG : `cargo run -p po-render --example eglise -- <settings.json> <sortie.png>`.

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let (Some(settings), Some(out)) = (args.first(), args.get(1)) else {
        eprintln!("usage : eglise <settings.json> <sortie.png>");
        std::process::exit(2);
    };
    let text = std::fs::read_to_string(settings).unwrap_or_default();
    let value: serde_json::Value = serde_json::from_str(&text).unwrap_or_default();
    let profile = po_design::church::ChurchProfile::from_settings(value.get("church"));
    let mut fonts = po_layout::Fonts::from_dirs(&[po_layout::bundled_fonts_dir()]);
    let mut renderer = po_render::Renderer::new();
    let (w, h, gap) = (960u32, 540u32, 24u32);
    let Some(mut sheet) = tiny_skia::Pixmap::new(w * 3 + gap * 4, h + gap * 2) else { return };
    sheet.fill(tiny_skia::Color::from_rgba8(11, 18, 23, 255));
    let lists = [
        po_layout::church::layout_welcome(&mut fonts, &profile, 1920.0, 1080.0),
        po_layout::church::layout_speaker(&mut fonts, &profile, 1920.0, 1080.0),
        po_layout::church::layout_socials(&mut fonts, &profile, 1920.0, 1080.0),
    ];
    for (i, list) in lists.iter().enumerate() {
        let Ok(tile) = renderer.render(&mut fonts, list, w, h) else { continue };
        let x = (gap + i as u32 * (w + gap)) as i32;
        sheet.draw_pixmap(
            x,
            gap as i32,
            tile.as_ref(),
            &tiny_skia::PixmapPaint::default(),
            tiny_skia::Transform::identity(),
            None,
        );
    }
    if let Ok(png) = po_render::encode_png(&sheet) {
        let _ = std::fs::write(out, png);
        println!("planche : {out}");
    }
}
