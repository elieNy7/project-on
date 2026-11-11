//! La gestion des Bibles (`bible_catalog.py` de la 2.8) : lire un fichier de Bible (XML Zefania ou
//! « Beblia », JSON scrollmapper, JSON Project-On, compressé ou non), l'installer dans
//! `bible_translation` / `bible_translation_verse` (d'un bloc : une installation interrompue ne
//! laisse rien à moitié), la supprimer (et ne pas la réinstaller : `bible_removed`), installer les
//! Bibles fournies qui manquent, et le catalogue des Bibles libres de droits à télécharger.

use std::io::Read;
use std::path::Path;

use rusqlite::{OptionalExtension, params};
use serde_json::Value;

use crate::{Database, DbError, Result};

/// L'adresse d'une Bible du catalogue (projet scrollmapper/bible_databases).
pub const SCROLLMAPPER_URL: &str =
    "https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/json/{code}.json";

/// Une Bible du catalogue : code scrollmapper, nom court, nom, langue, licence, fournie, note.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CatalogEntry {
    pub code: &'static str,
    pub shortname: &'static str,
    pub name: &'static str,
    pub lang: &'static str,
    pub license: &'static str,
    pub bundled: bool,
    pub note: &'static str,
}

impl CatalogEntry {
    pub fn module(&self) -> String {
        format!("sm_{}", self.code.to_lowercase())
    }

    pub fn url(&self) -> String {
        SCROLLMAPPER_URL.replace("{code}", self.code)
    }
}

const fn entry(
    code: &'static str,
    shortname: &'static str,
    name: &'static str,
    lang: &'static str,
    bundled: bool,
) -> CatalogEntry {
    CatalogEntry { code, shortname, name, lang, license: "Domaine public", bundled, note: "" }
}

/// Uniquement des textes du domaine public (ou sous licence libre explicite), comme la 2.8.
pub const CATALOG: [CatalogEntry; 20] = [
    entry("FreBDM1744", "Martin 1744", "Bible David Martin (1744)", "fr", true),
    CatalogEntry {
        note: "Livres deutérocanoniques non repris",
        ..entry("FreCrampon", "Crampon 1923", "Bible Augustin Crampon (1923)", "fr", true)
    },
    entry("FrePGR", "Perret-Gentil", "Bible Perret-Gentil et Rilliet (1866)", "fr", true),
    entry("FreBBB", "Bovet-Bonnet", "Bible Bovet-Bonnet (1900)", "fr", true),
    entry("FreJND", "Darby (JND)", "Bible J.N. Darby (1885)", "fr", false),
    entry("FreSynodale1921", "Synodale 1921", "Version Synodale 1921 (NT et Psaumes)", "fr", false),
    entry("FreOltramare1874", "Oltramare 1874", "Nouveau Testament Oltramare (1874)", "fr", false),
    entry("FreStapfer1889", "Stapfer 1889", "Nouveau Testament Stapfer (1889)", "fr", false),
    entry("KJV", "KJV", "King James Version (1769)", "en", true),
    entry("BSB", "BSB", "Berean Standard Bible", "en", true),
    entry("ASV", "ASV", "American Standard Version (1901)", "en", false),
    entry("Darby", "Darby EN", "Darby Bible (1889)", "en", false),
    entry("DRC", "Douay-Rheims", "Douay-Rheims, Challoner Revision", "en", false),
    entry("SpaRV", "Reina-Valera 1909", "La Santa Biblia Reina-Valera (1909)", "es", true),
    CatalogEntry { license: "CC BY 3.0 BR", ..entry("PorBLivre", "Bíblia Livre", "Bíblia Livre", "pt", false) },
    entry("Haitian", "Kreyòl", "Bib la an Kreyòl ayisyen", "ht", false),
    entry("Mg1865", "Malagasy 1865", "Baiboly Malagasy (1865)", "mg", false),
    entry("GerElb1905", "Elberfelder 1905", "Elberfelder Bibel (1905)", "de", false),
    entry("RusSynodal", "Synodale russe", "Синодальный перевод", "ru", false),
    entry("Viet", "Việt 1934", "Kinh Thánh Tiếng Việt (1934)", "vi", false),
];

