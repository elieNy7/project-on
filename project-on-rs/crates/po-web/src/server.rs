//! Le serveur HTTP + WebSocket (axum), sur son propre fil avec un petit runtime tokio.

use std::net::{IpAddr, SocketAddr};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use axum::Router;
use axum::extract::ws::{CloseFrame, Message, WebSocket, WebSocketUpgrade};
use axum::extract::{ConnectInfo, Path, RawQuery, Request, State};
use axum::http::{HeaderValue, StatusCode, header};
use axum::middleware::Next;
use axum::response::{Html, IntoResponse, Redirect, Response};
use axum::routing::get;
use futures_util::{SinkExt, StreamExt};
use po_design::graphics::{LowerThirdStyle, LowerThirdText, SubtitleStyle};
use po_design::{Animation, Band, Rgba, RoomDesign, SlideSource};
use po_layout::graphics::{graphic_frame, layout_lower_third, layout_subtitle_with_reference, test_pattern};
use po_layout::{DisplayList, Fonts, Item, Slide, layout_band, layout_room, layout_stage};
use po_render::Renderer;
use tokio::sync::{oneshot, watch};

use crate::access::{self, Access, COOKIE};
use crate::protocol::{ClientMessage, PROTOCOL_VERSION, ServerMessage};
use crate::screens::{PRESETS, Registry, ScreenInfo, ScreenKind};

/// Tout ce qui, en plus du slide au direct, décide de ce que montrent les écrans.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Context {
    /// Le design de la salle (écrans « salle »).
    pub design: RoomDesign,
    /// Le design des sorties de diffusion (écran Web « diffusion », NDI, HDMI).
    pub broadcast: Look,
    /// Le slide suivant (retour de scène).
    pub next: Option<Slide>,
    /// Le texte est masqué (le fond reste).
    pub hidden: bool,
    /// L'heure affichée sur le retour de scène (« 10:42 »).
    pub clock: String,
    /// Le déroulé du culte, pour le retour de scène (« Prédication · 12:00 restantes »).
    pub status: String,
    /// Le lower third de la diffusion (affiché, ou en train d'entrer ou de sortir).
    pub lower_third: Option<Overlay>,
    /// Le sous-titre affiché (écrans « sous-titres ») ; `None` : sous-titres masqués.
    pub subtitle: Option<(SubtitleStyle, String)>,
}

/// Le design des sorties de diffusion, choisi dans la page Designs : un bandeau, ou un design de
/// slide plein écran dont le texte est posé sur un fond transparent (la projection de la salle
/// garde son propre design).
#[derive(Debug, Clone, PartialEq)]
pub enum Look {
    Band(Band),
    Slide(RoomDesign),
}

impl Default for Look {
    fn default() -> Self {
        Look::Band(Band::default())
    }
}

impl Look {
    /// La transition entre deux slides.
    pub fn animation(&self) -> Animation {
        match self {
            Look::Band(band) => band.animation,
            Look::Slide(design) => design.animation,
        }
    }
}

/// Les ajustements propres à une sortie HDMI (`HdmiSettings` de la 2.8) : la taille du texte
/// (le rendu caméra supporte souvent plus grand que l'écran) et un décalage vertical fin.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Adjust {
    /// 0,6 à 1,8.
    pub scale: f32,
    /// En pixels pour 1080 lignes (positif : vers le bas).
    pub offset_y: f32,
}

impl Default for Adjust {
    fn default() -> Self {
        Adjust { scale: 1.0, offset_y: 0.0 }
    }
}

impl Adjust {
    /// Depuis les réglages de la 2.x (`text_scale` en %, `offset_y` en px).
    pub fn from_settings(text_scale: i64, offset_y: i64) -> Adjust {
        Adjust { scale: text_scale.clamp(60, 180) as f32 / 100.0, offset_y: offset_y.clamp(-300, 300) as f32 }
    }

    /// Agrandit et décale le texte d'une liste d'affichage. La bande grandit depuis son bord le
    /// plus proche du bord de l'image (une bande en bas reste en bas).
    pub fn apply(&self, list: &mut DisplayList) {
        if *self == Adjust::default() || list.items.is_empty() {
            return;
        }
        let [x, y, w, h] = list.stage;
        let middle = y + h / 2.0;
        let anchor_y = if middle > list.height * 0.6 {
            y + h
        } else if middle < list.height * 0.4 {
            y
        } else {
            middle
        };
        let mut group = po_layout::Group::plain(std::mem::take(&mut list.items));
        group.scale = self.scale;
        group.origin = [x + w / 2.0, anchor_y];
        group.dy = self.offset_y * list.height / 1080.0;
        list.items = vec![Item::Group(group)];
    }
}

