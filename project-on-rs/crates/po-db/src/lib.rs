//! La base de données de Project-On : le même fichier SQLite que la 2.x, sans conversion.
//!
//! - [`Database::open`] en lecture seule ne modifie jamais rien (mesures, aperçus, essais).
//! - [`Database::open_and_initialize`] ouvre en écriture et met le schéma à jour comme
//!   `Database.initialize()` de la 2.8 : migrations 1 à 11, seulement additives, puis la maintenance
//!   (titres communs, repères, index de recherche) quand elle est nécessaire. Jamais de contrôle
//!   d'intégrité automatique au démarrage (leçon de la 2.6).
//! - Les requêtes reprennent celles de `app.database.dao_*` (2.8), qu'elles remplacent.

mod backup;
mod bible;
pub mod bibles;
mod hymns;
mod media;
mod playlist;
mod schema;
mod sermons;
mod service_plan;

use std::path::{Path, PathBuf};
use std::time::Duration;

use rusqlite::functions::{Context, FunctionFlags};
use rusqlite::types::ValueRef;
use rusqlite::{Connection, OpenFlags, OptionalExtension};

pub use backup::{BackupReport, copy_database};
pub use bible::{LegacyBook, Translation, TranslationBook, Verse};
pub use hymns::{Hymn, HymnHit, Stanza};
pub use media::MediaItem;
pub use playlist::{Folder, ItemSnapshot, NewItem, PlaylistItem};
pub use schema::{InitOptions, InitReport, SCHEMA_VERSION};
pub use sermons::{
    Book, BookChapter, BookHit, Paragraph, ParagraphHit, ParagraphSearch, Sermon, SermonFilter, SermonSort,
};
pub use service_plan::Section;

/// Les erreurs de la base, présentées en français à l'utilisateur par l'application.
#[derive(Debug, thiserror::Error)]
pub enum DbError {
    #[error("la base de données « {path} » est introuvable")]
    Missing { path: String },
    #[error(
        "la base de données est en version {found} ; Project-On attend la version {SCHEMA_VERSION} (ouvrez-la une fois en écriture pour la mettre à jour)"
    )]
    Outdated { found: i64 },
    #[error("un cantique doit avoir au moins une strophe")]
    EmptyHymn,
    #[error("la sauvegarde doit être un autre fichier que la base active")]
    SameFile,
    #[error("la base est verrouillée par un autre programme : la copie n'avance plus")]
    Busy,
    #[error("la copie de la base a échoué au contrôle d'intégrité : {0}")]
    BadCopy(String),
    #[error("erreur d'accès au fichier : {0}")]
    Io(#[from] std::io::Error),
    #[error("erreur SQLite : {0}")]
    Sqlite(#[from] rusqlite::Error),
}

pub type Result<T> = std::result::Result<T, DbError>;

/// Comment ouvrir la base.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    /// Lecture seule : rien ne peut être écrit, même par erreur (mesures, aperçus).
    ReadOnly,
    /// Écriture, sans migration (essais) : préférer [`Database::open_and_initialize`].
    ReadWrite,
}

/// La connexion à la base.
pub struct Database {
    conn: Connection,
    path: PathBuf,
}

impl Database {
    /// Ouvre une base existante. En lecture seule, elle doit déjà être au schéma 11.
    pub fn open(path: &Path, mode: Mode) -> Result<Self> {
        if !path.is_file() {
            return Err(DbError::Missing { path: path.display().to_string() });
        }
        let flags = match mode {
            Mode::ReadOnly => OpenFlags::SQLITE_OPEN_READ_ONLY,
            Mode::ReadWrite => OpenFlags::SQLITE_OPEN_READ_WRITE,
        } | OpenFlags::SQLITE_OPEN_NO_MUTEX
            | OpenFlags::SQLITE_OPEN_URI;
        let db = Self::with_connection(Connection::open_with_flags(path, flags)?, path, mode)?;
        if mode == Mode::ReadOnly {
            let found = db.schema_version()?;
            if found < SCHEMA_VERSION {
                return Err(DbError::Outdated { found });
            }
        }
        Ok(db)
    }

