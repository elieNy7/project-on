from __future__ import annotations

"""Fenêtre plein écran dédiée à un mélangeur vidéo (ATEM, Roland V/AV).

Source d'incrustation chroma key : fond vert uniforme sur tout l'écran,
section texte composée exactement comme la sortie OBS (les deux lisent
``obs-config.json`` — même style, même géométrie). Le mélangeur supprime
le vert (chroma key) et incruste la section texte sur la caméra.

La composition est réalisée hors Qt par :mod:`app.utils.obs_overlay_render`
(PIL, 1920×1080) puis affichée mise à l'échelle : le rendu est identique
quelle que soit la résolution de la sortie HDMI. Si l'écran n'est pas
16:9, des marges vertes (letterbox) ramènent l'image au format du
mélangeur — elles sont elles aussi supprimées par la clé chroma.
"""

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

from PyQt6.QtCore import QRect, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QKeySequence,
    QPainter,
    QPixmap,
    QShortcut,
)
from PyQt6.QtWidgets import QWidget

from app.ui.ticker_overlay import TickerOverlay
from app.utils import power_guard
from app.utils.obs_overlay_render import (
    CHROMA_KEY_COLORS,
    CHROMA_KEY_GREEN,
    chroma_key_rgb,
    render_obs_overlay_on_color,
)

__all__ = [
    "MixerOutputWindow",
    "letterbox_rect",
    "hdmi_band_config",
    "CHROMA_KEY_GREEN",
]

# Libellés de la mire pour chaque couleur de clé.
KEY_COLOR_LABELS = {"green": "VERT", "magenta": "MAGENTA", "blue": "BLEU"}


def hdmi_band_config(cfg: dict[str, Any] | None) -> dict[str, Any]:
    """Config de composition du bandeau HDMI : TOUJOURS le lower third.

    La sortie mixeur incruste un bandeau sur la caméra : le mode
    géométrique choisi pour la page OBS (plein écran, panneau…) n'y
    hérite jamais. L'ajustement vertical fin reste ``offset_y``.
    """
    out = dict(cfg or {})
    out["layout_mode"] = "lower_third"
    out["position"] = "bottom"
    return out


