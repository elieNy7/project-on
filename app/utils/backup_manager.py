from __future__ import annotations

import os
import json
import hashlib
import shutil
import tempfile
import zipfile
from pathlib import PurePosixPath
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BackupResult:
    path: Path
    size_bytes: int
    integrity_message: str


def verify_database(path: Path) -> tuple[bool, str]:
    """Run SQLite's quick integrity check on a database file."""
    database_path = Path(path)
    if not database_path.is_file():
        return False, "Fichier introuvable"

    try:
        with closing(
            sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
        ) as conn:
            row = conn.execute("PRAGMA quick_check").fetchone()
    except sqlite3.Error as exc:
        return False, str(exc)

    message = str(row[0]) if row else "Aucun résultat"
    return message.lower() == "ok", message


def create_database_backup(source: Path, destination: Path) -> BackupResult:
    """Create an atomic, transactionally consistent SQLite backup.

    Copying an active SQLite file with a regular filesystem copy can omit WAL
    transactions.  The SQLite backup API takes a coherent snapshot while the
    application remains open, then the result is verified before publication.
    """
    source_path = Path(source).resolve()
    destination_path = Path(destination).resolve()

    if not source_path.is_file():
        raise FileNotFoundError(f"Base de données introuvable : {source_path}")
    if source_path == destination_path:
        raise ValueError("La sauvegarde doit utiliser un fichier différent de la base active.")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination_path.with_suffix(destination_path.suffix + ".tmp")
    if temporary_path.exists():
        temporary_path.unlink()

    try:
        with closing(sqlite3.connect(str(source_path), timeout=30)) as source_conn:
            with closing(
                sqlite3.connect(str(temporary_path), timeout=30)
            ) as backup_conn:
                source_conn.backup(backup_conn, pages=2048, sleep=0.01)

        valid, integrity_message = verify_database(temporary_path)
        if not valid:
            raise sqlite3.DatabaseError(
                f"La copie a échoué au contrôle d'intégrité : {integrity_message}"
            )

        os.replace(temporary_path, destination_path)
        return BackupResult(
            path=destination_path,
            size_bytes=destination_path.stat().st_size,
            integrity_message=integrity_message,
        )
    except Exception:
        if temporary_path.exists():
            temporary_path.unlink()
        raise


# Only these persisted SQL fields refer to projectable files. Source document
# provenance (sermon.source_path), caches and runtime output are not restored.
_REFERENCE_FIELDS = (("media_item", "path"), ("playlist_item", "background"))


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _safe_settings(value):
    """Remove credentials recursively, including protected DPAPI values."""
    if isinstance(value, dict):
        return {key: _safe_settings(item) for key, item in value.items()
                if not any(word in key.casefold() for word in
                           ("password", "secret", "token", "credential", "api_key"))}
    if isinstance(value, list):
        return [_safe_settings(item) for item in value]
    return value


def _reference_fields(conn):
    for table, column in _REFERENCE_FIELDS:
        columns = {row[1] for row in conn.execute(
            "SELECT * FROM pragma_table_info(?)", (table,))}
        if column in columns:
            yield table, column


