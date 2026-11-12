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
        web_port: None,
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

/// Des écrans Web de démonstration : un paragraphe réel change toutes les 4 s, avec à chaque fois
/// une autre transition ; le bandeau suit vos réglages OBS de la 2.x (lus sans rien écrire).
fn servir(db_path: &Path, port: u16) -> Result<()> {
    use po_design::AnimationKind;
    let db = Database::open(db_path, Mode::ReadOnly)?;
    let paragraphs: Vec<String> = sample_paragraphs(&db)?.into_iter().step_by(7).take(60).collect();
    let hub = po_web::Hub::new(project_on::worker::fonts_from(&fonts_dir()));
    let server = po_web::start(hub.clone(), ([127, 0, 0, 1], port).into())?;
    println!("Écrans : http://{}/", server.addr);
    let band = legacy_band();
    // Un fond image (servi aux navigateurs) et l'identification de Branham.
    let mut room = design();
    room.background.image =
        Some(po_layout::bundled_backgrounds_dir().join("bg-bleu-nuit_16x9.png").to_string_lossy().into_owned());
    let kinds =
        [AnimationKind::Fade, AnimationKind::Slide, AnimationKind::Scale, AnimationKind::Blur, AnimationKind::Reveal];
    let slide = |i: usize| {
        Slide::new(
            paragraphs[i % paragraphs.len()].clone(),
            format!("Paragraphe d'essai n° {}", i + 1),
            SlideSource::Sermon,
        )
    };
    // Jusqu'à l'arrêt du processus.
    for i in 0..usize::MAX {
        let mut design = room.clone();
        design.animation.kind = kinds[i % kinds.len()];
        design.animation.duration_ms = 700;
        // La diffusion alterne le bandeau et le design de slide (son texte sur fond transparent).
        let broadcast =
            if (i / 3) % 2 == 0 { po_web::Look::Band(band.clone()) } else { po_web::Look::Slide(design.clone()) };
        let context = po_web::Context {
            design,
            broadcast,
            next: Some(slide(i + 1)),
            hidden: i % 7 == 6,
            clock: format!("10:{:02}", i % 60),
            status: format!("Prédication · {}:00 restantes", 30 - i % 30),
            ..po_web::Context::default()
        };
        hub.update(Some(slide(i)), context);
        std::thread::sleep(Duration::from_secs(4));
    }
    Ok(())
}

/// La vraie régie, hors écran, avec ses écrans Web sur 127.0.0.1:`port` : un paragraphe au direct,
/// puis le suivant toutes les 4 s (diagnostic des écrans Web et des sorties, sans fenêtre).
fn regie_web(db_path: &Path, port: u16, seconds: u64) -> Result<()> {
    let out = db_path.parent().map_or_else(|| PathBuf::from("."), Path::to_path_buf);
    // Une copie des réglages de ce poste (comme la vraie régie), sans recherche de mise à jour.
    let mut config = ui_config(db_path, &out);
    config.settings.appearance.check_updates = false;
    config.web_port = Some(port);
    let mut harness = ui_harness(config);
    harness.run_ok();
    // Le design des sorties choisi sur ce poste (PO_SORTIES, sinon celui de designs-choisis.json).
    let chosen = std::env::var("PO_SORTIES").ok().or_else(|| {
        let file =
            PathBuf::from(std::env::var_os("APPDATA")?).join("Project-On").join("data").join("designs-choisis.json");
        let v: Value = serde_json::from_str(&std::fs::read_to_string(file).ok()?).ok()?;
        v.get("sorties").and_then(Value::as_str).map(str::to_string)
    });
    if let Some(id) = chosen {
        let app = harness.state_mut().app();
        if let Some(output) = app.designs.find(&id).and_then(project_on::designs::Output::of) {
            println!("Sorties : {}", output.name);
            app.output = output;
        }
    }
    let addr = harness.state_mut().app().web.as_ref().and_then(|w| w.addr()).ok_or("serveur Web absent")?;
    println!("Écrans : http://{addr}/");
    harness.state_mut().app().select_sermon(40);
    harness.step();
    harness.state_mut().app().cue_sermon_entry(3);
    until(&mut harness, |a| !a.rendering() && a.preview_frame().is_some());
    harness.state_mut().app().take();
    let start = Instant::now();
    let mut last = Instant::now();
    let mut saved = false;
    while start.elapsed() < Duration::from_secs(seconds) {
        harness.step();
        // L'image exacte de la source NDI (le genre « diffusion », 1920 × 1080), une fois.
        if !saved && start.elapsed() > Duration::from_secs(3) {
            let hub = harness.state_mut().app().hub.clone();
            let (pixels, _) = hub.render_rgba(&hub.program(), po_web::ScreenKind::Broadcast, 1920, 1080, None, false);
            let mut board = checkerboard(1920, 1080)?;
            if let Some(image) =
                tiny_skia::Pixmap::from_vec(pixels, tiny_skia::IntSize::from_wh(1920, 1080).ok_or("taille")?)
            {
                board.draw_pixmap(
                    0,
                    0,
                    image.as_ref(),
                    &tiny_skia::PixmapPaint::default(),
                    tiny_skia::Transform::identity(),
                    None,
                );
            }
            std::fs::write(out.join("ndi-diffusion.png"), encode_png(&board)?)?;
            println!("NDI : {}", out.join("ndi-diffusion.png").display());
            saved = true;
        }
        if last.elapsed() > Duration::from_secs(4) {
            harness.state_mut().app().step(1);
            last = Instant::now();
        }
        std::thread::sleep(Duration::from_millis(30));
    }
    Ok(())
}

