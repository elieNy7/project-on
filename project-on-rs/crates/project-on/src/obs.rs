//! Le **pilotage d'OBS** par obs-websocket 5 (`obs_websocket.py` de la 2.8) : Project-On change de
//! scène quand un slide passe au direct ou quand le texte est masqué, liste les scènes d'OBS et crée
//! la source navigateur « Project-On » (l'écran Web Diffusion) dans la scène choisie.
//!
//! - Les réglages sont ceux de la 2.x (`obs.remote` : hôte, port, scènes) ; le mot de passe y est
//!   chiffré par Windows (DPAPI, `password_protected`), comme dans la 2.8 : il ne se lit que sur ce
//!   profil Windows.
//! - La connexion vit dans un fil à part : OBS fermé ne gêne pas la régie, Project-On réessaie toutes
//!   les 10 secondes.
//! - La 3.0 ne change de scène que quand la scène voulue change (direct ↔ masqué) : l'opérateur
//!   peut passer à une autre scène dans OBS sans que chaque slide le ramène en arrière.

use std::io::ErrorKind;
use std::net::{TcpStream, ToSocketAddrs};
use std::sync::mpsc::{Receiver, Sender, channel};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use base64::Engine;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

/// Les réglages du pilotage (`ObsRemoteSettings` de la 2.8).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ObsSettings {
    pub enabled: bool,
    pub host: String,
    pub port: u16,
    pub password: String,
    /// La scène quand un slide passe au direct.
    pub scene_on_live: String,
    /// La scène quand le texte est masqué.
    pub scene_on_hide: String,
}

impl Default for ObsSettings {
    fn default() -> Self {
        ObsSettings {
            enabled: false,
            host: "127.0.0.1".into(),
            port: 4455,
            password: String::new(),
            scene_on_live: String::new(),
            scene_on_hide: String::new(),
        }
    }
}

impl ObsSettings {
    /// Depuis les réglages de la 2.x (`obs.remote`), le mot de passe déchiffré.
    pub fn from_settings(settings: &po_settings::Settings) -> ObsSettings {
        let d = ObsSettings::default();
        let Some(r) = settings.other.get("obs").and_then(|o| o.get("remote")).filter(|r| r.is_object()) else {
            return d;
        };
        let text = |k: &str| r.get(k).and_then(Value::as_str).unwrap_or("").trim().to_string();
        let protected = text("password_protected");
        let password = if protected.is_empty() { text("password") } else { unprotect(&protected).unwrap_or_default() };
        ObsSettings {
            enabled: r.get("enabled").and_then(Value::as_bool).unwrap_or(false),
            host: Some(text("host")).filter(|h| !h.is_empty()).unwrap_or(d.host),
            port: r.get("port").and_then(Value::as_u64).and_then(|p| u16::try_from(p).ok()).unwrap_or(d.port),
            password,
            scene_on_live: text("scene_on_live"),
            scene_on_hide: text("scene_on_hide"),
        }
    }

    /// Écrit les réglages dans `obs.remote`, le mot de passe chiffré (jamais en clair).
    pub fn write_into(&self, settings: &mut po_settings::Settings) {
        let obs = settings.other.entry("obs".to_string()).or_insert_with(|| json!({}));
        if !obs.is_object() {
            *obs = json!({});
        }
        let Some(obs) = obs.as_object_mut() else { return };
        let remote = obs.entry("remote").or_insert_with(|| json!({}));
        if !remote.is_object() {
            *remote = json!({});
        }
        let Some(remote) = remote.as_object_mut() else { return };
        // Le même mot de passe garde son chiffrement : le brouillon ne change pas à chaque image.
        let current = remote.get("password_protected").and_then(Value::as_str).unwrap_or("").to_string();
        let protected = if self.password.is_empty() {
            String::new()
        } else if unprotect(&current).as_deref() == Some(self.password.as_str()) {
            current
        } else {
            protect(&self.password).unwrap_or_default()
        };
        for (k, v) in [
            ("enabled", json!(self.enabled)),
            ("host", json!(self.host)),
            ("port", json!(self.port)),
            ("password", json!("")),
            ("password_protected", json!(protected)),
            ("scene_on_live", json!(self.scene_on_live)),
            ("scene_on_hide", json!(self.scene_on_hide)),
        ] {
            remote.insert(k.into(), v);
        }
    }
}

