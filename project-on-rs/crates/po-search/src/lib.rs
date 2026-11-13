//! Les recherches, sur un fil à part avec sa propre connexion (en lecture seule) : la recherche
//! plein texte peut prendre plusieurs secondes au premier appel, l'interface ne l'attend jamais.
//! Partagée par Project-On (`project_on::search`) et MEDITATION (son onglet Recherche) : les deux
//! trouvent les mêmes résultats.
//!
//! La recherche globale (Ctrl+K) est celle de la 2.8 (`app/utils/global_search.py`) : la Bible
//! (une référence tapée, sinon les versets de la traduction choisie), les prédications (titres,
//! puis paragraphes) et les livres. Les cantiques en sont exclus, comme dans la 2.8 ; les médias et
//! les playlists arriveront avec leurs phases.

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::mpsc::{Receiver, Sender, channel};

use po_db::{BookHit, Database, Hymn, HymnHit, Mode, ParagraphHit, ParagraphSearch, SermonFilter};
use po_text::{fold, looks_like_reference, parse_reference};

/// Moins de caractères : pas de recherche (titres, références).
pub const MIN_QUERY: usize = 2;
/// Moins de caractères : pas de recherche plein texte (versets, paragraphes).
pub const MIN_TEXT_QUERY: usize = 3;
/// Résultats par bibliothèque dans la recherche globale.
pub const PER_KIND: usize = 5;

/// Où mène un résultat.
#[derive(Debug, Clone, PartialEq)]
pub enum Target {
    Verse {
        translation: i64,
        book: i64,
        chapter: i64,
        verse: Option<i64>,
    },
    Sermon {
        sermon_id: i64,
        reference: Option<String>,
    },
    /// Un paragraphe d'ouvrage : son chapitre (une ligne de la table `sermon`) et sa référence brute.
    Book {
        chapter_id: i64,
        raw_ref: Option<String>,
    },
}

/// Un résultat de recherche.
#[derive(Debug, Clone, PartialEq)]
pub struct Hit {
    pub kind: Kind,
    pub title: String,
    pub subtitle: String,
    pub target: Target,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Kind {
    Bible,
    Sermon,
    Book,
}

impl Kind {
    pub fn label(self) -> &'static str {
        match self {
            Kind::Bible => "Bible",
            Kind::Sermon => "Prédications",
            Kind::Book => "Livres",
        }
    }
}

/// Une recherche demandée.
#[derive(Debug, Clone, PartialEq)]
pub enum Request {
    Global {
        query: String,
        translation: Option<i64>,
    },
    /// Ctrl+G : les paragraphes de toutes les prédications.
    Paragraphs {
        query: String,
        translator: Option<String>,
    },
    /// Les versets d'une traduction.
    Verses {
        query: String,
        translation: i64,
    },
    /// Les strophes des cantiques.
    Stanzas {
        query: String,
    },
    /// Les paragraphes d'un ouvrage.
    Book {
        query: String,
        key: String,
    },
}

impl Request {
    /// Deux demandes du même genre : seule la dernière compte.
    fn slot(&self) -> u8 {
        match self {
            Request::Global { .. } => 0,
            Request::Paragraphs { .. } => 1,
            Request::Verses { .. } => 2,
            Request::Stanzas { .. } => 3,
            Request::Book { .. } => 4,
        }
    }
}

/// Une réponse.
#[derive(Debug, Clone)]
pub enum Response {
    Global { query: String, hits: Vec<Hit> },
    Paragraphs { query: String, hits: Vec<ParagraphHit> },
    Verses { query: String, hits: Vec<Hit> },
    Stanzas { query: String, hits: Vec<HymnHit> },
    Book { query: String, key: String, hits: Vec<BookHit> },
}

/// Un verset indexé : livre, chapitre, verset, texte, texte plié (sans accents, minuscules).
type IndexedVerse = (i64, i64, i64, String, String);

/// L'état du fil de recherche.
pub struct Searcher {
    db: Database,
    /// Les versets de chaque traduction, pliés une fois (31 000 versets : la 2.8 en faisait autant).
    verses: HashMap<i64, Vec<IndexedVerse>>,
}

/// `text` sur une ligne, coupé à `limit` lettres (« … »).
pub fn one_line(text: &str, limit: usize) -> String {
    let flat = text.split_whitespace().collect::<Vec<_>>().join(" ");
    if flat.chars().count() <= limit {
        flat
    } else {
        format!("{}…", flat.chars().take(limit - 1).collect::<String>())
    }
}

impl Searcher {
    pub fn new(db: Database) -> Self {
        Searcher { db, verses: HashMap::new() }
    }

