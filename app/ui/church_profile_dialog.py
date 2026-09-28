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
    QInputDialog,
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
    BUILTIN_THUMBNAIL_MODELS,
    THUMBNAIL_LAYOUTS,
    ThumbnailSpec,
    render_quote,
    render_speaker,
    render_socials,
    render_welcome,
    render_youtube_thumbnail,
    sanitize_thumbnail_models,
    save_thumbnail,
    social_badge,
    speaker_info,
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
    thumbnailRequested = Signal()  # créer une miniature YouTube

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
        self.preview_kind.addItem("Écran de l'orateur du jour", "pastor")
        self.preview_kind.addItem("Image de citation", "quote")
        self.preview_kind.addItem("Miniature YouTube", "thumbnail")
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

        # ── Pasteur (visage de l'église, sur toutes les publications) ──
        self._photos = {"pastor": self._profile.pastor_photo,
                        "speaker": self._profile.speaker_photo}
        self._thumbs: dict[str, QLabel] = {}
        pastor = SettingSection("Pasteur", "users.svg")
        self.pastor_title = self._title_combo(self._profile.pastor_title)
        pastor.addRow("Titre", self.pastor_title, "Choisissez ou tapez le vôtre")
        self.pastor_name = QLineEdit(self._profile.pastor_name)
        self.pastor_name.setPlaceholderText("Prénom et nom")
        pastor.addRow("Nom du pasteur", self.pastor_name)
        pastor.addRow(
            "Photo (PNG sans arrière-plan)", self._photo_row("pastor"),
            "Présente sur l'accueil, les réseaux sociaux et chaque citation",
        )
        layout.addWidget(pastor)

        # ── Orateur du jour ──
        speaker = SettingSection("Orateur du jour", "mic.svg")
        self.speaker_title = self._title_combo(self._profile.speaker_title)
        speaker.addRow("Titre", self.speaker_title)
        self.speaker_name = QLineEdit(self._profile.speaker_name)
        self.speaker_name.setPlaceholderText("Vide = le pasteur prêche")
        speaker.addRow("Nom de l'orateur", self.speaker_name)
        speaker.addRow("Photo (PNG sans arrière-plan)", self._photo_row("speaker"))
        self.speaker_message = QLineEdit(self._profile.speaker_message)
        self.speaker_message.setPlaceholderText("Titre du message (facultatif)")
        speaker.addRow("Message du jour", self.speaker_message)
        pastor_preaches = QPushButton("Le pasteur prêche")
        pastor_preaches.setToolTip("Efface l'orateur invité (le message du jour est gardé)")
        pastor_preaches.clicked.connect(self._pastor_preaches)
        speaker.addRow("Pas d'invité aujourd'hui", pastor_preaches)
        self.speaker_on_slides = QComboBox()
        self.speaker_on_slides.addItem("Tous les slides de texte", "all")
        self.speaker_on_slides.addItem("Prédications seulement", "sermon")
        self.speaker_on_slides.addItem("Non", "off")
        self.speaker_on_slides.setCurrentIndex(
            max(0, self.speaker_on_slides.findData(self._profile.speaker_on_slides)))
        speaker.addRow(
            "Sur les slides de projection", self.speaker_on_slides,
            "Photo et nom de l'orateur au pied des slides (sans invité : le pasteur)",
        )
        self.speaker_slides_side = QComboBox()
        self.speaker_slides_side.addItem("À droite", "right")
        self.speaker_slides_side.addItem("À gauche", "left")
        self.speaker_slides_side.setCurrentIndex(
            max(0, self.speaker_slides_side.findData(self._profile.speaker_slides_side)))
        speaker.addRow("Côté", self.speaker_slides_side, "Le texte se décale pour lui laisser la place")
        self.speaker_slides_size = QSpinBox()
        self.speaker_slides_size.setRange(10, 40)
        self.speaker_slides_size.setSuffix(" %")
        self.speaker_slides_size.setValue(self._profile.speaker_slides_size)
        speaker.addRow("Hauteur de la photo", self.speaker_slides_size, "Part de la hauteur de l'écran")
        self.speaker_on_broadcast = QComboBox()
        self.speaker_on_broadcast.addItem("Tous les textes", "all")
        self.speaker_on_broadcast.addItem("Prédications seulement", "sermon")
        self.speaker_on_broadcast.addItem("Non", "off")
        self.speaker_on_broadcast.setCurrentIndex(
            max(0, self.speaker_on_broadcast.findData(self._profile.speaker_on_broadcast)))
        speaker.addRow(
            "Sur OBS, NDI et HDMI", self.speaker_on_broadcast,
            "À côté du bandeau sur la caméra (même côté que les slides)",
        )
        self.speaker_broadcast_size = QSpinBox()
        self.speaker_broadcast_size.setRange(10, 40)
        self.speaker_broadcast_size.setSuffix(" %")
        self.speaker_broadcast_size.setValue(self._profile.speaker_broadcast_size)
        speaker.addRow("Hauteur sur OBS / HDMI", self.speaker_broadcast_size,
                       "Part de la hauteur de l'image diffusée")
        layout.addWidget(speaker)
        for key in self._photos:
            self._refresh_thumb(key)

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
        use.addRow("Écran de l'orateur du jour", pastor_btn,
                   "Photo, nom et message avant la prédication · Ctrl+Shift+P")
        socials_btn = QPushButton("Projeter")
        socials_btn.clicked.connect(self.socialsRequested.emit)
        use.addRow("Écran « Réseaux sociaux »", socials_btn, "En fin de culte · Ctrl+Shift+R")
        quote_btn = QPushButton("Créer une image…")
        quote_btn.clicked.connect(self.quoteRequested.emit)
        use.addRow("Image de citation", quote_btn,
                   "Aussi par clic droit sur un verset ou un paragraphe")
        thumb_btn = QPushButton("Créer une miniature…")
        thumb_btn.clicked.connect(self.thumbnailRequested.emit)
        use.addRow("Miniature YouTube", thumb_btn,
                   "Titre, orateur et date en 1280×720 · Ctrl+Shift+Y")
        export_btn = QPushButton("Enregistrer…")
        export_btn.clicked.connect(self._export_visuals)
        use.addRow("Visuels en PNG", export_btn,
                   "Accueil et réseaux sociaux, à publier ou imprimer")
        layout.addWidget(use)
        layout.addStretch(1)

        # Champs assez larges pour lire une adresse entière, début visible.
        for edit in (self.name, self.welcome_title, self.motto, self.contact,
                     self.pastor_name, self.speaker_name, self.speaker_message,
                     *self.social_edits.values()):
            edit.setMinimumWidth(260)
            edit.setCursorPosition(0)
        self.service_times.setMinimumWidth(260)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._emit)
        for edit in (self.name, self.welcome_title, self.motto, self.contact,
                     self.pastor_name, self.speaker_name, self.speaker_message,
                     *self.social_edits.values()):
            edit.textChanged.connect(self._debounce.start)
        self.pastor_title.currentTextChanged.connect(self._debounce.start)
        self.speaker_title.currentTextChanged.connect(self._debounce.start)
        self.service_times.textChanged.connect(self._debounce.start)
        for button in (self.primary, self.accent, self.text):
            button.colorChanged.connect(self._debounce.start)
        for combo in (self.font, self.qr_target, self.background_mode, self.quote_style,
                      self.speaker_on_slides, self.speaker_slides_side,
                      self.speaker_on_broadcast):
            combo.currentIndexChanged.connect(self._debounce.start)
        self.background_dim.valueChanged.connect(self._debounce.start)
        self.speaker_slides_size.valueChanged.connect(self._debounce.start)
        self.speaker_broadcast_size.valueChanged.connect(self._debounce.start)
        for box in (self.show_socials_welcome, self.show_socials_quotes):
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
            pastor_photo=self._photos["pastor"],
            speaker_name=self.speaker_name.text(),
            speaker_title=self.speaker_title.currentText(),
            speaker_photo=self._photos["speaker"],
            speaker_message=self.speaker_message.text(),
            speaker_on_slides=str(self.speaker_on_slides.currentData() or "all"),
            speaker_slides_side=str(self.speaker_slides_side.currentData() or "right"),
            speaker_slides_size=self.speaker_slides_size.value(),
            speaker_on_broadcast=str(self.speaker_on_broadcast.currentData() or "all"),
            speaker_broadcast_size=self.speaker_broadcast_size.value(),
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
            image = render_speaker(profile, 960, 540)
        elif kind == "quote":
            image = render_quote(
                profile, "Car Dieu a tant aimé le monde qu'il a donné son Fils unique.",
                "Jean 3:16", "square",
            )
        elif kind == "thumbnail":
            image = render_youtube_thumbnail(profile, ThumbnailSpec(
                title="Le *vrai* repos de l'âme", date=french_date(), reference="Matthieu 11:28",
            ))
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

    # ── Photos (pasteur, orateur) : importées déjà sans arrière-plan ──

    @staticmethod
    def _title_combo(current: str) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        for title in ("Pasteur", "Révérend", "Apôtre", "Évêque", "Prophète",
                      "Évangéliste", "Docteur", "Frère", "Sœur", "Diacre", "Ancien"):
            combo.addItem(title)
        combo.setCurrentText(current)
        return combo

    def _photo_row(self, key: str) -> QWidget:
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        thumb = QLabel()
        thumb.setFixedSize(56, 56)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumbs[key] = thumb
        choose = QPushButton("Importer…")
        choose.clicked.connect(lambda _c=False, k=key: self._import_photo(k))
        remove = QPushButton("Retirer")
        remove.clicked.connect(lambda _c=False, k=key: self.set_photo(k, ""))
        row.addWidget(thumb)
        row.addWidget(choose)
        row.addWidget(remove)
        return box

    def _refresh_thumb(self, key: str) -> None:
        thumb = self._thumbs[key]
        path = Path(self._photos[key]) if self._photos[key] else None
        if path is not None and path.is_file():
            thumb.setPixmap(QPixmap(str(path)).scaled(
                56, 56, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            thumb.setToolTip(str(path))
        else:
            thumb.clear()
            thumb.setText("—")

    def _import_photo(self, key: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Photo sans arrière-plan", "", "Images PNG ou WebP transparentes (*.png *.webp)")
        if not path:
            return
        if not has_transparency(Path(path)):
            answer = QMessageBox.question(
                self, "Photo avec arrière-plan",
                "Cette photo n'a pas de fond transparent : elle apparaîtra dans un "
                "rectangle. Importez de préférence un PNG sans arrière-plan.\n\n"
                "L'utiliser quand même ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        import time

        target = self._copy_into_folder(Path(path), f"{key}-{int(time.time())}")
        self.set_photo(key, str(target))

    def set_photo(self, key: str, path: str) -> None:
        self._photos[key] = str(path or "")
        self._refresh_thumb(key)
        if self._photos[key]:
            kind = "pastor" if key == "speaker" else "welcome"
            self.preview_kind.setCurrentIndex(self.preview_kind.findData(kind))
        self._emit()

    def set_pastor_photo(self, path: str) -> None:
        self.set_photo("pastor", path)

    def _pastor_preaches(self) -> None:
        self.speaker_name.clear()
        self.speaker_title.setCurrentText("")
        self.set_photo("speaker", "")

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
    """Accueil, « Réseaux sociaux » (paysage + carré) et orateur du jour en PNG."""
    folder.mkdir(parents=True, exist_ok=True)
    outputs = [
        ("accueil.png", render_welcome(profile, 1920, 1080)),
        ("reseaux-sociaux.png", render_socials(profile, 1920, 1080)),
        ("reseaux-sociaux-carre.png", render_socials(profile, 1080, 1080)),
        ("orateur-du-jour.png", render_speaker(profile, 1920, 1080)),
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


_MONTHS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
           "septembre", "octobre", "novembre", "décembre")
_DAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


def french_date(day=None) -> str:
    """« Dimanche 28 septembre 2026 »."""
    from datetime import date

    day = day or date.today()
    return f"{_DAYS[day.weekday()].capitalize()} {day.day} {_MONTHS[day.month - 1]} {day.year}"


class ThumbnailDialog(QDialog):
    """Miniature YouTube (1280×720) aux couleurs de l'église, avec l'orateur.

    Modèles : ceux fournis avec Project-On et ceux enregistrés par l'église
    (mise en page, bandeau, fond, couleur, côté de la photo…), réutilisables
    d'un culte à l'autre. ``modelsChanged`` porte la liste des modèles de
    l'église à enregistrer dans les réglages.
    """

    modelsChanged = Signal(list)

    LABELS = ("Culte du dimanche", "En direct", "Enseignement", "Culte d'enseignement",
              "Culte de prière", "Veillée de prière", "Conférence", "Témoignage",
              "Culte spécial")

    def __init__(self, profile: ChurchProfile, title: str = "", reference: str = "",
                 parent=None, models: list | None = None,
                 media_folder: Path | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Miniature YouTube")
        self.setStyleSheet(DIALOG_STYLE)
        self.resize(1120, 640)
        self._profile = profile
        self._background = ""
        self._accent = ""
        self._models = sanitize_thumbnail_models(models or [])
        self._media_folder = media_folder
        self._loading = False

        # ── Modèles ──
        self.model = QComboBox()
        self.model.setMinimumWidth(220)
        self.model.activated.connect(self._apply_selected_model)
        self.save_model_btn = QPushButton("Enregistrer comme modèle…")
        self.save_model_btn.clicked.connect(self._save_model)
        self.delete_model_btn = QPushButton("Supprimer")
        self.delete_model_btn.clicked.connect(self._delete_model)
        models_row = QHBoxLayout()
        models_row.addWidget(self.model, 1)
        models_row.addWidget(self.save_model_btn)
        models_row.addWidget(self.delete_model_btn)

        self.title = QPlainTextEdit(title)
        self.title.setPlaceholderText("Le *vrai* repos de l'âme")
        self.title.setMaximumHeight(80)
        self.layout_combo = QComboBox()
        for key, label in THUMBNAIL_LAYOUTS.items():
            self.layout_combo.addItem(label, key)
        self.label = QComboBox()
        self.label.setEditable(True)
        self.label.addItems(self.LABELS)
        self.label.addItem("")
        self.date = QLineEdit(french_date())
        self.reference = QLineEdit(reference)
        self.reference.setPlaceholderText("Matthieu 11:28 (facultatif)")
        self.show_speaker = QCheckBox("Afficher l'orateur du jour (photo et nom)")
        self.show_speaker.setChecked(True)
        self.side = QComboBox()
        self.side.addItem("Photo à droite", "right")
        self.side.addItem("Photo à gauche", "left")
        self.uppercase = QCheckBox("Titre en majuscules")
        self.uppercase.setChecked(True)
        self.accent_btn = ColorPickerButton(profile.accent_color or "#F0BE64")
        self.accent_btn.colorChanged.connect(self._set_accent)
        church_color = QPushButton("Couleur de l'église")
        church_color.clicked.connect(lambda: self._set_accent(""))
        accent_row = QHBoxLayout()
        accent_row.addWidget(self.accent_btn)
        accent_row.addWidget(church_color)
        accent_row.addStretch(1)
        self.background_btn = QPushButton("Choisir une image de fond…")
        self.background_btn.clicked.connect(self._browse_background)
        clear_bg = QPushButton("Fond de l'église")
        clear_bg.clicked.connect(lambda: self._set_background(""))
        background_row = QHBoxLayout()
        background_row.addWidget(self.background_btn, 1)
        background_row.addWidget(clear_bg)

        form = QVBoxLayout()
        form.addWidget(QLabel("Modèle"))
        form.addLayout(models_row)
        form.addWidget(QLabel("Titre de la prédication"))
        form.addWidget(self.title)
        hint = QLabel("Mettez un mot entre *astérisques* pour l'écrire en couleur d'accent.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9aa4b2; font-size: 11px;")
        form.addWidget(hint)
        grid = QHBoxLayout()
        left, right = QVBoxLayout(), QVBoxLayout()
        for column, rows in ((left, (("Mise en page", self.layout_combo), ("Bandeau", self.label),
                                     ("Date", self.date))),
                             (right, (("Référence biblique", self.reference),
                                      ("Photo", self.side)))):
            for text, widget in rows:
                column.addWidget(QLabel(text))
                column.addWidget(widget)
        right.addWidget(QLabel("Couleur d'accent"))
        right.addLayout(accent_row)
        grid.addLayout(left, 1)
        grid.addLayout(right, 1)
        form.addLayout(grid)
        form.addWidget(self.show_speaker)
        form.addWidget(self.uppercase)
        form.addLayout(background_row)
        speaker = " ".join(p for p in speaker_info(profile)[:2] if p)
        note = QLabel(
            f"Orateur : {speaker}" if speaker else
            "Astuce : renseignez l'orateur du jour (et sa photo sans arrière-plan) "
            "dans Réglages → Profil de l'église."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #9aa4b2; font-size: 11px;")
        form.addWidget(note)
        form.addStretch(1)

        self.preview = QLabel()
        self.preview.setMinimumSize(640, 360)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body = QHBoxLayout()
        body.addLayout(form, 2)
        body.addWidget(self.preview, 3)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        save = buttons.addButton("Enregistrer la miniature…",
                                 QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Fermer")
        save.clicked.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(body, 1)
        layout.addWidget(buttons)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._render)
        self.title.textChanged.connect(self._debounce.start)
        self.label.currentTextChanged.connect(self._debounce.start)
        self.date.textChanged.connect(self._debounce.start)
        self.reference.textChanged.connect(self._debounce.start)
        for box in (self.show_speaker, self.uppercase):
            box.toggled.connect(self._render)
        for combo in (self.side, self.layout_combo):
            combo.currentIndexChanged.connect(self._render)

        self._fill_models()
        # Dernier modèle de l'église s'il y en a, sinon le premier fourni.
        self.model.setCurrentIndex(self.model.count() - 1 if self._models else 0)
        self._apply_selected_model()

    # ── Modèles ──────────────────────────────────────────────────────

    def _fill_models(self, select: str = "") -> None:
        self.model.blockSignals(True)
        self.model.clear()
        for model in BUILTIN_THUMBNAIL_MODELS:
            self.model.addItem(model["name"], f"builtin:{model['name']}")
        if self._models:
            self.model.insertSeparator(self.model.count())
            for model in self._models:
                self.model.addItem(f"★ {model['name']}", f"church:{model['name']}")
        if select:
            index = self.model.findData(f"church:{select}")
            if index >= 0:
                self.model.setCurrentIndex(index)
        self.model.blockSignals(False)
        self._update_model_buttons()

    def _selected_model(self) -> tuple[str, dict | None]:
        data = self.model.currentData()
        if not data:
            return "", None
        kind, _sep, name = str(data).partition(":")
        source = BUILTIN_THUMBNAIL_MODELS if kind == "builtin" else self._models
        return kind, next((m for m in source if m["name"] == name), None)

    def _update_model_buttons(self) -> None:
        kind, _model = self._selected_model()
        self.delete_model_btn.setEnabled(kind == "church")

    def _apply_selected_model(self, *_args) -> None:
        _kind, model = self._selected_model()
        self._update_model_buttons()
        if model is None:
            return
        spec = self.spec().with_model(model)
        self._loading = True
        self.layout_combo.setCurrentIndex(max(0, self.layout_combo.findData(spec.layout)))
        self.label.setCurrentText(spec.label)
        self.side.setCurrentIndex(max(0, self.side.findData(spec.photo_side)))
        self.show_speaker.setChecked(spec.show_speaker)
        self.uppercase.setChecked(spec.uppercase)
        self._set_accent(spec.accent, render=False)
        self._set_background(spec.background, render=False)
        self._loading = False
        self._render()

    def models(self) -> list[dict]:
        return list(self._models)

    def _save_model(self) -> None:
        kind, current = self._selected_model()
        suggestion = current["name"] if kind == "church" and current else ""
        name, ok = QInputDialog.getText(
            self, "Enregistrer comme modèle",
            "Nom du modèle (mise en page, bandeau, fond, couleur et côté de la photo) :",
            text=suggestion,
        )
        name = name.strip()
        if not ok or not name:
            return
        spec = self.spec()
        spec.background = self._keep_background(spec.background)
        self._background = spec.background
        model = spec.model(name)
        others = [m for m in self._models if m["name"].lower() != name.lower()]
        self._models = sanitize_thumbnail_models(others + [model])
        self._fill_models(select=model["name"])
        self.modelsChanged.emit(self.models())

    def _delete_model(self) -> None:
        kind, model = self._selected_model()
        if kind != "church" or model is None:
            return
        answer = QMessageBox.question(self, "Supprimer le modèle",
                                      f"Supprimer le modèle « {model['name']} » ?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._models = [m for m in self._models if m["name"] != model["name"]]
        self._fill_models()
        self.modelsChanged.emit(self.models())

    def _keep_background(self, path: str) -> str:
        """Copie l'image de fond d'un modèle dans les données de Project-On.

        Le modèle reste utilisable même si l'image d'origine est déplacée.
        """
        if not path or self._media_folder is None:
            return path
        source = Path(path)
        try:
            folder = self._media_folder
            if source.parent.resolve() == folder.resolve():
                return path
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / source.name
            index = 1
            while target.exists() and target.read_bytes() != source.read_bytes():
                target = folder / f"{source.stem}-{index}{source.suffix}"
                index += 1
            if not target.exists():
                shutil.copy2(source, target)
            return str(target)
        except OSError:
            return path

    # ── Miniature ────────────────────────────────────────────────────

    def spec(self) -> ThumbnailSpec:
        return ThumbnailSpec(
            title=self.title.toPlainText().strip(),
            label=self.label.currentText().strip(),
            date=self.date.text().strip(),
            reference=self.reference.text().strip(),
            background=self._background,
            photo_side=str(self.side.currentData() or "right"),
            show_speaker=self.show_speaker.isChecked(),
            uppercase=self.uppercase.isChecked(),
            layout=str(self.layout_combo.currentData() or "split"),
            accent=self._accent,
        ).sanitized()

    def image(self):
        return render_youtube_thumbnail(self._profile, self.spec())

    def _render(self, *_args) -> None:
        if self._loading:
            return
        self.preview.setPixmap(_to_pixmap(self.image()).scaled(
            640, 360, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def _set_accent(self, color: str, render: bool = True) -> None:
        self._accent = _hex(color) if color else ""
        self.accent_btn.set_color(self._accent or self._profile.accent_color or "#F0BE64")
        if render:
            self._render()

    def _browse_background(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Image de fond", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self._set_background(path)

    def _set_background(self, path: str, render: bool = True) -> None:
        self._background = path if path and Path(path).is_file() else ""
        self.background_btn.setText(
            Path(self._background).name if self._background else "Choisir une image de fond…")
        if render:
            self._render()

    def _save(self) -> None:
        from app.utils.montage_export import _slug

        default = f"miniature-{_slug(self.title.toPlainText().replace('*', '') or 'culte')}.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer la miniature", default, "PNG (*.png);;JPEG (*.jpg)")
        if not path:
            return
        written = save_thumbnail(self.image(), Path(path))
        QMessageBox.information(
            self, "Miniature YouTube",
            f"Miniature enregistrée (1280×720, moins de 2 Mo) :\n{written}",
        )


def has_transparency(path: Path) -> bool:
    """Vrai si l'image a des zones transparentes (photo « sans arrière-plan »)."""
    from PIL import Image

    try:
        with Image.open(path) as image:
            if image.mode not in ("RGBA", "LA", "PA") and "transparency" not in image.info:
                return False
            alpha = image.convert("RGBA").getchannel("A")
            return alpha.getextrema()[0] < 250
    except Exception:
        return False
