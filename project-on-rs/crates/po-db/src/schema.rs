//! Le schéma : migrations 1 à 11, tables assurées à chaque lancement, maintenance des métadonnées
//! de recherche, comme `Database.initialize()` de la 2.8 (`app/database/connection.py`).
//!
//! Le texte SQL est celui de la 2.8, espaces compris : SQLite garde ce texte dans `sqlite_master`,
//! et une base créée par la 3.0 est ainsi identique à une base créée par la 2.8.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use po_core::pyval::{to_int, to_str, truthy};
use rusqlite::{Connection, OptionalExtension, params};
use serde_json::Value;

use crate::{Result, columns, table_exists};

/// La version du schéma (`PRAGMA user_version`) que cette version de Project-On attend.
pub const SCHEMA_VERSION: i64 = 11;

const STARTUP_MAINTENANCE_KEY: &str = "startup_maintenance_version";
const STARTUP_MAINTENANCE_VERSION: &str = "11";
const VACUUM_KEY: &str = "vacuum_version";
const VACUUM_VERSION: &str = "2";

/// D'où viennent les données à importer pendant la maintenance.
#[derive(Debug, Clone, Default)]
pub struct InitOptions {
    /// Les Bibles livrées en JSON (`bible_json/` de l'installation), importées sur une base neuve.
    pub bible_json_dir: Option<PathBuf>,
}

/// Ce que la mise à jour a fait.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct InitReport {
    /// La version du schéma avant la mise à jour (0 pour une base neuve).
    pub from_version: i64,
    /// Des index inutiles ont été supprimés.
    pub indexes_dropped: bool,
    /// La maintenance (titres communs, repères, index de recherche) a tourné.
    pub maintenance_ran: bool,
    /// La base a été compactée (VACUUM).
    pub vacuumed: bool,
}

fn get_meta(conn: &Connection, key: &str) -> Option<String> {
    conn.query_row("SELECT value FROM app_meta WHERE key = ?", [key], |r| r.get::<_, String>(0))
        .optional()
        .ok()
        .flatten()
}