/// Le bandeau des réglages « OBS » de la 2.x de ce poste (lus sans rien écrire).
fn legacy_band() -> po_design::Band {
    std::env::var_os("APPDATA")
        .map(|d| PathBuf::from(d).join("Project-On").join("data").join("settings.json"))
        .and_then(|p| std::fs::read_to_string(p).ok())
        .and_then(|t| serde_json::from_str::<Value>(&t).ok())
        .and_then(|v| v.get("obs").and_then(|o| o.get("output")).cloned())
        .map_or_else(po_design::Band::default, |output| po_design::Band::from_obs_output(&output))
}

/// Un damier, comme les logiciels de montage montrent la transparence (là où passe la vidéo).
fn checkerboard(width: u32, height: u32) -> Result<tiny_skia::Pixmap> {
    let mut pixmap = tiny_skia::Pixmap::new(width, height).ok_or("taille")?;
    let cell = 24;
    for (i, px) in pixmap.pixels_mut().iter_mut().enumerate() {
        let (x, y) = (i as u32 % width / cell, i as u32 / width / cell);
        let v = if (x + y) % 2 == 0 { 58 } else { 44 };
        *px = tiny_skia::ColorU8::from_rgba(v, v + 4, v + 8, 255).premultiply();
    }
    Ok(pixmap)
}

