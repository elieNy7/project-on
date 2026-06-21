"""Professional OBS Web Server for Project-On.

Serves the OBS Browser Source page and pushes real-time updates via SSE.
Thread-safe design: all shared state is protected by locks, and SSE
notifications are sent OUTSIDE the data lock to prevent deadlocks.
"""

import json
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.utils.app_paths import ensure_presentation_workdir


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

    def handle_error(self, request, client_address):  # noqa: D102
        exc_type = sys.exc_info()[0]
        if exc_type is not None and issubclass(
            exc_type, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)
        ):
            return  # Client went away — expected, stay silent.
        super().handle_error(request, client_address)


class ObsWebServer:
    """HTTP server for OBS Browser Source with SSE push."""

    def __init__(self, port: int = 8080) -> None:
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
        print(f"[OBS] Server init (SSE Mode) — port={port}  base={self._base_dir}", flush=True)

    # ── Properties ─────────────────────────────────────────────────────────

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
                super().setup()
                self._write_lock = threading.Lock()

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

                init_json = json.dumps(
                    {"config": cfg, "slide": slide}, ensure_ascii=False
                )

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
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                q = queue.Queue()
                with server_ref._listeners_lock:
                    server_ref._listeners.append(q)

                # Push initial state immediately
                with server_ref._data_lock:
                    initial_payload = {
                        "config": server_ref._config.copy(),
                        "slide": server_ref._slide.copy(),
                    }
                try:
                    self.wfile.write(f"data: {json.dumps(initial_payload, ensure_ascii=False)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    with server_ref._listeners_lock:
                        if q in server_ref._listeners:
                            server_ref._listeners.remove(q)
                    return

                try:
                    while server_ref.is_running():
                        try:
                            # 15-second timeout for keepalive ping
                            payload = q.get(timeout=15.0)
                            if payload is None:
                                break

                            self.wfile.write(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8"))
                            self.wfile.flush()
                        except queue.Empty:
                            self.wfile.write(b": ping\n\n")
                            self.wfile.flush()
                except Exception:
                    pass
                finally:
                    with server_ref._listeners_lock:
                        if q in server_ref._listeners:
                            server_ref._listeners.remove(q)


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
                    body = fpath.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(body)
                except Exception as exc:
                    self.send_error(500, str(exc))

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
                except Exception as exc:
                    self.send_error(500, str(exc))


        try:
            self._server = _QuietThreadingHTTPServer(("", self._port), _Handler)
            self._thread = threading.Thread(
                target=self._server.serve_forever, daemon=True
            )
            self._thread.start()
            print(f"[OBS] Server started on port {self._port}", flush=True)
            return True
        except Exception as exc:
            print(f"[OBS] Server failed to start: {exc}", flush=True)
            self._server = None
            return False

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        self._thread = None
        
        with self._listeners_lock:
            for q in self._listeners:
                q.put(None)
            self._listeners.clear()
        print("[OBS] Server stopped", flush=True)

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
        self, text: str, reference: str, source: str = "custom", hidden: bool = False, image_path: str = ""
    ) -> None:
        """Update slide. Polling clients will pick it up on next interval."""
        slide = {
            "text": text,
            "reference": reference,
            "source": source,
            "hidden": hidden,
            "image_path": image_path,
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
                q.put(payload)

    # ── URL ────────────────────────────────────────────────────────────────

    def get_url(self) -> str:
        return f"http://127.0.0.1:{self._port}/obs"
