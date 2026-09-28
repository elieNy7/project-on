"""Détourage de photo (photo du pasteur sans arrière-plan).

Deux méthodes, toutes deux hors-ligne une fois prêtes :

- **Détourage IA** : modèle de segmentation « silueta » (U²-Net réduit à
  44 Mo, projet rembg, licence MIT) exécuté par ONNX Runtime. Il isole la
  personne quel que soit le décor. Le modèle est fourni avec l'installeur
  (``models/silueta.onnx``) ou téléchargé une fois depuis GitHub, empreinte
  SHA-256 vérifiée ;
- **Fond uni** : pour une photo prise devant un mur ou un drap de couleur
  unie, sans modèle ni Internet — la couleur des bords est effacée depuis
  l'extérieur, avec un contour adouci.

Le résultat est un PNG transparent recadré au plus près de la personne.
"""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path
from typing import Callable

MODEL_NAME = "silueta.onnx"
MODEL_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/silueta.onnx"
MODEL_SHA256 = "75da6c8d2f8096ec743d071951be73b4a8bc7b3e51d9a6625d63644f90ffeedb"
MODEL_SIZE = 44_173_029

_SESSION = None


def bundled_model_path() -> Path:
    from app.utils.app_paths import resource_root

    return resource_root() / "models" / MODEL_NAME


def user_model_path() -> Path:
    from app.utils.app_paths import data_dir

    return data_dir() / "models" / MODEL_NAME


def model_path() -> Path | None:
    """Modèle disponible (fourni, puis téléchargé), sinon None."""
    for path in (bundled_model_path(), user_model_path()):
        if path.is_file() and path.stat().st_size == MODEL_SIZE:
            return path
    return None


def ai_available() -> bool:
    try:
        import onnxruntime  # noqa: F401
    except Exception:
        return False
    return True


def download_model(progress: Callable[[int, int], None] | None = None,
                   timeout: float = 60.0) -> Path:
    """Télécharge le modèle une fois (≈ 44 Mo) et vérifie son empreinte."""
    target = user_model_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".part")
    digest = hashlib.sha256()
    received = 0
    request = urllib.request.Request(MODEL_URL, headers={"User-Agent": "Project-On"})
    with urllib.request.urlopen(request, timeout=timeout) as response, partial.open("wb") as out:
        total = int(response.headers.get("Content-Length") or MODEL_SIZE)
        while True:
            block = response.read(512 * 1024)
            if not block:
                break
            out.write(block)
            digest.update(block)
            received += len(block)
            if progress is not None:
                progress(received, total)
    if digest.hexdigest() != MODEL_SHA256:
        partial.unlink(missing_ok=True)
        raise ValueError("Modèle de détourage corrompu (empreinte différente).")
    partial.replace(target)
    return target


def _session(path: Path):
    global _SESSION
    if _SESSION is None or _SESSION[0] != path:
        import onnxruntime as ort

        _SESSION = (path, ort.InferenceSession(str(path), providers=["CPUExecutionProvider"]))
    return _SESSION[1]


def ai_mask(image, path: Path | None = None):
    """Masque de la personne (L, taille de l'image) prédit par le modèle."""
    import numpy as np
    from PIL import Image

    path = path or model_path()
    if path is None:
        raise FileNotFoundError("Modèle de détourage absent.")
    session = _session(path)
    rgb = image.convert("RGB")
    small = np.asarray(rgb.resize((320, 320), Image.LANCZOS)).astype(np.float32)
    small = small / max(1.0, float(small.max()))
    small = (small - (0.485, 0.456, 0.406)) / (0.229, 0.224, 0.225)
    tensor = small.transpose(2, 0, 1)[None].astype(np.float32)
    prediction = session.run(None, {session.get_inputs()[0].name: tensor})[0][0, 0]
    low, high = float(prediction.min()), float(prediction.max())
    prediction = (prediction - low) / max(1e-8, high - low)
    # Contraste doux : fond franchement transparent, contour gardé net.
    prediction = np.clip((prediction - 0.08) / 0.84, 0.0, 1.0)
    mask = Image.fromarray((prediction * 255).astype("uint8"), mode="L")
    return mask.resize(rgb.size, Image.LANCZOS)


