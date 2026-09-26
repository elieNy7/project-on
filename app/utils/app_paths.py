from __future__ import annotations

import glob
import json
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
import uuid
from contextlib import closing
from pathlib import Path

log = logging.getLogger(__name__)

BOOTSTRAP_DATA_FILES = {"project_on.db", "sermons_vgr.db"}

# Bump when the bundled default backgrounds change so existing installs are
# refreshed with the new artwork (and retired ones are removed) on next launch.
# v7 : rendu enrichi (halo, voile de lisibilité central, grain anti-banding)
# + familles « texte lourd » (bg-texte-*) et « clair » (bg-clair-*).
DEFAULT_BG_VERSION = 7
# Default backgrounds that earlier versions shipped and that we now retire.
# Removed on upgrade even for installs predating the version marker.
RETIRED_DEFAULT_BACKGROUNDS = {
    f"bg-symbole-{slug}_{ratio}.png"
    for slug in (
        "trinite",
        "alpha-omega",
        "chi-rho",
        "ichthys",
        "croix-rayonnante",
    )
    for ratio in ("16x9", "4x3", "9x16")
}


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False)) and hasattr(sys, "_MEIPASS")


def project_root() -> Path:
    """Root of the source tree (dev)."""
    return Path(__file__).resolve().parents[2]


def resource_root() -> Path:
    """Root for bundled resources.

    - dev: project root
    - PyInstaller: sys._MEIPASS
    """
    if is_frozen():
        return Path(sys._MEIPASS)
    return project_root()


def app_root() -> Path:
    """Root directory of the running app.

    - dev: project root
    - frozen: directory containing the executable
    """
    if bool(getattr(sys, "frozen", False)):
        return Path(sys.executable).resolve().parent
    return project_root()


def user_data_dir() -> Path:
    """Writable user data directory (Windows-friendly).

    Priority:
    1. Registry key set by installer (HKCU\\Software\\Project-On\\DataPath)
    2. %APPDATA%\\Project-On (standard Windows location)
    3. Fallback to %LOCALAPPDATA%\\Project-On
    """
    # Try to read from Windows registry (set by installer)
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Software\Project-On"
            ) as key:
                data_path, _ = winreg.QueryValueEx(key, "DataPath")
                if data_path and Path(data_path).exists():
                    return Path(data_path).parent  # DataPath points to 'data' subfolder
        except (OSError, FileNotFoundError, ImportError):
            pass

    # Standard location: %APPDATA%\Project-On
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Project-On"

    # Fallback
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Project-On"


def ensure_presentation_workdir() -> Path:
    """Return a writable presentation directory.

    In development mode: use project's presentation folder directly.
    In production (frozen): copy to AppData and keep updated.
    """
    # In development, use the project's presentation folder directly
    if not is_frozen():
        workdir = resource_root() / "presentation"
        workdir.mkdir(parents=True, exist_ok=True)
        return workdir

    # In production, copy to AppData
    workdir = user_data_dir() / "presentation"
    src = resource_root() / "presentation"

    workdir.mkdir(parents=True, exist_ok=True)

    # Files that should always be updated (contain application logic)
    always_update = {
        "obs-style.css",
        "obs-script.js",
        "obs.html",
        "fonts.css",
        "index.html",
        "style.css",
        "script.js",
    }

    # Copy static presentation assets if missing
    marker = workdir / ".initialized"
    if src.exists() and src.is_dir():
        for item in src.iterdir():
            dst_item = workdir / item.name
            if item.is_dir():
                if not dst_item.exists():
                    shutil.copytree(item, dst_item)
            # Always update critical files, copy others only if missing
            elif item.name in always_update or not dst_item.exists():
                shutil.copy2(item, dst_item)

    if not marker.exists():
        marker.write_text("ok", encoding="utf-8")

    return workdir


def data_dir() -> Path:
    """Return the data directory.

    - dev (not frozen): project_root / data
    - production (frozen): AppData / data
    """
    if is_frozen():
        return user_data_dir() / "data"
    return resource_root() / "data"


def logs_dir() -> Path:
    """Return the directory where application and crash logs are stored."""
    return data_dir() / "logs"


def settings_path() -> Path:
    return data_dir() / "settings.json"


def app_db_path() -> Path:
    return data_dir() / "project_on.db"


