"""Professional OBS Web Server for Project-On.

Serves the OBS Browser Source page and pushes real-time updates via SSE.
Thread-safe design: all shared state is protected by locks, and SSE
notifications are sent OUTSIDE the data lock to prevent deadlocks.
"""

import json
import logging
import os
import queue
import re
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.utils.app_paths import ensure_presentation_workdir

log = logging.getLogger(__name__)

FILE_BLOCK_SIZE = 64 * 1024
SOCKET_TIMEOUT = 10.0
SSE_HEARTBEAT = 5.0
MAX_SSE_LISTENERS = 16


def _inline_json(value: Any) -> str:
    """JSON safe in an HTML script raw-text element (not HTML entities)."""
    result = json.dumps(value, ensure_ascii=False)
    for char in ("<", ">", "&", "\u2028", "\u2029"):
        result = result.replace(char, f"\\u{ord(char):04x}")
    return result


def _byte_range(header: str, total: int) -> tuple[int, int]:
    """Parse one byte range; reject unsupported/malformed/unsatisfiable ranges."""
    match = re.fullmatch(r"bytes=([0-9]*)-([0-9]*)", header)
    if not match or not any(match.groups()) or total <= 0:
        raise ValueError("Invalid range")
    first, last = match.groups()
    if first:
        start = int(first)
        end = min(int(last), total - 1) if last else total - 1
    else:
        length = int(last)
        if length <= 0:
            raise ValueError("Invalid suffix")
        start, end = max(0, total - length), total - 1
    if start > end or start >= total:
        raise ValueError("Unsatisfiable range")
    return start, end


def _copy_blocks(source, target, length: int) -> None:
    while length > 0:
        block = source.read(min(FILE_BLOCK_SIZE, length))
        if not block:
            break
        target.write(block)
        length -= len(block)


def _offer_latest(q: queue.Queue, payload: Any) -> None:
    """Caller serializes producers with _listeners_lock; never block the UI."""
    try:
        q.put_nowait(payload)
    except queue.Full:
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        q.put_nowait(payload)