/// Chiffre un secret pour ce profil Windows (`protect_secret` de la 2.8 : DPAPI, base64).
#[cfg(windows)]
pub fn protect(secret: &str) -> Option<String> {
    use windows::Win32::Foundation::{HLOCAL, LocalFree};
    use windows::Win32::Security::Cryptography::{CRYPT_INTEGER_BLOB, CRYPTPROTECT_UI_FORBIDDEN, CryptProtectData};
    use windows::core::HSTRING;
    let mut bytes = secret.as_bytes().to_vec();
    let input = CRYPT_INTEGER_BLOB { cbData: bytes.len() as u32, pbData: bytes.as_mut_ptr() };
    let mut output = CRYPT_INTEGER_BLOB::default();
    // SAFETY : tampons valides pendant l'appel ; la sortie est libérée par LocalFree.
    #[allow(unsafe_code)]
    unsafe {
        CryptProtectData(
            &input,
            &HSTRING::from("Project-On OBS"),
            None,
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            &mut output,
        )
        .ok()?;
        let data = std::slice::from_raw_parts(output.pbData, output.cbData as usize).to_vec();
        let _ = LocalFree(Some(HLOCAL(output.pbData.cast())));
        Some(base64::engine::general_purpose::STANDARD.encode(data))
    }
}

/// Déchiffre un secret de [`protect`] (ou de la 2.8).
#[cfg(windows)]
pub fn unprotect(value: &str) -> Option<String> {
    use windows::Win32::Foundation::{HLOCAL, LocalFree};
    use windows::Win32::Security::Cryptography::{CRYPT_INTEGER_BLOB, CRYPTPROTECT_UI_FORBIDDEN, CryptUnprotectData};
    if value.is_empty() {
        return None;
    }
    let mut bytes = base64::engine::general_purpose::STANDARD.decode(value).ok()?;
    let input = CRYPT_INTEGER_BLOB { cbData: bytes.len() as u32, pbData: bytes.as_mut_ptr() };
    let mut output = CRYPT_INTEGER_BLOB::default();
    // SAFETY : tampons valides pendant l'appel ; la sortie est libérée par LocalFree.
    #[allow(unsafe_code)]
    unsafe {
        CryptUnprotectData(&input, None, None, None, None, CRYPTPROTECT_UI_FORBIDDEN, &mut output).ok()?;
        let data = std::slice::from_raw_parts(output.pbData, output.cbData as usize).to_vec();
        let _ = LocalFree(Some(HLOCAL(output.pbData.cast())));
        String::from_utf8(data).ok()
    }
}

#[cfg(not(windows))]
pub fn protect(_secret: &str) -> Option<String> {
    None
}

#[cfg(not(windows))]
pub fn unprotect(_value: &str) -> Option<String> {
    None
}

/// La réponse au défi d'obs-websocket 5 : base64(sha256(base64(sha256(mot de passe + sel)) + défi)).
pub fn auth_hash(password: &str, salt: &str, challenge: &str) -> String {
    let b64 = base64::engine::general_purpose::STANDARD;
    let secret = b64.encode(Sha256::digest(format!("{password}{salt}").as_bytes()));
    b64.encode(Sha256::digest(format!("{secret}{challenge}").as_bytes()))
}

/// La source navigateur 1080p (`build_browser_source_settings`).
pub fn browser_source_settings(url: &str) -> Value {
    json!({
        "url": url, "width": 1920, "height": 1080,
        "reroute_audio": false, "restart_when_active": false, "shutdown": false,
    })
}

/// L'état de la connexion, pour la régie.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub enum ObsState {
    /// Pilotage désactivé.
    #[default]
    Off,
    Connecting,
    Connected,
    /// Pas connecté, et pourquoi (OBS fermé, mot de passe refusé…).
    Failed(String),
}

impl ObsState {
    pub fn label(&self) -> String {
        match self {
            ObsState::Off => "Désactivé".into(),
            ObsState::Connecting => "Connexion à OBS…".into(),
            ObsState::Connected => "Connecté à OBS".into(),
            ObsState::Failed(why) => why.clone(),
        }
    }
}

