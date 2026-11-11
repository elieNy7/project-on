//! Les écrans de l'église (`church_graphics.py` de la 2.8) : l'**accueil** (titre, logo, nom,
//! devise, horaires, orateur du jour, réseaux, QR code), l'**orateur du jour** (photo, titre, nom,
//! message) et les **réseaux sociaux** (chaque compte en grand, QR code). La 2.8 les dessinait en
//! images avec PIL ; ici ce sont des listes d'affichage, dessinées par le même moteur que les slides.

use po_design::Rgba;
use po_design::church::{ChurchBackground, ChurchProfile, SocialPlatform, display_handle, link_url, platform};

use crate::display::{Anchor, DisplayList, Item, Stop, TextLine};
use crate::fit::{FontSpec, wrap_lines};
use crate::fonts::Fonts;

/// Le fond : dégradé (la couleur de l'église vers 55 % d'elle-même), uni, ou image assombrie.
fn background(profile: &ChurchProfile, w: f32, h: f32) -> (Rgba, Vec<Item>) {
    let top = profile.primary_color;
    if profile.background == ChurchBackground::Image
        && let Some((iw, ih)) = crate::backdrop::image_size_of(&profile.background_image)
    {
        let scale = (w / iw).max(h / ih);
        let (rw, rh) = (iw * scale, ih * scale);
        let image = Item::Image {
            path: profile.background_image.clone(),
            x: (w - rw) / 2.0,
            y: (h - rh) / 2.0,
            w: rw,
            h: rh,
            opacity: 1.0,
        };
        let veil = Rgba::new(0, 0, 0, (255.0 * f32::from(profile.background_dim) / 100.0) as u8);
        return (Rgba::BLACK, vec![image, Item::Rect { x: 0.0, y: 0.0, w, h, radius: 0.0, color: veil }]);
    }
    if profile.background == ChurchBackground::Solid {
        return (top, Vec::new());
    }
    let dark = |c: u8| (f32::from(c) * 0.55) as u8;
    let bottom = Rgba::rgb(dark(top.0[0]), dark(top.0[1]), dark(top.0[2]));
    let gradient = Item::LinearGradient {
        x: 0.0,
        y: 0.0,
        w,
        h,
        from: [0.0, 0.0],
        to: [0.0, h],
        stops: vec![Stop { at: 0.0, color: top }, Stop { at: 1.0, color: bottom }],
    };
    (top, vec![gradient])
}

/// Ce que l'on dessine : la police de l'église, et les éléments posés de haut en bas.
struct Canvas<'a> {
    fonts: &'a mut Fonts,
    family: String,
    items: Vec<Item>,
}

