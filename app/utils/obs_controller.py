"""Professional OBS Controller for Project-On.

This module manages both Web Server and NDI output modes for OBS integration.
The Web Server mode uses Server-Sent Events (SSE) for real-time updates.
"""

from __future__ import annotations

import logging
import threading
import webbrowser
from typing import Any

from app.utils.app_paths import ensure_presentation_workdir
from app.utils.obs_web_server import ObsWebServer
from app.utils.settings import ObsOutputSettings, ObsSettings
from app.utils.text_utils import (
    format_hymn_for_obs_lower_third,
    format_hymn_reference_for_obs,
)

logger = logging.getLogger(__name__)


class ObsController:
    """Professional OBS output controller.

    Manages two output modes:
    - Web Server: HTTP server with SSE for real-time OBS Browser Source updates
    - NDI: Network Device Interface for direct video streaming (requires NDI SDK)
    """

    def __init__(self, settings: ObsSettings | None = None) -> None:
        self._settings = settings or ObsSettings()
        self._web_server = ObsWebServer(port=self._settings.web_port)
        self._ndi_sender = None
        self._slide_lock = threading.Lock()
        self._current_slide: dict = {"text": "", "reference": "", "hidden": True}

        # Apply initial config
        self._apply_output_config()

    def start_server(self):
        if self._web_server is None:
            logger.info("Starting OBS web server instance")
            self._web_server = ObsWebServer(self._settings.web_port)
            self._web_server.start()
        else:
            logger.debug("OBS web server already running")

    @property
    def settings(self) -> ObsSettings:
        return self._settings

    def update_settings(self, settings: ObsSettings) -> None:
        """Update OBS settings and apply changes immediately."""
        old_port = self._settings.web_port
        old_mode = self._settings.mode
        self._settings = settings

        # Update web server port if changed
        if old_port != settings.web_port:
            self._web_server.port = settings.web_port

        # Apply output config changes
        self._apply_output_config()

        # Handle mode change
        if old_mode != settings.mode:
            if old_mode == "web":
                self.stop_web_server()
            elif old_mode == "ndi":
                self.stop_ndi()

        self.start()

    def update_output_settings(self, output: ObsOutputSettings) -> None:
        """Update only the output/style settings."""
        self._settings.output = output
        self._apply_output_config()

    def _apply_output_config(self) -> None:
        """Apply output configuration to the web server."""
        try:
            config = self._settings.output.to_obs_config()
            logger.debug("Applying OBS output config: %s", config)
            self._web_server.update_config(config)
        except Exception as e:
            logger.exception("Failed to apply OBS output config: %s", e)

    def update_slide(
        self, text: str, reference: str, source: str = "custom", hidden: bool = False, image_path: str = ""
    ) -> None:
        """Update the current slide content. This is called by the project controller."""
        if source == "hymn":
            text = format_hymn_for_obs_lower_third(text)
            reference = format_hymn_reference_for_obs(reference)
        with self._slide_lock:
            self._current_slide = {
                "text": text,
                "reference": reference,
                "source": source,
                "hidden": hidden,
                "image_path": image_path,
            }
        self._web_server.update_slide(text, reference, source, hidden, image_path)

        # Also update NDI if active (NDI reads from file, but we can trigger a refresh if the sender supports it)
        if self._ndi_sender is not None:
            try:
                # The NdiLowerThirdSender reads from slide.json periodically in its own thread,
                # so we don't strictly need to call an update method here unless we want immediate frame generation.
                # However, the current implementation of NdiLowerThirdSender does NOT have an update_slide method.
                pass
            except Exception:
                pass

    # ==================== WEB SERVER ====================

    def start_web_server(self) -> bool:
        """Start the HTTP server for OBS Browser Source."""
        if self._web_server.is_running():
            return True

        ok = self._web_server.start()
        if ok:
            self._apply_output_config()
            with self._slide_lock:
                slide = dict(self._current_slide)
            self._web_server.update_slide(
                slide.get("text", ""),
                slide.get("reference", ""),
                slide.get("source", "custom"),
                slide.get("hidden", True),
                slide.get("image_path", ""),
            )
        return ok

    def stop_web_server(self) -> None:
        """Stop the HTTP server."""
        self._web_server.stop()

    def is_web_server_running(self) -> bool:
        """Check if the web server is running."""
        return self._web_server.is_running()

    def get_web_server_url(self) -> str:
        """Get the URL for OBS Browser Source."""
        return self._web_server.get_url()

    def open_in_browser(self) -> None:
        """Open the OBS page in the default browser for testing."""
        url = self.get_web_server_url()
        if url:
            webbrowser.open_new_tab(url)

    # ==================== NDI ====================

    def start_ndi(self) -> bool:
        """Start NDI output. Returns False if NDI is not available."""
        try:
            from app.utils.ndi_lower_third import NdiLowerThirdSender
        except ImportError:
            return False

        availability = NdiLowerThirdSender.availability()
        if not availability.usable:
            logger.warning("NDI unavailable: %s", availability.message)
            return False

        if self._ndi_sender is not None:
            return True

        sender = NdiLowerThirdSender(
            presentation_dir=ensure_presentation_workdir(),
            source_name=self._settings.ndi_source_name or "Project-On",
        )
        ok = sender.start()
        if not ok:
            return False

        self._ndi_sender = sender

        return True

    def stop_ndi(self) -> None:
        """Stop NDI output."""
        if self._ndi_sender is not None:
            try:
                self._ndi_sender.stop()
            except Exception:
                pass
            finally:
                self._ndi_sender = None

    def is_ndi_running(self) -> bool:
        """Check if NDI output is active."""
        return self._ndi_sender is not None

    def is_ndi_available(self) -> bool:
        """Check if NDI SDK is available on this system."""
        return self.get_ndi_availability().get("usable", False)

    def get_ndi_availability(self) -> dict[str, Any]:
        """Return detailed NDI detection status for the UI."""
        try:
            from app.utils.ndi_lower_third import NdiLowerThirdSender

            availability = NdiLowerThirdSender.availability()
            return {
                "runtime_found": availability.runtime_found,
                "python_bridge_found": availability.python_bridge_found,
                "numpy_found": availability.numpy_found,
                "usable": availability.usable,
                "runtime_paths": list(availability.runtime_paths),
                "message": availability.message,
            }
        except ImportError:
            return {
                "runtime_found": False,
                "python_bridge_found": False,
                "numpy_found": False,
                "usable": False,
                "runtime_paths": [],
                "message": "Module NDI indisponible.",
            }

    # ==================== GENERAL ====================

    def start(self) -> bool:
        """Start the appropriate output based on current mode setting."""
        if self._settings.mode == "ndi":
            return self.start_ndi()
        return self.start_web_server()

    def stop(self) -> None:
        """Stop all outputs."""
        self.stop_web_server()
        self.stop_ndi()

    def get_status(self) -> dict[str, Any]:
        """Get the current status of all outputs."""
        return {
            "mode": self._settings.mode,
            "web_server": {
                "running": self.is_web_server_running(),
                "url": self.get_web_server_url(),
                "port": self._settings.web_port,
            },
            "ndi": {
                "available": self.is_ndi_available(),
                "detection": self.get_ndi_availability(),
                "running": self.is_ndi_running(),
                "source_name": self._settings.ndi_source_name,
            },
        }