def sermons_vgr_db_path() -> Path | None:
    """Return path to the sermons_vgr.db database if present.

    Checks data_dir() first (which handles dev vs prod),
    then resources (as a fallback).
    """
    # data_dir() already points to project/data in dev, and appdata/data in prod
    p = data_dir() / "sermons_vgr.db"
    if p.exists() and p.is_file():
        return p

    # Check resource root fallback (mostly for prod if not in appdata)
    p = resource_root() / "data" / "sermons_vgr.db"
    if p.exists() and p.is_file():
        return p

    return None


def bible_json_dir() -> Path:
    return resource_root() / "bible_json"


def ndi_dir() -> Path:
    """Optional NDI runtime folder.

    Searched in both the app folder (portable distribution) and the bundled
    resource folder (PyInstaller onefile/onefolder).
    """
    return app_root() / "ndi"


def assets_dir() -> Path:
    """Return the assets directory path."""
    return resource_root() / "assets"


def backgrounds_dir() -> Path:
    """Return the user backgrounds directory, creating it if needed."""
    d = user_data_dir() / "backgrounds"
    d.mkdir(parents=True, exist_ok=True)
    return d


def media_dir() -> Path:
    """Return the user media library directory (images + vidéos)."""
    d = user_data_dir() / "media"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _content_identity(path: Path) -> str:
    """Empreinte stable du contenu d'un fichier (SHA-256 hexadécimal)."""
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def import_media_file(source: str | Path) -> Path | None:
    """Copie un média dans la bibliothèque utilisateur (dédupliqué par contenu).

    Retourne le chemin de la copie, ou None si la source est absente.

    La déduplication repose sur l'identité du contenu (SHA-256), jamais sur le
    couple nom/taille : deux fichiers différents ne peuvent plus s'écraser
    mutuellement. Chaque copie est effectuée dans un fichier temporaire du
    dossier cible puis publiée par renommage atomique : une copie interrompue
    ne laisse jamais un fichier tronqué sous un nom définitif.
    """
    src = Path(str(source))
    if not src.is_file():
        return None

    identity = _content_identity(src)
    library = media_dir()
    library.mkdir(parents=True, exist_ok=True)

    # Include legacy filenames; equal size alone is never an identity check.
    for candidate in sorted(library.iterdir()):
        if (candidate.is_file() and not candidate.name.startswith(".importing-")
                and candidate.suffix.lower() == src.suffix.lower()
                and candidate.stat().st_size == src.stat().st_size
                and _content_identity(candidate) == identity):
            return candidate

    dest = library / f"{src.stem[:80]}__{identity}{src.suffix.lower()}"
    if dest.is_file():
        # Un import précédent, même avec un autre nom source, a déjà publié
        # exactement ce contenu.
        if _content_identity(dest) == identity:
            return dest
        dest = library / f"{src.stem[:80]}__{uuid.uuid4().hex}{src.suffix.lower()}"

    fd, name = tempfile.mkstemp(prefix=".importing-", dir=library)
    os.close(fd)
    temporary = Path(name)
    try:
        shutil.copy2(src, temporary)
        if _content_identity(temporary) != identity:
            raise OSError(f"Copie média incohérente : {src.name}")
        with temporary.open("rb+") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, dest)
        return dest
    finally:
        temporary.unlink(missing_ok=True)


def seed_default_backgrounds() -> None:
    """Copy the bundled default backgrounds into the user backgrounds folder.

    First launch: copies only files that are missing, so user-added images are
    preserved and deletions are not resurrected on the same launch.

    On a defaults version bump: refreshes the bundled defaults (overwrites their
    copies with the new artwork) and removes retired defaults — without ever
    touching images the user added themselves. A ``.defaults_version`` marker
    records the version and the set of managed default filenames.
    """
    source_dir = assets_dir() / "backgrounds"
    if not source_dir.is_dir():
        return
    target_dir = backgrounds_dir()

    bundled = [f for f in source_dir.iterdir() if f.is_file()]
    bundled_names = {f.name for f in bundled}

    marker = target_dir / ".defaults_version"
    prev_version = 0
    prev_files: set[str] = set()
    if marker.exists():
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            prev_version = int(data.get("version", 0))
            prev_files = set(data.get("files", []))
        except Exception:
            prev_version, prev_files = 0, set()

    upgrading = prev_version < DEFAULT_BG_VERSION

    # On upgrade, remove previously-managed defaults that are no longer bundled
    # (plus explicitly retired ones for installs predating the marker).
    if upgrading:
        for stale in (prev_files - bundled_names) | RETIRED_DEFAULT_BACKGROUNDS:
            try:
                (target_dir / stale).unlink(missing_ok=True)
            except Exception as e:
                log.error("Error removing retired background %s: %s", stale, e)

    for src_file in bundled:
        dst_file = target_dir / src_file.name
        # First run: copy missing only. Upgrade: overwrite managed defaults so
        # users actually receive the corrected artwork.
        if dst_file.exists() and not upgrading:
            continue
        try:
            shutil.copy2(src_file, dst_file)
        except Exception as e:
            log.error("Error seeding background %s: %s", src_file.name, e)

    try:
        marker.write_text(
            json.dumps(
                {"version": DEFAULT_BG_VERSION, "files": sorted(bundled_names)}
            ),
            encoding="utf-8",
        )
    except Exception as e:
        log.error("Error writing backgrounds marker: %s", e)