/// Un lower third et son animation : il entre (`shown`) ou sort depuis `since`.
#[derive(Debug, Clone, PartialEq)]
pub struct Overlay {
    pub style: LowerThirdStyle,
    pub text: LowerThirdText,
    pub shown: bool,
    pub since: Instant,
}

/// L'état d'un habillage à un instant : ses éléments, et quand le redessiner.
pub struct OverlayFrame {
    pub items: Vec<Item>,
    /// `Some(délai)` : l'habillage bouge (ou sortira de lui-même) ; `None` : il est immobile.
    pub next: Option<Duration>,
}

/// Une image à 30 images par seconde pendant les animations.
const ANIMATION_TICK: Duration = Duration::from_millis(33);

impl Overlay {
    /// L'habillage à l'instant `now`, mis en page pour `width` × `height`.
    pub fn frame(&self, fonts: &mut Fonts, width: f32, height: f32, now: Instant) -> OverlayFrame {
        let graphic = layout_lower_third(fonts, &self.text, &self.style, width, height);
        let motion = &self.style.motion;
        let duration = Duration::from_millis(u64::from(motion.duration_ms.max(1)));
        let elapsed = now.saturating_duration_since(self.since);
        let progress = |d: Duration| (d.as_secs_f32() / duration.as_secs_f32()).clamp(0.0, 1.0);
        if !self.shown {
            return if elapsed < duration {
                OverlayFrame {
                    items: graphic_frame(&graphic, motion, progress(elapsed), false),
                    next: Some(ANIMATION_TICK),
                }
            } else {
                OverlayFrame { items: Vec::new(), next: None }
            };
        }
        if elapsed < duration {
            return OverlayFrame {
                items: graphic_frame(&graphic, motion, progress(elapsed), true),
                next: Some(ANIMATION_TICK),
            };
        }
        // Affiché : jusqu'au masquage, ou pendant la durée choisie, puis il sort de lui-même.
        if self.style.hold_ms == 0 {
            return OverlayFrame { items: graphic.items(), next: None };
        }
        let hold = Duration::from_millis(u64::from(self.style.hold_ms));
        if elapsed < duration + hold {
            return OverlayFrame { items: graphic.items(), next: Some(duration + hold - elapsed) };
        }
        let out = elapsed - duration - hold;
        if out < duration {
            OverlayFrame { items: graphic_frame(&graphic, motion, progress(out), false), next: Some(ANIMATION_TICK) }
        } else {
            OverlayFrame { items: Vec::new(), next: None }
        }
    }
}

/// Ce qui est au direct.
#[derive(Debug, Clone)]
pub struct Program {
    /// Augmente à chaque slide mis au direct.
    pub seq: u64,
    pub slide: Slide,
    pub context: Context,
    /// Quand le slide est passé au direct.
    pub at: Instant,
}

impl Default for Program {
    fn default() -> Self {
        Program {
            seq: 0,
            slide: Slide::new("", "", SlideSource::Custom),
            context: Context::default(),
            at: Instant::now(),
        }
    }
}

impl Program {
    /// Deux états donnent-ils la même image sur un écran de ce genre ?
    fn same_image(&self, other: &Program, kind: ScreenKind) -> bool {
        let (a, b) = (&self.context, &other.context);
        self.seq == other.seq
            && a.hidden == b.hidden
            && match kind {
                ScreenKind::Room => a.design == b.design,
                ScreenKind::Broadcast => a.broadcast == b.broadcast && a.lower_third == b.lower_third,
                ScreenKind::Subtitles => a.subtitle == b.subtitle,
                ScreenKind::Stage => a.next == b.next && a.clock == b.clock && a.status == b.status,
            }
    }
}

/// Un fichier de police servi aux navigateurs.
struct FontFace {
    family: String,
    weight: u16,
    italic: bool,
    path: std::path::PathBuf,
}

/// L'état partagé entre Project-On et les écrans connectés.
pub struct Hub {
    program: watch::Sender<Arc<Program>>,
    fonts: Mutex<Fonts>,
    /// Sonde la luminosité des fonds (couleur de l'identification).
    renderer: Mutex<Renderer>,
    faces: Vec<FontFace>,
    /// Les images de fond servies aux navigateurs (`/images/{n}`) : seulement celles des slides
    /// mis au direct, jamais un chemin choisi par un navigateur.
    images: Mutex<Vec<std::path::PathBuf>>,
    registry: Registry,
    access: Mutex<Access>,
}

