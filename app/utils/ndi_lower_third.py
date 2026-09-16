from __future__ import annotations

import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.utils.app_paths import ndi_dir, resource_root
from app.utils.obs_overlay_render import (
    OverlayStyleConfig,
    _parse_rgba_tuple,
    render_obs_overlay,
)


@dataclass(frozen=True)
class NdiAvailability:
    runtime_found: bool
    python_bridge_found: bool
    numpy_found: bool
    usable: bool
    runtime_paths: tuple[str, ...] = ()
    message: str = ""


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(resolved)
    return out


def _runtime_search_roots() -> list[Path]:
    roots: list[Path] = []

    for getter in (ndi_dir, lambda: resource_root() / "ndi"):
        try:
            roots.append(getter())
        except Exception:
            pass

    for env_name in (
        "NDI_RUNTIME_DIR_V6",
        "NDI_RUNTIME_DIR_V5",
        "NDI_RUNTIME_DIR",
        "NDI_SDK_DIR",
    ):
        raw = os.environ.get(env_name)
        if raw:
            roots.append(Path(raw))

    if sys.platform == "win32":
        for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(env_name)
            if not base:
                continue
            base_path = Path(base)
            roots.extend(
                [
                    base_path / "NDI",
                    base_path / "NewTek" / "NDI",
                    base_path / "NDI" / "NDI 6 Runtime",
                    base_path / "NDI" / "NDI 5 Runtime",
                    base_path / "NDI" / "NDI 4 Runtime",
                ]
            )

    return _dedupe_paths(roots)


def _discover_ndi_runtime_dirs() -> list[Path]:
    dirs: list[Path] = []
    dll_names = (
        "Processing.NDI.Lib.x64.dll",
        "Processing.NDI.Lib.x86.dll",
        "Processing.NDI.Lib.dll",
    )

    for root in _runtime_search_roots():
        if not root.exists() or not root.is_dir():
            continue

        for child in (root, root / "bin", root / "runtime", root / "lib", root / "v5", root / "v6"):
            if child.exists() and child.is_dir():
                dirs.append(child)

        for dll_name in dll_names:
            try:
                hits = list(root.rglob(dll_name))
            except Exception:
                hits = []
            for hit in hits[:8]:
                dirs.append(hit.parent)

    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        path = Path(entry)
        try:
            if path.is_dir() and any((path / dll_name).exists() for dll_name in dll_names):
                dirs.append(path)
        except Exception:
            continue

    return _dedupe_paths(dirs)


def _activate_ndi_runtime_dirs(paths: list[Path]) -> None:
    for path in paths:
        try:
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(path))
            os.environ["PATH"] = str(path) + os.pathsep + os.environ.get("PATH", "")
        except Exception:
            pass


# Détection NDI : scan de dossiers + import coûteux → résultat partagé 10 s
# pour éviter de rescanner à chaque rafraîchissement d'interface.
_AVAILABILITY_TTL = 10.0
_availability_cache: tuple[float, NdiAvailability] | None = None


def check_ndi_availability() -> NdiAvailability:
    global _availability_cache
    now = time.monotonic()
    if (
        _availability_cache is not None
        and now - _availability_cache[0] < _AVAILABILITY_TTL
    ):
        return _availability_cache[1]

    runtime_dirs = _discover_ndi_runtime_dirs()
    _activate_ndi_runtime_dirs(runtime_dirs)

    np = None
    ndi = None
    try:
        import numpy as np  # type: ignore
    except Exception:
        np = None

    try:
        import NDIlib as ndi  # type: ignore
    except Exception:
        ndi = None

    runtime_found = bool(runtime_dirs)
    python_bridge_found = ndi is not None
    numpy_found = np is not None
    usable = python_bridge_found and numpy_found

    if usable:
        message = "NDI détecté et prêt."
    else:
        missing = []
        if not python_bridge_found:
            missing.append("NDIlib")
        if not numpy_found:
            missing.append("numpy")
        if runtime_found:
            message = "Runtime NDI détecté."
        else:
            message = "Runtime NDI non détecté sur ce système."
        if missing:
            message += " Dépendances Python manquantes : " + ", ".join(missing) + "."

    result = NdiAvailability(
        runtime_found=runtime_found,
        python_bridge_found=python_bridge_found,
        numpy_found=numpy_found,
        usable=usable,
        runtime_paths=tuple(str(p) for p in runtime_dirs),
        message=message,
    )
    _availability_cache = (now, result)
    return result


