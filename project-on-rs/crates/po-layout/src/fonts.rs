//! Les polices : chargement des fichiers de Project-On, mise en forme d'une ligne (cosmic-text), et
//! les mesures « à la Qt » qui permettent de couper les lignes comme la 2.8.
//!
//! La 2.8 mesure avec `QFontMetrics` : des pixels entiers. La hauteur de ligne vient des métriques
//! de la police ramenées en virgule fixe 26.6 puis arrondies, et la largeur d'une ligne est la somme
//! des avances de ses lettres, chacune arrondie au pixel. Les mêmes règles ici donnent les mêmes
//! tailles et les mêmes coupures (mesuré : voir le rapport de la phase 2).

use std::collections::HashMap;
use std::path::Path;

use cosmic_text::{Attrs, Buffer, CacheKeyFlags, Family, FontSystem, Metrics, Shaping, Weight, Wrap, fontdb};

/// Les mesures verticales d'une police, en fraction de sa taille (em).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct VerticalMetrics {
    pub ascent: f32,
    pub descent: f32,
    pub leading: f32,
}

impl VerticalMetrics {
    /// L'interligne naturel (ascendante + descendante + interligne de la police).
    pub fn line_spacing(&self) -> f32 {
        self.ascent + self.descent + self.leading
    }
}

/// Les mesures entières de `QFontMetrics` à une taille donnée.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct QtMetrics {
    pub ascent: i32,
    pub descent: i32,
    /// `ascent + descent`.
    pub height: i32,
    pub line_spacing: i32,
}

/// Les métriques verticales de la police, en unités de dessin : celles que Windows (DirectWrite)
/// donne à Qt.
#[derive(Debug, Clone, Copy, PartialEq)]
struct DesignVertical {
    ascent: f32,
    descent: f32,
    gap: f32,
    units_per_em: f32,
}

/// Le système de polices de Project-On.
pub struct Fonts {
    pub system: FontSystem,
    vertical: HashMap<(String, u16), VerticalMetrics>,
    design: HashMap<(String, u16), DesignVertical>,
    /// Les largeurs déjà mesurées : (famille, graisse, taille, espacement, texte).
    advances: HashMap<(String, u16, u32, u32, String), f32>,
    /// Les largeurs de Windows (DirectWrite), celles de la 2.8.
    #[cfg(windows)]
    dwrite: crate::dwrite::Advances,
}

fn be_u16(data: &[u8], at: usize) -> Option<u16> {
    Some(u16::from_be_bytes([*data.get(at)?, *data.get(at + 1)?]))
}

fn be_i16(data: &[u8], at: usize) -> Option<i16> {
    be_u16(data, at).map(|v| v as i16)
}

fn tag(name: &[u8; 4]) -> u32 {
    u32::from_be_bytes(*name)
}

impl Fonts {
    /// Les polices des dossiers donnés (un sous-dossier par famille, comme `assets/fonts`), sans les
    /// polices de Windows : le démarrage ne lit que ce dont Project-On a besoin.
    pub fn from_dirs<P: AsRef<Path>>(dirs: &[P]) -> Self {
        let mut db = fontdb::Database::new();
        for dir in dirs {
            db.load_fonts_dir(dir);
        }
        Self::from_db(db)
    }

    /// Seulement les fichiers donnés.
    pub fn from_files<P: AsRef<Path>>(files: &[P]) -> Self {
        let mut db = fontdb::Database::new();
        for file in files {
            // Un fichier illisible est ignoré : cosmic-text se rabat sur une autre police.
            let _ = db.load_font_file(file);
        }
        Self::from_db(db)
    }

    fn from_db(db: fontdb::Database) -> Self {
        let system = FontSystem::new_with_locale_and_db("fr-FR".to_string(), db);
        Fonts {
            system,
            vertical: HashMap::new(),
            design: HashMap::new(),
            advances: HashMap::new(),
            #[cfg(windows)]
            dwrite: crate::dwrite::Advances::default(),
        }
    }

