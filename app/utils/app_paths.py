from __future__ import annotations

import json
import logging
import os
import shutil
import sys
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


def import_media_file(source: str | Path) -> Path | None:
    """Copie un média dans la bibliothèque utilisateur (dédupliqué).

    Retourne le chemin de la copie, ou None si la source est absente.
    Un fichier de même nom et même taille déjà présent est réutilisé.
    """
    src = Path(str(source))
    if not src.is_file():
        return None
    dest = media_dir() / src.name
    if not dest.exists() or dest.stat().st_size != src.stat().st_size:
        shutil.copy2(src, dest)
    return dest


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


def ensure_data_initialized() -> None:
    """Ensure that the data directory and initial databases exist in AppData.

    If running as a bundled app and the database doesn't exist in AppData,
    copy the initial databases from the bundled resources.
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
        if not dst_file.exists():
            try:
                shutil.copy2(src_file, dst_file)
            except Exception as e:
                log.error("Error copying initial data file %s: %s", src_file.name, e)


# Version du pack de données éditorial embarqué dans l'installeur.
# 2 = Exposé des Sept Âges corrigé (lectures bibliques fusionnées en un seul
# paragraphe, résidus de mise en page purgés). Incrémenter à chaque fois que
# le contenu embarqué doit converger vers les bases déjà installées : les
# chapitres « BK-AGES-% » sont alors remplacés depuis la base embarquée, une
# seule fois, sans toucher aux cantiques, playlists et réglages de l'utilisateur.
DATA_PACK_VERSION = 2


def upgrade_data_pack(target_path: Path, bundled_path: Path) -> bool:
    """Remplace les chapitres de l'Exposé (dates ``BK-AGES-%``) par ceux du pack.

    Les bases utilisateur ne sont jamais écrasées, mais le contenu éditorial
    corrigé doit converger : si la base cible porte un ``data_pack_version``
    antérieur à :data:`DATA_PACK_VERSION`, les lignes BK-AGES sont remplacées
    depuis la base embarquée dans une transaction atomique. Retourne True si
    une migration a été appliquée.
    """
    import sqlite3

    if not target_path.is_file() or not bundled_path.is_file():
        return False
    connection = None
    try:
        connection = sqlite3.connect(target_path, timeout=120.0)
        row = connection.execute(
            "SELECT value FROM app_meta WHERE key = 'data_pack_version'"
        ).fetchone()
        if row is not None:
            try:
                if int(row[0]) >= DATA_PACK_VERSION:
                    return False
            except (TypeError, ValueError):
                pass

        connection.execute("BEGIN IMMEDIATE")
        connection.execute("ATTACH DATABASE ? AS pack", (str(bundled_path),))
        connection.execute(
            """
            DELETE FROM sermon_paragraph
            WHERE sermon_id IN (
                SELECT id FROM sermon WHERE date LIKE 'BK-AGES-%'
            )
            """
        )
        connection.execute("DELETE FROM sermon WHERE date LIKE 'BK-AGES-%'")
        connection.execute(
            """
            INSERT INTO sermon (title, date, tradition, language, source_path,
                                sort_key, location, canonical_title, title_search)
            SELECT title, date, tradition, language, source_path,
                   sort_key, location, canonical_title, title_search
            FROM pack.sermon
            WHERE date LIKE 'BK-AGES-%'
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
            """
            INSERT INTO _pack_map (old_id, new_id)
            SELECT p.id, s.id
            FROM pack.sermon p
            JOIN sermon s ON s.date = p.date AND s.tradition = p.tradition
            WHERE p.date LIKE 'BK-AGES-%'
            """
        )
        connection.execute(
            """
            INSERT INTO sermon_paragraph (sermon_id, paragraph_no, ref, text, marker)
            SELECT m.new_id, p.paragraph_no, p.ref, p.text, p.marker
            FROM pack.sermon_paragraph p
            JOIN _pack_map m ON m.old_id = p.sermon_id
            """
        )
        connection.execute("DROP TABLE _pack_map")
        connection.execute(
            """
            INSERT INTO app_meta (key, value) VALUES ('data_pack_version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (str(DATA_PACK_VERSION),),
        )
        connection.execute("COMMIT")
        connection.execute("DETACH DATABASE pack")
        log.info("Data pack v%s appliqué à %s", DATA_PACK_VERSION, target_path)
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
