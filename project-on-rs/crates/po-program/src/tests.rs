//! Les cas de base ; la comparaison complète avec la 2.8 est dans `po-parite programme`.

use super::*;

fn para(no: i64, marker: &str, text: &str) -> Paragraph {
    Paragraph { paragraph_no: no, marker: marker.into(), raw_ref: None, text: text.into() }
}

#[test]
fn a_click_prepares_the_whole_sermon_from_the_paragraph() {
    let paragraphs = [para(1, "¶1", "Premier."), para(2, "¶2", "Deuxième."), para(3, "¶3", "Troisième.")];
    let entries = sermon_entries(&paragraphs, "63-0317M", "Le Dévoilement de Dieu");
    assert_eq!(entries[1].reference, "63-0317M - Le Dévoilement de Dieu - ¶2");
    let focus = find_entry(&entries, "63-0317M - Le Dévoilement de Dieu - ¶2");
    let cue = Cue::new(SlideSource::Sermon, program_title("63-0317M", "Le Dévoilement de Dieu"), entries, focus);
    let mut program = Program::from_cue(&cue, &SplitSettings::default()).unwrap();
    assert_eq!(program.title, "63-0317M - Le Dévoilement de Dieu");
    assert_eq!(program.slide().text, "Deuxième.");
    assert!(program.next_slide());
    assert_eq!(program.slide().text, "Troisième.");
    assert!(!program.next_slide(), "rien après le dernier slide");
    assert!(program.edge(true));
    assert_eq!(program.slide().text, "Premier.");
    assert!(!program.prev_slide());
}

#[test]
fn alineas_of_one_paragraph_become_one_entry() {
    let paragraphs = [para(5, "§5", "Ligne une."), para(5, "§5", "Ligne deux."), para(6, "§6", "Autre.")];
    let entries = sermon_entries(&paragraphs, "64-0119", "Titre");
    assert_eq!(entries.len(), 2);
    assert_eq!(entries[0].text, "Ligne une.\nLigne deux.");
    assert_eq!(sermon_entries(&[para(7, "", "Sans repère.")], "", "Titre")[0].reference, "Titre - ¶7");
}

#[test]
fn long_texts_become_numbered_parts() {
    let long = "Une phrase assez longue pour remplir une partie entière du découpage. ".repeat(12);
    let cue = Cue::new(SlideSource::Sermon, "T", vec![Entry::new("Réf", long)], 0);
    let program = Program::from_cue(&cue, &SplitSettings::default()).unwrap();
    assert!(program.len() > 1);
    let total = program.len();
    assert_eq!(program.slides[0].reference, format!("Réf (1/{total})"));
    let quiet = SplitSettings { show_part_counter: false, ..SplitSettings::default() };
    let program = Program::from_cue(&cue, &quiet).unwrap();
    assert_eq!(program.slides[0].reference, "Réf");
}

#[test]
fn hymns_repeat_a_single_chorus_and_show_the_title_on_its_own_line() {
    let stanza =
        |no, chorus, text: &str| Stanza { stanza_no: no, label: String::new(), is_chorus: chorus, text: text.into() };
    let stanzas = [stanza(1, false, "Strophe un"), stanza(2, true, "Le refrain"), stanza(3, false, "Strophe deux")];
    let prepared = prepare_stanzas(&stanzas, "12", "Grâce infinie");
    assert_eq!(prepared[1].reference, "12 - Grâce infinie - Refrain");
    let entries = hymn_entries(&prepared, true);
    let labels: Vec<_> = entries.iter().map(|e| e.reference.rsplit(" - ").next().unwrap().to_string()).collect();
    assert_eq!(labels, ["Strophe 1", "Refrain", "Strophe 2", "Refrain"]);
    let cue = Cue::new(SlideSource::Hymn, "12 - Grâce infinie", entries, 0);
    let program = Program::from_cue(&cue, &SplitSettings::default()).unwrap();
    assert_eq!(program.slide().reference, "12\nGrâce infinie - Strophe 1");
}

#[test]
fn bible_and_book_references() {
    let verses = [Verse { verse: 16, text: "Car Dieu a tant aimé le monde".into() }];
    assert_eq!(bible_entries(&verses, "Jean", 3)[0].reference, "Jean 3:16");
    let ages = Book {
        key: "ages-vgr".into(),
        title: "Exposé…".into(),
        date_prefix: "BK-AGES-CH".into(),
        tradition: "VGR".into(),
    };
    let full = book_reference(Some(&ages), "L'Âge d'Éphèse");
    assert_eq!(full, "Exposé des Sept Âges — L'Âge d'Éphèse");
    let p = Paragraph { paragraph_no: 3, marker: "".into(), raw_ref: Some("BK 40-3".into()), text: "Texte".into() };
    assert_eq!(book_entries(&[p], &full)[0].reference, "Exposé des Sept Âges — L'Âge d'Éphèse · Page 40 §3");
    let brochure =
        Book { key: "brochures".into(), title: "Brochures".into(), date_prefix: "TR-".into(), tradition: "VGR".into() };
    assert_eq!(book_reference(Some(&brochure), "Le Signe"), "Le Signe");
}

#[test]
fn empty_entries_give_no_program() {
    let cue = Cue::new(SlideSource::Bible, "Vide", vec![Entry::new("Jean 1:1", "   ")], 0);
    assert!(Program::from_cue(&cue, &SplitSettings::default()).is_none());
}
