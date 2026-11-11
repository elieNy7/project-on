//! Les essais des playlists ; les attentes viennent des essais de la 2.8
//! (`test_playlist_display.py`, `test_playlist_organize.py`).

use std::path::Path;

use po_db::{Database, InitOptions};

use super::*;

fn scratch() -> tempfile::TempDir {
    let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
    std::fs::create_dir_all(&base).unwrap();
    tempfile::tempdir_in(base).unwrap()
}

fn database(dir: &tempfile::TempDir) -> Database {
    Database::open_and_initialize(&dir.path().join("p.db"), &InitOptions::default()).unwrap().0
}

fn refs(db: &Database, folder: i64) -> Vec<String> {
    db.list_items(Some(folder)).unwrap().into_iter().map(|i| i.reference).collect()
}

fn entries(list: &[&str]) -> Vec<Entry> {
    list.iter().map(|r| Entry::new(*r, r.to_lowercase())).collect()
}

#[test]
fn the_stored_kind_wins_and_old_items_are_recognised() {
    assert_eq!(item_kind("bible", "N'importe quoi", ""), Kind::Bible);
    assert_eq!(item_kind("hymn", "", ""), Kind::Hymn);
    assert_eq!(item_kind("media", "Affiche", "C:/a/affiche.png"), Kind::Image);
    assert_eq!(item_kind("media", "Clip", "C:/a/clip.mp4"), Kind::Video);
    assert_eq!(item_kind("media", "Cours", "C:/a/cours.pptx"), Kind::PowerPoint);
    assert_eq!(item_kind("custom", "Jean 3:16", ""), Kind::Bible);
    assert_eq!(item_kind("custom", "1 Corinthiens 13:4-7", ""), Kind::Bible);
    assert_eq!(item_kind("custom", "Cantique 12 - Strophe 2", ""), Kind::Hymn);
    assert_eq!(item_kind("custom", "65-0725M La Voix de Dieu - §42", ""), Kind::Sermon);
    assert_eq!(item_kind("custom", "49-0718 - Titre - E-11 (3/7)", ""), Kind::Sermon);
    assert_eq!(item_kind("custom", "Le Tabernacle · Page 3 §2", ""), Kind::Expose);
    assert_eq!(item_kind("custom", "Bienvenue", ""), Kind::Custom);
    assert_eq!(item_kind("", "", ""), Kind::Custom);
}

#[test]
fn the_identification_follows_each_item() {
    let bios = vec!["William Branham, un homme envoyé de Dieu".to_string()];
    assert_eq!(slide_source(Kind::Sermon, "47-0412 - La Foi - ¶3", &bios), SlideSource::Sermon);
    assert_eq!(
        slide_source(Kind::Expose, "Exposé des Sept Âges — L'Âge d'Éphèse · Page 3 §2", &bios),
        SlideSource::Expose
    );
    assert_eq!(
        slide_source(Kind::Expose, "William Branham, un homme envoyé de Dieu — Chapitre 1 · Page 4 §1", &bios),
        SlideSource::Book
    );
    assert_eq!(slide_source(Kind::Bible, "Jean 3:16", &bios), SlideSource::Bible);
    assert_eq!(slide_source(Kind::Custom, "Annonces", &bios), SlideSource::Custom);
}

#[test]
fn the_whole_selection_moves_and_drops() {
    let order = [1, 2, 3, 4, 5];
    assert_eq!(move_selection(&order, &[2, 4], -1), [2, 1, 4, 3, 5]);
    assert_eq!(move_selection(&order, &[2, 4], 1), [1, 3, 2, 5, 4]);
    // Au bord : rien ne passe par-dessus un autre élément choisi.
    assert_eq!(move_selection(&order, &[1, 2], -1), [1, 2, 3, 4, 5]);
    // Glisser le dernier en tête ; deux éléments choisis posés avant le 2.
    assert_eq!(drop_selection(&order, &[5], 0), [5, 1, 2, 3, 4]);
    assert_eq!(drop_selection(&order, &[4, 5], 1), [1, 4, 5, 2, 3]);
    assert_eq!(drop_selection(&order, &[1], 5), [2, 3, 4, 5, 1]);
    assert_eq!(drop_selection(&order, &[2], 2), [1, 2, 3, 4, 5], "posé à sa place");
}