    /// Les familles chargées.
    pub fn families(&self) -> Vec<String> {
        let mut out: Vec<String> =
            self.system.db().faces().filter_map(|f| f.families.first().map(|(name, _)| name.clone())).collect();
        out.sort();
        out.dedup();
        out
    }

    /// La famille est-elle chargée ?
    pub fn has_family(&self, name: &str) -> bool {
        self.system.db().faces().any(|f| f.families.iter().any(|(n, _)| n.eq_ignore_ascii_case(name)))
    }

    /// La famille réellement utilisable : celle demandée, sinon Poppins, sinon la première chargée
    /// (`SlideCanvas._resolve_font_family`).
    pub fn resolve_family(&self, wanted: &str) -> String {
        for candidate in [wanted, "Poppins", "Segoe UI", "Arial"] {
            if !candidate.trim().is_empty() && self.has_family(candidate) {
                return candidate.trim().to_string();
            }
        }
        self.families().into_iter().next().unwrap_or_else(|| wanted.to_string())
    }

    /// Une ligne mise en forme, sans retour à la ligne.
    pub fn line(&mut self, text: &str, family: &str, weight: u16, size: f32) -> Buffer {
        let size = size.max(1.0);
        let mut buffer = Buffer::new(&mut self.system, Metrics::new(size, size * 1.2));
        // Sans hinting : les grandes tailles de la projection gardent le dessin exact des lettres.
        let attrs = Attrs::new()
            .family(Family::Name(family))
            .weight(Weight(weight))
            .cache_key_flags(CacheKeyFlags::DISABLE_HINTING);
        {
            let mut b = buffer.borrow_with(&mut self.system);
            b.set_wrap(Wrap::None);
            b.set_size(None, None);
            b.set_text(text, &attrs, Shaping::Advanced, None);
            b.shape_until_scroll(false);
        }
        buffer
    }

    /// La largeur exacte d'une ligne.
    pub fn width(&mut self, text: &str, family: &str, weight: u16, size: f32) -> f32 {
        self.line(text, family, weight, size).layout_runs().map(|run| run.line_w).fold(0.0, f32::max)
    }

    /// La largeur d'une ligne comme `QFontMetrics.horizontalAdvance` de la 2.8 : sous Windows, les
    /// avances de DirectWrite (mode GDI naturel) en virgule fixe, plus l'espacement des lettres après
    /// chacune ; ailleurs, chaque lettre arrondie au pixel (la même chose aux grandes tailles).
    pub fn qt_advance(&mut self, text: &str, family: &str, weight: u16, size: f32, letter_spacing: f32) -> f32 {
        if text.is_empty() {
            return 0.0;
        }
        let buffer = self.line(text, family, weight, size);
        let glyphs: Vec<(fontdb::ID, u16, f32)> =
            buffer.layout_runs().flat_map(|run| run.glyphs.iter().map(|g| (g.font_id, g.glyph_id, g.w))).collect();
        #[cfg(windows)]
        if let Some(total) = self.dwrite_advance(&glyphs, weight, size, letter_spacing) {
            return total;
        }
        glyphs.iter().map(|&(_, _, w)| w.round() + letter_spacing).sum()
    }

    /// [`Self::qt_advance`] gardé en mémoire : un mot n'est mesuré qu'une fois par taille.
    pub fn qt_advance_cached(&mut self, text: &str, family: &str, weight: u16, size: f32, letter_spacing: f32) -> f32 {
        let key = (family.to_string(), weight, size.to_bits(), letter_spacing.to_bits(), text.to_string());
        if let Some(found) = self.advances.get(&key) {
            return *found;
        }
        let width = self.qt_advance(text, family, weight, size, letter_spacing);
        if self.advances.len() > 200_000 {
            self.advances.clear(); // une très longue soirée : la mémoire reste bornée
        }
        self.advances.insert(key, width);
        width
    }