class _QuietThreadingHTTPServer(ThreadingHTTPServer):
    """HTTP server that stays silent when a client drops the connection.

    OBS's browser source (and any SSE client) routinely aborts requests when
    a scene changes or the page reloads. The default ``BaseServer.handle_error``
    dumps a full traceback for those — overriding it here keeps the console
    clean. NOTE: this MUST live on the server, not the request handler, because
    socketserver calls ``handle_error`` on the server instance.
    """

    daemon_threads = True
    allow_reuse_address = True

    def server_bind(self):
        """Bind without the reverse-DNS lookup.

        ``http.server.HTTPServer.server_bind`` calls ``socket.getfqdn(host)``
        after binding, which triggers a reverse DNS query. On machines with a
        slow or unreachable resolver this blocks the UI thread for 1.5 s+ at
        startup. ``server_name`` is only used for informational headers, so
        keeping the bound host is safe here.
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(self.server_address)
        self.server_address = self.socket.getsockname()
        host, port = self.server_address[:2]
        self.server_name = host
        self.server_port = port

    def handle_error(self, request, client_address):  # noqa: D102
        exc_type = sys.exc_info()[0]
        if exc_type is not None and issubclass(
            exc_type, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)
        ):
            return  # Client went away — expected, stay silent.
        super().handle_error(request, client_address)


class ObsWebServer:
    """HTTP server for OBS Browser Source with SSE push."""

    def __init__(self, port: int = 8080, host: str = "127.0.0.1") -> None:
        # LAN binding is an explicit opt-in; this server has no authentication.
        if not isinstance(host, str) or not host.strip():
            raise ValueError("An explicit non-empty OBS bind host is required")
        self._host = host.strip()
        self._port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

        # Shared state — protected by _data_lock
        self._data_lock = threading.Lock()
        self._config: dict[str, Any] = {}
        self._slide: dict[str, Any] = {
            "text": "",
            "reference": "",
            "source": "custom",
            "hidden": True,
        }
        self._listeners: list[queue.Queue] = []
        self._listeners_lock = threading.Lock()

        self._base_dir = ensure_presentation_workdir().resolve()
        log.info("[OBS] Server init (SSE Mode) - port=%s base=%s", port, self._base_dir)

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def host(self) -> str:
        return self._host

    @host.setter
    def host(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("An explicit non-empty OBS bind host is required")
        value = value.strip()
        if self._host != value:
            self._host = value
            if self.is_running():
                self.restart()

    @property
    def port(self) -> int:
        return self._port

    @port.setter
    def port(self, value: int) -> None:
        if self._port != value:
            self._port = value
            if self.is_running():
                self.restart()

    def is_running(self) -> bool:
        return self._server is not None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self) -> bool:
        if self.is_running():
            return True

        server_ref = self  # closure for inner class

        class _Handler(BaseHTTPRequestHandler):
            """Request handler — one instance per request thread."""

            def log_message(self, fmt, *args):
                """Silences logs for cleaner console output."""
                pass

            def setup(self):
                self.request.settimeout(SOCKET_TIMEOUT)
                super().setup()

            # ── Routing ────────────────────────────────────────────────

            def do_GET(self):
                path = urlparse(self.path).path.lstrip("/")
                path = path.removeprefix("presentation/")

                if path in ("", "obs", "obs.html"):
                    self._serve_dynamic_obs()

                elif path == "slide.json":
                    with server_ref._data_lock:
                        data = server_ref._slide.copy()
                    self._json(data)

                elif path in ("obs-config.json", "api/config", "api/config.json"):
                    with server_ref._data_lock:
                        data = server_ref._config.copy()
                    self._json(data)

                elif path in ("api/updates", "api/updates.json"):
                    with server_ref._data_lock:
                        data = {
                            "config": server_ref._config.copy(),
                            "slide": server_ref._slide.copy(),
                        }
                    self._json(data)

                elif path == "api/stream":
                    self._serve_sse_stream()

                elif path == "api/status":
                    self._json({"status": "ok", "mode": "sse"})

                elif path == "api/image":
                    with server_ref._data_lock:
                        img_path = server_ref._slide.get("image_path", "")
                    if not img_path:
                        self.send_error(404)
                        return
                    target = Path(img_path)
                    if target.is_file():
                        self._file(target)
                    else:
                        self.send_error(404)

                elif path == "api/video":
                    with server_ref._data_lock:
                        video_path = str(
                            server_ref._slide.get("video_path", "") or ""
                        )
                    if not video_path:
                        self.send_error(404)
                        return
                    target = Path(video_path)
                    if target.is_file():
                        # Range basique : le navigateur OBS demande souvent
                        # « bytes=0- » avant de streamer.
                        self._video_file(target, self.headers.get("Range", ""))
                    else:
                        self.send_error(404)

                elif path == "api/bg-image":
                    with server_ref._data_lock:
                        bg_path = server_ref._config.get("bg_image", "")
                    if not bg_path:
                        self.send_error(404)
                        return
                    target = Path(bg_path)
                    if target.is_file():
                        self._file(target)
                    else:
                        self.send_error(404)

                elif path.startswith("assets/"):
                    # Serve assets from project root (parent of presentation dir)
                    # This allows fonts.css (which uses ../assets) to resolve correctly
                    asset_root = server_ref._base_dir.parent / "assets"
                    # Strip "assets/" prefix from path to get relative path inside assets dir
                    rel_path = path[len("assets/") :]
                    target = (asset_root / rel_path).resolve()

                    try:
                        target.relative_to(asset_root)
                    except ValueError:
                        self.send_error(403)
                        return

                    if target.is_file():
                        self._file(target)
                    else:
                        self.send_error(404)

                else:
                    target = (server_ref._base_dir / path).resolve()
                    try:
                        target.relative_to(server_ref._base_dir)
                    except ValueError:
                        self.send_error(403)
                        return
                    if target.is_file():
                        self._file(target)
                    else:
                        self.send_error(404)

            def _serve_dynamic_obs(self):
                """Serve the OBS page with inlined CSS/JS and injected state."""
                try:
                    html_template = (server_ref._base_dir / "obs.html").read_text(
                        encoding="utf-8"
                    )
                    css = (server_ref._base_dir / "obs-style.css").read_text(
                        encoding="utf-8"
                    )
                    js = (server_ref._base_dir / "obs-script.js").read_text(
                        encoding="utf-8"
                    )
                except Exception as e:
                    self.send_error(500, f"Template error: {e}")
                    return

                with server_ref._data_lock:
                    cfg = server_ref._config.copy()
                    slide = server_ref._slide.copy()

                init_json = _inline_json({"config": cfg, "slide": slide})

                # Inject CSS and JS inline to avoid OBS cache issues
                html = html_template.replace(
                    '<link rel="stylesheet" href="obs-style.css">',
                    f'<style>\n/* INLINED CSS */\n{css}\n</style>'
                ).replace(
                    '<script src="obs-script.js"></script>',
                    f'<script>\nwindow.initialData = {init_json};\n/* INLINED JS */\n{js}\n</script>'
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                # Aggressive no-cache
                self.send_header(
                    "Cache-Control", "no-store, no-cache, must-revalidate, max-age=0"
                )
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))

            def _serve_sse_stream(self):
                """Serve Server-Sent Events (SSE) stream for real-time updates."""
                q = queue.Queue(maxsize=1)
                with server_ref._listeners_lock:
                    if len(server_ref._listeners) >= MAX_SSE_LISTENERS:
                        self.send_error(503, "Too many event subscribers")
                        return
                    server_ref._listeners.append(q)
                try:
                    self._stream_events(q)
                except (OSError, TimeoutError):
                    pass
                finally:
                    with server_ref._listeners_lock:
                        if q in server_ref._listeners:
                            server_ref._listeners.remove(q)

            def _stream_events(self, q):
                # Push initial state immediately
                with server_ref._data_lock:
                    initial_payload = {
                        "config": server_ref._config.copy(),
                        "slide": server_ref._slide.copy(),
                    }
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(
                    f"data: {json.dumps(initial_payload, ensure_ascii=False)}\n\n".encode(
                        "utf-8"
                    )
                )
                self.wfile.flush()
                while server_ref.is_running():
                    try:
                        payload = q.get(timeout=SSE_HEARTBEAT)
                        if payload is None:
                            break
                        self.wfile.write(
                            f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode(
                                "utf-8"
                            )
                        )
                    except queue.Empty:
                        payload = None
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()


            # ── Helpers ────────────────────────────────────────────────

            _MIME = {
                ".html": "text/html",
                ".css": "text/css",
                ".js": "application/javascript",
                ".json": "application/json",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".svg": "image/svg+xml",
                ".ttf": "font/ttf",
                ".woff": "font/woff",
                ".woff2": "font/woff2",
                ".mp4": "video/mp4",
                ".webm": "video/webm",
                ".mov": "video/quicktime",
                ".mkv": "video/x-matroska",
                ".avi": "video/x-msvideo",
            }

            def _file(self, fpath: Path, ctype: str | None = None):
                if not fpath.is_file():
                    self.send_error(404)
                    return
                if ctype is None:
                    ctype = self._MIME.get(
                        fpath.suffix.lower(), "application/octet-stream"
                    )
                try:
                    fh = fpath.open("rb")
                except OSError:
                    self.send_error(404)
                    return
                try:
                    with fh:
                        length = os.fstat(fh.fileno()).st_size
                        self.send_response(200)
                        self.send_header("Content-Type", ctype)
                        self.send_header("Content-Length", str(length))
                        self.send_header("Cache-Control", "no-cache")
                        self.end_headers()
                        _copy_blocks(fh, self.wfile, length)
                except (OSError, TimeoutError):
                    self.close_connection = True

            def _video_file(self, fpath: Path, range_header: str = ""):
                """Sert une vidéo avec support Range (lecture navigateur OBS)."""
                if not fpath.is_file():
                    self.send_error(404)
                    return
                ctype = self._MIME.get(
                    fpath.suffix.lower(), "video/mp4"
                )
                total = fpath.stat().st_size
                start, end = 0, total - 1
                range_header = (range_header or "").strip()
                if range_header:
                    try:
                        start, end = _byte_range(range_header, total)
                    except ValueError:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{total}")
                        self.end_headers()
                        return
                try:
                    with fpath.open("rb") as fh:
                        fh.seek(start)
                        self.send_response(206 if range_header else 200)
                        if range_header:
                            self.send_header(
                                "Content-Range", f"bytes {start}-{end}/{total}"
                            )
                        self.send_header("Content-Type", ctype)
                        self.send_header("Content-Length", str(end - start + 1))
                        self.send_header("Accept-Ranges", "bytes")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.send_header("Cache-Control", "no-cache")
                        self.end_headers()
                        _copy_blocks(fh, self.wfile, end - start + 1)
                except (OSError, TimeoutError):
                    # Client déconnecté en cours de stream : non bloquant.
                    pass

            def _json(self, obj: Any):
                try:
                    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(body)
                except (OSError, TimeoutError):
                    self.close_connection = True


        try:
            self._server = _QuietThreadingHTTPServer((self._host, self._port), _Handler)
            self._port = self._server.server_port
            self._thread = threading.Thread(
                target=self._server.serve_forever, daemon=True
            )
            self._thread.start()
            log.info("[OBS] Server started on port %s", self._port)
            return True
        except Exception as exc:
            log.exception("Echec du demarrage du serveur OBS")
            self._server = None
            return False

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        self._thread = None

        with self._listeners_lock:
            listeners = list(self._listeners)
            self._listeners.clear()
        for q in listeners:
            _offer_latest(q, None)
        log.info("[OBS] Server stopped")

    def restart(self) -> bool:
        self.stop()
        return self.start()

    # ── Data Updates ───────────────────────────────────────────────────────
    #
    #  CRITICAL: We copy data under _data_lock, then release the lock
    #  BEFORE writing to SSE clients.  This prevents deadlocks when a
    #  socket write blocks.

    def update_config(self, config: dict[str, Any]) -> None:
        """Update config. Polling clients will pick it up on next interval."""
        with self._data_lock:
            self._config = config.copy()
        self._broadcast_update()

    def update_slide(
        self, text: str, reference: str, source: str = "custom", hidden: bool = False, image_path: str = "", video_path: str = "", video_playing: bool = False
    ) -> None:
        """Update slide. Polling clients will pick it up on next interval."""
        slide = {
            "text": text,
            "reference": reference,
            "source": source,
            "hidden": hidden,
            "image_path": image_path,
            "video_path": video_path,
            "video_playing": bool(video_playing),
        }
        with self._data_lock:
            self._slide = slide.copy()
        self._broadcast_update()

    def _broadcast_update(self) -> None:
        with self._data_lock:
            payload = {
                "config": self._config.copy(),
                "slide": self._slide.copy(),
            }
        with self._listeners_lock:
            for q in self._listeners:
                _offer_latest(q, payload)

    # ── URL ────────────────────────────────────────────────────────────────

    def get_url(self) -> str:
        host = self._host
        if host in ("", "0.0.0.0", "::"):
            host = "127.0.0.1"
        return f"http://{host}:{self._port}/obs"