/// Les langues proposées à l'import d'un fichier.
pub const LANGS: [(&str, &str); 13] = [
    ("fr", "Français"),
    ("en", "English"),
    ("es", "Español"),
    ("pt", "Português"),
    ("ht", "Kreyòl"),
    ("mg", "Malagasy"),
    ("de", "Deutsch"),
    ("ru", "Русский"),
    ("vi", "Tiếng Việt"),
    ("ln", "Lingala"),
    ("sw", "Kiswahili"),
    ("lua", "Tshiluba"),
    ("kg", "Kikongo"),
];

const FRENCH_BOOKS: [&str; 66] = [
    "Genèse",
    "Exode",
    "Lévitique",
    "Nombres",
    "Deutéronome",
    "Josué",
    "Juges",
    "Ruth",
    "1 Samuel",
    "2 Samuel",
    "1 Rois",
    "2 Rois",
    "1 Chroniques",
    "2 Chroniques",
    "Esdras",
    "Néhémie",
    "Esther",
    "Job",
    "Psaumes",
    "Proverbes",
    "Ecclésiaste",
    "Cantique des cantiques",
    "Ésaïe",
    "Jérémie",
    "Lamentations",
    "Ézéchiel",
    "Daniel",
    "Osée",
    "Joël",
    "Amos",
    "Abdias",
    "Jonas",
    "Michée",
    "Nahum",
    "Habacuc",
    "Sophonie",
    "Aggée",
    "Zacharie",
    "Malachie",
    "Matthieu",
    "Marc",
    "Luc",
    "Jean",
    "Actes",
    "Romains",
    "1 Corinthiens",
    "2 Corinthiens",
    "Galates",
    "Éphésiens",
    "Philippiens",
    "Colossiens",
    "1 Thessaloniciens",
    "2 Thessaloniciens",
    "1 Timothée",
    "2 Timothée",
    "Tite",
    "Philémon",
    "Hébreux",
    "Jacques",
    "1 Pierre",
    "2 Pierre",
    "1 Jean",
    "2 Jean",
    "3 Jean",
    "Jude",
    "Apocalypse",
];

const ENGLISH_BOOKS: [&str; 66] = [
    "Genesis",
    "Exodus",
    "Leviticus",
    "Numbers",
    "Deuteronomy",
    "Joshua",
    "Judges",
    "Ruth",
    "1 Samuel",
    "2 Samuel",
    "1 Kings",
    "2 Kings",
    "1 Chronicles",
    "2 Chronicles",
    "Ezra",
    "Nehemiah",
    "Esther",
    "Job",
    "Psalms",
    "Proverbs",
    "Ecclesiastes",
    "Song of Solomon",
    "Isaiah",
    "Jeremiah",
    "Lamentations",
    "Ezekiel",
    "Daniel",
    "Hosea",
    "Joel",
    "Amos",
    "Obadiah",
    "Jonah",
    "Micah",
    "Nahum",
    "Habakkuk",
    "Zephaniah",
    "Haggai",
    "Zechariah",
    "Malachi",
    "Matthew",
    "Mark",
    "Luke",
    "John",
    "Acts",
    "Romans",
    "1 Corinthians",
    "2 Corinthians",
    "Galatians",
    "Ephesians",
    "Philippians",
    "Colossians",
    "1 Thessalonians",
    "2 Thessalonians",
    "1 Timothy",
    "2 Timothy",
    "Titus",
    "Philemon",
    "Hebrews",
    "James",
    "1 Peter",
    "2 Peter",
    "1 John",
    "2 John",
    "3 John",
    "Jude",
    "Revelation",
];

