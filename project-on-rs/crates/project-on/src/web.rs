//! La projection Web dans la régie : le serveur, ses écrans et leur état (bouton « Web » de la
//! barre), l'ouverture au réseau local avec son QR code.
//!
//! Le choix « réseau local » et son jeton sont gardés dans `web.json`, dans les données de la bêta.

use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Instant;

use egui::{Color32, CornerRadius, RichText, Sense, Ui, pos2, vec2};
use po_web::{Access, Hub, PRESETS, ScreenInfo, ScreenState, Server};
use serde_json::{Value, json};

use crate::theme::*;
use crate::widgets::{self, Tone};

/// Le serveur Web de la régie.
pub struct Web {
    pub hub: Arc<Hub>,
    server: Option<Server>,
    /// Le port demandé (le serveur prend le suivant s'il est pris).
    port: u16,
    /// Ouvert aux appareils du réseau local (sinon : ce poste seulement).
    pub lan: bool,
    token: String,
    file: Option<PathBuf>,
    pub error: Option<String>,
    /// Le QR code de l'adresse du réseau, déjà en texture.
    qr: Option<(String, egui::TextureHandle)>,
    /// La dernière adresse copiée, et quand (le bouton dit « Copié ✓ » deux secondes).
    copied: Option<(String, Instant)>,
}

impl Web {
    /// Démarre le serveur sur `port` (0 : un port libre), avec le choix gardé dans `file`.
    pub fn start(hub: Arc<Hub>, port: u16, file: Option<PathBuf>) -> Web {
        let saved = file
            .as_ref()
            .and_then(|f| std::fs::read_to_string(f).ok())
            .and_then(|t| serde_json::from_str::<Value>(&t).ok())
            .unwrap_or(Value::Null);
        let lan = saved.get("lan").and_then(Value::as_bool).unwrap_or(false);
        let token = saved
            .get("token")
            .and_then(Value::as_str)
            .filter(|t| t.len() >= 8 && t.chars().all(|c| c.is_ascii_alphanumeric()))
            .map_or_else(po_web::new_token, str::to_string);
        let mut web = Web { hub, server: None, port, lan, token, file, error: None, qr: None, copied: None };
        web.restart();
        web
    }

    /// (Re)démarre le serveur avec les règles d'accès actuelles. Les écrans ouverts se reconnectent
    /// seuls.
    fn restart(&mut self) {
        let port = self.server.take().map_or(self.port, |s| s.addr.port());
        self.hub.set_access(if self.lan { Access::lan(self.token.clone()) } else { Access::default() });
        let ip = if self.lan { IpAddr::V4(Ipv4Addr::UNSPECIFIED) } else { IpAddr::V4(Ipv4Addr::LOCALHOST) };
        match po_web::start_near(self.hub.clone(), ip, port) {
            Ok(server) => {
                po_core::journal::line(&format!("web : écoute sur {}", server.addr));
                self.server = Some(server);
                self.error = None;
            }
            Err(e) => {
                po_core::journal::line(&format!("web : serveur arrêté ({e})"));
                self.error = Some(format!("Serveur Web arrêté : ports {port} à {} occupés.", port.saturating_add(9)));
            }
        }
    }

    fn save(&self) {
        if let Some(file) = &self.file {
            let body = json!({ "lan": self.lan, "token": self.token });
            if let Err(e) = std::fs::write(file, body.to_string()) {
                po_core::journal::line(&format!("web : réglage non enregistré ({e})"));
            }
        }
    }

    /// Ouvre (ou ferme) les écrans aux appareils du réseau local.
    pub fn set_lan(&mut self, on: bool) {
        if self.lan != on {
            self.lan = on;
            self.save();
            self.restart();
        }
    }

    /// Un nouveau jeton : les anciens QR codes ne marchent plus.
    pub fn renew_token(&mut self) {
        self.token = po_web::new_token();
        self.qr = None;
        self.save();
        self.hub.set_access(if self.lan { Access::lan(self.token.clone()) } else { Access::default() });
    }

    pub fn addr(&self) -> Option<SocketAddr> {
        self.server.as_ref().map(|s| s.addr)
    }

    /// L'adresse d'une page sur ce poste (OBS, navigateur de la régie).
    pub fn local_url(&self, path: &str) -> Option<String> {
        self.addr().map(|a| format!("http://127.0.0.1:{}{path}", a.port()))
    }