def letterbox_rect(width: int, height: int) -> QRect:
    """Plus grand rectangle 16:9 centré dans la zone (width, height).

    Plein cadre si la zone est déjà 16:9 ; sinon bandes vertes latérales
    ou haute/basses autour du rectangle retourné.
    """
    width = max(1, int(width))
    height = max(1, int(height))
    if width * 9 == height * 16:
        return QRect(0, 0, width, height)
    if width * 9 > height * 16:
        # Plus large que 16:9 → bandes à gauche et à droite.
        new_h = height
        new_w = height * 16 // 9
    else:
        # Plus haut que 16:9 → bandes en haut et en bas.
        new_w = width
        new_h = width * 9 // 16
    return QRect((width - new_w) // 2, (height - new_h) // 2, new_w, new_h)


class MixerOutputWindow(QWidget):
    """Sortie HDMI d'incrustation pour mélangeur vidéo.

    Fond vert chroma + section texte « façon OBS » ; le bandeau
    d'annonces suit les mêmes réglages que les autres diffusions.
    Le masquage (« B ») s'applique comme partout : cadre vert uniforme.
    """

    RENDER_WIDTH = 1920
    RENDER_HEIGHT = 1080

    def __init__(
        self,
        presentation_dir: Path,
        *,
        screen: str = "auto",
        letterbox: bool = True,
        exclude_screen: str = "",
        key_color: str = "green",
        text_scale: int = 100,
        offset_y: int = 0,
        show_ticker: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Project-On - Sortie HDMI")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self._slide_path = presentation_dir / "slide.json"
        self._cfg_path = presentation_dir / "obs-config.json"
        self._last_slide_mtime: float = -1.0
        self._last_cfg_mtime: float = -1.0
        self._last_cfg: dict[str, Any] | None = None

        self._screen_pref = str(screen or "auto")
        self._exclude_screen = str(exclude_screen or "")
        self._letterbox_enabled = bool(letterbox)
        self._key_color = "green"
        self._key_rgb: tuple[int, int, int] = CHROMA_KEY_GREEN
        self._text_scale = 100
        self._offset_y = 0
        self._ticker_enabled = bool(show_ticker)
        self._active_screen = ""
        self._mire_enabled = False
        self._power_held = False

        self._frame_pixmap: QPixmap | None = None

        # Bandeau d'annonces : mêmes réglages que la page OBS et le NDI
        # (charge utile « ticker » de obs-config.json).
        self._ticker = TickerOverlay(self)
        self._ticker.hide()

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self.setCursor(Qt.CursorShape.BlankCursor)
        self.set_key_color(key_color)
        self.set_text_scale(text_scale)
        self.set_offset_y(offset_y)
        self._apply_screen()
        self._tick()

        esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc_shortcut.activated.connect(self.close)
        f11_shortcut = QShortcut(QKeySequence(Qt.Key.Key_F11), self)
        f11_shortcut.activated.connect(self.close)

    # ── Écran cible ───────────────────────────────────────────────────

    def _pick_screen(self, preferred: str):
        screens = QGuiApplication.screens()
        if not screens:
            return None

        def name(screen) -> str:
            return str(screen.name() or "")

        if preferred not in ("", "auto"):
            for screen in screens:
                if name(screen) == preferred:
                    return screen

        # Auto : le plus grand écran secondaire, en évitant l'écran déjà
        # utilisé par la projection locale quand il est identifiable.
        candidates = [s for s in screens if name(s) != self._exclude_screen]
        if not candidates:
            candidates = screens
        primary = QGuiApplication.primaryScreen()
        secondary = [s for s in candidates if s != primary]
        pool = secondary or candidates
        return max(
            pool, key=lambda s: s.geometry().width() * s.geometry().height()
        )

    def _apply_screen(self) -> None:
        try:
            target = self._pick_screen(self._screen_pref)
            if target is None:
                self.showFullScreen()
                return
            geo = target.geometry()
            self._active_screen = str(target.name() or "")
            self.setGeometry(geo)
            self.move(geo.topLeft())
            self.showFullScreen()
        except Exception:
            log.exception("Échec de la sélection de l'écran HDMI")
            self.showFullScreen()

    def set_screen(self, screen: str) -> None:
        """Re-cible la sortie (préférence opérateur, live)."""
        screen = str(screen or "auto")
        if screen == self._screen_pref:
            return
        self._screen_pref = screen
        self._apply_screen()

    def set_letterbox(self, enabled: bool) -> None:
        self._letterbox_enabled = bool(enabled)
        self._position_ticker()
        self.update()

    @property
    def key_color(self) -> str:
        return self._key_color

    @property
    def key_rgb(self) -> tuple[int, int, int]:
        return self._key_rgb

    def set_key_color(self, color: str) -> None:
        """Couleur de clé chroma (green|magenta|blue), appliquée en direct."""
        name = str(color or "green").strip().lower()
        if name not in CHROMA_KEY_COLORS:
            name = "green"
        if name == self._key_color:
            return
        self._key_color = name
        self._key_rgb = CHROMA_KEY_COLORS[name]
        self._rerender()

    def set_text_scale(self, scale: int) -> None:
        """Taille de la section texte en % (60–180), appliquée en direct."""
        value = max(60, min(180, int(scale or 100)))
        if value == self._text_scale:
            return
        self._text_scale = value
        self._rerender()

    def set_offset_y(self, offset: int) -> None:
        """Décalage vertical du bandeau (px @1080), appliqué en direct."""
        value = max(-300, min(300, int(offset or 0)))
        if value == self._offset_y:
            return
        self._offset_y = value
        self._rerender()

    def set_ticker_enabled(self, enabled: bool) -> None:
        """Inclut ou non le bandeau d'annonces sur cette sortie."""
        enabled = bool(enabled)
        if enabled == self._ticker_enabled:
            return
        self._ticker_enabled = enabled
        if not enabled:
            self._ticker.hide()
        else:
            # Rejoue la dernière configuration connue du bandeau.
            self._last_cfg_mtime = -1.0
            self._tick()

    def _rerender(self) -> None:
        """Force la recomposition du cadre au prochain tick."""
        self._last_slide_mtime = -1.0
        self._tick()

    @property
    def active_screen(self) -> str:
        return self._active_screen

    @property
    def mire_enabled(self) -> bool:
        return self._mire_enabled

    def set_mire_enabled(self, enabled: bool) -> bool:
        """Affiche/masque la mire de calibrage (vérifier l'entrée du mélangeur)."""
        self._mire_enabled = bool(enabled)
        self.update()
        return self._mire_enabled

    def toggle_mire(self) -> bool:
        return self.set_mire_enabled(not self._mire_enabled)

    # ── Zone utile 16:9 ───────────────────────────────────────────────

    def _content_rect(self) -> QRect:
        if not self._letterbox_enabled:
            return self.rect()
        return letterbox_rect(self.width(), self.height())

    def _position_ticker(self) -> None:
        rect = self._content_rect()
        height = self._ticker.height()
        self._ticker.setGeometry(
            rect.left(), rect.bottom() + 1 - height, rect.width(), height
        )
        self._ticker.raise_()

    # ── Contenu : polling slide.json / obs-config.json ────────────────

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        try:
            if not path.exists() or not path.is_file():
                return None
            raw = path.read_text(encoding="utf-8")
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def _mtime(self, path: Path) -> float:
        try:
            return path.stat().st_mtime if path.exists() else -1.0
        except Exception:
            return -1.0

    def _tick(self) -> None:
        cfg_mtime = self._mtime(self._cfg_path)
        if cfg_mtime != self._last_cfg_mtime:
            self._last_cfg_mtime = cfg_mtime
            cfg = self._read_json(self._cfg_path)
            if cfg is not None:
                self._last_cfg = cfg
                try:
                    self._apply_ticker_config(cfg)
                except Exception:
                    log.exception("Échec du bandeau HDMI")

        slide_mtime = self._mtime(self._slide_path)
        if slide_mtime != self._last_slide_mtime:
            self._last_slide_mtime = slide_mtime
            slide = self._read_json(self._slide_path)
            if slide is not None:
                try:
                    self._apply_slide(slide)
                except Exception:
                    log.exception("Échec de la composition HDMI")

    def _apply_ticker_config(self, cfg: dict[str, Any]) -> None:
        ticker_cfg = cfg.get("ticker")
        if not isinstance(ticker_cfg, dict):
            self._ticker.configure([], False)
            return
        self._ticker.configure(
            texts=list(ticker_cfg.get("texts") or []),
            enabled=bool(ticker_cfg.get("enabled")) and self._ticker_enabled,
            speed=int(ticker_cfg.get("speed") or 90),
            height=int(ticker_cfg.get("height") or 64),
            bg_color=str(ticker_cfg.get("bg_color") or "rgba(5,10,22,0.82)"),
            text_color=str(ticker_cfg.get("text_color") or "rgba(255,255,255,0.95)"),
            font_size=int(ticker_cfg.get("font_size") or 30),
        )
        self._position_ticker()

    def _apply_slide(self, slide: dict[str, Any]) -> None:
        """Re-compose le cadre : couleur de clé + section texte façon OBS."""
        img = render_obs_overlay_on_color(
            hdmi_band_config(self._last_cfg),
            slide,
            bg_rgba=(*self._key_rgb, 255),
            width=self.RENDER_WIDTH,
            height=self.RENDER_HEIGHT,
            text_scale=self._text_scale / 100.0,
            offset_y=self._offset_y,
        )
        rgb = img.convert("RGB")
        data = rgb.tobytes()
        qimg = QImage(
            data,
            rgb.width,
            rgb.height,
            rgb.width * 3,
            QImage.Format.Format_RGB888,
        )
        # copy() : QImage référence le tampon PIL sans le copier.
        self._frame_pixmap = QPixmap.fromImage(qimg.copy())
        self.update()

    # ── Peinture ──────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        content = self._content_rect()

        # Tout l'écran garde la couleur de clé, marges comprises : la clé
        # du mélangeur supprime aussi les bandes letterbox.
        painter.fillRect(self.rect(), QColor(*self._key_rgb))

        if self._mire_enabled:
            self._paint_mire(painter, content)
            return

        if self._frame_pixmap is not None:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawPixmap(content, self._frame_pixmap)

    _MIRE_BARS = (
        (192, 192, 192),
        (192, 192, 0),
        (0, 192, 192),
        (0, 192, 0),
        (192, 0, 192),
        (192, 0, 0),
        (0, 0, 192),
    )

    _MIRE_GRAY_RAMP = (
        (255, 255, 255),
        (204, 204, 204),
        (153, 153, 153),
        (102, 102, 102),
        (51, 51, 51),
        (0, 0, 0),
    )

    def _paint_mire(self, painter: QPainter, rect: QRect) -> None:
        """Mire de calibrage professionnelle.

        Barres de couleur + rampe de gris (réglage du mélangeur), guides
        de zones utiles 93 % / 90 % + croix de centre ( cadrage), et zone
        de clé avec les trois pastilles de couleur : l'opérateur prélève
        la pipette du mélangeur sur celle qu'il veut utiliser.
        """
        # ── Bandes de référence : barres, rampe de gris, zone de clé ──
        bars_h = int(rect.height() * 0.52)
        ramp_h = int(rect.height() * 0.07)
        key_y = rect.top() + bars_h + ramp_h
        key_h = rect.top() + rect.height() - key_y

        bar_w = rect.width() / len(self._MIRE_BARS)
        for index, rgb in enumerate(self._MIRE_BARS):
            x = rect.left() + int(round(index * bar_w))
            painter.fillRect(
                QRect(x, rect.top(), int(bar_w) + 1, bars_h), QColor(*rgb)
            )

        ramp_w = rect.width() / len(self._MIRE_GRAY_RAMP)
        for index, rgb in enumerate(self._MIRE_GRAY_RAMP):
            x = rect.left() + int(round(index * ramp_w))
            painter.fillRect(
                QRect(x, rect.top() + bars_h, int(ramp_w) + 1, ramp_h), QColor(*rgb)
            )

        painter.fillRect(
            QRect(rect.left(), key_y, rect.width(), key_h), QColor(*self._key_rgb)
        )

        # ── Bandeau d'informations sur les barres ──
        banner_h = int(bars_h * 0.42)
        banner_y = rect.top() + int((bars_h - banner_h) / 2)
        painter.fillRect(
            QRect(rect.left(), banner_y, rect.width(), banner_h),
            QColor(5, 10, 22, 235),
        )
        painter.setPen(QColor(255, 255, 255, 240))
        title_font = QFont(self.font().family())
        title_font.setPixelSize(max(16, banner_h // 3))
        title_font.setWeight(QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.drawText(
            QRect(rect.left(), banner_y, rect.width(), banner_h // 2),
            Qt.AlignmentFlag.AlignCenter,
            "PROJECT-ON · MIRE HDMI",
        )
        key_label = KEY_COLOR_LABELS.get(self._key_color, "VERT")
        info = (
            f"{self._active_screen or 'écran principal'} · "
            f"{rect.width()}"
            "\u00d7"
            f"{rect.height()} · 16:9 · clé {key_label} "
            f"#{self._key_rgb[0]:02X}{self._key_rgb[1]:02X}{self._key_rgb[2]:02X}"
        )
        info_font = QFont(self.font().family())
        info_font.setPixelSize(max(13, banner_h // 5))
        painter.setFont(info_font)
        painter.drawText(
            QRect(rect.left(), banner_y + banner_h // 2, rect.width(), banner_h // 2),
            Qt.AlignmentFlag.AlignCenter,
            info,
        )

        # ── Guides de cadrage : zones utiles 93 % / 90 % + croix centrale ──
        for ratio, pen_w, alpha in ((0.93, 2, 150), (0.90, 1, 100)):
            inset = int((1.0 - ratio) * rect.width() / 2)
            inset_v = int((1.0 - ratio) * rect.height() / 2)
            painter.setPen(QColor(255, 255, 255, alpha))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(
                QRect(
                    rect.left() + inset,
                    rect.top() + inset_v,
                    rect.width() - inset * 2,
                    rect.height() - inset_v * 2,
                )
            )
        cx = rect.left() + rect.width() // 2
        cy = rect.top() + rect.height() // 2
        painter.setPen(QColor(255, 255, 255, 120))
        painter.drawLine(rect.left(), cy, rect.left() + rect.width(), cy)
        painter.drawLine(cx, rect.top(), cx, rect.top() + rect.height())

        # ── Pastilles de clé : bandeau sombre pour que chaque couleur
        # ressorte (le vert reste visible sur un fond vert), la pastille
        # active est entourée d'un double liseré blanc ──
        strip_pad_top = int(key_h * 0.10)
        strip_pad_bottom = int(key_h * 0.07)
        strip = QRect(
            rect.left() + int(rect.width() * 0.04),
            key_y + strip_pad_top,
            int(rect.width() * 0.92),
            key_h - strip_pad_top - strip_pad_bottom,
        )
        painter.setBrush(QColor(5, 10, 22, 235))
        painter.setPen(QColor(255, 255, 255, 45))
        painter.drawRoundedRect(strip, 10, 10)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        cap_px = max(12, int(key_h * 0.072))
        cap_font = QFont(self.font().family())
        cap_font.setPixelSize(cap_px)
        cap_font.setWeight(QFont.Weight.DemiBold)
        label_px = max(11, int(key_h * 0.060))
        label_font = QFont(self.font().family())
        label_font.setPixelSize(label_px)

        painter.setPen(QColor(255, 255, 255, 235))
        painter.setFont(cap_font)
        painter.drawText(
            QRect(
                strip.left(),
                strip.top() + int(key_h * 0.045),
                strip.width(),
                cap_px + 10,
            ),
            Qt.AlignmentFlag.AlignCenter,
            "COULEUR DE CLÉ — prélevez la pipette du mélangeur sur une pastille",
        )

        swatch_h = max(26, int(key_h * 0.24))
        swatch_w = min(int(strip.width() * 0.22), int(swatch_h * 1.7))
        gap = int(swatch_w * 0.45)
        total_w = len(CHROMA_KEY_COLORS) * swatch_w + (len(CHROMA_KEY_COLORS) - 1) * gap
        sx = strip.center().x() - total_w // 2
        sy = strip.top() + int(key_h * 0.045) + cap_px + int(key_h * 0.055)

        for name, rgb in CHROMA_KEY_COLORS.items():
            box = QRect(sx, sy, swatch_w, swatch_h)
            painter.setBrush(QColor(*rgb))
            painter.setPen(QColor(255, 255, 255, 230))
            painter.drawRect(box)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if name == self._key_color:
                painter.setPen(QColor(255, 255, 255, 255))
                painter.drawRect(box.adjusted(-4, -4, 4, 4))
                painter.setPen(QColor(5, 10, 22, 180))
                painter.drawRect(box.adjusted(-2, -2, 2, 2))
            hex_text = f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"
            painter.setPen(
                QColor(255, 255, 255, 255 if name == self._key_color else 175)
            )
            painter.setFont(label_font)
            painter.drawText(
                QRect(sx, sy + swatch_h + 8, swatch_w, label_px + 10),
                Qt.AlignmentFlag.AlignCenter,
                f"{KEY_COLOR_LABELS.get(name, name)} {hex_text}",
            )
            sx += swatch_w + gap

    # ── Cycle de vie ──────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_ticker()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.setCursor(Qt.CursorShape.BlankCursor)
        if not self._power_held:
            self._power_held = True
            power_guard.acquire()

    def closeEvent(self, event) -> None:
        if self._power_held:
            self._power_held = False
            power_guard.release()
        super().closeEvent(event)
