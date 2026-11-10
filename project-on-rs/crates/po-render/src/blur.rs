//! Le flou des ombres, des halos et de la transition « flou » : trois flous en boîte successifs,
//! proches d'un flou gaussien, sur une zone de l'image seulement.

use tiny_skia::{Pixmap, PremultipliedColorU8, Rect};

/// Un flou en boîte horizontal puis vertical, de rayon `r`, sur la zone `[x0, x1) × [y0, y1)`.
fn box_pass(data: &mut [PremultipliedColorU8], width: usize, area: (usize, usize, usize, usize), r: usize) {
    let (x0, y0, x1, y1) = area;
    let mut line = Vec::new();
    // Horizontal.
    for y in y0..y1 {
        line.clear();
        line.extend((x0..x1).map(|x| data[y * width + x]));
        blur_line(&line, r, |i, px| data[y * width + x0 + i] = px);
    }
    // Vertical.
    for x in x0..x1 {
        line.clear();
        line.extend((y0..y1).map(|y| data[y * width + x]));
        blur_line(&line, r, |i, px| data[(y0 + i) * width + x] = px);
    }
}

/// Une moyenne glissante sur `2r + 1` pixels (les bords comptent comme transparents).
fn blur_line(src: &[PremultipliedColorU8], r: usize, mut put: impl FnMut(usize, PremultipliedColorU8)) {
    let n = src.len();
    let window = (2 * r + 1) as u32;
    let mut sum = [0u32; 4];
    let add = |sum: &mut [u32; 4], p: PremultipliedColorU8, sign: i32| {
        let v = [p.red(), p.green(), p.blue(), p.alpha()];
        for (s, c) in sum.iter_mut().zip(v) {
            *s = (*s as i32 + sign * i32::from(c)) as u32;
        }
    };
    for p in src.iter().take(r.min(n)) {
        add(&mut sum, *p, 1);
    }
    for i in 0..n {
        if i + r < n {
            add(&mut sum, src[i + r], 1);
        }
        if i > r {
            add(&mut sum, src[i - r - 1], -1);
        }
        let avg = |s: u32| ((s + window / 2) / window).min(255) as u8;
        let alpha = avg(sum[3]);
        let px = PremultipliedColorU8::from_rgba(
            avg(sum[0]).min(alpha),
            avg(sum[1]).min(alpha),
            avg(sum[2]).min(alpha),
            alpha,
        )
        .unwrap_or(PremultipliedColorU8::TRANSPARENT);
        put(i, px);
    }
}

/// Le rayon de chacune des trois boîtes : ensemble, un gaussien de σ ≈ rayon / 2.
fn box_radius(radius: f32) -> usize {
    ((radius / 2.0).round() as usize).max(1)
}

/// La distance, en pixels, jusqu'où le flou de rayon `radius` étale une forme.
pub fn reach(radius: f32) -> f32 {
    if radius < 0.5 { 0.0 } else { (3 * box_radius(radius) + 2) as f32 }
}

/// Floute une image d'opacité (un octet par pixel, `width` × `height`, hors de l'image : transparent)
/// avec le même flou que [`blur_region`]. C'est le chemin des ombres et des halos : une seule couleur,
/// donc une seule valeur à flouter au lieu de quatre, et les deux sens parcourus ligne à ligne (le
/// sens vertical garde une somme par colonne au lieu de sauter d'une ligne à l'autre).
pub fn blur_alpha(alpha: &mut [u8], width: usize, height: usize, radius: f32) {
    if radius < 0.5 || width == 0 || height == 0 || alpha.len() < width * height {
        return;
    }
    let r = box_radius(radius);
    let window = 2 * r + 1;
    // La moyenne arrondie, exacte, sans division : somme → valeur.
    let average: Vec<u8> = (0..=255 * window).map(|s| ((s + window / 2) / window).min(255) as u8).collect();
    let mut tmp = vec![0u8; width * height];
    let mut sums = vec![0usize; width];
    for _ in 0..3 {
        // Horizontal : alpha → tmp.
        for (src, dst) in alpha.chunks_exact(width).zip(tmp.chunks_exact_mut(width)) {
            let mut sum: usize = src.iter().take(r.min(width)).map(|&v| usize::from(v)).sum();
            for i in 0..width {
                if i + r < width {
                    sum += usize::from(src[i + r]);
                }
                if i > r {
                    sum -= usize::from(src[i - r - 1]);
                }
                dst[i] = average[sum];
            }
        }
        // Vertical : tmp → alpha, une somme par colonne.
        sums.iter_mut().for_each(|s| *s = 0);
        for row in tmp.chunks_exact(width).take(r.min(height)) {
            for (s, &v) in sums.iter_mut().zip(row) {
                *s += usize::from(v);
            }
        }
        for y in 0..height {
            if y + r < height {
                let row = &tmp[(y + r) * width..(y + r + 1) * width];
                for (s, &v) in sums.iter_mut().zip(row) {
                    *s += usize::from(v);
                }
            }
            if y > r {
                let row = &tmp[(y - r - 1) * width..(y - r) * width];
                for (s, &v) in sums.iter_mut().zip(row) {
                    *s -= usize::from(v);
                }
            }
            for (out, &s) in alpha[y * width..(y + 1) * width].iter_mut().zip(&sums) {
                *out = average[s];
            }
        }
    }
}

/// Floute la zone `bounds` (agrandie du flou) avec un rayon proche de `radius` pixels.
pub fn blur_region(pixmap: &mut Pixmap, bounds: Rect, radius: f32) {
    if radius < 0.5 {
        return;
    }
    let r = box_radius(radius);
    let margin = reach(radius);
    let (w, h) = (pixmap.width() as usize, pixmap.height() as usize);
    let x0 = (bounds.left() - margin).floor().max(0.0) as usize;
    let y0 = (bounds.top() - margin).floor().max(0.0) as usize;
    let x1 = ((bounds.right() + margin).ceil().max(0.0) as usize).min(w);
    let y1 = ((bounds.bottom() + margin).ceil().max(0.0) as usize).min(h);
    if x0 >= x1 || y0 >= y1 {
        return;
    }
    let data = pixmap.pixels_mut();
    for _ in 0..3 {
        box_pass(data, w, (x0, y0, x1, y1), r);
    }
}