/// Ce que reçoit chaque genre d'écran Web (mêmes listes d'affichage que le navigateur), en une
/// planche, puis la régie avec ses écrans connectés et la fenêtre « Web » ouverte.
fn capture_web(db_path: &Path, out_dir: &Path) -> Result<()> {
    use po_web::ScreenKind;
    std::fs::create_dir_all(out_dir)?;
    let db = Database::open(db_path, Mode::ReadOnly)?;
    let paragraphs = sample_paragraphs(&db)?;
    let mut fonts = project_on::worker::fonts_from(&fonts_dir());
    let hub = po_web::Hub::new(project_on::worker::fonts_from(&fonts_dir()));
    let mut room = design();
    room.background.image =
        Some(po_layout::bundled_backgrounds_dir().join("bg-bleu-nuit_16x9.png").to_string_lossy().into_owned());
    let slide = Slide::new(paragraphs[2].clone(), "La Foi · §12", SlideSource::Sermon);
    let next = Slide::new(paragraphs[3].clone(), "La Foi · §13", SlideSource::Sermon);
    hub.update(
        Some(slide),
        po_web::Context {
            design: room,
            broadcast: po_web::Look::Band(legacy_band()),
            next: Some(next),
            hidden: false,
            clock: "10:42".into(),
            status: "Prédication · 32:15 restantes".into(),
            ..po_web::Context::default()
        },
    );
    let program = hub.program();
    let (w, h, gap) = (960u32, 540u32, 24u32);
    let mut sheet = tiny_skia::Pixmap::new(2 * w + 3 * gap, 2 * h + 3 * gap).ok_or("taille")?;
    sheet.fill(tiny_skia::Color::from_rgba8(11, 18, 23, 255));
    let mut renderer = Renderer::new();
    let kinds = [ScreenKind::Room, ScreenKind::Broadcast, ScreenKind::Subtitles, ScreenKind::Stage];
    for (i, kind) in kinds.into_iter().enumerate() {
        let list = hub.layout(&program, kind, 1920.0, 1080.0);
        let image = renderer.render(&mut fonts, &list, w, h)?;
        let mut tile =
            if kind.transparent() { checkerboard(w, h)? } else { tiny_skia::Pixmap::new(w, h).ok_or("taille")? };
        let paint = tiny_skia::PixmapPaint::default();
        tile.draw_pixmap(0, 0, image.as_ref(), &paint, tiny_skia::Transform::identity(), None);
        let (x, y) = (gap + (i as u32 % 2) * (w + gap), gap + (i as u32 / 2) * (h + gap));
        sheet.draw_pixmap(x as i32, y as i32, tile.as_ref(), &paint, tiny_skia::Transform::identity(), None);
    }
    std::fs::write(out_dir.join("ecrans.png"), encode_png(&sheet)?)?;
    println!("Planche : {}", out_dir.join("ecrans.png").display());

    // La régie : trois écrans connectés, un quatrième qui vient de se couper.
    let mut config = ui_config(db_path, out_dir);
    config.web_port = Some(0);
    let mut harness = ui_harness(config);
    harness.run_ok();
    let app = harness.state_mut().app();
    let addr = app.web.as_ref().and_then(|w| w.addr()).ok_or("serveur Web absent")?;
    let (stop, stopped) = std::sync::mpsc::channel::<()>();
    let clients = std::thread::spawn(move || -> std::result::Result<(), String> {
        let runtime = tokio::runtime::Builder::new_current_thread().enable_all().build().map_err(|e| e.to_string())?;
        runtime.block_on(async move {
            let mut sockets = Vec::new();
            let screens =
                [("salle", 1920, 1080), ("diffusion", 1920, 1080), ("retour", 1280, 800), ("hall", 1366, 768)];
            for (screen, w, h) in screens {
                let (mut socket, _) = tokio_tungstenite::connect_async(format!("ws://{addr}/ws/{screen}"))
                    .await
                    .map_err(|e| e.to_string())?;
                let hello = format!(r#"{{"type":"hello","width":{w},"height":{h}}}"#);
                socket.send(Message::Text(hello.into())).await.map_err(|e| e.to_string())?;
                sockets.push(socket);
            }
            tokio::time::sleep(Duration::from_millis(300)).await;
            drop(sockets.pop());
            while stopped.try_recv().is_err() {
                for socket in &mut sockets {
                    while let Ok(Some(Ok(Message::Text(text)))) =
                        tokio::time::timeout(Duration::from_millis(20), socket.next()).await
                    {
                        if let Ok(po_web::ServerMessage::Frame { seq, .. }) = serde_json::from_str(&text) {
                            let ack = format!(r#"{{"type":"ack","seq":{seq}}}"#);
                            socket.send(Message::Text(ack.into())).await.map_err(|e| e.to_string())?;
                        }
                    }
                }
            }
            Ok(())
        })
    });
    std::thread::sleep(Duration::from_millis(800));
    harness.state_mut().app().select_sermon(40);
    harness.step();
    harness.state_mut().app().cue_sermon_entry(3);
    until(&mut harness, |a| !a.rendering() && a.preview_frame().is_some());
    harness.state_mut().app().take();
    until(&mut harness, |a| !a.rendering() && a.live_frame().is_some());
    std::thread::sleep(Duration::from_millis(500));
    harness.step();
    {
        use egui_kittest::kittest::Queryable;
        harness.get_by_label_contains("Web ·").click();
    }
    for _ in 0..5 {
        harness.step();
    }
    let image = harness.render()?;
    image.save(out_dir.join("web-regie.png"))?;
    println!("Capture : {}", out_dir.join("web-regie.png").display());
    let _ = stop.send(());
    clients.join().map_err(|_| "clients")??;
    Ok(())
}

/// La planche de tous les designs intégrés (aperçus réels, avec leur nom), puis la page Designs
/// de la régie avec un lower third et des sous-titres affichés.
fn capture_designs(db_path: &Path, out_dir: &Path) -> Result<()> {
    use po_design::library::DesignBody;
    std::fs::create_dir_all(out_dir)?;
    let mut fonts = project_on::worker::fonts_from(&fonts_dir());
    let mut renderer = Renderer::new();
    let room_2x = ui_config(db_path, out_dir).settings.projection.clone();
    let designs = po_design::library::builtin(&RoomDesign::from_projection(&room_2x), &legacy_band());
    let slide = project_on::designs::sample_slide();
    let [w, h] = project_on::designs::PREVIEW_SIZE;
    let (gap, label) = (16u32, 40u32);
    let columns = 5u32;
    let rows = (designs.len() as u32).div_ceil(columns);
    let (sheet_w, sheet_h) = (columns * (w + gap) + gap, rows * (h + label + gap) + gap);
    let mut sheet = tiny_skia::Pixmap::new(sheet_w, sheet_h).ok_or("taille")?;
    sheet.fill(tiny_skia::Color::from_rgba8(11, 18, 23, 255));
    let mut names = DisplayList::blank(sheet_w as f32, sheet_h as f32, Rgba::TRANSPARENT);
    for (i, design) in designs.iter().enumerate() {
        let pixels = project_on::designs::render_preview(&mut fonts, &mut renderer, &design.body, &slide);
        let tile =
            tiny_skia::Pixmap::from_vec(pixels, tiny_skia::IntSize::from_wh(w, h).ok_or("taille")?).ok_or("aperçu")?;
        let (col, row) = (i as u32 % columns, i as u32 / columns);
        let (x, y) = (gap + col * (w + gap), gap + row * (h + label + gap));
        let paint = tiny_skia::PixmapPaint::default();
        sheet.draw_pixmap(x as i32, y as i32, tile.as_ref(), &paint, tiny_skia::Transform::identity(), None);
        let kind = match &design.body {
            DesignBody::Room(_) => "Salle",
            DesignBody::Band(_) => "Bandeau",
            DesignBody::LowerThird(_) => "Lower third",
            DesignBody::Subtitles(_) => "Sous-titres",
        };
        for (text, dy, size, color, weight) in [
            (design.name.clone(), 20.0, 15.0, Rgba::rgb(242, 240, 233), 600),
            (format!("{kind} · {}", design.category), 37.0, 12.0, Rgba::rgb(147, 163, 173), 400),
        ] {
            let width = fonts.qt_advance(&text, "Inter", weight, size, 0.0);
            names.items.push(po_layout::Item::Text(po_layout::TextLine {
                text,
                x: x as f32,
                baseline: (y + h) as f32 + dy,
                anchor: po_layout::Anchor::Start,
                size,
                family: "Inter".into(),
                weight,
                color,
                width,
                letter_spacing: 0.0,
                advance_scale: 1.0,
                shadow: None,
                outline: None,
            }));
        }
    }
    let labels = renderer.render(&mut fonts, &names, sheet_w, sheet_h)?;
    sheet.draw_pixmap(
        0,
        0,
        labels.as_ref(),
        &tiny_skia::PixmapPaint::default(),
        tiny_skia::Transform::identity(),
        None,
    );
    std::fs::write(out_dir.join("designs.png"), encode_png(&sheet)?)?;
    println!("Planche : {} ({} designs)", out_dir.join("designs.png").display(), designs.len());

    // La page Designs : un paragraphe au direct, le lower third et les sous-titres affichés.
    let mut harness = ui_harness(ui_config(db_path, out_dir));
    harness.run_ok();
    harness.state_mut().app().select_sermon(40);
    harness.step();
    harness.state_mut().app().cue_sermon_entry(3);
    until(&mut harness, |a| !a.rendering() && a.preview_frame().is_some());
    harness.state_mut().app().take();
    until(&mut harness, |a| !a.rendering() && a.live_frame().is_some());
    let app = harness.state_mut().app();
    app.page = project_on::library::Page::Designs;
    app.lower_third.auto = true;
    app.toggle_lower_third();
    app.designs.selected = Some("lt-moderne".into());
    for _ in 0..40 {
        harness.step();
        std::thread::sleep(Duration::from_millis(25));
    }
    let image = harness.render()?;
    image.save(out_dir.join("designs-regie.png"))?;
    println!("Capture : {}", out_dir.join("designs-regie.png").display());
    Ok(())
}

/// Les captures du site (1600 × 960), sur une copie de la base fournie et avec les réglages par
/// défaut : aucune donnée de l'église ni de l'opérateur n'y apparaît.
fn capture_site(db_path: &Path, out_dir: &Path) -> Result<()> {
    use project_on::library::Page;
    use project_on::library::playlist::PlaylistAction;
    std::fs::create_dir_all(out_dir)?;
    // Aucune recherche de mise à jour pendant les captures (la version définitive en fait une).
    let mut settings = po_settings::Settings::default();
    settings.appearance.check_updates = false;
    let config = project_on::Config {
        fonts_dir: fonts_dir(),
        locations: None,
        database: Some(db_path.to_path_buf()),
        settings,
        windowed_projection: true,
        web_port: None,
    };
    let mut harness = egui_kittest::Harness::builder()
        .with_size([1600.0, 960.0])
        .with_accessibility_check(false)
        .wgpu()
        .build_ui_state(|ui, boot: &mut project_on::Boot| boot.ui(ui), project_on::Boot::new(config));
    harness.run_ok();
    let save = |harness: &mut egui_kittest::Harness<'static, project_on::Boot>, name: &str| -> Result<()> {
        for _ in 0..30 {
            harness.step();
            std::thread::sleep(Duration::from_millis(20));
        }
        let image = harness.render()?;
        let path = out_dir.join(format!("{name}.png"));
        image.save(&path)?;
        println!("Capture : {}", path.display());
        Ok(())
    };
    let program_of = |app: &project_on::App| -> Vec<po_program::Entry> {
        app.preview.as_ref().map_or_else(Vec::new, |s| {
            s.program.slides.iter().map(|p| po_program::Entry::new(p.reference.clone(), p.text.clone())).collect()
        })
    };
    let ready = |a: &project_on::App| !a.rendering() && a.preview_frame().is_some();
    let live = |a: &project_on::App| !a.rendering() && a.live_frame().is_some();

    // Bible : Jean 3:16 au direct, 3:17 dans l'Aperçu.
    let (translation, john) = {
        let db = harness.state_mut().app().database().ok_or("base absente")?;
        let t = db
            .list_translations()?
            .into_iter()
            .find(|t| t.lang.as_deref() == Some("fr"))
            .ok_or("aucune Bible française")?
            .id;
        let john = db.list_translation_books(t)?.into_iter().find(|b| b.name == "Jean").ok_or("Jean")?.id;
        (t, john)
    };
    harness.state_mut().app().open_bible(translation, john, 3, Some(16));
    until(&mut harness, ready);
    let bible = program_of(harness.state_mut().app());
    harness.state_mut().app().take();
    until(&mut harness, live);
    harness.state_mut().app().open_bible(translation, john, 3, Some(17));
    until(&mut harness, ready);
    save(&mut harness, "bible")?;

    // Cantiques : une strophe au direct, la suivante dans l'Aperçu.
    let hymn = std::env::var("PO_CANTIQUE").ok().and_then(|v| v.parse().ok()).unwrap_or(0);
    harness.state_mut().app().select_hymn(hymn);
    harness.step();
    harness.state_mut().app().cue_hymn_entry(0);
    until(&mut harness, ready);
    let hymn_entries = program_of(harness.state_mut().app());
    harness.state_mut().app().take();
    until(&mut harness, live);
    harness.state_mut().app().cue_hymn_entry(1);
    until(&mut harness, ready);
    save(&mut harness, "cantiques")?;

    // Prédications : un paragraphe au direct, le suivant dans l'Aperçu.
    harness.state_mut().app().select_sermon(40);
    harness.step();
    harness.state_mut().app().cue_sermon_entry(3);
    until(&mut harness, ready);
    let sermon = program_of(harness.state_mut().app());
    harness.state_mut().app().take();
    until(&mut harness, live);
    harness.state_mut().app().cue_sermon_entry(4);
    until(&mut harness, ready);
    save(&mut harness, "predications")?;

    // L'Exposé des Sept Âges.
    harness.state_mut().app().select_expose(1);
    harness.step();
    harness.state_mut().app().cue_expose_entry(2);
    until(&mut harness, ready);
    harness.state_mut().app().take();
    until(&mut harness, live);
    harness.state_mut().app().cue_expose_entry(3);
    until(&mut harness, ready);
    save(&mut harness, "expose")?;

    // Playlist : un culte préparé (cantique, versets, prédication), en sections, un slide au direct.
    {
        let app = harness.state_mut().app();
        app.apply_playlist(vec![PlaylistAction::CreateFolder("Culte du dimanche".into())]);
        app.playlists_add(&hymn_entries, "hymn");
        app.playlists_add(&bible[..bible.len().min(3)], "bible");
        app.playlists_add(&sermon[..sermon.len().min(6)], "sermon");
        app.page = Page::Playlist;
    }
    harness.step();
    let app = harness.state_mut().app();
    let ids: Vec<i64> = app.playlist.items.iter().map(|i| i.id).collect();
    let (first_bible, first_sermon) = (hymn_entries.len(), hymn_entries.len() + bible.len().min(3));
    if ids.len() > first_sermon {
        app.apply_playlist(vec![
            PlaylistAction::StartSectionAt { section: None, item: ids[0], name: "Louange".into(), duration: 20 },
            PlaylistAction::StartSectionAt {
                section: None,
                item: ids[first_bible],
                name: "Lecture".into(),
                duration: 10,
            },
            PlaylistAction::StartSectionAt {
                section: None,
                item: ids[first_sermon],
                name: "Prédication".into(),
                duration: 45,
            },
            PlaylistAction::SetStartTime("9:30".into()),
        ]);
    }
    app.playlist.show_plan = true;
    let start = ids.get(first_bible).copied().unwrap_or_default();
    app.play_playlist(start, true);
    until(&mut harness, live);
    harness.state_mut().app().playlist.selected = vec![start];
    save(&mut harness, "playlist")?;

    // Designs : le lower third et les sous-titres affichés sur le paragraphe au direct.
    harness.state_mut().app().select_sermon(40);
    harness.step();
    harness.state_mut().app().cue_sermon_entry(3);
    until(&mut harness, ready);
    harness.state_mut().app().take();
    until(&mut harness, live);
    {
        let app = harness.state_mut().app();
        app.page = Page::Designs;
        app.lower_third.auto = true;
        app.toggle_lower_third();
        app.designs.selected = Some("lt-moderne".into());
    }
    save(&mut harness, "designs")?;
    // Réglages → Projection : un fond fourni choisi, l'aperçu en direct et la galerie des fonds.
    {
        let app = harness.state_mut().app();
        app.toggle_lower_third();
        let mut settings = app.settings.clone();
        settings.projection.bg_mode = "image".into();
        settings.projection.bg_image =
            po_layout::bundled_backgrounds_dir().join("bg-photo-croix-aube_16x9.png").to_string_lossy().into_owned();
        settings.projection.background_dimmer = 0.45;
        app.apply_settings(settings);
        app.settings_view.draft = None;
        app.page = Page::Settings;
    }
    // Les vignettes des fonds et l'aperçu se préparent dans leurs fils.
    for _ in 0..160 {
        harness.step();
        std::thread::sleep(Duration::from_millis(25));
    }
    save(&mut harness, "reglages")?;
    {
        use egui_kittest::kittest::Queryable;
        harness.get_by_label("Fond : Croix aube").scroll_to_me();
    }
    save(&mut harness, "reglages-fonds")?;
    harness.state_mut().app().page = Page::Media;
    save(&mut harness, "medias")?;

    // Les écrans Web : salle, diffusion (transparente), sous-titres, retour de scène.
    let mut fonts = project_on::worker::fonts_from(&fonts_dir());
    let hub = po_web::Hub::new(project_on::worker::fonts_from(&fonts_dir()));
    let mut room = design();
    room.background.image =
        Some(po_layout::bundled_backgrounds_dir().join("bg-bleu-nuit_16x9.png").to_string_lossy().into_owned());
    // Jean 3:16 au direct, 3:17 en suivant (le programme du chapitre commence au verset 1).
    let text = |i: usize| bible.get(i).map_or_else(String::new, |e| e.text.clone());
    let reference = |i: usize| bible.get(i).map_or_else(String::new, |e| e.reference.clone());
    let subtitle = po_design::graphics::SubtitleStyle::new(po_design::graphics::SubtitleLook::BoxPerLine);
    hub.update(
        Some(Slide::new(text(15), reference(15), SlideSource::Bible)),
        po_web::Context {
            design: room,
            broadcast: po_web::Look::Band(po_design::Band::default()),
            next: Some(Slide::new(text(16), reference(16), SlideSource::Bible)),
            hidden: false,
            clock: "10:42".into(),
            status: "Lecture · 4:15 restantes".into(),
            subtitle: Some((subtitle, text(15))),
            ..po_web::Context::default()
        },
    );
    let program = hub.program();
    let (w, h, gap) = (960u32, 540u32, 24u32);
    let mut sheet = tiny_skia::Pixmap::new(2 * w + 3 * gap, 2 * h + 3 * gap).ok_or("taille")?;
    sheet.fill(tiny_skia::Color::from_rgba8(11, 18, 23, 255));
    let mut renderer = Renderer::new();
    let kinds = [
        po_web::ScreenKind::Room,
        po_web::ScreenKind::Broadcast,
        po_web::ScreenKind::Subtitles,
        po_web::ScreenKind::Stage,
    ];
    for (i, kind) in kinds.into_iter().enumerate() {
        let list = hub.layout(&program, kind, 1920.0, 1080.0);
        let image = renderer.render(&mut fonts, &list, w, h)?;
        let mut tile =
            if kind.transparent() { checkerboard(w, h)? } else { tiny_skia::Pixmap::new(w, h).ok_or("taille")? };
        let paint = tiny_skia::PixmapPaint::default();
        tile.draw_pixmap(0, 0, image.as_ref(), &paint, tiny_skia::Transform::identity(), None);
        let (x, y) = (gap + (i as u32 % 2) * (w + gap), gap + (i as u32 / 2) * (h + gap));
        sheet.draw_pixmap(x as i32, y as i32, tile.as_ref(), &paint, tiny_skia::Transform::identity(), None);
    }
    std::fs::write(out_dir.join("ecrans.png"), encode_png(&sheet)?)?;
    println!("Planche : {}", out_dir.join("ecrans.png").display());
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
        ["web", db, out] => capture_web(Path::new(db), Path::new(out)),
        ["designs", db, out] => capture_designs(Path::new(db), Path::new(out)),
        ["site", db, out] => capture_site(Path::new(db), Path::new(out)),
        ["regie-web", db, port, seconds] => regie_web(Path::new(db), port.parse()?, seconds.parse()?),
        ["trigramme", db, out] => {
            let report = trigramme::evaluate(Path::new(db), Path::new(out))?;
            std::fs::write(Path::new(out).join("trigramme.json"), serde_json::to_string_pretty(&report)?)?;
            Ok(())
        }
        _ => {
            eprintln!(
                "usage : po-mesures tout <base.db> <dossier> | demarrage <base.db> | servir <base.db> <port> | recherche <base.db> <sortie.json> | trigramme <base.db> <dossier> | captures <références 2.8> <dossier> | playlist <base.db> <dossier> | web <base.db> <dossier> | designs <base.db> <dossier> | site <base.db> <dossier>"
            );
            std::process::exit(2);
        }
    }
}
