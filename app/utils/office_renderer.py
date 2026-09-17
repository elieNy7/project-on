"""Rendu fidèle des présentations PowerPoint en images projetables.

Deux moteurs, détectés automatiquement :
1. Microsoft PowerPoint (via COM/pywin32) — fidélité 100 % ;
2. LibreOffice headless — PPTX→PDF puis PDF→PNG via pymupdf.

Les images sont mises en cache dans ``media_dir()/powerpoint/<nom>-<hash>/`` :
si le cache est complet, aucun moteur n'est sollicité (rendu instantané).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from app.utils.app_paths import media_dir
from app.utils.media_utils import is_powerpoint_file

_PPT_EXPORT_WIDTH = 1920
_PPT_EXPORT_HEIGHT = 1080
_COMPLETE_MARKER = "_complete.json"
_LOCK_SUFFIX = ".render.lock"
_MAX_CACHE_SLIDES = 1000
_SOFFICE_CANDIDATES = [
    Path("C:/Program Files/LibreOffice/program/soffice.exe"),
    Path("C:/Program Files (x86)/LibreOffice/program/soffice.exe"),
]

_SLIDE_NAME_RE = re.compile(r"^slide-(\d+)\.png$")


class OfficeRenderError(RuntimeError):
    """Aucun moteur de rendu disponible (PowerPoint ni LibreOffice)."""


def _slide_sort_key(path: Path) -> tuple[int, int]:
    """Tri numérique des noms de cache : slide-2 < slide-10 (au-delà de 99).

    Un tri lexicographique placerait slide-10 avant slide-2 et désordonnerait
    la projection dès que la présentation dépasse 99 slides.
    """
    match = _SLIDE_NAME_RE.match(path.name)
    if match:
        return (int(match.group(1)), 0)
    return (10**9, hash(path.name))


def _slide_filename(index: int) -> str:
    """Nom de cache numéroté sur 4 chiffres (tri numérique jusqu'à 9999)."""
    return f"slide-{index:04d}.png"


def _cached_slide_paths(out_dir: Path) -> list[Path]:
    return sorted(out_dir.glob("slide-*.png"), key=_slide_sort_key)


class _FileLock:
    """Verrou par présentation (création exclusive atomique, PID pour diagnostic).

    Protège le cache ``powerpoint/<nom>-<hash>`` contre deux rendus concurrents
    (double-clic impatient, playlist + activation simultanées) qui produiraient
    un cache mélangé.  Un verrou stale (> 30 min) est repris.
    """

    _STALE_SECONDS = 1800

    def __init__(self, path: Path) -> None:
        self._path = path
        self._acquired = False

    def __enter__(self) -> "_FileLock":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + 120.0
        while True:
            try:
                # O_CREAT|O_EXCL : création exclusive, atomique sur Windows.
                fd = os.open(
                    str(self._path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                os.write(fd, str(os.getpid()).encode("utf-8"))
                os.close(fd)
                self._acquired = True
                return self
            except FileExistsError:
                try:
                    age = time.time() - self._path.stat().st_mtime
                    if age > self._STALE_SECONDS:
                        self._path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    # Rendu quand même : le marqueur d'achèvement reste l'arbitre
                    # de validité du cache, donc aucun cache corrompu possible.
                    return self
                time.sleep(0.25)

    def __exit__(self, *_exc: object) -> None:
        if self._acquired:
            self._path.unlink(missing_ok=True)
            self._acquired = False


def pptx_slides_dir(pptx_path: str | Path) -> Path:
    """Dossier de cache déterministe pour les slides rendues d'un .pptx."""
    abs_path = Path(str(pptx_path)).resolve()
    key = hashlib.sha256(str(abs_path).lower().encode("utf-8")).hexdigest()[:12]
    d = media_dir() / "powerpoint" / f"{abs_path.stem}-{key}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _find_soffice() -> Path | None:
    which = shutil.which("soffice")
    if which:
        return Path(which)
    for candidate in _SOFFICE_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def _render_with_powerpoint(pptx_path: Path, out_dir: Path) -> list[Path]:
    """Export PNG par slide via PowerPoint COM (fidélité maximale)."""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    try:
        try:
            app = win32com.client.GetActiveObject("PowerPoint.Application")
            launched_here = False
        except Exception:
            app = win32com.client.Dispatch("PowerPoint.Application")
            launched_here = True

        presentation = app.Presentations.Open(
            str(pptx_path), ReadOnly=True, Untitled=False, WithWindow=False
        )
        exported: list[Path] = []
        try:
            slide_count = int(presentation.Slides.Count)
            if slide_count > _MAX_CACHE_SLIDES:
                raise OfficeRenderError(
                    f"Présentation trop grande : {slide_count} slides "
                    f"(maximum {_MAX_CACHE_SLIDES})."
                )
            for index in range(1, slide_count + 1):
                png = out_dir / _slide_filename(index)
                presentation.Slides(index).Export(
                    str(png), "PNG", _PPT_EXPORT_WIDTH, _PPT_EXPORT_HEIGHT
                )
                exported.append(png)
        finally:
            presentation.Close()
            if launched_here:
                app.Quit()
        return exported
    finally:
        pythoncom.CoUninitialize()


def _render_with_libreoffice(pptx_path: Path, out_dir: Path) -> list[Path]:
    """PPTX → PDF via LibreOffice headless, puis PNG par page via pymupdf."""
    soffice = _find_soffice()
    if soffice is None:
        raise OfficeRenderError("LibreOffice introuvable")
    tmp_dir = out_dir / "_pdf"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [
                str(soffice),
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(tmp_dir),
                str(pptx_path),
            ],
            capture_output=True,
            timeout=300,
        )
        pdfs = list(tmp_dir.glob("*.pdf"))
        if result.returncode != 0 or not pdfs:
            raise OfficeRenderError(
                f"Conversion LibreOffice échouée : {result.stderr.decode(errors='ignore')[:200]}"
            )
        import fitz

        exported: list[Path] = []
        document = fitz.open(str(pdfs[0]))
        try:
            if document.page_count > _MAX_CACHE_SLIDES:
                raise OfficeRenderError(
                    f"Présentation trop grande : {document.page_count} pages "
                    f"(maximum {_MAX_CACHE_SLIDES})."
                )
            for index, page in enumerate(document, start=1):
                png = out_dir / _slide_filename(index)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                pix.save(str(png))
                exported.append(png)
        finally:
            document.close()
        return exported
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _source_fingerprint(source: Path) -> dict[str, int]:
    st = source.stat()
    return {"size": int(st.st_size), "mtime": int(st.st_mtime)}


def _write_complete_marker(out_dir: Path, source: Path, slide_count: int) -> None:
    payload = _source_fingerprint(source)
    payload["slides"] = slide_count
    # Écriture atomique : le marqueur n'apparaît jamais à moitié écrit.
    marker = out_dir / _COMPLETE_MARKER
    fd, tmp_name = tempfile.mkstemp(dir=str(out_dir), suffix=".marker.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, marker)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _cache_is_complete(out_dir: Path, source: Path) -> bool:
    """True when a full render of *this exact source file* is cached.

    A marker written only after every slide was exported distinguishes a
    complete render from one interrupted mid-way, and its fingerprint
    invalidates the cache when the .pptx is modified.
    """
    marker = out_dir / _COMPLETE_MARKER
    if not marker.is_file():
        return False
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
        expected = _source_fingerprint(source)
        if (
            int(payload.get("size", -1)) != expected["size"]
            or int(payload.get("mtime", -1)) != expected["mtime"]
        ):
            return False
        cached = list(out_dir.glob("slide-*.png"))
        return len(cached) == int(payload.get("slides", -1))
    except (ValueError, OSError):
        return False


def render_pptx_to_images(pptx_path: str | Path, force: bool = False) -> list[Path]:
    """Rend chaque slide du .pptx en PNG (cache réutilisé si complet).

    Le rendu s'effectue dans un dossier d'attente (``_staging``) puis est
    publié en une opération : le cache public ne contient jamais un mélange
    d'anciens et de nouveaux slides, et une interruption ne laisse aucun
    cache incomplet exploitable.  Un verrou par présentation empêche deux
    rendus concurrents du même fichier.

    Lève ``OfficeRenderError`` si ni PowerPoint ni LibreOffice ne sont
    disponibles. Le fichier doit être un .pptx/.ppsx.
    """
    source = Path(str(pptx_path))
    if not is_powerpoint_file(source):
        raise OfficeRenderError(f"Fichier non pris en charge : {source.name}")
    if not source.is_file():
        raise OfficeRenderError(f"Fichier introuvable : {source.name}")

    out_dir = pptx_slides_dir(source)
    if not force and _cache_is_complete(out_dir, source):
        return _cached_slide_paths(out_dir)

    lock = _FileLock(out_dir / f"{out_dir.name}{_LOCK_SUFFIX}")
    with lock:
        # Un autre rendu a peut-être achevé le cache pendant l'attente.
        if not force and _cache_is_complete(out_dir, source):
            return _cached_slide_paths(out_dir)

        # Purger tout cache obsolète avant le rendu : sans le marqueur,
        # aucun ancien slide ne doit rester visible comme résultat.
        (out_dir / _COMPLETE_MARKER).unlink(missing_ok=True)
        for stale in out_dir.glob("slide-*.png"):
            stale.unlink(missing_ok=True)

        staging = Path(
            tempfile.mkdtemp(prefix=f".{out_dir.name}-staging-", dir=str(out_dir))
        )
        try:
            errors: list[str] = []
            try:
                _render_with_powerpoint(source, staging)
                engine = "powerpoint"
            except ImportError as exc:
                engine = None
                errors.append(f"PowerPoint/COM : {exc}")
            except Exception as exc:
                if "trop grande" in str(exc):
                    raise
                engine = None
                errors.append(f"PowerPoint/COM : {exc}")

            if engine is None:
                try:
                    _render_with_libreoffice(source, staging)
                except OfficeRenderError as exc:
                    if "trop grande" in str(exc):
                        raise
                    errors.append(str(exc))
                except Exception as exc:
                    errors.append(f"LibreOffice : {exc}")
                else:
                    engine = "libreoffice"

            if engine is None:
                raise OfficeRenderError(
                    "Aucun moteur de rendu disponible. Installez Microsoft PowerPoint "
                    "ou LibreOffice pour importer une présentation. Détails : "
                    + " | ".join(errors)
                )

            # Publication : tous les slides rendus existent dans le staging,
            # on les déplace vers le cache puis on pose le marqueur.
            slide_files = _cached_slide_paths(staging)
            if len(slide_files) > _MAX_CACHE_SLIDES:
                raise OfficeRenderError(
                    f"Présentation trop grande : {len(slide_files)} slides "
                    f"(maximum {_MAX_CACHE_SLIDES})."
                )
            _write_complete_marker(staging, source, len(slide_files))
            for png in slide_files:
                os.replace(png, out_dir / png.name)
            os.replace(staging / _COMPLETE_MARKER, out_dir / _COMPLETE_MARKER)
            return [out_dir / png.name for png in slide_files]
        finally:
            shutil.rmtree(staging, ignore_errors=True)
