//! Les essais du serveur, avec de vrais clients WebSocket et HTTP.

use super::*;
use crate::screens::ScreenState;
use std::time::Instant;
use tokio_tungstenite::tungstenite::Message as WsMessage;

type Socket = tokio_tungstenite::WebSocketStream<tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>>;

fn hub() -> Arc<Hub> {
    let dir = po_layout::bundled_fonts_dir();
    Hub::new(Fonts::from_files(&[dir.join("Passion One/PassionOne-Bold.ttf")]))
}

/// Le prochain message utile (sans les pings).
async fn next_message(stream: &mut Socket) -> ServerMessage {
    loop {
        let msg = tokio::time::timeout(Duration::from_secs(10), stream.next()).await.unwrap().unwrap().unwrap();
        if let WsMessage::Text(text) = msg {
            let parsed: ServerMessage = serde_json::from_str(&text).unwrap();
            if parsed != ServerMessage::Ping {
                return parsed;
            }
        }
    }
}

struct Frame {
    seq: u64,
    list: DisplayList,
    animation: Option<Animation>,
    hidden: bool,
}

async fn next_frame(stream: &mut Socket) -> Frame {
    loop {
        if let ServerMessage::Frame { seq, list, animation, hidden } = next_message(stream).await {
            return Frame { seq, list, animation, hidden };
        }
    }
}

/// Rien d'autre qu'un ping pendant `wait`.
async fn quiet(stream: &mut Socket, wait: Duration) -> bool {
    let deadline = tokio::time::Instant::now() + wait;
    loop {
        match tokio::time::timeout_at(deadline, stream.next()).await {
            Err(_) => return true,
            Ok(Some(Ok(WsMessage::Text(text)))) => {
                if serde_json::from_str::<ServerMessage>(&text).unwrap() != ServerMessage::Ping {
                    return false;
                }
            }
            Ok(_) => {}
        }
    }
}

