from __future__ import annotations

"""Profil de l'église (Réglages) et création d'images de citations."""

import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.ui.obs_output_settings_dialog import DIALOG_STYLE, ColorPickerButton
from app.ui.setting_cards import PageHeader, SettingSection
from app.utils.church_graphics import (
    FORMATS,
    SOCIAL_PLATFORMS,
    ChurchProfile,
    render_quote,
    render_pastor,
    render_socials,
    render_welcome,
    social_badge,
)
from app.utils.fonts import get_available_fonts


def _to_pixmap(image) -> QPixmap:
    rgb = image.convert("RGB")
    data = rgb.tobytes()
    qimage = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimage.copy())


def _to_pixmap_rgba(image) -> QPixmap:
    """Image PIL RGBA → QPixmap (transparence conservée)."""
    rgba = image.convert("RGBA")
    data = rgba.tobytes()
    qimage = QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimage.copy())


def _hex(color: str) -> str:
    from app.utils.church_graphics import _parse_color

    rgb = _parse_color(color) or (0, 0, 0)
    return "#{:02X}{:02X}{:02X}".format(*rgb)


class ChurchProfileDialog(QDialog):
    """Identité, réseaux sociaux et personnalisation des visuels de l'église."""

    profileChanged = Signal(ChurchProfile)
    welcomeRequested = Signal()  # projeter l'écran d'accueil
    socialsRequested = Signal()  # projeter l'écran « Réseaux sociaux »
    pastorRequested = Signal()  # projeter l'écran du prédicateur
    quoteRequested = Signal()  # créer une image de citation

    def __init__(self, profile: ChurchProfile, parent=None, embedded: bool = False,
                 logo_folder: Path | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Profil de l'église")
        self.setStyleSheet(DIALOG_STYLE)
        self.resize(660, 900)
        self._profile = (profile or ChurchProfile()).sanitized()
        self._logo_folder = logo_folder
        self._logo = self._profile.logo
        self._background_image = self._profile.background_image

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setSpacing(14)
        layout.addWidget(PageHeader(
            "Profil de l'église",
            "Identité, réseaux sociaux et personnalisation de l'écran d'accueil et des images.",
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

        # ── Aperçu ──
        preview_section = SettingSection("Aperçu", "eye.svg")
        self.preview_kind = QComboBox()
        self.preview_kind.addItem("Écran d'accueil", "welcome")
        self.preview_kind.addItem("Écran « Réseaux sociaux »", "socials")
        self.preview_kind.addItem("Écran du prédicateur", "pastor")
        self.preview_kind.addItem("Image de citation", "quote")
        self.preview_kind.currentIndexChanged.connect(self._render_preview)
        preview_section.addRow("Afficher", self.preview_kind)
        self.preview = QLabel()
        self.preview.setMinimumHeight(220)
        self.preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_section.addWidget(self.preview)
        layout.addWidget(preview_section)

        # ── Identité ──
        identity = SettingSection("Identité", "church.svg")
        self.name = QLineEdit(self._profile.name)
        self.name.setPlaceholderText("Église …")
        identity.addRow("Nom de l'église", self.name)
        self.welcome_title = QLineEdit(self._profile.welcome_title)
        self.welcome_title.setPlaceholderText("Bienvenue")
        identity.addRow("Titre d'accueil", self.welcome_title, "Au-dessus du logo (vide = aucun)")
        self.motto = QLineEdit(self._profile.motto)
        self.motto.setPlaceholderText("Devise ou verset de l'église")
        identity.addRow("Devise", self.motto)
        self.service_times = QPlainTextEdit(self._profile.service_times)
        self.service_times.setPlaceholderText(
            "Dimanche 9h30 · Culte d'adoration\nMercredi 17h00 · Étude biblique"
        )
        self.service_times.setFixedHeight(80)
        identity.addRow("Horaires des cultes", self.service_times, "Une ligne par rendez-vous")
        self.contact = QLineEdit(self._profile.contact)
        self.contact.setPlaceholderText("Adresse, quartier, autre contact…")
        identity.addRow("Autre information", self.contact)
        logo_box = QWidget()
        logo_row = QHBoxLayout(logo_box)
        logo_row.setContentsMargins(0, 0, 0, 0)
        self.logo_label = QLabel(Path(self._logo).name if self._logo else "Aucun")
        browse = QPushButton("Parcourir")
        browse.clicked.connect(self._browse_logo)
        clear = QPushButton("Aucun")
        clear.clicked.connect(self._clear_logo)
        logo_row.addWidget(self.logo_label, 1)
        logo_row.addWidget(browse)
        logo_row.addWidget(clear)
        identity.addRow("Logo", logo_box, "PNG à fond transparent conseillé")
        layout.addWidget(identity)

        # ── Pasteur ──
        self._pastor_photo = self._profile.pastor_photo
        pastor = SettingSection("Pasteur", "users.svg")
        self.pastor_title = QComboBox()
        self.pastor_title.setEditable(True)
        for title in ("Pasteur", "Révérend", "Apôtre", "Évêque", "Prophète",
                      "Évangéliste", "Docteur", "Frère", "Diacre"):
            self.pastor_title.addItem(title)
        self.pastor_title.setCurrentText(self._profile.pastor_title)
        pastor.addRow("Titre", self.pastor_title, "Choisissez ou tapez le vôtre")
        self.pastor_name = QLineEdit(self._profile.pastor_name)
        self.pastor_name.setPlaceholderText("Prénom et nom")
        pastor.addRow("Nom du pasteur", self.pastor_name)
        photo_box = QWidget()
        photo_box.setStyleSheet("background: transparent;")
        photo_row = QHBoxLayout(photo_box)
        photo_row.setContentsMargins(0, 0, 0, 0)
        self.pastor_thumb = QLabel()
        self.pastor_thumb.setFixedSize(56, 56)
        self.pastor_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        choose = QPushButton("Choisir une photo…")
        choose.clicked.connect(self._choose_pastor_photo)
        remove = QPushButton("Retirer")
        remove.clicked.connect(self._clear_pastor_photo)
        photo_row.addWidget(self.pastor_thumb)
        photo_row.addWidget(choose)
        photo_row.addWidget(remove)
        pastor.addRow("Photo sans arrière-plan", photo_box,
                      "L'arrière-plan est retiré automatiquement")
        self.pastor_message = QLineEdit(self._profile.pastor_message)
        self.pastor_message.setPlaceholderText("Titre du message du jour (facultatif)")
        pastor.addRow("Message du jour", self.pastor_message, "Affiché sur l'écran du prédicateur")
        self.show_pastor_welcome = QCheckBox("Pasteur sur l'écran d'accueil")
        self.show_pastor_welcome.setChecked(self._profile.show_pastor_welcome)
        pastor.addWidget(self.show_pastor_welcome)
        self.show_pastor_quotes = QCheckBox("Signature et photo du pasteur sur les citations")
        self.show_pastor_quotes.setChecked(self._profile.show_pastor_quotes)
        pastor.addWidget(self.show_pastor_quotes)
        layout.addWidget(pastor)
        self._refresh_pastor_thumb()

        # ── Réseaux sociaux ──
        socials = SettingSection("Réseaux sociaux et contacts", "globe.svg")
        self.social_edits: dict[str, QLineEdit] = {}
        for platform in SOCIAL_PLATFORMS:
            edit = QLineEdit(self._profile.socials.get(platform.key, ""))
            edit.setPlaceholderText(platform.placeholder)
            edit.setMinimumWidth(220)
            # Logo officiel du réseau devant le champ.
            field_box = QWidget()
            field_box.setStyleSheet("background: transparent;")
            field_row = QHBoxLayout(field_box)
            field_row.setContentsMargins(0, 0, 0, 0)
            field_row.setSpacing(8)
            logo = QLabel()
            badge = social_badge(platform.key, 26)
            if badge is not None:
                logo.setPixmap(_to_pixmap_rgba(badge))
            logo.setFixedSize(26, 26)
            field_row.addWidget(logo)
            field_row.addWidget(edit, 1)
            socials.addRow(platform.label, field_box)
            self.social_edits[platform.key] = edit
        self.qr_target = QComboBox()
        self.qr_target.addItem("Aucun QR code", "")
        for platform in SOCIAL_PLATFORMS:
            self.qr_target.addItem(f"QR code vers {platform.label}", platform.key)
        index = self.qr_target.findData(self._profile.qr_target)
        self.qr_target.setCurrentIndex(max(index, 0))
        socials.addRow(
            "QR code", self.qr_target,
            "Affiché sur l'écran d'accueil et l'écran « Réseaux sociaux » : à scanner",
        )
        self.show_socials_welcome = QCheckBox("Réseaux sur l'écran d'accueil")
        self.show_socials_welcome.setChecked(self._profile.show_socials_welcome)
        socials.addWidget(self.show_socials_welcome)
        self.show_socials_quotes = QCheckBox("Réseaux sur les images de citations")
        self.show_socials_quotes.setChecked(self._profile.show_socials_quotes)
        socials.addWidget(self.show_socials_quotes)
        layout.addWidget(socials)

        # ── Personnalisation ──
        look = SettingSection("Personnalisation", "palette.svg")
        self.background_mode = QComboBox()
        self.background_mode.addItem("Dégradé de la couleur principale", "gradient")
        self.background_mode.addItem("Couleur unie", "solid")
        self.background_mode.addItem("Image de fond", "image")
        self.background_mode.setCurrentIndex(
            max(0, self.background_mode.findData(self._profile.background_mode))
        )
        look.addRow("Fond", self.background_mode)
        bg_box = QWidget()
        bg_row = QHBoxLayout(bg_box)
        bg_row.setContentsMargins(0, 0, 0, 0)
        self.background_label = QLabel(
            Path(self._background_image).name if self._background_image else "Aucune"
        )
        bg_browse = QPushButton("Parcourir")
        bg_browse.clicked.connect(self._browse_background)
        bg_row.addWidget(self.background_label, 1)
        bg_row.addWidget(bg_browse)
        look.addRow("Image de fond", bg_box, "Photo de l'église, de la chorale…")
        self.background_dim = QSpinBox()
        self.background_dim.setRange(0, 85)
        self.background_dim.setSuffix(" %")
        self.background_dim.setValue(self._profile.background_dim)
        look.addRow("Assombrir l'image", self.background_dim, "Rend le texte lisible sur la photo")
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
        self.quote_style = QComboBox()
        self.quote_style.addItem("Classique (grand guillemet)", "classic")
        self.quote_style.addItem("Minimal", "minimal")
        self.quote_style.addItem("Encadré", "framed")
        self.quote_style.setCurrentIndex(max(0, self.quote_style.findData(self._profile.quote_style)))
        look.addRow("Style des citations", self.quote_style)
        layout.addWidget(look)

        # ── Utiliser ──
        use = SettingSection("Utiliser", "cast.svg")
        welcome_btn = QPushButton("Projeter")
        welcome_btn.clicked.connect(self.welcomeRequested.emit)
        use.addRow("Écran d'accueil", welcome_btn, "Avant le culte · Ctrl+Shift+W")
        pastor_btn = QPushButton("Projeter")
        pastor_btn.clicked.connect(self.pastorRequested.emit)
        use.addRow("Écran du prédicateur", pastor_btn,
                   "Photo et nom du pasteur avant la prédication · Ctrl+Shift+P")
        socials_btn = QPushButton("Projeter")
        socials_btn.clicked.connect(self.socialsRequested.emit)
        use.addRow("Écran « Réseaux sociaux »", socials_btn, "En fin de culte · Ctrl+Shift+R")
        quote_btn = QPushButton("Créer une image…")
        quote_btn.clicked.connect(self.quoteRequested.emit)
        use.addRow("Image de citation", quote_btn,
                   "Aussi par clic droit sur un verset ou un paragraphe")
        export_btn = QPushButton("Enregistrer…")
        export_btn.clicked.connect(self._export_visuals)
        use.addRow("Visuels en PNG", export_btn,
                   "Accueil et réseaux sociaux, à publier ou imprimer")
        layout.addWidget(use)
        layout.addStretch(1)

        # Champs assez larges pour lire une adresse entière, début visible.
        for edit in (self.name, self.welcome_title, self.motto, self.contact,
                     self.pastor_name, self.pastor_message, *self.social_edits.values()):
            edit.setMinimumWidth(260)
            edit.setCursorPosition(0)
        self.service_times.setMinimumWidth(260)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._emit)
        for edit in (self.name, self.welcome_title, self.motto, self.contact,
                     self.pastor_name, self.pastor_message, *self.social_edits.values()):
            edit.textChanged.connect(self._debounce.start)
        self.pastor_title.currentTextChanged.connect(self._debounce.start)
        self.service_times.textChanged.connect(self._debounce.start)
        for button in (self.primary, self.accent, self.text):
            button.colorChanged.connect(self._debounce.start)
        for combo in (self.font, self.qr_target, self.background_mode, self.quote_style):
            combo.currentIndexChanged.connect(self._debounce.start)
        self.background_dim.valueChanged.connect(self._debounce.start)
        for box in (self.show_socials_welcome, self.show_socials_quotes,
                    self.show_pastor_welcome, self.show_pastor_quotes):
            box.toggled.connect(self._debounce.start)
        self._render_preview()

    def read_profile(self) -> ChurchProfile:
        return ChurchProfile(
            name=self.name.text(),
            motto=self.motto.text(),
            logo=self._logo,
            contact=self.contact.text(),
            socials={k: e.text() for k, e in self.social_edits.items()},
            primary_color=_hex(self.primary.color()),
            accent_color=_hex(self.accent.color()),
            text_color=_hex(self.text.color()),
            font_family=str(self.font.currentData() or "Poppins"),
            welcome_title=self.welcome_title.text(),
            service_times=self.service_times.toPlainText(),
            background_mode=str(self.background_mode.currentData() or "gradient"),
            background_image=self._background_image,
            background_dim=self.background_dim.value(),
            show_socials_welcome=self.show_socials_welcome.isChecked(),
            show_socials_quotes=self.show_socials_quotes.isChecked(),
            qr_target=str(self.qr_target.currentData() or ""),
            quote_style=str(self.quote_style.currentData() or "classic"),
            pastor_name=self.pastor_name.text(),
            pastor_title=self.pastor_title.currentText(),
            pastor_photo=self._pastor_photo,
            pastor_message=self.pastor_message.text(),
            show_pastor_welcome=self.show_pastor_welcome.isChecked(),
            show_pastor_quotes=self.show_pastor_quotes.isChecked(),
        ).sanitized()

    def _emit(self) -> None:
        self._profile = self.read_profile()
        self._render_preview()
        self.profileChanged.emit(self._profile)

    def _render_preview(self, *_args) -> None:
        profile = self.read_profile()
        kind = self.preview_kind.currentData()
        if kind == "socials":
            image = render_socials(profile, 960, 540)
        elif kind == "pastor":
            image = render_pastor(profile, 960, 540, subtitle=profile.pastor_message)
        elif kind == "quote":
            image = render_quote(
                profile, "Car Dieu a tant aimé le monde qu'il a donné son Fils unique.",
                "Jean 3:16", "square",
            )
        else:
            image = render_welcome(profile, 960, 540)
        self.preview.setPixmap(_to_pixmap(image).scaledToHeight(
            220, Qt.TransformationMode.SmoothTransformation))

    def _copy_into_folder(self, source: Path, stem: str) -> Path:
        if self._logo_folder is None:
            return source
        self._logo_folder.mkdir(parents=True, exist_ok=True)
        target = self._logo_folder / f"{stem}{source.suffix.lower()}"
        shutil.copy2(source, target)
        return target

    def _browse_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Logo de l'église", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        self._logo = str(self._copy_into_folder(Path(path), "logo"))
        self.logo_label.setText(Path(path).name)
        self._emit()

    def _clear_logo(self) -> None:
        self._logo = ""
        self.logo_label.setText("Aucun")
        self._emit()

    def _refresh_pastor_thumb(self) -> None:
        path = Path(self._pastor_photo) if self._pastor_photo else None
        if path is not None and path.is_file():
            pixmap = QPixmap(str(path)).scaled(
                56, 56, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self.pastor_thumb.setPixmap(pixmap)
            self.pastor_thumb.setToolTip(str(path))
        else:
            self.pastor_thumb.clear()
            self.pastor_thumb.setText("—")

    def _choose_pastor_photo(self) -> None:
        from app.ui.pastor_photo_dialog import PastorPhotoDialog

        path, _ = QFileDialog.getOpenFileName(
            self, "Photo du pasteur", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        folder = self._logo_folder or Path(path).parent
        import time

        target = folder / f"pasteur-{int(time.time())}.png"
        try:
            dialog = PastorPhotoDialog(Path(path), target, self)
        except Exception as exc:
            QMessageBox.warning(self, "Photo du pasteur", f"Image illisible : {exc}")
            return
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_pastor_photo(str(target))

    def set_pastor_photo(self, path: str) -> None:
        self._pastor_photo = str(path or "")
        self._refresh_pastor_thumb()
        if self._pastor_photo:
            self.preview_kind.setCurrentIndex(self.preview_kind.findData("pastor"))
        self._emit()

    def _clear_pastor_photo(self) -> None:
        self.set_pastor_photo("")

    def _browse_background(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Image de fond", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        self._background_image = str(self._copy_into_folder(Path(path), "fond"))
        self.background_label.setText(Path(path).name)
        self.background_mode.setCurrentIndex(self.background_mode.findData("image"))
        self._emit()

    def _export_visuals(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Dossier des visuels")
        if not folder:
            return
        written = export_visuals(self.read_profile(), Path(folder))
        QMessageBox.information(
            self, "Visuels", "Enregistrés :\n" + "\n".join(p.name for p in written)
        )


def export_visuals(profile: ChurchProfile, folder: Path) -> list[Path]:
    """Écran d'accueil et « Réseaux sociaux » en PNG (paysage + carré)."""
    folder.mkdir(parents=True, exist_ok=True)
    outputs = [
        ("accueil.png", render_welcome(profile, 1920, 1080)),
        ("reseaux-sociaux.png", render_socials(profile, 1920, 1080)),
        ("reseaux-sociaux-carre.png", render_socials(profile, 1080, 1080)),
    ]
    written = []
    for name, image in outputs:
        path = folder / name
        image.convert("RGB").save(path)
        written.append(path)
    return written


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
