from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sqlite3
import sys
import unicodedata
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FOLDER = ROOT / "CANTIQUE D'ADORATION"
DEFAULT_DB = ROOT / "data" / "project_on.db"
DEFAULT_CACHE = ROOT / "build" / "cantique_adoration_pptx_cache"

SUPPORTED_EXTENSIONS = {".pptx", ".ppsx", ".pptm", ".potx", ".ppt", ".pps", ".ewsx"}
POWERPOINT_EXTENSIONS = {".pptx", ".ppsx", ".pptm", ".potx", ".ppt", ".pps"}
NATIVE_OPENXML_EXTENSIONS = {".pptx", ".ppsx", ".pptm", ".potx"}
LEGACY_POWERPOINT_EXTENSIONS = {".ppt", ".pps"}


if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.connection import Database, DatabaseConfig
from app.database.dao_hymns import HymnsDao
from app.utils.pptx_parser import parse_pptx_as_hymn, parse_slides_as_hymn
from app.utils.text_utils import clean_text


@dataclass
class ImportStats:
    scanned: int = 0
    parsed: int = 0
    imported: int = 0
    skipped_existing: int = 0
    skipped_duplicate: int = 0
    skipped_unsupported: int = 0
    skipped_legacy_unavailable: int = 0
    failed: int = 0


def normalize_key(value: object) -> str:
    text = clean_text(value)
    text = text.replace("’", "'").replace("`", "'")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def safe_cache_name(path: Path) -> str:
    stem = normalize_key(path.stem).replace(" ", "-") or "presentation"
    digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:10]
    return f"{stem}-{digest}.pptx"


def iter_folder_files(folder: Path, recursive: bool = False) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    files = [
        path
        for path in folder.glob(pattern)
        if path.is_file() and not path.name.startswith("~$")
    ]
    return sorted(files, key=lambda item: normalize_key(item.stem))


def load_existing_title_keys(db: Database) -> set[str]:
    with db.connect() as conn:
        rows = conn.execute("SELECT title FROM hymn").fetchall()
    return {normalize_key(row["title"]) for row in rows if row["title"]}


