//! Les mesures des phases 0 et 1, sur une COPIE de la base ouverte en lecture seule.
//!
//! ```text
//! po-mesures tout <base.db> <dossier de sortie>   toutes les mesures → mesures.json + images PNG
//! po-mesures demarrage <base.db>                  démarrage jusqu'à la première image, puis sortie
//! po-mesures servir <base.db> <port>              un écran Web de démonstration (Ctrl+C pour arrêter)
//! po-mesures recherche <base.db> <sortie.json>    la recherche seule (comparaison à froid, phase 1)
//! po-mesures trigramme <base.db> <dossier>        l'essai d'un index trigramme (phase 1)
//! po-mesures captures <références> <dossier>     les captures de référence (phase 2)
//! ```
//!
//! Aucune fenêtre ne s'ouvre : l'interface est rendue hors écran (egui_kittest + wgpu).

use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

mod captures;
mod trigramme;

use futures_util::{SinkExt, StreamExt};
use po_db::{Database, Mode, ParagraphSearch, SermonFilter};
use po_design::{ReferencePosition, Rgba, RoomDesign, SlideSource};
use po_layout::{DisplayList, Fonts, Slide, layout_room};
use po_render::{Renderer, encode_png};
use serde_json::{Value, json};
use tokio_tungstenite::tungstenite::Message;

pub(crate) type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

fn fonts_dir() -> PathBuf {
    po_layout::bundled_fonts_dir()
}

fn projection_fonts() -> Fonts {
    let dir = fonts_dir();
    Fonts::from_files(&[
        dir.join("Passion One/PassionOne-Bold.ttf"),
        dir.join("Passion One/PassionOne-Regular.ttf"),
        dir.join("Spectral/Spectral-Regular.ttf"),
        dir.join("Lato/Lato-Regular.ttf"),
        dir.join("Lato/Lato-Bold.ttf"),
    ])
}

/// Le style mesuré depuis la phase 0 : celui de presentation/config.json (Passion One 45,
/// capitales, référence en haut, fond uni sombre).
fn design() -> RoomDesign {
    let mut d = RoomDesign::default();
    d.text.family = "Passion One".into();
    d.text.weight = 700;
    d.text.size = 45.0;
    d.text.uppercase = true;
    d.text.line_height = 1.18;
    d.text.color = Rgba::new(255, 255, 255, 234);
    d.reference.size = 33.0;
    d.reference.position = ReferencePosition::Top;
    d.reference.color = Rgba::new(255, 255, 255, 198);
    d.shadow = None;
    d.background.color = Rgba::rgb(12, 15, 20);
    d
}

/// Une prédication mise en page (l'identification de Branham comprise), fond sombre.
fn lay(fonts: &mut Fonts, text: &str, reference: &str, style: &RoomDesign, w: f32, h: f32) -> DisplayList {
    let slide = Slide::new(text, reference, SlideSource::Sermon);
    layout_room(fonts, &slide, style, w, h, &mut |_: &DisplayList, _: [f32; 4]| 0.02)
}

pub(crate) fn ms(d: Duration) -> f64 {
    (d.as_secs_f64() * 10_000.0).round() / 10.0
}

/// Médiane, 95e centile et maximum, en millisecondes.
fn stats(mut samples: Vec<f64>) -> Value {
    samples.sort_by(f64::total_cmp);
    let at = |q: f64| samples.get(((samples.len() as f64 - 1.0) * q).round() as usize).copied().unwrap_or(0.0);
    let round = |v: f64| (v * 100.0).round() / 100.0;
    json!({ "n": samples.len(), "mediane_ms": round(at(0.5)), "p95_ms": round(at(0.95)), "max_ms": round(at(1.0)) })
}