impl Canvas<'_> {
    /// Une ligne dont le haut des lettres est à `top` (l'ancre « ma » de PIL).
    fn line(&mut self, text: &str, x: f32, top: f32, size: f32, bold: bool, color: Rgba, anchor: Anchor) -> f32 {
        let weight = if bold { 700 } else { 400 };
        let m = self.fonts.qt_metrics(&self.family, weight, size);
        let width = self.fonts.qt_advance(text, &self.family, weight, size, 0.0);
        self.items.push(Item::Text(TextLine {
            text: text.to_string(),
            x,
            baseline: top + m.ascent as f32,
            anchor,
            size,
            family: self.family.clone(),
            weight,
            color,
            width,
            letter_spacing: 0.0,
            advance_scale: 1.0,
            shadow: None,
            outline: None,
        }));
        width
    }

    fn wrap(&mut self, text: &str, size: f32, bold: bool, width: f32) -> Vec<String> {
        let spec = FontSpec { family: &self.family, weight: if bold { 700 } else { 400 }, letter_spacing: 0.0 };
        wrap_lines(self.fonts, text, spec, size, width)
    }

    /// La plus grande taille (de `start` à `minimum`) où le texte tient dans `box_w` × `box_h`
    /// (`_fit_text`).
    fn fit(&mut self, text: &str, box_w: f32, box_h: f32, start: f32, minimum: f32, factor: f32) -> (f32, Vec<String>) {
        let mut size = start.round();
        loop {
            let lines = self.wrap(text, size, true, box_w);
            if lines.len() as f32 * size * factor <= box_h || size <= minimum {
                return (size, lines);
            }
            size -= 2.0;
        }
    }

    /// Le logo, centré sur `cx`, haut de `max_h` au plus ; rend sa hauteur.
    fn logo(&mut self, path: &str, cx: f32, top: f32, max_h: f32) -> f32 {
        let Some((iw, ih)) = crate::backdrop::image_size_of(path) else { return 0.0 };
        let scale = (max_h / ih).min(max_h * 2.5 / iw);
        let (w, h) = (iw * scale, ih * scale);
        self.items.push(Item::Image { path: path.to_string(), x: cx - w / 2.0, y: top, w, h, opacity: 1.0 });
        h
    }

    /// Une pastille de réseau : un disque à sa couleur et son initiale.
    fn badge(&mut self, x: f32, y: f32, p: &SocialPlatform, d: f32) {
        self.items.push(Item::Rect { x, y, w: d, h: d, radius: d / 2.0, color: po_design::parse_color(p.color) });
        let letter = match p.key {
            "youtube" => "▶",
            "website" => "W",
            "email" => "@",
            "phone" => "+",
            _ => &p.label[..1],
        };
        let size = (d * 0.5).round();
        let m = self.fonts.qt_metrics(&self.family, 700, size);
        let top = y + (d - m.height as f32) / 2.0;
        self.line(letter, x + d / 2.0, top, size, true, Rgba::WHITE, Anchor::Middle);
    }

    /// Un QR code sur fond blanc, coin en (`x`, `y`), côté `side`.
    fn qr(&mut self, url: &str, x: f32, y: f32, side: f32) -> bool {
        let Ok(code) = qrcode::QrCode::with_error_correction_level(url.as_bytes(), qrcode::EcLevel::M) else {
            return false;
        };
        let width = code.width();
        let quiet = 2.0;
        let module = side / (width as f32 + 2.0 * quiet);
        self.items.push(Item::Rect { x, y, w: side, h: side, radius: module * 1.5, color: Rgba::WHITE });
        for (i, dark) in code.to_colors().into_iter().enumerate() {
            if dark == qrcode::Color::Dark {
                let (cx, cy) = ((i % width) as f32 + quiet, (i / width) as f32 + quiet);
                self.items.push(Item::Rect {
                    x: x + cx * module,
                    y: y + cy * module,
                    w: module + 0.5,
                    h: module + 0.5,
                    radius: 0.0,
                    color: Rgba::BLACK,
                });
            }
        }
        true
    }

    /// La rangée « pastille + compte », centrée sur `cx` (`_socials_strip`) ; rend sa hauteur.
    fn socials_strip(&mut self, profile: &ChurchProfile, cx: f32, y: f32, max_w: f32, unit: f32, limit: usize) -> f32 {
        let items: Vec<_> = profile.social_items().into_iter().take(limit).collect();
        if items.is_empty() {
            return 0.0;
        }
        let size = (28.0 * unit).round();
        let d = (size * 1.25).round();
        let gap = (34.0 * unit).round();
        let pieces: Vec<(&SocialPlatform, String, f32)> = items
            .iter()
            .map(|(p, v)| {
                let label = display_handle(p.key, v);
                let w = d + 10.0 * unit + self.fonts.qt_advance(&label, &self.family, 400, size, 0.0);
                (*p, label, w)
            })
            .collect();
        let mut rows: Vec<Vec<(&SocialPlatform, String, f32)>> = vec![Vec::new()];
        let mut row_w = 0.0;
        for piece in pieces {
            let extra = piece.2 + if rows.last().is_some_and(|r| !r.is_empty()) { gap } else { 0.0 };
            if rows.last().is_some_and(|r| !r.is_empty()) && row_w + extra > max_w {
                rows.push(Vec::new());
                row_w = 0.0;
            }
            row_w += piece.2 + if rows.last().is_some_and(|r| !r.is_empty()) { gap } else { 0.0 };
            if let Some(row) = rows.last_mut() {
                row.push(piece);
            }
        }
        let line_h = (d * 1.45).round();
        let color = profile.text_color.with_alpha(235.0 / 255.0);
        for (index, row) in rows.iter().enumerate() {
            let total: f32 = row.iter().map(|p| p.2).sum::<f32>() + gap * (row.len() as f32 - 1.0);
            let mut x = cx - total / 2.0;
            let top = y + index as f32 * line_h;
            for (p, label, w) in row {
                self.badge(x, top, p, d);
                let m = self.fonts.qt_metrics(&self.family, 400, size);
                self.line(
                    label,
                    x + d + 10.0 * unit,
                    top + (d - m.height as f32) / 2.0,
                    size,
                    false,
                    color,
                    Anchor::Start,
                );
                x += w + gap;
            }
        }
        line_h * rows.len() as f32
    }

    /// La photo (sans fond) en bas à gauche ou à droite, avec le nom dessous (`_pastor_corner`) ;
    /// rend sa largeur (0 sans photo).
    #[allow(clippy::too_many_arguments)]
    fn portrait(
        &mut self,
        photo: &str,
        caption: &str,
        w: f32,
        h: f32,
        max_w: f32,
        max_h: f32,
        margin: f32,
        right: bool,
        profile: &ChurchProfile,
        unit: f32,
    ) -> f32 {
        let Some((iw, ih)) = crate::backdrop::image_size_of(photo) else { return 0.0 };
        let scale = (max_w / iw).min(max_h / ih);
        let (pw, ph) = (iw * scale, ih * scale);
        let x = if right { w - margin - pw } else { margin };
        self.items.push(Item::Image { path: photo.to_string(), x, y: h - ph, w: pw, h: ph, opacity: 1.0 });
        if !caption.is_empty() {
            let size = (28.0 * unit).round();
            let band_h = size * 1.8;
            self.items.push(Item::Rect {
                x,
                y: h - band_h,
                w: pw,
                h: band_h,
                radius: 0.0,
                color: Rgba::new(0, 0, 0, 140),
            });
            self.line(caption, x + pw / 2.0, h - band_h + size * 0.35, size, true, profile.text_color, Anchor::Middle);
        }
        pw
    }
}