def try_convert_legacy_powerpoint(path: Path, cache_dir: Path) -> Path | None:
    """Convert .ppt/.pps to .pptx with PowerPoint COM when available."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    output = cache_dir / safe_cache_name(path)
    if output.exists() and output.stat().st_mtime >= path.stat().st_mtime:
        return output

    if not legacy_conversion_available():
        return None

    import win32com.client  # type: ignore

    powerpoint = None
    presentation = None
    try:
        powerpoint = win32com.client.DispatchEx("PowerPoint.Application")
        powerpoint.Visible = 1
        presentation = powerpoint.Presentations.Open(
            str(path.resolve()),
            WithWindow=False,
            ReadOnly=True,
            Untitled=False,
        )
        # 24 = ppSaveAsOpenXMLPresentation
        presentation.SaveAs(str(output.resolve()), 24)
        return output if output.exists() else None
    except Exception:
        return None
    finally:
        try:
            if presentation is not None:
                presentation.Close()
        except Exception:
            pass
        try:
            if powerpoint is not None:
                powerpoint.Quit()
        except Exception:
            pass


@lru_cache(maxsize=1)
def legacy_conversion_available() -> bool:
    try:
        import win32com.client  # type: ignore  # noqa: F401

        return True
    except Exception:
        return False


def rtf_to_text(value: str) -> str:
    text = str(value or "")

    def decode_unicode(match: re.Match[str]) -> str:
        code = int(match.group(1))
        if code < 0:
            code += 65536
        return chr(code)

    text = re.sub(r"\\u(-?\d+)\??", decode_unicode, text)
    text = re.sub(r"\\'[0-9a-fA-F]{2}", "", text)
    text = re.sub(r"\{\\\*[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", "", text)
    text = re.sub(r"\\(?:par|line)\b", "\n", text)
    text = re.sub(r"\\[a-zA-Z]+\d* ?", "", text)
    text = text.replace("\\{", "{").replace("\\}", "}").replace("\\\\", "\\")
    text = text.replace("{", "").replace("}", "")
    lines = [clean_text(line) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def parse_ewsx_as_hymn(path: Path) -> dict[str, Any] | None:
    try:
        with zipfile.ZipFile(path, "r") as package:
            if "main.db" not in package.namelist():
                return None
            db_bytes = package.read("main.db")
    except Exception:
        return None

    temp_db: Path | None = None
    try:
        with tempfile_named_sqlite(db_bytes) as temp_db:
            conn = sqlite3.connect(temp_db)
            conn.row_factory = sqlite3.Row
            try:
                presentation = conn.execute(
                    """
                    SELECT rowid, title
                    FROM presentation
                    WHERE presentation_type NOT IN (11, 13)
                    ORDER BY order_index, rowid
                    LIMIT 1
                    """
                ).fetchone()
                if presentation is None:
                    return None

                title = clean_text(presentation["title"] or path.stem)
                rows = conn.execute(
                    """
                    SELECT s.order_index, rt.rtf
                    FROM slide s
                    JOIN element e ON e.slide_id = s.rowid
                    JOIN resource_text rt
                      ON rt.resource_id = e.foreground_resource_id
                      OR rt.resource_id = e.background_resource_id
                    WHERE s.presentation_id = ?
                    ORDER BY s.order_index, e.order_index
                    """,
                    (presentation["rowid"],),
                ).fetchall()
            finally:
                conn.close()
    except Exception:
        return None

    grouped: dict[int, list[str]] = {}
    for row in rows:
        text = rtf_to_text(row["rtf"])
        if text:
            grouped.setdefault(int(row["order_index"] or 0), []).append(text)

    slides = ["\n".join(parts).strip() for _, parts in sorted(grouped.items())]
    slides = [slide for slide in slides if slide]
    hymn = parse_slides_as_hymn(slides, title or path.stem)
    if hymn is None:
        return None
    hymn["title"] = title or clean_text(path.stem)
    hymn["source_path"] = str(path)
    return hymn


class tempfile_named_sqlite:
    def __init__(self, content: bytes) -> None:
        self._content = content
        self._path: Path | None = None

    def __enter__(self) -> Path:
        import tempfile

        handle = tempfile.NamedTemporaryFile(
            prefix="project_on_ewsx_", suffix=".db", delete=False
        )
        try:
            handle.write(self._content)
            self._path = Path(handle.name)
            return self._path
        finally:
            handle.close()

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._path is not None:
            try:
                self._path.unlink()
            except OSError:
                pass


def parse_cantique_file(path: Path, cache_dir: Path) -> dict[str, Any] | None:
    suffix = path.suffix.lower()
    if suffix == ".ewsx":
        return parse_ewsx_as_hymn(path)

    parse_path = path

    if suffix in LEGACY_POWERPOINT_EXTENSIONS:
        converted = try_convert_legacy_powerpoint(path, cache_dir)
        if converted is None:
            return None
        parse_path = converted

    hymn = parse_pptx_as_hymn(parse_path)
    if hymn is None:
        return None

    hymn["title"] = clean_text(path.stem)
    hymn["source_path"] = str(path)
    return hymn


def next_ad_sort_number(db: Database) -> int:
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT sort_key
            FROM hymn
            WHERE sort_key LIKE 'AD-FOLDER-%'
            ORDER BY sort_key DESC
            LIMIT 1
            """
        ).fetchone()

    if row is None or not row["sort_key"]:
        return 1

    match = re.search(r"AD-FOLDER-(\d+)", str(row["sort_key"]))
    return int(match.group(1)) + 1 if match else 1


def import_hymn(
    db: Database,
    dao: HymnsDao,
    hymn: dict[str, Any],
    sort_no: int,
    dry_run: bool,
) -> None:
    if dry_run:
        return

    hymn_id = dao.import_hymn(
        clean_text(hymn["title"]),
        [clean_text(stanza) for stanza in hymn["stanzas"] if clean_text(stanza)],
        number=f"AD-FOLDER-{sort_no:04d}",
        language="fr",
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE hymn SET sort_key = ? WHERE id = ?",
            (f"AD-FOLDER-{sort_no:04d}", hymn_id),
        )