#[test]
fn every_change_can_be_undone_in_order() {
    let dir = scratch();
    let mut db = database(&dir);
    let mut p = Playlists::default();
    let folder = p.create_folder(&mut db, "Culte").unwrap();
    let other = p.create_folder(&mut db, "Jeunesse").unwrap();
    let (_, ids) = p.add_entries(&mut db, Some(folder), "", &entries(&["A", "B", "C"]), "bible").unwrap();
    let (a, b, c) = (ids[0], ids[1], ids[2]);

    assert!(p.reorder(&mut db, folder, &[c, b, a]));
    p.duplicate(&mut db, folder, &[b]);
    p.move_to(&mut db, &[a], folder, other);
    p.delete_items(&mut db, folder, &[c]);
    assert_eq!(refs(&db, folder), ["B", "B"]);
    assert_eq!(refs(&db, other), ["A"]);
    assert!(p.undo.available());

    assert!(p.undo(&mut db)); // la suppression
    assert_eq!(refs(&db, folder), ["C", "B", "B"]);
    assert!(p.undo(&mut db)); // le déplacement vers « Jeunesse »
    assert_eq!(refs(&db, folder), ["C", "B", "B", "A"]);
    assert!(refs(&db, other).is_empty());
    assert!(p.undo(&mut db)); // la duplication
    assert!(p.undo(&mut db)); // le nouvel ordre
    assert_eq!(refs(&db, folder), ["A", "B", "C"]);
    let back: Vec<i64> = db.list_items(Some(folder)).unwrap().iter().map(|i| i.id).collect();
    assert_eq!(back, [a, b, c], "les mêmes identifiants");
    assert!(p.undo(&mut db)); // l'ajout depuis la Bible
    assert!(refs(&db, folder).is_empty());
    assert!(!p.undo(&mut db), "plus rien à annuler");
    assert!(!p.undo.available());
}

#[test]
fn a_deleted_playlist_drops_its_undo_steps_and_a_stale_order_leaves_none() {
    let dir = scratch();
    let mut db = database(&dir);
    let mut p = Playlists::default();
    let folder = p.create_folder(&mut db, "Culte").unwrap();
    let (_, ids) = p.add_entries(&mut db, Some(folder), "", &entries(&["A", "B"]), "custom").unwrap();
    assert!(!p.reorder(&mut db, folder, &ids[..1]), "ordre incomplet refusé");
    assert_eq!(p.undo.len(), 1, "seul l'ajout s'annule");
    assert!(p.delete_folder(&db, folder));
    assert!(p.undo.is_empty());
    // Ajouter vers une nouvelle playlist la crée ; une entrée vide est ignorée.
    let (created, ids) =
        p.add_entries(&mut db, None, "Mariage", &[Entry::new("", " "), Entry::new("Ps 23", "Texte")], "bible").unwrap();
    assert_eq!(ids.len(), 1);
    assert_eq!(db.folder(created).unwrap().unwrap().name, "Mariage");
    assert!(p.add_entries(&mut db, None, "", &entries(&["X"]), "custom").is_none(), "sans nom, pas de playlist");
    // L'annulation est bornée à 30 étapes.
    for i in 0..40 {
        p.create_item(&mut db, created, &format!("Slide {i}"), "texte");
    }
    assert_eq!(p.undo.len(), UNDO_DEPTH);
}

#[test]
fn a_playlist_is_played_from_the_chosen_item() {
    let item = |id, source: &str, reference: &str, text: &str, background: &str| PlaylistItem {
        id,
        folder_id: Some(1),
        source: source.into(),
        reference: reference.into(),
        text: text.into(),
        sort_order: Some(id),
        background: background.into(),
    };
    let items = [
        item(1, "bible", "Jean 3:16", "Car Dieu a tant aimé le monde.", ""),
        item(2, "custom", "Vide", "   ", ""),
        item(3, "media", "Affiche", "", "C:/affiche.png"),
        item(4, "sermon", "47-0412 - La Foi - ¶3", "La foi est une ferme assurance.", ""),
        item(5, "custom", "", "Annonce sans référence.", ""),
    ];
    let p = program("Culte du dimanche", &items, Some(4), &[], &|_| None).unwrap();
    assert_eq!(p.item_of_entry, [1, 3, 4, 5], "texte vide sauté ; l'image a son slide");
    assert_eq!(p.cue.focus, 2);
    assert_eq!(p.cue.entries[3].reference, "Culte du dimanche", "sans référence : le titre");
    assert_eq!(p.cue.kinds, [SlideSource::Bible, SlideSource::Custom, SlideSource::Sermon, SlideSource::Custom]);
    let split = po_settings::SplitSettings::default();
    let mut prog = po_program::Program::from_cue(&p.cue, &split).unwrap();
    assert_eq!(prog.slide().source, SlideSource::Sermon, "la prédication garde son identification");
    assert!(prog.next_slide());
    assert_eq!(prog.slide().source, SlideSource::Custom);
    // Élément introuvable : le premier.
    assert_eq!(program("T", &items, Some(99), &[], &|_| None).unwrap().cue.focus, 0);
    assert!(program("T", &items[1..2], None, &[], &|_| None).is_none(), "rien à projeter");
    assert!(program("T", &items[1..3], None, &[], &|_| None).is_some(), "une image seule se projette");
}