/// Les mêmes requêtes que `bench_py.py` (version 2.8).
fn measure_db(db: &Database) -> Result<Value> {
    type Query = Box<dyn Fn(&Database) -> po_db::Result<(usize, String)>>;
    let queries: Vec<(&str, Query)> = vec![
        (
            "liste_sermons",
            Box::new(|d| {
                let l = d.list_sermons(&SermonFilter::default())?;
                Ok((l.len(), l.first().map(|s| s.title.clone()).unwrap_or_default()))
            }),
        ),
        (
            "liste_titre_foi",
            Box::new(|d| {
                let l = d.list_sermons(&SermonFilter { title: Some("foi"), ..Default::default() })?;
                Ok((l.len(), l.first().map(|s| s.title.clone()).unwrap_or_default()))
            }),
        ),
        ("fts_grace", Box::new(|d| hits(d.search_paragraphs(&search("grâce"))?))),
        ("fts_ferme_assurance", Box::new(|d| hits(d.search_paragraphs(&search("ferme assurance"))?))),
        ("fts_expression", Box::new(|d| hits(d.search_paragraphs(&search("\"colonne de feu\""))?))),
        ("sous_chaine_ernel_die", Box::new(|d| hits(d.search_paragraphs(&search("ernel Die"))?))),
        ("sous_chaine_absente", Box::new(|d| hits(d.search_paragraphs(&search("zzqxw"))?))),
    ];
    let mut out = serde_json::Map::new();
    for (name, run) in queries {
        let mut times = Vec::new();
        let mut last = (0, String::new());
        for _ in 0..3 {
            let start = Instant::now();
            last = run(db)?;
            times.push(ms(start.elapsed()));
        }
        println!("  {name:24} {:9.1} ms  ({} résultats)", times.iter().copied().fold(f64::MAX, f64::min), last.0);
        out.insert(
            name.into(),
            json!({ "ms_first": times[0], "ms_best": times.iter().copied().fold(f64::MAX, f64::min), "count": last.0, "first": last.1 }),
        );
    }
    Ok(Value::Object(out))
}

/// Les mêmes réglages que la recherche de la 2.8 mesurée (`bench_py.py`).
fn search(query: &str) -> ParagraphSearch<'_> {
    ParagraphSearch { query, language: Some("fr"), translator: None, limit: 100, substring_fallback: true }
}

fn hits(found: Vec<po_db::ParagraphHit>) -> po_db::Result<(usize, String)> {
    Ok((found.len(), found.first().map(|h| h.reference.clone()).unwrap_or_default()))
}

/// Des paragraphes réels : un sermon sur 25, ceux qui tiennent sur un slide (≤ 280 caractères,
/// comme le découpage de la 2.x) et les longs, coupés à 280.
fn sample_paragraphs(db: &Database) -> Result<Vec<String>> {
    let sermons = db.list_sermons(&SermonFilter::default())?;
    let mut out = Vec::new();
    for sermon in sermons.iter().step_by(25) {
        for paragraph in db.paragraphs(sermon.id)?.into_iter().take(12) {
            let text: String = paragraph.text.chars().take(280).collect();
            if text.trim().len() > 3 {
                out.push(text);
            }
        }
    }
    Ok(out)
}