impl Hub {
    /// `fonts` : les polices de la mise en page, les mêmes que celles servies aux navigateurs.
    pub fn new(fonts: Fonts) -> Arc<Self> {
        let faces = fonts
            .system
            .db()
            .faces()
            .filter_map(|face| {
                let path = match &face.source {
                    cosmic_text_fontdb::Source::File(path) | cosmic_text_fontdb::Source::SharedFile(path, _) => {
                        path.clone()
                    }
                    cosmic_text_fontdb::Source::Binary(_) => return None,
                };
                Some(FontFace {
                    family: face.families.first()?.0.clone(),
                    weight: face.weight.0,
                    italic: face.style != cosmic_text_fontdb::Style::Normal,
                    path,
                })
            })
            .collect();
        let (program, _) = watch::channel(Arc::new(Program::default()));
        Arc::new(Hub {
            program,
            fonts: Mutex::new(fonts),
            renderer: Mutex::new(Renderer::new()),
            faces,
            images: Mutex::new(Vec::new()),
            registry: Registry::default(),
            access: Mutex::new(Access::default()),
        })
    }

    /// Met un slide au direct avec ce design de salle : tous les écrans le reçoivent. Renvoie son
    /// numéro.
    pub fn publish(&self, slide: Slide, design: RoomDesign) -> u64 {
        let mut context = self.program.borrow().context.clone();
        context.design = design;
        self.update(Some(slide), context)
    }

    /// Met à jour ce que montrent les écrans : un nouveau slide au direct (`Some`), ou seulement le
    /// contexte (texte masqué, slide suivant, heure…). Rien n'est envoyé si rien ne change ; la
    /// régie peut donc l'appeler à chaque image. Le slide déjà au direct, remis au direct (la
    /// projection rouverte), ne rejoue pas de transition. Renvoie le numéro du slide au direct.
    pub fn update(&self, slide: Option<Slide>, context: Context) -> u64 {
        let mut seq = 0;
        self.program.send_if_modified(|current| {
            let slide = slide.filter(|s| current.seq == 0 || *s != current.slide);
            if slide.is_none() && current.context == context {
                seq = current.seq;
                return false;
            }
            let mut next = Program::clone(current);
            if let Some(slide) = slide {
                next.seq += 1;
                next.slide = slide;
                next.at = Instant::now();
            }
            next.context = context;
            seq = next.seq;
            *current = Arc::new(next);
            true
        });
        seq
    }

    /// Ce qui est au direct.
    pub fn program(&self) -> Arc<Program> {
        self.program.borrow().clone()
    }

    /// Prévenu à chaque changement du direct (sorties NDI et HDMI).
    pub fn subscribe(&self) -> watch::Receiver<Arc<Program>> {
        self.program.subscribe()
    }

    /// Une image PNG d'une liste d'affichage mise en page avec les polices des écrans (les écrans de
    /// l'église, projetés comme une image, à la manière de la 2.8).
    pub fn render_png(
        &self,
        width: u32,
        height: u32,
        layout: impl FnOnce(&mut Fonts) -> DisplayList,
    ) -> Result<Vec<u8>, String> {
        let mut fonts = self.fonts.lock().unwrap_or_else(|e| e.into_inner());
        let list = layout(&mut fonts);
        let mut renderer = self.renderer.lock().unwrap_or_else(|e| e.into_inner());
        let pixmap = renderer.render(&mut fonts, &list, width, height).map_err(|e| e.to_string())?;
        po_render::encode_png(&pixmap).map_err(|e| e.to_string())
    }

    /// Une image RVBA prémultipliée de `width` × `height` d'une liste d'affichage mise en page avec
    /// les polices des écrans (l'aperçu de l'image de citation, sa copie dans le presse-papiers).
    pub fn render_list_rgba(
        &self,
        width: u32,
        height: u32,
        layout: impl FnOnce(&mut Fonts) -> DisplayList,
    ) -> Result<Vec<u8>, String> {
        let mut fonts = self.fonts.lock().unwrap_or_else(|e| e.into_inner());
        let list = layout(&mut fonts);
        let mut renderer = self.renderer.lock().unwrap_or_else(|e| e.into_inner());
        renderer.render(&mut fonts, &list, width, height).map(|p| p.data().to_vec()).map_err(|e| e.to_string())
    }

    /// Découpe un texte en sous-titres (pour 1920 × 1080, avec les polices des écrans).
    pub fn subtitle_chunks(&self, text: &str, style: &SubtitleStyle) -> Vec<String> {
        let mut fonts = self.fonts.lock().unwrap_or_else(|e| e.into_inner());
        po_layout::graphics::subtitle_chunks(&mut fonts, text, style)
    }

