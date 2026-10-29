//! Redimensionnement des photos des visuels (citations, miniatures).
//!
//! Pillow redimensionne en C mais sur un seul cœur ; `fast_image_resize`
//! utilise le SIMD et tous les cœurs (rayon), sans bloquer Python pendant
//! le calcul. Lanczos 3 construit sur le modèle de Pillow : l'écart reste
//! invisible (quelques niveaux sur 255 aux contours).
//!
//! Les pixels arrivent et repartent en octets entrelacés (`Image.tobytes()`),
//! 1, 3 ou 4 canaux par pixel.

use fast_image_resize::images::{Image, ImageRef};
use fast_image_resize::{FilterType, PixelType, ResizeAlg, ResizeOptions, Resizer};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

fn pixel_type(channels: usize) -> PyResult<PixelType> {
    match channels {
        1 => Ok(PixelType::U8),
        3 => Ok(PixelType::U8x3),
        4 => Ok(PixelType::U8x4),
        _ => Err(PyValueError::new_err("1, 3 ou 4 canaux attendus")),
    }
}

/// Redimensionne en Lanczos 3. `alpha` : le 4e canal est une transparence
/// (pixels prémultipliés pendant le calcul, comme Pillow pour le RGBA).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn resize_lanczos<'py>(
    py: Python<'py>,
    data: &[u8],
    width: u32,
    height: u32,
    channels: usize,
    alpha: bool,
    new_width: u32,
    new_height: u32,
) -> PyResult<Bound<'py, PyBytes>> {
    let kind = pixel_type(channels)?;
    if width == 0 || height == 0 || data.len() != width as usize * height as usize * channels {
        return Err(PyValueError::new_err("taille des pixels incohérente"));
    }
    if new_width == 0 || new_height == 0 {
        return Err(PyValueError::new_err("taille cible nulle"));
    }
    let out = py.detach(|| -> Result<Vec<u8>, String> {
        let src = ImageRef::new(width, height, data, kind).map_err(|e| e.to_string())?;
        let mut dst = Image::new(new_width, new_height, kind);
        let options = ResizeOptions::new()
            .resize_alg(ResizeAlg::Convolution(FilterType::Lanczos3))
            .use_alpha(alpha && channels == 4);
        Resizer::new()
            .resize(&src, &mut dst, &options)
            .map_err(|e| e.to_string())?;
        Ok(dst.into_vec())
    });
    Ok(PyBytes::new(py, &out.map_err(PyValueError::new_err)?))
}
