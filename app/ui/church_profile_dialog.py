from __future__ import annotations

"""Profil de l'église (Réglages) et création d'images de citations."""

import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.obs_output_settings_dialog import DIALOG_STYLE, ColorPickerButton
from app.ui.setting_cards import PageHeader, SettingSection
from app.utils.church_graphics import FORMATS, ChurchProfile, render_quote, render_welcome
from app.utils.fonts import get_available_fonts


def _to_pixmap(image) -> QPixmap:
    rgb = image.convert("RGB")
    data = rgb.tobytes()
    qimage = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimage.copy())


def _hex(color: str) -> str:
    from app.utils.church_graphics import _parse_color

    rgb = _parse_color(color) or (0, 0, 0)
    return "#{:02X}{:02X}{:02X}".format(*rgb)


class ChurchProfileDialog(QDialog):
    """Nom, devise, logo, couleurs : écran d'accueil et images de citations."""

    profileChanged = Signal(ChurchProfile)
    welcomeRequested = Signal()  # projeter l'écran d'accueil
    quoteRequested = Signal()  # créer une image de citation

    def __init__(self, profile: ChurchProfile, parent=None, embedded: bool = False,
                 logo_folder: Path | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Profil de l'église")
        self.setStyleSheet(DIALOG_STYLE)
        self.resize(640, 820)
        self._profile = (profile or ChurchProfile()).sanitized()
        self._logo_folder = logo_folder

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setSpacing(14)
        layout.addWidget(PageHeader(
            "Profil de l'église",
            "Nom, devise, logo et couleurs : écran d'accueil et images à partager.",
        ))
        if embedded:
            layout.setContentsMargins(16, 16, 16, 16)
            main_layout.addWidget(content)
        else:
            layout.setContentsMargins(24, 20, 24, 16)
            scroll = QScrollArea(self)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidget(content)
            main_layout.addWidget(scroll, 1)

        self.preview = QLabel()
        self.preview.setMinimumHeight(200)
        self.preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.preview)

        identity = SettingSection("Identité", "church.svg")
        self.name = QLineEdit(self._profile.name)
        self.name.setPlaceholderText("Église …")
        identity.addRow("Nom de l'église", self.name)
        self.motto = QLineEdit(self._profile.motto)
        self.motto.setPlaceholderText("Devise ou verset de l'église")
        identity.addRow("Devise", self.motto)
        self.contact = QLineEdit(self._profile.contact)
        self.contact.setPlaceholderText("site, page Facebook, @compte…")
        identity.addRow("Contact", self.contact)
        logo_box = QWidget()
        logo_row = QHBoxLayout(logo_box)
        logo_row.setContentsMargins(0, 0, 0, 0)
        self.logo_label = QLabel(Path(self._profile.logo).name if self._profile.logo else "Aucun")
        browse = QPushButton("Parcourir")
        browse.clicked.connect(self._browse_logo)
        clear = QPushButton("Aucun")
        clear.clicked.connect(self._clear_logo)
        logo_row.addWidget(self.logo_label, 1)
        logo_row.addWidget(browse)
        logo_row.addWidget(clear)
        identity.addRow("Logo", logo_box, "PNG à fond transparent conseillé")
        layout.addWidget(identity)

        look = SettingSection("Couleurs et police", "palette.svg")
        self.primary = ColorPickerButton(self._profile.primary_color)
        self.accent = ColorPickerButton(self._profile.accent_color)
        self.text = ColorPickerButton(self._profile.text_color)
        look.addRow("Couleur principale (fond)", self.primary)
        look.addRow("Couleur d'accent", self.accent)
        look.addRow("Couleur du texte", self.text)
        self.font = QComboBox()
        for display, css in get_available_fonts():
            self.font.addItem(display, css)
        index = self.font.findData(self._profile.font_family)
        self.font.setCurrentIndex(max(index, 0))
        look.addRow("Police", self.font)
        layout.addWidget(look)

        use = SettingSection("Utiliser", "cast.svg")
        welcome_btn = QPushButton("Projeter l'écran d'accueil")
        welcome_btn.clicked.connect(self.welcomeRequested.emit)
        use.addRow("Avant le culte", welcome_btn, "Logo, nom et devise en plein écran")
        quote_btn = QPushButton("Créer une image…")
        quote_btn.clicked.connect(self.quoteRequested.emit)
        use.addRow(
            "Image de citation", quote_btn,
            "Aussi par clic droit sur un verset ou un paragraphe",
        )
        layout.addWidget(use)
        layout.addStretch(1)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._emit)
        for edit in (self.name, self.motto, self.contact):
            edit.textChanged.connect(self._debounce.start)
        for button in (self.primary, self.accent, self.text):
            button.colorChanged.connect(self._debounce.start)
        self.font.currentIndexChanged.connect(self._debounce.start)
        self._render_preview()

    def read_profile(self) -> ChurchProfile:
        return ChurchProfile(
            name=self.name.text(), motto=self.motto.text(), logo=self._profile.logo,
            primary_color=_hex(self.primary.color()), accent_color=_hex(self.accent.color()),
            text_color=_hex(self.text.color()),
            font_family=str(self.font.currentData() or "Poppins"), contact=self.contact.text(),
        ).sanitized()

    def _emit(self) -> None:
        self._profile = self.read_profile()
        self._render_preview()
        self.profileChanged.emit(self._profile)

    def _render_preview(self) -> None:
        image = render_welcome(self.read_profile(), 960, 540)
        self.preview.setPixmap(_to_pixmap(image).scaledToHeight(
            200, Qt.TransformationMode.SmoothTransformation))

    def _browse_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Logo de l'église", "", "Images (*.png *.jpg *.jpeg *.webp *.svg)")
        if not path:
            return
        source = Path(path)
        target = source
        if self._logo_folder is not None:
            self._logo_folder.mkdir(parents=True, exist_ok=True)
            target = self._logo_folder / f"logo{source.suffix.lower()}"
            shutil.copy2(source, target)
        self._profile.logo = str(target)
        self.logo_label.setText(source.name)
        self._emit()

    def _clear_logo(self) -> None:
        self._profile.logo = ""
        self.logo_label.setText("Aucun")
        self._emit()