const SPANISH_BOOKS: [&str; 66] = [
    "Génesis",
    "Éxodo",
    "Levítico",
    "Números",
    "Deuteronomio",
    "Josué",
    "Jueces",
    "Rut",
    "1 Samuel",
    "2 Samuel",
    "1 Reyes",
    "2 Reyes",
    "1 Crónicas",
    "2 Crónicas",
    "Esdras",
    "Nehemías",
    "Ester",
    "Job",
    "Salmos",
    "Proverbios",
    "Eclesiastés",
    "Cantares",
    "Isaías",
    "Jeremías",
    "Lamentaciones",
    "Ezequiel",
    "Daniel",
    "Oseas",
    "Joel",
    "Amós",
    "Abdías",
    "Jonás",
    "Miqueas",
    "Nahúm",
    "Habacuc",
    "Sofonías",
    "Hageo",
    "Zacarías",
    "Malaquías",
    "Mateo",
    "Marcos",
    "Lucas",
    "Juan",
    "Hechos",
    "Romanos",
    "1 Corintios",
    "2 Corintios",
    "Gálatas",
    "Efesios",
    "Filipenses",
    "Colosenses",
    "1 Tesalonicenses",
    "2 Tesalonicenses",
    "1 Timoteo",
    "2 Timoteo",
    "Tito",
    "Filemón",
    "Hebreos",
    "Santiago",
    "1 Pedro",
    "2 Pedro",
    "1 Juan",
    "2 Juan",
    "3 Juan",
    "Judas",
    "Apocalipsis",
];

/// Un nom de livre réduit à l'essentiel : sans accents, sans casse, chiffres romains en chiffres
/// (`_norm` de la 2.8).
fn norm(value: &str) -> String {
    let plain: String = value
        .chars()
        .map(|c| match c {
            'à' | 'á' | 'â' | 'ä' | 'À' | 'Á' | 'Â' | 'Ä' => 'a',
            'ç' | 'Ç' => 'c',
            'è' | 'é' | 'ê' | 'ë' | 'È' | 'É' | 'Ê' | 'Ë' => 'e',
            'ì' | 'í' | 'î' | 'ï' | 'Í' | 'Î' | 'Ï' => 'i',
            'ñ' | 'Ñ' => 'n',
            'ò' | 'ó' | 'ô' | 'ö' | 'Ó' | 'Ô' | 'Ö' => 'o',
            'ù' | 'ú' | 'û' | 'ü' | 'Ú' | 'Û' | 'Ü' => 'u',
            other => other,
        })
        .flat_map(char::to_lowercase)
        .collect();
    let words: Vec<String> = plain
        .split(|c: char| !c.is_ascii_alphanumeric())
        .filter(|w| !w.is_empty())
        .map(|w| match w {
            "iii" => "3".to_string(),
            "ii" => "2".to_string(),
            "i" => "1".to_string(),
            other => other.to_string(),
        })
        .collect();
    words.concat()
}

/// Le numéro canonique (1 à 66) d'un livre nommé en anglais, français ou espagnol ; `None` pour
/// un livre deutérocanonique.
pub fn book_number(name: &str) -> Option<i64> {
    let key = norm(name);
    for names in [&ENGLISH_BOOKS, &FRENCH_BOOKS, &SPANISH_BOOKS] {
        if let Some(i) = names.iter().position(|n| norm(n) == key) {
            return Some(i as i64 + 1);
        }
    }
    match key.as_str() {
        "revelationofjohn" | "apocalypsis" => Some(66),
        "songofsongs" | "canticles" | "cantiquedescantiques" | "cantique" => Some(22),
        "psalm" => Some(19),
        "isaie" => Some(23),
        _ => None,
    }
}

/// Le nom d'un livre dans la langue de la Bible.
pub fn book_display_name(book: i64, lang: &str) -> String {
    let names = match lang {
        "en" => &ENGLISH_BOOKS,
        "es" => &SPANISH_BOOKS,
        _ => &FRENCH_BOOKS,
    };
    usize::try_from(book - 1).ok().and_then(|i| names.get(i)).map_or_else(|| book.to_string(), |n| (*n).to_string())
}

/// Un verset à installer.
#[derive(Debug, Clone, PartialEq)]
pub struct NewVerse {
    pub book: i64,
    pub book_name: String,
    pub chapter: i64,
    pub verse: i64,
    pub text: String,
}

/// Une Bible lue, prête à installer (le format commun de la 2.8).
#[derive(Debug, Clone, PartialEq)]
pub struct BiblePayload {
    pub module: String,
    pub name: String,
    pub shortname: String,
    pub lang: String,
    pub license: String,
    pub source: String,
    pub verses: Vec<NewVerse>,
}

/// Une traduction installée et son nombre de versets.
#[derive(Debug, Clone, PartialEq)]
pub struct InstalledBible {
    pub id: i64,
    pub module: String,
    pub name: String,
    pub shortname: String,
    pub lang: String,
    pub verses: i64,
}