    /// L'adresse d'une page pour un appareil du réseau, avec le jeton.
    pub fn lan_url(&self, path: &str) -> Option<String> {
        if !self.lan {
            return None;
        }
        let port = self.addr()?.port();
        let ip = po_web::lan_ip()?;
        Some(format!("http://{ip}:{port}{path}?t={}", self.token))
    }

    /// Le texte et la couleur du bouton « Web ».
    pub fn summary(&self, screens: &[ScreenInfo]) -> (String, Color32) {
        if self.server.is_none() {
            return ("Web · arrêté".into(), PGM);
        }
        let live = screens.iter().filter(|s| s.state != ScreenState::Dropped).count();
        let troubled = screens.iter().filter(|s| s.state != ScreenState::Ok).count();
        let text = match live {
            0 => "Web".to_string(),
            1 => "Web · 1 écran".to_string(),
            n => format!("Web · {n} écrans"),
        };
        let color = if troubled > 0 {
            WARN
        } else if live > 0 {
            PREVIEW
        } else {
            FAINT
        };
        (text, color)
    }

    /// Le bouton « Web » de la barre et sa fenêtre : les écrans, leurs adresses, le réseau local.
    pub fn button(&mut self, ui: &mut Ui) {
        let screens = self.hub.screens();
        let (text, color) = self.summary(&screens);
        let response = chip_button(ui, &text, color).on_hover_text("Les écrans Web : état, adresses, réseau local");
        egui::Popup::menu(&response)
            .close_behavior(egui::PopupCloseBehavior::CloseOnClickOutside)
            .width(430.0)
            .show(|ui| self.panel(ui, &screens));
        // Un écran qui se déconnecte devient orange sans attendre un clic.
        if !screens.is_empty() {
            ui.ctx().request_repaint_after(std::time::Duration::from_secs(1));
        }
    }