async fn open(addr: SocketAddr, screen: &str, width: u32, height: u32) -> (Socket, ServerMessage) {
    let (mut socket, _) = tokio_tungstenite::connect_async(format!("ws://{addr}/ws/{screen}")).await.unwrap();
    let hello = next_message(&mut socket).await;
    socket
        .send(WsMessage::Text(format!(r#"{{"type":"hello","width":{width},"height":{height}}}"#).into()))
        .await
        .unwrap();
    (socket, hello)
}

async fn get(addr: SocketAddr, path: &str, cookie: Option<&str>) -> String {
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    let mut s = tokio::net::TcpStream::connect(addr).await.unwrap();
    let cookie = cookie.map(|c| format!("Cookie: {c}\r\n")).unwrap_or_default();
    s.write_all(format!("GET {path} HTTP/1.1\r\nHost: x\r\n{cookie}Connection: close\r\n\r\n").as_bytes())
        .await
        .unwrap();
    let mut out = Vec::new();
    s.read_to_end(&mut out).await.unwrap();
    String::from_utf8_lossy(&out).to_string()
}

fn context() -> Context {
    Context { clock: "10:42".into(), ..Context::default() }
}

fn scripture() -> Slide {
    Slide::new("Car Dieu a tant aimé le monde qu'il a donné son Fils unique.", "Jean 3:16", SlideSource::Bible)
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn screens_receive_the_live_slide_at_their_own_size_and_after_reconnecting() {
    let hub = hub();
    let server = start(hub.clone(), "127.0.0.1:0".parse().unwrap()).unwrap();
    hub.publish(Slide::new("Premier", "", SlideSource::Custom), RoomDesign::default());

    // Deux écrans de tailles différentes.
    let (mut wide, hello) = open(server.addr, "salle", 1920, 1080).await;
    assert_eq!(
        hello,
        ServerMessage::Hello {
            version: PROTOCOL_VERSION,
            screen: "salle".into(),
            kind: "salle".into(),
            transparent: false
        }
    );
    let (mut square, _) = open(server.addr, "salle", 1024, 768).await;
    let frame = next_frame(&mut wide).await;
    assert_eq!((frame.seq, frame.list.width, frame.list.height), (1, 1920.0, 1080.0));
    let frame = next_frame(&mut square).await;
    assert_eq!((frame.list.width, frame.list.height), (1024.0, 768.0));
    assert_eq!(hub.connected(), 2);

    // Un changement du direct arrive vite chez les deux.
    let sent = Instant::now();
    let seq = hub.publish(scripture(), RoomDesign::default());
    let frame = next_frame(&mut wide).await;
    assert_eq!(frame.seq, seq);
    assert!(frame.list.text_lines().any(|l| l.text.contains("Dieu")));
    assert_eq!(frame.animation, Some(RoomDesign::default().animation));
    assert_eq!(next_frame(&mut square).await.seq, seq);
    assert!(sent.elapsed() < Duration::from_millis(500));

    // Les accusés de réception remontent dans le registre.
    wide.send(WsMessage::Text(format!(r#"{{"type":"ack","seq":{seq}}}"#).into())).await.unwrap();
    tokio::time::sleep(Duration::from_millis(100)).await;
    let screens = hub.screens();
    assert_eq!(screens.len(), 2);
    let wide_info = screens.iter().find(|s| s.width == 1920.0).unwrap();
    assert_eq!((wide_info.acked, wide_info.kind, wide_info.state), (seq, ScreenKind::Room, ScreenState::Ok));
    assert!(wide_info.local());

    // Coupure : l'écran reste une minute dans la régie, en « déconnecté ».
    drop(square);
    tokio::time::sleep(Duration::from_millis(200)).await;
    assert_eq!(hub.connected(), 1);
    assert!(hub.screens().iter().any(|s| s.state == ScreenState::Dropped));
    // Reprise : l'état courant revient aussitôt, et la trace orange disparaît.
    let (mut again, _) = open(server.addr, "salle", 800, 600).await;
    assert_eq!(next_frame(&mut again).await.seq, seq);
    assert!(hub.screens().iter().all(|s| s.state != ScreenState::Dropped));

    // Une « commande » envoyée par un écran ne change rien.
    again.send(WsMessage::Text(r#"{"type":"take"}"#.into())).await.unwrap();
    hub.publish(Slide::new("Troisième", "", SlideSource::Custom), RoomDesign::default());
    assert_eq!(next_frame(&mut again).await.seq, seq + 1);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn each_kind_of_screen_gets_its_own_image() {
    let hub = hub();
    let server = start(hub.clone(), "127.0.0.1:0".parse().unwrap()).unwrap();
    let next = Slide::new("Et la vie éternelle.", "Jean 3:17", SlideSource::Bible);
    hub.update(Some(scripture()), Context { next: Some(next), status: "Lecture · 4:00 restantes".into(), ..context() });

    let (mut room, _) = open(server.addr, "salle", 1920, 1080).await;
    let (mut broadcast, hello) = open(server.addr, "diffusion", 1920, 1080).await;
    assert!(matches!(hello, ServerMessage::Hello { transparent: true, ref kind, .. } if kind == "diffusion"));
    let (mut subtitles, _) = open(server.addr, "sous-titres", 1920, 1080).await;
    let (mut stage, hello) = open(server.addr, "retour", 1920, 1080).await;
    assert!(matches!(hello, ServerMessage::Hello { transparent: false, ref kind, .. } if kind == "retour"));

    let room = next_frame(&mut room).await;
    assert_eq!(room.list.background.alpha(), 1.0, "la salle a un fond");
    let band = next_frame(&mut broadcast).await;
    assert_eq!(band.list.background.alpha(), 0.0, "la diffusion est transparente");
    assert!(band.list.text_lines().any(|l| l.text == "JEAN 3:16"), "la référence en tête du bandeau");
    assert_eq!(band.animation, Some(Band::default().animation));
    let subs = next_frame(&mut subtitles).await;
    assert_eq!(subs.list.background.alpha(), 0.0);
    assert!(subs.list.text_lines().all(|l| !l.text.contains("JEAN")), "pas de référence en sous-titres");
    let stage_frame = next_frame(&mut stage).await;
    let texts: Vec<String> = stage_frame.list.text_lines().map(|l| l.text.clone()).collect();
    let joined = texts.join(" | ");
    assert!(joined.contains("10:42") && joined.contains("SUIVANT") && joined.contains("Jean 3:17"), "{joined}");
    assert!(joined.contains("Lecture · 4:00 restantes"));
    assert_eq!(stage_frame.animation, None, "le retour de scène change sans transition");
    drop(server);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn hidden_text_and_the_clock_reach_only_the_screens_concerned() {
    let hub = hub();
    let server = start(hub.clone(), "127.0.0.1:0".parse().unwrap()).unwrap();
    let seq = hub.update(Some(scripture()), context());
    let (mut room, _) = open(server.addr, "salle", 1280, 720).await;
    let (mut stage, _) = open(server.addr, "retour", 1280, 720).await;
    assert!(!next_frame(&mut room).await.hidden);
    next_frame(&mut stage).await;

    // L'heure change : seul le retour de scène reçoit une image, sans transition (même `seq`).
    hub.update(None, Context { clock: "10:43".into(), ..context() });
    let frame = next_frame(&mut stage).await;
    assert_eq!(frame.seq, seq);
    assert!(frame.list.text_lines().any(|l| l.text == "10:43"));
    assert!(quiet(&mut room, Duration::from_millis(400)).await, "la salle n'a rien reçu");

    // La même mise à jour deux fois : rien n'est renvoyé.
    hub.update(None, Context { clock: "10:43".into(), ..context() });
    assert!(quiet(&mut stage, Duration::from_millis(300)).await);

    // Texte masqué : la salle le masque ; le retour de scène le montre, avec un bandeau.
    hub.update(None, Context { clock: "10:43".into(), hidden: true, ..context() });
    let frame = next_frame(&mut room).await;
    assert!(frame.hidden && frame.seq == seq);
    let frame = next_frame(&mut stage).await;
    assert!(!frame.hidden);
    assert!(frame.list.text_lines().any(|l| l.text == "TEXTE MASQUÉ"));
    drop(server);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_restarted_server_on_the_same_port_gets_its_screens_back() {
    let hub = hub();
    let server = start(hub.clone(), "127.0.0.1:0".parse().unwrap()).unwrap();
    let addr = server.addr;
    let seq = hub.publish(scripture(), RoomDesign::default());
    let (mut screen, _) = open(addr, "salle", 1920, 1080).await;
    assert_eq!(next_frame(&mut screen).await.seq, seq);

    // Arrêt (fermeture de la régie, changement d'accès) : l'écran est prévenu, la connexion se ferme.
    drop(server);
    let closed = tokio::time::timeout(Duration::from_secs(5), async {
        loop {
            match screen.next().await {
                Some(Ok(WsMessage::Close(frame))) => return frame.map(|f| u16::from(f.code)),
                Some(Ok(_)) => {}
                _ => return None,
            }
        }
    })
    .await
    .unwrap();
    assert_eq!(closed, Some(1012));
    assert!(tokio_tungstenite::connect_async(format!("ws://{addr}/ws/salle")).await.is_err());

    // Même port, nouveau serveur : l'écran revient et reçoit le direct, qui a changé entre-temps.
    let seq = hub.publish(Slide::new("Pendant la coupure", "", SlideSource::Custom), RoomDesign::default());
    let _server = start(hub.clone(), addr).unwrap();
    let (mut screen, _) = open(addr, "salle", 1920, 1080).await;
    let frame = next_frame(&mut screen).await;
    assert_eq!(frame.seq, seq);
    assert!(frame.list.text_lines().any(|l| l.text.contains("coupure")));
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn network_screens_need_the_token() {
    let hub = hub();
    // Le poste lui-même n'est pas dispensé ici : c'est lui qui joue l'appareil du réseau.
    hub.set_access(Access { token: Some("jeton123".into()), loopback_trusted: false });
    let server = start(hub.clone(), "127.0.0.1:0".parse().unwrap()).unwrap();
    let addr = server.addr;
    assert!(get(addr, "/ecran/salle", None).await.starts_with("HTTP/1.1 403"));
    assert!(get(addr, "/polices.css", None).await.starts_with("HTTP/1.1 403"));
    assert!(tokio_tungstenite::connect_async(format!("ws://{addr}/ws/salle")).await.is_err());
    assert!(tokio_tungstenite::connect_async(format!("ws://{addr}/ws/salle?t=faux")).await.is_err());

    // L'adresse du QR code : la page passe et dépose le jeton en cookie.
    let page = get(addr, "/ecran/salle?t=jeton123", None).await;
    assert!(page.starts_with("HTTP/1.1 200"));
    assert!(page.to_lowercase().contains("set-cookie: po_t=jeton123"));
    assert!(get(addr, "/polices.css", Some("po_t=jeton123")).await.starts_with("HTTP/1.1 200"));
    let (mut socket, _) = tokio_tungstenite::connect_async(format!("ws://{addr}/ws/salle?t=jeton123")).await.unwrap();
    assert!(matches!(next_message(&mut socket).await, ServerMessage::Hello { .. }));

    // Le poste de la régie (OBS) entre sans jeton quand il est dispensé.
    hub.set_access(Access::lan("jeton123"));
    assert!(get(addr, "/ecran/diffusion", None).await.starts_with("HTTP/1.1 200"));
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_2x_addresses_still_work() {
    let hub = hub();
    let server = start(hub.clone(), "127.0.0.1:0".parse().unwrap()).unwrap();
    let addr = server.addr;
    for path in ["/obs", "/obs.html", "/presentation/obs", "/presentation/obs.html"] {
        let response = get(addr, path, None).await;
        assert!(response.starts_with("HTTP/1.1 307"), "{path} : {response}");
        assert!(response.to_lowercase().contains("location: /ecran/diffusion\r\n"), "{response}");
    }
    let response = get(addr, "/obs?scene=principale", None).await;
    assert!(response.to_lowercase().contains("location: /ecran/diffusion?scene=principale"));

    // `/slide.json` : le slide au direct, avec les champs de la 2.8.
    assert!(get(addr, "/slide.json", None).await.contains("\"hidden\":true"), "rien au direct");
    hub.publish(scripture(), RoomDesign::default());
    let json = get(addr, "/presentation/slide.json", None).await;
    let body: serde_json::Value = serde_json::from_str(json.split("\r\n\r\n").nth(1).unwrap()).unwrap();
    assert_eq!(body["reference"], "Jean 3:16");
    assert_eq!(body["source"], "bible");
    assert_eq!(body["hidden"], false);

    // Les pages : la diffusion est transparente, la salle non ; l'accueil liste les quatre écrans.
    assert!(get(addr, "/ecran/diffusion", None).await.contains("<body class=\"transparent\">"));
    assert!(get(addr, "/ecran/salle", None).await.contains("<body class=\"\">"));
    let js = get(addr, "/ecran.js", None).await;
    assert!(js.contains(&format!("const PROTOCOL = {PROTOCOL_VERSION};")));
    let index = get(addr, "/", None).await;
    for (name, _, _, _) in PRESETS {
        assert!(index.contains(&format!("/ecran/{name}")), "{name} absent de l'accueil");
    }
    let (_screen, _) = open(addr, "hall", 1280, 720).await;
    tokio::time::sleep(Duration::from_millis(100)).await;
    let index = get(addr, "/", None).await;
    assert!(index.contains("/ecran/hall") && index.contains("1 connecté"));
    assert!(get(addr, "/polices.css", None).await.contains("Passion One"));
    assert!(get(addr, "/polices/0", None).await.starts_with("HTTP/1.1 200"));
    assert!(get(addr, "/polices/99", None).await.starts_with("HTTP/1.1 404"));
}

#[test]
fn a_busy_port_moves_to_the_next_one() {
    let hub = hub();
    let first = start(hub.clone(), "127.0.0.1:0".parse().unwrap()).unwrap();
    let port = first.addr.port();
    let second = start_near(hub, "127.0.0.1".parse().unwrap(), port).unwrap();
    assert_ne!(second.addr.port(), port);
    assert!(second.addr.port() > port && second.addr.port() < port + 10);
}

/// Les transitions du navigateur sont celles du vidéoprojecteur : le code JavaScript de `ecran.js`
/// (exécuté par Node, s'il est installé) donne les mêmes couches que `po_layout::transition::plan`.
#[test]
fn the_browser_transitions_are_the_projector_ones() {
    use po_design::{AnimationKind, Direction};
    use po_layout::transition::{Layer, plan};
    // Le dossier temporaire de Windows est fermé aux exécutables d'essai : `target/tmp`.
    let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
    std::fs::create_dir_all(&dir).unwrap();
    let script = dir.join(format!("po-web-plan-{}.js", std::process::id()));
    let js = include_str!("../../web/ecran.js");
    let (Some(start), Some(end)) = (js.find("  function ease(t)"), js.find("  // Un support animé")) else {
        panic!("fonctions de transition introuvables dans ecran.js");
    };
    let kinds = [
        (AnimationKind::None, "none"),
        (AnimationKind::Fade, "fade"),
        (AnimationKind::Slide, "slide"),
        (AnimationKind::Scale, "scale"),
        (AnimationKind::Blur, "blur"),
        (AnimationKind::Reveal, "reveal"),
    ];
    let directions =
        [(Direction::Up, "up"), (Direction::Down, "down"), (Direction::Left, "left"), (Direction::Right, "right")];
    let times = [0.0f32, 0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0];
    let stage = [100.0f32, 80.0, 1720.0, 920.0];
    let mut cases = Vec::new();
    let mut expected = Vec::new();
    for (kind, kind_name) in kinds {
        for (direction, direction_name) in directions {
            for t in times {
                let animation = Animation { kind, duration_ms: 700, direction };
                cases.push(
                    serde_json::json!({"kind": kind_name, "direction": direction_name, "duration_ms": 700, "t": t}),
                );
                expected.push(plan(stage, 1920.0, 1080.0, &animation, t));
            }
        }
    }
    let program = format!(
        "let transparent = false;\n{}\nconst cases = {};\nconsole.log(JSON.stringify(cases.map(c => plan({:?}, 1920, 1080, c, c.t))));\n",
        &js[start..end],
        serde_json::to_string(&cases).unwrap(),
        stage,
    );
    std::fs::write(&script, program).unwrap();
    let output = std::process::Command::new("node").arg(&script).output();
    let _ = std::fs::remove_file(&script);
    let Ok(output) = output else {
        eprintln!("Node absent : comparaison des transitions sautée");
        return;
    };
    assert!(output.status.success(), "{}", String::from_utf8_lossy(&output.stderr));
    let got: Vec<Vec<serde_json::Value>> = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(got.len(), expected.len());
    // Le navigateur calcule en f64, la projection en f32 : à un centième de pixel près.
    let close = |a: f64, b: f32| (a - f64::from(b)).abs() < 1e-2 + 1e-5 * f64::from(b).abs();
    for ((case, js), rust) in cases.iter().zip(&got).zip(&expected) {
        assert_eq!(js.len(), rust.len(), "{case} : {js:?} / {rust:?}");
        for (j, r) in js.iter().zip(rust) {
            let layer = if r.layer == Layer::From { "from" } else { "to" };
            assert_eq!(j["layer"], layer, "{case}");
            for (key, value) in
                [("opacity", r.opacity), ("dx", r.dx), ("dy", r.dy), ("scale", r.scale), ("blur", r.blur)]
            {
                assert!(close(j[key].as_f64().unwrap(), value), "{case} {key} : {} / {value}", j[key]);
            }
            for i in 0..2 {
                assert!(close(j["origin"][i].as_f64().unwrap(), r.origin[i]), "{case} origine");
            }
            match r.clip {
                None => assert!(j["clip"].is_null(), "{case} découpe"),
                Some(clip) => {
                    for i in 0..4 {
                        assert!(close(j["clip"][i].as_f64().unwrap(), clip[i]), "{case} découpe");
                    }
                }
            }
        }
    }
}

fn has_text(items: &[Item], wanted: &str) -> bool {
    items.iter().any(|item| match item {
        Item::Text(line) => line.text == wanted,
        Item::Group(group) => has_text(&group.items, wanted),
        _ => false,
    })
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_lower_third_moves_on_the_broadcast_screen_only_while_it_animates() {
    use po_design::graphics::{LowerThirdText, builtin_lower_thirds};
    let hub = hub();
    let server = start(hub.clone(), "127.0.0.1:0".parse().unwrap()).unwrap();
    hub.update(Some(scripture()), context());
    let (mut broadcast, _) = open(server.addr, "diffusion", 1280, 720).await;
    let (mut room, _) = open(server.addr, "salle", 1280, 720).await;
    assert!(next_frame(&mut broadcast).await.list.overlay.is_empty());
    next_frame(&mut room).await;

    let (_, _, _, style) = builtin_lower_thirds().remove(1);
    let overlay =
        Overlay { style, text: LowerThirdText::new("Frère Paul", "Ancien"), shown: true, since: Instant::now() };
    hub.update(None, Context { lower_third: Some(overlay.clone()), ..context() });
    // L'entrée (450 ms) : des images à 30 par seconde, toutes différentes, puis plus rien.
    let mut overlays = Vec::new();
    while overlays
        .last()
        .is_none_or(|o: &Vec<Item>| !has_text(o, "Frère Paul") || o.iter().any(|i| matches!(i, Item::Group(_))))
    {
        let frame = next_frame(&mut broadcast).await;
        assert_eq!(frame.seq, 1, "même slide : pas de transition du bandeau");
        overlays.push(frame.list.overlay);
        assert!(overlays.len() < 60, "l'entrée ne finit pas");
    }
    assert!(overlays.len() >= 5, "{} images pendant l'entrée", overlays.len());
    assert!(quiet(&mut broadcast, Duration::from_millis(400)).await, "immobile : rien n'est renvoyé");
    assert!(quiet(&mut room, Duration::from_millis(100)).await, "la salle n'a pas d'habillage");

    // Masqué : il sort, puis disparaît.
    hub.update(
        None,
        Context { lower_third: Some(Overlay { shown: false, since: Instant::now(), ..overlay }), ..context() },
    );
    let mut last = next_frame(&mut broadcast).await.list.overlay;
    while !last.is_empty() {
        last = next_frame(&mut broadcast).await.list.overlay;
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn subtitles_show_the_current_chunk_and_nothing_when_hidden() {
    use po_design::graphics::{SubtitleLook, SubtitleStyle};
    let hub = hub();
    let server = start(hub.clone(), "127.0.0.1:0".parse().unwrap()).unwrap();
    hub.update(Some(scripture()), context());
    let (mut subtitles, _) = open(server.addr, "sous-titres", 1920, 1080).await;
    let frame = next_frame(&mut subtitles).await;
    assert!(frame.list.items.is_empty() && frame.list.background.alpha() == 0.0, "masqués : rien");
    let style = SubtitleStyle::new(SubtitleLook::BoxPerLine);
    hub.update(None, Context { subtitle: Some((style.clone(), "Que ton règne vienne".into())), ..context() });
    let frame = next_frame(&mut subtitles).await;
    assert!(frame.list.text_lines().any(|l| l.text.contains("règne")));
    assert!(frame.list.items.iter().any(|i| matches!(i, Item::Rect { .. })), "une boîte par ligne");
    assert_eq!(frame.animation, None);
    hub.update(None, Context { subtitle: Some((style, "Que ta volonté soit faite".into())), ..context() });
    assert!(next_frame(&mut subtitles).await.list.text_lines().any(|l| l.text.contains("volonté")));
}

#[test]
fn outputs_render_on_a_key_color_or_show_the_test_pattern() {
    let hub = hub();
    hub.update(Some(scripture()), context());
    let program = hub.program();
    let green = Rgba::rgb(0, 255, 0);
    let (pixels, next) = hub.render_rgba(&program, ScreenKind::Broadcast, 320, 180, Some(green), false);
    assert_eq!(pixels.len(), 320 * 180 * 4);
    assert_eq!(&pixels[..4], &[0, 255, 0, 255], "le coin est de la couleur de clé");
    assert_eq!(next, None);
    let (transparent, _) = hub.render_rgba(&program, ScreenKind::Broadcast, 320, 180, None, false);
    assert_eq!(transparent[3], 0, "NDI : le fond reste transparent");
    let (pattern, _) = hub.render_rgba(&program, ScreenKind::Broadcast, 320, 180, Some(green), true);
    // La première barre de la mire : gris 75 %.
    assert_eq!(&pattern[(20 * 320 + 10) * 4..(20 * 320 + 10) * 4 + 3], &[192, 192, 192]);
}
