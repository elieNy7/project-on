from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from app.ui.icons import app_icon
from app.ui.list_selection import select_first
from app.utils.translations import tr
from app.ui.theme import (
    Colors,
    Spacing,
    Typography,
    get_compact_button_style,
    get_input_style,
    get_list_style,
    get_menu_style,
    get_preview_text_style,
    get_splitter_style,
    item_hover_color,
    item_selection_color,
    item_separator_color,
)


# Rôles des éléments de la liste des slides.
ROLE_ID, ROLE_REF, ROLE_TEXT, ROLE_MEDIA, ROLE_KIND = 256, 257, 258, 259, 260

# Type d'élément → (icône, libellé).
ITEM_KINDS = {
    "bible": ("book.svg", "Bible"),
    "hymn": ("music.svg", "Cantique"),
    "sermon": ("mic.svg", "Sermon"),
    "expose": ("book-open.svg", "Exposé"),
    "image": ("image.svg", "Image"),
    "video": ("play.svg", "Vidéo"),
    "powerpoint": ("layout.svg", "PowerPoint"),
    "custom": ("type.svg", "Slide"),
}

_SERMON_REF = re.compile(r"^\d{2}-\d{4}[A-Z]?\b|\bE-\d+\b|§")
_EXPOSE_REF = re.compile(r"·\s*Page\s+\d+|^Page\s+\d+\s*§")
_HYMN_REF = re.compile(r"cantique|strophe|refrain|ch(?:oe|œ)ur|chant", re.IGNORECASE)
_BIBLE_REF = re.compile(r"\b\d+\s*:\s*\d+")


def item_kind(source: str, reference: str = "", background: str = "") -> str:
    """Type d'un élément de playlist (clé de ITEM_KINDS).

    Les éléments ajoutés avant que le type soit enregistré portent tous
    « custom » : leur type est deviné d'après la référence.
    """
    source = str(source or "").strip().lower()
    if source == "media":
        from app.utils.media_utils import media_kind

        return media_kind(background)
    if source in ITEM_KINDS:
        if source != "custom":
            return source
    reference = str(reference or "")
    if _EXPOSE_REF.search(reference):
        return "expose"
    if _SERMON_REF.search(reference):
        return "sermon"
    if _HYMN_REF.search(reference):
        return "hymn"
    if _BIBLE_REF.search(reference):
        return "bible"
    return "custom"


def _two_lines(text: str, metrics: QFontMetrics, width: int) -> list[str]:
    """Deux lignes au plus : la première coupée entre deux mots, la seconde
    terminée par « … » si le texte continue."""
    words = " ".join(text.split()).split(" ")
    first = ""
    index = 0
    for index, word in enumerate(words):
        candidate = f"{first} {word}".strip()
        if first and metrics.horizontalAdvance(candidate) > width:
            break
        first = candidate
    else:
        return [first] if first else []
    rest = " ".join(words[index:])
    return [first, metrics.elidedText(rest, Qt.TextElideMode.ElideRight, width)]


