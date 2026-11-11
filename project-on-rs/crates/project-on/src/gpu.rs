//! Le choix de la carte graphique : DirectX 12 d'abord, OpenGL en repli, jamais Vulkan par défaut.
//!
//! Le pilote Vulkan de l'Intel UHD 620 (le portable de l'église, `igvk64.dll` 31.0.101.2127) fait
//! planter le processus dès la première image : Pgraphics l'avait mesuré le 20 octobre 2026, la
//! bêta 1 de Project-On l'a subi le 11 novembre (rien ne s'affichait). `WGPU_BACKEND` impose un choix.

use std::sync::Arc;

use eframe::egui_wgpu::{WgpuConfiguration, WgpuSetup, WgpuSetupCreateNew, wgpu};

/// Les interfaces graphiques essayées, sauf si `WGPU_BACKEND` en impose une.
pub fn backends() -> wgpu::Backends {
    if std::env::var_os("WGPU_BACKEND").is_some() {
        wgpu::Backends::from_env().unwrap_or(wgpu::Backends::all())
    } else {
        wgpu::Backends::DX12 | wgpu::Backends::GL
    }
}

/// Le rang d'une carte : DirectX 12 avant OpenGL, une carte dédiée avant la carte intégrée.
fn rank(info: &wgpu::AdapterInfo) -> (bool, bool) {
    (info.backend != wgpu::Backend::Dx12, info.device_type != wgpu::DeviceType::DiscreteGpu)
}

/// La carte choisie parmi celles qui peuvent dessiner dans la fenêtre.
pub fn choose(adapters: &[wgpu::Adapter], surface: Option<&wgpu::Surface<'_>>) -> Result<wgpu::Adapter, String> {
    adapters
        .iter()
        .filter(|a| surface.is_none_or(|s| a.is_surface_supported(s)))
        .min_by_key(|a| rank(&a.get_info()))
        .cloned()
        .ok_or_else(|| "aucune carte graphique DirectX 12 ni OpenGL".to_string())
}

/// La configuration d'eframe.
pub fn configuration() -> WgpuConfiguration {
    let mut setup = WgpuSetupCreateNew::without_display_handle();
    setup.instance_descriptor.backends = backends();
    if std::env::var_os("WGPU_BACKEND").is_none() {
        setup.native_adapter_selector = Some(Arc::new(choose));
    }
    WgpuConfiguration { wgpu_setup: WgpuSetup::CreateNew(setup), ..Default::default() }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Sans fenêtre : les cartes que verrait la régie sur ce poste. Sous Windows, la carte choisie
    /// est une carte DirectX 12, jamais Vulkan.
    #[cfg(windows)]
    #[test]
    fn this_computer_gets_a_directx_12_adapter() {
        let mut descriptor = wgpu::InstanceDescriptor::new_without_display_handle_from_env();
        descriptor.backends = wgpu::Backends::DX12 | wgpu::Backends::GL;
        let instance = wgpu::Instance::new(descriptor);
        let adapters = pollster::block_on(instance.enumerate_adapters(wgpu::Backends::DX12 | wgpu::Backends::GL));
        let chosen = choose(&adapters, None).expect("une carte graphique");
        let info = chosen.get_info();
        assert_eq!(info.backend, wgpu::Backend::Dx12, "{info:?}");
        assert!(adapters.iter().all(|a| a.get_info().backend != wgpu::Backend::Vulkan));
    }
}