    /// La base où il cherche (pour les recherches qu'il n'enveloppe pas).
    pub fn database(&self) -> &Database {
        &self.db
    }

    fn verse_index(&mut self, translation: i64) -> &[IndexedVerse] {
        if !self.verses.contains_key(&translation) {
            let mut index = Vec::new();
            if let Ok(books) = self.db.list_translation_books(translation) {
                for book in books {
                    for chapter in self.db.list_translation_chapters(translation, book.id).unwrap_or_default() {
                        for v in self.db.list_translation_verses(translation, book.id, chapter).unwrap_or_default() {
                            let folded = fold(&v.text).to_lowercase();
                            index.push((book.id, chapter, v.verse, v.text, folded));
                        }
                    }
                }
            }
            self.verses.insert(translation, index);
        }
        self.verses.get(&translation).map(Vec::as_slice).unwrap_or_default()
    }

    /// Les versets contenant `query` (sans accents ni casse), au plus `limit`.
    pub fn verses(&mut self, query: &str, translation: i64, limit: usize) -> Vec<Hit> {
        let names: HashMap<i64, String> = self
            .db
            .list_translation_books(translation)
            .unwrap_or_default()
            .into_iter()
            .map(|b| (b.id, b.name))
            .collect();
        let needle = fold(&query.split_whitespace().collect::<Vec<_>>().join(" ")).to_lowercase();
        if needle.chars().count() < MIN_TEXT_QUERY {
            return Vec::new();
        }
        self.verse_index(translation)
            .iter()
            .filter(|v| v.4.contains(&needle))
            .take(limit)
            .map(|(book, chapter, verse, text, _)| Hit {
                kind: Kind::Bible,
                title: format!("{} {chapter}:{verse}", names.get(book).cloned().unwrap_or_else(|| book.to_string())),
                subtitle: one_line(text, 140),
                target: Target::Verse { translation, book: *book, chapter: *chapter, verse: Some(*verse) },
            })
            .collect()
    }

    fn bible(&mut self, query: &str, translation: Option<i64>) -> Vec<Hit> {
        self.bible_hits(query, translation, PER_KIND)
    }

    /// La Bible : une référence tapée (« Jean 3:16 »), sinon au plus `limit` versets de la
    /// traduction `translation` qui contiennent `query`.
    pub fn bible_hits(&mut self, query: &str, translation: Option<i64>, limit: usize) -> Vec<Hit> {
        let Some(tid) = translation else { return Vec::new() };
        let books: Vec<po_text::Book> = self
            .db
            .list_translation_books(tid)
            .unwrap_or_default()
            .into_iter()
            .map(|b| po_text::Book { id: b.id, name: b.name })
            .collect();
        if let Some(r) = parse_reference(query, &books) {
            let mut subtitle = "Ouvrir le chapitre".to_string();
            if let Some(verse) = r.verse {
                let verses = self.db.list_translation_verses(tid, r.book_id, i64::from(r.chapter)).unwrap_or_default();
                if let Some(v) = verses.iter().find(|v| v.verse == i64::from(verse)) {
                    subtitle = one_line(&v.text, 140);
                }
            }
            return vec![Hit {
                kind: Kind::Bible,
                title: r.label(),
                subtitle,
                target: Target::Verse {
                    translation: tid,
                    book: r.book_id,
                    chapter: i64::from(r.chapter),
                    verse: r.verse.map(i64::from),
                },
            }];
        }
        if query.trim().chars().count() < MIN_TEXT_QUERY {
            return Vec::new();
        }
        self.verses(query, tid, limit)
    }

    fn sermons(&mut self, query: &str) -> Vec<Hit> {
        let q = query.trim();
        let filter = SermonFilter { language: Some("fr"), title: Some(q), limit: Some(PER_KIND), ..Default::default() };
        let mut hits: Vec<Hit> = self
            .db
            .list_sermons(&filter)
            .unwrap_or_default()
            .into_iter()
            .map(|s| {
                let date = if s.printed_date.is_empty() { s.date.clone().unwrap_or_default() } else { s.printed_date };
                Hit {
                    kind: Kind::Sermon,
                    title: s.title,
                    subtitle: if date.is_empty() { "Prédication".into() } else { format!("Prédication · {date}") },
                    target: Target::Sermon { sermon_id: s.id, reference: None },
                }
            })
            .collect();
        if q.chars().count() >= MIN_TEXT_QUERY && !looks_like_reference(q) {
            let search = ParagraphSearch {
                query: q,
                language: Some("fr"),
                translator: None,
                limit: PER_KIND,
                substring_fallback: false,
            };
            hits.extend(self.db.search_paragraphs(&search).unwrap_or_default().into_iter().map(|p| Hit {
                kind: Kind::Sermon,
                title: format!("{} {}", p.sermon_title, p.marker).trim().to_string(),
                subtitle: one_line(&p.text, 140),
                target: Target::Sermon { sermon_id: p.sermon_id, reference: Some(p.reference) },
            }));
        }
        hits
    }

