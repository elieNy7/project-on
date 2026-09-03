from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSignalBlocker, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.icons import app_icon
from app.ui.slide_canvas import SlideCanvas
from app.ui.theme import Colors, Radius, Typography, get_theme
from app.utils.translations import tr


# ═══════════════════════════════════════════════════════════════════
#  Navigation arrow (circle button)
# ═══════════════════════════════════════════════════════════════════
class _NavArrowButton(QPushButton):
    def __init__(self, icon_name: str, tooltip: str, parent=None) -> None:
        super().__init__(parent)
        self.setIcon(app_icon(icon_name, Colors.TEXT_PRIMARY))
        self.setIconSize(QSize(18, 18))
        self.setToolTip(tooltip)
        self.setFixedSize(40, 40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 20px;
                color: {Colors.TEXT_PRIMARY};
            }}
            QPushButton:hover {{
                background: {Colors.ACCENT_GLOW};
                color: {Colors.ACCENT_LIGHT};
                border-color: {Colors.ACCENT_GLOW_STRONG};
            }}
            QPushButton:pressed {{
                background: {Colors.ACCENT_GLOW_STRONG};
            }}
        """)


# ═══════════════════════════════════════════════════════════════════
#  Pill control button
# ═══════════════════════════════════════════════════════════════════
class PreviewControlButton(QPushButton):
    """Premium action button used in the presenter preview toolbar."""

    def __init__(
        self, icon_name: str, tooltip: str, parent=None, text: str = ""
    ) -> None:
        super().__init__(text, parent)
        self._icon_name = icon_name
        self.setIcon(app_icon(icon_name, Colors.TEXT_PRIMARY))
        self.setIconSize(QSize(16, 16))
        self.setToolTip(tooltip)
        if text:
            self.setFixedHeight(40)
            padding = "padding: 0 16px;"
            # La feuille de style passe le libellé en MAJUSCULES au rendu ;
            # mesurer la version uppercase pour ne jamais tronquer le texte.
            self.ensurePolished()
            upper_width = self.fontMetrics().horizontalAdvance(text.upper())
            self.setMinimumWidth(max(132, upper_width + 16 * 2 + 20 + 8))
        else:
            self.setFixedSize(40, 40)
            padding = ""

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._padding = padding
        self.setStyleSheet(self._build_style())

    def _build_style(
        self,
        *,
        checked_bg: str = Colors.ACCENT_GLOW_STRONG,
        checked_border: str = Colors.ACCENT_PRIMARY,
        checked_text: str = Colors.ACCENT_LIGHT,
    ) -> str:
        return f"""
            QPushButton {{
                background: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 20px;
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_CONTROL}px;
                font-weight: 700;
                letter-spacing: 0;
                text-transform: uppercase;
                {self._padding}
            }}
            QPushButton:hover {{
                background: {Colors.SURFACE_HOVER};
                color: {Colors.TEXT_PRIMARY};
                border-color: {Colors.BORDER_HOVER};
            }}
            QPushButton:pressed {{
                background: {Colors.SURFACE_ACTIVE};
            }}
            QPushButton:checked {{
                background: {checked_bg};
                border: 1px solid {checked_border};
                color: {checked_text};
            }}
        """


# ═══════════════════════════════════════════════════════════════════
#  Preview Panel
# ═══════════════════════════════════════════════════════════════════
class PreviewPanel(QFrame):
    hideToggled = pyqtSignal(bool)
    prevRequested = pyqtSignal()
    nextRequested = pyqtSignal()
    projectToggled = pyqtSignal(bool)
    # Édition rapide de la slide en direct
    quickEditRequested = pyqtSignal()
    # Texte rapide : (titre, textes, découpage)
    quickTextRequested = pyqtSignal(str, list, bool)
    # Position de la référence sur la projection : True = en haut
    referencePositionToggled = pyqtSignal(bool)
    # Contrôle vidéo opérateur : "play" | "pause" | "stop"
    videoControlRequested = pyqtSignal(str)
    # Écran scène : on/off + message opérateur
    stageToggled = pyqtSignal(bool)
    stageMessageRequested = pyqtSignal()
    # Boucle d'annonces : lancer / arrêter
    announcementsToggled = pyqtSignal()

    def __init__(self, parent=None, settings=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setObjectName("PreviewPanel")
        self._is_hidden = False
        self._has_content = False
        self._current_row = -1
        self._total_slides = 0
        self._current_reference = ""
        self._current_image_path = ""
        self._project_active = False
        # Rendu fidèle : canvas hors écran (même moteur que la projection).
        self._canvas: SlideCanvas | None = None
        self._canvas_cfg: dict | None = None
        self._presentation_dir = None
        self._render_pixmap_full = None
        self._is_light_theme = get_theme() == "light"
        if self._is_light_theme:
            self._stage_text_rgb = (23, 32, 51)
            self._stage_ref_rgb = (183, 121, 31)
            self._stage_empty_color = "rgba(100, 116, 139, 0.38)"
            self._stage_meta_color = "rgba(71, 85, 105, 0.62)"
            self._stage_chip_bg = "rgba(20, 28, 42, 0.07)"
            self._stage_counter_bg = "rgba(255, 255, 255, 0.72)"
            self._stage_border = f"1px solid {Colors.BORDER_DEFAULT}"
        else:
            self._stage_text_rgb = (248, 250, 252)
            self._stage_ref_rgb = (240, 184, 91)
            self._stage_empty_color = "rgba(145, 162, 184, 0.42)"
            self._stage_meta_color = "rgba(203, 213, 225, 0.54)"
            self._stage_chip_bg = "rgba(203, 213, 225, 0.09)"
            self._stage_counter_bg = "rgba(0, 0, 0, 0.24)"
            self._stage_border = f"1px solid {Colors.BORDER_DEFAULT}"

        self.setStyleSheet("")

        # ── Header ────────────────────────────────────────────────
        self.header = QFrame(self)
        self.header.setObjectName("TopBar")
        self.header.setFixedHeight(56)
        self.header.setStyleSheet(f"""
            QFrame#TopBar {{
                background: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: {Radius.LG}px;
            }}
        """)

        header_lay = QHBoxLayout(self.header)
        header_lay.setContentsMargins(16, 0, 16, 0)
        header_lay.setSpacing(10)
        header_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        icon_chip = QFrame(self.header)
        icon_chip.setFixedSize(30, 30)
        icon_chip.setStyleSheet(f"""
            background: {Colors.ACCENT_GLOW};
            border: 1px solid {Colors.ACCENT_GLOW_STRONG};
            border-radius: 11px;
        """)
        icon_chip_layout = QHBoxLayout(icon_chip)
        icon_chip_layout.setContentsMargins(7, 7, 7, 7)
        icon_chip_layout.setSpacing(0)

        icon_label = QLabel(icon_chip)
        icon_label.setPixmap(app_icon("monitor.svg", Colors.ACCENT_LIGHT).pixmap(15, 15))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_chip_layout.addWidget(icon_label)
        header_lay.addWidget(icon_chip, 0, Qt.AlignmentFlag.AlignVCenter)

        title_wrap = QVBoxLayout()
        title_wrap.setContentsMargins(0, 0, 0, 0)
        title_wrap.setSpacing(1)

        title = QLabel(tr("preview"), self.header)
        title.setStyleSheet(
            f"font-size: {Typography.SIZE_SECTION}px; font-weight: 800; color: {Colors.TEXT_PRIMARY};"
            f"text-transform: uppercase; letter-spacing: 0;"
        )
        title_wrap.addWidget(title)

        self._program_title_label = QLabel(tr("projection"), self.header)
        self._program_title_label.setStyleSheet(
            f"font-size: {Typography.SIZE_META}px; color: {Colors.TEXT_MUTED};"
            "letter-spacing: 0;"
        )
        title_wrap.addWidget(self._program_title_label)
        header_lay.addLayout(title_wrap, 1)
        header_lay.addStretch()

        self._mode_badge = QLabel("PREVIEW", self.header)
        self._mode_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mode_badge.setFixedHeight(24)
        self._mode_badge.setMinimumWidth(72)
        self._mode_badge.setMaximumWidth(120)
        self._update_mode_badge()
        header_lay.addWidget(self._mode_badge, 0, Qt.AlignmentFlag.AlignVCenter)

        # ── Slide screen ──────────────────────────────────────────
        self._bg_live = (
            "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 #ffffff, stop:0.48 #f2f5fa, stop:1 #e6edf6)"
            if self._is_light_theme
            else "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 #0f1c2e, stop:0.48 #0a1424, stop:1 #04070d)"
        )
        self._bg_hidden = (
            "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 #fff1f2, stop:1 #f8d7da)"
            if self._is_light_theme
            else "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2e1520, stop:1 #0e090d)"
        )

        self._slide_frame = QFrame()
        self._slide_frame.setObjectName("SlideScreen")
        self._slide_frame.setStyleSheet(self._slide_screen_style(self._bg_live))

        frame_layout = QVBoxLayout(self._slide_frame)
        self._frame_layout = frame_layout
        frame_layout.setContentsMargins(18, 18, 18, 16)
        frame_layout.setSpacing(10)

        self._stage_top = QFrame(self._slide_frame)
        self._stage_top.setStyleSheet("background: transparent;")
        stage_top_layout = QHBoxLayout(self._stage_top)
        stage_top_layout.setContentsMargins(0, 0, 0, 0)
        stage_top_layout.setSpacing(8)

        self._live_badge = QLabel(tr("live").upper(), self._stage_top)
        self._live_badge.setStyleSheet(
            f"""
            background: rgba(86,214,129,0.18);
            border: none;
            color: #dfffe9;
            padding: 4px 10px;
            border-radius: 11px;
            font-size: {Typography.SIZE_NUMBER}px;
            font-weight: 800;
            letter-spacing: 0;
            """,
        )
        self._live_badge.hide()
        stage_top_layout.addWidget(self._live_badge, 0, Qt.AlignmentFlag.AlignLeft)

        self._status_chip = QLabel(tr("waiting"), self._stage_top)
        self._status_chip.setStyleSheet(
            f"""
            background: {self._stage_chip_bg};
            border: none;
            color: {Colors.TEXT_SECONDARY};
            padding: 4px 10px;
            border-radius: 11px;
            font-size: {Typography.SIZE_NUMBER}px;
            font-weight: 700;
            letter-spacing: 0;
            """
        )
        stage_top_layout.addWidget(self._status_chip, 0, Qt.AlignmentFlag.AlignLeft)
        stage_top_layout.addStretch()
        frame_layout.addWidget(self._stage_top, 0)

        # Main text
        self.slide_view = QLabel("", self._slide_frame)
        self.slide_view.setObjectName("SlideText")
        self.slide_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.slide_view.setWordWrap(True)
        frame_layout.addWidget(self.slide_view, 1)

        # Empty state — shown when nothing is loaded on the program
        self._empty_state = QWidget(self._slide_frame)
        self._empty_state.setStyleSheet("background: transparent;")
        empty_lay = QVBoxLayout(self._empty_state)
        empty_lay.setContentsMargins(0, 0, 0, 0)
        empty_lay.setSpacing(10)
        empty_lay.addStretch(1)

        empty_icon = QLabel(self._empty_state)
        empty_icon.setPixmap(app_icon("monitor.svg", Colors.TEXT_MUTED).pixmap(42, 42))
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon.setStyleSheet("background: transparent;")
        empty_lay.addWidget(empty_icon)

        empty_title = QLabel(tr("stage_empty"), self._empty_state)
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_title.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_SECONDARY};"
            f" font-size: {Typography.SIZE_SECTION}px; font-weight: 600;"
        )
        empty_lay.addWidget(empty_title)

        empty_hint = QLabel(tr("stage_empty_hint"), self._empty_state)
        empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_hint.setWordWrap(True)
        empty_hint.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED};"
            f" font-size: {Typography.SIZE_META}px;"
        )
        empty_lay.addWidget(empty_hint)
        empty_lay.addStretch(1)
        # Au démarrage aucun programme n'est chargé : montrer l'invite tout de suite.
        self._empty_state.setVisible(True)
        self.slide_view.setVisible(False)
        frame_layout.addWidget(self._empty_state, 1)

        # Image display (shown instead of text for image slides)
        self._image_label = QLabel("", self._slide_frame)
        self._image_label.setObjectName("SlideImage")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._image_label.setStyleSheet("background: transparent; border: none;")
        self._image_label.setVisible(False)
        frame_layout.addWidget(self._image_label, 1)

        # Reference
        self._ref_label = QLabel("", self._slide_frame)
        self._ref_label.setObjectName("SlideRef")
        self._ref_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ref_label.setWordWrap(True)
        frame_layout.addWidget(self._ref_label, 0)

        self._stage_footer = QFrame(self._slide_frame)
        self._stage_footer.setStyleSheet("background: transparent;")
        stage_footer_layout = QHBoxLayout(self._stage_footer)
        stage_footer_layout.setContentsMargins(0, 0, 0, 0)
        stage_footer_layout.setSpacing(10)

        self._scene_label = QLabel("SCENE 00", self._stage_footer)
        self._scene_label.setStyleSheet(
            f"""
            color: {self._stage_meta_color};
            font-size: {Typography.SIZE_NUMBER}px;
            font-weight: 700;
            letter-spacing: 0;
            """
        )
        stage_footer_layout.addWidget(self._scene_label)
        stage_footer_layout.addStretch()

        self._counter_label = QLabel("", self._stage_footer)
        self._counter_label.setStyleSheet(
            f"""
            color: {Colors.TEXT_SECONDARY};
            font-size: {Typography.SIZE_NUMBER}px;
            font-weight: 800;
            letter-spacing: 0.7px;
            background: {self._stage_counter_bg};
            border: none;
            border-radius: 11px;
            padding: 4px 10px;
            """
        )
        stage_footer_layout.addWidget(self._counter_label, 0, Qt.AlignmentFlag.AlignRight)
        frame_layout.addWidget(self._stage_footer, 0)

        # Subtle text shadows
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setOffset(0, 1)
        shadow.setBlurRadius(10)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.slide_view.setGraphicsEffect(shadow)

        ref_shadow = QGraphicsDropShadowEffect(self)
        ref_shadow.setOffset(0, 1)
        ref_shadow.setBlurRadius(6)
        ref_shadow.setColor(QColor(0, 0, 0, 160))
        self._ref_label.setGraphicsEffect(ref_shadow)

        self._slide_frame.resizeEvent = self._on_slide_resize

        # ── Panneau « Suivant » : le slide qui viendra après celui en direct ──
        self._next_frame = QFrame(self)
        self._next_frame.setObjectName("NextSlideBar")
        self._next_frame.setStyleSheet(f"""
            QFrame#NextSlideBar {{
                background: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: {Radius.MD}px;
            }}
        """)
        self._next_frame.setFixedHeight(40)
        next_lay = QHBoxLayout(self._next_frame)
        next_lay.setContentsMargins(14, 0, 14, 0)
        next_lay.setSpacing(10)

        next_badge = QLabel("SUIVANT", self._next_frame)
        next_badge.setStyleSheet(
            f"""
            color: {Colors.ACCENT_LIGHT};
            background: {Colors.ACCENT_GLOW};
            border: none;
            border-radius: 8px;
            padding: 2px 8px;
            font-size: {Typography.SIZE_2XS}px;
            font-weight: 800;
            letter-spacing: 0.6px;
            """
        )
        next_lay.addWidget(next_badge)

        self._next_ref_label = QLabel("", self._next_frame)
        self._next_ref_label.setStyleSheet(
            f"""
            color: {Colors.ACCENT_LIGHT};
            background: transparent;
            font-size: {Typography.SIZE_META}px;
            font-weight: 700;
            """
        )
        self._next_ref_label.setMaximumWidth(260)
        next_lay.addWidget(self._next_ref_label)

        self._next_text_label = QLabel("", self._next_frame)
        self._next_text_label.setStyleSheet(
            f"""
            color: {Colors.TEXT_MUTED};
            background: transparent;
            font-size: {Typography.SIZE_META}px;
            """
        )
        next_lay.addWidget(self._next_text_label, 1)

        self._next_frame.hide()

        # ── Controls bar ──────────────────────────────────────────
        self.controls = QFrame(self)
        self.controls.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: {Radius.LG}px;
            }}
        """)
        controls_layout = QHBoxLayout(self.controls)
        controls_layout.setContentsMargins(12, 10, 12, 10)
        controls_layout.setSpacing(6)

        self._prev_button = _NavArrowButton(
            "chevron-left.svg", tr("previous"), self.controls
        )
        self._next_button = _NavArrowButton(
            "chevron-right.svg", tr("next"), self.controls
        )

        # Console capsule
        self.console_frame = QFrame(self.controls)
        self.console_frame.setStyleSheet(f"""
            background: {Colors.BG_SECONDARY};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: 22px;
        """)
        console_layout = QHBoxLayout(self.console_frame)
        console_layout.setContentsMargins(6, 6, 6, 6)
        console_layout.setSpacing(6)

        self._project_button = PreviewControlButton(
            "cast.svg", tr("project"), self.console_frame, text=tr("project")
        )
        self._project_button.setCheckable(True)
        self._project_button.setObjectName("ProjectButton")

        self._hide_button = PreviewControlButton(
            "eye.svg", tr("hide"), self.console_frame, text=tr("hide")
        )
        self._hide_button.setCheckable(True)
        self._hide_button.setObjectName("HideButton")
        self._hide_button_base_style = self._hide_button.styleSheet()
        self._hide_button_hidden_style = self._hide_button._build_style(
            checked_bg="rgba(229,83,75,0.18)",
            checked_border="rgba(229,83,75,0.38)",
            checked_text="#ffb4ae",
        )
        self._hide_button.setStyleSheet(
            (
                self._hide_button_hidden_style
                if self._is_hidden
                else self._hide_button_base_style
            ),
        )

        console_layout.addWidget(self._project_button)
        console_layout.addWidget(self._hide_button)

        # Position de la référence (en haut / en bas) — réglage rapide, sans
        # passer par le dialogue des réglages de projection.
        self._ref_pos_button = PreviewControlButton(
            "chevron-down.svg", tr("reference_position"), self.console_frame
        )
        self._ref_pos_button.setCheckable(True)
        self._ref_pos_button.setToolTip(tr("reference_position_tooltip"))
        self._ref_pos_button.clicked.connect(self._on_ref_pos_clicked)
        console_layout.addWidget(self._ref_pos_button)

        # Contrôles vidéo — visibles seulement quand une vidéo est en direct.
        self._video_play_button = PreviewControlButton(
            "play.svg", tr("video_play"), self.console_frame, text=tr("video_play")
        )
        self._video_play_button.setCheckable(True)
        self._video_play_button.setToolTip(tr("video_play_tooltip"))
        self._video_play_button.clicked.connect(self._on_video_play_clicked)
        console_layout.addWidget(self._video_play_button)

        self._video_stop_button = PreviewControlButton(
            "x-circle.svg", tr("video_stop"), self.console_frame, text=tr("video_stop")
        )
        self._video_stop_button.setToolTip(tr("video_stop_tooltip"))
        self._video_stop_button.clicked.connect(
            lambda: self.videoControlRequested.emit("stop")
        )
        console_layout.addWidget(self._video_stop_button)

        self._video_play_button.hide()
        self._video_stop_button.hide()

        # Écran scène : activation + message opérateur.
        self._stage_button = PreviewControlButton(
            "users.svg", tr("stage_toggle"), self.console_frame,
            text=tr("stage_display"),
        )
        self._stage_button.setCheckable(True)
        self._stage_button.toggled.connect(self.stageToggled.emit)
        console_layout.addWidget(self._stage_button)

        self._stage_message_button = PreviewControlButton(
            "type.svg", tr("stage_send_message"), self.console_frame,
            text=tr("stage_send_message"),
        )
        self._stage_message_button.clicked.connect(self.stageMessageRequested.emit)
        console_layout.addWidget(self._stage_message_button)

        # Boucle d'annonces : bouton bascule (rouge quand actif).
        self._announce_button = PreviewControlButton(
            "megaphone.svg", tr("announcement_loop"), self.console_frame,
            text=tr("announcement_loop_start"),
        )
        self._announce_button.setCheckable(True)
        self._announce_button.clicked.connect(
            lambda: self.announcementsToggled.emit()
        )
        console_layout.addWidget(self._announce_button)

        # Lecteur vidéo de l'APERÇU (miniature, mutée) — créé paresseusement.
        self._video_preview = None  # QVideoWidget | False (indisponible)
        self._video_preview_player = None
        self._video_preview_audio = None
        self._video_preview_path = ""

        # Édition rapide de la slide en direct (utile pour corriger une faute
        # pendant le culte) — active seulement quand du contenu est chargé.
        self._edit_button = PreviewControlButton(
            "edit-3.svg", tr("quick_edit"), self.console_frame
        )
        self._edit_button.setToolTip(tr("quick_edit"))
        self._edit_button.setEnabled(False)
        self._edit_button.clicked.connect(self.quickEditRequested.emit)
        console_layout.addWidget(self._edit_button)

        controls_layout.addStretch(1)
        controls_layout.addWidget(self._prev_button, 0, Qt.AlignmentFlag.AlignVCenter)
        controls_layout.addWidget(self.console_frame, 0, Qt.AlignmentFlag.AlignVCenter)
        controls_layout.addWidget(self._next_button, 0, Qt.AlignmentFlag.AlignVCenter)
        controls_layout.addStretch(1)

        # Connections
        self._prev_button.clicked.connect(self.prevRequested.emit)
        self._next_button.clicked.connect(self.nextRequested.emit)
        self._hide_button.clicked.connect(self._on_hide_clicked)
        self._project_button.toggled.connect(self.projectToggled.emit)

        # Shortcut — Espace masque/affiche la sortie, sauf quand le focus est
        # sur un contrôle interactif (le bouton focalisé doit recevoir son Espace).
        self._hide_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self._hide_shortcut.activated.connect(self._on_space_shortcut)

        # Main Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.header)
        layout.addWidget(self._slide_frame, 1)
        layout.addWidget(self._next_frame)
        layout.addWidget(self.controls)

        # Position initiale de la référence conforme aux réglages courants.
        self.set_settings(self._settings)

    # ──────────────────────────────────────────────────────────────
    def set_next_slide(self, reference: str, text: str) -> None:
        """Affiche le slide à venir dans le bandeau « SUIVANT » (ou le masque)."""
        ref = str(reference or "").strip()
        body = " ".join(str(text or "").split())
        if not ref and not body:
            self._next_frame.hide()
            return
        self._next_ref_label.setText(ref)
        self._next_ref_label.setVisible(bool(ref))
        if len(body) > 90:
            body = body[:87] + "…"
        self._next_text_label.setText(body)
        self._next_frame.show()

    # ──────────────────────────────────────────────────────────────
    def _slide_screen_style(self, background: str) -> str:
        return f"""
            QFrame#SlideScreen {{
                background: {background};
                border-radius: 18px;
                border: {self._stage_border};
            }}
        """

    @staticmethod
    def _rgba(rgb: tuple[int, int, int], alpha: float) -> str:
        r, g, b = rgb
        return f"rgba({r}, {g}, {b}, {max(0.0, min(1.0, alpha)):.2f})"

    def _on_slide_resize(self, event) -> None:
        if event:
            QFrame.resizeEvent(self._slide_frame, event)
        self._refresh_image_pixmap()

    def set_stage_active(self, active: bool) -> None:
        """Synchronise le bouton scène avec l'état réel de la fenêtre."""
        with QSignalBlocker(self._stage_button):
            self._stage_button.setChecked(bool(active))

    def set_announcement_active(self, active: bool) -> None:
        """Réflète l'état de la boucle d'annonces sur le bouton."""
        with QSignalBlocker(self._announce_button):
            self._announce_button.setChecked(bool(active))
        self._announce_button.setText(
            tr("announcement_loop_stop") if active else tr("announcement_loop_start")
        )

    def set_project_active(self, active: bool) -> None:
        self._project_active = active
        with QSignalBlocker(self._project_button):
            self._project_button.setChecked(active)
        self._live_badge.setVisible(self._project_active and not self._is_hidden)
        self._update_mode_badge()
        self._update_stage_meta()

    def set_program_title(self, title: str) -> None:
        """Affiche le titre du programme live (sermon, chapitre, cantique…)."""
        text = str(title or "").strip()
        self._program_title_label.setText(text if text else tr("projection"))
        self._program_title_label.setToolTip(text)
        self._program_title_label.setStyleSheet(
            f"font-size: {Typography.SIZE_META}px;"
            f" color: {Colors.TEXT_SECONDARY if text else Colors.TEXT_MUTED};"
            "letter-spacing: 0;"
        )

    # ── Position de la référence (haut / bas) ─────────────────────────
    def _on_ref_pos_clicked(self, checked: bool) -> None:
        self._apply_ref_position(checked)
        self.referencePositionToggled.emit(checked)

    def set_reference_position(self, top: bool) -> None:
        """Synchronise le bouton et l'aperçu avec la position demandée."""
        with QSignalBlocker(self._ref_pos_button):
            self._ref_pos_button.setChecked(bool(top))
        self._apply_ref_position(bool(top))

    def _apply_ref_position(self, top: bool) -> None:
        icon = "chevron-up.svg" if top else "chevron-down.svg"
        self._ref_pos_button.setIcon(app_icon(icon, Colors.TEXT_PRIMARY))
        tooltip = (
            tr("reference_position_tooltip_top")
            if top
            else tr("reference_position_tooltip_bottom")
        )
        self._ref_pos_button.setToolTip(tooltip)
        self._move_ref_label(top)

    def _move_ref_label(self, top: bool) -> None:
        """Place la référence de l'aperçu en haut ou en bas de l'écran."""
        lay = self._slide_frame.layout()
        if lay is None:
            return
        lay.removeWidget(self._ref_label)
        if top:
            # Juste sous la rangée de badges LIVE / statut.
            lay.insertWidget(lay.indexOf(self._stage_top) + 1, self._ref_label, 0)
        else:
            # Juste au-dessus de la barre de pied (scène / compteur).
            lay.insertWidget(lay.indexOf(self._stage_footer), self._ref_label, 0)

    # ── Contrôles vidéo (vidéo en direct) ─────────────────────────────

    def _on_video_play_clicked(self, checked: bool) -> None:
        self.videoControlRequested.emit("play" if checked else "pause")

    def set_video_state(self, has_video: bool, playing: bool) -> None:
        """Affiche les contrôles vidéo et reflète l'état de lecture."""
        self._video_play_button.setVisible(bool(has_video))
        self._video_stop_button.setVisible(bool(has_video))
        with QSignalBlocker(self._video_play_button):
            self._video_play_button.setChecked(bool(playing))
            self._video_play_button.setText(tr("video_pause") if playing else tr("video_play"))
        if has_video:
            if playing:
                self.play_video()
            else:
                self.pause_video()

    # ── Lecteur miniature de l'aperçu (muté, ratio = projection) ──────

    def _ensure_video_preview(self) -> bool:
        """Crée paresseusement le lecteur d'aperçu ; False si QtMultimedia manque."""
        if self._video_preview is not None:
            return self._video_preview is not False
        try:
            from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
            from PyQt6.QtMultimediaWidgets import QVideoWidget
        except Exception:
            self._video_preview = False
            return False

        widget = QVideoWidget(self._slide_frame)
        widget.setStyleSheet("background: black; border: none; border-radius: 10px;")
        # Ratio préservé (letterbox) = exactement ce que voit l'écran projeté,
        # sans jamais occuper l'écran entier.
        widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._frame_layout.insertWidget(
            self._frame_layout.indexOf(self._stage_footer), widget, 1
        )
        widget.hide()
        self._video_preview = widget
        self._video_preview_audio = QAudioOutput(self)
        self._video_preview_audio.setMuted(True)  # le son sort en projection
        self._video_preview_player = QMediaPlayer(self)
        self._video_preview_player.setAudioOutput(self._video_preview_audio)
        self._video_preview_player.setVideoOutput(self._video_preview)
        return True

    def _show_video_preview(self, path: str) -> bool:
        if not self._ensure_video_preview():
            return False
        from PyQt6.QtCore import QUrl

        if path != self._video_preview_path:
            self._video_preview_path = path
            self._video_preview_player.setSource(QUrl.fromLocalFile(path))
        self._video_preview.show()
        self._video_preview.raise_()
        return True

    def _hide_video_preview(self) -> None:
        self._video_preview_path = ""
        if self._video_preview_player is not None:
            self._video_preview_player.stop()
        if self._video_preview:
            self._video_preview.hide()

    def play_video(self) -> None:
        if self._ensure_video_preview() and self._video_preview_path:
            self._video_preview_player.play()

    def pause_video(self) -> None:
        if self._ensure_video_preview() and self._video_preview_path:
            self._video_preview_player.pause()

    def stop_video(self) -> None:
        if self._ensure_video_preview() and self._video_preview_path:
            self._video_preview_player.pause()
            self._video_preview_player.setPosition(0)

    def set_slide(
        self,
        reference: str,
        text: str,
        image_path: str = "",
        video_path: str = "",
        video_playing: bool = False,
        source: str = "",
        hidden: bool = False,
    ) -> None:
        ref = str(reference or "").strip()
        body = str(text or "").strip()
        img = str(image_path or "").strip()
        vid = str(video_path or "").strip()
        self._current_reference = ref
        self._current_image_path = img
        self._has_content = bool(ref or body or img or vid)

        self.set_video_state(bool(vid), bool(video_playing))

        if vid and Path(vid).is_file():
            self._image_label.setVisible(False)
            self._image_label.clear()
            self._render_pixmap_full = None
            self._empty_state.setVisible(False)
            if self._show_video_preview(vid):
                # Cadre vidéo réel : le même ratio que la projection.
                self.slide_view.setVisible(False)
                self._ref_label.setText(ref)
            else:
                # QtMultimedia absent : repli texte.
                self.slide_view.setVisible(True)
                self.slide_view.setText(f"🎬  {ref}")
                self._ref_label.setText("")
        else:
            self._hide_video_preview()
            # Rendu fidèle (texte OU image) via le canvas partagé : l'aperçu
            # devient identique à la projection, voiles et typographie comprises.
            pixmap = self._render_canvas_pixmap(
                ref, body, source=source, image_path=img, hidden=hidden
            )
            self._current_image_path = ""
            if pixmap is not None:
                self._render_pixmap_full = pixmap
                self.slide_view.setVisible(False)
                self._ref_label.setText("")
                self._empty_state.setVisible(False)
                self._image_label.setVisible(True)
                self._refresh_image_pixmap()
            else:
                # Repli historique si le canvas n'est pas disponible.
                self._render_pixmap_full = None
                self._image_label.setVisible(False)
                self._image_label.clear()
                has_text = bool(body or ref)
                self.slide_view.setVisible(has_text)
                self._empty_state.setVisible(not has_text)
                self.slide_view.setText(body)
                self._ref_label.setText(ref)

        self._update_stage_meta()
        self._edit_button.setEnabled(self._has_content)
        self._apply_slide_text_style()

    # ── Rendu fidèle (canvas partagé avec la projection) ─────────────

    def set_presentation_dir(self, path) -> None:
        """Dossier de travail projection (chemins de visuels relatifs)."""
        self._presentation_dir = path
        if self._canvas is not None:
            self._canvas._presentation_dir = path

    def _ensure_canvas(self) -> SlideCanvas | None:
        if self._canvas is not None:
            return self._canvas
        try:
            self._canvas = SlideCanvas(presentation_dir=self._presentation_dir)
        except Exception:
            return None
        return self._canvas

    def _canvas_style_config(self) -> dict:
        if self._settings is None or not hasattr(self._settings, "projection"):
            return {}
        try:
            return self._settings.projection.to_presentation_config()
        except Exception:
            return {}

    def _render_canvas_pixmap(
        self,
        reference: str,
        text: str,
        source: str = "",
        image_path: str = "",
        hidden: bool = False,
    ):
        """Rend la slide hors écran à la résolution de sortie (1920×1080),
        avec le thème assigné au type de contenu si pertinent."""
        canvas = self._ensure_canvas()
        if canvas is None:
            return None
        cfg = self._canvas_style_config()
        effective: dict = cfg
        if cfg:
            from app.utils.themes import ThemeRegistry

            registry = ThemeRegistry(cfg)
            theme_style = registry.style_for(str(source or ""))
            if theme_style is not None:
                effective = theme_style
        if effective != self._canvas_cfg:
            self._canvas_cfg = effective
            try:
                canvas._apply_config(dict(effective))
            except Exception:
                return None
        try:
            return canvas.render_pixmap(
                {
                    "source": str(source or "custom"),
                    "reference": str(reference or ""),
                    "text": str(text or ""),
                    "image": str(image_path or ""),
                    "background": str(image_path or ""),
                    "hidden": bool(hidden),
                }
            )
        except Exception:
            return None

    def _refresh_image_pixmap(self) -> None:
        """Met à l'échelle le rendu 1080p sur la taille du cadre d'aperçu."""
        if self._render_pixmap_full is None or not self._image_label.isVisible():
            return
        size = self._image_label.size()
        if size.width() < 10 or size.height() < 10:
            size = QSize(400, 280)
        self._image_label.setPixmap(
            self._render_pixmap_full.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def set_slide_counter(self, current: int, total: int) -> None:
        self._current_row = current
        self._total_slides = total
        if total > 0 and current >= 0:
            self._counter_label.setText(f"{current + 1} / {total}")
            self._scene_label.setText(f"SCENE {current + 1:02d}")
        else:
            self._counter_label.setText("")
            self._scene_label.setText("SCENE 00")

    def _on_hide_clicked(self) -> None:
        self._is_hidden = self._hide_button.isChecked()
        self._update_hide_button()
        self.hideToggled.emit(self._is_hidden)

    def _update_mode_badge(self) -> None:
        if self._project_active:
            self._mode_badge.setText("LIVE")
            self._mode_badge.setStyleSheet(
                f"""
                QLabel {{
                    background: {Colors.ACCENT_SUCCESS_GLOW};
                    border: none;
                    border-radius: 10px;
                    padding: 4px 10px;
                    min-width: 56px;
                    color: {Colors.ACCENT_SUCCESS};
                    font-size: {Typography.SIZE_NUMBER}px;
                    font-weight: 800;
                    letter-spacing: 0;
                }}
                """
            )
        else:
            self._mode_badge.setText("PREVIEW")
            self._mode_badge.setStyleSheet(
                f"""
                QLabel {{
                    background: {Colors.ACCENT_SECONDARY_GLOW};
                    border: none;
                    border-radius: 10px;
                    padding: 4px 10px;
                    min-width: 56px;
                    color: {Colors.TEXT_SECONDARY};
                    font-size: {Typography.SIZE_NUMBER}px;
                    font-weight: 800;
                    letter-spacing: 0;
                }}
                """
            )

    def _update_stage_meta(self) -> None:
        if self._is_hidden:
            self._status_chip.setText(tr("output_hidden"))
        elif self._project_active and self._has_content:
            self._status_chip.setText(tr("projection_active"))
        elif self._has_content:
            self._status_chip.setText(tr("ready_to_project"))
        else:
            self._status_chip.setText(tr("waiting"))

    def _update_hide_button(self) -> None:
        if self._is_hidden:
            self._hide_button.setIcon(app_icon("eye-off.svg", "#ffb4ae"))
            self._hide_button.setText(tr("show"))
            self._hide_button.setStyleSheet(self._hide_button_hidden_style)
            self._slide_frame.setStyleSheet(self._slide_screen_style(self._bg_hidden))
        else:
            self._hide_button.setIcon(app_icon("eye.svg", Colors.TEXT_PRIMARY))
            self._hide_button.setText(tr("hide"))
            self._hide_button.setStyleSheet(self._hide_button_base_style)
            self._slide_frame.setStyleSheet(self._slide_screen_style(self._bg_live))

        self._live_badge.setVisible(self._project_active and not self._is_hidden)
        self._update_stage_meta()
        self._apply_slide_text_style()

    def set_hidden(self, hidden: bool) -> None:
        self._is_hidden = hidden
        self._hide_button.setChecked(hidden)
        self._update_hide_button()

    def set_settings(self, settings) -> None:
        """Refresh the operator preview from the active application settings."""
        self._settings = settings
        # Invalide la config du canvas : le prochain rendu fidèle repartira
        # des réglages à jour (thème, typographie, fond…).
        self._canvas_cfg = None
        reference_position = ""
        if settings is not None and hasattr(settings, "projection"):
            reference_position = str(
                getattr(settings.projection, "reference_position", "") or ""
            ).lower()
        self.set_reference_position(reference_position == "top")
        self._apply_slide_text_style()

    def _toggle_hide(self) -> None:
        self._hide_button.setChecked(not self._hide_button.isChecked())
        self._on_hide_clicked()

    def _on_space_shortcut(self) -> None:
        """Laisse l'Espace activer le contrôle focalisé (bouton, champ, liste)."""
        from PyQt6.QtWidgets import (
            QApplication,
            QAbstractButton,
            QComboBox,
            QPlainTextEdit,
            QSpinBox,
            QTextEdit,
            QLineEdit,
            QListWidget,
            QTreeWidget,
        )

        fw = QApplication.focusWidget()
        if isinstance(
            fw,
            (
                QAbstractButton,
                QComboBox,
                QLineEdit,
                QTextEdit,
                QPlainTextEdit,
                QSpinBox,
                QListWidget,
                QTreeWidget,
            ),
        ):
            return
        self._toggle_hide()

    def _apply_slide_text_style(self) -> None:
        base_size = 16
        line_height = 1.3
        font_weight = "600"
        transform = "none"

        if self._settings and hasattr(self._settings, "projection"):
            projection = self._settings.projection
            # The operator preview is a monitoring view, not the stage: keep
            # the text clearly smaller than the real projection output.
            base_size = max(13, int(projection.text_size * 0.42))
            pane_h = self._slide_frame.height()
            if pane_h > 120:
                base_size = max(base_size, int(pane_h * 0.038))
            line_height = projection.line_height
            font_weight = (
                "800"
                if projection.font_weight == "bold"
                else "300" if projection.font_weight == "light" else "500"
            )
            transform = "uppercase" if projection.uppercase else "none"

        # Mirror the stage contract: text length never alters typography.
        font_size = max(10, int(base_size))

        alpha = 0.18 if self._is_hidden else 1.0
        color = (
            self._rgba(self._stage_text_rgb, alpha)
            if self._has_content
            else self._stage_empty_color
        )
        ref_color = (
            self._rgba(self._stage_ref_rgb, alpha * 0.8)
            if self._has_content
            else "transparent"
        )

        self.slide_view.setStyleSheet(f"""
            QLabel {{
                font-size: {font_size}px;
                font-weight: {font_weight};
                color: {color};
                background: transparent;
                line-height: {line_height};
                text-transform: {transform};
                padding: 10px 10px 4px 10px;
            }}
        """)

        ref_size = max(9, font_size - 5)
        # Qt style sheets ignore letter-spacing — set it on the QFont instead.
        ref_font = QFont()
        ref_font.setPixelSize(ref_size)
        ref_font.setWeight(QFont.Weight.Bold)
        ref_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 112.0)
        self._ref_label.setFont(ref_font)
        self._ref_label.setStyleSheet(f"""
            QLabel {{
                color: {ref_color};
                background: transparent;
                padding-top: 6px;
            }}
        """)

    def get_current_reference(self) -> str:
        return self._current_reference
