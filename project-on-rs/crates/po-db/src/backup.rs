//! La copie cohérente d'une base ouverte (`create_database_backup` de la 2.8) : l'API de sauvegarde
//! de SQLite prend un instantané même pendant que Project-On l'utilise (une copie de fichier
//! oublierait le journal WAL), la copie est vérifiée, puis publiée par renommage.
//!
//! C'est aussi elle qui donnera à la bêta 3.0 sa copie des données de la 2.x.

use std::path::{Path, PathBuf};
use std::time::Duration;

use rusqlite::backup::{Backup, StepResult};
use rusqlite::{Connection, OpenFlags};

use crate::{DbError, Result};

/// Une copie réussie.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BackupReport {
    pub path: PathBuf,
    pub size_bytes: u64,
}

/// Sans progrès pendant ce temps (base verrouillée par un autre programme), la copie abandonne :
/// la 2.8 réessayait indéfiniment, et l'application restait figée.
const STALL_LIMIT: Duration = Duration::from_secs(60);

/// Les pages de `from` vers `to`, 2048 à la fois (8 Mo), avec une courte pause quand la base est
/// occupée.
fn copy_pages(from: &Connection, to: &mut Connection) -> Result<()> {
    let backup = Backup::new(from, to)?;
    let mut last_progress = std::time::Instant::now();
    let mut remaining = i32::MAX;
    loop {
        match backup.step(2048)? {
            StepResult::Done => return Ok(()),
            StepResult::More => {}
            StepResult::Busy | StepResult::Locked => std::thread::sleep(Duration::from_millis(10)),
            _ => std::thread::sleep(Duration::from_millis(10)),
        }
        let now = backup.progress().remaining;
        if now < remaining {
            remaining = now;
            last_progress = std::time::Instant::now();
        } else if last_progress.elapsed() > STALL_LIMIT {
            return Err(DbError::Busy);
        }
    }
}

/// Copie `source` dans `destination` sans jamais laisser une copie à moitié écrite sous le nom
/// final. La copie (et elle seule) passe un `quick_check`.
pub fn copy_database(source: &Path, destination: &Path) -> Result<BackupReport> {
    if !source.is_file() {
        return Err(DbError::Missing { path: source.display().to_string() });
    }
    let same = match (source.canonicalize(), destination.canonicalize()) {
        (Ok(a), Ok(b)) => a == b,
        _ => false,
    };
    if same {
        return Err(DbError::SameFile);
    }
    if let Some(dir) = destination.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let mut temporary = destination.as_os_str().to_owned();
    temporary.push(".tmp");
    let temporary = PathBuf::from(temporary);
    let _ = std::fs::remove_file(&temporary);

    let result = (|| -> Result<()> {
        let from =
            Connection::open_with_flags(source, OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX)?;
        from.busy_timeout(Duration::from_secs(30))?;
        let mut to = Connection::open(&temporary)?;
        copy_pages(&from, &mut to)?;
        let verdict: String = to.query_row("PRAGMA quick_check", [], |r| r.get(0))?;
        if !verdict.eq_ignore_ascii_case("ok") {
            return Err(DbError::BadCopy(verdict));
        }
        drop(to);
        std::fs::rename(&temporary, destination)?;
        Ok(())
    })();
    if let Err(e) = result {
        let _ = std::fs::remove_file(&temporary);
        return Err(e);
    }
    Ok(BackupReport { path: destination.to_path_buf(), size_bytes: std::fs::metadata(destination)?.len() })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Database, InitOptions, Mode};

    fn scratch() -> tempfile::TempDir {
        let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
        std::fs::create_dir_all(&base).unwrap();
        tempfile::tempdir_in(base).unwrap()
    }

    #[test]
    fn copies_an_open_database_with_its_wal() {
        let dir = scratch();
        let source = dir.path().join("project_on.db");
        let (mut db, _) = Database::open_and_initialize(&source, &InitOptions::default()).unwrap();
        // Une écriture encore dans le journal WAL au moment de la copie.
        let folder = db.create_folder("Culte du dimanche").unwrap();
        let copy = dir.path().join("copie").join("project_on.db");
        let report = copy_database(&source, &copy).unwrap();
        assert!(report.size_bytes > 0);
        let copied = Database::open(&copy, Mode::ReadOnly).unwrap();
        assert_eq!(copied.folder(folder).unwrap().unwrap().name, "Culte du dimanche");
        assert!(matches!(copy_database(&source, &source), Err(DbError::SameFile)));
        assert!(matches!(copy_database(&dir.path().join("absente.db"), &copy), Err(DbError::Missing { .. })));
    }
}