def _rewrite_settings(value, mapping):
    if isinstance(value, dict):
        return {key: _rewrite_settings(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite_settings(item, mapping) for item in value]
    if isinstance(value, str):
        return mapping.get(value, value)
    return value


def create_backup_bundle(source: Path, destination: Path, *,
                         media_root: Path | None = None,
                         backgrounds_root: Path | None = None,
                         settings_file: Path | None = None) -> BackupResult:
    """Snapshot DB, managed media/backgrounds and non-secret settings to ZIP.

    Paths are explicit: this service never looks up the real profile. Missing
    referenced media aborts publication. Optional roots include unreferenced
    library assets too. Sources must not be edited during export. The output
    can only be restored into a new profile, not merged into an active one.
    """
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError("La destination ne peut pas être la base active.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".bundle-", dir=destination.parent) as work:
        stage = Path(work)
        db = stage / "data" / "project_on.db"
        create_database_backup(source, db)
        files = {"data/project_on.db": db}
        mapping = {}
        warnings = ["Documents source, caches et sorties live exclus ; secrets exclus."]

        def add_file(path, category, relative=None):
            path = Path(path)
            if not path.is_file():
                raise FileNotFoundError(f"Dépendance introuvable : {path}")
            resolved = path.resolve()
            if resolved == destination or resolved == source or resolved.is_relative_to(stage):
                raise ValueError(f"Dépendance non média : {path}")
            if str(resolved) in mapping:
                mapping[str(path)] = mapping[str(resolved)]
                return
            member = category + "/" + (relative or (hashlib.sha256(
                str(resolved).encode()).hexdigest()[:16] + path.suffix.lower()))
            if member in files:
                raise ValueError(f"Collision dans l'archive : {member}")
            copied = stage / member
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(resolved, copied)
            if _digest(copied) != _digest(resolved):
                raise OSError(f"Fichier modifié pendant la sauvegarde : {path}")
            files[member] = copied
            mapping[str(path)] = member
            mapping[str(resolved)] = member

        for root, category in ((media_root, "media"), (backgrounds_root, "backgrounds")):
            if root is not None:
                root = Path(root).resolve()
                if not root.is_dir():
                    raise FileNotFoundError(f"Dossier introuvable : {root}")
                for path in sorted(root.rglob("*")):
                    if path.is_file() and not path.name.startswith("."):
                        add_file(path, category, path.relative_to(root).as_posix())
        with closing(sqlite3.connect(db)) as conn:
            for table, column in _reference_fields(conn):
                for (value,) in conn.execute(
                        f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" != ?', ("",)):
                    if value not in mapping:
                        add_file(value, "media" if table == "media_item" else "backgrounds")

        settings_member = None
        if settings_file is not None:
            payload = json.loads(Path(settings_file).read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Les paramètres doivent être un objet JSON.")
            payload = _safe_settings(payload)

            def gather_settings(value, key=""):
                if isinstance(value, dict):
                    for k, item in value.items():
                        gather_settings(item, k)
                elif isinstance(value, list):
                    for item in value:
                        gather_settings(item, key)
                elif isinstance(value, str) and value and (
                        "background" in key or "logo" in key or "image_path" in key):
                    if value not in mapping and (Path(value).is_absolute() or Path(value).suffix):
                        add_file(value, "backgrounds")
            gather_settings(payload)
            settings_member = "data/settings.json"
            settings_copy = stage / settings_member
            settings_copy.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            files[settings_member] = settings_copy
        manifest = {"format": "project-on-backup", "format_version": 1,
                    "database": "data/project_on.db", "settings": settings_member,
                    "path_map": mapping, "warnings": warnings,
                    "files": {name: {"size": path.stat().st_size, "sha256": _digest(path)}
                              for name, path in files.items()}}
        temporary = stage / "bundle.zip"
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for name, path in files.items():
                archive.write(path, name)
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        # Verify both the archive bytes and restoration contract before publish.
        restore_backup_bundle(temporary, stage / "verification")
        with temporary.open("rb+") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    return BackupResult(destination, destination.stat().st_size, "ok")


def _bundle_member(name: str) -> str:
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ValueError("Chemin d'archive invalide.")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in ("", ".", "..") for part in name.split("/")):
        raise ValueError("Chemin d'archive hors profil.")
    if path.parts[0] not in ("data", "media", "backgrounds"):
        raise ValueError("Dossier d'archive non autorisé.")
    # Windows aliases/device names are not portable filenames.
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)),
                *(f"lpt{i}" for i in range(10))}
    if any(part.endswith((" ", ".")) or part.split(".")[0].casefold() in reserved
           for part in path.parts):
        raise ValueError("Nom de fichier non portable.")
    return name