class QuoteImageDialog(QDialog):
    """Verset ou paragraphe → image PNG à partager (WhatsApp, Facebook…)."""

    def __init__(self, profile: ChurchProfile, reference: str = "", text: str = "",
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Image de citation")
        self.setStyleSheet(DIALOG_STYLE)
        self.resize(900, 620)
        self._profile = profile

        self.text = QPlainTextEdit(text)
        self.reference = QLineEdit(reference)
        self.reference.setPlaceholderText("Jean 3:16")
        self.format = QComboBox()
        for key, (label, _w, _h) in FORMATS.items():
            self.format.addItem(label, key)
        form = QVBoxLayout()
        form.addWidget(QLabel("Texte"))
        form.addWidget(self.text, 1)
        form.addWidget(QLabel("Référence"))
        form.addWidget(self.reference)
        form.addWidget(QLabel("Format"))
        form.addWidget(self.format)
        if not profile.name:
            hint = QLabel("Astuce : renseignez le profil de l'église (Réglages) pour "
                          "ajouter son nom et son logo.")
            hint.setWordWrap(True)
            form.addWidget(hint)

        self.preview = QLabel()
        self.preview.setMinimumSize(420, 420)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body = QHBoxLayout()
        body.addLayout(form, 1)
        body.addWidget(self.preview, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        save = buttons.addButton("Enregistrer l'image…", QDialogButtonBox.ButtonRole.AcceptRole)
        save.clicked.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(body, 1)
        layout.addWidget(buttons)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._render)
        self.text.textChanged.connect(self._debounce.start)
        self.reference.textChanged.connect(self._debounce.start)
        self.format.currentIndexChanged.connect(self._render)
        self._render()

    def image(self):
        return render_quote(
            self._profile, self.text.toPlainText().strip(), self.reference.text().strip(),
            str(self.format.currentData() or "square"),
        )

    def _render(self) -> None:
        pixmap = _to_pixmap(self.image())
        self.preview.setPixmap(pixmap.scaled(
            420, 420, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def _save(self) -> None:
        from app.utils.montage_export import _slug

        default = f"{_slug(self.reference.text() or 'citation')}.png"
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer l'image", default, "PNG (*.png)")
        if not path:
            return
        self.image().convert("RGB").save(path)
        QMessageBox.information(self, "Image de citation", f"Image enregistrée :\n{path}")