    /// La somme des avances de DirectWrite, plus le crénage de la mise en forme, arrondie au pixel
    /// comme `QFontMetrics`.
    #[cfg(windows)]
    fn dwrite_advance(
        &mut self,
        glyphs: &[(fontdb::ID, u16, f32)],
        weight: u16,
        size: f32,
        letter_spacing: f32,
    ) -> Option<f32> {
        let spacing = (f64::from(letter_spacing) * 64.0) as i64;
        let mut total = 0i64;
        let mut start = 0;
        while start < glyphs.len() {
            let font_id = glyphs[start].0;
            let end = glyphs[start..].iter().position(|g| g.0 != font_id).map_or(glyphs.len(), |n| start + n);
            let chunk = &glyphs[start..end];
            let (path, index) = {
                let face = self.system.db().face(font_id)?;
                let path = match &face.source {
                    fontdb::Source::File(path) => path.clone(),
                    fontdb::Source::SharedFile(path, _) => path.clone(),
                    fontdb::Source::Binary(_) => return None,
                };
                (path, face.index)
            };
            let ids: Vec<u16> = chunk.iter().map(|g| g.1).collect();
            let advances = self.dwrite.glyph_advances(&path, index, size, &ids)?;
            // Le crénage (GPOS) que la mise en forme ajoute aux avances de la police.
            let font = self.system.get_font(font_id, fontdb::Weight(weight))?;
            let face = font.as_swash();
            let upem = f32::from(face.metrics(&[]).units_per_em.max(1));
            let metrics = face.glyph_metrics(&[]);
            for (g, advance) in chunk.iter().zip(advances) {
                let design = metrics.advance_width(g.1) * size / upem;
                let kern = g.2 - design;
                let kern = if kern.abs() > 0.01 { (f64::from(kern) * 64.0) as i64 } else { 0 };
                // Chaque avance arrondie au pixel, comme les avances entières de Qt.
                total += ((advance + 32) >> 6 << 6) + spacing + kern;
            }
            start = end;
        }
        Some(((total + 32) >> 6) as f32)
    }

    fn font_id(&mut self, family: &str, weight: u16) -> Option<fontdb::ID> {
        let buffer = self.line("Hg", family, weight, 100.0);
        buffer.layout_runs().flat_map(|run| run.glyphs.iter()).map(|g| g.font_id).next()
    }

    /// Les mesures verticales de la police utilisée pour cette famille et cette graisse.
    pub fn vertical(&mut self, family: &str, weight: u16) -> VerticalMetrics {
        if let Some(found) = self.vertical.get(&(family.to_string(), weight)) {
            return *found;
        }
        let d = self.design(family, weight);
        let metrics = VerticalMetrics {
            ascent: d.ascent / d.units_per_em,
            descent: d.descent / d.units_per_em,
            leading: d.gap / d.units_per_em,
        };
        self.vertical.insert((family.to_string(), weight), metrics);
        metrics
    }

    /// Les métriques de dessin, comme DirectWrite les donne à Qt : celles de `OS/2` « typo » si la
    /// police le demande (USE_TYPO_METRICS), sinon les métriques « win », avec l'interligne de
    /// `hhea` qui dépasse.
    fn design(&mut self, family: &str, weight: u16) -> DesignVertical {
        if let Some(found) = self.design.get(&(family.to_string(), weight)) {
            return *found;
        }
        let fallback = DesignVertical { ascent: 900.0, descent: 250.0, gap: 0.0, units_per_em: 1000.0 };
        let found = self
            .font_id(family, weight)
            .and_then(|id| self.system.get_font(id, fontdb::Weight(weight)))
            .and_then(|font| {
                let face = font.as_swash();
                let head = face.table(tag(b"head"))?;
                let hhea = face.table(tag(b"hhea"))?;
                let units_per_em = f32::from(be_u16(head, 18)?.max(1));
                let (h_asc, h_desc, h_gap) =
                    (f32::from(be_i16(hhea, 4)?), f32::from(be_i16(hhea, 6)?), f32::from(be_i16(hhea, 8)?));
                let Some(os2) = face.table(tag(b"OS/2")) else {
                    return Some(DesignVertical { ascent: h_asc, descent: -h_desc, gap: h_gap, units_per_em });
                };
                let use_typo = be_u16(os2, 62)? & 0x80 != 0;
                if use_typo {
                    Some(DesignVertical {
                        ascent: f32::from(be_i16(os2, 68)?),
                        descent: -f32::from(be_i16(os2, 70)?),
                        gap: f32::from(be_i16(os2, 72)?),
                        units_per_em,
                    })
                } else {
                    let (w_asc, w_desc) = (f32::from(be_u16(os2, 74)?), f32::from(be_u16(os2, 76)?));
                    let gap = (h_asc - h_desc + h_gap - w_asc - w_desc).max(0.0);
                    Some(DesignVertical { ascent: w_asc, descent: w_desc, gap, units_per_em })
                }
            })
            .unwrap_or(fallback);
        self.design.insert((family.to_string(), weight), found);
        found
    }