    /// Ouvre (ou crée) la base en écriture et met son schéma à jour, comme au lancement de la 2.8.
    pub fn open_and_initialize(path: &Path, options: &InitOptions) -> Result<(Self, InitReport)> {
        if let Some(dir) = path.parent() {
            std::fs::create_dir_all(dir)?;
        }
        let flags = OpenFlags::SQLITE_OPEN_READ_WRITE
            | OpenFlags::SQLITE_OPEN_CREATE
            | OpenFlags::SQLITE_OPEN_NO_MUTEX
            | OpenFlags::SQLITE_OPEN_URI;
        let mut db = Self::with_connection(Connection::open_with_flags(path, flags)?, path, Mode::ReadWrite)?;
        let report = schema::initialize(&mut db.conn, options)?;
        Ok((db, report))
    }

    fn with_connection(conn: Connection, path: &Path, mode: Mode) -> Result<Self> {
        conn.busy_timeout(Duration::from_secs(30))?;
        register_unaccent(&conn)?;
        // Mêmes réglages que la 2.x (connection.py).
        if mode == Mode::ReadWrite {
            conn.execute_batch("PRAGMA foreign_keys = ON;")?;
            // Une base en mémoire répond « memory » : sans importance.
            let _: String = conn.query_row("PRAGMA journal_mode = WAL", [], |r| r.get(0))?;
            conn.execute_batch("PRAGMA synchronous = NORMAL;")?;
        }
        conn.execute_batch("PRAGMA temp_store = MEMORY; PRAGMA cache_size = -64000; PRAGMA mmap_size = 268435456;")?;
        Ok(Database { conn, path: path.to_path_buf() })
    }

    /// Le fichier de la base.
    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Le numéro de version du schéma (`PRAGMA user_version`).
    pub fn schema_version(&self) -> Result<i64> {
        Ok(self.conn.query_row("PRAGMA user_version", [], |r| r.get(0))?)
    }

    /// Une valeur de `app_meta` (repères de maintenance, version du pack de données).
    pub fn meta(&self, key: &str) -> Result<Option<String>> {
        if !table_exists(&self.conn, "app_meta")? {
            return Ok(None);
        }
        Ok(self.conn.query_row("SELECT value FROM app_meta WHERE key = ?", [key], |r| r.get(0)).optional()?)
    }

    /// La connexion, pour les essais et les outils de mesure.
    pub fn connection(&self) -> &Connection {
        &self.conn
    }
}

pub(crate) fn table_exists(conn: &Connection, table: &str) -> rusqlite::Result<bool> {
    conn.query_row("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", [table], |_| Ok(()))
        .optional()
        .map(|found| found.is_some())
}

pub(crate) fn columns(conn: &Connection, table: &str) -> rusqlite::Result<Vec<String>> {
    let mut stmt = conn.prepare("SELECT name FROM pragma_table_info(?)")?;
    let rows = stmt.query_map([table], |r| r.get(0))?;
    rows.collect()
}

/// `language[:2].lower()` de la 2.8.
pub(crate) fn language_code(language: &str) -> String {
    po_text::py::prefix(language, 2).to_lowercase()
}

/// `unaccent()` dans SQLite, lue sur place : mêmes règles que l'extension de la 2.8 (NULL, 0 et ""
/// donnent "" ; un nombre est d'abord converti en texte).
fn register_unaccent(conn: &Connection) -> rusqlite::Result<()> {
    conn.create_scalar_function(
        "unaccent",
        1,
        FunctionFlags::SQLITE_UTF8 | FunctionFlags::SQLITE_DETERMINISTIC | FunctionFlags::SQLITE_INNOCUOUS,
        |ctx: &Context<'_>| {
            Ok(match ctx.get_raw(0) {
                ValueRef::Null | ValueRef::Integer(0) | ValueRef::Real(0.0) | ValueRef::Blob([]) => String::new(),
                ValueRef::Text(bytes) | ValueRef::Blob(bytes) => po_text::fold(&String::from_utf8_lossy(bytes)),
                ValueRef::Integer(i) => i.to_string(),
                ValueRef::Real(f) => po_text::fold(&f.to_string()),
            })
        },
    )
}

#[cfg(test)]
pub(crate) mod testing {
    use super::*;

    /// Une base neuve au schéma de la 2.8, en mémoire, sans données de démonstration.
    pub fn empty() -> Database {
        let conn = Connection::open_in_memory().unwrap();
        let mut db = Database::with_connection(conn, Path::new(":memory:"), Mode::ReadWrite).unwrap();
        schema::migrate(&mut db.conn).unwrap();
        db
    }
}