fn measure_layout(paragraphs: &[String], out_dir: &Path) -> Result<Value> {
    let style = design();
    let reference = "63-0317M - Le Dévoilement de Dieu - ¶12".to_string();
    let cold = Instant::now();
    let mut fonts = projection_fonts();
    let fonts_ms = ms(cold.elapsed());
    let first = Instant::now();
    let _ = lay(&mut fonts, &paragraphs[0], &reference, &style, 1920.0, 1080.0);
    let first_ms = ms(first.elapsed());

    let mut layout_times = Vec::new();
    for text in paragraphs {
        let content = text.clone();
        let start = Instant::now();
        let _ = lay(&mut fonts, &content, &reference, &style, 1920.0, 1080.0);
        layout_times.push(start.elapsed().as_secs_f64() * 1000.0);
    }

    // Rendu en image (sorties NDI / HDMI, aperçus) d'un échantillon.
    let mut renderer = Renderer::new();
    let mut render_hd = Vec::new();
    let mut render_monitor = Vec::new();
    for text in paragraphs.iter().step_by(10) {
        let content = text.clone();
        let list = lay(&mut fonts, &content, &reference, &style, 1920.0, 1080.0);
        let start = Instant::now();
        renderer.render(&mut fonts, &list, 1920, 1080)?;
        render_hd.push(start.elapsed().as_secs_f64() * 1000.0);
        let list = lay(&mut fonts, &content, &reference, &style, 960.0, 540.0);
        let start = Instant::now();
        renderer.render(&mut fonts, &list, 960, 540)?;
        render_monitor.push(start.elapsed().as_secs_f64() * 1000.0);
    }
    // Les réglages par défaut de la 2.x : ombre portée, dégradé, voile « cinéma ».
    let shadowed = RoomDesign::default();
    let mut render_shadow = Vec::new();
    for text in paragraphs.iter().step_by(10) {
        let list = lay(&mut fonts, text, &reference, &shadowed, 1920.0, 1080.0);
        let start = Instant::now();
        renderer.render(&mut fonts, &list, 1920, 1080)?;
        render_shadow.push(start.elapsed().as_secs_f64() * 1000.0);
    }

    // Les images de référence : le plus long et le plus court des paragraphes, et un verset.
    let longest = paragraphs.iter().max_by_key(|p| p.chars().count()).cloned().unwrap_or_default();
    let shortest = paragraphs
        .iter()
        .filter(|p| p.split_whitespace().count() >= 3)
        .min_by_key(|p| p.chars().count())
        .cloned()
        .unwrap_or_default();
    for (name, text, reference) in [
        ("slide-long.png", longest, reference.clone()),
        ("slide-court.png", shortest, reference.clone()),
        ("slide-verset.png", "Car Dieu a tant aimé le monde qu'il a donné son Fils unique, afin que quiconque croit en lui ne périsse point, mais qu'il ait la vie éternelle.".to_string(), "Jean 3:16".to_string()),
    ] {
        let list = lay(&mut fonts, &text, &reference, &style, 1920.0, 1080.0);
        std::fs::write(out_dir.join(name), encode_png(&renderer.render(&mut fonts, &list, 1920, 1080)?)?)?;
    }
    Ok(json!({
        "paragraphes": paragraphs.len(),
        "chargement_polices_ms": fonts_ms,
        "premiere_mise_en_page_ms": first_ms,
        "mise_en_page_1080p": stats(layout_times),
        "rendu_1920x1080": stats(render_hd),
        "rendu_moniteur_960x540": stats(render_monitor),
        "rendu_1920x1080_reglages_par_defaut": stats(render_shadow),
    }))
}

async fn next_frame<S>(stream: &mut S) -> Option<u64>
where
    S: StreamExt<Item = std::result::Result<Message, tokio_tungstenite::tungstenite::Error>> + Unpin,
{
    while let Some(Ok(msg)) = stream.next().await {
        if let Message::Text(text) = msg
            && let Ok(po_web::ServerMessage::Frame { seq, .. }) = serde_json::from_str(&text)
        {
            return Some(seq);
        }
    }
    None
}

