"""Preview ("Aperçu") monitor: what the operator prepared, not yet live.

A single click in a library prepares a ProgramCue here; the operator checks
the exact first slide (same renderer, theme and typography as the outputs)
and sends it live with the button or F2. Nothing on this monitor ever
reaches the audience by itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.icons import app_icon
from app.ui.theme import Colors, Radius, Typography, get_accent_button_style, get_icon_button_style
from app.utils.models import Slide
from app.utils.project_on_controller import ProgramCue

Renderer = Callable[[str, str, str, str], "QPixmap | None"]

_SOURCE_LABELS = {
    "bible": "Bible",
    "hymn": "Cantique",
    "sermon": "Prédication",
    "custom": "Playlist",
    "image": "Média",
    "video": "Vidéo",
}


class _Screen(QLabel):
    """16:9 surface that keeps the rendered slide scaled to its size."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full: QPixmap | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(160, 90)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setWordWrap(True)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return int(width * 9 / 16)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(480, 270)

    def set_pixmap(self, pixmap: QPixmap | None) -> None:
        self._full = pixmap
        self._rescale()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self) -> None:
        if self._full is None or self._full.isNull():
            self.setPixmap(QPixmap())
            return
        self.setPixmap(
            self._full.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class CueMonitor(QFrame):
    """Preview monitor with the "send live" action."""

    takeRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CueMonitor")
        self.setStyleSheet(
            f"""
            QFrame#CueMonitor {{
                background: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: {Radius.LG}px;
            }}
            """
        )
        self._cue: ProgramCue | None = None
        self._slide: Slide | None = None
        self._renderer: Renderer | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("Aperçu", self)
        title.setStyleSheet(
            f"font-size: {Typography.SIZE_SECTION}px; font-weight: {Typography.WEIGHT_SEMIBOLD};"
            f" color: {Colors.TEXT_PRIMARY}; background: transparent;"
        )
        header.addWidget(title)
        self._subtitle = QLabel("", self)
        self._subtitle.setStyleSheet(
            f"font-size: {Typography.SIZE_META}px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        self._subtitle.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        header.addWidget(self._subtitle, 1)
        self._clear_button = QPushButton(self)
        self._clear_button.setIcon(app_icon("x-circle.svg", Colors.TEXT_SECONDARY))
        self._clear_button.setIconSize(QSize(16, 16))
        self._clear_button.setToolTip("Vider l'aperçu")
        self._clear_button.setStyleSheet(get_icon_button_style(28))
        self._clear_button.clicked.connect(self.clear)
        header.addWidget(self._clear_button)
        layout.addLayout(header)

        self._screen = _Screen(self)
        self._screen.setStyleSheet(
            f"background: #000000; border-radius: {Radius.SM}px;"
            f" color: {Colors.TEXT_SECONDARY}; font-size: {Typography.SIZE_FILTER}px;"
        )
        layout.addWidget(self._screen, 1)

        self._take_button = QPushButton("Envoyer au direct   F2", self)
        self._take_button.setIcon(app_icon("cast.svg", Colors.PROJECT_BUTTON_TEXT))
        self._take_button.setIconSize(QSize(16, 16))
        self._take_button.setStyleSheet(get_accent_button_style())
        self._take_button.setMinimumHeight(34)
        self._take_button.setToolTip("Projeter l'aperçu devant l'assemblée (F2)")
        self._take_button.clicked.connect(self.takeRequested.emit)
        layout.addWidget(self._take_button)

        self.clear()

    # ── API ──

    def set_renderer(self, renderer: Renderer) -> None:
        self._renderer = renderer

    def cue(self) -> ProgramCue | None:
        return self._cue

    def set_cue(self, cue: ProgramCue | None, slide: Slide | None) -> None:
        self._cue = cue if slide is not None else None
        self._slide = slide if cue is not None else None
        if self._cue is None:
            self.clear()
            return
        source = _SOURCE_LABELS.get(str(slide.source), "")
        title = " ".join(str(cue.title or slide.reference or "").split())
        self._subtitle.setText(f"{source} · {title}" if source else title)
        self._subtitle.setToolTip(title)
        self._take_button.setEnabled(True)
        self._clear_button.setVisible(True)
        self.refresh()

    def clear(self) -> None:
        self._cue = None
        self._slide = None
        self._subtitle.setText("")
        self._screen.set_pixmap(None)
        self._screen.setText("Cliquez un élément pour le préparer ici")
        self._take_button.setEnabled(False)
        self._clear_button.setVisible(False)

    def refresh(self) -> None:
        """Re-render the prepared slide (after a style or settings change)."""
        slide = self._slide
        if slide is None:
            return
        if slide.video_path:
            self._screen.set_pixmap(None)
            self._screen.setText(f"Vidéo · {Path(slide.video_path).name}")
            return
        pixmap = None
        if self._renderer is not None:
            pixmap = self._renderer(
                slide.reference, slide.text, str(slide.source), slide.image_path or ""
            )
        if pixmap is None or pixmap.isNull():
            self._screen.set_pixmap(None)
            self._screen.setText(f"{slide.reference}\n\n{slide.text}".strip())
        else:
            self._screen.setText("")
            self._screen.set_pixmap(pixmap)
