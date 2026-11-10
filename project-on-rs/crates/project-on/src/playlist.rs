//! Les playlists, comme dans la 2.8 (`LibraryController`, `PlaylistTab`) : le genre de chaque
//! élément, le programme projeté depuis une playlist, l'ordre (sélection déplacée d'un cran,
//! glisser-déposer) et l'annulation (Ctrl+Z, 30 étapes, ajouts depuis les bibliothèques compris).
//!
//! Aucune interface ici : la page Playlist appelle ces fonctions, les essais aussi.

use std::sync::LazyLock;

use po_db::{Database, ItemSnapshot, PlaylistItem};
use po_design::SlideSource;
use po_program::{Cue, Entry};
use po_text::clean_text;
use regex::Regex;

use crate::icons::Icon;

/// Le genre d'un élément de playlist (`ITEM_KINDS` de la 2.8).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Kind {
    Bible,
    Hymn,
    Sermon,
    Expose,
    Image,
    Video,
    PowerPoint,
    Custom,
}

impl Kind {
    pub fn label(self) -> &'static str {
        match self {
            Kind::Bible => "Bible",
            Kind::Hymn => "Cantique",
            Kind::Sermon => "Sermon",
            Kind::Expose => "Exposé",
            Kind::Image => "Image",
            Kind::Video => "Vidéo",
            Kind::PowerPoint => "PowerPoint",
            Kind::Custom => "Slide",
        }
    }

    pub fn icon(self) -> Icon {
        match self {
            Kind::Bible => Icon::BookOpen,
            Kind::Hymn => Icon::Music,
            Kind::Sermon => Icon::Mic,
            Kind::Expose => Icon::FileText,
            Kind::Image => Icon::Image,
            Kind::Video => Icon::Play,
            Kind::PowerPoint => Icon::Presentation,
            Kind::Custom => Icon::Copy,
        }
    }

    /// Un média (image, vidéo, présentation) : projeté à partir de la phase 7.
    pub fn is_media(self) -> bool {
        matches!(self, Kind::Image | Kind::Video | Kind::PowerPoint)
    }
}

static SERMON_REF: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^\d{2}-\d{4}[A-Z]?\b|\bE-\d+\b|§").unwrap_or_else(|_| unreachable!()));
static EXPOSE_REF: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"·\s*Page\s+\d+|^Page\s+\d+\s*§").unwrap_or_else(|_| unreachable!()));
static HYMN_REF: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)cantique|strophe|refrain|ch(?:oe|œ)ur|chant").unwrap_or_else(|_| unreachable!()));
static BIBLE_REF: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\b\d+\s*:\s*\d+").unwrap_or_else(|_| unreachable!()));

/// Image, vidéo ou présentation, d'après l'extension (`media_kind` de la 2.8).
pub fn media_kind(path: &str) -> Kind {
    let ext =
        std::path::Path::new(path.trim()).extension().map(|e| e.to_string_lossy().to_lowercase()).unwrap_or_default();
    match ext.as_str() {
        "mp4" | "webm" | "mov" | "mkv" | "avi" => Kind::Video,
        "pptx" | "ppsx" => Kind::PowerPoint,
        _ => Kind::Image,
    }
}

/// Le genre d'un élément (`item_kind` de la 2.8) : celui enregistré, sinon (anciens éléments
/// « custom ») deviné d'après la référence.
pub fn item_kind(source: &str, reference: &str, background: &str) -> Kind {
    let source = source.trim().to_lowercase();
    match source.as_str() {
        "media" => return media_kind(background),
        "bible" => return Kind::Bible,
        "hymn" => return Kind::Hymn,
        "sermon" => return Kind::Sermon,
        "expose" => return Kind::Expose,
        "image" => return Kind::Image,
        "video" => return Kind::Video,
        "powerpoint" => return Kind::PowerPoint,
        _ => {}
    }
    if EXPOSE_REF.is_match(reference) {
        Kind::Expose
    } else if SERMON_REF.is_match(reference) {
        Kind::Sermon
    } else if HYMN_REF.is_match(reference) {
        Kind::Hymn
    } else if BIBLE_REF.is_match(reference) {
        Kind::Bible
    } else {
        Kind::Custom
    }
}

/// Le genre de slide d'un élément (il décide de l'identification de Branham et du filet). Un
/// paragraphe d'ouvrage dont la référence commence par le titre d'une biographie n'a pas
/// d'identification (décision 3).
pub fn slide_source(kind: Kind, reference: &str, biographies: &[String]) -> SlideSource {
    match kind {
        Kind::Bible => SlideSource::Bible,
        Kind::Hymn => SlideSource::Hymn,
        // « 47-0412 - Titre - ¶3 » : le code de date d'abord.
        Kind::Sermon => SlideSource::of_sermon_date(reference.split(" - ").next().unwrap_or("")),
        Kind::Expose => {
            if biographies.iter().any(|b| !b.is_empty() && reference.starts_with(b.as_str())) {
                SlideSource::Book
            } else {
                SlideSource::Expose
            }
        }
        _ => SlideSource::Custom,
    }
}

