"""Cycle de vie NDI : le thread est propriétaire des ressources natives.

Tests avec mocks uniquement — aucun runtime NDI réel ni réseau.
"""
from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock

from app.utils.ndi_lower_third import NdiLowerThirdSender


class _FakeNdi:
    def __init__(self) -> None:
        self.send_destroy_calls: list[object] = []
        self.destroy_calls = 0

    def send_destroy(self, send) -> None:
        self.send_destroy_calls.append(send)

    def destroy(self) -> None:
        self.destroy_calls += 1


def _make_sender(tmp_path: Path) -> tuple[NdiLowerThirdSender, _FakeNdi]:
    sender = NdiLowerThirdSender(tmp_path, "Test")
    fake = _FakeNdi()
    sender._ndi = fake
    sender._np = MagicMock()
    sender._video_frame = MagicMock()
    sender._ndi_send = object()
    return sender, fake


def test_stop_destroys_runtime_once_thread_has_exited(tmp_path):
    sender, fake = _make_sender(tmp_path)
    # Thread déjà terminé (pas _run) : stop() détruit send + runtime global.
    thread = threading.Thread(target=lambda: None)
    thread.start()
    thread.join()
    sender._thread = thread
    handle = sender._ndi_send

    sender.stop()

    assert fake.send_destroy_calls == [handle]
    assert fake.destroy_calls == 1
    assert sender._ndi_send is None
    assert sender._thread is None


def test_stop_never_destroys_while_thread_is_alive(tmp_path):
    sender, fake = _make_sender(tmp_path)

    entered = threading.Event()
    released = threading.Event()

    def blocked_run() -> None:
        entered.set()
        released.wait(timeout=10)

    thread = threading.Thread(target=blocked_run, daemon=True)
    thread.start()
    sender._thread = thread
    assert entered.wait(2)

    sender.stop()  # join 2 s puis renonce sans destruction native

    assert thread.is_alive()
    assert fake.send_destroy_calls == []
    assert fake.destroy_calls == 0

    released.set()
    thread.join(timeout=5)
    assert not thread.is_alive()


def test_run_finally_owns_send_destroy(tmp_path):
    sender, fake = _make_sender(tmp_path)
    handle = sender._ndi_send
    sender._stop.set()  # boucle immédiate : seul le finally s'exécute

    sender._run()

    assert fake.send_destroy_calls == [handle]
    assert sender._ndi_send is None
    assert sender._video_frame is None


def test_is_alive_false_and_start_refuses_while_winding_down(tmp_path):
    sender, fake = _make_sender(tmp_path)
    sender._ndi_send = None  # finally du thread déjà passé : nettoyage en cours

    def hanging_run() -> None:
        threading.Event().wait(timeout=30)

    thread = threading.Thread(target=hanging_run, daemon=True)
    thread.start()
    sender._thread = thread

    assert sender.is_alive is False
    assert sender.start() is False
    assert "Arrêt NDI précédent" in sender.last_error