class PlaylistItemDelegate(QStyledItemDelegate):
    """Carte d'un élément : icône du type, référence, puis deux lignes de texte."""

    CARD_PADDING_V = 8
    CARD_PADDING_H = 10
    ICON_SIZE = 18
    ICON_COLUMN = 30

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.ref_font = QFont(Typography.FAMILY)
        self.ref_font.setPixelSize(Typography.SIZE_NUMBER)
        self.ref_font.setWeight(QFont.Weight.Bold)

        self.text_font = QFont(Typography.FAMILY)
        self.text_font.setPixelSize(Typography.SIZE_BODY)
        self.text_font.setWeight(QFont.Weight.Normal)

        self.color_bg_sel = item_selection_color()
        self.color_bg_hover = item_hover_color()
        self.color_separator = item_separator_color()
        self.color_text = QColor(Colors.TEXT_PRIMARY)
        self.color_text_dim = QColor(Colors.TEXT_MUTED)
        self.color_accent = QColor(Colors.ACCENT_PRIMARY)
        self._icons: dict[tuple[str, str], Any] = {}

    def _icon(self, kind: str, color: QColor):
        key = (kind, color.name())
        if key not in self._icons:
            name = ITEM_KINDS.get(kind, ITEM_KINDS["custom"])[0]
            self._icons[key] = app_icon(name, color.name())
        return self._icons[key]

    def _lines(self, index: QModelIndex) -> tuple[str, list[str]]:
        ref = str(index.data(ROLE_REF) or "").replace("\n", " · ")
        kind = str(index.data(ROLE_KIND) or "custom")
        text = str(index.data(ROLE_TEXT) or "")
        if not text.strip() and kind in ("image", "video", "powerpoint"):
            media = str(index.data(ROLE_MEDIA) or "")
            text = f"{ITEM_KINDS[kind][1]} · {media.replace(chr(92), '/').rsplit('/', 1)[-1]}"
        return ref, text

    def paint(
        self, painter: QPainter, option, index: QModelIndex
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_sel = option.state & QStyle.StateFlag.State_Selected
        is_hover = option.state & QStyle.StateFlag.State_MouseOver

        rect = option.rect
        if is_sel:
            painter.fillRect(rect, self.color_bg_sel)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.color_accent)
            painter.drawRect(rect.left(), rect.top() + 4, 3, rect.height() - 8)
        elif is_hover:
            painter.fillRect(rect, self.color_bg_hover)

        content = rect.adjusted(
            self.CARD_PADDING_H,
            self.CARD_PADDING_V,
            -self.CARD_PADDING_H,
            -self.CARD_PADDING_V,
        )

        # Icône du type
        kind = str(index.data(ROLE_KIND) or "custom")
        icon_color = self.color_accent if is_sel else self.color_text_dim
        self._icon(kind, icon_color).paint(
            painter,
            QRect(content.left(), content.top() + 1, self.ICON_SIZE, self.ICON_SIZE),
        )
        content.setLeft(content.left() + self.ICON_COLUMN)

        ref, text = self._lines(index)
        fm_ref = QFontMetrics(self.ref_font)
        fm_text = QFontMetrics(self.text_font)

        # Référence / titre
        painter.setFont(self.ref_font)
        painter.setPen(self.color_accent if is_sel else self.color_text)
        painter.drawText(
            content.left(),
            content.top() + fm_ref.ascent(),
            fm_ref.elidedText(ref, Qt.TextElideMode.ElideRight, content.width()),
        )

        # Texte : deux lignes au plus
        painter.setFont(self.text_font)
        painter.setPen(self.color_text_dim)
        y = content.top() + fm_ref.height() + 3 + fm_text.ascent()
        for line in _two_lines(text, fm_text, content.width()):
            painter.drawText(content.left(), y, line)
            y += fm_text.lineSpacing()

        painter.setPen(self.color_separator if not is_sel else Qt.PenStyle.NoPen)
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        painter.restore()

    def sizeHint(self, option, index: QModelIndex) -> QSize:
        ref, text = self._lines(index)
        width = max(80, option.rect.width() - 2 * self.CARD_PADDING_H - self.ICON_COLUMN)
        fm_text = QFontMetrics(self.text_font)
        lines = len(_two_lines(text, fm_text, width)) if text.strip() else 0
        height = (
            2 * self.CARD_PADDING_V
            + QFontMetrics(self.ref_font).height()
            + (3 + lines * fm_text.lineSpacing() if lines else 0)
        )
        return QSize(option.rect.width(), max(40, height))


