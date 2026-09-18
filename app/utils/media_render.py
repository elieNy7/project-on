"""Composition plein cadre d'un média pour les sorties composées hors Qt.

La projection locale, l'aperçu et la page OBS dessinent le média dans leur
propre moteur ; le mixeur HDMI et la sortie NDI, eux, composent leurs trames
en PIL. Ce module est leur source commune : un média est un **contenu** —
image entière centrée, proportions préservées, jamais rognée — posé sur une
copie floue et assombrie de la même image, sans aucune transparence (une
sortie à clé ou à canal alpha doit rester pleinement opaque sur le média).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageOps

__all__ = [
    "load_media_image",
    "compose_media_frame",
    "normalize_media_options",
]

# Côté long de la miniature floutée : le flou gomme les détails, inutile de
# travailler à pleine résolution (même approche que le moteur Qt).
_BACKDROP_EDGE = 320
# Rayon de flou de référence sur un écran 1080p, ramené à la miniature.
_BACKDROP_BLUR_1080 = 40
_CACHE_LIMIT = 6

_cache: dict[tuple, Image.Image] = {}


def normalize_media_options(
    cfg: dict[str, Any] | None,
) -> tuple[str, str, float]:
    """(cadrage, habillage, assombrissement) bornés — mêmes défauts que Qt."""
    cfg = cfg or {}
    fit = "cover" if str(cfg.get("media_fit") or "") == "cover" else "contain"
    backdrop = str(cfg.get("media_backdrop") or "blur")
    if backdrop not in ("blur", "black", "color"):
        backdrop = "blur"
    try:
        dim = float(cfg.get("media_backdrop_dim", 0.45))
    except (TypeError, ValueError):
        dim = 0.45
    return fit, backdrop, max(0.0, min(0.9, dim))


def load_media_image(path: str | Path) -> Image.Image | None:
    """Charge l'image d'un média (orientation EXIF comprise), avec cache.

    Renvoie ``None`` si le fichier est absent ou illisible : les sorties
    gardent alors leur fond habituel au lieu d'échouer.
    """
    target = Path(str(path))
    try:
        stamp = target.stat().st_mtime
    except OSError:
        return None
    key = ("image", str(target), round(float(stamp), 3))
    cached = _cache.get(key)
    if cached is not None:
        return cached
    try:
        with Image.open(target) as raw:
            image = ImageOps.exif_transpose(raw)
            image = image.convert("RGB")
            image.load()
    except Exception:
        return None
    _remember(key, image)
    return image


def compose_media_frame(
    path: str | Path,
    width: int,
    height: int,
    cfg: dict[str, Any] | None = None,
) -> Image.Image | None:
    """Trame RVB plein cadre : image entière nette sur fond flou assombri.

    ``None`` si le média ne peut pas être lu (l'appelant conserve alors son
    rendu habituel : couleur de clé pour le mixeur, transparence pour le NDI).
    """
    source = load_media_image(path)
    if source is None:
        return None
    width = max(1, int(width))
    height = max(1, int(height))
    fit, backdrop, dim = normalize_media_options(cfg)

    try:
        stamp = Path(str(path)).stat().st_mtime
    except OSError:
        stamp = 0.0
    key = ("frame", str(path), round(float(stamp), 3), width, height, fit, backdrop, dim)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    if backdrop == "blur":
        base = _blurred_backdrop(source, width, height, dim)
    else:
        tone = (0, 0, 0) if backdrop == "black" else _theme_tone(cfg)
        base = Image.new("RGB", (width, height), tone)

    if fit == "cover":
        picture = ImageOps.fit(source, (width, height), Image.LANCZOS)
    else:
        picture = ImageOps.contain(source, (width, height), Image.LANCZOS)
    frame = base.copy()
    frame.paste(
        picture,
        ((width - picture.width) // 2, (height - picture.height) // 2),
    )
    _remember(key, frame)
    return frame


def _blurred_backdrop(
    source: Image.Image, width: int, height: int, dim: float
) -> Image.Image:
    """Copie « cover » de l'image, floutée puis assombrie, à la taille voulue."""
    small = ImageOps.fit(source, (_BACKDROP_EDGE, _BACKDROP_EDGE), Image.LANCZOS)
    radius = max(1.0, _BACKDROP_BLUR_1080 * small.width / 1920.0)
    small = small.filter(ImageFilter.GaussianBlur(radius))
    backdrop = small.resize((width, height), Image.LANCZOS)
    if dim > 0:
        backdrop = Image.blend(backdrop, Image.new("RGB", backdrop.size, (0, 0, 0)), dim)
    return backdrop


def _theme_tone(cfg: dict[str, Any] | None) -> tuple[int, int, int]:
    """Couleur de fond du thème, lue dans la configuration de style."""
    raw = str((cfg or {}).get("bg_color") or "#000000").strip()
    if raw.startswith("#") and len(raw) in (7, 9):
        try:
            return (
                int(raw[1:3], 16),
                int(raw[3:5], 16),
                int(raw[5:7], 16),
            )
        except ValueError:
            return (0, 0, 0)
    if raw.lower().startswith("rgb"):
        numbers = [p for p in raw.replace(" ", "").partition("(")[2].rstrip(")").split(",") if p]
        if len(numbers) >= 3:
            try:
                return tuple(min(255, max(0, int(float(n)))) for n in numbers[:3])  # type: ignore[return-value]
            except ValueError:
                return (0, 0, 0)
    return (0, 0, 0)


def _remember(key: tuple, image: Image.Image) -> None:
    """Cache borné : quelques clichés, jamais une croissance illimitée."""
    _cache[key] = image
    while len(_cache) > _CACHE_LIMIT:
        _cache.pop(next(iter(_cache)))
