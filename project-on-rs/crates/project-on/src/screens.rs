//! Les écrans branchés et le choix de l'écran de projection.
//!
//! Le nom d'un écran est celui de Windows (`\\.\DISPLAY2`), le même que `QScreen::name()` : le
//! réglage `display_screen` de la 2.x désigne donc le même écran ici. La liste vient de
//! `EnumDisplayMonitors` (code repris de Pgraphics, `sources/desktop.rs`).

#![allow(unsafe_code)]

/// Un écran : son nom Windows, un libellé pour l'opérateur, sa place en pixels.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Screen {
    pub device: String,
    pub label: String,
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
    pub primary: bool,
}

impl Screen {
    pub fn area(&self) -> u64 {
        u64::from(self.width) * u64::from(self.height)
    }
}

/// Les écrans branchés.
#[cfg(windows)]
pub fn list() -> Vec<Screen> {
    use windows::Win32::Foundation::{LPARAM, RECT};
    use windows::Win32::Graphics::Gdi::{EnumDisplayMonitors, GetMonitorInfoW, HDC, HMONITOR, MONITORINFOEXW};
    use windows::core::BOOL;

    unsafe extern "system" fn found(monitor: HMONITOR, _: HDC, _: *mut RECT, data: LPARAM) -> BOOL {
        // SAFETY : `data` est le vecteur passé à EnumDisplayMonitors, vivant pendant l'appel.
        let list = unsafe { &mut *(data.0 as *mut Vec<Screen>) };
        let mut info = MONITORINFOEXW::default();
        info.monitorInfo.cbSize = std::mem::size_of::<MONITORINFOEXW>() as u32;
        // SAFETY : `info` est un MONITORINFOEXW dont la taille est annoncée dans cbSize.
        if unsafe { GetMonitorInfoW(monitor, &mut info.monitorInfo) }.as_bool() {
            let r = info.monitorInfo.rcMonitor;
            let (width, height) = ((r.right - r.left).max(0) as u32, (r.bottom - r.top).max(0) as u32);
            let primary = info.monitorInfo.dwFlags & 1 != 0;
            let len = info.szDevice.iter().position(|c| *c == 0).unwrap_or(info.szDevice.len());
            let device = String::from_utf16_lossy(&info.szDevice[..len]);
            let n = list.len() + 1;
            let label = format!("Écran {n}{} — {width} × {height}", if primary { " (principal)" } else { "" });
            list.push(Screen { device, label, x: r.left, y: r.top, width, height, primary });
        }
        BOOL(1)
    }
    let mut list: Vec<Screen> = Vec::new();
    // SAFETY : rappel et données valides pendant l'énumération.
    unsafe {
        let _ = EnumDisplayMonitors(None, None, Some(found), LPARAM(&mut list as *mut _ as isize));
    }
    list
}

#[cfg(not(windows))]
pub fn list() -> Vec<Screen> {
    Vec::new()
}

/// L'écran de projection, comme la 2.8 (`_apply_best_screen_fullscreen`) : celui des réglages
/// s'il est branché ; sinon le plus grand des écrans secondaires ; sinon le plus grand.
pub fn choose<'a>(screens: &'a [Screen], preferred: &str) -> Option<&'a Screen> {
    let preferred = preferred.trim();
    if !preferred.is_empty()
        && preferred != "auto"
        && let Some(s) = screens.iter().find(|s| s.device == preferred)
    {
        return Some(s);
    }
    if screens.len() >= 2
        && let Some(s) = screens.iter().filter(|s| !s.primary).max_by_key(|s| s.area())
    {
        return Some(s);
    }
    screens.iter().max_by_key(|s| s.area())
}

/// Pose la fenêtre `title` exactement sur l'écran, au premier plan. Faux tant qu'elle n'existe pas.
#[cfg(windows)]
pub fn place(title: &str, screen: &Screen) -> bool {
    use windows::Win32::UI::WindowsAndMessaging::{FindWindowW, HWND_TOPMOST, SWP_SHOWWINDOW, SetWindowPos};
    use windows::core::HSTRING;
    // SAFETY : appels Win32 sur une fenêtre de ce processus, retrouvée par son titre.
    unsafe {
        let Ok(hwnd) = FindWindowW(None, &HSTRING::from(title)) else { return false };
        if hwnd.0.is_null() {
            return false;
        }
        SetWindowPos(
            hwnd,
            Some(HWND_TOPMOST),
            screen.x,
            screen.y,
            screen.width as i32,
            screen.height as i32,
            SWP_SHOWWINDOW,
        )
        .is_ok()
    }
}

#[cfg(not(windows))]
pub fn place(_title: &str, _screen: &Screen) -> bool {
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    fn screen(device: &str, w: u32, h: u32, primary: bool) -> Screen {
        Screen { device: device.into(), label: device.into(), x: 0, y: 0, width: w, height: h, primary }
    }

    #[test]
    fn the_projection_screen_follows_the_2x_rule() {
        let laptop = screen(r"\\.\DISPLAY1", 1920, 1080, true);
        let projector = screen(r"\\.\DISPLAY2", 1280, 720, false);
        let tv = screen(r"\\.\DISPLAY3", 3840, 2160, false);
        let all = [laptop.clone(), projector.clone(), tv.clone()];
        assert_eq!(choose(&all, r"\\.\DISPLAY2"), Some(&projector), "l'écran des réglages");
        assert_eq!(choose(&all, "auto"), Some(&tv), "le plus grand des secondaires");
        assert_eq!(choose(&all, r"\\.\DISPLAY9"), Some(&tv), "écran débranché : comme « auto »");
        assert_eq!(choose(std::slice::from_ref(&laptop), "auto"), Some(&laptop), "un seul écran");
        assert_eq!(choose(&[], "auto"), None);
    }

    #[test]
    fn this_computer_has_at_least_one_screen() {
        // Rien n'est ouvert : seulement la liste de Windows.
        let screens = list();
        assert!(!screens.is_empty());
        assert!(screens.iter().all(|s| s.device.starts_with(r"\\.\")), "{screens:?}");
    }
}