    fn panel(&mut self, ui: &mut Ui, screens: &[ScreenInfo]) {
        ui.set_width(430.0);
        ui.label(RichText::new("ÉCRANS CONNECTÉS").font(semibold(10.5)).color(FAINT));
        if let Some(error) = &self.error {
            ui.label(RichText::new(error).font(medium(12.0)).color(PGM));
        }
        if screens.is_empty() {
            ui.label(RichText::new("Aucun écran ouvert.").font(regular(12.0)).color(MUTED));
        }
        let now = Instant::now();
        for s in screens {
            ui.horizontal(|ui| {
                let (color, state) = match s.state {
                    ScreenState::Ok => (PREVIEW, "à jour".to_string()),
                    ScreenState::Late => (WARN, "en retard".to_string()),
                    ScreenState::Dropped => (
                        WARN,
                        format!("déconnecté il y a {} s", s.dropped.map_or(0, |t| now.duration_since(t).as_secs())),
                    ),
                };
                widgets::dot(ui, color);
                ui.label(RichText::new(s.kind.label()).font(semibold(12.5)).color(TEXT));
                let place = if s.local() { "ce poste".to_string() } else { s.addr.ip().to_string() };
                let size = if s.width > 0.0 {
                    format!(" · {}×{}", s.width.round(), s.height.round())
                } else {
                    String::new()
                };
                ui.label(RichText::new(format!("/{}{size} · {place}", s.name)).font(regular(11.5)).color(MUTED));
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    ui.label(RichText::new(state).font(medium(11.5)).color(color));
                });
            });
        }
        ui.add_space(8.0);
        ui.separator();
        ui.label(RichText::new("ADRESSES SUR CE POSTE").font(semibold(10.5)).color(FAINT));
        for (name, kind, _, about) in PRESETS {
            let Some(url) = self.local_url(&format!("/ecran/{name}")) else { break };
            ui.horizontal(|ui| {
                ui.label(RichText::new(kind.label()).font(semibold(12.0)).color(TEXT)).on_hover_text(about);
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    if widgets::button(ui, None, "Ouvrir", Tone::Secondary)
                        .on_hover_text("Ouvrir dans le navigateur de ce poste")
                        .clicked()
                    {
                        ui.ctx().open_url(egui::OpenUrl::new_tab(&url));
                    }
                    self.copy_button(ui, &url);
                    // L'adresse se sélectionne aussi à la souris (Ctrl+C).
                    ui.add(egui::Label::new(RichText::new(&url).font(regular(11.5)).color(ACCENT)).selectable(true));
                });
            });
        }
        ui.label(
            RichText::new("Dans OBS : une source « Navigateur » sur l'adresse Diffusion (l'ancienne /obs y mène).")
                .font(regular(11.0))
                .color(FAINT),
        );
        ui.add_space(8.0);
        ui.separator();
        let mut lan = self.lan;
        if ui
            .checkbox(
                &mut lan,
                RichText::new("Ouvrir aux appareils du réseau (téléviseurs, tablettes)").font(medium(12.0)),
            )
            .changed()
        {
            self.set_lan(lan);
        }
        if self.lan {
            match self.lan_url("/") {
                Some(url) => {
                    ui.label(
                        RichText::new("Sur l'appareil, scannez ce code ou tapez l'adresse, puis choisissez l'écran.")
                            .font(regular(11.5))
                            .color(MUTED),
                    );
                    ui.horizontal(|ui| {
                        self.qr_image(ui, &url);
                        ui.vertical(|ui| {
                            ui.add(
                                egui::Label::new(RichText::new(&url).font(medium(12.0)).color(ACCENT)).selectable(true),
                            );
                            self.copy_button(ui, &url);
                            if widgets::button(ui, None, "Nouveau code", Tone::Secondary)
                                .on_hover_text("Les anciens codes ne permettent plus d'ouvrir un écran")
                                .clicked()
                            {
                                self.renew_token();
                            }
                        });
                    });
                }
                None => {
                    ui.label(RichText::new("Ce poste n'est relié à aucun réseau.").font(regular(12.0)).color(WARN));
                }
            }
        } else {
            ui.label(
                RichText::new("Fermé : seuls OBS et les navigateurs de ce poste ouvrent les écrans.")
                    .font(regular(11.5))
                    .color(FAINT),
            );
        }
    }

    /// « Copier » met l'adresse dans le presse-papiers, puis dit « Copié ✓ » deux secondes.
    fn copy_button(&mut self, ui: &mut Ui, url: &str) {
        let recent = self.copied.as_ref().is_some_and(|(u, at)| u == url && at.elapsed().as_secs_f32() < 2.0);
        let label = if recent { "Copié ✓" } else { "Copier" };
        let tone = if recent { Tone::Primary(PREVIEW) } else { Tone::Secondary };
        if widgets::button(ui, None, label, tone).on_hover_text("Copier l'adresse").clicked() {
            ui.ctx().copy_text(url.to_string());
            self.copied = Some((url.to_string(), Instant::now()));
            ui.ctx().request_repaint_after(std::time::Duration::from_secs(2));
        }
    }

    /// La dernière adresse copiée (essais).
    pub fn copied(&self) -> Option<&str> {
        self.copied.as_ref().map(|(u, _)| u.as_str())
    }

    fn qr_image(&mut self, ui: &mut Ui, url: &str) {
        if self.qr.as_ref().is_none_or(|(u, _)| u != url)
            && let Some((width, modules)) = po_web::qr(url)
        {
            let quiet = 2;
            let side = width + 2 * quiet;
            let mut pixels = vec![Color32::WHITE; side * side];
            for (i, dark) in modules.iter().enumerate() {
                if *dark {
                    pixels[(i / width + quiet) * side + i % width + quiet] = Color32::BLACK;
                }
            }
            let image = egui::ColorImage::new([side, side], pixels);
            let texture = ui.ctx().load_texture("web-qr", image, egui::TextureOptions::NEAREST);
            self.qr = Some((url.to_string(), texture));
        }
        if let Some((_, texture)) = &self.qr {
            ui.add(egui::Image::new(texture).fit_to_exact_size(vec2(132.0, 132.0)));
        }
    }
}

/// Un bouton en forme d'étiquette colorée.
fn chip_button(ui: &mut Ui, text: &str, color: Color32) -> egui::Response {
    let g = ui.painter().layout_no_wrap(text.to_string(), semibold(10.5), color);
    let size = vec2(g.size().x + 26.0, 22.0);
    let (rect, response) = ui.allocate_exact_size(size, Sense::click());
    let fill = if response.hovered() { color.gamma_multiply(0.26) } else { color.gamma_multiply(0.16) };
    let painter = ui.painter();
    painter.rect_filled(rect, CornerRadius::same(11), fill);
    painter.circle_filled(pos2(rect.min.x + 10.0, rect.center().y), 3.5, color);
    painter.galley(pos2(rect.min.x + 18.0, rect.center().y - g.size().y / 2.0), g, color);
    let label = text.to_string();
    ui.ctx().accesskit_node_builder(response.id, |n| {
        n.set_role(egui::accesskit::Role::Button);
        n.set_label(label);
    });
    response
}
