//! Les polices : chargement des fichiers de Project-On et mise en forme d'une ligne (cosmic-text).

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
    /// L'interligne naturel (ascendante + descendante + interligne de la police), comme
    /// `QFontMetrics.lineSpacing()` dans la 2.x.
    pub fn line_spacing(&self) -> f32 {
        self.ascent + self.descent + self.leading
    }
}

/// Le système de polices de Project-On.
pub struct Fonts {
    pub system: FontSystem,
    vertical: HashMap<(String, u16), VerticalMetrics>,
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

    /// Seulement les fichiers donnés (le plus rapide : la police de la projection et celle de la
    /// référence).
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
        Fonts { system, vertical: HashMap::new() }
    }

    /// Les familles chargées.
    pub fn families(&self) -> Vec<String> {
        let mut out: Vec<String> =
            self.system.db().faces().filter_map(|f| f.families.first().map(|(name, _)| name.clone())).collect();
        out.sort();
        out.dedup();
        out
    }

    /// Une ligne mise en forme, sans retour à la ligne.
    pub fn line(&mut self, text: &str, family: &str, weight: u16, size: f32) -> Buffer {
        let size = size.max(1.0);
        let mut buffer = Buffer::new(&mut self.system, Metrics::new(size, size * 1.2));
        // Sans hinting : les grandes tailles de la projection gardent le dessin exact des lettres, et
        // la largeur mesurée ne dépend pas de la grille des pixels.
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

    /// La largeur d'une ligne.
    pub fn width(&mut self, text: &str, family: &str, weight: u16, size: f32) -> f32 {
        self.line(text, family, weight, size).layout_runs().map(|run| run.line_w).fold(0.0, f32::max)
    }

    /// Les mesures verticales de la police utilisée pour cette famille et cette graisse.
    pub fn vertical(&mut self, family: &str, weight: u16) -> VerticalMetrics {
        if let Some(found) = self.vertical.get(&(family.to_string(), weight)) {
            return *found;
        }
        let buffer = self.line("Hg", family, weight, 100.0);
        let font_id = buffer.layout_runs().flat_map(|run| run.glyphs.iter()).map(|g| g.font_id).next();
        let metrics = font_id
            .and_then(|id| self.system.get_font(id, fontdb::Weight(weight)))
            .map(|font| {
                let m = font.metrics();
                let em = f32::from(m.units_per_em.max(1));
                VerticalMetrics { ascent: m.ascent / em, descent: m.descent.abs() / em, leading: m.leading / em }
            })
            // Sans police du tout : des valeurs courantes, pour ne jamais bloquer l'affichage.
            .unwrap_or(VerticalMetrics { ascent: 0.9, descent: 0.25, leading: 0.0 });
        self.vertical.insert((family.to_string(), weight), metrics);
        metrics
    }
}