def _sqlite_ok(path: Path) -> bool:
    """Contrôle d'intégrité rapide d'un fichier base SQLite.

    Toute connexion est fermée avant le retour : sur Windows, un descripteur
    laissé ouvert empêcherait le renommage atomique suivant.
    """
    conn = None
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        row = conn.execute("PRAGMA quick_check").fetchone()
        return bool(row) and str(row[0]).lower() == "ok"
    except sqlite3.Error:
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass


def ensure_data_initialized() -> None:
    """Ensure that the data directory and initial databases exist in AppData.

    If running as a bundled app and the database doesn't exist in AppData,
    copy the initial databases from the bundled resources.

    Chaque copie est publiée par renommage atomique après vérification
    d'intégrité : une interruption ne laisse jamais une base tronquée sous le
    nom définitif, et la reprise est possible au lancement suivant. Une base
    utilisateur existante n'est jamais remplacée en silence.
    """
    target_dir = data_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    # If not frozen, we use the local data directory, so no need to copy
    if not is_frozen():
        return

    source_dir = resource_root() / "data"
    if not source_dir.exists():
        return

    for src_file in source_dir.iterdir():
        if not src_file.is_file() or src_file.name not in BOOTSTRAP_DATA_FILES:
            continue

        dst_file = target_dir / src_file.name
        if dst_file.exists():
            if _sqlite_ok(dst_file):
                continue
            # Base présente mais illisible : on ne sait pas distinguer un
            # fichier utilisateur corrompu d'un vestige de copie interrompue.
            # Par prudence, ne jamais remplacer en silence : l'erreur sera
            # remontée par l'ouverture applicative de la base.
            log.error(
                "Base %s illisible : amorçage ignoré (aucun remplacement "
                "silencieux)",
                dst_file.name,
            )
            continue

        temporary = target_dir / f"{src_file.name}.bootstrap-{os.getpid()}"
        try:
            shutil.copy2(src_file, temporary)
            if not _sqlite_ok(temporary):
                raise OSError(
                    f"La base amorcée {src_file.name} a échoué au contrôle "
                    "d'intégrité"
                )
            os.replace(temporary, dst_file)
        except Exception as e:
            log.error("Error copying initial data file %s: %s", src_file.name, e)
            try:
                temporary.unlink()
            except OSError:
                pass


# Version du pack de données éditorial embarqué dans l'installeur.
# 2 = Exposé des Sept Âges corrigé (lectures bibliques fusionnées en un seul
# paragraphe, résidus de mise en page purgés).
# 3 = sermons SHP réimportés depuis les PDF (un alinéa par ligne, paragraphes
# sans en-tête récupérés, titre/lieu/date imprimés).
# 4 = onglet « Livres » : deux livres et dix brochures (``BK-*``, ``TR-*``).
# Incrémenter à chaque fois que le contenu embarqué doit converger vers les
# bases déjà installées : les livres (« BK-% », « TR-% ») et les sermons SHP
# sont alors remplacés depuis la base embarquée, une seule fois, sans toucher
# aux cantiques, playlists et réglages de l'utilisateur.
DATA_PACK_VERSION = 4

# Contenu éditorial remplacé par le pack (alias de table ``s``).
_PACK_SCOPE = "(s.date LIKE 'BK-%' OR s.date LIKE 'TR-%' OR s.tradition = 'SHP')"
_PACK_SERMON_COLUMNS = (
    "title", "date", "tradition", "language", "source_path", "sort_key",
    "location", "canonical_title", "title_search",
)
_PACK_OPTIONAL_COLUMNS = ("printed_date", "printed_location")