fn slug(text: &str) -> String {
    let n = norm(text);
    if n.is_empty() { "bible".into() } else { n }
}

fn bad(message: impl Into<String>) -> DbError {
    DbError::BadCopy(message.into())
}

/// Le JSON scrollmapper (livres → chapitres → versets).
pub fn from_scrollmapper(
    data: &Value,
    module: &str,
    shortname: &str,
    name: &str,
    lang: &str,
    license: &str,
) -> BiblePayload {
    let mut verses = Vec::new();
    for book in data.get("books").and_then(Value::as_array).into_iter().flatten() {
        let Some(number) = book.get("name").and_then(Value::as_str).and_then(book_number) else { continue };
        let display = book_display_name(number, lang);
        for chapter in book.get("chapters").and_then(Value::as_array).into_iter().flatten() {
            let ch = chapter.get("chapter").and_then(Value::as_i64).unwrap_or(0);
            for verse in chapter.get("verses").and_then(Value::as_array).into_iter().flatten() {
                let text = po_text::clean_text(verse.get("text").and_then(Value::as_str).unwrap_or(""));
                if ch > 0 && !text.is_empty() {
                    verses.push(NewVerse {
                        book: number,
                        book_name: display.clone(),
                        chapter: ch,
                        verse: verse.get("verse").and_then(Value::as_i64).unwrap_or(0),
                        text,
                    });
                }
            }
        }
    }
    BiblePayload {
        module: module.into(),
        name: name.into(),
        shortname: shortname.into(),
        lang: lang.into(),
        license: license.into(),
        source: "scrollmapper/bible_databases".into(),
        verses,
    }
}

/// Une Bible XML : Zefania (`BIBLEBOOK/CHAPTER/VERS`) ou Beblia (`book/chapter/verse`). Le livre
/// est lu par son numéro, sinon par son nom.
pub fn from_xml(text: &str, stem: &str, file_name: &str, shortname: &str, lang: &str) -> Result<BiblePayload> {
    let doc = roxmltree::Document::parse(text).map_err(|e| bad(format!("XML illisible : {e}")))?;
    let root = doc.root_element();
    let info_title = root
        .descendants()
        .find(|n| n.tag_name().name().eq_ignore_ascii_case("title"))
        .and_then(|n| n.text())
        .map(str::trim)
        .filter(|t| !t.is_empty());
    let title = root
        .attribute("biblename")
        .or_else(|| root.attribute("translation"))
        .or(info_title)
        .unwrap_or(stem)
        .to_string();
    let attr =
        |n: &roxmltree::Node<'_, '_>, keys: &[&str]| keys.iter().find_map(|k| n.attribute(*k)).map(str::to_string);
    let mut verses = Vec::new();
    for book in
        root.descendants().filter(|n| matches!(n.tag_name().name().to_lowercase().as_str(), "biblebook" | "book"))
    {
        let number = attr(&book, &["bnumber", "number"])
            .and_then(|n| n.trim().parse::<i64>().ok())
            .or_else(|| attr(&book, &["bname", "name"]).and_then(|n| book_number(&n)));
        let Some(number) = number.filter(|n| (1..=66).contains(n)) else { continue };
        let display = book_display_name(number, lang);
        for chapter in book.children().filter(|n| n.tag_name().name().eq_ignore_ascii_case("chapter")) {
            let ch = attr(&chapter, &["cnumber", "number"]).and_then(|n| n.trim().parse::<i64>().ok()).unwrap_or(0);
            for verse in
                chapter.children().filter(|n| matches!(n.tag_name().name().to_lowercase().as_str(), "vers" | "verse"))
            {
                let raw: String = verse.descendants().filter(|n| n.is_text()).filter_map(|n| n.text()).collect();
                let text = po_text::clean_text(&raw);
                let vno = attr(&verse, &["vnumber", "number"]).and_then(|n| n.trim().parse::<i64>().ok()).unwrap_or(0);
                if ch > 0 && vno > 0 && !text.is_empty() {
                    verses.push(NewVerse { book: number, book_name: display.clone(), chapter: ch, verse: vno, text });
                }
            }
        }
    }
    let shortname =
        if shortname.trim().is_empty() { title.chars().take(40).collect() } else { shortname.trim().to_string() };
    Ok(BiblePayload {
        module: format!("file_{}", slug(stem)),
        name: title,
        shortname,
        lang: lang.into(),
        license: "Fichier importé".into(),
        source: file_name.into(),
        verses,
    })
}