/// Le programme projeté depuis une playlist, et l'élément d'origine de chaque entrée.
#[derive(Debug, Clone, PartialEq)]
pub struct PlaylistProgram {
    pub cue: Cue,
    pub item_of_entry: Vec<i64>,
}

/// `on_playlist_play` de la 2.8 : toute la playlist, à partir de l'élément `start` (le premier si
/// `None` ou introuvable). Un élément sans texte est sauté. Le découpage est celui d'un texte
/// saisi, comme dans la 2.8 ; le genre de chaque élément décide de son identification.
///
/// Les médias (images, vidéos, PowerPoint) ne sont pas encore projetés (phase 7) : ils sont sautés.
pub fn program(
    title: &str,
    items: &[PlaylistItem],
    start: Option<i64>,
    biographies: &[String],
) -> Option<PlaylistProgram> {
    let mut entries = Vec::new();
    let mut kinds = Vec::new();
    let mut item_of_entry = Vec::new();
    for item in items {
        let kind = item_kind(&item.source, &item.reference, &item.background);
        if kind.is_media() && item.source == "media" {
            continue;
        }
        let reference = clean_text(if item.reference.is_empty() { title } else { &item.reference });
        let text = clean_text(&item.text);
        if text.is_empty() {
            continue;
        }
        kinds.push(slide_source(kind, &reference, biographies));
        entries.push(Entry { reference, text });
        item_of_entry.push(item.id);
    }
    if entries.is_empty() {
        return None;
    }
    let focus = start.and_then(|id| item_of_entry.iter().position(|i| *i == id)).unwrap_or(0);
    let mut cue = Cue::new(SlideSource::Custom, clean_text(title), entries, focus);
    cue.kinds = kinds;
    Some(PlaylistProgram { cue, item_of_entry })
}

/// Monte (`delta` < 0) ou descend d'un cran tous les éléments sélectionnés (`_move_selected`) :
/// un élément ne passe jamais par-dessus un autre élément sélectionné.
pub fn move_selection(order: &[i64], selected: &[i64], delta: i32) -> Vec<i64> {
    let mut order = order.to_vec();
    if delta == 0 {
        return order;
    }
    let n = order.len();
    let positions: Vec<usize> = if delta < 0 { (0..n).collect() } else { (0..n).rev().collect() };
    for i in positions {
        let j = if delta < 0 { i.checked_sub(1) } else { (i + 1 < n).then_some(i + 1) };
        if let Some(j) = j
            && selected.contains(&order[i])
            && !selected.contains(&order[j])
        {
            order.swap(i, j);
        }
    }
    order
}

/// Le glisser-déposer : les éléments sélectionnés (dans leur ordre) posés avant la ligne `at` de
/// l'ordre d'origine (`at` = longueur : à la fin).
pub fn drop_selection(order: &[i64], selected: &[i64], at: usize) -> Vec<i64> {
    let moving: Vec<i64> = order.iter().copied().filter(|id| selected.contains(id)).collect();
    let before = order[..at.min(order.len())].iter().filter(|id| !selected.contains(id)).count();
    let mut rest: Vec<i64> = order.iter().copied().filter(|id| !selected.contains(id)).collect();
    let tail = rest.split_off(before);
    rest.extend(moving);
    rest.extend(tail);
    rest
}

/// Un instantané de playlists, pris juste avant de les modifier.
type Snapshot = Vec<(i64, Vec<ItemSnapshot>)>;

/// Le nombre d'étapes d'annulation (`_UNDO_DEPTH`).
pub const UNDO_DEPTH: usize = 30;

/// L'annulation des modifications de playlists.
#[derive(Default)]
pub struct Undo {
    stack: Vec<Snapshot>,
}

impl Undo {
    pub fn available(&self) -> bool {
        !self.stack.is_empty()
    }

    pub fn len(&self) -> usize {
        self.stack.len()
    }

    pub fn is_empty(&self) -> bool {
        self.stack.is_empty()
    }

    /// Garde l'état des playlists touchées, juste avant de les modifier.
    pub fn remember(&mut self, db: &Database, folders: &[Option<i64>]) {
        let mut ids: Vec<i64> = folders.iter().flatten().copied().collect();
        ids.sort_unstable();
        ids.dedup();
        if ids.is_empty() {
            return;
        }
        if let Ok(snapshot) = db.snapshot_folders(&ids) {
            self.stack.push(snapshot);
            let excess = self.stack.len().saturating_sub(UNDO_DEPTH);
            self.stack.drain(..excess);
        }
    }

    /// Oublie la dernière étape (la modification n'a rien changé).
    pub fn drop_last(&mut self) {
        self.stack.pop();
    }

    /// Les étapes qui concernent une playlist supprimée ne peuvent plus s'appliquer.
    pub fn forget_folder(&mut self, folder: i64) {
        self.stack.retain(|s| s.iter().all(|(id, _)| *id != folder));
    }