fn finish(width: f32, height: f32, background: (Rgba, Vec<Item>), items: Vec<Item>) -> DisplayList {
    let mut list = DisplayList::blank(width, height, background.0);
    list.backdrop = background.1;
    list.items = items;
    list
}

/// L'écran d'accueil (`render_welcome`). Le bas (réseaux, QR code) est posé d'abord ; le haut
/// (titre, logo, nom, devise, horaires, orateur) se resserre s'il le faut pour ne jamais le toucher.
pub fn layout_welcome(fonts: &mut Fonts, profile: &ChurchProfile, width: f32, height: f32) -> DisplayList {
    let family = fonts.resolve_family(&profile.font_family);
    let mut c = Canvas { fonts, family, items: Vec::new() };
    let unit = width.min(height) / 1080.0;
    let accent = profile.accent_color;
    let text = profile.text_color;
    // La photo du pasteur en bas à gauche : le contenu se décale vers la droite.
    let photo_w = c.portrait(
        &profile.pastor_photo,
        &profile.pastor_label(),
        width,
        height,
        width * 0.30,
        height * 0.72,
        40.0 * unit,
        false,
        profile,
        unit,
    );
    let left_reserved = if photo_w > 0.0 { 40.0 * unit + photo_w } else { 0.0 };
    let cx = if photo_w > 0.0 { (left_reserved + width) / 2.0 } else { width / 2.0 };
    let text_w = if photo_w > 0.0 { (width - left_reserved) * 0.86 } else { width * 0.8 };
    let socials = profile.show_socials_welcome && !profile.socials.is_empty();

    // Le bas : les réseaux (centrés), le QR code (à droite).
    let bottom = height - 60.0 * unit;
    let mut right_reserved = 0.0;
    let mut limit = bottom;
    if let Some(p) = platform(&profile.qr_target) {
        let side = 170.0 * unit;
        let (qx, qy) = (width - side - 60.0 * unit, bottom - side - 30.0 * unit);
        if c.qr(&link_url(p.key, profile.social(p.key).unwrap_or("")), qx, qy, side) {
            c.line(
                p.label,
                qx + side / 2.0,
                qy + side + 10.0 * unit,
                (22.0 * unit).round(),
                true,
                text,
                Anchor::Middle,
            );
            right_reserved = side + 90.0 * unit;
        }
    }
    if socials {
        let mut free_left = left_reserved + 40.0 * unit;
        let free_right = width - right_reserved - 40.0 * unit;
        if photo_w == 0.0 && right_reserved > 0.0 {
            free_left = right_reserved;
        }
        let rows = if profile.socials.len() > 3 { 2.0 } else { 1.0 };
        let d = (28.0 * unit).round() * 1.25;
        let line_h = (d * 1.45).round();
        let top = bottom - line_h * rows - 10.0 * unit;
        c.socials_strip(profile, (free_left + free_right) / 2.0, top, (free_right - free_left).max(400.0), unit, 6);
        limit = top - 24.0 * unit;
    } else if !profile.contact.is_empty() {
        let top = bottom - 30.0 * unit;
        c.line(&profile.contact, cx, top, (30.0 * unit).round(), false, accent, Anchor::Middle);
        limit = top - 24.0 * unit;
    }

    // Le haut, à l'échelle `k` : on la réduit jusqu'à ce qu'il tienne au-dessus du bas.
    let fixed = c.items.len();
    let mut k = 1.0f32;
    loop {
        c.items.truncate(fixed);
        let u = unit * k;
        let mut y = height * if !profile.service_times.is_empty() || socials { 0.10 } else { 0.16 } * k.max(0.4);
        if !profile.welcome_title.is_empty() {
            c.line(&profile.welcome_title.to_uppercase(), cx, y, (34.0 * u).round(), true, accent, Anchor::Middle);
            y += 64.0 * u;
        }
        let logo_h = c.logo(&profile.logo, cx, y, 220.0 * u);
        y += if logo_h > 0.0 { logo_h + 40.0 * u } else { 60.0 * u };
        let name = if profile.name.is_empty() { "Bienvenue" } else { &profile.name };
        let (size, lines) = c.fit(name, text_w, 240.0 * u, 104.0 * u, 46.0 * u, 1.15);
        for line in &lines {
            c.line(line, cx, y, size, true, text, Anchor::Middle);
            y += size * 1.15;
        }
        y += 16.0 * u;
        let thick = (5.0 * u).max(2.0);
        c.items.push(Item::Rect { x: cx - 90.0 * u, y, w: 180.0 * u, h: thick, radius: thick / 2.0, color: accent });
        y += 36.0 * u;
        if !profile.motto.is_empty() {
            let size = (42.0 * u).round();
            for line in c.wrap(&profile.motto, size, false, text_w * 0.88) {
                c.line(&line, cx, y, size, false, text.with_alpha(225.0 / 255.0), Anchor::Middle);
                y += 56.0 * u;
            }
        }
        let times = profile.times();
        if !times.is_empty() {
            y += 18.0 * u;
            for line in times {
                c.line(line, cx, y, (32.0 * u).round(), true, accent, Anchor::Middle);
                y += 46.0 * u;
            }
        }
        if profile.has_guest_speaker() || !profile.speaker_message.is_empty() {
            y += 18.0 * u;
            c.line(
                &format!("Orateur du jour : {}", profile.speaker_label()),
                cx,
                y,
                (32.0 * u).round(),
                false,
                text,
                Anchor::Middle,
            );
            y += 44.0 * u;
            if !profile.speaker_message.is_empty() {
                c.line(
                    &format!("« {} »", profile.speaker_message),
                    cx,
                    y,
                    (30.0 * u).round(),
                    false,
                    text.with_alpha(210.0 / 255.0),
                    Anchor::Middle,
                );
                y += 44.0 * u;
            }
        }
        if y <= limit || k <= 0.4 {
            // Resserré, le haut se centre dans la place libre (au plus d'un dixième de l'écran).
            if k < 1.0 {
                let shift = ((limit - y) / 2.0).clamp(0.0, height * 0.1);
                for item in &mut c.items[fixed..] {
                    match item {
                        Item::Text(line) => line.baseline += shift,
                        Item::Rect { y, .. } | Item::Image { y, .. } => *y += shift,
                        _ => {}
                    }
                }
            }
            break;
        }
        k -= 0.05;
    }
    finish(width, height, background(profile, width, height), c.items)
}