def import_folder(
    folder: Path,
    db_path: Path,
    recursive: bool,
    dry_run: bool,
    cache_dir: Path,
    verbose: bool,
) -> ImportStats:
    if not folder.exists() or not folder.is_dir():
        raise SystemExit(f"Dossier introuvable: {folder}")
    if not db_path.exists():
        raise SystemExit(f"Base de donnees introuvable: {db_path}")

    db = Database(DatabaseConfig(db_path=db_path))
    dao = HymnsDao(db)
    existing_keys = load_existing_title_keys(db)
    seen_keys: set[str] = set()
    sort_no = next_ad_sort_number(db)
    stats = ImportStats()

    for path in iter_folder_files(folder, recursive=recursive):
        stats.scanned += 1
        suffix = path.suffix.lower()

        if suffix not in SUPPORTED_EXTENSIONS:
            stats.skipped_unsupported += 1
            if verbose:
                print(f"IGNORE {path.name} (format non pris en charge)")
            continue
        if suffix in LEGACY_POWERPOINT_EXTENSIONS and not legacy_conversion_available():
            stats.skipped_legacy_unavailable += 1
            if verbose:
                print(f"SKIP   {path.name} (.ppt: conversion PowerPoint indisponible)")
            continue

        hymn = parse_cantique_file(path, cache_dir)
        if hymn is None:
            stats.failed += 1
            if verbose:
                print(f"ECHEC  {path.name}")
            continue

        title = clean_text(hymn.get("title") or path.stem)
        stanzas = [clean_text(s) for s in hymn.get("stanzas", []) if clean_text(s)]
        if not title or not stanzas:
            stats.failed += 1
            if verbose:
                print(f"VIDE   {path.name}")
            continue

        stats.parsed += 1
        key = normalize_key(title)
        if key in existing_keys:
            stats.skipped_existing += 1
            if verbose:
                print(f"EXISTE {title}")
            continue
        if key in seen_keys:
            stats.skipped_duplicate += 1
            if verbose:
                print(f"DOUBLE {title}")
            continue

        hymn["title"] = title
        hymn["stanzas"] = stanzas
        import_hymn(db, dao, hymn, sort_no, dry_run=dry_run)
        seen_keys.add(key)
        existing_keys.add(key)
        stats.imported += 1
        if verbose:
            action = "DRY" if dry_run else "OK"
            print(f"{action:<6} {title} ({len(stanzas)} strophe(s))")
        sort_no += 1

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Scanne le dossier CANTIQUE D'ADORATION et importe les fichiers "
            "PowerPoint dans la table hymn sans creer de doublons."
        )
    )
    parser.add_argument("--folder", type=Path, default=DEFAULT_FOLDER)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Supprime le cache de conversion .ppt -> .pptx avant le scan.",
    )
    args = parser.parse_args()

    folder = args.folder.resolve()
    db_path = args.db.resolve()
    cache_dir = args.cache_dir.resolve()

    if args.clear_cache and cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    stats = import_folder(
        folder=folder,
        db_path=db_path,
        recursive=bool(args.recursive),
        dry_run=bool(args.dry_run),
        cache_dir=cache_dir,
        verbose=not bool(args.quiet),
    )

    mode = "Simulation" if args.dry_run else "Import"
    print(f"\n{mode} termine.")
    print(f"  Fichiers scannes: {stats.scanned}")
    print(f"  Cantiques lus: {stats.parsed}")
    print(f"  Importes: {stats.imported}")
    print(f"  Ignored deja en BD: {stats.skipped_existing}")
    print(f"  Ignored doublons du dossier: {stats.skipped_duplicate}")
    print(f"  Formats ignores: {stats.skipped_unsupported}")
    print(f"  Anciens .ppt non convertis: {stats.skipped_legacy_unavailable}")
    print(f"  Echecs/non lisibles: {stats.failed}")
    if stats.skipped_legacy_unavailable:
        print(
            "Note: les anciens .ppt exigent Microsoft PowerPoint + pywin32 "
            "pour etre convertis automatiquement."
        )


if __name__ == "__main__":
    main()