    fn books(&mut self, query: &str) -> Vec<Hit> {
        let q = query.trim();
        if q.chars().count() < MIN_TEXT_QUERY || looks_like_reference(q) {
            return Vec::new();
        }
        self.db
            .search_book(q, "ages-vgr", PER_KIND)
            .unwrap_or_default()
            .into_iter()
            .map(|p| {
                let title =
                    [p.title.as_str(), p.marker.as_str()].into_iter().filter(|s| !s.is_empty()).collect::<Vec<_>>();
                let title = if title.is_empty() { p.reference.clone() } else { title.join(" · ") };
                Hit {
                    kind: Kind::Book,
                    title,
                    subtitle: one_line(&p.text, 140),
                    target: Target::Book { chapter_id: p.sermon_id, raw_ref: p.raw_ref },
                }
            })
            .collect()
    }

    /// La recherche globale : Bible, prédications, livres, dans cet ordre.
    pub fn global(&mut self, query: &str, translation: Option<i64>) -> Vec<Hit> {
        let q = query.trim();
        if q.chars().count() < MIN_QUERY {
            return Vec::new();
        }
        let mut hits = self.bible(q, translation);
        hits.extend(self.sermons(q));
        hits.extend(self.books(q));
        hits
    }

    pub fn run(&mut self, request: Request) -> Response {
        match request {
            Request::Global { query, translation } => {
                let hits = self.global(&query, translation);
                Response::Global { query, hits }
            }
            Request::Paragraphs { query, translator } => {
                let search = ParagraphSearch {
                    query: &query,
                    language: Some("fr"),
                    translator: translator.as_deref(),
                    limit: 200,
                    substring_fallback: true,
                };
                let hits = if query.trim().chars().count() < MIN_TEXT_QUERY {
                    Vec::new()
                } else {
                    self.db.search_paragraphs(&search).unwrap_or_default()
                };
                Response::Paragraphs { query, hits }
            }
            Request::Verses { query, translation } => {
                let hits = self.verses(&query, translation, 200);
                Response::Verses { query, hits }
            }
            Request::Stanzas { query } => {
                let hits = if query.trim().chars().count() < MIN_TEXT_QUERY {
                    Vec::new()
                } else {
                    self.db.search_stanzas(&query, 200).unwrap_or_default()
                };
                Response::Stanzas { query, hits }
            }
            Request::Book { query, key } => {
                let hits = if query.trim().chars().count() < MIN_TEXT_QUERY {
                    Vec::new()
                } else {
                    self.db.search_book(&query, &key, 200).unwrap_or_default()
                };
                Response::Book { query, key, hits }
            }
        }
    }
}

/// Le fil de recherche.
pub struct SearchThread {
    requests: Sender<Request>,
    responses: Receiver<Response>,
}

impl SearchThread {
    /// Ouvre sa propre connexion à `db_path` ; `wake` est appelé après chaque réponse.
    pub fn spawn(db_path: PathBuf, wake: impl Fn() + Send + 'static) -> Self {
        let (requests, inbox) = channel::<Request>();
        let (outbox, responses) = channel::<Response>();
        let spawned = std::thread::Builder::new().name("recherche".into()).spawn(move || {
            let Ok(db) = Database::open(&db_path, Mode::ReadOnly) else { return };
            let mut searcher = Searcher::new(db);
            while let Ok(first) = inbox.recv() {
                let mut latest: Vec<Request> = vec![first];
                for r in inbox.try_iter() {
                    latest.retain(|l| l.slot() != r.slot());
                    latest.push(r);
                }
                for request in latest {
                    if outbox.send(searcher.run(request)).is_err() {
                        return;
                    }
                    wake();
                }
            }
        });
        if let Err(e) = spawned {
            po_core::journal::line(&format!("fil de recherche impossible : {e}"));
        }
        SearchThread { requests, responses }
    }

    pub fn ask(&self, request: Request) {
        let _ = self.requests.send(request);
    }

    pub fn answers(&self) -> Vec<Response> {
        self.responses.try_iter().collect()
    }
}

/// Les cantiques dont le numéro ou le titre contient `query` (dans l'interface : quelques ms).
pub fn hymns(db: &Database, query: &str) -> Vec<Hymn> {
    db.list_hymns(None, None, Some(query.trim())).unwrap_or_default()
}