def restore_backup_bundle(archive: Path, destination_profile: Path, *,
                          max_bytes: int = 50 * 1024**3,
                          max_files: int = 100000) -> Path:
    """Verify then atomically publish a new profile; never overwrite/merge.

    The caller must close the application before selecting this restored
    profile. SHA-256 detects damage, not authenticity of an untrusted archive.
    Extraction is confined, streamed and bounded; no archive code is executed.
    """
    target = Path(destination_profile).resolve()
    if target.exists():
        raise ValueError("Restauration uniquement vers un dossier inexistant.")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive) as bundle, tempfile.TemporaryDirectory(
                prefix=".restore-", dir=target.parent) as work:
            infos = bundle.infolist()
            names = [info.filename for info in infos]
            if len(infos) > max_files or len({n.casefold() for n in names}) != len(names):
                raise ValueError("Archive trop grande ou noms dupliqués.")
            if sum(info.file_size for info in infos) > max_bytes:
                raise ValueError("Volume décompressé excessif.")
            if "manifest.json" not in names or bundle.getinfo("manifest.json").file_size > 16 * 1024**2:
                raise ValueError("Manifeste absent ou trop grand.")
            manifest = json.loads(bundle.read("manifest.json"))
            if manifest.get("format") != "project-on-backup" or manifest.get("format_version") != 1:
                raise ValueError("Format de sauvegarde non pris en charge.")
            entries = manifest["files"]
            if not isinstance(entries, dict) or set(names) != set(entries) | {"manifest.json"}:
                raise ValueError("Inventaire du manifeste incohérent.")
            if manifest["database"] != "data/project_on.db" or manifest["database"] not in entries:
                raise ValueError("Base absente du manifeste.")
            if manifest.get("settings") not in (None, "data/settings.json"):
                raise ValueError("Chemin de paramètres invalide.")
            stage = Path(work) / "profile"
            stage.mkdir()
            for name, metadata in entries.items():
                _bundle_member(name)
                if name.startswith("data/") and name not in ("data/project_on.db", "data/settings.json"):
                    raise ValueError("Fichier de données non autorisé.")
                info = bundle.getinfo(name)
                if info.is_dir() or ((info.external_attr >> 16) & 0o170000) == 0o120000:
                    raise ValueError("Liens et répertoires non autorisés.")
                if info.file_size != metadata["size"]:
                    raise ValueError("Taille différente du manifeste.")
                output = stage / name
                output.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(info) as src, output.open("xb") as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
                if _digest(output) != metadata["sha256"]:
                    raise ValueError("Empreinte différente du manifeste.")
            db = stage / manifest["database"]
            if not verify_database(db)[0]:
                raise ValueError("Base restaurée invalide.")
            mapping = manifest.get("path_map", {})
            if not isinstance(mapping, dict) or any(not isinstance(k, str) or v not in entries
                    or not v.startswith(("media/", "backgrounds/")) for k, v in mapping.items()):
                raise ValueError("Références de fichiers invalides.")
            relocated = {old: str(target / member) for old, member in mapping.items()}
            with closing(sqlite3.connect(db)) as conn:
                for table, column in _reference_fields(conn):
                    for old, new in relocated.items():
                        conn.execute(f'UPDATE "{table}" SET "{column}"=? WHERE "{column}"=?', (new, old))
                conn.commit()
                if conn.execute("PRAGMA foreign_key_check").fetchone():
                    raise ValueError("Relations de base invalides.")
            if manifest.get("settings"):
                path = stage / manifest["settings"]
                payload = _safe_settings(json.loads(path.read_text(encoding="utf-8")))
                path.write_text(json.dumps(_rewrite_settings(payload, relocated), ensure_ascii=False, indent=2), encoding="utf-8")
            if not verify_database(db)[0]:
                raise ValueError("Base invalide après relocalisation.")
            # Windows rename refuses an existing target, including a racing one.
            if target.exists():
                raise ValueError("La destination a été créée pendant la restauration.")
            os.rename(stage, target)
        return target
    except (zipfile.BadZipFile, KeyError, TypeError, json.JSONDecodeError, sqlite3.Error) as error:
        raise ValueError(f"Sauvegarde invalide : {error}") from error
