from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.icons import app_icon
from app.ui.list_selection import select_first
from app.ui.theme import (
    Colors,
    Spacing,
    Typography,
    get_compact_button_style,
    get_menu_style,
    item_hover_color,
    item_selection_color,
)

_THUMB_W, _THUMB_H = 168, 110


def _duration_label(seconds: int) -> str:
    """Durée lisible dans la galerie (« 8 s », « 1 min 30 »)."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} s"
    minutes, rest = divmod(seconds, 60)
    return f"{minutes} min {rest:02d}" if rest else f"{minutes} min"


class MediaTab(QWidget):
    """Galerie de médias (images + vidéos) : projeter, ajouter à la playlist."""

    importRequested = Signal(str)  # "image" | "video" | "pptx"
    itemActivated = Signal(int)  # projeter le média
    itemCued = Signal(int)  # clic simple : préparer dans l'aperçu
    itemDeleteRequested = Signal(int)
    itemRenameRequested = Signal(int, str)
    itemLoopRequested = Signal(int, bool)  # media_id, boucle on/off
    itemDurationRequested = Signal(int, int)  # media_id, durée en secondes
    refreshRequested = Signal()
    mediaAddToPlaylistRequested = Signal(dict)  # {name, path, kind}
    # Diaporama : liste ordonnée de médias ({id, name, path, kind, duration}).
    slideshowRequested = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(Spacing.SM)

        self.info_label = QLabel("0 média", self)
        self.info_label.setStyleSheet(
            f"font-size: {Typography.SIZE_META}px; color: {Colors.TEXT_MUTED};"
        )
        header.addWidget(self.info_label)
        header.addStretch(1)

        # Diaporama : enchaîne les médias sélectionnés (ou toute la
        # bibliothèque) avec la durée réglée pour chacun.
        self.slideshow_btn = QPushButton("Diaporama", self)
        self.slideshow_btn.setIcon(app_icon("play.svg", Colors.TEXT_PRIMARY))
        self.slideshow_btn.setToolTip(
            "Enchaîner automatiquement les médias sélectionnés (Ctrl+clic pour "
            "en choisir plusieurs), avec la durée d'affichage de chacun"
        )
        self.slideshow_btn.clicked.connect(self._on_slideshow_clicked)

        self.import_images_btn = QPushButton("Images", self)
        self.import_images_btn.setIcon(app_icon("image.svg", Colors.TEXT_PRIMARY))
        self.import_images_btn.setToolTip(
            "Ajouter des images à la bibliothèque (copiées dans Project-On)"
        )
        self.import_images_btn.clicked.connect(
            lambda: self.importRequested.emit("image")
        )

        self.import_videos_btn = QPushButton("Vidéos", self)
        self.import_videos_btn.setIcon(app_icon("play.svg", Colors.TEXT_PRIMARY))
        self.import_videos_btn.setToolTip(
            "Ajouter des vidéos à la bibliothèque (mp4, webm, mov…)"
        )
        self.import_videos_btn.clicked.connect(
            lambda: self.importRequested.emit("video")
        )

        self.import_pptx_btn = QPushButton("PowerPoint", self)
        self.import_pptx_btn.setIcon(app_icon("layout.svg", Colors.TEXT_PRIMARY))
        self.import_pptx_btn.setToolTip(
            "Ajouter une présentation PowerPoint : chaque slide est rendue "
            "en image fidèle (nécessite PowerPoint ou LibreOffice)"
        )
        self.import_pptx_btn.clicked.connect(
            lambda: self.importRequested.emit("pptx")
        )

        self.delete_btn = QPushButton(self)
        self.delete_btn.setIcon(app_icon("trash.svg", Colors.TEXT_PRIMARY))
        self.delete_btn.setToolTip("Retirer le média sélectionné de la bibliothèque")
        self.delete_btn.clicked.connect(self._on_delete_clicked)

        for btn in (
            self.slideshow_btn,
            self.import_images_btn,
            self.import_videos_btn,
            self.import_pptx_btn,
            self.delete_btn,
        ):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIconSize(QSize(12, 12))
            btn.setFixedHeight(28)
            btn.setStyleSheet(get_compact_button_style())
            header.addWidget(btn)

        header_widget = QWidget(self)
        header_widget.setStyleSheet("background: transparent;")
        header_widget.setLayout(header)

        # Galerie
        self.gallery = QListWidget(self)
        self.gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self.gallery.setIconSize(QSize(_THUMB_W, _THUMB_H))
        self.gallery.setGridSize(QSize(_THUMB_W + 22, _THUMB_H + 46))
        self.gallery.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.gallery.setMovement(QListWidget.Movement.Static)
        self.gallery.setSpacing(10)
        self.gallery.setWordWrap(True)
        self.gallery.setUniformItemSizes(False)
        self.gallery.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        # Sélection multiple : « Lancer le diaporama » enchaîne les médias
        # cochés dans l'ordre de la galerie.
        self.gallery.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection
        )
        self.gallery.setStyleSheet(
            f"""
            QListWidget {{
                background: transparent;
                border: none;
            }}
            QListWidget::item {{
                border-radius: 10px;
                padding: 4px;
            }}
            QListWidget::item:selected {{
                background: {item_selection_color()};
                border: 1px solid {Colors.ACCENT_GLOW_STRONG};
            }}
            QListWidget::item:hover {{
                background: {item_hover_color()};
            }}
            """
        )
        self.gallery.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.gallery.customContextMenuRequested.connect(self._on_context_menu)
        self.gallery.itemDoubleClicked.connect(self._on_double_clicked)
        self.gallery.itemClicked.connect(self._on_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)
        layout.addWidget(header_widget)
        layout.addWidget(self.gallery, 1)

    # ── Public API ────────────────────────────────────────────────────────

    def set_media(self, items: list[dict[str, Any]]) -> None:
        self.gallery.clear()
        for media in items:
            name = str(media.get("name") or "")
            path = str(media.get("path") or "")
            kind = str(media.get("kind") or "image")

            item = QListWidgetItem(name)
            item.setData(256, int(media["id"]))
            item.setData(257, name)
            item.setData(258, path)
            item.setData(259, kind)
            item.setData(260, int(media.get("duration_seconds") or 0))
            item.setToolTip(f"{name}\n{path}")

            if kind == "image":
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    item.setIcon(QIcon(pixmap.scaled(
                        _THUMB_W,
                        _THUMB_H,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )))
            elif kind == "powerpoint":
                # Miniature = première slide rendue (si le cache existe).
                try:
                    from app.utils.office_renderer import pptx_slides_dir

                    slides = sorted(pptx_slides_dir(path).glob("slide-*.png"))
                    if slides:
                        pixmap = QPixmap(str(slides[0]))
                        if not pixmap.isNull():
                            item.setIcon(QIcon(pixmap.scaled(
                                _THUMB_W,
                                _THUMB_H,
                                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                Qt.TransformationMode.SmoothTransformation,
                            )))
                except Exception:
                    pass

            if item.icon().isNull():
                if kind == "video":
                    item.setIcon(app_icon("play.svg", "#7dd3fc"))
                elif kind == "powerpoint":
                    item.setIcon(app_icon("layout.svg", "#fdba74"))
                else:
                    item.setIcon(app_icon("image.svg", Colors.TEXT_MUTED))

            if kind == "video":
                label = f"▶ {name}"
            elif kind == "powerpoint":
                label = f"PPT · {name}"
            else:
                label = name
            seconds = int(item.data(260) or 0)
            if seconds > 0:
                label = f"{label}  ·  {_duration_label(seconds)}"
            item.setText(label)
            self.gallery.addItem(item)

        count = len(items)
        self.info_label.setText(f"{count} média{'s' if count != 1 else ''}")

    def select_media(self, media_id: int) -> bool:
        return select_first(self.gallery, lambda it: int(it.data(256)) == int(media_id))

    def selected_media(self) -> dict[str, Any] | None:
        item = self.gallery.currentItem()
        if item is None:
            return None
        return {
            "id": int(item.data(256)),
            "name": str(item.data(257) or ""),
            "path": str(item.data(258) or ""),
            "kind": str(item.data(259) or "image"),
            "duration_seconds": int(item.data(260) or 0),
        }

    def selected_medias(self) -> list[dict[str, Any]]:
        """Médias sélectionnés, dans l'ordre de la galerie (Ctrl+clic)."""
        chosen: list[dict[str, Any]] = []
        for item in self.gallery.selectedItems():
            chosen.append(
                {
                    "id": int(item.data(256)),
                    "name": str(item.data(257) or ""),
                    "path": str(item.data(258) or ""),
                    "kind": str(item.data(259) or "image"),
                    "duration_seconds": int(item.data(260) or 0),
                }
            )
        return chosen

    def all_medias(self) -> list[dict[str, Any]]:
        """Toute la bibliothèque, dans l'ordre affiché."""
        return [
            {
                "id": int(self.gallery.item(row).data(256)),
                "name": str(self.gallery.item(row).data(257) or ""),
                "path": str(self.gallery.item(row).data(258) or ""),
                "kind": str(self.gallery.item(row).data(259) or "image"),
                "duration_seconds": int(self.gallery.item(row).data(260) or 0),
            }
            for row in range(self.gallery.count())
        ]

    # ── Slots privés ──────────────────────────────────────────────────────

    def _current_id(self) -> int | None:
        media = self.selected_media()
        return int(media["id"]) if media else None

    def _on_slideshow_clicked(self) -> None:
        """Lance le diaporama : la sélection, sinon toute la bibliothèque."""
        medias = self.selected_medias() or self.all_medias()
        if medias:
            self.slideshowRequested.emit(medias)

    def _emit_slideshow(self, medias: list[dict[str, Any]]) -> None:
        if medias:
            self.slideshowRequested.emit(medias)

    def _on_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(256)
        if data is not None:
            self.itemCued.emit(int(data))

    def _on_double_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(256)
        if data is not None:
            self.itemActivated.emit(int(data))

    def _on_delete_clicked(self) -> None:
        media_id = self._current_id()
        if media_id is not None:
            self.itemDeleteRequested.emit(media_id)

    def _on_rename_clicked(self) -> None:
        item = self.gallery.currentItem()
        if item is None:
            return
        media_id = int(item.data(256))
        name, ok = QInputDialog.getText(
            self, "Renommer le média", "Nouveau nom :", text=str(item.data(257) or "")
        )
        if ok and name.strip():
            self.itemRenameRequested.emit(media_id, name.strip())

    def _on_context_menu(self, pos) -> None:
        item = self.gallery.itemAt(pos)
        if item is None:
            return
        if not item.isSelected():
            # Clic droit sur un média hors sélection : il devient la sélection,
            # comme dans l'explorateur Windows.
            self.gallery.clearSelection()
            self.gallery.setCurrentItem(item)
            item.setSelected(True)
        media = self.selected_media() or {}
        selection = self.selected_medias()

        menu = QMenu(self)
        menu.setStyleSheet(get_menu_style())
        act_project = menu.addAction(app_icon("cast.svg"), "Projeter")
        if selection:
            libelle = (
                f"Lancer le diaporama ({len(selection)} médias)"
                if len(selection) > 1
                else "Lancer le diaporama"
            )
            act_slideshow = menu.addAction(app_icon("play.svg"), libelle)
        else:
            act_slideshow = None
        act_playlist = menu.addAction(app_icon("plus.svg"), "Ajouter à la playlist")
        act_rename = menu.addAction(app_icon("edit-3.svg"), "Renommer")
        is_video = str(media.get("kind") or "") == "video"
        act_loop = None
        if is_video:
            loop_on = bool(media.get("loop"))
            act_loop = menu.addAction(
                app_icon("refresh-cw.svg"),
                "Boucle : activée" if loop_on else "Boucle : désactivée",
            )
            act_loop.setCheckable(True)
            act_loop.setChecked(loop_on)
        act_duration, duration_actions = self._build_duration_menu(menu, media)
        menu.addSeparator()
        act_delete = menu.addAction(app_icon("trash.svg"), "Retirer de la bibliothèque")
        chosen = menu.exec(self.gallery.mapToGlobal(pos))
        if chosen is act_project:
            self._on_double_clicked(item)
        elif act_slideshow is not None and chosen is act_slideshow:
            self._emit_slideshow(selection)
        elif chosen is act_playlist:
            self.mediaAddToPlaylistRequested.emit(media)
        elif chosen is act_rename:
            self._on_rename_clicked()
        elif act_loop is not None and chosen is act_loop:
            self.itemLoopRequested.emit(int(media.get("id")), act_loop.isChecked())
        elif chosen is act_duration:
            self._ask_duration(media)
        elif chosen in duration_actions:
            self.itemDurationRequested.emit(
                int(media.get("id")), int(duration_actions[chosen])
            )
        elif chosen is act_delete:
            self._on_delete_clicked()

    # ── Durée d'affichage (diaporama) ─────────────────────────────────────

    _DURATION_CHOICES = (3, 5, 8, 10, 15, 30)

    def _build_duration_menu(self, menu: QMenu, media: dict[str, Any]):
        """Sous-menu « Durée d'affichage » : préréglages + durée libre."""
        submenu = menu.addMenu(app_icon("clock.svg"), "Durée d'affichage")
        current = int(media.get("duration_seconds") or 0)
        actions: dict[Any, int] = {}
        act_none = submenu.addAction("Aucune (avance manuelle)")
        act_none.setCheckable(True)
        act_none.setChecked(current <= 0)
        actions[act_none] = 0
        submenu.addSeparator()
        for seconds in self._DURATION_CHOICES:
            action = submenu.addAction(f"{seconds} secondes")
            action.setCheckable(True)
            action.setChecked(current == seconds)
            actions[action] = seconds
        submenu.addSeparator()
        act_custom = submenu.addAction("Durée personnalisée…")
        return act_custom, actions

    def _ask_duration(self, media: dict[str, Any]) -> None:
        current = int(media.get("duration_seconds") or 0)
        seconds, ok = QInputDialog.getInt(
            self,
            "Durée d'affichage",
            "Secondes d'affichage en diaporama\n(0 = avance manuelle) :",
            current,
            0,
            3600,
            1,
        )
        if ok:
            self.itemDurationRequested.emit(int(media.get("id")), int(seconds))