def _try_import_ndi():
    try:
        runtime_dirs = _discover_ndi_runtime_dirs()
        _activate_ndi_runtime_dirs(runtime_dirs)

        import NDIlib as ndi  # type: ignore
        import numpy as np  # type: ignore

        return np, ndi
    except Exception:
        return None, None


# La composition de la section texte vit dans obs_overlay_render
# (partagée avec la sortie HDMI mixeur) ; l'alias conserve le nom
# historique.
NdiLowerThirdConfig = OverlayStyleConfig


class NdiLowerThirdSender:
    def __init__(self, presentation_dir: Path, source_name: str) -> None:
        self._presentation_dir = presentation_dir
        self._source_name = str(source_name or "Project-On").strip() or "Project-On"

        self._slide_path = presentation_dir / "slide.json"
        self._cfg_path = presentation_dir / "obs-config.json"

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self._np = None
        self._ndi = None
        self._ndi_send = None
        self._video_frame = None

        self._last_slide_mtime: float = -1.0
        self._last_cfg_mtime: float = -1.0
        self._last_payload: dict[str, Any] | None = None
        self._last_cfg: dict[str, Any] | None = None

        self._width = 1920
        self._height = 1080

        # Bandeau défilant : ressources pré-rendues (ligne de texte, période)
        # partagées entre les frames ; seule la bande basse est recomposée.
        self._ticker_sig = None
        self._ticker_res: dict[str, Any] | None = None
        self._ticker_offset = 0.0
        self._ticker_last = 0.0

        # Diagnostic du dernier échec (démarrage ou thread d'envoi).
        self.last_error: str = ""

    @property
    def source_name(self) -> str:
        return self._source_name

    @property
    def is_alive(self) -> bool:
        """True tant que le thread d'envoi NDI tourne."""
        return self._thread is not None and self._thread.is_alive()

    @staticmethod
    def availability() -> NdiAvailability:
        return check_ndi_availability()

    def start(self) -> bool:
        if self.is_alive:
            return True  # déjà en cours

        self.last_error = ""
        np, ndi = _try_import_ndi()
        if np is None or ndi is None:
            self.last_error = (
                "Runtime ou pont Python NDI introuvable "
                "(NDIlib/numpy). Installez le NDI Runtime."
            )
            return False
        self._np = np
        self._ndi = ndi

        if not ndi.initialize():
            self.last_error = "NDI initialize() a échoué (runtime déjà chargé ?)."
            return False

        # ndi-python supports both `send_create()` and `send_create(SendCreate(...))`
        # depending on wrapper version.
        try:
            self._ndi_send = ndi.send_create(
                ndi.SendCreate(p_ndi_name=self._source_name)
            )
        except Exception:
            self._ndi_send = ndi.send_create()
        if self._ndi_send is None:
            self.last_error = "Création de la source NDI impossible."
            ndi.destroy()
            return False

        img = np.zeros((self._height, self._width, 4), dtype=np.uint8)
        video_frame = ndi.VideoFrameV2()
        video_frame.data = img
        video_frame.FourCC = ndi.FOURCC_VIDEO_TYPE_BGRA

        self._video_frame = video_frame
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

        if self._ndi is None:
            return
        try:
            if self._ndi_send is not None:
                self._ndi.send_destroy(self._ndi_send)
        finally:
            self._ndi_send = None
            self._video_frame = None
            try:
                self._ndi.destroy()
            except Exception:
                pass

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        try:
            if not path.exists() or not path.is_file():
                return None
            raw = path.read_text(encoding="utf-8")
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def _get_config(self) -> NdiLowerThirdConfig:
        """Style courant, lu de la charge utile OBS."""
        return OverlayStyleConfig.from_payload(self._last_cfg)

    def _render(self, slide: dict[str, Any] | None) -> Any:
        """Section texte façon OBS : composition PIL partagée, en BGRA."""
        assert self._np is not None

        img = render_obs_overlay(self._last_cfg, slide, self._width, self._height)
        if img is None:
            return self._np.zeros(
                (self._height, self._width, 4), dtype=self._np.uint8
            )
        rgba = self._np.array(img, dtype=self._np.uint8)
        bgra = rgba[:, :, [2, 1, 0, 3]].copy()
        return bgra

    # ── Bandeau défilant (même charge utile que la page OBS) ──────────

    def _ticker_config(self) -> dict[str, Any] | None:
        """Payload « ticker » de obs-config.json, sanitisé. None si inactif."""
        raw = self._last_cfg.get("ticker") if isinstance(self._last_cfg, dict) else None
        if not isinstance(raw, dict) or not raw.get("enabled"):
            return None
        texts = [
            str(t or "").strip()
            for t in (raw.get("texts") or [])
            if str(t or "").strip()
        ]
        if not texts:
            return None

        def _clamp(value, low, high, default):
            try:
                return max(low, min(high, int(float(value))))
            except Exception:
                return default

        return {
            "texts": texts,
            "speed": max(
                20.0, min(400.0, _clamp(raw.get("speed"), 20, 400, 90))
            ),
            "height": _clamp(raw.get("height"), 32, 220, 64),
            "font_size": _clamp(raw.get("font_size"), 14, 90, 30),
            "bg_color": str(raw.get("bg_color") or "rgba(5,10,22,0.82)"),
            "text_color": str(raw.get("text_color") or "rgba(255,255,255,0.95)"),
            "font_family": str(
                (self._last_cfg or {}).get("font_family") or "Poppins"
            ),
        }

    def _refresh_ticker_resources(self) -> None:
        """(Re)construit la ligne de texte pré-rendue si la config a changé."""
        cfg = self._ticker_config()
        sig = (
            tuple(
                (key, repr(value))
                for key, value in sorted(cfg.items())
                if key != "speed"
            )
            if cfg is not None
            else None
        )
        if sig == self._ticker_sig:
            # La vitesse ne nécessite pas de re-rendu : appliquée en direct.
            if self._ticker_res is not None and cfg is not None:
                self._ticker_res["speed"] = float(cfg["speed"])
            return
        self._ticker_sig = sig
        self._ticker_res = None
        if cfg is None:
            return

        from PIL import Image, ImageDraw, ImageFont

        height = int(cfg["height"])
        px = int(cfg["font_size"])
        try:
            font = ImageFont.truetype(str(cfg["font_family"]), px)
        except Exception:
            try:
                font = ImageFont.truetype("arial.ttf", px)
            except Exception:
                font = ImageFont.load_default()

        separator = "   •   "
        text = separator.join(cfg["texts"]) + separator
        probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
        try:
            text_w = int(probe.textlength(text, font=font)) + 24
        except Exception:
            text_w = self._width
        text_w = max(1, text_w)

        line = Image.new("RGBA", (text_w, height), (0, 0, 0, 0))
        ldraw = ImageDraw.Draw(line)
        text_fill = _parse_rgba_tuple(cfg["text_color"], (255, 255, 255, 242))
        try:
            bbox = ldraw.textbbox((0, 0), text, font=font)
            y = max(0, (height - (bbox[3] - bbox[1])) // 2 - bbox[1])
        except Exception:
            y = max(0, (height - px) // 2)
        ldraw.text((12, y), text, font=font, fill=text_fill)

        self._ticker_res = {
            "height": height,
            "speed": float(cfg["speed"]),
            "bg": _parse_rgba_tuple(cfg["bg_color"], (5, 10, 22, 209)),
            "line": line,
            "period": text_w,
        }
        self._ticker_last = 0.0

    def _apply_ticker(self, base: Any, offset: float) -> Any:
        """Compose la bande défilante sur une copie de l'image de base.

        Seule la bande basse est réécrite : le reste de l'image (bandeau
        texte, image de fond) est recopié tel quel, sans re-rendu PIL.
        """
        assert self._np is not None
        res = self._ticker_res
        if res is None:
            return base

        from PIL import Image, ImageDraw

        height = min(int(res["height"]), self._height)
        band = Image.new("RGBA", (self._width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(band)
        draw.rectangle([0, 0, self._width, height], fill=res["bg"])

        line = res["line"]
        period = int(res["period"])
        x = -(float(offset) % period)
        while x < self._width:
            band.paste(line, (int(x), 0), line)
            x += period
        draw.line([0, 0, self._width, 0], fill=(255, 255, 255, 26), width=1)

        strip = self._np.array(band, dtype=self._np.uint8)[:, :, [2, 1, 0, 3]]
        frame = base.copy()
        frame[self._height - height :, :, :] = strip
        return frame

    def _run(self) -> None:
        assert self._ndi is not None
        assert self._np is not None
        assert self._ndi_send is not None
        assert self._video_frame is not None

        fps = 30.0
        interval = 1.0 / fps

        last_frame = self._np.zeros(
            (self._height, self._width, 4), dtype=self._np.uint8
        )

        needs_render = True
        consecutive_send_errors = 0
        # Cadence corrigée en dérive : l'heure de la frame suivante est
        # calculée sur une horloge monotone, pas sur la durée du travail.
        next_frame = time.monotonic()
        while not self._stop.is_set():
            try:
                cfg_mtime = (
                    self._cfg_path.stat().st_mtime if self._cfg_path.exists() else -1.0
                )
            except Exception:
                cfg_mtime = -1.0
            if cfg_mtime != self._last_cfg_mtime:
                self._last_cfg_mtime = cfg_mtime
                self._last_cfg = self._read_json(self._cfg_path) or {}
                needs_render = True

            try:
                slide_mtime = (
                    self._slide_path.stat().st_mtime
                    if self._slide_path.exists()
                    else -1.0
                )
            except Exception:
                slide_mtime = -1.0
            if slide_mtime != self._last_slide_mtime:
                self._last_slide_mtime = slide_mtime
                self._last_payload = self._read_json(self._slide_path)
                needs_render = True

            # Only re-render (PIL raster) when the slide or config actually
            # changed; the same cached frame is streamed at a steady rate.
            if needs_render:
                try:
                    frame = self._render(self._last_payload)
                except Exception:
                    frame = None
                if frame is not None:
                    last_frame = frame
                self._refresh_ticker_resources()
                needs_render = False

            # Bandeau défilant : recomposé à chaque frame (seule la bande
            # basse change), décalage piloté par une horloge monotone.
            if self._ticker_res is not None:
                now = time.monotonic()
                if self._ticker_last:
                    dt = min(0.5, now - self._ticker_last)
                    self._ticker_offset = (
                        self._ticker_offset + self._ticker_res["speed"] * dt
                    ) % float(self._ticker_res["period"])
                self._ticker_last = now
                last_frame = self._apply_ticker(last_frame, self._ticker_offset)

            # Reuse frame object; swap underlying data. Une erreur d'envoi
            # (runtime arrêté, adaptateur réseau changé) n'interrompt pas la
            # boucle : on réessaie, et on rend les armes après ~3 s d'échecs
            # pour laisser le superviseur relancer proprement.
            self._video_frame.data = last_frame
            try:
                self._ndi.send_send_video_v2(self._ndi_send, self._video_frame)
                consecutive_send_errors = 0
            except Exception as exc:
                consecutive_send_errors += 1
                self.last_error = f"Envoi NDI en échec : {exc}"
                if consecutive_send_errors == 1:
                    self._log_warning("Envoi NDI interrompu (%s)", exc)
                if consecutive_send_errors >= 90:
                    self._log_warning(
                        "Envoi NDI abandonné après %d échecs consécutifs",
                        consecutive_send_errors,
                    )
                    break

            next_frame += interval
            delay = next_frame - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                # On a pris du retard : on repart de l'instant présent.
                next_frame = time.monotonic()

    @staticmethod
    def _log_warning(message: str, *args) -> None:
        import logging

        logging.getLogger(__name__).warning(message, *args)