/// Le JSON au format Project-On (`{"metadata": {...}, "verses": [...]}`).
fn from_project_on(data: &Value) -> Result<BiblePayload> {
    let meta = data.get("metadata").cloned().unwrap_or(Value::Null);
    let text = |k: &str| meta.get(k).and_then(Value::as_str).unwrap_or("").trim().to_string();
    let module = text("module");
    if module.is_empty() {
        return Err(bad("Bible sans identifiant (metadata.module)"));
    }
    let lang = Some(text("lang")).filter(|l| !l.is_empty()).unwrap_or_else(|| "fr".into());
    let verses = data
        .get("verses")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|v| {
            let int =
                |k: &str| v.get(k).and_then(|x| x.as_i64().or_else(|| x.as_str().and_then(|s| s.trim().parse().ok())));
            let (book, chapter, verse) = (int("book")?, int("chapter")?, int("verse")?);
            let text = po_text::clean_text(v.get("text").and_then(Value::as_str).unwrap_or(""));
            (!text.is_empty()).then(|| NewVerse {
                book,
                book_name: v
                    .get("book_name")
                    .and_then(Value::as_str)
                    .map_or_else(|| book_display_name(book, &lang), str::to_string),
                chapter,
                verse,
                text,
            })
        })
        .collect();
    Ok(BiblePayload {
        module,
        name: text("name"),
        shortname: text("shortname"),
        lang,
        license: text("license"),
        source: text("source"),
        verses,
    })
}

/// Lit un fichier de Bible : XML (Zefania, Beblia), JSON scrollmapper ou Project-On, `.gz` compris.
pub fn load_bible_file(path: &Path, shortname: &str, lang: &str) -> Result<BiblePayload> {
    let name = path.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
    let lower = name.to_lowercase();
    let mut raw = std::fs::read(path)?;
    if lower.ends_with(".gz") {
        let mut out = Vec::new();
        flate2::read::GzDecoder::new(raw.as_slice())
            .read_to_end(&mut out)
            .map_err(|e| bad(format!("Fichier .gz illisible : {e}")))?;
        raw = out;
    }
    let stem = name.split('.').next().unwrap_or("bible").to_string();
    let text = String::from_utf8(raw).map_err(|_| bad("Le fichier n'est pas en UTF-8"))?;
    let text = text.trim_start_matches('\u{feff}');
    if lower.ends_with(".xml") || lower.ends_with(".xml.gz") || text.trim_start().starts_with('<') {
        return from_xml(text, &stem, &name, shortname, lang);
    }
    let data: Value = serde_json::from_str(text).map_err(|e| bad(format!("JSON illisible : {e}")))?;
    if data.get("verses").is_some_and(Value::is_array) {
        return from_project_on(&data);
    }
    if data.get("books").is_some_and(Value::is_array) {
        let title = data.get("translation").and_then(Value::as_str).unwrap_or(&stem).to_string();
        let short = if shortname.trim().is_empty() {
            title.split(':').next().unwrap_or(&title).chars().take(40).collect()
        } else {
            shortname.trim().to_string()
        };
        let mut payload =
            from_scrollmapper(&data, &format!("sm_{}", slug(&stem)), &short, &title, lang, "Fichier importé");
        payload.source = name;
        return Ok(payload);
    }
    Err(bad("Format de Bible non reconnu (XML Zefania ou Beblia, ou JSON attendu)"))
}