    /// Le nombre d'écrans connectés.
    pub fn connected(&self) -> usize {
        self.registry.connected()
    }

    /// Les écrans connectés, et ceux qui viennent de se déconnecter.
    pub fn screens(&self) -> Vec<ScreenInfo> {
        let program = self.program();
        self.registry.list(program.seq, program.at)
    }

    /// Change les règles d'accès (jeton du réseau local). Les écrans déjà ouverts restent ouverts.
    pub fn set_access(&self, access: Access) {
        *self.access.lock().unwrap_or_else(|e| e.into_inner()) = access;
    }

    pub fn access(&self) -> Access {
        self.access.lock().unwrap_or_else(|e| e.into_inner()).clone()
    }

    /// Les chemins des images deviennent des adresses `/images/{n}` servies par le serveur.
    fn share_images(&self, items: &mut [Item]) {
        for item in items {
            match item {
                Item::Image { path, .. } => {
                    let mut images = self.images.lock().unwrap_or_else(|e| e.into_inner());
                    let file = std::path::PathBuf::from(&*path);
                    let n = images.iter().position(|p| *p == file).unwrap_or_else(|| {
                        images.push(file);
                        images.len() - 1
                    });
                    *path = format!("/images/{n}");
                }
                Item::Group(group) => self.share_images(&mut group.items),
                _ => {}
            }
        }
    }

    /// La liste d'affichage d'un écran de ce genre et de cette taille.
    pub fn layout(&self, program: &Program, kind: ScreenKind, width: f32, height: f32) -> DisplayList {
        self.layout_at(program, kind, width, height, Instant::now()).0
    }

    /// La liste d'affichage à l'instant `now` (le lower third peut être en mouvement), et quand la
    /// redessiner.
    pub fn layout_at(
        &self,
        program: &Program,
        kind: ScreenKind,
        width: f32,
        height: f32,
        now: Instant,
    ) -> (DisplayList, Option<Duration>) {
        // Un fil qui a paniqué en tenant le verrou ne doit pas éteindre les écrans.
        let mut fonts = self.fonts.lock().unwrap_or_else(|e| e.into_inner());
        let c = &program.context;
        let mut next = None;
        let list = match kind {
            ScreenKind::Room => {
                let mut renderer = self.renderer.lock().unwrap_or_else(|e| e.into_inner());
                let mut probe = |list: &DisplayList, zone: [f32; 4]| renderer.backdrop_luminance(list, zone);
                layout_room(&mut fonts, &program.slide, &c.design, width, height, &mut probe)
            }
            ScreenKind::Broadcast => {
                let mut list = match &c.broadcast {
                    Look::Band(band) => layout_band(&mut fonts, &program.slide, band, width, height),
                    Look::Slide(design) => {
                        let mut renderer = self.renderer.lock().unwrap_or_else(|e| e.into_inner());
                        let mut probe = |list: &DisplayList, zone: [f32; 4]| renderer.backdrop_luminance(list, zone);
                        let mut list = layout_room(&mut fonts, &program.slide, design, width, height, &mut probe);
                        // Le texte seul, posé sur la vidéo : le fond du design s'efface. Une image
                        // seule (une affiche, une photo) reste visible.
                        let image_alone = program.slide.background.is_some() && list.items.is_empty();
                        if !image_alone {
                            list.backdrop.clear();
                        }
                        list.background = Rgba::TRANSPARENT;
                        list
                    }
                };
                if let Some(overlay) = &c.lower_third {
                    let frame = overlay.frame(&mut fonts, width, height, now);
                    list.overlay = frame.items;
                    next = frame.next;
                }
                list
            }
            ScreenKind::Subtitles => {
                let mut list = DisplayList::blank(width, height, Rgba::TRANSPARENT);
                if let Some((style, text)) = &c.subtitle {
                    // La référence du slide au direct, en petit sous le texte.
                    let reference = &program.slide.reference;
                    let graphic = layout_subtitle_with_reference(&mut fonts, text, reference, style, width, height);
                    list.stage = graphic.rect;
                    list.items = graphic.items();
                }
                list
            }
            ScreenKind::Stage => {
                layout_stage(&mut fonts, &program.slide, c.next.as_ref(), &c.clock, &c.status, c.hidden, width, height)
            }
        };
        (list, next)
    }