enum Command {
    SetScene(String),
    RefreshScenes,
    CreateSource { scene: String, url: String },
}

#[derive(Default)]
struct Shared {
    settings: ObsSettings,
    state: Option<ObsState>,
    scenes: Vec<String>,
    /// Le dernier message à montrer (« Source créée dans … »).
    message: String,
    stop: bool,
}

fn lock(shared: &Mutex<Shared>) -> std::sync::MutexGuard<'_, Shared> {
    shared.lock().unwrap_or_else(|e| e.into_inner())
}

/// Le pilotage d'OBS (un fil à part).
pub struct ObsRemote {
    shared: Arc<Mutex<Shared>>,
    commands: Sender<Command>,
    thread: Option<JoinHandle<()>>,
    /// La dernière scène demandée par la régie.
    last_target: Option<String>,
}

impl ObsRemote {
    pub fn start(wake: impl Fn() + Send + 'static) -> ObsRemote {
        let shared = Arc::new(Mutex::new(Shared::default()));
        let (commands, rx) = channel();
        let state = shared.clone();
        let thread = std::thread::Builder::new().name("po-obs".into()).spawn(move || run(&state, &rx, &wake)).ok();
        ObsRemote { shared, commands, thread, last_target: None }
    }

    /// Les réglages en vigueur (la connexion suit : ouverte, fermée ou refaite).
    pub fn configure(&self, settings: ObsSettings) {
        let mut shared = lock(&self.shared);
        if shared.settings != settings {
            shared.settings = settings;
        }
    }

    pub fn state(&self) -> ObsState {
        lock(&self.shared).state.clone().unwrap_or(ObsState::Off)
    }

    pub fn scenes(&self) -> Vec<String> {
        lock(&self.shared).scenes.clone()
    }

    pub fn message(&self) -> String {
        lock(&self.shared).message.clone()
    }

    pub fn refresh_scenes(&self) {
        let _ = self.commands.send(Command::RefreshScenes);
    }

    /// Crée (ou réoriente) la source navigateur « Project-On » dans `scene`.
    pub fn create_source(&self, scene: &str, url: &str) {
        let _ = self.commands.send(Command::CreateSource { scene: scene.into(), url: url.into() });
    }

    /// La régie signale l'état du direct : la scène voulue (direct ou masqué) est demandée à OBS
    /// quand elle change. `live` : un slide est au direct.
    pub fn notify_live(&mut self, live: bool, hidden: bool) {
        let settings = lock(&self.shared).settings.clone();
        if !settings.enabled || !live {
            return;
        }
        let target = if hidden { settings.scene_on_hide } else { settings.scene_on_live };
        if target.is_empty() || self.last_target.as_deref() == Some(target.as_str()) {
            return;
        }
        self.last_target = Some(target.clone());
        let _ = self.commands.send(Command::SetScene(target));
    }
}

