from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QImage, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.ui.icons import app_icon
from app.ui.obs_output_settings_dialog import DIALOG_STYLE, SettingSection
from app.ui.settings_dialog import _style_combo
from app.ui.theme import Colors, Typography
from app.utils.obs_overlay_render import chroma_key_rgb, render_obs_overlay_on_color
from app.utils.settings import HdmiSettings

# Texte de démonstration quand la slide en cours est masquée ou vide :
# l'aperçu reste utile pour régler l'incrustation hors service.
_DEMO_SLIDE = {
    "text": "Car Dieu a tant aimé le monde qu'il a donné son Fils unique",
    "reference": "Jean 3:16",
    "source": "bible",
}

_SLIDER_STYLE = f"""
    QSlider {{
        min-height: 24px;
    }}
    QSlider::groove:horizontal {{
        height: 6px;
        background: {Colors.BG_ELEVATED};
        border-radius: 3px;
    }}
    QSlider::handle:horizontal {{
        width: 20px; height: 20px;
        margin: -7px 0;
        background: {Colors.ACCENT_PRIMARY};
        border: 2px solid #fff;
        border-radius: 10px;
    }}
    QSlider::sub-page:horizontal {{
        background: {Colors.ACCENT_PRIMARY};
        border-radius: 3px;
    }}
"""


