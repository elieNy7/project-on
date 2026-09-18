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
from app.utils.media_render import compose_media_frame
from app.utils.obs_overlay_render import animation_total_ms
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
    def __init__(
        self,
        presentation_dir: Path,
        source_name: str,
        hub: Any = None,
    ) -> None:
        self._presentation_dir = presentation_dir
        self._source_name = str(source_name or "Project-On").strip() or "Project-On"
        # Lecteur vidéo partagé : les images y sont décodées une seule fois
        # pour toutes les sorties (la projection garde son lecteur natif).
        self._hub = hub

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

        # Entrée animée du bandeau : horodatage de départ + durée totale.
        self._anim_started: float | None = None
        self._anim_ms = 0
        self._anim_loaded = False

        # Diagnostic du dernier échec (démarrage ou thread d'envoi).
        self.last_error: str = ""

    @property
    def source_name(self) -> str:
        return self._source_name

    def set_media_hub(self, hub: Any) -> None:
        """Branche (ou rebranche) le lecteur vidéo partagé."""
        self._hub = hub
        if hub is not None and self.is_alive:
            try:
                hub.set_numpy_enabled(True)
            except Exception:
                pass

    @property
    def is_alive(self) -> bool:
        """True tant que le thread d'envoi NDI tourne ET possède sa source.

        Un thread en cours de nettoyage (source déjà détruite par son
        finally) ne doit pas passer pour « en cours » auprès du superviseur.
        """
        return (
            self._thread is not None
            and self._thread.is_alive()
            and self._ndi_send is not None
        )

    @staticmethod
    def availability() -> NdiAvailability:
        return check_ndi_availability()

    def start(self) -> bool:
        if self.is_alive:
            return True  # déjà en cours
        if self._thread is not None and self._thread.is_alive():
            # Le thread précédent termine son nettoyage natif (sa source est
            # déjà détruite) ; un nouveau départ partagerait un état mort.
            self.last_error = (
                "Arrêt NDI précédent pas encore terminé ; réessayez à l'instant."
            )
            return False

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
        # Une vidéo peut apparaître à tout moment : le hub prépare alors aussi
        # la copie numpy de ses images (coût nul quand aucune vidéo ne joue).
        if self._hub is not None:
            try:
                self._hub.set_numpy_enabled(True)
            except Exception:
                pass
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
            if thread.is_alive():
                # Le thread est encore bloqué dans un appel natif : ne jamais
                # détruire les ressources qu'il est susceptible d'utiliser.
                # Son bloc finally de _run fait le nettoyage à sa sortie.
                self._log_warning(
                    "Thread NDI toujours vivant à l'arrêt : "
                    "destruction native abandonnée au thread"
                )
                return
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

    def _hub_video_frame(self, slide: dict[str, Any] | None) -> Any:
        """Dernière image vidéo du lecteur partagé, ou ``None`` si aucune.

        Le décodage appartient au hub (thread GUI) : ici on ne fait que copier
        la trame courante. Aucun décodage dans ce thread — le budget de 33 ms
        reste tenu par le bandeau et l'envoi.
        """
        hub = self._hub
        if hub is None or not isinstance(slide, dict) or slide.get("hidden"):
            return None
        if not str(slide.get("video") or "").strip():
            return None
        try:
            frame = hub.latest_bgra()
        except Exception:
            return None
        if frame is None:
            return None
        if getattr(frame, "shape", None) != (self._height, self._width, 4):
            return None
        return frame

    def _begin_animation(self, slide: dict[str, Any] | None) -> None:
        """Prépare l'entrée animée : la durée vient de la page OBS."""
        if not isinstance(slide, dict) or slide.get("hidden"):
            self._anim_started = None
            return
        total = animation_total_ms(self._last_cfg, str(slide.get("text") or ""))
        if total <= 0:
            self._anim_started = None
            return
        self._anim_ms = total
        self._anim_started = time.monotonic()

    def _render(self, slide: dict[str, Any] | None, *, elapsed_ms=None) -> Any:
        """Trame plein cadre : média opaque, sinon section texte façon OBS.

        ``elapsed_ms`` compose une trame de l'entrée animée ; ``None`` donne
        l'état final, identique à la page OBS stabilisée.
        """
        assert self._np is not None

        media_path = ""
        if isinstance(slide, dict) and not slide.get("hidden"):
            media_path = str(slide.get("image") or "").strip()
        if media_path:
            # Le média est un contenu plein cadre : opaque partout (alpha 255),
            # sans quoi le receveur NDI le découperait comme du texte.
            frame = compose_media_frame(
                media_path, self._width, self._height, self._last_cfg
            )
            if frame is not None:
                rgba = self._np.array(frame.convert("RGBA"), dtype=self._np.uint8)
                return rgba[:, :, [2, 1, 0, 3]].copy()

        img = render_obs_overlay(
            self._last_cfg, slide, self._width, self._height, elapsed_ms=elapsed_ms
        )
        if img is None:
            return self._np.zeros(
                (self._height, self._width, 4), dtype=self._np.uint8
            )
        rgba = self._np.array(img, dtype=self._np.uint8)
        bgra = rgba[:, :, [2, 1, 0, 3]].copy()
        return bgra

    # ── Bandeau défilant (même charge utile que la page OBS) ──────────

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
        try:
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
                    self._begin_animation(self._last_payload)

                # Entrée animée : on recompose une trame par cycle tant que
                # l'animation court, puis l'état final (une seule fois).
                elapsed_ms = None
                if self._anim_started is not None:
                    elapsed_ms = (time.monotonic() - self._anim_started) * 1000.0
                    if elapsed_ms >= self._anim_ms:
                        self._anim_started = None
                    else:
                        needs_render = True

                # Only re-render (PIL raster) when the slide or config actually
                # changed; the same cached frame is streamed at a steady rate.
                if needs_render:
                    try:
                        frame = self._render(self._last_payload, elapsed_ms=elapsed_ms)
                    except Exception:
                        frame = None
                    if frame is not None:
                        last_frame = frame
                    needs_render = False

                # Vidéo réellement lue : la dernière image du lecteur partagé
                # remplace la trame statique (aucun décodage ici — le thread
                # NDI ne fait que copier des octets).
                video_frame = self._hub_video_frame(self._last_payload)
                if video_frame is not None:
                    self._np.copyto(last_frame, video_frame)

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
        finally:
            # Le thread est propriétaire de la source NDI : détruite ici,
            # à sa sortie — jamais depuis l'extérieur pendant qu'il vit.
            try:
                if self._ndi_send is not None:
                    self._ndi.send_destroy(self._ndi_send)
            except Exception:
                pass
            finally:
                self._ndi_send = None
                self._video_frame = None

    @staticmethod
    def _log_warning(message: str, *args) -> None:
        import logging

        logging.getLogger(__name__).warning(message, *args)