#[test]
fn images_and_videos_are_projected_in_their_place() {
    let item = |id, source: &str, reference: &str, text: &str, background: &str| PlaylistItem {
        id,
        folder_id: Some(1),
        source: source.into(),
        reference: reference.into(),
        text: text.into(),
        sort_order: Some(id),
        background: background.into(),
    };
    let items = [
        item(1, "custom", "Annonce", "Bienvenue à tous", "#123456"),
        item(2, "media", "affiche", "", "C:/medias/affiche.png"),
        item(3, "media", "clip", "", "C:/medias/clip.mp4"),
        item(4, "custom", "Prière", "Notre Père", "C:/fonds/ciel.jpg"),
        item(5, "media", "", "", "C:/medias/Photo du groupe.JPEG"),
    ];
    let p = program("Culte", &items, Some(2), &[], &|_| None).unwrap();
    let refs: Vec<&str> = p.cue.entries.iter().map(|e| e.reference.as_str()).collect();
    assert_eq!(refs, ["Annonce", "affiche", "clip", "Prière", "Photo du groupe.JPEG"]);
    assert_eq!(p.item_of_entry, [1, 2, 3, 4, 5]);
    assert_eq!(p.cue.focus, 1, "le départ sur l'image");
    assert_eq!(
        p.cue.backgrounds,
        [
            None,
            Some("C:/medias/affiche.png".into()),
            Some("C:/medias/clip.mp4".into()),
            Some("C:/fonds/ciel.jpg".into()),
            Some("C:/medias/Photo du groupe.JPEG".into())
        ],
        "une couleur n'est pas une image ; le fond propre d'un texte suit"
    );
    // Sans aucune image, rien ne change pour le programme.
    let plain = program("Culte", &items[..1], None, &[], &|_| None).unwrap();
    assert!(plain.cue.backgrounds.is_empty());
}

#[test]
fn a_rendered_powerpoint_gives_one_slide_per_image() {
    let item = |id, source: &str, reference: &str, text: &str, background: &str| PlaylistItem {
        id,
        folder_id: Some(1),
        source: source.into(),
        reference: reference.into(),
        text: text.into(),
        sort_order: Some(id),
        background: background.into(),
    };
    let items = [
        item(1, "bible", "Jean 3:16", "Car Dieu a tant aimé le monde.", ""),
        item(2, "media", "", "", "C:/Annonces.pptx"),
        item(3, "custom", "Prière", "Notre Père.", ""),
    ];
    // Pas encore rendu : sauté.
    let p = program("Culte", &items, None, &[], &|_| None).unwrap();
    assert_eq!(p.item_of_entry, [1, 3]);
    // Rendu : ses trois slides, à sa place, chacun avec son image.
    let slides =
        |path: &str| (path == "C:/Annonces.pptx").then(|| vec!["s1.png".into(), "s2.png".into(), "s3.png".into()]);
    let p = program("Culte", &items, Some(2), &[], &slides).unwrap();
    assert_eq!(p.item_of_entry, [1, 2, 2, 2, 3]);
    assert_eq!(p.cue.focus, 1, "la lecture commence au premier slide du PowerPoint");
    assert_eq!(p.cue.entries[1].reference, "Annonces · 1/3");
    assert_eq!(p.cue.backgrounds[3].as_deref(), Some("s3.png"));
}