class HdmiSettingsDialog(QDialog):
    """Réglages de la sortie HDMI vers un mélangeur (ATEM, Roland…).

    Source d'incrustation chroma key : fond à la couleur de clé + section
    texte au style de la sortie OBS. Chaque changement est appliqué en
    direct (la fenêtre s'ouvre, se ferme ou se re-cible immédiatement) ;
    Annuler revient à l'état d'origine. L'incrustation elle-même est
    ajustable — couleur de clé, taille du texte, position verticale,
    bandeau d'annonces — avec aperçu fidèle temps réel.
    """

    hdmiChanged = pyqtSignal(HdmiSettings)
    mireToggled = pyqtSignal()

    def __init__(
        self,
        settings: HdmiSettings,
        presentation_dir: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sortie HDMI / mixeur")
        self.setMinimumSize(580, 620)
        self.resize(640, 880)
        self.setStyleSheet(DIALOG_STYLE)

        self._presentation_dir = Path(presentation_dir) if presentation_dir else None
        self._preview_slide_mtime = -1.0
        self._preview_cfg_mtime = -1.0

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Header ──
        header = QFrame(self)
        header.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_SECONDARY};
                border-bottom: 1px solid {Colors.BORDER_DEFAULT};
            }}
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(24, 16, 24, 14)
        h_layout.setSpacing(14)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(app_icon("cast.svg").pixmap(28, 28))
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        h_layout.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Sortie HDMI / mixeur")
        title.setStyleSheet(
            f"font-size: {Typography.SIZE_TITLE}px; font-weight: 700; "
            f"color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;"
        )
        title_col.addWidget(title)
        subtitle = QLabel("Source d'incrustation pour ATEM, Roland V/AV et autres mélangeurs")
        subtitle.setStyleSheet(
            f"font-size: {Typography.SIZE_CONTROL}px; color: {Colors.TEXT_SECONDARY}; "
            "background: transparent; border: none;"
        )
        title_col.addWidget(subtitle)
        h_layout.addLayout(title_col, 1)
        main_layout.addWidget(header)

        # ── Contenu défilant ──
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(14)

        howto = QLabel(
            "Brancher une sortie HDMI du PC sur une entrée du mélangeur, régler "
            "cet écran en 1920×1080 dans Windows (mode Étendre), puis activer la "
            "clé chroma sur cette entrée dans le mélangeur : seul le texte "
            "apparaît sur le programme."
        )
        howto.setWordWrap(True)
        howto.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY};
            background: {Colors.BG_TERTIARY};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: 10px;
            padding: 12px 14px;
            font-size: {Typography.SIZE_CONTROL}px;
        """)
        layout.addWidget(howto)

        # ═══════ Section: Incrustation (aperçu + réglages) ═══════
        overlay_section = SettingSection("Incrustation", "palette.svg")

        self._preview = QLabel()
        self._preview.setAlignment(
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self._preview.setMinimumSize(440, 248)  # 16:9, tient dans la carte
        self._preview.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._preview.setStyleSheet(f"""
            QLabel {{
                background: #000;
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 10px;
            }}
        """)
        overlay_section.addWidget(self._preview)

        self._preview_hint = QLabel("")
        self._preview_hint.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; background: transparent; border: none; "
            f"font-size: {Typography.SIZE_CONTROL}px;"
        )
        overlay_section.addWidget(self._preview_hint)

        self._key_color = QComboBox()
        self._key_color.addItem("Vert — standard", "green")
        self._key_color.addItem("Magenta — si la scène contient du vert", "magenta")
        self._key_color.addItem("Bleu — si la scène contient du vert et du magenta", "blue")
        idx = self._key_color.findData(settings.key_color or "green")
        self._key_color.setCurrentIndex(max(idx, 0))
        self._key_color.currentIndexChanged.connect(self._on_change)
        overlay_section.addRow(
            "Couleur de clé",
            self._key_color,
            "Couleur supprimée par le chroma key du mélangeur",
        )
        _style_combo(self._key_color)

        self._text_scale = QSlider(Qt.Orientation.Horizontal)
        self._text_scale.setRange(60, 180)
        self._text_scale.setSingleStep(5)
        self._text_scale.setValue(int(settings.text_scale or 100))
        self._text_scale.setMinimumWidth(240)
        self._text_scale.setStyleSheet(_SLIDER_STYLE)
        self._text_scale_label = QLabel(f"{int(settings.text_scale or 100)} %")
        self._text_scale_label.setFixedWidth(52)
        self._text_scale_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._text_scale_label.setStyleSheet(
            f"font-size: {Typography.SIZE_NUMBER}px; color: {Colors.TEXT_SECONDARY}; "
            "border: none;"
        )
        scale_row = QWidget()
        scale_row.setStyleSheet("background: transparent;")
        scale_hl = QHBoxLayout(scale_row)
        scale_hl.setContentsMargins(0, 0, 0, 0)
        scale_hl.setSpacing(8)
        scale_hl.addWidget(self._text_scale)
        scale_hl.addWidget(self._text_scale_label)
        self._text_scale.valueChanged.connect(
            lambda v: self._text_scale_label.setText(f"{v} %")
        )
        self._text_scale.valueChanged.connect(self._on_change)
        overlay_section.addRow(
            "Taille du texte",
            scale_row,
            "Agrandit ou réduit la section texte sans toucher au style OBS",
        )

        self._offset_y = QSlider(Qt.Orientation.Horizontal)
        self._offset_y.setRange(-300, 300)
        self._offset_y.setSingleStep(10)
        self._offset_y.setValue(int(settings.offset_y or 0))
        self._offset_y.setMinimumWidth(240)
        self._offset_y.setStyleSheet(_SLIDER_STYLE)
        self._offset_y_label = QLabel(self._format_offset(int(settings.offset_y or 0)))
        self._offset_y_label.setFixedWidth(52)
        self._offset_y_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._offset_y_label.setStyleSheet(
            f"font-size: {Typography.SIZE_NUMBER}px; color: {Colors.TEXT_SECONDARY}; "
            "border: none;"
        )
        offset_row = QWidget()
        offset_row.setStyleSheet("background: transparent;")
        offset_hl = QHBoxLayout(offset_row)
        offset_hl.setContentsMargins(0, 0, 0, 0)
        offset_hl.setSpacing(8)
        offset_hl.addWidget(self._offset_y)
        offset_hl.addWidget(self._offset_y_label)
        self._offset_y.valueChanged.connect(
            lambda v: self._offset_y_label.setText(self._format_offset(v))
        )
        self._offset_y.valueChanged.connect(self._on_change)
        overlay_section.addRow(
            "Position verticale",
            offset_row,
            "Décalage fin du bandeau (px @1080) pour éviter un habillage caméra",
        )


        layout.addWidget(overlay_section)

        # ═══════ Section: Sortie ═══════
        output_section = SettingSection("Sortie", "cast.svg")

        self._enabled = QCheckBox("Sortie HDMI activée")
        self._enabled.setChecked(bool(settings.enabled))
        self._enabled.toggled.connect(self._on_change)
        output_section.addWidget(self._enabled)

        self._screen = QComboBox()
        self._screen.addItem("Automatique (écran secondaire)", "auto")
        for index, screen in enumerate(QGuiApplication.screens(), start=1):
            geo = screen.geometry()
            screen_name = str(screen.name() or f"Écran {index}")
            self._screen.addItem(
                f"{screen_name} — {geo.width()}×{geo.height()}", screen_name
            )
        idx = self._screen.findData(settings.screen or "auto")
        self._screen.setCurrentIndex(max(idx, 0))
        self._screen.currentIndexChanged.connect(self._on_change)
        output_section.addRow("Écran cible", self._screen)
        _style_combo(self._screen)

        self._screen_hint = QLabel("")
        self._screen_hint.setWordWrap(True)
        self._screen_hint.setStyleSheet(
            f"color: {Colors.ACCENT_WARNING}; background: transparent; "
            f"border: none; font-size: {Typography.SIZE_CONTROL}px;"
        )
        output_section.addWidget(self._screen_hint)

        self._letterbox = QCheckBox("Marges de clé 16:9 si l'écran n'est pas 16:9")
        self._letterbox.setChecked(bool(settings.letterbox))
        self._letterbox.toggled.connect(self._on_change)
        output_section.addWidget(self._letterbox)
        layout.addWidget(output_section)

        # ═══════ Section: Vérification ═══════
        check_section = SettingSection("Vérification", "check-circle.svg")

        mire_row = QHBoxLayout()
        mire_row.setSpacing(10)
        self._mire_btn = QPushButton("Afficher / masquer la mire")
        self._mire_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mire_btn.setToolTip(
            "Mire de calibrage (F8) : barres, rampe de gris, zones utiles et "
            "pastilles de couleur pour prélever la pipette du mélangeur."
        )
        self._mire_btn.clicked.connect(self.mireToggled.emit)
        mire_row.addWidget(self._mire_btn)
        mire_row.addStretch(1)
        check_section.addWidget(self._wrap_layout(mire_row))

        self._status = QLabel("Inactive")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; background: transparent; "
            f"border: none; font-size: {Typography.SIZE_CONTROL}px;"
        )
        check_section.addWidget(self._status)
        layout.addWidget(check_section)

        note = QLabel(
            "Le style du bandeau (police, couleurs, disposition) suit la sortie "
            "OBS — Diffusion & OBS → Style bandeau. Le masquage « B » vide "
            "l'incrustation ; la mire F8 sert au calibrage du mélangeur."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; background: transparent; "
            f"border: none; font-size: {Typography.SIZE_CONTROL}px;"
        )
        layout.addWidget(note)

        layout.addStretch(1)
        scroll.setWidget(content)
        main_layout.addWidget(scroll, 1)

        # ── Boutons ──
        btn_frame = QFrame(self)
        btn_frame.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_SECONDARY};
                border-top: 1px solid {Colors.BORDER_DEFAULT};
            }}
        """)
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(24, 12, 24, 12)
        btn_layout.addStretch(1)

        reset_btn = QPushButton("Réglages par défaut")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 8px;
                padding: 8px 18px;
                color: {Colors.TEXT_SECONDARY};
                font-size: {Typography.SIZE_CONTROL}px;
            }}
            QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; border-color: {Colors.BORDER_FOCUS}; }}
        """)
        reset_btn.clicked.connect(self._reset_overlay)
        btn_layout.addWidget(reset_btn)

        cancel_btn = QPushButton("Annuler")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 8px;
                padding: 8px 22px;
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_CONTROL}px;
            }}
            QPushButton:hover {{ background: {Colors.SURFACE_ACTIVE}; border-color: {Colors.BORDER_FOCUS}; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Enregistrer")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ACCENT_PRIMARY};
                border: none;
                border-radius: 8px;
                padding: 8px 22px;
                color: {Colors.PROJECT_BUTTON_TEXT};
                font-size: {Typography.SIZE_CONTROL}px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {Colors.ACCENT_LIGHT}; }}
        """)
        save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(save_btn)
        main_layout.addWidget(btn_frame)

        # Aperçu live : re-rendu à chaque changement + suivi de la slide.
        # Les glissements de slider sont regroupés (debounce) pour ne pas
        # composer une image par pixel parcouru.
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self._emit_changed)

        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(1000)
        self._preview_timer.timeout.connect(self._refresh_preview_if_stale)
        self._preview_timer.start()

        self._refresh_hints()
        self._render_preview()

    # ── Aperçu temps réel ─────────────────────────────────────────────

    @staticmethod
    def _format_offset(value: int) -> str:
        value = int(value or 0)
        return f"+{value} px" if value > 0 else f"{value} px"

    @staticmethod
    def _read_json(path: Path | None) -> dict[str, Any] | None:
        try:
            if path is None or not path.is_file():
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    @staticmethod
    def _mtime(path: Path | None) -> float:
        try:
            return path.stat().st_mtime if path is not None and path.exists() else -1.0
        except Exception:
            return -1.0

    def _refresh_preview_if_stale(self) -> None:
        slide_mtime = self._mtime(
            self._presentation_dir / "slide.json" if self._presentation_dir else None
        )
        cfg_mtime = self._mtime(
            self._presentation_dir / "obs-config.json" if self._presentation_dir else None
        )
        if slide_mtime != self._preview_slide_mtime or cfg_mtime != self._preview_cfg_mtime:
            self._render_preview()

    def _render_preview(self) -> None:
        """Aperçu fidèle de la sortie : couleur de clé + section texte."""
        settings = self.read_settings()
        cfg = self._read_json(
            self._presentation_dir / "obs-config.json" if self._presentation_dir else None
        )
        slide = self._read_json(
            self._presentation_dir / "slide.json" if self._presentation_dir else None
        )
        demo = not isinstance(slide, dict) or bool(
            slide.get("hidden")
            or not (
                str(slide.get("text") or "").strip()
                or str(slide.get("reference") or "").strip()
            )
        )
        if demo:
            slide = dict(_DEMO_SLIDE)

        key = chroma_key_rgb(settings.key_color)
        # Rendu à la résolution de sortie réelle puis réduction : les
        # réglages en pixels (marges, offsets, tailles) doivent apparaître
        # à l'échelle de l'écran, comme sur la sortie HDMI.
        img = render_obs_overlay_on_color(
            cfg,
            slide,
            bg_rgba=(*key, 255),
            width=1920,
            height=1080,
            text_scale=settings.text_scale / 100.0,
            offset_y=settings.offset_y,
        )
        rgb = img.convert("RGB")
        data = rgb.tobytes()
        qimg = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg.copy())
        self._preview.setPixmap(
            pixmap.scaled(
                self._preview.width(),
                self._preview.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        source = "texte de démonstration" if demo else "slide en cours"
        self._preview_hint.setText(f"Aperçu fidèle de la sortie · {source}")
        if self._presentation_dir is not None:
            self._preview_slide_mtime = self._mtime(
                self._presentation_dir / "slide.json"
            )
            self._preview_cfg_mtime = self._mtime(
                self._presentation_dir / "obs-config.json"
            )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # L'aperçu suit la largeur de la fenêtre (16:9 conservé au rendu) ;
        # différé d'un cycle pour laisser le layout mettre la QLabel à jour.
        if self._preview.pixmap() is not None:
            QTimer.singleShot(0, self._render_preview)

    def _reset_overlay(self) -> None:
        self._key_color.setCurrentIndex(0)
        self._text_scale.setValue(100)
        self._offset_y.setValue(0)

    # ── Lecture / signaux ─────────────────────────────────────────────

    @staticmethod
    def _wrap_layout(inner: QHBoxLayout) -> QWidget:
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent; border: none;")
        inner.setContentsMargins(0, 0, 0, 0)
        wrap.setLayout(inner)
        return wrap

    def read_settings(self) -> HdmiSettings:
        return HdmiSettings(
            enabled=self._enabled.isChecked(),
            screen=str(self._screen.currentData() or "auto"),
            letterbox=self._letterbox.isChecked(),
            key_color=str(self._key_color.currentData() or "green"),
            text_scale=int(self._text_scale.value()),
            offset_y=int(self._offset_y.value()),
        ).sanitized()

    def _on_change(self, *_args) -> None:
        self._refresh_hints()
        self._debounce.start()

    def _emit_changed(self) -> None:
        self._render_preview()
        self.hdmiChanged.emit(self.read_settings())

    def set_live_status(self, text: str) -> None:
        self._status.setText(text)

    def set_mire_available(self, available: bool) -> None:
        self._mire_btn.setEnabled(bool(available))

    def _refresh_hints(self) -> None:
        self.set_mire_available(self._enabled.isChecked())
        name = str(self._screen.currentData() or "auto")
        if name == "auto":
            self._screen_hint.setText("")
            return
        screen = next(
            (
                s
                for s in QGuiApplication.screens()
                if str(s.name() or "") == name
            ),
            None,
        )
        if screen is None:
            self._screen_hint.setText("Cet écran n'est plus détecté.")
            return
        geo = screen.geometry()
        if geo.width() == 1920 and geo.height() == 1080:
            self._screen_hint.setText("")
            return
        self._screen_hint.setText(
            f"{geo.width()}×{geo.height()} : réglez cette sortie sur "
            "1920×1080 dans Windows pour un mélangeur."
        )
