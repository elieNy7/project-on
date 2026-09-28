from __future__ import annotations

"""Photo du pasteur : détourage automatique (IA) ou fond uni, avec aperçu."""

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from app.ui.obs_output_settings_dialog import DIALOG_STYLE
from app.utils import background_removal as br

log = logging.getLogger(__name__)
PREVIEW = 300


def _checkerboard(width: int, height: int) -> QPixmap:
    """Damier gris : montre la transparence du détourage."""
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(236, 236, 236))
    painter = QPainter(pixmap)
    step = 12
    for y in range(0, height, step):
        for x in range(0, width, step):
            if (x // step + y // step) % 2:
                painter.fillRect(x, y, step, step, QColor(200, 200, 200))
    painter.end()
    return pixmap


def _pil_to_qimage(image) -> QImage:
    rgba = image.convert("RGBA")
    data = rgba.tobytes()
    return QImage(data, rgba.width, rgba.height, rgba.width * 4,
                  QImage.Format.Format_RGBA8888).copy()


class _Relay(QObject):
    progress = Signal(int, int)
    done = Signal(object, str)  # image PIL ou None, erreur


class PastorPhotoDialog(QDialog):
    """Choisir la photo, retirer l'arrière-plan, enregistrer le PNG transparent."""

    def __init__(self, source: Path, target: Path, parent=None) -> None:
        super().__init__(parent)
        from PIL import Image, ImageOps

        self.setWindowTitle("Photo du pasteur")
        self.setStyleSheet(DIALOG_STYLE)
        self._target = Path(target)
        self._original = ImageOps.exif_transpose(Image.open(source)).convert("RGB")
        # Taille raisonnable : détourage rapide, projection nette en 1080p.
        self._original.thumbnail((1600, 1600))
        self._result = None
        self._relay = _Relay(self)
        self._relay.progress.connect(self._on_progress)
        self._relay.done.connect(self._on_done)

        self.before = QLabel()
        self.after = QLabel()
        for label in (self.before, self.after):
            label.setFixedSize(PREVIEW, PREVIEW)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._show(self.before, self._original, checker=False)
        self.after.setPixmap(_checkerboard(PREVIEW, PREVIEW))
        images = QHBoxLayout()
        for title, label in (("Photo d'origine", self.before), ("Sans arrière-plan", self.after)):
            column = QVBoxLayout()
            column.addWidget(QLabel(title))
            column.addWidget(label)
            images.addLayout(column)

        self.ai_btn = QPushButton("Détourage automatique (IA)")
        self.ai_btn.setToolTip("Isole la personne quel que soit le décor (hors-ligne)")
        self.ai_btn.clicked.connect(self.run_ai)
        self.plain_btn = QPushButton("Fond uni")
        self.plain_btn.setToolTip("Photo prise devant un mur ou un drap de couleur unie")
        self.plain_btn.clicked.connect(self.run_plain)
        self.keep_btn = QPushButton("Garder tel quel")
        self.keep_btn.setToolTip("La photo est déjà un PNG transparent, ou le fond convient")
        self.keep_btn.clicked.connect(self.keep_original)
        self.tolerance = QSlider(Qt.Orientation.Horizontal)
        self.tolerance.setRange(5, 120)
        self.tolerance.setValue(40)
        self.tolerance.setToolTip("Fond uni : écart de couleur effacé")
        self.tolerance.sliderReleased.connect(self.run_plain)
        tools = QHBoxLayout()
        tools.addWidget(self.ai_btn)
        tools.addWidget(self.plain_btn)
        tools.addWidget(QLabel("Tolérance"))
        tools.addWidget(self.tolerance)
        tools.addWidget(self.keep_btn)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setVisible(False)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Enregistrer")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(images)
        layout.addLayout(tools)
        layout.addWidget(self.status)
        layout.addWidget(self.progress)
        layout.addWidget(self.buttons)

        if not br.ai_available():
            self.ai_btn.setEnabled(False)
            self.status.setText("Détourage IA indisponible sur ce poste : utilisez « Fond uni ».")
        elif self._original.mode == "RGB":
            self.run_ai()

    @property
    def result(self):
        return self._result

    def _show(self, label: QLabel, image, checker: bool = True) -> None:
        canvas = _checkerboard(PREVIEW, PREVIEW) if checker else QPixmap(PREVIEW, PREVIEW)
        if not checker:
            canvas.fill(QColor(30, 30, 30))
        picture = QPixmap.fromImage(_pil_to_qimage(image)).scaled(
            PREVIEW, PREVIEW, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        painter = QPainter(canvas)
        painter.drawPixmap((PREVIEW - picture.width()) // 2,
                           (PREVIEW - picture.height()) // 2, picture)
        painter.end()
        label.setPixmap(canvas)

    def _set_busy(self, busy: bool, text: str = "") -> None:
        for button in (self.ai_btn, self.plain_btn, self.keep_btn):
            button.setEnabled(not busy)
        if not busy and not br.ai_available():
            self.ai_btn.setEnabled(False)
        self.status.setText(text)

    # ── Méthodes ─────────────────────────────────────────────────────

    def run_ai(self) -> None:
        if br.model_path() is None:
            answer = QMessageBox.question(
                self, "Détourage IA",
                "Le modèle de détourage (44 Mo) doit être téléchargé une seule fois "
                "(connexion Internet requise). Télécharger maintenant ?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._set_busy(True, "Détourage en cours…")
        original = self._original

        def work() -> None:
            try:
                if br.model_path() is None:
                    br.download_model(lambda d, t: self._relay.progress.emit(d, t))
                self._relay.done.emit(br.remove_background(original, "ai"), "")
            except Exception as exc:
                log.exception("Détourage IA impossible")
                self._relay.done.emit(None, str(exc) or exc.__class__.__name__)

        threading.Thread(target=work, name="pastor-cutout", daemon=True).start()

    def run_plain(self) -> None:
        self._set_busy(True, "Effacement du fond uni…")
        try:
            result = br.remove_background(self._original, "plain", self.tolerance.value())
        except Exception as exc:
            self._on_done(None, str(exc))
            return
        self._on_done(result, "")

    def keep_original(self) -> None:
        self._on_done(self._original.convert("RGBA"), "")

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setVisible(True)
        self.progress.setValue(int(done * 100 / max(1, total)))
        self.status.setText("Téléchargement du modèle de détourage…")

    def _on_done(self, image, error: str) -> None:
        self.progress.setVisible(False)
        if error or image is None:
            self._set_busy(False, f"Détourage impossible : {error}")
            return
        self._result = image
        self._show(self.after, image)
        self._set_busy(False, "Vérifiez le résultat, puis enregistrez.")
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(True)

    def _save(self) -> None:
        if self._result is None:
            return
        self._target.parent.mkdir(parents=True, exist_ok=True)
        self._result.save(self._target)
        self.accept()
