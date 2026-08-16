"""Remote control of OBS via obs-websocket 5.x.

Implements the small subset of the protocol Project-On needs:
identify (with challenge/response auth), list scenes, switch program
scene, and create/update the Project-On browser source.

Uses PyQt6's QWebSocket so everything runs on the Qt event loop — no
extra dependency and thread-safe interaction with the UI.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any, Callable

from PyQt6.QtCore import QObject, QUrl, QTimer, pyqtSignal
from PyQt6.QtWebSockets import QWebSocket

from app.utils.settings import ObsRemoteSettings

logger = logging.getLogger(__name__)

# WebSocket operations (obs-websocket 5.x)
OP_HELLO = 0
OP_IDENTIFY = 1
OP_IDENTIFIED = 2
OP_REQUEST = 6
OP_REQUEST_RESPONSE = 7


def compute_obs_auth_hash(password: str, salt: str, challenge: str) -> str:
    """obs-websocket v5 auth string.

    base64( sha256( base64( sha256( password + salt ) ) + challenge ) )
    """
    secret = hashlib.sha256((password + salt).encode("utf-8")).digest()
    challenge_bytes = base64.b64encode(secret) + challenge.encode("utf-8")
    final = hashlib.sha256(challenge_bytes).digest()
    return base64.b64encode(final).decode("ascii")


def build_identify_payload(
    password: str, salt: str, challenge: str
) -> dict[str, Any]:
    """Identify payload for a Hello message that requested authentication."""
    payload: dict[str, Any] = {"rpcVersion": 1, "eventSubscriptions": 0}
    if salt and challenge:
        payload["authentication"] = compute_obs_auth_hash(password, salt, challenge)
    return payload


def build_browser_source_settings(url: str) -> dict[str, Any]:
    """Default input settings for a 1080p browser source."""
    return {
        "url": url,
        "width": 1920,
        "height": 1080,
        "reroute_audio": False,
        "restart_when_active": False,
        "shutdown": False,
    }


class ObsRemoteClient(QObject):
    """Qt client for obs-websocket 5.x with auto-reconnect."""

    connected = pyqtSignal()
    disconnected = pyqtSignal()
    errorOccurred = pyqtSignal(str)
    scenesLoaded = pyqtSignal(list)
    browserSourceCreated = pyqtSignal(str)  # scene name

    RECONNECT_MS = 10_000

    def __init__(self, settings: ObsRemoteSettings | None = None, parent=None):
        super().__init__(parent)
        self._settings = settings or ObsRemoteSettings()
        self._socket: QWebSocket | None = None
        self._identified = False
        self._request_counter = 0
        self._pending: dict[str, Callable[[dict[str, Any]], None]] = {}
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._try_reconnect)

    # ── Settings / lifecycle ────────────────────────────────────────────

    @property
    def settings(self) -> ObsRemoteSettings:
        return self._settings

    def apply_settings(self, settings: ObsRemoteSettings) -> None:
        """Swap settings; reconnect if the endpoint changed while active."""
        was_active = self._settings.enabled and self._identified
        endpoint_changed = (
            settings.host != self._settings.host
            or settings.port != self._settings.port
            or settings.password != self._settings.password
        )
        self._settings = settings
        if not settings.enabled:
            self.disconnect_from_obs()
            return
        if was_active and endpoint_changed:
            self.disconnect_from_obs()
            self.connect_to_obs()
        elif settings.enabled and not self.is_connected():
            self.connect_to_obs()

    def is_connected(self) -> bool:
        return self._identified and self._socket is not None

    def connect_to_obs(self) -> None:
        if self.is_connected():
            return
        if self._socket is not None:
            self._close_socket()

        socket = QWebSocket()
        socket.textMessageReceived.connect(self._on_text_message)
        socket.connected.connect(self._on_socket_connected)
        socket.disconnected.connect(self._on_socket_disconnected)
        socket.errorOccurred.connect(self._on_socket_error)
        self._socket = socket

        url = QUrl(f"ws://{self._settings.host}:{int(self._settings.port)}")
        logger.info("OBS remote: connecting to %s", url.toString())
        socket.open(url)

    def disconnect_from_obs(self) -> None:
        self._reconnect_timer.stop()
        self._close_socket()

    def _close_socket(self) -> None:
        if self._socket is None:
            return
        socket = self._socket
        self._socket = None
        try:
            socket.textMessageReceived.disconnect(self._on_text_message)
            socket.connected.disconnect(self._on_socket_connected)
            socket.disconnected.disconnect(self._on_socket_disconnected)
            socket.errorOccurred.disconnect(self._on_socket_error)
        except (TypeError, RuntimeError):
            pass
        socket.close()
        socket.deleteLater()
        was_identified = self._identified
        self._identified = False
        self._pending.clear()
        if was_identified:
            self.disconnected.emit()

    def _try_reconnect(self) -> None:
        if self._settings.enabled and not self.is_connected():
            self.connect_to_obs()

    # ── Socket events ───────────────────────────────────────────────────

    def _on_socket_connected(self) -> None:
        logger.debug("OBS remote: socket connected, awaiting Hello")

    def _on_socket_disconnected(self) -> None:
        was_identified = self._identified
        self._identified = False
        self._pending.clear()
        if self._socket is not None:
            self._socket.deleteLater()
            self._socket = None
        if was_identified:
            self.disconnected.emit()
        if self._settings.enabled:
            self._reconnect_timer.start(self.RECONNECT_MS)

    def _on_socket_error(self, error) -> None:
        message = str(error)
        logger.warning("OBS remote error: %s", message)
        # Only surface user-facing failures; stay quiet while OBS is simply
        # not running (auto-reconnect keeps retrying in the background).
        if self._identified:
            self.errorOccurred.emit(message)

    def _on_text_message(self, message: str) -> None:
        import json

        try:
            payload = json.loads(message)
        except ValueError:
            logger.warning("OBS remote: invalid JSON message")
            return

        op = payload.get("op")
        data = payload.get("d") or {}

        if op == OP_HELLO:
            self._handle_hello(data)
        elif op == OP_IDENTIFIED:
            self._identified = True
            logger.info("OBS remote: identified")
            self.connected.emit()
        elif op == OP_REQUEST_RESPONSE:
            self._handle_response(data)

    def _handle_hello(self, data: dict[str, Any]) -> None:
        auth = data.get("authentication") or {}
        identify = build_identify_payload(
            self._settings.password,
            str(auth.get("salt") or ""),
            str(auth.get("challenge") or ""),
        )
        import json

        if self._socket is not None:
            self._socket.sendTextMessage(
                json.dumps({"op": OP_IDENTIFY, "d": identify})
            )

    def _handle_response(self, data: dict[str, Any]) -> None:
        request_id = str(data.get("requestId") or "")
        callback = self._pending.pop(request_id, None)
        if callback is None:
            return
        try:
            callback(data)
        except Exception:
            logger.exception("OBS remote: response handler failed")

    # ── Requests ────────────────────────────────────────────────────────

    def _send_request(
        self,
        request_type: str,
        request_data: dict[str, Any] | None = None,
        on_response: Callable[[dict[str, Any]], None] | None = None,
    ) -> str | None:
        import json

        if not self.is_connected() or self._socket is None:
            return None
        self._request_counter += 1
        request_id = f"projecton-{self._request_counter}"
        if on_response is not None:
            self._pending[request_id] = on_response
        message: dict[str, Any] = {
            "op": OP_REQUEST,
            "d": {"requestType": request_type, "requestId": request_id},
        }
        if request_data is not None:
            message["d"]["requestData"] = request_data
        self._socket.sendTextMessage(json.dumps(message))
        return request_id

    def get_scenes(self) -> None:
        """Request the OBS scene list; emits scenesLoaded(list[str])."""

        def handle(data: dict[str, Any]) -> None:
            status = data.get("requestStatus") or {}
            if not status.get("result"):
                self.errorOccurred.emit(
                    "Impossible de lire les scènes OBS ("
                    + str(status.get("comment") or "erreur")
                    + ")"
                )
                return
            response = data.get("responseData") or {}
            names = [
                item.get("sceneName")
                for item in response.get("scenes") or []
                if item.get("sceneName")
            ]
            self.scenesLoaded.emit(list(names))

        self._send_request("GetSceneList", None, handle)

    def set_scene(self, scene_name: str) -> None:
        """Switch the OBS program scene."""
        if not scene_name:
            return
        self._send_request(
            "SetCurrentProgramScene", {"sceneName": scene_name}
        )

    def notify_live(self, hidden: bool) -> None:
        """Apply the configured scene switch for live/hidden state."""
        if not self.is_connected() or not self._settings.enabled:
            return
        target = self._settings.scene_on_hide if hidden else self._settings.scene_on_live
        if target:
            self.set_scene(target)

    def create_browser_source(
        self, scene_name: str, url: str, source_name: str = "Project-On"
    ) -> None:
        """Create (or re-point) the Project-On browser source in a scene."""

        def on_created(data: dict[str, Any]) -> None:
            status = data.get("requestStatus") or {}
            if status.get("result"):
                self.browserSourceCreated.emit(scene_name)
                return
            # Most likely the input already exists — update its URL instead.
            self._send_request(
                "SetInputSettings",
                {
                    "inputName": source_name,
                    "inputSettings": build_browser_source_settings(url),
                    "overlay": True,
                },
                lambda _data: self.browserSourceCreated.emit(scene_name),
            )

        self._send_request(
            "CreateInput",
            {
                "sceneName": scene_name,
                "inputName": source_name,
                "inputKind": "browser_source",
                "inputSettings": build_browser_source_settings(url),
                "sceneItemEnabled": True,
            },
            on_created,
        )