def data_pack_pending(target_path: Path, bundled_path: Path) -> bool:
    """Lecture rapide : la base cible attend-elle le pack de contenu ?"""
    if not target_path.is_file() or not bundled_path.is_file():
        return False
    try:
        with closing(sqlite3.connect(target_path, timeout=30.0)) as connection:
            row = connection.execute(
                "SELECT value FROM app_meta WHERE key = 'data_pack_version'"
            ).fetchone()
    except sqlite3.Error:
        return False
    try:
        return row is None or int(row[0]) < DATA_PACK_VERSION
    except (TypeError, ValueError):
        return True


def _remove_stale_pack_backups(target_path: Path) -> None:
    """Supprime les sauvegardes pré-pack laissées par des tentatives interrompues.

    Chaque tentative copiait toute la base (plusieurs centaines de Mo) ; une
    migration interrompue à répétition remplissait le disque. Seule la
    sauvegarde de la tentative en cours est conservée.
    """
    for leftover in target_path.parent.glob(glob.escape(target_path.name) + ".pre-datapack-*"):
        try:
            leftover.unlink()
        except OSError:
            log.warning("Sauvegarde pré-pack non supprimée : %s", leftover.name)


def upgrade_data_pack(target_path: Path, bundled_path: Path) -> bool:
    """Remplace l'Exposé (``BK-AGES-%``) et les sermons SHP par ceux du pack.

    Les bases utilisateur ne sont jamais écrasées, mais le contenu éditorial
    corrigé doit converger : si la base cible porte un ``data_pack_version``
    antérieur à :data:`DATA_PACK_VERSION`, ces lignes sont remplacées
    depuis la base embarquée dans une transaction atomique. Retourne True si
    une migration a été appliquée.

    Fiabilité : la reconstruction de l'index FTS des sermons est exécutée dans
    la même transaction que le remplacement de contenu — l'index ne peut plus
    rester obsolète après un remplacement à nombre de lignes identique. Le
    marqueur de maintenance de démarrage est retiré de la transaction pour
    replanifier la resynchronisation complète (titres, marqueurs) au prochain
    lancement ; une sauvegarde de la base est prise avant migration.
    """
    if not target_path.is_file() or not bundled_path.is_file():
        return False

    connection = None
    try:
        connection = sqlite3.connect(target_path, timeout=120.0, uri=True)
        row = connection.execute(
            "SELECT value FROM app_meta WHERE key = 'data_pack_version'"
        ).fetchone()
        if row is not None:
            try:
                if int(row[0]) >= DATA_PACK_VERSION:
                    return False
            except (TypeError, ValueError):
                pass

        if target_path.resolve() == bundled_path.resolve():
            return False
        connection.execute("PRAGMA foreign_keys=ON")
        # immutable=1 : la base embarquée (Program Files, non inscriptible)
        # est lue sans créer de fichiers -wal/-shm à côté d'elle.
        connection.execute(
            "ATTACH DATABASE ? AS pack",
            (bundled_path.resolve().as_uri() + "?mode=ro&immutable=1",),
        )
        if connection.execute("PRAGMA pack.quick_check").fetchone()[0] != "ok":
            raise ValueError("Pack illisible")
        chapters = connection.execute(
            "SELECT s.date, s.tradition, COUNT(*) FROM pack.sermon s "
            f"WHERE {_PACK_SCOPE} GROUP BY s.date, s.tradition"
        ).fetchall()
        if not chapters or any(row[2] != 1 for row in chapters):
            raise ValueError("Pack vide ou chapitres ambigus")
        if connection.execute(
            f"SELECT 1 FROM pack.sermon s WHERE {_PACK_SCOPE} AND "
            "(trim(s.title)='' OR NOT EXISTS (SELECT 1 FROM pack.sermon_paragraph p "
            "WHERE p.sermon_id=s.id AND trim(p.text) != '')) LIMIT 1"
        ).fetchone():
            raise ValueError("Pack incomplet")
        from app.utils.backup_manager import create_database_backup
        _remove_stale_pack_backups(target_path)
        create_database_backup(target_path, target_path.with_name(
            target_path.name + ".pre-datapack-" + uuid.uuid4().hex + ".db"))
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            f"""
            DELETE FROM sermon_paragraph
            WHERE sermon_id IN (SELECT s.id FROM sermon s WHERE {_PACK_SCOPE})
            """
        )
        connection.execute(f"DELETE FROM sermon AS s WHERE {_PACK_SCOPE}")
        # Colonnes récentes (date/lieu imprimés) copiées si les deux bases
        # les ont ; les noms viennent d'une liste fixe.
        target_cols = {r[1] for r in connection.execute("PRAGMA main.table_info(sermon)")}
        pack_cols = {r[1] for r in connection.execute("PRAGMA pack.table_info(sermon)")}
        columns = ", ".join(
            _PACK_SERMON_COLUMNS
            + tuple(c for c in _PACK_OPTIONAL_COLUMNS if c in target_cols and c in pack_cols)
        )
        connection.execute(
            f"""
            INSERT INTO sermon ({columns})
            SELECT {columns}
            FROM pack.sermon s
            WHERE {_PACK_SCOPE}
            """
        )
        # Les identifiants du pack ne correspondent pas à ceux de la base
        # cible : remapper les paragraphes sur les nouveaux ids de sermons
        # (date + tradition identifient un chapitre de façon unique).
        connection.execute(
            "CREATE TEMP TABLE _pack_map "
            "(old_id INTEGER PRIMARY KEY, new_id INTEGER NOT NULL)"
        )
        connection.execute(
            f"""
            INSERT INTO _pack_map (old_id, new_id)
            SELECT s.id, t.id
            FROM pack.sermon s
            JOIN sermon t ON t.date = s.date AND t.tradition = s.tradition
            WHERE {_PACK_SCOPE}
            """
        )
        connection.execute(
            """
            INSERT INTO sermon_paragraph (sermon_id, paragraph_no, ref, text, marker)
            SELECT m.new_id, p.paragraph_no, p.ref, p.text, p.marker
            FROM pack.sermon_paragraph p
            JOIN _pack_map m ON m.old_id = p.sermon_id
            WHERE p.rowid IN (
                -- Un seul alinéa par numéro (le dernier). Agrégat linéaire :
                -- l'ancien NOT EXISTS corrélé faisait des centaines de
                -- millions de recherches et figeait le démarrage.
                SELECT max(q.rowid) FROM pack.sermon_paragraph q
                GROUP BY q.sermon_id, q.paragraph_no
            )
            """
        )
        connection.execute("DROP TABLE _pack_map")
        # Catalogue des livres de l'onglet « Livres ».
        if connection.execute(
            "SELECT 1 FROM pack.sqlite_master WHERE type='table' AND name='library_book'"
        ).fetchone():
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS library_book (
                    key TEXT PRIMARY KEY, title TEXT NOT NULL, date_prefix TEXT NOT NULL,
                    tradition TEXT NOT NULL, sort_order INTEGER DEFAULT 0, source TEXT DEFAULT ''
                )
                """
            )
            connection.execute(
                "INSERT OR REPLACE INTO library_book "
                "(key, title, date_prefix, tradition, sort_order, source) "
                "SELECT key, title, date_prefix, tradition, sort_order, source "
                "FROM pack.library_book"
            )
        connection.execute(
            """
            INSERT INTO app_meta (key, value) VALUES ('data_pack_version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (str(DATA_PACK_VERSION),),
        )
        # Index de recherche : reconstruit dans la même transaction que le
        # remplacement de contenu, pour que le résultat des recherches reflète
        # immédiatement le nouveau contenu.
        fts_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='sermon_paragraph_fts'"
        ).fetchone()
        if fts_exists:
            connection.execute("DROP TABLE IF EXISTS sermon_paragraph_fts")
            connection.execute(
                "CREATE VIRTUAL TABLE sermon_paragraph_fts USING fts5("
                "text, ref, sermon_title, canonical_title, "
                "content='', detail=full, "
                "tokenize='unicode61 remove_diacritics 2')"
            )
            connection.execute(
                """
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
                """
            )
        # Marqueur durable : retirer le repère de maintenance terminée pour que
        # le prochain démarrage resynchronise titres canoniques et index. Ceci
        # fait partie de la transaction : si la migration échoue, le marqueur
        # reste en place.
            connection.execute(
                "DELETE FROM app_meta WHERE key = 'startup_maintenance_version'"
            )
        connection.execute("COMMIT")
        # Le verrou d'écriture est libéré : publiée ou non, la sauvegarde
        # pré-migration doit refléter la base d'origine vérifiée.
        return True
    except sqlite3.Error as error:
        log.error("Data pack upgrade impossible : %s", error)
        try:
            if connection is not None:
                connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        return False
    finally:
        if connection is not None:
            connection.close()
