//! Le journal (`data\logs\project-on.log`), repris de celui de Pgraphics : de quoi comprendre un
//! incident chez une église, sans jamais remplir son disque.
//!
//! - Au lancement, un journal de plus de 5 Mo part en archive (`project-on.1.log` … `.5.log`, le
//!   plus ancien est effacé), comme les cinq fichiers tournants de la 2.8.
//! - Chaque ligne est datée. Au-delà de 20 Mo dans un même lancement, plus rien n'est écrit : un
//!   message répété à chaque image ne remplit pas le disque pendant un long culte.
//! - Le journal n'est jamais une raison de s'arrêter : une écriture impossible est ignorée.
//!
//! Les rapports de plantage (minidumps, code `unsafe` de Windows) restent dans l'application.

use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Mutex, OnceLock};

/// Au-delà, le journal part en archive au lancement suivant.
const MAX_BYTES: u64 = 5 * 1024 * 1024;
/// Les archives gardées (`project-on.1.log` est la plus récente).
const OLD_LOGS: u32 = 5;
/// Ce qu'un lancement peut écrire au plus.
const MAX_WRITTEN: usize = 20 * 1024 * 1024;

const FILE: &str = "project-on.log";

/// Le journal d'un dossier.
#[derive(Debug)]
pub struct Journal {
    dir: PathBuf,
    written: AtomicUsize,
    /// Une ligne à la fois : deux fils n'entremêlent jamais leurs lignes.
    lock: Mutex<()>,
}

impl Journal {
    /// Ouvre le journal de `dir` et fait tourner les archives si besoin.
    pub fn open(dir: impl Into<PathBuf>) -> Self {
        let journal = Self { dir: dir.into(), written: AtomicUsize::new(0), lock: Mutex::new(()) };
        journal.rotate();
        journal
    }

    pub fn path(&self) -> PathBuf {
        self.dir.join(FILE)
    }

    fn archive(&self, n: u32) -> PathBuf {
        self.dir.join(format!("project-on.{n}.log"))
    }

    fn rotate(&self) {
        if std::fs::metadata(self.path()).is_ok_and(|m| m.len() > MAX_BYTES) {
            let _ = std::fs::remove_file(self.archive(OLD_LOGS));
            for n in (1..OLD_LOGS).rev() {
                let _ = std::fs::rename(self.archive(n), self.archive(n + 1));
            }
            let _ = std::fs::rename(self.path(), self.archive(1));
        }
    }

    /// Le journal et ses archives, du plus récent au plus ancien.
    pub fn files(&self) -> Vec<PathBuf> {
        std::iter::once(self.path()).chain((1..=OLD_LOGS).map(|n| self.archive(n))).filter(|p| p.is_file()).collect()
    }

    /// Ajoute une ligne datée.
    pub fn line(&self, text: &str) {
        let stamped = format!("{} {text}\n", chrono::Local::now().format("%Y-%m-%d %H:%M:%S"));
        self.append(&stamped);
    }

    /// Ajoute un texte tel quel (une panique et sa pile d'appels, par exemple).
    pub fn append(&self, text: &str) {
        let before = self.written.fetch_add(text.len(), Ordering::Relaxed);
        if before > MAX_WRITTEN {
            return;
        }
        let _guard = self.lock.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        let _ = std::fs::create_dir_all(&self.dir);
        if let Ok(mut file) = std::fs::OpenOptions::new().create(true).append(true).open(self.path()) {
            let _ = file.write_all(text.as_bytes());
            if before + text.len() > MAX_WRITTEN {
                let _ = file.write_all(b"(trop de messages : la suite de ce lancement n'est pas gardee)\n");
            }
        }
    }
}

static GLOBAL: OnceLock<Journal> = OnceLock::new();

/// Installe le journal de l'application (une fois, au lancement). Rend `false` s'il l'était déjà.
pub fn install(dir: &Path) -> bool {
    GLOBAL.set(Journal::open(dir)).is_ok()
}

/// Le journal de l'application, s'il est installé.
pub fn global() -> Option<&'static Journal> {
    GLOBAL.get()
}

/// Une ligne au journal de l'application (et sur la sortie d'erreur, utile en développement).
pub fn line(text: &str) {
    eprintln!("[project-on] {text}");
    if let Some(journal) = GLOBAL.get() {
        journal.line(text);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Un dossier temporaire sous `target/tmp` : sur certains postes, le dossier temporaire de
    /// Windows est fermé en écriture aux programmes de test.
    fn scratch() -> tempfile::TempDir {
        let base = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/tmp");
        std::fs::create_dir_all(&base).unwrap();
        tempfile::tempdir_in(base).unwrap()
    }

    #[test]
    fn lines_are_dated_and_appended() {
        let dir = scratch();
        let journal = Journal::open(dir.path().join("logs"));
        journal.line("Project-On démarre");
        journal.line("base ouverte");
        let text = std::fs::read_to_string(journal.path()).unwrap();
        let lines: Vec<&str> = text.lines().collect();
        assert_eq!(lines.len(), 2);
        assert!(lines[0].ends_with(" Project-On démarre"));
        assert_eq!(lines[0].as_bytes()[4], b'-'); // « AAAA-MM-JJ HH:MM:SS »
    }

    #[test]
    fn a_big_journal_is_archived_at_launch() {
        let dir = scratch();
        let first = Journal::open(dir.path());
        std::fs::write(first.path(), vec![b'x'; MAX_BYTES as usize + 1]).unwrap();
        std::fs::write(first.archive(OLD_LOGS), b"le plus ancien").unwrap();
        std::fs::write(first.archive(1), b"ancien 1").unwrap();
        let second = Journal::open(dir.path());
        assert!(!second.path().exists());
        assert_eq!(std::fs::metadata(second.archive(1)).unwrap().len(), MAX_BYTES + 1);
        assert_eq!(std::fs::read(second.archive(2)).unwrap(), b"ancien 1");
        assert!(!second.archive(OLD_LOGS + 1).exists());
        second.line("nouveau");
        assert_eq!(second.files().len(), 3);
    }
}
