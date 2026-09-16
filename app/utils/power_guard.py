"""Anti-veille Windows pendant les sorties plein écran.

Tant qu'une fenêtre de sortie (projection locale, sortie HDMI mixeur) est
ouverte, Windows ne doit ni éteindre l'écran ni déclencher l'économiseur :
le projecteur et le mélangeur attendent un signal stable pendant tout le
service. Les appels sont comptés par références : le garde est actif tant
qu'au moins une sortie est ouverte.
"""

from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)

_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001
_ES_DISPLAY_REQUIRED = 0x00000002

_lock = threading.Lock()
_refcount = 0
_last_error = ""

try:  # pragma: no cover - dépend de la plateforme
    import ctypes

    _SetThreadExecutionState = ctypes.windll.kernel32.SetThreadExecutionState
except Exception:  # non-Windows ou kernel32 indisponible
    _SetThreadExecutionState = None


def _apply(keep: bool) -> None:
    global _last_error
    if _SetThreadExecutionState is None:
        return
    flags = _ES_CONTINUOUS
    if keep:
        flags |= _ES_SYSTEM_REQUIRED | _ES_DISPLAY_REQUIRED
    try:
        # Appelé uniquement depuis le thread Qt principal : l'état
        # ES_CONTINUOUS est par thread, un seul émetteur évite les conflits.
        result = _SetThreadExecutionState(flags)
        if result == 0 and keep:
            _last_error = "SetThreadExecutionState a échoué"
    except Exception as exc:  # pragma: no cover - chemin défensif
        _last_error = str(exc)
        log.warning("Anti-veille indisponible : %s", exc)


def acquire() -> None:
    """Demande le maintien de l'écran allumé (une sortie de plus)."""
    global _refcount
    with _lock:
        if _refcount == 0:
            _apply(True)
        _refcount += 1


def release() -> None:
    """Libère une demande ; l'anti-veille s'arrête à la dernière sortie."""
    global _refcount
    with _lock:
        if _refcount <= 0:
            return
        _refcount -= 1
        if _refcount == 0:
            _apply(False)


def is_active() -> bool:
    """True tant qu'au moins une sortie maintient l'écran allumé."""
    with _lock:
        return _refcount > 0


def last_error() -> str:
    return _last_error