impl Database {
    /// Les traductions installées, avec leur nombre de versets.
    pub fn installed_bibles(&self) -> Result<Vec<InstalledBible>> {
        let mut stmt = self.conn.prepare(
            "SELECT t.id, t.module, COALESCE(t.name, ''), COALESCE(t.shortname, ''), COALESCE(t.lang, ''),
                    (SELECT COUNT(1) FROM bible_translation_verse v WHERE v.translation_id = t.id)
             FROM bible_translation t ORDER BY COALESCE(t.shortname, t.name, t.module)",
        )?;
        let rows = stmt.query_map([], |r| {
            Ok(InstalledBible {
                id: r.get(0)?,
                module: r.get(1)?,
                name: r.get(2)?,
                shortname: r.get(3)?,
                lang: r.get(4)?,
                verses: r.get(5)?,
            })
        })?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    /// Installe (ou remplace) une traduction, d'un bloc ; rend son identifiant. Une Bible
    /// supprimée puis réinstallée par l'opérateur n'est plus marquée supprimée.
    pub fn install_bible(&mut self, payload: &BiblePayload) -> Result<i64> {
        if payload.module.trim().is_empty() || payload.verses.is_empty() {
            return Err(bad("Bible vide ou sans identifiant"));
        }
        let tx = self.conn.transaction()?;
        tx.execute(
            "INSERT INTO bible_translation (module, name, shortname, lang) VALUES (?, ?, ?, ?)
             ON CONFLICT(module) DO UPDATE SET name = excluded.name, shortname = excluded.shortname, lang = excluded.lang",
            params![payload.module, payload.name, payload.shortname, payload.lang],
        )?;
        let id: i64 =
            tx.query_row("SELECT id FROM bible_translation WHERE module = ?", [&payload.module], |r| r.get(0))?;
        tx.execute("DELETE FROM bible_translation_verse WHERE translation_id = ?", [id])?;
        {
            let mut insert = tx.prepare(
                "INSERT OR IGNORE INTO bible_translation_verse (translation_id, book, book_name, chapter, verse, text)
                 VALUES (?, ?, ?, ?, ?, ?)",
            )?;
            for v in &payload.verses {
                insert.execute(params![id, v.book, v.book_name, v.chapter, v.verse, v.text])?;
            }
        }
        let mut removed = removed_modules(&tx);
        if removed.remove(&payload.module) {
            write_removed(&tx, &removed)?;
        }
        tx.commit()?;
        Ok(id)
    }

    /// Supprime une traduction ; elle ne sera pas réinstallée avec les Bibles fournies.
    pub fn remove_bible(&mut self, module: &str) -> Result<bool> {
        let tx = self.conn.transaction()?;
        let Some(id) = tx
            .query_row("SELECT id FROM bible_translation WHERE module = ?", [module], |r| r.get::<_, i64>(0))
            .optional()?
        else {
            return Ok(false);
        };
        tx.execute("DELETE FROM bible_translation_verse WHERE translation_id = ?", [id])?;
        tx.execute("DELETE FROM bible_translation WHERE id = ?", [id])?;
        let mut removed = removed_modules(&tx);
        removed.insert(module.to_string());
        write_removed(&tx, &removed)?;
        tx.commit()?;
        Ok(true)
    }

    /// Les Bibles supprimées volontairement (`bible_removed`).
    pub fn removed_bibles(&self) -> std::collections::BTreeSet<String> {
        removed_modules(&self.conn)
    }
}

fn removed_modules(conn: &rusqlite::Connection) -> std::collections::BTreeSet<String> {
    conn.query_row("SELECT value FROM app_meta WHERE key = 'bible_removed'", [], |r| r.get::<_, Option<String>>(0))
        .ok()
        .flatten()
        .map(|v| v.split(',').filter(|m| !m.is_empty()).map(str::to_string).collect())
        .unwrap_or_default()
}

fn write_removed(conn: &rusqlite::Connection, modules: &std::collections::BTreeSet<String>) -> Result<()> {
    let value = modules.iter().cloned().collect::<Vec<_>>().join(",");
    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES ('bible_removed', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        [value],
    )?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{InitOptions, Mode};

    fn scratch() -> tempfile::TempDir {
        let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
        std::fs::create_dir_all(&base).unwrap();
        tempfile::tempdir_in(base).unwrap()
    }

    #[test]
    fn book_names_in_three_languages_give_the_canonical_number() {
        assert_eq!(book_number("Genesis"), Some(1));
        assert_eq!(book_number("Ésaïe"), Some(23));
        assert_eq!(book_number("I Samuel"), Some(9));
        assert_eq!(book_number("III John"), Some(64));
        assert_eq!(book_number("Revelation of John"), Some(66));
        assert_eq!(book_number("Apocalipsis"), Some(66));
        assert_eq!(book_number("Tobit"), None);
        assert_eq!(book_display_name(43, "fr"), "Jean");
        assert_eq!(book_display_name(43, "en"), "John");
    }

    #[test]
    fn a_zefania_bible_is_read_installed_removed_and_not_reinstalled() {
        let dir = scratch();
        let xml = r#"<?xml version="1.0" encoding="utf-8"?>
<XMLBIBLE biblename="Biblia na Lingala">
  <BIBLEBOOK bnumber="43" bname="Yoane">
    <CHAPTER cnumber="3">
      <VERS vnumber="16">Pamba te Nzambe alingaki mokili <STYLE>mingi</STYLE></VERS>
      <VERS vnumber="17">Mpo Nzambe atindaki Mwana</VERS>
    </CHAPTER>
  </BIBLEBOOK>
  <BIBLEBOOK bname="Tobit"><CHAPTER cnumber="1"><VERS vnumber="1">hors canon</VERS></CHAPTER></BIBLEBOOK>
</XMLBIBLE>"#;
        let file = dir.path().join("Lingala 1952.xml");
        std::fs::write(&file, xml).unwrap();
        let payload = load_bible_file(&file, "Lingala", "ln").unwrap();
        assert_eq!(payload.module, "file_lingala1952");
        assert_eq!(payload.name, "Biblia na Lingala");
        assert_eq!(payload.verses.len(), 2);
        assert_eq!(payload.verses[0].text, "Pamba te Nzambe alingaki mokili mingi");
        assert_eq!(payload.verses[0].book, 43);

        let path = dir.path().join("project_on.db");
        let (mut db, _) = Database::open_and_initialize(&path, &InitOptions::default()).unwrap();
        let id = db.install_bible(&payload).unwrap();
        let installed = db.installed_bibles().unwrap();
        let lingala = installed.iter().find(|b| b.module == payload.module).unwrap();
        assert_eq!((lingala.id, lingala.verses, lingala.shortname.as_str()), (id, 2, "Lingala"));
        // Réinstaller remplace (pas de doublon).
        db.install_bible(&payload).unwrap();
        assert_eq!(db.installed_bibles().unwrap().iter().filter(|b| b.module == payload.module).count(), 1);
        assert_eq!(db.list_translation_verses(id, 43, 3).unwrap().len(), 2);

        assert!(db.remove_bible(&payload.module).unwrap());
        assert!(db.removed_bibles().contains(&payload.module));
        assert!(!db.installed_bibles().unwrap().iter().any(|b| b.module == payload.module));
        drop(db);
        let db = Database::open(&path, Mode::ReadOnly).unwrap();
        assert!(db.removed_bibles().contains(&payload.module));
    }

    #[test]
    fn scrollmapper_and_compressed_bibles_are_read() {
        let dir = scratch();
        let data = serde_json::json!({
            "translation": "King James Version: 1769",
            "books": [{"name": "John", "chapters": [{"chapter": 3, "verses": [{"verse": 16, "text": "For God so loved"}]}]},
                      {"name": "Tobit", "chapters": [{"chapter": 1, "verses": [{"verse": 1, "text": "x"}]}]}]
        });
        let file = dir.path().join("KJV.json.gz");
        let mut gz = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::default());
        std::io::Write::write_all(&mut gz, data.to_string().as_bytes()).unwrap();
        std::fs::write(&file, gz.finish().unwrap()).unwrap();
        let payload = load_bible_file(&file, "", "en").unwrap();
        assert_eq!(payload.shortname, "King James Version");
        assert_eq!(payload.verses.len(), 1);
        assert_eq!(payload.verses[0].book_name, "John");
        // Les Bibles fournies avec l'application (format Project-On, compressées).
        let bundled = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../bibles/sm_kjv.json.gz");
        if bundled.is_file() {
            let kjv = load_bible_file(&bundled, "", "en").unwrap();
            assert_eq!(kjv.module, "sm_kjv");
            assert!(kjv.verses.len() > 30_000, "{}", kjv.verses.len());
        }
        let bad = dir.path().join("photo.json");
        std::fs::write(&bad, "{\"x\": 1}").unwrap();
        assert!(load_bible_file(&bad, "", "fr").is_err());
    }
}