    /// Remet les playlists dans l'état d'avant la dernière modification. Faux s'il n'y a plus rien
    /// à annuler.
    pub fn undo(&mut self, db: &mut Database) -> bool {
        while let Some(snapshot) = self.stack.pop() {
            if db.restore_folders(&snapshot).unwrap_or(false) {
                return true;
            }
        }
        false
    }
}

/// Les modifications de playlists, chacune annulable (comme `LibraryController`).
#[derive(Default)]
pub struct Playlists {
    pub undo: Undo,
}

impl Playlists {
    /// Une nouvelle playlist (nom nettoyé, jamais vide).
    pub fn create_folder(&mut self, db: &mut Database, name: &str) -> Option<i64> {
        let name = clean_text(name);
        if name.is_empty() {
            return None;
        }
        db.create_folder(&name).ok()
    }

    pub fn rename_folder(&mut self, db: &Database, folder: i64, name: &str) -> bool {
        let name = clean_text(name);
        !name.is_empty() && db.rename_folder(folder, &name).unwrap_or(false)
    }

    /// Supprime une playlist et ses éléments ; ses étapes d'annulation partent avec elle.
    pub fn delete_folder(&mut self, db: &Database, folder: i64) -> bool {
        self.undo.forget_folder(folder);
        db.delete_folder(folder).unwrap_or(false)
    }

    /// « Ajouter à la playlist » (`_commit_to_playlist`) : dans `folder`, ou dans une nouvelle
    /// playlist nommée `new_name`. Les entrées vides sont ignorées. Rend la playlist et les
    /// éléments ajoutés.
    pub fn add_entries(
        &mut self,
        db: &mut Database,
        folder: Option<i64>,
        new_name: &str,
        entries: &[Entry],
        source: &str,
    ) -> Option<(i64, Vec<i64>)> {
        let cleaned: Vec<(String, String, String)> = entries
            .iter()
            .map(|e| (source.to_string(), clean_text(&e.reference), clean_text(&e.text)))
            .filter(|(_, r, t)| !r.is_empty() || !t.is_empty())
            .collect();
        if cleaned.is_empty() {
            return None;
        }
        let folder = match folder {
            Some(f) => f,
            None => self.create_folder(db, new_name)?,
        };
        self.undo.remember(db, &[Some(folder)]);
        let ids = db.add_items(&cleaned, Some(folder)).ok()?;
        Some((folder, ids))
    }

    /// Un slide saisi (« Nouveau slide »).
    pub fn create_item(&mut self, db: &mut Database, folder: i64, reference: &str, text: &str) -> Option<i64> {
        self.undo.remember(db, &[Some(folder)]);
        db.add_item("custom", &clean_text(reference), &clean_text(text), Some(folder), "").ok()
    }

    pub fn update_item(&mut self, db: &Database, folder: i64, item: i64, reference: &str, text: &str) -> bool {
        self.undo.remember(db, &[Some(folder)]);
        db.update_item(item, &clean_text(reference), &clean_text(text)).unwrap_or(false)
    }

    pub fn delete_items(&mut self, db: &mut Database, folder: i64, items: &[i64]) -> usize {
        if items.is_empty() {
            return 0;
        }
        self.undo.remember(db, &[Some(folder)]);
        db.delete_items(items).unwrap_or(0)
    }

    /// Ctrl+D : chaque copie suit son original.
    pub fn duplicate(&mut self, db: &mut Database, folder: i64, items: &[i64]) -> Vec<i64> {
        if items.is_empty() {
            return Vec::new();
        }
        self.undo.remember(db, &[Some(folder)]);
        db.duplicate_items(items).unwrap_or_default()
    }

    /// Le nouvel ordre de toute la playlist (glisser-déposer, flèches). Un ordre périmé ne change
    /// rien et ne laisse pas d'étape d'annulation.
    pub fn reorder(&mut self, db: &mut Database, folder: i64, order: &[i64]) -> bool {
        self.undo.remember(db, &[Some(folder)]);
        let done = db.reorder_items(folder, order).unwrap_or(false);
        if !done {
            self.undo.drop_last();
        }
        done
    }

    /// Copie vers une autre playlist (à la fin, dans l'ordre d'origine).
    pub fn copy_to(&mut self, db: &mut Database, items: &[i64], destination: i64) -> Vec<i64> {
        if items.is_empty() {
            return Vec::new();
        }
        self.undo.remember(db, &[Some(destination)]);
        db.copy_items(items, destination).unwrap_or_default()
    }

    /// Déplace vers une autre playlist.
    pub fn move_to(&mut self, db: &mut Database, items: &[i64], from: i64, destination: i64) -> usize {
        if items.is_empty() {
            return 0;
        }
        self.undo.remember(db, &[Some(from), Some(destination)]);
        db.move_items_to_folder(items, destination).unwrap_or(0)
    }

    /// Ctrl+Z.
    pub fn undo(&mut self, db: &mut Database) -> bool {
        self.undo.undo(db)
    }
}

#[cfg(test)]
mod tests;