class AddToPlaylistDialog(QDialog):
    """Choisit la playlist de destination pour de nouveaux slides.

    Propose les playlists existantes et la création d'une nouvelle à la volée.
    """

    NEW_SENTINEL = "__new_playlist__"

    def __init__(self, folders: list[dict[str, Any]], count: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ajouter à la playlist")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        layout.setSpacing(Spacing.SM)

        summary = QLabel(
            f"Ajouter {count} slide{'s' if count > 1 else ''} à :", self
        )
        summary.setStyleSheet(
            f"font-size: {Typography.SIZE_BODY}px; color: {Colors.TEXT_PRIMARY};"
        )
        layout.addWidget(summary)

        self.folder_combo = QComboBox(self)
        self.folder_combo.setStyleSheet(get_input_style())
        self.folder_combo.setFixedHeight(36)
        for folder in folders:
            self.folder_combo.addItem(str(folder.get("name", "")), int(folder["id"]))
        self.folder_combo.insertSeparator(self.folder_combo.count())
        self.folder_combo.addItem("＋ Nouvelle playlist…", self.NEW_SENTINEL)
        layout.addWidget(self.folder_combo)

        self.name_input = QLineEdit(self)
        self.name_input.setPlaceholderText("Nom de la nouvelle playlist")
        self.name_input.setStyleSheet(get_input_style())
        self.name_input.setFixedHeight(36)
        self.name_input.hide()
        layout.addWidget(self.name_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.folder_combo.currentIndexChanged.connect(self._on_combo_changed)
        if folders:
            self.folder_combo.setCurrentIndex(0)
        else:
            self._on_combo_changed()

    def _on_combo_changed(self, *_args) -> None:
        is_new = self.folder_combo.currentData() == self.NEW_SENTINEL
        self.name_input.setVisible(is_new)
        if is_new:
            self.name_input.setFocus()

    def _on_accept(self) -> None:
        folder_id, new_name = self.selected_folder()
        if folder_id is None and not new_name:
            self.name_input.setFocus()
            return
        self.accept()

    def selected_folder(self) -> tuple[int | None, str]:
        """(folder_id existant, nom de nouvelle playlist) — id est None si création."""
        data = self.folder_combo.currentData()
        if data == self.NEW_SENTINEL:
            return None, self.name_input.text().strip()
        return (int(data) if data is not None else None), ""


class _SlideDialog(QDialog):

    def __init__(self, parent=None, reference: str = "", text: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Slide de playlist")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        layout.setSpacing(Spacing.SM)

        ref_label = QLabel("Titre / Référence :", self)
        ref_label.setStyleSheet(
            f"font-size: {Typography.SIZE_LABEL}px; color: {Colors.TEXT_SECONDARY};"
        )
        self.reference_input = QLineEdit(self)
        self.reference_input.setPlaceholderText("Ex. Jean 3:16 ou Annonce")
        self.reference_input.setStyleSheet(get_input_style())
        self.reference_input.setFixedHeight(36)
        self.reference_input.setText(reference)

        text_label = QLabel("Texte du slide :", self)
        text_label.setStyleSheet(
            f"font-size: {Typography.SIZE_LABEL}px; color: {Colors.TEXT_SECONDARY};"
        )
        self.text_input = QPlainTextEdit(self)
        self.text_input.setPlaceholderText("Contenu projeté…")
        self.text_input.setStyleSheet(get_input_style())
        self.text_input.setPlainText(text)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(ref_label)
        layout.addWidget(self.reference_input)
        layout.addWidget(text_label)
        layout.addWidget(self.text_input, 1)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str]:
        return (
            self.reference_input.text().strip(),
            self.text_input.toPlainText().strip(),
        )


class PlaylistTab(QFrame):
    """Onglet Playlists : dossiers de slides préparés à l'avance, projetables."""

    folderSelected = Signal(object)  # folder_id ou None
    itemActivated = Signal(int)  # projeter à partir de ce slide
    itemCued = Signal(int)  # clic simple : préparer dans l'aperçu
    playRequested = Signal(object)  # item_id de départ ou None (début)
    folderCreateRequested = Signal(str)
    folderRenameRequested = Signal(int, str)
    folderDeleteRequested = Signal(int)
    folderExportRequested = Signal(int)
    # Diaporama : médias du dossier choisi, dans l'ordre de la playlist.
    slideshowRequested = Signal(list)
    importRequested = Signal()
    itemCreateRequested = Signal(int, str, str)  # folder_id, référence, texte
    itemUpdateRequested = Signal(int, str, str)  # item_id, référence, texte
    itemDeleteRequested = Signal(int)
    itemMoveRequested = Signal(int, int)  # item_id, delta (+1 / -1)
    quoteImageRequested = Signal(str, str)  # référence, texte (image à partager)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._folders: list[dict[str, Any]] = []
        self._items: list[dict[str, Any]] = []
        self._suppress_folder_signals = False

        # ── Gauche : liste des playlists ─────────────────────────────────
        folders_label = QLabel(self.tr("Playlists"), self)
        folders_label.setObjectName("PanelTitle")

        self.folders_list = QListWidget(self)
        self.folders_list.setMinimumWidth(140)
        self.folders_list.setStyleSheet(get_list_style(borderless=True))
        self.folders_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.folders_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.folders_list.customContextMenuRequested.connect(
            self._on_folder_context_menu
        )

        self.new_folder_btn = QPushButton(tr("playlist_new_short"), self)
        self.new_folder_btn.setIcon(app_icon("plus.svg"))
        self.new_folder_btn.setIconSize(QSize(12, 12))
        self.new_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_folder_btn.setStyleSheet(get_compact_button_style())
        self.new_folder_btn.setFixedHeight(28)
        self.new_folder_btn.setToolTip("Créer une nouvelle playlist")
        self.new_folder_btn.clicked.connect(self._on_new_folder_clicked)

        self.import_btn = QPushButton(tr("import"), self)
        self.import_btn.setIcon(app_icon("upload.svg"))
        self.import_btn.setIconSize(QSize(12, 12))
        self.import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_btn.setStyleSheet(get_compact_button_style())
        self.import_btn.setFixedHeight(28)
        self.import_btn.setToolTip(
            "Importer une playlist exportée (fichier .json) — "
            "pratique pour partager un culte entre deux ordinateurs"
        )
        self.import_btn.clicked.connect(self.importRequested.emit)

        left_widget = QWidget()
        left_widget.setStyleSheet("background: transparent;")
        left = QVBoxLayout(left_widget)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(Spacing.SM)
        left.addWidget(folders_label)
        left.addWidget(self.folders_list, 1)
        folders_buttons = QHBoxLayout()
        folders_buttons.setContentsMargins(0, 0, 0, 0)
        folders_buttons.setSpacing(Spacing.SM)
        folders_buttons.addWidget(self.new_folder_btn, 1)
        folders_buttons.addWidget(self.import_btn)
        left.addLayout(folders_buttons)

        # ── Droite : slides de la playlist ───────────────────────────────
        self.info_label = QLabel("", self)
        self.info_label.setStyleSheet(
            f"font-size: {Typography.SIZE_META}px; color: {Colors.TEXT_MUTED};"
        )

        self.items_list = QListWidget(self)
        self.items_list.setStyleSheet(get_list_style(borderless=True))
        self.items_list.setItemDelegate(PlaylistItemDelegate(self))
        self.items_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        # Les cartes suivent la largeur : jamais de défilement horizontal.
        self.items_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.items_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.items_list.customContextMenuRequested.connect(self._on_item_context_menu)

        self.preview = QPlainTextEdit(self)
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Aperçu du slide sélectionné…")
        self.preview.setMinimumHeight(96)
        self.preview.setStyleSheet(f"""
            {get_preview_text_style()}
            QPlainTextEdit {{
                font-family: {Typography.FAMILY};
                font-size: {Typography.SIZE_BODY + 1}px;
                line-height: 1.5;
            }}
        """)

        # Liste / aperçu séparés verticalement : l'opérateur agrandit
        # l'aperçu selon ses besoins (défaut ~1/4 de la hauteur).
        self.list_preview_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.list_preview_splitter.addWidget(self.items_list)
        self.list_preview_splitter.addWidget(self.preview)
        self.list_preview_splitter.setStretchFactor(0, 3)
        self.list_preview_splitter.setStretchFactor(1, 1)
        self.list_preview_splitter.setHandleWidth(1)
        self.list_preview_splitter.setStyleSheet(get_splitter_style())
        self.list_preview_splitter.setSizes([560, 190])

        # Barre d'actions — boutons compacts (28 px) et libellés courts :
        # la barre complète doit tenir au-dessus de la liste sans déborder.
        self.new_item_btn = QPushButton(tr("playlist_item_new_short"), self)
        self.new_item_btn.setIcon(app_icon("file-plus.svg"))
        self.new_item_btn.setToolTip("Ajouter un slide à la playlist")
        self.new_item_btn.clicked.connect(self._on_new_item_clicked)

        self.edit_item_btn = QPushButton(tr("edit"), self)
        self.edit_item_btn.setIcon(app_icon("edit-3.svg"))
        self.edit_item_btn.setToolTip("Modifier le slide sélectionné")
        self.edit_item_btn.clicked.connect(self._on_edit_item_clicked)

        self.delete_item_btn = QPushButton(self)
        self.delete_item_btn.setIcon(app_icon("trash.svg"))
        self.delete_item_btn.setToolTip("Supprimer le slide sélectionné")
        self.delete_item_btn.clicked.connect(self._on_delete_item_clicked)

        self.up_btn = QPushButton(self)
        self.up_btn.setIcon(app_icon("chevron-up.svg"))
        self.up_btn.setToolTip("Monter le slide")
        self.up_btn.clicked.connect(lambda: self._move_selected(-1))

        self.down_btn = QPushButton(self)
        self.down_btn.setIcon(app_icon("chevron-down.svg"))
        self.down_btn.setToolTip("Descendre le slide")
        self.down_btn.clicked.connect(lambda: self._move_selected(1))

        self.play_btn = QPushButton(tr("project"), self)
        self.play_btn.setIcon(app_icon("cast.svg"))
        self.play_btn.setIconSize(QSize(12, 12))
        self.play_btn.setToolTip(
            "Projeter la playlist à partir du slide sélectionné "
            "(ou du début si aucun slide n'est sélectionné)"
        )
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.setStyleSheet(get_compact_button_style())

        for btn in (
            self.new_item_btn,
            self.edit_item_btn,
            self.delete_item_btn,
            self.up_btn,
            self.down_btn,
        ):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIconSize(QSize(12, 12))
            btn.setFixedHeight(28)
            btn.setStyleSheet(get_compact_button_style())
        self.play_btn.setFixedHeight(28)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(Spacing.SM)
        actions.addWidget(self.new_item_btn)
        actions.addWidget(self.edit_item_btn)
        actions.addWidget(self.delete_item_btn)
        actions.addWidget(self.up_btn)
        actions.addWidget(self.down_btn)
        actions.addStretch(1)
        actions.addWidget(self.play_btn)

        actions_frame = QFrame(self)
        actions_frame.setStyleSheet("background: transparent;")
        actions_frame.setLayout(actions)

        right_widget = QWidget()
        right_widget.setStyleSheet("background: transparent;")
        right = QVBoxLayout(right_widget)
        right.setContentsMargins(Spacing.SM, 0, 0, 0)
        right.setSpacing(Spacing.SM)
        right.addWidget(self.info_label)
        right.addWidget(self.list_preview_splitter, 1)
        right.addWidget(actions_frame)

        # ── Splitter ─────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(get_splitter_style())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)
        layout.addWidget(splitter, 1)

        # ── Signaux ──────────────────────────────────────────────────────
        self.folders_list.currentItemChanged.connect(self._on_folder_changed)
        self.folders_list.itemDoubleClicked.connect(
            lambda _item: self._on_rename_folder_clicked()
        )
        self.items_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.items_list.itemClicked.connect(self._on_item_clicked)
        self.items_list.currentItemChanged.connect(self._on_item_selection_changed)
        self.play_btn.clicked.connect(self._on_play_clicked)

    # ── Public API ────────────────────────────────────────────────────────

    def attach_service_panel(self, panel: QWidget) -> None:
        """Place le panneau « Déroulé du culte » sous la liste des slides."""
        self.list_preview_splitter.addWidget(panel)
        self.list_preview_splitter.setStretchFactor(2, 0)

    def select_folder(self, folder_id: int) -> bool:
        """Select a playlist (emits folderSelected when it changes)."""
        return select_first(self.folders_list, lambda it: int(it.data(256)) == int(folder_id))

    def current_folder_id(self) -> int | None:
        item = self.folders_list.currentItem()
        if item is None:
            return None
        data = item.data(256)
        return int(data) if data is not None else None

    def selected_item_id(self) -> int | None:
        item = self.items_list.currentItem()
        if item is None:
            return None
        data = item.data(256)
        return int(data) if data is not None else None

    def set_folders(
        self, folders: list[dict[str, Any]], select_id: int | None = None
    ) -> None:
        self._folders = folders
        previous = self.current_folder_id()
        target = select_id if select_id is not None else previous

        self._suppress_folder_signals = True
        self.folders_list.clear()
        for folder in folders:
            item = QListWidgetItem(str(folder.get("name", "")))
            item.setData(256, int(folder["id"]))
            count = folder.get("item_count")
            if count is not None:
                item.setToolTip(f"{count} slide(s)")
            self.folders_list.addItem(item)

        row = -1
        if target is not None:
            for i in range(self.folders_list.count()):
                if int(self.folders_list.item(i).data(256)) == int(target):
                    row = i
                    break
        if row < 0 and self.folders_list.count():
            row = 0
        if row >= 0:
            self.folders_list.setCurrentRow(row)
        else:
            self.folders_list.setCurrentRow(-1)
        self._suppress_folder_signals = False

        # N'émettre que si le dossier sélectionné a réellement changé — un
        # simple rafraîchissement ne doit pas recharger les slides.
        if self.current_folder_id() != previous:
            self._on_folder_changed(self.folders_list.currentItem(), None)

    def set_items(self, items: list[dict[str, Any]]) -> None:
        self._items = items
        self.items_list.clear()
        for it in items:
            item = QListWidgetItem()
            item.setData(ROLE_ID, int(it["id"]))
            item.setData(ROLE_REF, str(it.get("reference") or ""))
            item.setData(ROLE_TEXT, str(it.get("text") or ""))
            item.setData(ROLE_KIND, item_kind(
                str(it.get("source") or ""), str(it.get("reference") or ""),
                str(it.get("background") or ""),
            ))
            # Média rattaché (item « media ») : chemin conservé pour pouvoir
            # lancer le dossier en diaporama.
            if str(it.get("source") or "") == "media":
                item.setData(ROLE_MEDIA, str(it.get("background") or ""))
            self.items_list.addItem(item)
        self.info_label.setText(f"{len(items)} slide(s)")
        if items:
            self.items_list.setCurrentRow(0)

    def media_entries(self) -> list[dict[str, Any]]:
        """Médias du dossier courant, dans l'ordre (pour le diaporama)."""
        medias: list[dict[str, Any]] = []
        for row in range(self.items_list.count()):
            item = self.items_list.item(row)
            path = str(item.data(259) or "").strip()
            if path:
                medias.append(
                    {"name": str(item.data(257) or ""), "path": path}
                )
        return medias

    # ── Slots privés ──────────────────────────────────────────────────────

    def _on_folder_changed(self, current, _previous) -> None:
        if self._suppress_folder_signals:
            return
        folder_id = None
        if current is not None:
            data = current.data(256)
            folder_id = int(data) if data is not None else None
        self.folderSelected.emit(folder_id)

    def _on_item_selection_changed(self, current, _previous) -> None:
        if current is None:
            self.preview.clear()
            return
        ref = str(current.data(257) or "")
        text = str(current.data(258) or "")
        self.preview.setPlainText(f"{ref}\n\n{text}" if ref else text)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(256)
        if data is not None:
            self.itemCued.emit(int(data))

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(256)
        if data is not None:
            self.itemActivated.emit(int(data))

    def _on_play_clicked(self) -> None:
        self.playRequested.emit(self.selected_item_id())

    # Dossiers
    def _on_new_folder_clicked(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Nouvelle playlist", "Nom de la playlist :"
        )
        if ok and name.strip():
            self.folderCreateRequested.emit(name.strip())

    def _on_rename_folder_clicked(self) -> None:
        item = self.folders_list.currentItem()
        if item is None:
            return
        folder_id = int(item.data(256))
        name, ok = QInputDialog.getText(
            self,
            "Renommer la playlist",
            "Nouveau nom :",
            text=str(item.text()),
        )
        if ok and name.strip() and name.strip() != item.text():
            self.folderRenameRequested.emit(folder_id, name.strip())

    def _on_delete_folder_clicked(self) -> None:
        item = self.folders_list.currentItem()
        if item is None:
            return
        folder_id = int(item.data(256))
        if self._confirm_delete(f"Supprimer la playlist « {item.text()} » ?"):
            self.folderDeleteRequested.emit(folder_id)

    def _confirm_delete(self, message: str) -> bool:
        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            "Confirmation",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _on_folder_context_menu(self, pos) -> None:
        item = self.folders_list.itemAt(pos)
        if item is None:
            return
        self.folders_list.setCurrentItem(item)
        folder_id = int(item.data(256))
        menu = QMenu(self)
        menu.setStyleSheet(get_menu_style())
        act_export = menu.addAction(
            app_icon("download.svg"), "Exporter vers un fichier…"
        )
        act_slideshow = menu.addAction(
            app_icon("play.svg"), "Lancer en diaporama (médias)"
        )
        menu.addSeparator()
        act_rename = menu.addAction(app_icon("edit-3.svg"), "Renommer")
        act_delete = menu.addAction(app_icon("trash.svg"), "Supprimer")
        chosen = menu.exec(self.folders_list.mapToGlobal(pos))
        if chosen is act_export:
            self.folderExportRequested.emit(folder_id)
        elif chosen is act_slideshow:
            self._emit_slideshow_for_folder(folder_id)
        elif chosen is act_rename:
            self._on_rename_folder_clicked()
        elif chosen is act_delete:
            self._on_delete_folder_clicked()

    def _emit_slideshow_for_folder(self, folder_id: int) -> None:
        """Demande le diaporama des médias du dossier (durées réglées ailleurs)."""
        if folder_id != self.current_folder_id():
            # Le contenu affiché n'est pas celui du dossier visé : on demande
            # au contrôleur de charger ce dossier d'abord.
            self.folderSelected.emit(folder_id)
        medias = self.media_entries()
        if medias:
            self.slideshowRequested.emit(medias)

    # Slides
    def _on_new_item_clicked(self) -> None:
        folder_id = self.current_folder_id()
        if folder_id is None:
            return
        dialog = _SlideDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        reference, text = dialog.values()
        if not text and not reference:
            return
        self.itemCreateRequested.emit(folder_id, reference, text)

    def _on_edit_item_clicked(self) -> None:
        item = self.items_list.currentItem()
        if item is None:
            return
        item_id = int(item.data(256))
        dialog = _SlideDialog(
            self,
            reference=str(item.data(257) or ""),
            text=str(item.data(258) or ""),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        reference, text = dialog.values()
        if not text and not reference:
            return
        self.itemUpdateRequested.emit(item_id, reference, text)

    def _on_delete_item_clicked(self) -> None:
        item = self.items_list.currentItem()
        if item is None:
            return
        item_id = int(item.data(256))
        ref = str(item.data(257) or "")
        if self._confirm_delete(f"Supprimer le slide « {ref} » ?"):
            self.itemDeleteRequested.emit(item_id)

    def _move_selected(self, delta: int) -> None:
        item_id = self.selected_item_id()
        if item_id is None:
            return
        self.itemMoveRequested.emit(item_id, delta)

    def _on_item_context_menu(self, pos) -> None:
        item = self.items_list.itemAt(pos)
        if item is None:
            return
        self.items_list.setCurrentItem(item)
        menu = QMenu(self)
        act_play = menu.addAction(app_icon("cast.svg"), "Projeter à partir d'ici")
        act_edit = menu.addAction(app_icon("edit-3.svg"), "Modifier")
        act_quote = menu.addAction(app_icon("image.svg"), "Créer une image de citation…")
        act_quote.setEnabled(bool(str(item.data(258) or "").strip()))
        menu.addSeparator()
        act_delete = menu.addAction(app_icon("trash.svg"), "Supprimer")
        chosen = menu.exec(self.items_list.mapToGlobal(pos))
        if chosen is act_play:
            self._on_item_double_clicked(item)
        elif chosen is act_quote:
            self.quoteImageRequested.emit(
                str(item.data(257) or "").replace("\n", " — "), str(item.data(258) or "")
            )
        elif chosen is act_edit:
            self._on_edit_item_clicked()
        elif chosen is act_delete:
            self._on_delete_item_clicked()