    /// L'image d'un écran (sortie NDI ou HDMI) : RVBA prémultiplié, `width` × `height`. `background`
    /// remplace le fond (la couleur de clé d'une sortie HDMI) ; `pattern` : la mire. Rend aussi
    /// quand la redessiner.
    pub fn render_rgba(
        &self,
        program: &Program,
        kind: ScreenKind,
        width: u32,
        height: u32,
        background: Option<Rgba>,
        pattern: bool,
    ) -> (Vec<u8>, Option<Duration>) {
        self.render_rgba_adjusted(program, kind, width, height, background, pattern, Adjust::default())
    }

    /// [`Hub::render_rgba`], avec la taille et le décalage du texte d'une sortie HDMI.
    #[allow(clippy::too_many_arguments)]
    pub fn render_rgba_adjusted(
        &self,
        program: &Program,
        kind: ScreenKind,
        width: u32,
        height: u32,
        background: Option<Rgba>,
        pattern: bool,
        adjust: Adjust,
    ) -> (Vec<u8>, Option<Duration>) {
        let (mut list, next) = if pattern {
            (test_pattern(width as f32, height as f32), None)
        } else {
            let (mut list, next) = self.layout_at(program, kind, width as f32, height as f32, Instant::now());
            if kind.transparent() {
                adjust.apply(&mut list);
            }
            (list, next)
        };
        if let Some(color) = background {
            list.background = color;
        }
        let mut fonts = self.fonts.lock().unwrap_or_else(|e| e.into_inner());
        let mut renderer = self.renderer.lock().unwrap_or_else(|e| e.into_inner());
        let pixels = renderer.render(&mut fonts, &list, width, height).map(|p| p.data().to_vec()).unwrap_or_default();
        (pixels, next)
    }

    fn frame(&self, program: &Program, kind: ScreenKind, width: f32, height: f32) -> (String, Option<Duration>) {
        let (mut list, next) = self.layout_at(program, kind, width, height, Instant::now());
        self.share_images(&mut list.backdrop);
        self.share_images(&mut list.items);
        let c = &program.context;
        let (animation, hidden): (Option<Animation>, bool) = match kind {
            ScreenKind::Room => (Some(c.design.animation), c.hidden),
            ScreenKind::Broadcast => (Some(c.broadcast.animation()), c.hidden),
            // Les sous-titres changent sans transition ; masqués, ils ne sont pas envoyés.
            ScreenKind::Subtitles => (None, false),
            // Le retour de scène change sans transition, et montre le texte même masqué.
            ScreenKind::Stage => (None, false),
        };
        let text = serde_json::to_string(&ServerMessage::Frame { seq: program.seq, list, animation, hidden })
            .unwrap_or_default();
        (text, next)
    }

    fn fonts_css(&self) -> String {
        let mut css = String::new();
        for (i, face) in self.faces.iter().enumerate() {
            css.push_str(&format!(
                "@font-face{{font-family:\"{}\";src:url(/polices/{i});font-weight:{};font-style:{};font-display:block}}\n",
                face.family.replace('"', ""),
                face.weight,
                if face.italic { "italic" } else { "normal" },
            ));
        }
        css
    }
}

// fontdb, par cosmic-text (même version que la mise en page).
use po_layout::fontdb as cosmic_text_fontdb;

/// Le serveur en marche. Il s'arrête quand on le lâche, et ferme alors les écrans connectés (ils
/// se reconnectent seuls quand un serveur revient).
pub struct Server {
    pub addr: SocketAddr,
    shutdown: Option<oneshot::Sender<()>>,
    stop_clients: watch::Sender<bool>,
    thread: Option<JoinHandle<()>>,
}

