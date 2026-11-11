//! Les huit modèles d'images de citation avec le profil des réglages de la 2.x (lus sans rien
//! écrire), en une planche PNG : `cargo run -p po-render --example citations -- <settings.json> <sortie.png>`.

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let (Some(settings), Some(out)) = (args.first(), args.get(1)) else {
        eprintln!("usage : citations <settings.json> <sortie.png>");
        std::process::exit(2);
    };
    let text = std::fs::read_to_string(settings).unwrap_or_default();
    let value: serde_json::Value = serde_json::from_str(&text).unwrap_or_default();
    let profile = po_design::church::ChurchProfile::from_settings(value.get("church"));
    let mut fonts = po_layout::Fonts::from_dirs(&[po_layout::bundled_fonts_dir()]);
    let mut renderer = po_render::Renderer::new();
    let quote = "Car Dieu a tant aimé le monde qu'il a donné son Fils unique, afin que quiconque croit en lui ne périsse point, mais qu'il ait la vie éternelle.";
    let (side, gap) = (480u32, 20u32);
    let Some(mut sheet) = tiny_skia::Pixmap::new(side * 4 + gap * 5, side * 2 + gap * 3) else { return };
    sheet.fill(tiny_skia::Color::from_rgba8(11, 18, 23, 255));
    for (i, (style, _)) in po_design::church::QUOTE_STYLES.iter().enumerate() {
        let list = po_layout::church::layout_quote(
            &mut fonts,
            &profile,
            quote,
            "Jean 3:16\nLouis Segond 1910",
            style,
            1080.0,
            1080.0,
        );
        let Ok(tile) = renderer.render(&mut fonts, &list, side, side) else { continue };
        let (col, row) = (i as u32 % 4, i as u32 / 4);
        sheet.draw_pixmap(
            (gap + col * (side + gap)) as i32,
            (gap + row * (side + gap)) as i32,
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