/// L'écran de l'orateur du jour (`render_speaker`) : sans invité, c'est le pasteur ; avec un
/// invité, le pasteur reste présent dans le coin.
pub fn layout_speaker(fonts: &mut Fonts, profile: &ChurchProfile, width: f32, height: f32) -> DisplayList {
    let family = fonts.resolve_family(&profile.font_family);
    let mut c = Canvas { fonts, family, items: Vec::new() };
    let unit = width.min(height) / 1080.0;
    let (accent, text) = (profile.accent_color, profile.text_color);
    let (title, name, photo) = profile.speaker_info();
    let (left, text_w) = match crate::backdrop::image_size_of(photo) {
        Some((iw, ih)) => {
            let scale = (width * 0.46 / iw).min(height * 0.94 / ih);
            let (pw, ph) = (iw * scale, ih * scale);
            c.items.push(Item::Image {
                path: photo.to_string(),
                x: width * 0.27 - pw / 2.0 + 20.0 * unit,
                y: height - ph,
                w: pw,
                h: ph,
                opacity: 1.0,
            });
            (width * 0.52, width * 0.42)
        }
        None => (width * 0.12, width * 0.76),
    };
    if profile.has_guest_speaker() {
        c.portrait(
            &profile.pastor_photo,
            &profile.pastor_label(),
            width,
            height,
            width * 0.16,
            height * 0.34,
            50.0 * unit,
            true,
            profile,
            unit * 0.75,
        );
    }
    let mut y = height * 0.28;
    c.line("ORATEUR DU JOUR", left, y, (34.0 * unit).round(), true, accent, Anchor::Start);
    y += 62.0 * unit;
    if !title.is_empty() {
        c.line(title, left, y, (44.0 * unit).round(), false, text.with_alpha(220.0 / 255.0), Anchor::Start);
        y += 62.0 * unit;
    }
    let shown = if name.is_empty() { "Orateur" } else { name };
    let (size, lines) = c.fit(shown, text_w, 280.0 * unit, 96.0 * unit, 44.0 * unit, 1.1);
    for line in &lines {
        c.line(line, left, y, size, true, text, Anchor::Start);
        y += size * 1.1;
    }
    y += 20.0 * unit;
    let thick = (6.0 * unit).max(2.0);
    c.items.push(Item::Rect { x: left, y, w: 140.0 * unit, h: thick, radius: thick / 2.0, color: accent });
    y += 40.0 * unit;
    if !profile.speaker_message.is_empty() {
        let size = (40.0 * unit).round();
        for line in c.wrap(&profile.speaker_message, size, false, text_w).into_iter().take(3) {
            c.line(&line, left, y, size, false, text, Anchor::Start);
            y += 54.0 * unit;
        }
    }
    if !profile.name.is_empty() {
        c.line(
            &profile.name,
            left,
            height - 110.0 * unit,
            (30.0 * unit).round(),
            false,
            text.with_alpha(200.0 / 255.0),
            Anchor::Start,
        );
    }
    finish(width, height, background(profile, width, height), c.items)
}

