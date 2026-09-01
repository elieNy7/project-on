from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
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
from app.ui.theme import (
    Colors,
    Spacing,
    Typography,
    get_button_style,
    get_menu_style,
    item_hover_color,
    item_selection_color,
)

_THUMB_W, _THUMB_H = 168, 110


class MediaTab(QWidget):
    """Galerie de médias (images + vidéos) : projeter, ajouter à la playlist."""

    importRequested = pyqtSignal(str)  # "image" | "video"
    itemActivated = pyqtSignal(int)  # projeter le média
    itemDeleteRequested = pyqtSignal(int)
    itemRenameRequested = pyqtSignal(int, str)
    refreshRequested = pyqtSignal()
    mediaAddToPlaylistRequested = pyqtSignal(dict)  # {name, path, kind}

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

        self.import_images_btn = QPushButton("Importer images", self)
        self.import_images_btn.setIcon(app_icon("image.svg", Colors.TEXT_PRIMARY))
        self.import_images_btn.setToolTip(
            "Ajouter des images à la bibliothèque (copiées dans Project-On)"
        )
        self.import_images_btn.clicked.connect(
            lambda: self.importRequested.emit("image")
        )

        self.import_videos_btn = QPushButton("Importer vidéos", self)
        self.import_videos_btn.setIcon(app_icon("play.svg", Colors.TEXT_PRIMARY))
        self.import_videos_btn.setToolTip(
            "Ajouter des vidéos à la bibliothèque (mp4, webm, mov…)"
        )
        self.import_videos_btn.clicked.connect(
            lambda: self.importRequested.emit("video")
        )

        self.delete_btn = QPushButton(self)
        self.delete_btn.setIcon(app_icon("trash.svg", Colors.TEXT_PRIMARY))
        self.delete_btn.setToolTip("Retirer le média sélectionné de la bibliothèque")
        self.delete_btn.clicked.connect(self._on_delete_clicked)

        for btn in (self.import_images_btn, self.import_videos_btn, self.delete_btn):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(get_button_style())
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
            if item.icon().isNull():
                tint = "#7dd3fc" if kind == "video" else Colors.TEXT_MUTED
                item.setIcon(app_icon("play.svg", tint))

            label = f"{name}" if kind == "image" else f"▶ {name}"
            item.setText(label)
            self.gallery.addItem(item)

        count = len(items)
        self.info_label.setText(f"{count} média{'s' if count != 1 else ''}")

    def selected_media(self) -> dict[str, Any] | None:
        item = self.gallery.currentItem()
        if item is None:
            return None
        return {
            "id": int(item.data(256)),
            "name": str(item.data(257) or ""),
            "path": str(item.data(258) or ""),
            "kind": str(item.data(259) or "image"),
        }

    # ── Slots privés ──────────────────────────────────────────────────────

    def _current_id(self) -> int | None:
        media = self.selected_media()
        return int(media["id"]) if media else None

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
        self.gallery.setCurrentItem(item)
        media = self.selected_media() or {}

        menu = QMenu(self)
        menu.setStyleSheet(get_menu_style())
        act_project = menu.addAction(app_icon("cast.svg"), "Projeter")
        act_playlist = menu.addAction(app_icon("plus.svg"), "Ajouter à la playlist")
        act_rename = menu.addAction(app_icon("edit-3.svg"), "Renommer")
        menu.addSeparator()
        act_delete = menu.addAction(app_icon("trash.svg"), "Retirer de la bibliothèque")
        chosen = menu.exec(self.gallery.mapToGlobal(pos))
        if chosen is act_project:
            self._on_double_clicked(item)
        elif chosen is act_playlist:
            self.mediaAddToPlaylistRequested.emit(media)
        elif chosen is act_rename:
            self._on_rename_clicked()
        elif chosen is act_delete:
            self._on_delete_clicked()
