//! Le serveur HTTP + WebSocket (axum), sur son propre fil avec un petit runtime tokio.

use std::net::SocketAddr;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::Duration;

use axum::Router;
use axum::extract::ws::{Message, WebSocket, WebSocketUpgrade};
use axum::extract::{Path, State};
use axum::http::{StatusCode, header};
use axum::response::{Html, IntoResponse, Response};
use axum::routing::get;
use futures_util::{SinkExt, StreamExt};
use po_design::{RoomDesign, SlideSource};
use po_layout::{DisplayList, Fonts, Item, Slide, layout_room};
use po_render::Renderer;
use tokio::sync::{oneshot, watch};

use crate::protocol::{ClientMessage, PROTOCOL_VERSION, ServerMessage};

/// Ce qui est au direct.
#[derive(Debug, Clone)]
pub struct Program {
    pub seq: u64,
    pub slide: Slide,
    pub design: RoomDesign,
}

impl Default for Program {
    fn default() -> Self {
        Program { seq: 0, slide: Slide::new("", "", SlideSource::Custom), design: RoomDesign::default() }
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
    clients: AtomicUsize,
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
            clients: AtomicUsize::new(0),
        })
    }

    /// Met un slide au direct : tous les écrans le reçoivent. Renvoie son numéro.
    pub fn publish(&self, slide: Slide, design: RoomDesign) -> u64 {
        let seq = self.program.borrow().seq + 1;
        self.program.send_replace(Arc::new(Program { seq, slide, design }));
        seq
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

    /// Le nombre d'écrans connectés.
    pub fn connected(&self) -> usize {
        self.clients.load(Ordering::Relaxed)
    }

    fn frame(&self, program: &Program, width: f32, height: f32) -> String {
        let mut list = {
            // Un fil qui a paniqué en tenant le verrou ne doit pas éteindre les écrans.
            let mut fonts = self.fonts.lock().unwrap_or_else(|e| e.into_inner());
            let mut renderer = self.renderer.lock().unwrap_or_else(|e| e.into_inner());
            let mut probe = |list: &DisplayList, zone: [f32; 4]| renderer.backdrop_luminance(list, zone);
            layout_room(&mut fonts, &program.slide, &program.design, width, height, &mut probe)
        };
        self.share_images(&mut list.backdrop);
        self.share_images(&mut list.items);
        serde_json::to_string(&ServerMessage::Frame { seq: program.seq, list }).unwrap_or_default()
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

/// Le serveur en marche. Il s'arrête quand on le lâche.
pub struct Server {
    pub addr: SocketAddr,
    shutdown: Option<oneshot::Sender<()>>,
    thread: Option<JoinHandle<()>>,
}

impl Drop for Server {
    fn drop(&mut self) {
        if let Some(tx) = self.shutdown.take() {
            let _ = tx.send(());
        }
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
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
    let app = Router::new()
        .route("/", get(index))
        .route("/ecran/{screen}", get(screen_page))
        .route("/ecran.js", get(screen_js))
        .route("/polices.css", get(fonts_css))
        .route("/polices/{id}", get(font_file))
        .route("/images/{id}", get(image_file))
        .route("/ws/{screen}", get(ws))
        .with_state(hub);
    let thread = std::thread::Builder::new().name("po-web".into()).spawn(move || {
        runtime.block_on(async move {
            let Ok(listener) = tokio::net::TcpListener::from_std(listener) else { return };
            let _ = axum::serve(listener, app)
                .with_graceful_shutdown(async move {
                    let _ = stop.await;
                })
                .await;
        });
    })?;
    Ok(Server { addr, shutdown: Some(shutdown), thread: Some(thread) })
}

async fn index() -> Html<&'static str> {
    Html(include_str!("../web/index.html"))
}

async fn screen_page() -> Html<&'static str> {
    Html(include_str!("../web/ecran.html"))
}

async fn screen_js() -> Response {
    ([(header::CONTENT_TYPE, "text/javascript; charset=utf-8")], include_str!("../web/ecran.js")).into_response()
}

async fn fonts_css(State(hub): State<Arc<Hub>>) -> Response {
    ([(header::CONTENT_TYPE, "text/css; charset=utf-8")], hub.fonts_css()).into_response()
}

async fn font_file(State(hub): State<Arc<Hub>>, Path(id): Path<usize>) -> Response {
    let Some(face) = hub.faces.get(id) else { return StatusCode::NOT_FOUND.into_response() };
    match tokio::fs::read(&face.path).await {
        Ok(bytes) => {
            ([(header::CONTENT_TYPE, "font/ttf"), (header::CACHE_CONTROL, "max-age=86400")], bytes).into_response()
        }
        Err(_) => StatusCode::NOT_FOUND.into_response(),
    }
}

async fn image_file(State(hub): State<Arc<Hub>>, Path(id): Path<usize>) -> Response {
    let Some(path) = hub.images.lock().unwrap_or_else(|e| e.into_inner()).get(id).cloned() else {
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

async fn ws(ws: WebSocketUpgrade, Path(screen): Path<String>, State(hub): State<Arc<Hub>>) -> Response {
    ws.on_upgrade(move |socket| client(socket, screen, hub))
}

/// Compte un écran connecté tant qu'il vit.
struct Connected(Arc<Hub>);

impl Drop for Connected {
    fn drop(&mut self) {
        self.0.clients.fetch_sub(1, Ordering::Relaxed);
    }
}

async fn client(socket: WebSocket, screen: String, hub: Arc<Hub>) {
    hub.clients.fetch_add(1, Ordering::Relaxed);
    let _connected = Connected(hub.clone());
    let (mut tx, mut rx) = socket.split();
    let hello = ServerMessage::Hello { version: PROTOCOL_VERSION, screen };
    if tx.send(Message::Text(serde_json::to_string(&hello).unwrap_or_default().into())).await.is_err() {
        return;
    }
    let mut program = hub.program.subscribe();
    let mut viewport: Option<(f32, f32)> = None;
    let mut ping = tokio::time::interval(Duration::from_secs(5));
    loop {
        let outgoing = tokio::select! {
            incoming = rx.next() => match incoming {
                Some(Ok(Message::Text(text))) => match serde_json::from_str::<ClientMessage>(&text) {
                    Ok(ClientMessage::Hello { width, height }) => {
                        viewport = Some((width.clamp(16.0, 8192.0), height.clamp(16.0, 8192.0)));
                        let current = program.borrow_and_update().clone();
                        viewport.map(|(w, h)| hub.frame(&current, w, h))
                    }
                    // Accusés de réception et pongs : rien à faire ; un message inconnu est ignoré.
                    _ => None,
                },
                Some(Ok(Message::Close(_))) | None | Some(Err(_)) => break,
                Some(Ok(_)) => None,
            },
            changed = program.changed() => {
                if changed.is_err() {
                    break;
                }
                let current = program.borrow_and_update().clone();
                viewport.map(|(w, h)| hub.frame(&current, w, h))
            }
            _ = ping.tick() => Some(serde_json::to_string(&ServerMessage::Ping).unwrap_or_default()),
        };
        if let Some(text) = outgoing
            && tx.send(Message::Text(text.into())).await.is_err()
        {
            break;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Instant;
    use tokio_tungstenite::tungstenite::Message as WsMessage;

    fn hub() -> Arc<Hub> {
        let dir = po_layout::bundled_fonts_dir();
        Hub::new(Fonts::from_files(&[dir.join("Passion One/PassionOne-Bold.ttf")]))
    }

    async fn next_frame<S>(stream: &mut S) -> (u64, po_layout::DisplayList)
    where
        S: StreamExt<Item = Result<WsMessage, tokio_tungstenite::tungstenite::Error>> + Unpin,
    {
        loop {
            let msg = stream.next().await.unwrap().unwrap();
            if let WsMessage::Text(text) = msg
                && let Ok(ServerMessage::Frame { seq, list }) = serde_json::from_str(&text)
            {
                return (seq, list);
            }
        }
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn screens_receive_the_live_slide_at_their_own_size_and_after_reconnecting() {
        let hub = hub();
        let server = start(hub.clone(), "127.0.0.1:0".parse().unwrap()).unwrap();
        let url = format!("ws://{}/ws/salle", server.addr);
        hub.publish(Slide::new("Premier", "", SlideSource::Custom), RoomDesign::default());

        // Deux écrans de tailles différentes.
        let (mut wide, _) = tokio_tungstenite::connect_async(&url).await.unwrap();
        let (mut square, _) = tokio_tungstenite::connect_async(&url).await.unwrap();
        wide.send(WsMessage::Text(r#"{"type":"hello","width":1920,"height":1080}"#.into())).await.unwrap();
        square.send(WsMessage::Text(r#"{"type":"hello","width":1024,"height":768}"#.into())).await.unwrap();
        let (seq, list) = next_frame(&mut wide).await;
        assert_eq!((seq, list.width, list.height), (1, 1920.0, 1080.0));
        let (_, list) = next_frame(&mut square).await;
        assert_eq!((list.width, list.height), (1024.0, 768.0));
        assert_eq!(hub.connected(), 2);

        // Un changement du direct arrive vite chez les deux.
        let sent = Instant::now();
        let seq = hub.publish(Slide::new("Deuxième", "Jean 3:16", SlideSource::Bible), RoomDesign::default());
        let (got, list) = next_frame(&mut wide).await;
        assert_eq!(got, seq);
        assert!(list.text_lines().any(|l| l.text == "Deuxième"));
        assert_eq!(next_frame(&mut square).await.0, seq);
        assert!(sent.elapsed() < Duration::from_millis(500));

        // Coupure puis reconnexion : l'état courant revient aussitôt.
        drop(square);
        let (mut again, _) = tokio_tungstenite::connect_async(&url).await.unwrap();
        again.send(WsMessage::Text(r#"{"type":"hello","width":800,"height":600}"#.into())).await.unwrap();
        assert_eq!(next_frame(&mut again).await.0, seq);

        // Une « commande » envoyée par un écran ne change rien.
        again.send(WsMessage::Text(r#"{"type":"take"}"#.into())).await.unwrap();
        hub.publish(Slide::new("Troisième", "", SlideSource::Custom), RoomDesign::default());
        assert_eq!(next_frame(&mut again).await.0, seq + 1);
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn serves_the_screen_page_and_fonts() {
        let server = start(hub(), "127.0.0.1:0".parse().unwrap()).unwrap();
        let get = |path: &str| {
            let addr = server.addr;
            let path = path.to_string();
            async move {
                use tokio::io::{AsyncReadExt, AsyncWriteExt};
                let mut s = tokio::net::TcpStream::connect(addr).await.unwrap();
                s.write_all(format!("GET {path} HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n").as_bytes())
                    .await
                    .unwrap();
                let mut out = Vec::new();
                s.read_to_end(&mut out).await.unwrap();
                String::from_utf8_lossy(&out).to_string()
            }
        };
        assert!(get("/ecran/salle").await.contains("ecran.js"));
        assert!(get("/polices.css").await.contains("Passion One"));
        assert!(get("/polices/0").await.starts_with("HTTP/1.1 200"));
        assert!(get("/polices/99").await.starts_with("HTTP/1.1 404"));
    }
}