fn set_meta(conn: &Connection, key: &str, value: &str) -> rusqlite::Result<()> {
    conn.execute(
        "
            INSERT INTO app_meta (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            ",
        params![key, value],
    )
    .map(|_| ())
}

fn user_version(conn: &Connection) -> rusqlite::Result<i64> {
    conn.query_row("PRAGMA user_version;", [], |r| r.get(0))
}

fn set_user_version(conn: &Connection, version: i64) -> rusqlite::Result<()> {
    conn.execute_batch(&format!("PRAGMA user_version = {version};"))
}

/// Une migration : elle mène le schéma à la version qui l'accompagne.
type Migration = fn(&Connection) -> rusqlite::Result<()>;

/// Les migrations et les tables assurées à chaque lancement, sans la maintenance.
pub(crate) fn migrate(conn: &mut Connection) -> Result<i64> {
    let tx = conn.transaction()?;
    tx.execute_batch(
        "
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            ",
    )?;
    let from = user_version(&tx)?;
    let mut version = from;
    if version == 0 {
        tx.execute_batch(MIGRATION_V1)?;
        version = 1;
        set_user_version(&tx, 1)?;
    }
    let steps: [(i64, Migration); 10] = [
        (2, |c| c.execute_batch(MIGRATION_V2)),
        (3, ensure_playlist_base_tables),
        (4, migration_v4),
        (5, migration_v5),
        (6, migration_v6),
        (7, migration_v7),
        (8, migration_v8),
        (9, migration_v9),
        (10, migration_v10),
        (11, ensure_library_books),
    ];
    for (target, step) in steps {
        if version < target {
            step(&tx)?;
            set_user_version(&tx, target)?;
            version = target;
        }
    }
    ensure_playlist_base_tables(&tx)?;
    ensure_service_plan_tables(&tx)?;
    ensure_media_tables(&tx)?;
    ensure_library_books(&tx)?;
    tx.commit()?;
    Ok(from)
}

/// `Database.initialize()` : migrations, puis maintenance et compactage si besoin.
pub(crate) fn initialize(conn: &mut Connection, options: &InitOptions) -> Result<InitReport> {
    let from_version = migrate(conn)?;
    let tx = conn.transaction()?;
    let indexes_dropped = drop_obsolete_indexes(&tx);
    let mut maintenance_ran = false;
    if startup_maintenance_needed(&tx)? {
        seed_demo_data_if_empty(&tx)?;
        ensure_sermon_title_metadata(&tx)?;
        ensure_sermon_paragraph_markers(&tx)?;
        ensure_sermon_fts(&tx)?;
        ensure_hymn_title_metadata(&tx)?;
        ensure_hymn_stanza_labels(&tx)?;
        ensure_hymn_fts(&tx)?;
        if let Some(dir) = &options.bible_json_dir {
            import_bible_json_translations(&tx, dir)?;
        }
        set_meta(&tx, STARTUP_MAINTENANCE_KEY, STARTUP_MAINTENANCE_VERSION)?;
        maintenance_ran = true;
    }
    let vacuum_needed =
        (maintenance_ran || indexes_dropped) && get_meta(&tx, VACUUM_KEY).as_deref() != Some(VACUUM_VERSION);
    tx.commit()?;

    // Le VACUUM se fait hors transaction ; il récupère la place libérée par la reconstruction des
    // index. Le repère n'est posé qu'en cas de succès, pour réessayer au lancement suivant.
    let mut vacuumed = false;
    if vacuum_needed {
        conn.busy_timeout(std::time::Duration::from_secs(60))?;
        let compacted = conn.execute_batch("PRAGMA wal_checkpoint(TRUNCATE); VACUUM;");
        conn.busy_timeout(std::time::Duration::from_secs(30))?;
        match compacted {
            Ok(()) => {
                set_meta(conn, VACUUM_KEY, VACUUM_VERSION)?;
                vacuumed = true;
            }
            Err(e) => po_core::journal::line(&format!("Échec du VACUUM — sera retenté au prochain démarrage : {e}")),
        }
    }
    Ok(InitReport { from_version, indexes_dropped, maintenance_ran, vacuumed })
}

const MIGRATION_V1: &str = "
            CREATE TABLE IF NOT EXISTS bible_book (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                abbreviation TEXT,
                testament TEXT,
                sort_order INTEGER
            );

            CREATE TABLE IF NOT EXISTS bible_verse (
                id INTEGER PRIMARY KEY,
                book_id INTEGER NOT NULL,
                chapter INTEGER NOT NULL,
                verse INTEGER NOT NULL,
                text TEXT NOT NULL,
                FOREIGN KEY (book_id) REFERENCES bible_book (id) ON DELETE CASCADE,
                UNIQUE (book_id, chapter, verse)
            );

            CREATE INDEX IF NOT EXISTS idx_bible_verse_book_chapter
                ON bible_verse (book_id, chapter);


            CREATE TABLE IF NOT EXISTS sermon (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                date TEXT,
                tradition TEXT NOT NULL,
                language TEXT,
                source_path TEXT,
                sort_key TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_sermon_tradition
                ON sermon (tradition);

            CREATE INDEX IF NOT EXISTS idx_sermon_sort
                ON sermon (sort_key, date);


            CREATE TABLE IF NOT EXISTS sermon_paragraph (
                id INTEGER PRIMARY KEY,
                sermon_id INTEGER NOT NULL,
                paragraph_no INTEGER NOT NULL,
                ref TEXT,
                text TEXT NOT NULL,
                FOREIGN KEY (sermon_id) REFERENCES sermon (id) ON DELETE CASCADE,
                UNIQUE (sermon_id, paragraph_no)
            );

            CREATE INDEX IF NOT EXISTS idx_sermon_paragraph_sermon
                ON sermon_paragraph (sermon_id, paragraph_no);


            CREATE TABLE IF NOT EXISTS hymn (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                number TEXT,
                language TEXT,
                sort_key TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_hymn_sort
                ON hymn (sort_key, number);


            CREATE TABLE IF NOT EXISTS hymn_stanza (
                id INTEGER PRIMARY KEY,
                hymn_id INTEGER NOT NULL,
                stanza_no INTEGER NOT NULL,
                text TEXT NOT NULL,
                FOREIGN KEY (hymn_id) REFERENCES hymn (id) ON DELETE CASCADE,
                UNIQUE (hymn_id, stanza_no)
            );

            CREATE INDEX IF NOT EXISTS idx_hymn_stanza_hymn
                ON hymn_stanza (hymn_id, stanza_no);
            ";

const MIGRATION_V2: &str = "
            CREATE TABLE IF NOT EXISTS bible_translation (
                id INTEGER PRIMARY KEY,
                module TEXT NOT NULL UNIQUE,
                name TEXT,
                shortname TEXT,
                lang TEXT
            );

            CREATE TABLE IF NOT EXISTS bible_translation_verse (
                id INTEGER PRIMARY KEY,
                translation_id INTEGER NOT NULL,
                book INTEGER NOT NULL,
                book_name TEXT,
                chapter INTEGER NOT NULL,
                verse INTEGER NOT NULL,
                text TEXT NOT NULL,
                FOREIGN KEY (translation_id) REFERENCES bible_translation (id) ON DELETE CASCADE,
                UNIQUE (translation_id, book, chapter, verse)
            );

            CREATE INDEX IF NOT EXISTS idx_bible_translation_verse_ref
                ON bible_translation_verse (translation_id, book, chapter);
            ";

/// Migration 3, rejouée à chaque lancement : les tables de la playlist.
fn ensure_playlist_base_tables(conn: &Connection) -> rusqlite::Result<()> {
    conn.execute_batch(
        "
            CREATE TABLE IF NOT EXISTS playlist_folder (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_playlist_folder_sort
                ON playlist_folder (sort_order);

            CREATE TABLE IF NOT EXISTS playlist_item (
                id INTEGER PRIMARY KEY,
                folder_id INTEGER,
                source TEXT NOT NULL,
                reference TEXT NOT NULL,
                text TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (folder_id) REFERENCES playlist_folder (id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_playlist_item_folder
                ON playlist_item (folder_id, sort_order);
            ",
    )
}

/// Ajoute une colonne si elle manque (les migrations sont rejouables).
fn add_column(conn: &Connection, table: &str, column: &str, sql: &str) -> rusqlite::Result<()> {
    if !columns(conn, table)?.iter().any(|c| c == column) {
        conn.execute_batch(sql)?;
    }
    Ok(())
}

fn migration_v4(conn: &Connection) -> rusqlite::Result<()> {
    add_column(conn, "sermon", "location", "ALTER TABLE sermon ADD COLUMN location TEXT DEFAULT ''")?;
    add_column(conn, "sermon", "sort_key", "ALTER TABLE sermon ADD COLUMN sort_key TEXT DEFAULT ''")
}

fn migration_v5(conn: &Connection) -> rusqlite::Result<()> {
    add_column(conn, "sermon", "canonical_title", "ALTER TABLE sermon ADD COLUMN canonical_title TEXT DEFAULT ''")?;
    add_column(conn, "sermon", "title_search", "ALTER TABLE sermon ADD COLUMN title_search TEXT DEFAULT ''")?;
    add_column(conn, "sermon_paragraph", "marker", "ALTER TABLE sermon_paragraph ADD COLUMN marker TEXT DEFAULT ''")?;
    conn.execute_batch(
        "
            CREATE INDEX IF NOT EXISTS idx_sermon_lang_trad_date
                ON sermon (language, tradition, date);
            CREATE INDEX IF NOT EXISTS idx_sermon_date_lang
                ON sermon (date, language);
            CREATE INDEX IF NOT EXISTS idx_sermon_canonical_title
                ON sermon (canonical_title);
            CREATE INDEX IF NOT EXISTS idx_sermon_title_search
                ON sermon (title_search);
            CREATE INDEX IF NOT EXISTS idx_sermon_paragraph_marker
                ON sermon_paragraph (sermon_id, marker);
            ",
    )
}

fn migration_v6(conn: &Connection) -> rusqlite::Result<()> {
    add_column(conn, "hymn", "canonical_title", "ALTER TABLE hymn ADD COLUMN canonical_title TEXT DEFAULT ''")?;
    add_column(conn, "hymn", "title_search", "ALTER TABLE hymn ADD COLUMN title_search TEXT DEFAULT ''")?;
    add_column(conn, "hymn_stanza", "label", "ALTER TABLE hymn_stanza ADD COLUMN label TEXT DEFAULT ''")?;
    add_column(conn, "hymn_stanza", "is_chorus", "ALTER TABLE hymn_stanza ADD COLUMN is_chorus INTEGER DEFAULT 0")?;
    conn.execute_batch(
        "
            CREATE INDEX IF NOT EXISTS idx_hymn_language_sort
                ON hymn (language, sort_key, number);
            CREATE INDEX IF NOT EXISTS idx_hymn_title_search
                ON hymn (title_search);
            CREATE INDEX IF NOT EXISTS idx_hymn_canonical_title
                ON hymn (canonical_title);
            CREATE INDEX IF NOT EXISTS idx_hymn_stanza_label
                ON hymn_stanza (hymn_id, label);
            ",
    )
}

fn migration_v7(conn: &Connection) -> rusqlite::Result<()> {
    add_column(conn, "playlist_item", "background", "ALTER TABLE playlist_item ADD COLUMN background TEXT DEFAULT ''")
}

/// La boucle vidéo des médias (2.0), seulement si la table existe déjà.
fn migration_v8(conn: &Connection) -> rusqlite::Result<()> {
    if !table_exists(conn, "media_item")? {
        return Ok(());
    }
    add_column(conn, "media_item", "loop", "ALTER TABLE media_item ADD COLUMN loop INTEGER DEFAULT 0")
}

/// La durée d'affichage des médias en diaporama (2.5), seulement si la table existe déjà.
fn migration_v9(conn: &Connection) -> rusqlite::Result<()> {
    if !table_exists(conn, "media_item")? {
        return Ok(());
    }
    add_column(
        conn,
        "media_item",
        "duration_seconds",
        "ALTER TABLE media_item ADD COLUMN duration_seconds INTEGER DEFAULT 0",
    )
}

/// La date et le lieu tels qu'imprimés dans la source (sermons SHP).
fn migration_v10(conn: &Connection) -> rusqlite::Result<()> {
    if columns(conn, "sermon")?.is_empty() {
        return Ok(());
    }
    add_column(conn, "sermon", "printed_date", "ALTER TABLE sermon ADD COLUMN printed_date TEXT DEFAULT ''")?;
    add_column(conn, "sermon", "printed_location", "ALTER TABLE sermon ADD COLUMN printed_location TEXT DEFAULT ''")
}

/// Les deux Exposés existent dans toutes les bases (onglet « Livres »).
const BUILTIN_BOOKS: [(&str, &str, &str, &str, i64, &str); 2] = [
    (
        "ages-vgr",
        "Exposé des Sept Âges de l’Église",
        "BK-AGES-CH",
        "VGR",
        1,
        "FRNBK-AGES Expose du Sept ages de l'eglise VGR.pdf",
    ),
    ("ages-shp", "Exposé des Sept Âges de l’Église (SHP)", "BK-AGES-SHP-", "SHP", 2, "Expose SHP.pdf"),
];

fn ensure_library_books(conn: &Connection) -> rusqlite::Result<()> {
    conn.execute_batch(
        "
            CREATE TABLE IF NOT EXISTS library_book (
                key TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                date_prefix TEXT NOT NULL,
                tradition TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                source TEXT DEFAULT ''
            )
            ",
    )?;
    for (key, title, prefix, tradition, order, source) in BUILTIN_BOOKS {
        conn.execute(
            "INSERT OR IGNORE INTO library_book (key, title, date_prefix, tradition, sort_order, source) VALUES (?, ?, ?, ?, ?, ?)",
            params![key, title, prefix, tradition, order, source],
        )?;
    }
    Ok(())
}

/// Le déroulé du culte : heure de début par playlist et sections.
fn ensure_service_plan_tables(conn: &Connection) -> rusqlite::Result<()> {
    add_column(
        conn,
        "playlist_folder",
        "start_time",
        "ALTER TABLE playlist_folder ADD COLUMN start_time TEXT DEFAULT ''",
    )?;
    conn.execute_batch(
        "
            CREATE TABLE IF NOT EXISTS service_section (
                id INTEGER PRIMARY KEY,
                folder_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                duration_min INTEGER NOT NULL DEFAULT 10,
                item_id INTEGER,
                sort_order INTEGER DEFAULT 0,
                FOREIGN KEY (folder_id) REFERENCES playlist_folder (id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_service_section_folder
                ON service_section (folder_id, sort_order);
            ",
    )
}

fn ensure_media_tables(conn: &Connection) -> rusqlite::Result<()> {
    conn.execute_batch(
        "
            CREATE TABLE IF NOT EXISTS media_item (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL DEFAULT 'image',
                sort_order INTEGER DEFAULT 0,
                loop INTEGER DEFAULT 0,
                duration_seconds INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_media_item_sort
                ON media_item (sort_order, id);
            ",
    )?;
    migration_v8(conn)?;
    migration_v9(conn)
}

/// Des index B-tree sur des colonnes de texte entier : aucune requête ne s'en sert (la recherche
/// passe par FTS), ils doublent le texte sur le disque (~600 Mo).
const OBSOLETE_INDEXES: [&str; 4] =
    ["idx_sermon_paragraph_text", "idx_bible_translation_verse_text", "idx_bible_verse_text", "idx_hymn_stanza_text"];

fn drop_obsolete_indexes(conn: &Connection) -> bool {
    let mut dropped = false;
    for name in OBSOLETE_INDEXES {
        let exists = conn
            .query_row("SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", [name], |_| Ok(()))
            .optional()
            .ok()
            .flatten()
            .is_some();
        if exists && conn.execute_batch(&format!("DROP INDEX IF EXISTS {name}")).is_ok() {
            dropped = true;
        }
    }
    dropped
}

fn startup_maintenance_needed(conn: &Connection) -> rusqlite::Result<bool> {
    if get_meta(conn, STARTUP_MAINTENANCE_KEY).as_deref() == Some(STARTUP_MAINTENANCE_VERSION) {
        return Ok(false);
    }
    if startup_data_already_ready(conn) {
        set_meta(conn, STARTUP_MAINTENANCE_KEY, STARTUP_MAINTENANCE_VERSION)?;
        return Ok(false);
    }
    Ok(true)
}

/// Les données sont-elles déjà prêtes (index complets, titres, repères et étiquettes remplis) ?
fn startup_data_already_ready(conn: &Connection) -> bool {
    let check = || -> rusqlite::Result<bool> {
        let count = |sql: &str| conn.query_row(sql, [], |r| r.get::<_, Option<i64>>(0)).map(|n| n.unwrap_or(0));
        let any = |sql: &str| conn.query_row(sql, [], |_| Ok(())).optional().map(|r| r.is_some());
        let sermons = count("SELECT COUNT(*) FROM sermon_paragraph")?;
        let sermons_fts = count("SELECT COUNT(*) FROM sermon_paragraph_fts")?;
        let stanzas = count("SELECT COUNT(*) FROM hymn_stanza")?;
        let stanzas_fts = count("SELECT COUNT(*) FROM hymn_stanza_fts")?;
        let verses = count("SELECT COUNT(*) FROM bible_translation_verse")?;
        let missing_sermon_meta = any(
            "SELECT 1 FROM sermon WHERE canonical_title IS NULL OR canonical_title = '' OR title_search IS NULL OR title_search = '' LIMIT 1",
        )?;
        let missing_hymn_meta = any(
            "SELECT 1 FROM hymn WHERE canonical_title IS NULL OR canonical_title = '' OR title_search IS NULL OR title_search = '' LIMIT 1",
        )?;
        let missing_markers = any("SELECT 1 FROM sermon_paragraph WHERE marker IS NULL OR marker = '' LIMIT 1")?;
        let missing_labels = any("SELECT 1 FROM hymn_stanza WHERE label IS NULL OR label = '' LIMIT 1")?;
        Ok(sermons > 0
            && sermons == sermons_fts
            && stanzas > 0
            && stanzas == stanzas_fts
            && verses > 0
            && !missing_sermon_meta
            && !missing_hymn_meta
            && !missing_markers
            && !missing_labels)
    };
    check().unwrap_or(false)
}

/// Une base vide reçoit quelques versets, un cantique et un sermon de démonstration.
fn seed_demo_data_if_empty(conn: &Connection) -> rusqlite::Result<()> {
    let empty = |table: &str| -> rusqlite::Result<bool> {
        conn.query_row(&format!("SELECT COUNT(1) FROM {table};"), [], |r| r.get::<_, i64>(0)).map(|n| n == 0)
    };
    if empty("bible_book")? {
        for (id, name, abbreviation, testament, order) in
            [(1, "Genèse", "Gn", "OT", 1), (2, "Exode", "Ex", "OT", 2), (3, "Jean", "Jn", "NT", 43)]
        {
            conn.execute(
                "INSERT INTO bible_book (id, name, abbreviation, testament, sort_order) VALUES (?, ?, ?, ?, ?)",
                params![id, name, abbreviation, testament, order],
            )?;
        }
        let verses: [(i64, i64, i64, &str); 5] = [
            (1, 1, 1, "Au commencement, Dieu créa les cieux et la terre."),
            (
                1,
                1,
                2,
                "La terre était informe et vide: il y avait des ténèbres à la surface de l'abîme, et l'Esprit de Dieu se mouvait au-dessus des eaux.",
            ),
            (1, 1, 3, "Dieu dit: Que la lumière soit! Et la lumière fut."),
            (
                2,
                3,
                14,
                "Dieu dit à Moïse: Je suis celui qui suis. Et il ajouta: C'est ainsi que tu répondras aux enfants d'Israël: Celui qui s'appelle “je suis” m'a envoyé vers vous.",
            ),
            (
                3,
                3,
                16,
                "Car Dieu a tant aimé le monde qu'il a donné son Fils unique, afin que quiconque croit en lui ne périsse point, mais qu'il ait la vie éternelle.",
            ),
        ];
        for (book, chapter, verse, text) in verses {
            conn.execute(
                "INSERT INTO bible_verse (book_id, chapter, verse, text) VALUES (?, ?, ?, ?)",
                params![book, chapter, verse, text],
            )?;
        }
    }
    if empty("hymn")? {
        conn.execute(
            "INSERT INTO hymn (id, title, number, language, sort_key) VALUES (?, ?, ?, ?, ?)",
            params![1, "Je veux chanter", "1", "fr", "0001"],
        )?;
        for (no, text) in [
            (1, "Je veux chanter, louer mon Roi,\nCar Il est bon et fidèle."),
            (2, "Sa grâce m'a relevé,\nSon amour m'a délivré."),
        ] {
            conn.execute("INSERT INTO hymn_stanza (hymn_id, stanza_no, text) VALUES (?, ?, ?)", params![1, no, text])?;
        }
    }
    if empty("sermon")? {
        conn.execute(
            "INSERT INTO sermon (id, title, date, tradition, language, source_path, sort_key) VALUES (?, ?, ?, ?, ?, ?, ?)",
            params![1, "La Foi", "1953-09-12", "VGR", "fr", "", "0001"],
        )?;
        for (no, reference, text) in [
            (
                1,
                "La Foi ¶1",
                "La foi est une substance des choses qu'on espère, une démonstration de celles qu'on ne voit pas.",
            ),
            (2, "La Foi ¶2", "Elle prend Dieu au mot et marche comme si la promesse était déjà accomplie."),
        ] {
            conn.execute(
                "INSERT INTO sermon_paragraph (sermon_id, paragraph_no, ref, text) VALUES (?, ?, ?, ?)",
                params![1, no, reference, text],
            )?;
        }
    }
    Ok(())
}

/// `str(value or "")` d'une colonne de texte.
fn text_or_empty(value: Option<String>) -> String {
    value.unwrap_or_default()
}

/// Les titres communs et les clés de recherche des sermons (`_ensure_sermon_title_metadata`).
fn ensure_sermon_title_metadata(conn: &Connection) -> rusqlite::Result<()> {
    struct Row {
        id: i64,
        date: Option<String>,
        title: String,
        tradition: Option<String>,
        language: Option<String>,
        location: Option<String>,
        canonical_title: Option<String>,
        title_search: Option<String>,
    }
    let mut stmt = conn.prepare(
        "SELECT id, date, title, tradition, language, location, canonical_title, title_search FROM sermon ORDER BY id",
    )?;
    let rows = stmt
        .query_map([], |r| {
            Ok(Row {
                id: r.get(0)?,
                date: r.get(1)?,
                title: r.get(2)?,
                tradition: r.get(3)?,
                language: r.get(4)?,
                location: r.get(5)?,
                canonical_title: r.get(6)?,
                title_search: r.get(7)?,
            })
        })?
        .collect::<rusqlite::Result<Vec<Row>>>()?;

    // Les traductions d'une même prédication : même date et même langue (dans l'ordre d'arrivée).
    let mut order: Vec<(String, String)> = Vec::new();
    let mut groups: HashMap<(String, String), Vec<&Row>> = HashMap::new();
    for row in &rows {
        let date = po_text::py::strip(row.date.as_deref().unwrap_or("")).to_string();
        let language = po_text::py::strip(row.language.as_deref().unwrap_or("")).to_lowercase();
        let key = if date.is_empty() { (format!("id:{}", row.id), language) } else { (date, language) };
        groups
            .entry(key.clone())
            .or_insert_with(|| {
                order.push(key);
                Vec::new()
            })
            .push(row);
    }

    let mut update = conn.prepare("UPDATE sermon SET canonical_title = ?, title_search = ? WHERE id = ?")?;
    for key in order {
        let items = &groups[&key];
        let candidates: Vec<po_text::TitleCandidate<'_>> = items
            .iter()
            .map(|r| po_text::TitleCandidate { title: &r.title, tradition: r.tradition.as_deref().unwrap_or("") })
            .collect();
        let shared = po_text::choose_canonical_title(&candidates);
        for row in items {
            // La traduction SHP garde son propre titre, celui du PDF (seule la casse change ; les
            // chapitres de l'Exposé gardent leur titre exact).
            let canonical = if row.tradition.as_deref().unwrap_or("").to_uppercase() == "SHP" {
                if row.date.as_deref().unwrap_or("").starts_with("BK-AGES") {
                    row.title.clone()
                } else {
                    po_text::title_case_words(&row.title)
                }
            } else {
                shared.clone()
            };
            let parts = [
                canonical.clone(),
                row.title.clone(),
                text_or_empty(row.date.clone()),
                text_or_empty(row.tradition.clone()),
                text_or_empty(row.language.clone()),
                text_or_empty(row.location.clone()),
            ];
            let title_search = po_text::search_key(&parts.join(" "));
            if row.canonical_title.as_deref().unwrap_or("") != canonical
                || row.title_search.as_deref().unwrap_or("") != title_search
            {
                update.execute(params![canonical, title_search, row.id])?;
            }
        }
    }
    Ok(())
}

/// Les repères des paragraphes (« ¶12 », « E-76 », « 112-3 ») manquants ou mal encodés.
fn ensure_sermon_paragraph_markers(conn: &Connection) -> rusqlite::Result<()> {
    let mut stmt = conn.prepare(
        "
            SELECT id, paragraph_no, ref, marker
            FROM sermon_paragraph
            WHERE marker IS NULL OR marker = '' OR marker LIKE '%Â%' OR marker LIKE '%Ã%'
            ",
    )?;
    let rows = stmt
        .query_map([], |r| Ok((r.get::<_, i64>(0)?, r.get::<_, i64>(1)?, r.get::<_, Option<String>>(2)?)))?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    let mut update = conn.prepare("UPDATE sermon_paragraph SET marker = ? WHERE id = ?")?;
    for (id, no, reference) in rows {
        update.execute(params![po_text::marker_from_ref(reference.as_deref().unwrap_or(""), no), id])?;
    }
    Ok(())
}

/// Index sans contenu (content='') : il ne garde pas de copie du texte. detail=full garde les
/// positions des mots, nécessaires aux « expressions exactes ».
const SERMON_FTS_DDL: &str = "CREATE VIRTUAL TABLE sermon_paragraph_fts USING fts5(text, ref, sermon_title, canonical_title, content='', detail=full, tokenize='unicode61 remove_diacritics 2')";

const SERMON_FTS_FILL: &str = "
            INSERT INTO sermon_paragraph_fts
                (rowid, text, ref, sermon_title, canonical_title)
            SELECT
                p.id,
                p.text,
                COALESCE(p.ref, ''),
                s.title,
                COALESCE(NULLIF(s.canonical_title, ''), s.title)
            FROM sermon_paragraph p
            JOIN sermon s ON s.id = p.sermon_id
            ";

/// L'index de recherche existe-t-il avec le bon format ? Le recrée sinon, puis le remplit s'il ne
/// compte pas autant de lignes que la table.
fn ensure_fts(
    conn: &Connection,
    table: &str,
    source: &str,
    ddl: &str,
    detail: &str,
    fill: &str,
) -> rusqlite::Result<()> {
    let existing: Option<Option<String>> = conn
        .query_row("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", [table], |r| r.get(0))
        .optional()?;
    let mut exists = existing.is_some();
    if let Some(sql) = existing
        && !sql.unwrap_or_default().to_lowercase().contains(detail)
    {
        conn.execute_batch(&format!("DROP TABLE {table}"))?;
        exists = false;
    }
    if !exists {
        conn.execute_batch(ddl)?;
    }
    let indexed: i64 = conn.query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |r| r.get(0))?;
    let rows: i64 = conn.query_row(&format!("SELECT COUNT(*) FROM {source}"), [], |r| r.get(0))?;
    if indexed == rows && rows > 0 {
        return Ok(());
    }
    // Un index sans contenu refuse DELETE : on le recrée pour retirer les lignes périmées.
    conn.execute_batch(&format!("DROP TABLE IF EXISTS {table}"))?;
    conn.execute_batch(ddl)?;
    conn.execute_batch(fill)
}

fn ensure_sermon_fts(conn: &Connection) -> rusqlite::Result<()> {
    ensure_fts(conn, "sermon_paragraph_fts", "sermon_paragraph", SERMON_FTS_DDL, "detail=full", SERMON_FTS_FILL)
}

pub(crate) const HYMN_FTS_DDL: &str = "CREATE VIRTUAL TABLE hymn_stanza_fts USING fts5(text, hymn_title, hymn_number, label, content='', detail=none, tokenize='unicode61 remove_diacritics 2')";

pub(crate) const HYMN_FTS_FILL: &str = "
            INSERT INTO hymn_stanza_fts
                (rowid, text, hymn_title, hymn_number, label)
            SELECT
                hs.id,
                hs.text,
                COALESCE(NULLIF(h.canonical_title, ''), h.title),
                COALESCE(h.number, ''),
                COALESCE(NULLIF(hs.label, ''), 'Strophe ' || hs.stanza_no)
            FROM hymn_stanza hs
            JOIN hymn h ON h.id = hs.hymn_id
            ";

fn ensure_hymn_fts(conn: &Connection) -> rusqlite::Result<()> {
    ensure_fts(conn, "hymn_stanza_fts", "hymn_stanza", HYMN_FTS_DDL, "detail=none", HYMN_FTS_FILL)
}

/// Les titres communs et les clés de recherche des cantiques.
fn ensure_hymn_title_metadata(conn: &Connection) -> rusqlite::Result<()> {
    let mut stmt =
        conn.prepare("SELECT id, title, number, language, canonical_title, title_search FROM hymn ORDER BY id")?;
    type Row = (i64, String, Option<String>, Option<String>, Option<String>, Option<String>);
    let rows = stmt
        .query_map([], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?, r.get(4)?, r.get(5)?)))?
        .collect::<rusqlite::Result<Vec<Row>>>()?;
    let mut update = conn.prepare("UPDATE hymn SET canonical_title = ?, title_search = ? WHERE id = ?")?;
    for (id, title, number, language, stored_canonical, stored_search) in rows {
        let canonical = po_text::clean_hymn_title_for_canonical(&title);
        let parts = [canonical.clone(), title, text_or_empty(number), text_or_empty(language)];
        let title_search = po_text::search_key(&parts.join(" "));
        if stored_canonical.as_deref().unwrap_or("") != canonical
            || stored_search.as_deref().unwrap_or("") != title_search
        {
            update.execute(params![canonical, title_search, id])?;
        }
    }
    Ok(())
}

/// Les étiquettes des strophes (« Strophe 2 », « Refrain ») et le drapeau des refrains.
fn ensure_hymn_stanza_labels(conn: &Connection) -> rusqlite::Result<()> {
    let mut stmt = conn.prepare(
        "
            SELECT id, hymn_id, stanza_no, text, label, is_chorus
            FROM hymn_stanza
            ORDER BY hymn_id, stanza_no
            ",
    )?;
    type Row = (i64, i64, String, Option<String>, Option<i64>);
    let rows = stmt
        .query_map([], |r| Ok((r.get(0)?, r.get(1)?, r.get(3)?, r.get(4)?, r.get(5)?)))?
        .collect::<rusqlite::Result<Vec<Row>>>()?;
    let mut update = conn.prepare("UPDATE hymn_stanza SET label = ?, is_chorus = ? WHERE id = ?")?;
    let mut current: Option<i64> = None;
    let (mut verse_no, mut chorus_no) = (0, 0);
    for (id, hymn_id, text, label, is_chorus) in rows {
        if current != Some(hymn_id) {
            current = Some(hymn_id);
            verse_no = 0;
            chorus_no = 0;
        }
        let chorus = po_text::is_chorus(&text);
        let wanted = if chorus {
            chorus_no += 1;
            if chorus_no == 1 { "Refrain".to_string() } else { format!("Refrain {chorus_no}") }
        } else {
            verse_no += 1;
            format!("Strophe {verse_no}")
        };
        let flag = i64::from(chorus);
        if label.as_deref().unwrap_or("") != wanted || is_chorus.unwrap_or(0) != flag {
            update.execute(params![wanted, flag, id])?;
        }
    }
    Ok(())
}

/// `optional_str` : `None` reste `None`, le reste devient du texte comme `str()` de Python.
fn optional_str(value: Option<&Value>) -> Option<String> {
    match value {
        None | Some(Value::Null) => None,
        Some(v) => Some(to_str(v)),
    }
}

/// Les Bibles livrées en JSON (`_import_bible_json_translations`) : les traductions et versets
/// absents sont ajoutés, rien n'est remplacé.
fn import_bible_json_translations(conn: &Connection, dir: &Path) -> rusqlite::Result<()> {
    let Ok(entries) = std::fs::read_dir(dir) else { return Ok(()) };
    let mut files: Vec<PathBuf> = entries
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.is_file() && p.extension().is_some_and(|e| e.eq_ignore_ascii_case("json")))
        .collect();
    files.sort_by_key(|p| p.to_string_lossy().to_lowercase());

    let mut insert = conn.prepare(
        "
                        INSERT OR IGNORE INTO bible_translation_verse
                            (translation_id, book, book_name, chapter, verse, text)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ",
    )?;
    for path in files {
        let Ok(text) = std::fs::read_to_string(&path) else { continue };
        let Ok(Value::Object(payload)) = serde_json::from_str::<Value>(&text) else { continue };
        let Some(metadata) = payload.get("metadata").and_then(Value::as_object) else { continue };
        let module = match metadata.get("module") {
            Some(m) if truthy(m) => to_str(m),
            _ => path.file_stem().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default(),
        };
        let lang = match metadata.get("lang_short") {
            Some(short) if truthy(short) => Some(short),
            _ => metadata.get("lang"),
        };
        conn.execute(
            "INSERT OR IGNORE INTO bible_translation (module, name, shortname, lang) VALUES (?, ?, ?, ?)",
            params![
                module,
                optional_str(metadata.get("name")),
                optional_str(metadata.get("shortname")),
                optional_str(lang)
            ],
        )?;
        let Some(translation_id) = conn
            .query_row("SELECT id FROM bible_translation WHERE module = ?", [&module], |r| r.get::<_, i64>(0))
            .optional()?
        else {
            continue;
        };
        let Some(verses) = payload.get("verses").and_then(Value::as_array).filter(|v| !v.is_empty()) else { continue };
        for verse in verses.iter().filter_map(Value::as_object) {
            let number = |key: &str| verse.get(key).and_then(to_int);
            let (Some(book), Some(chapter), Some(verse_no)) = (number("book"), number("chapter"), number("verse"))
            else {
                continue;
            };
            let raw = verse.get("text").filter(|t| truthy(t)).map(to_str).unwrap_or_default();
            let text = po_text::clean_text(&raw);
            if text.is_empty() {
                continue;
            }
            insert.execute(params![
                translation_id,
                book,
                optional_str(verse.get("book_name")),
                chapter,
                verse_no,
                text
            ])?;
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tables(conn: &Connection) -> Vec<String> {
        let mut stmt = conn.prepare("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").unwrap();
        stmt.query_map([], |r| r.get(0)).unwrap().collect::<rusqlite::Result<_>>().unwrap()
    }

    #[test]
    fn a_new_database_reaches_version_11_with_demo_data() {
        let mut conn = Connection::open_in_memory().unwrap();
        let report = initialize(&mut conn, &InitOptions::default()).unwrap();
        assert_eq!(report.from_version, 0);
        assert!(report.maintenance_ran);
        assert_eq!(user_version(&conn).unwrap(), SCHEMA_VERSION);
        let names = tables(&conn);
        for table in
            ["app_meta", "hymn_stanza_fts", "library_book", "media_item", "service_section", "sermon_paragraph_fts"]
        {
            assert!(names.iter().any(|n| n == table), "table {table} absente");
        }
        let canonical: String =
            conn.query_row("SELECT canonical_title FROM sermon WHERE id = 1", [], |r| r.get(0)).unwrap();
        assert_eq!(canonical, "La Foi");
        let marker: String =
            conn.query_row("SELECT marker FROM sermon_paragraph WHERE paragraph_no = 2", [], |r| r.get(0)).unwrap();
        assert_eq!(marker, "¶2");
        let label: String =
            conn.query_row("SELECT label FROM hymn_stanza WHERE stanza_no = 2", [], |r| r.get(0)).unwrap();
        assert_eq!(label, "Strophe 2");
        // Relancer ne refait rien.
        let again = initialize(&mut conn, &InitOptions::default()).unwrap();
        assert_eq!(again, InitReport { from_version: 11, ..Default::default() });
    }

    #[test]
    fn an_old_database_gets_the_new_columns_without_losing_data() {
        let mut conn = Connection::open_in_memory().unwrap();
        conn.execute_batch(MIGRATION_V1).unwrap();
        conn.execute_batch("PRAGMA user_version = 1;").unwrap();
        conn.execute(
            "INSERT INTO sermon (title, date, tradition, language) VALUES ('LA FOI', '53-0912', 'VGR', 'fr')",
            [],
        )
        .unwrap();
        migrate(&mut conn).unwrap();
        let cols = columns(&conn, "sermon").unwrap();
        for col in ["location", "canonical_title", "title_search", "printed_date", "printed_location"] {
            assert!(cols.iter().any(|c| c == col), "colonne {col} absente");
        }
        let title: String = conn.query_row("SELECT title FROM sermon", [], |r| r.get(0)).unwrap();
        assert_eq!(title, "LA FOI");
    }
}