impl Drop for ObsRemote {
    fn drop(&mut self) {
        lock(&self.shared).stop = true;
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

type Socket = tungstenite::WebSocket<TcpStream>;

/// Une connexion identifiée à OBS.
struct Session {
    socket: Socket,
    counter: u64,
    /// Les demandes en attente de réponse : identifiant → ce qu'on en fera.
    pending: Vec<(String, Pending)>,
}

#[derive(Clone)]
enum Pending {
    Scenes,
    Created { scene: String, url: String },
    Updated { scene: String },
    Ignore,
}

impl Session {
    fn request(&mut self, kind: &str, data: Option<Value>, then: Pending) -> Result<(), String> {
        self.counter += 1;
        let id = format!("projecton-{}", self.counter);
        let mut d = json!({ "requestType": kind, "requestId": id });
        if let Some(data) = data {
            d["requestData"] = data;
        }
        self.socket
            .send(tungstenite::Message::text(json!({ "op": 6, "d": d }).to_string()))
            .map_err(|e| e.to_string())?;
        self.pending.push((id, then));
        Ok(())
    }
}

/// Ouvre la connexion et s'identifie (Hello → Identify → Identified).
fn connect(settings: &ObsSettings) -> Result<Socket, String> {
    let address = (settings.host.as_str(), settings.port)
        .to_socket_addrs()
        .map_err(|_| format!("Adresse d'OBS introuvable : {}", settings.host))?
        .next()
        .ok_or("Adresse d'OBS introuvable")?;
    let stream = TcpStream::connect_timeout(&address, Duration::from_secs(3))
        .map_err(|_| "OBS ne répond pas (est-il ouvert, avec le serveur WebSocket activé ?)".to_string())?;
    stream.set_read_timeout(Some(Duration::from_secs(5))).map_err(|e| e.to_string())?;
    let url = format!("ws://{}:{}", settings.host, settings.port);
    let (mut socket, _) = tungstenite::client(url.as_str(), stream).map_err(|e| format!("OBS : {e}"))?;
    let hello = read_json(&mut socket)?.ok_or("OBS n'a pas répondu")?;
    if hello.get("op").and_then(Value::as_i64) != Some(0) {
        return Err("Réponse inattendue d'OBS".into());
    }
    let mut identify = json!({ "rpcVersion": 1, "eventSubscriptions": 0 });
    if let Some(auth) = hello.get("d").and_then(|d| d.get("authentication")) {
        let salt = auth.get("salt").and_then(Value::as_str).unwrap_or("");
        let challenge = auth.get("challenge").and_then(Value::as_str).unwrap_or("");
        if settings.password.is_empty() {
            return Err("OBS demande un mot de passe (Réglages → Pilotage d'OBS)".into());
        }
        identify["authentication"] = json!(auth_hash(&settings.password, salt, challenge));
    }
    socket
        .send(tungstenite::Message::text(json!({ "op": 1, "d": identify }).to_string()))
        .map_err(|e| e.to_string())?;
    match read_json(&mut socket) {
        Ok(Some(m)) if m.get("op").and_then(Value::as_i64) == Some(2) => {}
        Err(e) if e.contains("4009") => return Err("Mot de passe d'OBS refusé".into()),
        Err(e) => return Err(e),
        _ => return Err("OBS a refusé la connexion".into()),
    }
    // Ensuite, lectures courtes : le fil écoute OBS et la régie à tour de rôle.
    socket.get_ref().set_read_timeout(Some(Duration::from_millis(100))).map_err(|e| e.to_string())?;
    Ok(socket)
}

/// Le prochain message JSON ; `None` : rien pour l'instant.
fn read_json(socket: &mut Socket) -> Result<Option<Value>, String> {
    match socket.read() {
        Ok(tungstenite::Message::Text(text)) => Ok(serde_json::from_str(text.as_str()).ok()),
        Ok(tungstenite::Message::Close(frame)) => {
            Err(frame
                .map_or_else(|| "OBS a fermé la connexion".into(), |f| format!("OBS a fermé ({})", u16::from(f.code))))
        }
        Ok(_) => Ok(None),
        Err(tungstenite::Error::Io(e)) if matches!(e.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut) => Ok(None),
        Err(e) => Err(format!("Connexion à OBS perdue : {e}")),
    }
}

fn run(shared: &Mutex<Shared>, commands: &Receiver<Command>, wake: &dyn Fn()) {
    let mut session: Option<(Session, ObsSettings)> = None;
    let mut retry_at = Instant::now();
    let set_state = |state: ObsState| {
        let mut s = lock(shared);
        if s.state.as_ref() != Some(&state) {
            s.state = Some(state);
            drop(s);
            wake();
        }
    };
    loop {
        let (settings, stop) = {
            let s = lock(shared);
            (s.settings.clone(), s.stop)
        };
        if stop {
            return;
        }
        // Désactivé, ou les réglages ont changé : la connexion se ferme (et se refait).
        if session.as_ref().is_some_and(|(_, used)| *used != settings) {
            if let Some((mut s, _)) = session.take() {
                let _ = s.socket.close(None);
            }
            retry_at = Instant::now();
        }
        if !settings.enabled {
            set_state(ObsState::Off);
            while commands.try_recv().is_ok() {}
            std::thread::sleep(Duration::from_millis(200));
            continue;
        }
        let Some((current, _)) = session.as_mut() else {
            if Instant::now() < retry_at {
                std::thread::sleep(Duration::from_millis(200));
                continue;
            }
            set_state(ObsState::Connecting);
            match connect(&settings) {
                Ok(socket) => {
                    let mut s = Session { socket, counter: 0, pending: Vec::new() };
                    let _ = s.request("GetSceneList", None, Pending::Scenes);
                    session = Some((s, settings));
                    po_core::journal::line("OBS : connecté");
                    set_state(ObsState::Connected);
                }
                Err(why) => {
                    po_core::journal::line(&format!("OBS : {why}"));
                    set_state(ObsState::Failed(why));
                    retry_at = Instant::now() + Duration::from_secs(10);
                }
            }
            continue;
        };
        // Les demandes de la régie.
        let mut failed = None;
        while let Ok(command) = commands.try_recv() {
            let sent = match command {
                Command::SetScene(scene) => {
                    current.request("SetCurrentProgramScene", Some(json!({ "sceneName": scene })), Pending::Ignore)
                }
                Command::RefreshScenes => current.request("GetSceneList", None, Pending::Scenes),
                Command::CreateSource { scene, url } => current.request(
                    "CreateInput",
                    Some(json!({
                        "sceneName": scene, "inputName": "Project-On", "inputKind": "browser_source",
                        "inputSettings": browser_source_settings(&url), "sceneItemEnabled": true,
                    })),
                    Pending::Created { scene, url },
                ),
            };
            if let Err(e) = sent {
                failed = Some(e);
                break;
            }
        }
        // Les réponses d'OBS.
        if failed.is_none() {
            match read_json(&mut current.socket) {
                Ok(Some(message)) if message.get("op").and_then(Value::as_i64) == Some(7) => {
                    let d = message.get("d").cloned().unwrap_or(Value::Null);
                    let id = d.get("requestId").and_then(Value::as_str).unwrap_or("").to_string();
                    let ok =
                        d.get("requestStatus").and_then(|s| s.get("result")).and_then(Value::as_bool) == Some(true);
                    if let Some(i) = current.pending.iter().position(|(p, _)| *p == id) {
                        let (_, then) = current.pending.remove(i);
                        match then {
                            Pending::Scenes if ok => {
                                let scenes: Vec<String> = d
                                    .get("responseData")
                                    .and_then(|r| r.get("scenes"))
                                    .and_then(Value::as_array)
                                    .map(|a| {
                                        a.iter()
                                            .filter_map(|s| s.get("sceneName").and_then(Value::as_str))
                                            .map(str::to_string)
                                            .collect()
                                    })
                                    .unwrap_or_default();
                                lock(shared).scenes = scenes;
                                wake();
                            }
                            // La source existe déjà : on change seulement son adresse.
                            Pending::Created { scene, url } if !ok => {
                                let _ = current.request(
                                    "SetInputSettings",
                                    Some(json!({
                                        "inputName": "Project-On",
                                        "inputSettings": browser_source_settings(&url), "overlay": true,
                                    })),
                                    Pending::Updated { scene },
                                );
                            }
                            Pending::Created { scene, .. } | Pending::Updated { scene } => {
                                lock(shared).message = if ok {
                                    format!("Source « Project-On » prête dans la scène « {scene} »")
                                } else {
                                    "OBS a refusé de créer la source".into()
                                };
                                wake();
                            }
                            _ => {}
                        }
                    }
                }
                Ok(_) => {}
                Err(e) => failed = Some(e),
            }
        }
        if let Some(why) = failed {
            po_core::journal::line(&format!("OBS : {why}"));
            session = None;
            set_state(ObsState::Failed(why));
            retry_at = Instant::now() + Duration::from_secs(10);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_challenge_answer_is_the_one_obs_expects() {
        // Le calcul de la 2.8 (`compute_obs_auth_hash`), mêmes entrées.
        assert_eq!(
            auth_hash(
                "supersecret",
                "lM1GncleQOaCu9lT1yeUZhFYnqhsLLP1G5lAGo3ixaI=",
                "+IxH4CnCiqpX1rM9scsNynZzbOe4KhDeYcTNS3PDaeY="
            ),
            "sQBlPUYd9mki/3XVFBp4Pt08FCMWdMVIqnFWdEitUME="
        );
    }

    #[cfg(windows)]
    #[test]
    fn the_password_is_never_written_in_clear() {
        let mut settings = po_settings::Settings::default();
        let obs = ObsSettings {
            enabled: true,
            password: "mot de passe".into(),
            scene_on_live: "Direct".into(),
            ..ObsSettings::default()
        };
        obs.write_into(&mut settings);
        let text = serde_json::to_string(&settings.other).unwrap();
        assert!(!text.contains("mot de passe"), "{text}");
        assert_eq!(ObsSettings::from_settings(&settings), obs);
        // Réécrit sans changement : le même chiffrement (le brouillon ne bouge pas).
        let before = settings.other.clone();
        obs.write_into(&mut settings);
        assert_eq!(settings.other, before);
    }

    /// Un faux OBS (obs-websocket 5, avec mot de passe) sur ce poste seulement.
    #[test]
    fn scenes_are_listed_and_switched_with_a_password() {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let seen = Arc::new(Mutex::new(Vec::<String>::new()));
        let log = seen.clone();
        std::thread::spawn(move || {
            let (stream, _) = listener.accept().unwrap();
            let mut ws = tungstenite::accept(stream).unwrap();
            let (salt, challenge) = ("sel", "défi");
            ws.send(tungstenite::Message::text(
                json!({"op": 0, "d": {"rpcVersion": 1, "authentication": {"salt": salt, "challenge": challenge}}})
                    .to_string(),
            ))
            .unwrap();
            let identify: Value = serde_json::from_str(ws.read().unwrap().to_text().unwrap()).unwrap();
            assert_eq!(identify["d"]["authentication"], json!(auth_hash("secret", salt, challenge)));
            ws.send(tungstenite::Message::text(json!({"op": 2, "d": {"negotiatedRpcVersion": 1}}).to_string()))
                .unwrap();
            loop {
                let Ok(message) = ws.read() else { return };
                let Ok(text) = message.to_text() else { return };
                let request: Value = serde_json::from_str(text).unwrap();
                let kind = request["d"]["requestType"].as_str().unwrap().to_string();
                let id = request["d"]["requestId"].clone();
                let mut data = json!({});
                if kind == "GetSceneList" {
                    data = json!({"scenes": [{"sceneName": "Caméra"}, {"sceneName": "Caméra + texte"}]});
                } else {
                    log.lock()
                        .unwrap()
                        .push(format!("{kind} {}", request["d"]["requestData"]["sceneName"].as_str().unwrap_or("")));
                }
                let reply = json!({"op": 7, "d": {"requestType": kind, "requestId": id,
                    "requestStatus": {"result": true, "code": 100}, "responseData": data}});
                ws.send(tungstenite::Message::text(reply.to_string())).unwrap();
            }
        });
        let mut obs = ObsRemote::start(|| {});
        obs.configure(ObsSettings {
            enabled: true,
            port,
            password: "secret".into(),
            scene_on_live: "Caméra + texte".into(),
            scene_on_hide: "Caméra".into(),
            ..ObsSettings::default()
        });
        let start = Instant::now();
        while obs.scenes().len() < 2 && start.elapsed() < Duration::from_secs(10) {
            std::thread::sleep(Duration::from_millis(20));
        }
        assert_eq!(obs.state(), ObsState::Connected);
        assert_eq!(obs.scenes(), ["Caméra", "Caméra + texte"]);
        obs.notify_live(true, false);
        obs.notify_live(true, false); // même scène : rien de plus
        obs.notify_live(true, true);
        obs.create_source("Caméra + texte", "http://127.0.0.1:8080/ecran/diffusion");
        while obs.message().is_empty() && start.elapsed() < Duration::from_secs(10) {
            std::thread::sleep(Duration::from_millis(20));
        }
        assert_eq!(obs.message(), "Source « Project-On » prête dans la scène « Caméra + texte »");
        assert_eq!(
            *seen.lock().unwrap(),
            ["SetCurrentProgramScene Caméra + texte", "SetCurrentProgramScene Caméra", "CreateInput Caméra + texte"]
        );
    }
}
