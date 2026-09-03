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
import shutil
import subprocess
from pathlib import Path

from app.utils.app_paths import media_dir
from app.utils.media_utils import is_powerpoint_file

_PPT_EXPORT_WIDTH = 1920
_PPT_EXPORT_HEIGHT = 1080
_COMPLETE_MARKER = "_complete.json"
_SOFFICE_CANDIDATES = [
    Path("C:/Program Files/LibreOffice/program/soffice.exe"),
    Path("C:/Program Files (x86)/LibreOffice/program/soffice.exe"),
]


class OfficeRenderError(RuntimeError):
    """Aucun moteur de rendu disponible (PowerPoint ni LibreOffice)."""


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
            for index in range(1, int(presentation.Slides.Count) + 1):
                png = out_dir / f"slide-{index:02d}.png"
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
            for index, page in enumerate(document, start=1):
                png = out_dir / f"slide-{index:02d}.png"
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
    (out_dir / _COMPLETE_MARKER).write_text(
        json.dumps(payload), encoding="utf-8"
    )


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
        return sorted(out_dir.glob("slide-*.png"))
    (out_dir / _COMPLETE_MARKER).unlink(missing_ok=True)

    errors: list[str] = []
    try:
        exported = _render_with_powerpoint(source, out_dir)
        _write_complete_marker(out_dir, source, len(exported))
        return exported
    except OfficeRenderError:
        raise
    except ImportError as exc:
        errors.append(f"PowerPoint/COM : {exc}")
    except Exception as exc:
        errors.append(f"PowerPoint/COM : {exc}")

    try:
        exported = _render_with_libreoffice(source, out_dir)
        _write_complete_marker(out_dir, source, len(exported))
        return exported
    except OfficeRenderError as exc:
        errors.append(str(exc))
    except Exception as exc:
        errors.append(f"LibreOffice : {exc}")

    raise OfficeRenderError(
        "Aucun moteur de rendu disponible. Installez Microsoft PowerPoint "
        "ou LibreOffice pour importer une présentation. Détails : "
        + " | ".join(errors)
    )