    /// `QFontMetrics` à `size` pixels : valeurs de la police en virgule fixe 26.6 (tronquées),
    /// arrondies au pixel.
    pub fn qt_metrics(&mut self, family: &str, weight: u16, size: f32) -> QtMetrics {
        let d = self.design(family, weight);
        // Le calcul de Qt (`QFixed::fromReal(valeur * taille / unités)`), en double précision et dans
        // cet ordre : `1050 / 1000 * 45` donnerait 47,2499… et un interligne trop court d'un pixel.
        let fixed = |v: f32| ((f64::from(v) * f64::from(size) / f64::from(d.units_per_em)) * 64.0) as i64;
        let (a, de, g) = (fixed(d.ascent), fixed(d.descent), fixed(d.gap));
        let round = |v: i64| ((v + 32) >> 6) as i32;
        let ascent = round(a);
        let descent = round(de);
        QtMetrics { ascent, descent, height: ascent + descent, line_spacing: round(a + de + g) }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::bundled_fonts_dir;

    // Valeurs relevées avec `QFontMetrics` de PySide6 (2.8) sur les mêmes fichiers.
    #[test]
    fn vertical_metrics_like_qt() {
        let dir = bundled_fonts_dir();
        let mut fonts = Fonts::from_files(&[
            dir.join("Passion One/PassionOne-Bold.ttf"),
            dir.join("Poppins/Poppins-Bold.ttf"),
            dir.join("Poppins/Poppins-SemiBold.ttf"),
        ]);
        let m = |f: &mut Fonts, family: &str, weight: u16, size: f32| {
            let q = f.qt_metrics(family, weight, size);
            (q.ascent, q.descent, q.height, q.line_spacing)
        };
        assert_eq!(m(&mut fonts, "Passion One", 700, 100.0), (84, 27, 111, 110));
        assert_eq!(m(&mut fonts, "Passion One", 700, 21.0), (18, 6, 24, 23));
        assert_eq!(m(&mut fonts, "Passion One", 700, 180.0), (150, 48, 198, 198));
        assert_eq!(m(&mut fonts, "Poppins", 700, 21.0), (22, 7, 29, 31));
        assert_eq!(m(&mut fonts, "Poppins", 600, 100.0), (105, 35, 140, 150));
        assert_eq!(m(&mut fonts, "Poppins", 700, 180.0), (189, 63, 252, 270));
        assert_eq!(m(&mut fonts, "Poppins", 700, 45.0).3, 68);
        // Les avances entières des grandes tailles.
        assert_eq!(fonts.qt_advance("AMEN", "Passion One", 700, 100.0, 0.0), 238.0);
        assert_eq!(fonts.qt_advance("ET CETTE SEMAINE", "Passion One", 700, 100.0, 0.0), 729.0);
        assert_eq!(fonts.qt_advance("Jean 3:16", "Poppins", 600, 100.0, 0.0), 463.0);
    }
}
