//! Les largeurs des lettres données par DirectWrite, en mode « GDI naturel » : celles que Qt
//! utilise sous Windows (`QWindowsFontEngineDirectWrite::recalcAdvances`), donc celles de la 2.8.
//!
//! Aux tailles moyennes (20 à 60 px), Windows arrondit la largeur de chaque lettre d'une façon que
//! le simple arrondi ne reproduit pas ; sans ces largeurs, la 3.0 couperait une ligne sur cinquante
//! à un autre mot que la 2.8. Les largeurs sont gardées en cache : un mot déjà mesuré ne repasse
//! plus par Windows.
//!
//! Seul module de `po-layout` qui appelle Windows (COM) : le code `unsafe` est limité aux appels,
//! avec des tampons de la bonne taille.

#![allow(unsafe_code)]

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use windows::Win32::Graphics::DirectWrite::{
    DWRITE_FACTORY_TYPE_SHARED, DWRITE_FONT_FACE_TYPE_TRUETYPE, DWRITE_FONT_METRICS, DWRITE_FONT_SIMULATIONS_NONE,
    DWRITE_GLYPH_METRICS, DWriteCreateFactory, IDWriteFactory, IDWriteFontFace,
};
use windows::core::HSTRING;

/// Une police ouverte par DirectWrite.
struct Face {
    face: IDWriteFontFace,
    units_per_em: f64,
}

/// Les largeurs de DirectWrite, par fichier de police, taille et lettre.
#[derive(Default)]
pub struct Advances {
    factory: Option<IDWriteFactory>,
    faces: HashMap<(PathBuf, u32), Option<Face>>,
    /// (fichier, index, taille en 1/64 px, lettre) → avance en 1/64 px (virgule fixe 26.6 de Qt).
    cache: HashMap<(PathBuf, u32, i64, u16), i64>,
}

impl Advances {
    fn face(&mut self, path: &Path, index: u32) -> Option<&Face> {
        let key = (path.to_path_buf(), index);
        if !self.faces.contains_key(&key) {
            let opened = self.open(path, index);
            self.faces.insert(key.clone(), opened);
        }
        self.faces.get(&key).and_then(Option::as_ref)
    }

    fn open(&mut self, path: &Path, index: u32) -> Option<Face> {
        if self.factory.is_none() {
            // SAFETY : création de la fabrique partagée de DirectWrite, sans argument.
            self.factory = unsafe { DWriteCreateFactory::<IDWriteFactory>(DWRITE_FACTORY_TYPE_SHARED) }.ok();
        }
        let factory = self.factory.as_ref()?;
        // SAFETY : le chemin est une chaîne valide ; les interfaces rendues sont gardées vivantes.
        unsafe {
            let file = factory.CreateFontFileReference(&HSTRING::from(path.as_os_str()), None).ok()?;
            let face = factory
                .CreateFontFace(DWRITE_FONT_FACE_TYPE_TRUETYPE, &[Some(file)], index, DWRITE_FONT_SIMULATIONS_NONE)
                .ok()?;
            let mut metrics = DWRITE_FONT_METRICS::default();
            face.GetMetrics(&mut metrics);
            Some(Face { face, units_per_em: f64::from(metrics.designUnitsPerEm.max(1)) })
        }
    }

    /// Les avances des lettres `glyphs` de la police `path` à `size` pixels, en 1/64 de pixel
    /// (`QFixed`), ou `None` si DirectWrite ne peut pas ouvrir le fichier.
    pub fn glyph_advances(&mut self, path: &Path, index: u32, size: f32, glyphs: &[u16]) -> Option<Vec<i64>> {
        let size_key = (f64::from(size) * 64.0) as i64;
        let missing: Vec<u16> = {
            let mut seen = Vec::new();
            for &g in glyphs {
                if !self.cache.contains_key(&(path.to_path_buf(), index, size_key, g)) && !seen.contains(&g) {
                    seen.push(g);
                }
            }
            seen
        };
        if !missing.is_empty() {
            let face = self.face(path, index)?;
            let mut metrics = vec![DWRITE_GLYPH_METRICS::default(); missing.len()];
            // SAFETY : `missing` et `metrics` ont la même longueur, passée à DirectWrite.
            unsafe {
                face.face
                    .GetGdiCompatibleGlyphMetrics(
                        size,
                        1.0,
                        None,
                        true,
                        missing.as_ptr(),
                        missing.len() as u32,
                        metrics.as_mut_ptr(),
                        false,
                    )
                    .ok()?;
            }
            let units = face.units_per_em;
            for (g, m) in missing.iter().zip(&metrics) {
                // `DESIGN_TO_LOGICAL` puis `QFixed::fromReal` (troncature).
                let fixed = ((f64::from(m.advanceWidth) / units) * f64::from(size) * 64.0) as i64;
                self.cache.insert((path.to_path_buf(), index, size_key, *g), fixed);
            }
        }
        Some(
            glyphs
                .iter()
                .map(|g| self.cache.get(&(path.to_path_buf(), index, size_key, *g)).copied().unwrap_or(0))
                .collect(),
        )
    }
}