/// Latence du direct vers trois écrans Web de tailles différentes, et temps de reconnexion.
fn measure_web(paragraphs: &[String]) -> Result<Value> {
    let hub = po_web::Hub::new(projection_fonts());
    let server = po_web::start(hub.clone(), ([127, 0, 0, 1], 0).into())?;
    let url = format!("ws://{}/ws/salle", server.addr);
    let runtime = tokio::runtime::Builder::new_multi_thread().worker_threads(2).enable_all().build()?;
    runtime.block_on(async move {
        hub.publish(Slide::new("Bienvenue", "", SlideSource::Custom), design());
        let sizes = [(1920, 1080), (1280, 720), (1024, 768)];
        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<(u64, Instant)>();
        let mut tasks = Vec::new();
        for (w, h) in sizes {
            let (mut ws, _) = tokio_tungstenite::connect_async(&url).await?;
            ws.send(Message::Text(format!(r#"{{"type":"hello","width":{w},"height":{h}}}"#).into())).await?;
            next_frame(&mut ws).await;
            let tx = tx.clone();
            tasks.push(tokio::spawn(async move {
                while let Some(seq) = next_frame(&mut ws).await {
                    let _ = tx.send((seq, Instant::now()));
                }
            }));
        }
        let mut sent = std::collections::HashMap::new();
        let style = design();
        for text in paragraphs.iter().take(100) {
            let at = Instant::now();
            let seq = hub.publish(Slide::new(text.clone(), "Référence", SlideSource::Sermon), style.clone());
            sent.insert(seq, at);
            tokio::time::sleep(Duration::from_millis(30)).await;
        }
        tokio::time::sleep(Duration::from_millis(300)).await;
        let mut latencies = Vec::new();
        while let Ok((seq, at)) = rx.try_recv() {
            if let Some(start) = sent.get(&seq) {
                latencies.push(at.duration_since(*start).as_secs_f64() * 1000.0);
            }
        }
        let received = latencies.len();
        // Reconnexion : un écran qui revient reçoit l'état courant.
        let start = Instant::now();
        let (mut ws, _) = tokio_tungstenite::connect_async(&url).await?;
        ws.send(Message::Text(r#"{"type":"hello","width":1920,"height":1080}"#.into())).await?;
        next_frame(&mut ws).await;
        let reconnect = ms(start.elapsed());
        for task in tasks {
            task.abort();
        }
        drop(server);
        Ok::<Value, Box<dyn std::error::Error>>(json!({
            "ecrans": sizes.len(),
            "images_envoyees": sent.len(),
            "images_recues": received,
            "latence": stats(latencies),
            "reconnexion_jusqu_a_l_image_ms": reconnect,
        }))
    })
}

/// La configuration de l'interface pour les mesures : la copie de la base, et une copie des
/// réglages de l'utilisateur (le fichier d'origine n'est jamais ouvert en écriture).
fn ui_config(db_path: &Path, out_dir: &Path) -> project_on::Config {
    let settings = std::env::var_os("APPDATA")
        .map(|d| PathBuf::from(d).join("Project-On").join("data").join("settings.json"))
        .filter(|p| p.is_file())
        .and_then(|p| {
            let copy = out_dir.join("reglages-copie.json");
            std::fs::copy(&p, &copy).ok().map(|_| po_settings::Settings::load(&copy).settings)
        })
        .unwrap_or_default();
    project_on::Config {
        fonts_dir: fonts_dir(),
        locations: None,
        database: Some(db_path.to_path_buf()),
        settings,
        windowed_projection: true,
    }
}

fn ui_harness(config: project_on::Config) -> egui_kittest::Harness<'static, project_on::Boot> {
    egui_kittest::Harness::builder()
        .with_size([1600.0, 940.0])
        .with_accessibility_check(false)
        .wgpu()
        .build_ui_state(|ui, boot: &mut project_on::Boot| boot.ui(ui), project_on::Boot::new(config))
}

/// Fait tourner l'interface jusqu'à ce que `done` soit vrai (au plus 10 s) ; rend la durée en ms.
fn until(
    harness: &mut egui_kittest::Harness<'static, project_on::Boot>,
    done: impl Fn(&project_on::App) -> bool,
) -> f64 {
    let start = Instant::now();
    while start.elapsed() < Duration::from_secs(10) {
        harness.step();
        if harness.state().get().is_some_and(&done) {
            break;
        }
        std::thread::sleep(Duration::from_millis(1));
    }
    let elapsed = ms(start.elapsed());
    // Comme la vraie fenêtre, qui dessine chaque image : les textures partent à la carte graphique
    // au fur et à mesure (hors du temps mesuré). Sans cela, kittest les accumule toutes.
    let _ = harness.render();
    elapsed
}

/// L'interface rendue hors écran : démarrage, Aperçu, direct, recherche globale, capture.
fn measure_ui(db_path: &Path, out_dir: &Path) -> Result<Value> {
    let start = Instant::now();
    let mut harness = ui_harness(ui_config(db_path, out_dir));
    harness.run_ok();
    harness.render()?;
    let first_frame = ms(start.elapsed());

    // Un sermon, un paragraphe dans l'Aperçu (le rendu se fait sur son fil), puis F2.
    harness.state_mut().app().select_sermon(40);
    harness.step();
    harness.state_mut().app().cue_sermon_entry(3);
    let first_preview = until(&mut harness, |a| !a.rendering() && a.preview_frame().is_some());
    let count = harness.state_mut().app().sermons.entry_count();
    let mut previews = Vec::new();
    for index in 4..count.min(24) {
        harness.state_mut().app().cue_sermon_entry(index);
        previews.push(until(&mut harness, |a| !a.rendering()));
    }
    harness.state_mut().app().take();
    let take = until(&mut harness, |a| !a.rendering() && a.live_frame().is_some());
    let mut steps = Vec::new();
    for _ in 0..10 {
        harness.state_mut().app().step(1);
        steps.push(until(&mut harness, |a| !a.rendering()));
    }
    // L'image de l'interface pendant une transition (processeur seul : egui prépare l'image).
    harness.state_mut().app().step(1);
    let mut frames = Vec::new();
    for _ in 0..30 {
        let t = Instant::now();
        harness.step();
        frames.push(t.elapsed().as_secs_f64() * 1000.0);
    }
    // La recherche globale : une référence, puis des mots (premier appel, à froid pour l'index).
    let mut search = serde_json::Map::new();
    for query in ["Jean 3:16", "grâce", "ferme assurance"] {
        harness.state_mut().app().search_everywhere(query);
        harness.step();
        let ms = until(&mut harness, |a| !a.global_results_now().1);
        let hits = harness.state().get().map_or(0, |a| a.global_results_now().0.len());
        search.insert(query.into(), json!({ "ms": ms, "resultats": hits }));
    }
    harness.state_mut().app().search_everywhere("");
    for _ in 0..5 {
        harness.step();
    }
    let mut renders = Vec::new();
    let mut image = None;
    for _ in 0..5 {
        harness.step();
        let t = Instant::now();
        image = Some(harness.render()?);
        renders.push(t.elapsed().as_secs_f64() * 1000.0);
    }
    if let Some(image) = image {
        image.save(out_dir.join("interface.png"))?;
    }
    let sermons = harness.state_mut().app().sermons.sermon_count();
    Ok(json!({
        "sermons_affiches": sermons,
        "premiere_image_ms": first_frame,
        "clic_jusqu_a_l_apercu_ms": first_preview,
        "clics_suivants_ms": stats(previews),
        "envoi_au_direct_ms": take,
        "slide_suivant_ms": stats(steps),
        "image_egui_pendant_une_transition": stats(frames),
        "recherche_globale": search,
        "rendu_gpu_et_lecture": stats(renders),
    }))
}

/// La page Playlist, capturée sur une base qui a des playlists (celle des références de la
/// phase 4) : la playlist « Culte complet », une section du déroulé, un slide au direct.
fn capture_playlist(db_path: &Path, out_dir: &Path) -> Result<()> {
    std::fs::create_dir_all(out_dir)?;
    let mut harness = ui_harness(ui_config(db_path, out_dir));
    harness.run_ok();
    let app = harness.state_mut().app();
    app.page = project_on::library::Page::Playlist;
    harness.step();
    let app = harness.state_mut().app();
    let folder = app
        .database()
        .and_then(|db| db.list_folders().ok())
        .and_then(|f| f.into_iter().find(|f| f.name == "Culte complet"))
        .map(|f| f.id);
    let Some(folder) = folder else { return Err("playlist « Culte complet » introuvable".into()) };
    app.apply_playlist(vec![project_on::library::playlist::PlaylistAction::SelectFolder(folder)]);
    let ids: Vec<i64> = app.playlist.items.iter().map(|i| i.id).collect();
    if app.playlist.sections.is_empty() && ids.len() > 13 {
        use project_on::library::playlist::PlaylistAction as A;
        app.apply_playlist(vec![
            A::StartSectionAt { section: None, item: ids[0], name: "Louange".into(), duration: 25 },
            A::StartSectionAt { section: None, item: ids[9], name: "Cantiques".into(), duration: 15 },
            A::StartSectionAt { section: None, item: ids[13], name: "Prédication".into(), duration: 45 },
            A::SetStartTime("9:30".into()),
        ]);
    }
    app.playlist.show_plan = true;
    let start = ids.get(14).copied().unwrap_or(ids[0]);
    app.play_playlist(start, true);
    until(&mut harness, |a| !a.rendering() && a.live_frame().is_some());
    harness.state_mut().app().playlist.selected = vec![start];
    for _ in 0..5 {
        harness.step();
    }
    let image = harness.render()?;
    image.save(out_dir.join("playlist.png"))?;
    println!("Capture : {}", out_dir.join("playlist.png").display());
    Ok(())
}

/// Le démarrage, mesuré de l'intérieur jusqu'à la première image de l'interface.
fn demarrage(db_path: &Path) -> Result<()> {
    let start = Instant::now();
    let out = std::env::temp_dir();
    let mut harness = ui_harness(ui_config(db_path, &out));
    harness.run_ok();
    harness.render()?;
    println!("première image après {} ms", ms(start.elapsed()));
    Ok(())
}

/// La recherche seule, du lancement du processus jusqu'au dernier résultat : sur une copie jamais
/// lue (cache disque froid), c'est la première recherche d'un culte.
fn recherche(db_path: &Path, out: &Path) -> Result<()> {
    let open = Instant::now();
    let db = Database::open(db_path, Mode::ReadOnly)?;
    let open_ms = ms(open.elapsed());
    let search = measure_db(&db)?;
    let report = json!({ "ouverture_base_ms": open_ms, "recherche": search });
    std::fs::write(out, serde_json::to_string_pretty(&report)?)?;
    Ok(())
}

fn tout(db_path: &Path, out_dir: &Path) -> Result<()> {
    std::fs::create_dir_all(out_dir)?;
    let open = Instant::now();
    let db = Database::open(db_path, Mode::ReadOnly)?;
    let open_ms = ms(open.elapsed());
    println!("Base (schéma {}) ouverte en {open_ms} ms", db.schema_version()?);
    println!("Recherche :");
    let search = measure_db(&db)?;
    let paragraphs = sample_paragraphs(&db)?;
    println!("Mise en page et rendu ({} paragraphes réels)…", paragraphs.len());
    let layout = measure_layout(&paragraphs, out_dir)?;
    println!("{layout:#}");
    println!("Projection Web…");
    let web = measure_web(&paragraphs)?;
    println!("{web:#}");
    println!("Interface (hors écran)…");
    let ui = measure_ui(db_path, out_dir)?;
    println!("{ui:#}");
    let report = json!({ "ouverture_base_ms": open_ms, "recherche": search, "mise_en_page": layout, "web": web, "interface": ui });
    std::fs::write(out_dir.join("mesures.json"), serde_json::to_string_pretty(&report)?)?;
    Ok(())
}

/// Un écran Web de démonstration : un paragraphe réel change toutes les 4 s.
fn servir(db_path: &Path, port: u16) -> Result<()> {
    let db = Database::open(db_path, Mode::ReadOnly)?;
    let paragraphs = sample_paragraphs(&db)?;
    let hub = po_web::Hub::new(projection_fonts());
    let server = po_web::start(hub.clone(), ([127, 0, 0, 1], port).into())?;
    println!("Écran : http://{}/ecran/salle", server.addr);
    // Un fond image (servi aux navigateurs) et l'identification de Branham.
    let mut room = design();
    room.background.image =
        Some(po_layout::bundled_backgrounds_dir().join("bg-bleu-nuit_16x9.png").to_string_lossy().into_owned());
    for (i, text) in paragraphs.iter().cycle().step_by(7).enumerate() {
        hub.publish(
            Slide::new(text.clone(), format!("Paragraphe d'essai n° {}", i + 1), SlideSource::Sermon),
            room.clone(),
        );
        std::thread::sleep(Duration::from_secs(4));
    }
    Ok(())
}

fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.iter().map(String::as_str).collect::<Vec<_>>().as_slice() {
        ["tout", db, out] => tout(Path::new(db), Path::new(out)),
        ["demarrage", db] => demarrage(Path::new(db)),
        ["servir", db, port] => servir(Path::new(db), port.parse()?),
        ["recherche", db, out] => recherche(Path::new(db), Path::new(out)),
        ["captures", refs, out] => captures::run(Path::new(refs), Path::new(out)),
        ["playlist", db, out] => capture_playlist(Path::new(db), Path::new(out)),
        ["trigramme", db, out] => {
            let report = trigramme::evaluate(Path::new(db), Path::new(out))?;
            std::fs::write(Path::new(out).join("trigramme.json"), serde_json::to_string_pretty(&report)?)?;
            Ok(())
        }
        _ => {
            eprintln!(
                "usage : po-mesures tout <base.db> <dossier> | demarrage <base.db> | servir <base.db> <port> | recherche <base.db> <sortie.json> | trigramme <base.db> <dossier> | captures <références 2.8> <dossier> | playlist <base.db> <dossier>"
            );
            std::process::exit(2);
        }
    }
}