def keep_main_subject(mask, grid: int = 160, keep_ratio: float = 0.15):
    """Retire les îlots isolés (restes de décor) : garde la personne.

    Les zones opaques sont regroupées sur une grille réduite ; les zones
    plus petites que ``keep_ratio`` × la plus grande sont effacées (une main
    ou une épaule détachées de la silhouette restent).
    """
    from collections import deque

    from PIL import Image

    small = mask.resize((grid, max(1, int(grid * mask.height / mask.width))), Image.BILINEAR)
    width, height = small.size
    pixels = small.load()
    labels = [[0] * width for _ in range(height)]
    sizes = {0: 0}
    current = 0
    for y in range(height):
        for x in range(width):
            if pixels[x, y] < 96 or labels[y][x]:
                continue
            current += 1
            queue = deque([(x, y)])
            labels[y][x] = current
            count = 0
            while queue:
                cx, cy = queue.popleft()
                count += 1
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < width and 0 <= ny < height and not labels[ny][nx] \
                            and pixels[nx, ny] >= 96:
                        labels[ny][nx] = current
                        queue.append((nx, ny))
            sizes[current] = count
    if current == 0:
        return mask
    largest = max(sizes.values())
    keep = {label for label, size in sizes.items() if label and size >= largest * keep_ratio}
    keep_small = Image.new("L", (width, height), 0)
    keep_pixels = keep_small.load()
    for y in range(height):
        row = labels[y]
        for x in range(width):
            if row[x] in keep:
                keep_pixels[x, y] = 255
    # Masque agrandi et légèrement élargi pour ne pas rogner les contours.
    from PIL import ImageChops, ImageFilter

    keep_full = keep_small.filter(ImageFilter.MaxFilter(3)).resize(mask.size, Image.BILINEAR)
    return ImageChops.multiply(mask, keep_full.point(lambda v: 255 if v > 20 else 0))


def plain_background_mask(image, tolerance: int = 40):
    """Masque pour une photo sur fond uni : efface la couleur des bords.

    Remplissage depuis les quatre bords des pixels proches de la couleur
    de fond (écart ≤ ``tolerance``), puis léger adoucissement du contour.
    """
    import numpy as np
    from PIL import Image, ImageFilter

    rgb = np.asarray(image.convert("RGB")).astype(np.int32)
    height, width, _ = rgb.shape
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    background = np.median(border, axis=0)
    distance = np.sqrt(((rgb - background) ** 2).sum(axis=2))
    similar = distance <= max(1, int(tolerance))

    # Remplissage par diffusion depuis les bords (pas de trou dans la personne).
    reached = np.zeros_like(similar)
    reached[0, :] = similar[0, :]
    reached[-1, :] = similar[-1, :]
    reached[:, 0] |= similar[:, 0]
    reached[:, -1] |= similar[:, -1]
    for _ in range(max(width, height)):
        grown = reached.copy()
        grown[1:, :] |= reached[:-1, :]
        grown[:-1, :] |= reached[1:, :]
        grown[:, 1:] |= reached[:, :-1]
        grown[:, :-1] |= reached[:, 1:]
        grown &= similar
        if (grown == reached).all():
            break
        reached = grown
    mask = Image.fromarray(np.where(reached, 0, 255).astype("uint8"), mode="L")
    return mask.filter(ImageFilter.GaussianBlur(radius=max(1.0, min(width, height) / 400)))


def apply_mask(image, mask, margin: float = 0.03):
    """Image RGBA transparente, recadrée au plus près de la personne."""
    rgba = image.convert("RGBA")
    rgba.putalpha(mask)
    box = mask.point(lambda v: 255 if v > 24 else 0).getbbox()
    if box is None:
        return rgba
    pad = int(max(rgba.width, rgba.height) * margin)
    left, top, right, bottom = box
    return rgba.crop((
        max(0, left - pad), max(0, top - pad),
        min(rgba.width, right + pad), min(rgba.height, bottom + pad),
    ))


def remove_background(image, method: str = "ai", tolerance: int = 40):
    """Photo détourée (RGBA). ``method`` : "ai" ou "plain"."""
    if method == "ai":
        mask = keep_main_subject(ai_mask(image))
    else:
        mask = plain_background_mask(image, tolerance)
    return apply_mask(image, mask)