/// L'écran « Réseaux sociaux » de fin de culte (`render_socials`).
pub fn layout_socials(fonts: &mut Fonts, profile: &ChurchProfile, width: f32, height: f32) -> DisplayList {
    let family = fonts.resolve_family(&profile.font_family);
    let mut c = Canvas { fonts, family, items: Vec::new() };
    let unit = width.min(height) / 1080.0;
    let (accent, text) = (profile.accent_color, profile.text_color);
    let margin = 110.0 * unit;
    c.line("Restons connectés", width / 2.0, margin, (76.0 * unit).round(), true, text, Anchor::Middle);
    if !profile.name.is_empty() {
        c.line(&profile.name, width / 2.0, margin + 100.0 * unit, (34.0 * unit).round(), false, accent, Anchor::Middle);
    }
    let items: Vec<_> = profile.social_items().into_iter().take(7).collect();
    let qr = platform(&profile.qr_target);
    let photo_w = c.portrait(
        &profile.pastor_photo,
        &profile.pastor_label(),
        width,
        height,
        width * 0.26,
        height * 0.66,
        40.0 * unit,
        false,
        profile,
        unit,
    );
    let mut list_left = if qr.is_some() { margin } else { width * 0.26 };
    if photo_w > 0.0 {
        list_left = list_left.max(40.0 * unit + photo_w + 50.0 * unit);
    }
    let list_top = margin + 210.0 * unit;
    let available = height - list_top - margin;
    let row_h = if items.is_empty() { 0.0 } else { (112.0 * unit).min(available / items.len() as f32) };
    let d = (row_h * 0.62).round();
    for (index, (p, value)) in items.iter().enumerate() {
        let top = list_top + index as f32 * row_h;
        c.badge(list_left, top, p, d);
        let tx = list_left + d + 26.0 * unit;
        c.line(
            p.label,
            tx,
            top - 4.0 * unit,
            (row_h * 0.26).round(),
            false,
            text.with_alpha(170.0 / 255.0),
            Anchor::Start,
        );
        c.line(
            &display_handle(p.key, value),
            tx,
            top + row_h * 0.26,
            (row_h * 0.36).round(),
            true,
            text,
            Anchor::Start,
        );
    }
    if items.is_empty() {
        c.line(
            "Ajoutez vos réseaux dans Réglages → Profil de l'église",
            width / 2.0,
            height / 2.0,
            (34.0 * unit).round(),
            false,
            text.with_alpha(200.0 / 255.0),
            Anchor::Middle,
        );
    }
    if let Some(p) = qr {
        let side = 380.0 * unit;
        let qx = width - margin - side;
        let qy = list_top + ((available - side) / 2.0 - 20.0 * unit).max(0.0);
        if c.qr(&link_url(p.key, profile.social(p.key).unwrap_or("")), qx, qy, side) {
            c.line(
                &format!("Scannez · {}", p.label),
                qx + side / 2.0,
                qy + side + 18.0 * unit,
                (30.0 * unit).round(),
                true,
                accent,
                Anchor::Middle,
            );
        }
    }
    if photo_w == 0.0 {
        c.logo(&profile.logo, width / 2.0, height - 120.0 * unit, 80.0 * unit);
    }
    finish(width, height, background(profile, width, height), c.items)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn fonts() -> Fonts {
        Fonts::from_dirs(&[crate::bundled_fonts_dir()])
    }

    fn profile() -> ChurchProfile {
        let logo = crate::bundled_backgrounds_dir().join("bg-indigo_16x9.png");
        ChurchProfile::from_settings(Some(&json!({
            "name": "OUVRIERS DE LA ONZIÈME HEURE", "motto": "Tenez-vous tranquilles et sachez que je suis Dieu",
            "logo": logo.to_string_lossy(), "service_times": "Mercredi : 16H00 - 18H20\nDimanche : 9H30",
            "socials": {"facebook": "@Eglise", "youtube": "@Eglise", "whatsapp": "+243812436993", "phone": "+243812436993"},
            "qr_target": "youtube", "pastor_title": "Révérend", "pastor_name": "Joseph Nyembo"
        })))
    }

    fn texts(list: &DisplayList) -> String {
        list.text_lines().map(|l| l.text.clone()).collect::<Vec<_>>().join(" | ")
    }

    #[test]
    fn the_welcome_screen_shows_the_church() {
        let mut fonts = fonts();
        let p = profile();
        let list = layout_welcome(&mut fonts, &p, 1920.0, 1080.0);
        let all = texts(&list);
        for wanted in ["BIENVENUE", "OUVRIERS", "Tenez-vous", "Mercredi : 16H00 - 18H20", "Eglise", "YouTube"] {
            assert!(all.contains(wanted), "{wanted} absent : {all}");
        }
        assert!(list.items.iter().any(|i| matches!(i, Item::Image { .. })), "le logo");
        let qr_modules =
            list.items.iter().filter(|i| matches!(i, Item::Rect { color, .. } if *color == Rgba::BLACK)).count();
        assert!(qr_modules > 100, "le QR code : {qr_modules} modules");
        assert!(matches!(list.backdrop[0], Item::LinearGradient { .. }), "le dégradé de l'église");
        for l in list.text_lines() {
            assert!(l.baseline > 0.0 && l.baseline < 1080.0, "{} hors de l'écran", l.text);
        }
    }

    #[test]
    fn a_full_welcome_screen_never_overlaps_the_networks() {
        let mut fonts = fonts();
        let mut p = profile();
        p.name = "OUVRIERS DE LA ONZIÈME HEURE, ASSEMBLÉE DE LA FOI".into();
        p.service_times = "Mercredi : 16H00 - 18H20
Vendredi : 16H00 - 18H20
Dimanche : 09H00 - 12H30
Samedi : 15H00"
            .into();
        p.speaker_name = "Frère Paul".into();
        p.speaker_message = "La foi qui vainc le monde".into();
        for (k, v) in [("instagram", "@Eglise"), ("tiktok", "@Eglise"), ("x", "@Eglise")] {
            p.socials.push((k.into(), v.into()));
        }
        let list = layout_welcome(&mut fonts, &p, 1920.0, 1080.0);
        // Le haut des pastilles des réseaux : le plus haut des disques colorés de la rangée du bas.
        let strip_top = list
            .items
            .iter()
            .filter_map(|i| match i {
                Item::Rect { y, w, h, radius, .. }
                    if (*w - *h).abs() < 0.5 && (*radius - *w / 2.0).abs() < 0.5 && *y > 700.0 =>
                {
                    Some(*y)
                }
                _ => None,
            })
            .fold(f32::MAX, f32::min);
        assert!(strip_top < 1080.0, "les réseaux sont là");
        let times = list
            .text_lines()
            .filter(|l| l.text.contains("H00") || l.text.contains("Frère") || l.text.contains("vainc"));
        for l in times {
            let m = fonts.qt_metrics(&l.family, l.weight, l.size);
            assert!(
                l.baseline + m.descent as f32 <= strip_top,
                "« {} » touche les réseaux ({} > {strip_top})",
                l.text,
                l.baseline
            );
        }
    }

    #[test]
    fn the_speaker_and_socials_screens() {
        let mut fonts = fonts();
        let mut p = profile();
        let pastor = texts(&layout_speaker(&mut fonts, &p, 1920.0, 1080.0));
        assert!(pastor.contains("ORATEUR DU JOUR") && pastor.contains("Révérend") && pastor.contains("Joseph Nyembo"));
        p.speaker_name = "Frère Paul".into();
        p.speaker_message = "La foi qui vainc".into();
        let guest = texts(&layout_speaker(&mut fonts, &p, 1920.0, 1080.0));
        assert!(guest.contains("Frère Paul") && guest.contains("La foi qui vainc") && !guest.contains("Joseph Nyembo"));
        let socials = texts(&layout_socials(&mut fonts, &p, 1920.0, 1080.0));
        for wanted in ["Restons connectés", "Facebook", "WhatsApp", "+243812436993", "Scannez · YouTube"] {
            assert!(socials.contains(wanted), "{wanted} absent : {socials}");
        }
        let empty = texts(&layout_socials(&mut fonts, &ChurchProfile::default(), 1920.0, 1080.0));
        assert!(empty.contains("Ajoutez vos réseaux"));
    }
}
