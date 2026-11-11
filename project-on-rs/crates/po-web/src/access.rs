//! Qui peut ouvrir un écran. Par défaut, le serveur n'écoute que ce poste (127.0.0.1) : OBS et les
//! navigateurs de la régie. Sur le réseau local (option), un appareil doit présenter le jeton de la
//! régie, dans l'adresse (`?t=…`, celle du QR code) puis dans un cookie que la page dépose.

use std::net::IpAddr;

/// Le nom du cookie qui garde le jeton après la première page.
pub const COOKIE: &str = "po_t";

/// Les règles d'accès.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Access {
    /// Le jeton demandé aux appareils du réseau ; `None` : aucun jeton demandé.
    pub token: Option<String>,
    /// Ce poste (OBS, navigateur de la régie) entre sans jeton.
    pub loopback_trusted: bool,
}

impl Default for Access {
    fn default() -> Self {
        Access { token: None, loopback_trusted: true }
    }
}

impl Access {
    /// Le réseau local avec un jeton.
    pub fn lan(token: impl Into<String>) -> Self {
        Access { token: Some(token.into()), loopback_trusted: true }
    }

    /// Une requête de `ip`, avec le jeton de l'adresse (`query`) ou du cookie, peut-elle passer ?
    pub fn allows(&self, ip: IpAddr, query: Option<&str>, cookie: Option<&str>) -> bool {
        let Some(token) = &self.token else { return true };
        if self.loopback_trusted && ip.is_loopback() {
            return true;
        }
        let given = query.and_then(|q| param(q, "t")).or_else(|| cookie.and_then(|c| cookie_value(c, COOKIE)));
        given.is_some_and(|g| constant_time_eq(g.as_bytes(), token.as_bytes()))
    }
}

/// La valeur de `key` dans une chaîne de requête (`a=1&t=xyz`).
pub fn param<'a>(query: &'a str, key: &str) -> Option<&'a str> {
    query.split('&').filter_map(|pair| pair.split_once('=')).find(|(k, _)| *k == key).map(|(_, v)| v)
}

fn cookie_value<'a>(header: &'a str, key: &str) -> Option<&'a str> {
    header.split(';').filter_map(|pair| pair.trim().split_once('=')).find(|(k, _)| *k == key).map(|(_, v)| v)
}

fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    a.len() == b.len() && a.iter().zip(b).fold(0u8, |acc, (x, y)| acc | (x ^ y)) == 0
}

/// Un nouveau jeton : 12 caractères sans ambiguïté (ni 0/O ni 1/l), tirés de l'aléa du système.
pub fn new_token() -> String {
    use std::collections::hash_map::RandomState;
    use std::hash::{BuildHasher, Hasher};
    const ALPHABET: &[u8] = b"abcdefghijkmnpqrstuvwxyz23456789";
    let mut out = String::new();
    while out.len() < 12 {
        // `RandomState` est semé par le système à chaque création.
        let mut h = RandomState::new().build_hasher();
        h.write_u128(std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(0, |d| d.as_nanos()));
        let mut v = h.finish();
        for _ in 0..6 {
            out.push(ALPHABET[(v % ALPHABET.len() as u64) as usize] as char);
            v /= ALPHABET.len() as u64;
        }
    }
    out.truncate(12);
    out
}

/// Le QR code d'un texte : le côté en modules et les modules noirs, ligne par ligne.
pub fn qr(text: &str) -> Option<(usize, Vec<bool>)> {
    let code = qrcode::QrCode::with_error_correction_level(text.as_bytes(), qrcode::EcLevel::M).ok()?;
    let width = code.width();
    let modules = code.to_colors().into_iter().map(|c| c == qrcode::Color::Dark).collect();
    Some((width, modules))
}

/// Le QR code en SVG (pour la page d'accueil des écrans).
pub fn qr_svg(text: &str, pixels: u32) -> String {
    let Some((width, modules)) = qr(text) else { return String::new() };
    let quiet = 2;
    let side = width + 2 * quiet;
    let mut path = String::new();
    for (i, dark) in modules.iter().enumerate() {
        if *dark {
            let (x, y) = (i % width + quiet, i / width + quiet);
            path.push_str(&format!("M{x} {y}h1v1h-1z"));
        }
    }
    format!(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 {side} {side}\" width=\"{pixels}\" height=\"{pixels}\" shape-rendering=\"crispEdges\"><rect width=\"{side}\" height=\"{side}\" fill=\"#fff\"/><path d=\"{path}\" fill=\"#000\"/></svg>"
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn network_devices_need_the_token_this_computer_does_not() {
        let lan: IpAddr = "192.168.1.30".parse().unwrap();
        let local: IpAddr = "127.0.0.1".parse().unwrap();
        assert!(Access::default().allows(lan, None, None), "sans jeton, tout passe (écoute locale seule)");
        let access = Access::lan("abc123");
        assert!(access.allows(local, None, None));
        assert!(!access.allows(lan, None, None));
        assert!(!access.allows(lan, Some("t=abc12"), None));
        assert!(access.allows(lan, Some("x=1&t=abc123"), None));
        assert!(access.allows(lan, None, Some("autre=1; po_t=abc123")));
        let strict = Access { loopback_trusted: false, ..access };
        assert!(!strict.allows(local, None, None));
    }

    #[test]
    fn tokens_are_fresh_and_readable() {
        let a = new_token();
        let b = new_token();
        assert_eq!(a.len(), 12);
        assert_ne!(a, b);
        assert!(a.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit()));
        let (width, modules) = qr("http://192.168.1.20:8090/?t=abcdefghijkm").unwrap();
        assert_eq!(modules.len(), width * width);
        assert!(qr_svg("http://x", 120).starts_with("<svg"));
    }
}