impl Drop for Server {
    fn drop(&mut self) {
        let _ = self.stop_clients.send(true);
        if let Some(tx) = self.shutdown.take() {
            let _ = tx.send(());
        }
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

/// L'état d'un serveur, partagé par ses routes.
#[derive(Clone)]
struct Shared {
    hub: Arc<Hub>,
    stop: watch::Receiver<bool>,
}

/// Démarre le serveur sur `addr` (port 0 : un port libre). Rend la main quand il écoute.
pub fn start(hub: Arc<Hub>, addr: SocketAddr) -> std::io::Result<Server> {
    let runtime =
        tokio::runtime::Builder::new_multi_thread().worker_threads(2).thread_name("po-web").enable_all().build()?;
    // Écoute ouverte ici, de façon synchrone : l'appelant sait aussitôt si le port est pris, et
    // `start` peut être appelée depuis n'importe quel fil, même un fil tokio.
    let listener = std::net::TcpListener::bind(addr)?;
    listener.set_nonblocking(true)?;
    let addr = listener.local_addr()?;
    let (shutdown, stop) = oneshot::channel::<()>();
    let (stop_clients, stop_rx) = watch::channel(false);
    let shared = Shared { hub, stop: stop_rx };
    let app = Router::new()
        .route("/", get(index))
        .route("/ecran/{screen}", get(screen_page))
        .route("/ecran.js", get(screen_js))
        .route("/polices.css", get(fonts_css))
        .route("/logo.png", get(logo))
        .route("/favicon.ico", get(logo))
        .route("/polices/{id}", get(font_file))
        .route("/images/{id}", get(image_file))
        .route("/ws/{screen}", get(ws))
        // Les adresses de la 2.8 : la source navigateur d'OBS réglée sur `/obs` continue de marcher.
        .route("/obs", get(obs))
        .route("/obs.html", get(obs))
        .route("/presentation/obs", get(obs))
        .route("/presentation/obs.html", get(obs))
        .route("/slide.json", get(slide_json))
        .route("/presentation/slide.json", get(slide_json))
        .layer(axum::middleware::from_fn_with_state(shared.clone(), guard))
        .with_state(shared);
    let thread = std::thread::Builder::new().name("po-web".into()).spawn(move || {
        runtime.block_on(async move {
            let Ok(listener) = tokio::net::TcpListener::from_std(listener) else { return };
            let _ = axum::serve(listener, app.into_make_service_with_connect_info::<SocketAddr>())
                .with_graceful_shutdown(async move {
                    let _ = stop.await;
                })
                .await;
        });
    })?;
    Ok(Server { addr, shutdown: Some(shutdown), stop_clients, thread: Some(thread) })
}

/// Démarre le serveur sur `port`, ou sur l'un des neuf suivants s'il est pris.
pub fn start_near(hub: Arc<Hub>, ip: IpAddr, port: u16) -> std::io::Result<Server> {
    let mut last = None;
    for p in port..port.saturating_add(10) {
        match start(hub.clone(), SocketAddr::new(ip, p)) {
            Ok(server) => return Ok(server),
            Err(e) => last = Some(e),
        }
    }
    Err(last.unwrap_or_else(|| std::io::Error::other("aucun port libre")))
}

/// Refuse les appareils du réseau sans le jeton ; dépose le jeton en cookie quand il vient de
/// l'adresse, pour les polices, les images et le WebSocket de la page.
async fn guard(
    State(shared): State<Shared>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    request: Request,
    next: Next,
) -> Response {
    let access = shared.hub.access();
    let query = request.uri().query().map(str::to_string);
    let cookie = request.headers().get(header::COOKIE).and_then(|v| v.to_str().ok()).map(str::to_string);
    if !access.allows(peer.ip(), query.as_deref(), cookie.as_deref()) {
        return (StatusCode::FORBIDDEN, Html(FORBIDDEN)).into_response();
    }
    let mut response = next.run(request).await;
    if let (Some(token), Some(q)) = (&access.token, query.as_deref())
        && access::param(q, "t") == Some(token.as_str())
        && let Ok(value) = HeaderValue::from_str(&format!("{COOKIE}={token}; Path=/; SameSite=Strict; HttpOnly"))
    {
        response.headers_mut().append(header::SET_COOKIE, value);
    }
    response
}

const FORBIDDEN: &str = "<!doctype html><meta charset=utf-8><title>Project-On</title>\
<body style=\"font:16px system-ui;background:#0b1217;color:#f2f0e9;display:grid;place-items:center;height:100vh;margin:0\">\
<p>Adresse incomplète : scannez le QR code affiché dans la régie de Project-On (bouton « Web »).</p>";

fn escape(text: &str) -> String {
    text.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;").replace('"', "&quot;")
}

/// La page d'accueil : les écrans proposés, ceux qui sont connectés.
async fn index(State(shared): State<Shared>) -> Html<String> {
    let screens = shared.hub.screens();
    let mut rows = String::new();
    let mut names: Vec<(String, ScreenKind, String)> =
        PRESETS.iter().map(|(name, kind, _, about)| (name.to_string(), *kind, about.to_string())).collect();
    for s in &screens {
        if !names.iter().any(|(n, _, _)| *n == s.name) {
            names.push((s.name.clone(), s.kind, format!("Un écran « {} » de plus.", s.kind.label())));
        }
    }
    for (name, kind, about) in names {
        let live = screens.iter().filter(|s| s.name == name && s.dropped.is_none()).count();
        let badge = match live {
            0 => String::new(),
            1 => "<b>1 connecté</b>".to_string(),
            n => format!("<b>{n} connectés</b>"),
        };
        rows.push_str(&format!(
            "<a href=\"/ecran/{href}\"><div><strong>{label}</strong><small>{about}</small></div><span>/ecran/{name}{badge}</span></a>",
            href = escape(&name),
            label = escape(kind.label()),
            about = escape(&about),
            name = escape(&name),
        ));
    }
    Html(include_str!("../web/index.html").replace("{{ROWS}}", &rows))
}

async fn screen_page(Path(screen): Path<String>) -> Html<String> {
    let kind = ScreenKind::of(&screen);
    let class = if kind.transparent() { "transparent" } else { "" };
    Html(
        include_str!("../web/ecran.html")
            .replace("{{TITLE}}", &escape(&format!("{} — Project-On", kind.label())))
            .replace("{{CLASS}}", class),
    )
}

async fn screen_js() -> Response {
    let js = include_str!("../web/ecran.js").replace("__PROTOCOL__", &PROTOCOL_VERSION.to_string());
    ([(header::CONTENT_TYPE, "text/javascript; charset=utf-8"), (header::CACHE_CONTROL, "no-cache")], js)
        .into_response()
}

/// `/obs` (2.8) : la diffusion, avec les mêmes paramètres.
async fn obs(RawQuery(query): RawQuery) -> Redirect {
    match query.filter(|q| !q.is_empty()) {
        Some(q) => Redirect::temporary(&format!("/ecran/diffusion?{q}")),
        None => Redirect::temporary("/ecran/diffusion"),
    }
}

/// `/slide.json` (2.8) : le slide au direct, pour les intégrations écrites pour la 2.8.
async fn slide_json(State(shared): State<Shared>) -> Response {
    let program = shared.hub.program();
    let source = match program.slide.source {
        SlideSource::Bible => "bible",
        SlideSource::Hymn => "hymn",
        SlideSource::Sermon => "sermon",
        SlideSource::Expose => "expose",
        SlideSource::Brochure => "brochure",
        SlideSource::Book => "book",
        SlideSource::Custom => "custom",
    };
    let body = serde_json::json!({
        "text": program.slide.text,
        "reference": program.slide.reference,
        "source": source,
        "hidden": program.context.hidden || program.seq == 0,
        "seq": program.seq,
    });
    ([(header::CONTENT_TYPE, "application/json"), (header::CACHE_CONTROL, "no-store")], body.to_string())
        .into_response()
}

/// Le logo de Project-On (icône des onglets et en-tête de la page d'accueil).
const LOGO_PNG: &[u8] = include_bytes!("../../../../assets/logo/app icon.png");

async fn logo() -> Response {
    ([(header::CONTENT_TYPE, "image/png"), (header::CACHE_CONTROL, "max-age=86400")], LOGO_PNG).into_response()
}

async fn fonts_css(State(shared): State<Shared>) -> Response {
    ([(header::CONTENT_TYPE, "text/css; charset=utf-8")], shared.hub.fonts_css()).into_response()
}

async fn font_file(State(shared): State<Shared>, Path(id): Path<usize>) -> Response {
    let Some(face) = shared.hub.faces.get(id) else { return StatusCode::NOT_FOUND.into_response() };
    match tokio::fs::read(&face.path).await {
        Ok(bytes) => {
            ([(header::CONTENT_TYPE, "font/ttf"), (header::CACHE_CONTROL, "max-age=86400")], bytes).into_response()
        }
        Err(_) => StatusCode::NOT_FOUND.into_response(),
    }
}

async fn image_file(State(shared): State<Shared>, Path(id): Path<usize>) -> Response {
    let Some(path) = shared.hub.images.lock().unwrap_or_else(|e| e.into_inner()).get(id).cloned() else {
        return StatusCode::NOT_FOUND.into_response();
    };
    let kind = match path.extension().map(|e| e.to_string_lossy().to_lowercase()).as_deref() {
        Some("png") => "image/png",
        Some("jpg" | "jpeg") => "image/jpeg",
        Some("webp") => "image/webp",
        _ => "application/octet-stream",
    };
    match tokio::fs::read(&path).await {
        Ok(bytes) => ([(header::CONTENT_TYPE, kind), (header::CACHE_CONTROL, "max-age=3600")], bytes).into_response(),
        Err(_) => StatusCode::NOT_FOUND.into_response(),
    }
}

async fn ws(
    ws: WebSocketUpgrade,
    Path(screen): Path<String>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    State(shared): State<Shared>,
) -> Response {
    let screen: String = screen.chars().filter(|c| !c.is_control()).take(40).collect();
    ws.on_upgrade(move |socket| client(socket, screen, peer, shared))
}

/// Retire un écran du registre quand sa connexion se termine, quelle qu'en soit la raison.
struct Leave(Arc<Hub>, u64);

impl Drop for Leave {
    fn drop(&mut self) {
        self.0.registry.leave(self.1);
    }
}

async fn client(socket: WebSocket, screen: String, peer: SocketAddr, shared: Shared) {
    let Shared { hub, mut stop } = shared;
    let kind = ScreenKind::of(&screen);
    let id = hub.registry.next_id();
    hub.registry.join(id, &screen, peer);
    let _leave = Leave(hub.clone(), id);
    let (mut tx, mut rx) = socket.split();
    let hello = ServerMessage::Hello {
        version: PROTOCOL_VERSION,
        screen,
        kind: kind.slug().into(),
        transparent: kind.transparent(),
    };
    if tx.send(Message::Text(serde_json::to_string(&hello).unwrap_or_default().into())).await.is_err() {
        return;
    }
    let mut program = hub.program.subscribe();
    let mut viewport: Option<(f32, f32)> = None;
    // Ce que l'écran montre déjà : un changement qui ne le concerne pas (l'heure pour la salle) ne
    // lui renvoie rien.
    let mut shown: Option<(Arc<Program>, (f32, f32))> = None;
    let mut last_text = String::new();
    // Le prochain redessin d'un habillage en mouvement.
    let mut redraw: Option<tokio::time::Instant> = None;
    let mut ping = tokio::time::interval(Duration::from_secs(5));
    loop {
        let animate = async {
            match redraw {
                Some(at) => tokio::time::sleep_until(at).await,
                None => std::future::pending().await,
            }
        };
        let mut forced = false;
        let wanted = tokio::select! {
            _ = animate => {
                redraw = None;
                forced = true;
                true
            }
            incoming = rx.next() => match incoming {
                Some(Ok(Message::Text(text))) => match serde_json::from_str::<ClientMessage>(&text) {
                    Ok(ClientMessage::Hello { width, height }) => {
                        // Une taille absurde (fenêtre cachée) donnerait une mise en page illisible.
                        let size = if width < 100.0 || height < 100.0 || !width.is_finite() || !height.is_finite() {
                            (1920.0, 1080.0)
                        } else {
                            (width.min(8192.0), height.min(8192.0))
                        };
                        viewport = Some(size);
                        hub.registry.touch(id, |s| (s.width, s.height) = size);
                        shown = None;
                        true
                    }
                    Ok(ClientMessage::Ack { seq }) => {
                        hub.registry.touch(id, |s| s.acked = s.acked.max(seq));
                        false
                    }
                    Ok(ClientMessage::Pong) => {
                        hub.registry.touch(id, |_| {});
                        false
                    }
                    // Un message inconnu (une tentative de commande) est ignoré.
                    Err(_) => false,
                },
                Some(Ok(Message::Close(_))) | None | Some(Err(_)) => break,
                Some(Ok(_)) => false,
            },
            changed = program.changed() => {
                if changed.is_err() {
                    break;
                }
                true
            }
            _ = stop.changed() => {
                // Le serveur s'arrête (changement d'accès, fermeture) : l'écran se reconnectera.
                let _ = tx.send(Message::Close(Some(CloseFrame { code: 1012, reason: "redémarrage".into() }))).await;
                break;
            }
            _ = ping.tick() => {
                if tx.send(Message::Text(serde_json::to_string(&ServerMessage::Ping).unwrap_or_default().into())).await.is_err() {
                    break;
                }
                false
            }
        };
        let Some(size) = viewport else { continue };
        if !wanted {
            continue;
        }
        let current = program.borrow_and_update().clone();
        if !forced
            && let Some((before, at)) = &shown
            && *at == size
            && before.same_image(&current, kind)
        {
            continue;
        }
        // La mise en page (quelques millisecondes) ne bloque pas les autres écrans.
        let (text, next) = {
            let hub = hub.clone();
            let current = current.clone();
            tokio::task::spawn_blocking(move || hub.frame(&current, kind, size.0, size.1)).await.unwrap_or_default()
        };
        redraw = next.map(|d| tokio::time::Instant::now() + d);
        shown = Some((current, size));
        if text.is_empty() || text == last_text {
            continue;
        }
        if tx.send(Message::Text(text.clone().into())).await.is_err() {
            break;
        }
        last_text = text;
    }
}

#[cfg(test)]
mod tests;
