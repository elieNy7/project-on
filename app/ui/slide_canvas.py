from __future__ import annotations

import logging
import math
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QImage,
    QLinearGradient,
    QPainter,
    QPixmap,
    QRadialGradient,
    QRegion,
)
from PyQt6.QtWidgets import (
    QGraphicsBlurEffect,
    QGraphicsOpacityEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def _blur_pixmap(pix: QPixmap, radius: float) -> QPixmap:
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(pix)
    blur = QGraphicsBlurEffect()
    blur.setBlurRadius(radius)
    item.setGraphicsEffect(blur)
    scene.addItem(item)
    out = QImage(pix.size(), QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    scene.render(painter, QRectF(out.rect()), QRectF(pix.rect()))
    painter.end()
    return QPixmap.fromImage(out)


class ShadowTextLabel(QLabel):
    """QLabel with a real blurred drop shadow painted by hand.

    QGraphicsDropShadowEffect conflicts with the opacity effect applied to the
    parent during slide transitions (Qt graphics effects do not nest), and its
    intermediate pixmap can crop glyphs on Windows. Painting the shadow
    ourselves avoids both problems and stays crisp during animations. The
    blurred shadow is cached, so Ken Burns repaints stay cheap.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._shadow_color: QColor | None = None
        self._shadow_blur = 0
        self._shadow_dy = 2
        self._shadow_cache_key: tuple | None = None
        self._shadow_cache = QPixmap()
        self._rendering_shadow = False

    def set_shadow(self, color: QColor | None, blur: int = 18, dy: int = 2) -> None:
        self._shadow_color = color
        self._shadow_blur = max(0, int(blur))
        self._shadow_dy = int(dy)
        self._shadow_cache_key = None
        self.update()

    def paintEvent(self, event) -> None:
        if (
            self._shadow_color is None
            or self._shadow_blur <= 0
            or not self.text()
            or self._rendering_shadow
        ):
            super().paintEvent(event)
            return

        key = (
            self.text(),
            self.width(),
            self.height(),
            self._shadow_blur,
            self._shadow_dy,
            self._shadow_color.rgba(),
            self.font().toString(),
        )
        if key != self._shadow_cache_key:
            img = QImage(self.size(), QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(Qt.GlobalColor.transparent)
            self._rendering_shadow = True
            try:
                src_painter = QPainter(img)
                self.render(
                    src_painter, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren
                )
                src_painter.end()
            finally:
                self._rendering_shadow = False
            tinted = QImage(img.size(), img.format())
            tinted.fill(Qt.GlobalColor.transparent)
            tint_painter = QPainter(tinted)
            tint_painter.drawImage(0, 0, img)
            tint_painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceIn
            )
            tint_painter.fillRect(tinted.rect(), self._shadow_color)
            tint_painter.end()
            self._shadow_cache = _blur_pixmap(
                QPixmap.fromImage(tinted), float(self._shadow_blur)
            )
            self._shadow_cache_key = key

        shadow_painter = QPainter(self)
        shadow_painter.drawPixmap(0, self._shadow_dy, self._shadow_cache)
        shadow_painter.end()
        super().paintEvent(event)


class SlideCanvas(QWidget):
    """Zone de rendu d'une diapositive : fond + voiles + bloc texte.

    Unique source de vérité du dessin Project-On : la fenêtre de projection
    locale l'utilise telle quelle (plein écran), l'aperçu opérateur la rend
    hors écran à la résolution de sortie — l'aperçu devient fidèle au pixel
    prêt, et l'écran scène réutilise le même contrat visuel.
    """

    RENDER_WIDTH = 1920
    RENDER_HEIGHT = 1080

    def __init__(
        self,
        presentation_dir: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._presentation_dir = presentation_dir
        self._config: dict[str, Any] = {}
        self._current_slide: dict[str, Any] = {}
        self._background_pixmap = QPixmap()
        self._active_visual_path = ""
        self._available_content_width = 0
        self._available_content_height = 0
        self._stage_accent = QColor(109, 180, 255, 210)
        self._stage_accent_soft = QColor(109, 180, 255, 42)
        # Ken Burns : état du fond animé (piloté par ProjectionWindow en live ;
        # les rendus hors écran restent statiques sur la position de départ).
        self._kb_zoom = 1.0
        self._kb_pan = QPointF(0.0, 0.0)

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        self._content_shell = QWidget(self)
        self._content_shell.setObjectName("ProjectionCanvas")
        self._content_shell.setStyleSheet(
            "QWidget#ProjectionCanvas { background: transparent; border: none; }"
        )
        self._content_shell.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._shell_layout = QVBoxLayout(self._content_shell)
        self._shell_layout.setContentsMargins(0, 0, 0, 0)
        self._shell_layout.setSpacing(0)

        self._content_widget = QWidget(self._content_shell)
        self._content_widget.setStyleSheet("background: transparent;")
        self._content_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(18)

        self.text_label = ShadowTextLabel("")
        self.text_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.text_label.setWordWrap(True)
        self.text_label.setTextFormat(Qt.TextFormat.PlainText)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Hidden by default: local projection should feel like a clean PowerPoint slide.
        self._accent_line = QWidget(self._content_widget)
        self._accent_line.setFixedHeight(3)
        self._accent_line.setMaximumWidth(100)
        self._accent_line.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            " stop:0 transparent, stop:0.2 rgba(230, 180, 76, 0.6),"
            " stop:0.8 rgba(230, 180, 76, 0.6), stop:1 transparent);"
            " border-radius: 1px;"
        )

        self.ref_label = ShadowTextLabel("")
        self.ref_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.ref_label.setWordWrap(True)
        self.ref_label.setTextFormat(Qt.TextFormat.PlainText)
        self.ref_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._shell_layout.addWidget(self._content_widget, 1)
        self._main_layout.addWidget(self._content_shell, 1)

        # Opacity effect — used to hide the live content while a pixmap-based
        # transition plays over the (continuous) background.
        self._fade_effect = QGraphicsOpacityEffect(self._content_widget)
        self._fade_effect.setOpacity(1.0)
        self._content_widget.setGraphicsEffect(self._fade_effect)

    # ── API publique ───────────────────────────────────────────────────────

    def _apply_config(self, cfg: dict[str, Any]) -> None:
        """Applique (et normalise) une configuration de style, puis re-rend."""
        cfg = dict(cfg)
        cfg["layout_mode"] = self._choice(
            cfg.get("layout_mode"), self._LAYOUT_MODES, "fullscreen"
        )
        cfg["position"] = self._choice(
            cfg.get("position"), ("top", "center", "bottom"), "center"
        )
        cfg["slide_style"] = self._choice(
            cfg.get("slide_style"), ("cinematic", "clean", "split"), "cinematic"
        )
        cfg["reference_position"] = self._choice(
            cfg.get("reference_position"), ("top", "bottom"), "bottom"
        )
        cfg["align"] = self._choice(
            cfg.get("align"), ("left", "center", "right"), "center"
        )
        cfg["panel_side"] = self._choice(
            cfg.get("panel_side"), ("left", "right"), "left"
        )
        try:
            cfg["padding"] = max(0, min(160, int(cfg.get("padding") or 0)))
        except (TypeError, ValueError):
            cfg["padding"] = 0
        self._config = cfg

        self._apply_layout_metrics(cfg)
        self._update_shell_style(cfg)

        while self._main_layout.count():
            item = self._main_layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self._content_shell:
                widget.setParent(None)

        show_ref = bool(cfg.get("show_reference", True))
        align = cfg["align"]
        reference_position = cfg["reference_position"]
        slide_style = cfg["slide_style"]
        layout_mode = cfg["layout_mode"]
        pos = cfg["position"]

        accent_align = (
            Qt.AlignmentFlag.AlignLeft
            if slide_style == "split" or align == "left"
            else Qt.AlignmentFlag.AlignRight
            if align == "right"
            else Qt.AlignmentFlag.AlignHCenter
        )
        self._refresh_content_order(show_ref, reference_position, accent_align)

        vertical_container_align = (
            Qt.AlignmentFlag.AlignTop
            if pos == "top"
            else Qt.AlignmentFlag.AlignBottom
            if pos == "bottom"
            else Qt.AlignmentFlag.AlignVCenter
        )
        # Horizontal placement: side_panel follows panel_side, band modes
        # follow the text alignment, everything else stays centred.
        if layout_mode == "side_panel":
            horizontal_container_align = (
                Qt.AlignmentFlag.AlignRight
                if cfg["panel_side"] == "right"
                else Qt.AlignmentFlag.AlignLeft
            )
        elif layout_mode in ("lower_third", "subtitle"):
            horizontal_container_align = (
                Qt.AlignmentFlag.AlignLeft
                if align == "left"
                else Qt.AlignmentFlag.AlignRight
                if align == "right"
                else Qt.AlignmentFlag.AlignHCenter
            )
        else:
            horizontal_container_align = Qt.AlignmentFlag.AlignHCenter
        self._main_layout.addWidget(
            self._content_shell,
            1,
            horizontal_container_align | vertical_container_align,
        )

        # Visibility of the divider is decided per-slide in _render_slide_content.
        self._accent_line.setVisible(False)

        # Text Alignment — the split style is always left-aligned by design.
        effective_align = "left" if slide_style == "split" else align
        horizontal_align = (
            Qt.AlignmentFlag.AlignHCenter
            if effective_align == "center"
            else Qt.AlignmentFlag.AlignRight
            if effective_align == "right"
            else Qt.AlignmentFlag.AlignLeft
        )
        vertical_align = (
            Qt.AlignmentFlag.AlignTop
            if pos == "top"
            else Qt.AlignmentFlag.AlignBottom
            if pos == "bottom"
            else Qt.AlignmentFlag.AlignVCenter
        )
        label_align = horizontal_align | vertical_align
        self.text_label.setAlignment(label_align)
        self.ref_label.setAlignment(label_align)

        self.update()

        # Re-apply current slide content with the new style.
        if self._current_slide:
            self._render_slide_content(self._current_slide)

    def apply_config(self, cfg: dict[str, Any]) -> None:
        """Alias public de ``_apply_config`` (rendus hors écran)."""
        self._apply_config(cfg)

    def set_slide(self, slide: dict[str, Any]) -> None:
        """Affiche une slide (fond + contenu), sans transition ni média.

        C'est le point d'entrée des rendus hors écran (aperçu, vignettes) ;
        la projection locale passe par ``ProjectionWindow._apply_slide`` qui
        gère vidéo/web/transitions avant d'appeler le rendu partagé.
        """
        self._render_slide_content(slide)

    def render_pixmap(
        self,
        slide: dict[str, Any] | None = None,
        width: int = RENDER_WIDTH,
        height: int = RENDER_HEIGHT,
    ) -> QPixmap:
        """Rend hors écran la slide demandée à la résolution de sortie.

        Utilisé par l'aperçu opérateur : le pixmap produit est strictement
        identique à ce que la projection affiche, simplement réduit.
        """
        if self.width() != width or self.height() != height:
            self.resize(int(width), int(height))
            if self._config:
                self._apply_layout_metrics(self._config)
        if slide is not None:
            self.set_slide(slide)
        return self.grab()

    # ── Peinture du fond ───────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        """Draw a clean full-screen slide, close to a PowerPoint presentation."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = self.rect()
        cfg = self._config

        bg_color = self._parse_color(cfg.get("bg_color") or "#000000", 1.0)

        if cfg.get("bg_gradient_enabled"):
            bg_color_2 = self._parse_color(cfg.get("bg_color_2") or "#020818", 1.0)
            angle_value = cfg.get("bg_gradient_angle")
            angle = float(angle_value if angle_value is not None else 180)

            rad = math.radians(angle)
            x1 = rect.center().x() - math.sin(rad) * rect.height()
            y1 = rect.center().y() + math.cos(rad) * rect.height()
            x2 = rect.center().x() + math.sin(rad) * rect.height()
            y2 = rect.center().y() - math.cos(rad) * rect.height()

            gradient = QLinearGradient(x1, y1, x2, y2)
            gradient.setColorAt(0, bg_color)
            gradient.setColorAt(1, bg_color_2)
            painter.setBrush(QBrush(gradient))
        else:
            painter.setBrush(QBrush(bg_color))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(rect)

        if not self._background_pixmap.isNull():
            has_text = bool(str(self._current_slide.get("text") or "").strip())
            has_ref = bool(str(self._current_slide.get("reference") or "").strip())
            is_contain = str(cfg.get("bg_image_fit") or "cover") == "contain"
            target = self._cover_rect(
                self._background_pixmap.width(),
                self._background_pixmap.height(),
                rect,
                contain=is_contain,
            )
            if self._kb_zoom != 1.0 or self._kb_pan != QPointF(0.0, 0.0):
                target = self._apply_ken_burns(target)
            painter.drawPixmap(
                target,
                self._background_pixmap,
                QRectF(self._background_pixmap.rect()),
            )
            dimmer = max(
                0.0, min(0.85, float(cfg.get("background_dimmer", 0.34)))
            )
            slide_style = self._choice(
                cfg.get("slide_style"), ("cinematic", "clean", "split"), "cinematic"
            )
            self._paint_cinematic_scrim(
                painter, rect, dimmer, has_text or has_ref, slide_style
            )
        elif cfg.get("bg_gradient_enabled"):
            # Depth vignette on plain gradient backgrounds (skipped for the
            # « clean » style, which stays perfectly flat by design).
            slide_style = self._choice(
                cfg.get("slide_style"), ("cinematic", "clean", "split"), "cinematic"
            )
            if slide_style != "clean":
                w, h = rect.width(), rect.height()
                vignette = QRadialGradient(
                    rect.center().x(), rect.center().y(), math.hypot(w, h) * 0.62
                )
                vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
                vignette.setColorAt(0.75, QColor(0, 0, 0, 0))
                vignette.setColorAt(1.0, QColor(0, 0, 0, 60))
                painter.fillRect(rect, QBrush(vignette))

    def _apply_ken_burns(self, target: QRectF) -> QRectF:
        """Étend la cible du fond selon l'état Ken Burns (zoom + pan lents).

        ``_kb_zoom`` >= 1 grossit l'image autour du centre ; ``_kb_pan`` est un
        décalage exprimé en fraction de la taille de la cible. L'excédent
        déborde du widget et est naturellement rogné — comme un cadrage caméra.
        """
        cx, cy = target.center().x(), target.center().y()
        w, h = target.width() * self._kb_zoom, target.height() * self._kb_zoom
        dx = self._kb_pan.x() * w
        dy = self._kb_pan.y() * h
        return QRectF(cx - w / 2.0 + dx, cy - h / 2.0 + dy, w, h)

    def set_ken_burns_state(self, zoom: float, pan_x: float, pan_y: float) -> None:
        """Met à jour l'état Ken Burns (appelé par l'animation live)."""
        self._kb_zoom = max(1.0, float(zoom))
        self._kb_pan = QPointF(float(pan_x), float(pan_y))
        self.update()

    def _paint_cinematic_scrim(
        self,
        painter: QPainter,
        rect,
        dimmer: float,
        has_content: bool,
        slide_style: str = "cinematic",
    ) -> None:
        """Layered scrim over a background image, in three flavours.

        « cinematic » — soft global veil, weighted top/bottom gradients and a
        vignette that focuses the eye toward the centre.
        « clean » — a single flat veil, no gradients, no vignette: the most
        discreet, documentary look.
        « split » — a strong horizontal gradient anchored on the text side
        (left) that fades to the right, keeping the image alive on the
        opposite half.
        """
        w, h = rect.width(), rect.height()

        if slide_style == "clean":
            veil = dimmer * (0.55 if has_content else 0.20)
            painter.fillRect(rect, QColor(0, 0, 0, int(255 * veil)))
            return

        if slide_style == "split":
            if has_content:
                # Anchor the darkness on the left text zone, fade to clear.
                side = QLinearGradient(0, 0, w * 0.78, 0)
                side.setColorAt(0.0, QColor(0, 0, 0, int(255 * dimmer * 0.92)))
                side.setColorAt(0.55, QColor(0, 0, 0, int(255 * dimmer * 0.45)))
                side.setColorAt(1.0, QColor(0, 0, 0, 0))
                painter.fillRect(rect, QBrush(side))
            else:
                painter.fillRect(rect, QColor(0, 0, 0, int(255 * dimmer * 0.22)))
            # Gentle vignette, weaker than cinematic.
            vig_alpha = int(255 * (0.10 + 0.18 * dimmer))
            vignette = QRadialGradient(
                rect.center().x(), rect.center().y(), math.hypot(w, h) * 0.62
            )
            vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
            vignette.setColorAt(0.74, QColor(0, 0, 0, 0))
            vignette.setColorAt(1.0, QColor(0, 0, 0, vig_alpha))
            painter.fillRect(rect, QBrush(vignette))
            return

        if has_content:
            # Soft global veil
            painter.fillRect(rect, QColor(0, 0, 0, int(255 * dimmer * 0.55)))
            # Bottom-weighted gradient (main text zone)
            bottom = QLinearGradient(0, h * 0.35, 0, h)
            bottom.setColorAt(0.0, QColor(0, 0, 0, 0))
            bottom.setColorAt(1.0, QColor(0, 0, 0, int(255 * dimmer * 0.85)))
            painter.fillRect(rect, QBrush(bottom))
            # Top-weighted gradient (upper reference zone)
            top = QLinearGradient(0, 0, 0, h * 0.42)
            top.setColorAt(0.0, QColor(0, 0, 0, int(255 * dimmer * 0.55)))
            top.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillRect(rect, QBrush(top))
        else:
            # Image-only slide: barely veil it, keep the picture alive.
            painter.fillRect(rect, QColor(0, 0, 0, int(255 * dimmer * 0.25)))

        # Vignette — subtle darkening toward the edges, always on images.
        vig_alpha = int(255 * (0.16 + 0.30 * dimmer))
        vignette = QRadialGradient(
            rect.center().x(), rect.center().y(), math.hypot(w, h) * 0.62
        )
        vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
        vignette.setColorAt(0.72, QColor(0, 0, 0, 0))
        vignette.setColorAt(1.0, QColor(0, 0, 0, vig_alpha))
        painter.fillRect(rect, QBrush(vignette))

    _installed_families: set[str] | None = None

    @classmethod
    def _resolve_font_family(cls, configured: str) -> str:
        """Pick the first installed family so a missing configured font
        (e.g. « Google Sans ») never falls back to an arbitrary system font."""
        if cls._installed_families is None:
            try:
                cls._installed_families = {
                    f.lower() for f in QFontDatabase.families()
                }
            except Exception:
                cls._installed_families = set()
        available = cls._installed_families
        for candidate in (configured, "Poppins", "Segoe UI", "Arial"):
            name = str(candidate or "").strip()
            if name and (not available or name.lower() in available):
                return name
        return "sans-serif"

    def _cover_rect(
        self, pix_w: int, pix_h: int, target: QRectF, contain: bool = False
    ) -> QRectF:
        if pix_w <= 0 or pix_h <= 0:
            return target

        # "cover" scales to fill (crop overflow); "contain" scales to fit fully.
        if contain:
            scale = min(target.width() / pix_w, target.height() / pix_h)
        else:
            scale = max(target.width() / pix_w, target.height() / pix_h)
        width = pix_w * scale
        height = pix_h * scale
        x = target.center().x() - (width / 2.0)
        y = target.center().y() - (height / 2.0)
        return QRectF(x, y, width, height)

    def _parse_color(self, color_str: str, alpha: float | None = None) -> QColor:
        try:
            if "rgba" in color_str:
                m = re.match(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)", color_str)
                if m:
                    r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    a = float(m.group(4)) if alpha is None else alpha
                    return QColor(r, g, b, int(a * 255))
            qc = QColor(color_str)
            if alpha is not None:
                qc.setAlpha(int(alpha * 255))
            return qc
        except Exception:
            return QColor(0, 0, 0, 255)

    def _set_source_accent(self, source: str) -> None:
        # Aligned with the app source palette (theme.Colors.SRC_*) and OBS.
        palette = {
            "bible": QColor(86, 214, 129, 220),
            "sermon": QColor(224, 160, 68, 220),
            "hymn": QColor(185, 151, 255, 220),
            "expose": QColor(0, 172, 193, 220),
            "custom": QColor(109, 180, 255, 220),
            "image": QColor(130, 123, 112, 220),
        }
        accent = palette.get(str(source or "").lower(), palette["custom"])
        self._stage_accent = accent
        self._stage_accent_soft = QColor(
            accent.red(), accent.green(), accent.blue(), 52
        )
        self._update_accent_line_style()

    def _update_accent_line_style(self) -> None:
        accent = self._stage_accent
        css_color = (
            f"rgba({accent.red()}, {accent.green()}, {accent.blue()}, "
            f"{accent.alpha() / 255:.2f})"
        )
        self._accent_line.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f" stop:0 transparent, stop:0.15 {css_color},"
            f" stop:0.85 {css_color}, stop:1 transparent);"
            f" border-radius: 1px;"
        )

    def _font_weight_to_qt(self, weight: str) -> QFont.Weight:
        value = str(weight or "").lower()
        if value in ("bold", "700", "800", "900"):
            return QFont.Weight.Bold
        if value in ("600", "semibold", "demi"):
            return QFont.Weight.DemiBold
        if value in ("light", "300", "200"):
            return QFont.Weight.Light
        return QFont.Weight.Normal

    def _apply_layout_metrics(self, cfg: dict[str, Any]) -> tuple[int, int]:
        sw = self.width() if self.width() > 100 else 1920
        sh = self.height() if self.height() > 100 else 1080

        edge_guard = max(0, min(240, int(cfg.get("safe_margin") or 0)))
        self._main_layout.setContentsMargins(
            edge_guard, edge_guard, edge_guard, edge_guard
        )

        mode = self._choice(
            cfg.get("layout_mode"), self._LAYOUT_MODES, "fullscreen"
        )
        content_width = int(cfg.get("content_width") or 88)
        maximum_width = int(cfg.get("max_width") or 100)
        width_pct = max(40, min(100, content_width, maximum_width))
        height_pct = max(35, min(100, int(cfg.get("content_height") or 82)))
        if mode == "lower_third":
            width_pct = min(width_pct, 88)
            height_pct = min(height_pct, 38)
        elif mode == "subtitle":
            width_pct = min(96, max(width_pct, 72))
            height_pct = min(height_pct, 26)
        elif mode == "side_panel":
            width_pct = min(width_pct, 46)
            height_pct = min(94, max(height_pct, 68))
        elif mode == "focus_card":
            width_pct = min(width_pct, 72)
            height_pct = min(height_pct, 62)
        available_width = max(320, int((sw - (edge_guard * 2)) * width_pct / 100))
        available_height = max(240, int((sh - (edge_guard * 2)) * height_pct / 100))

        self._available_content_width = available_width
        self._available_content_height = available_height
        self._content_shell.setMinimumWidth(available_width)
        self._content_shell.setMaximumWidth(available_width)
        self._content_shell.setMinimumHeight(available_height)
        self._content_shell.setMaximumHeight(available_height)
        self._content_widget.setMinimumSize(0, 0)
        self.text_label.setMinimumSize(0, 0)
        self.ref_label.setMinimumSize(0, 0)

        # Text sits directly on the background — no inner frame padding.
        panel_mode = mode in ("lower_third", "side_panel", "subtitle", "focus_card")
        panel_on = bool(cfg.get("panel_enabled", False)) or panel_mode
        padding_value = cfg.get("padding")
        panel_padding = max(
            0, int(padding_value if padding_value is not None else 0)
        )
        if not panel_on:
            panel_padding = 0
        self._shell_layout.setContentsMargins(
            panel_padding, panel_padding, panel_padding, panel_padding
        )
        self._content_layout.setSpacing(max(8, min(24, int(sh * 0.018))))
        show_top_reference = (
            bool(cfg.get("show_reference", True))
            and str(cfg.get("reference_position") or "bottom").lower() == "top"
        )
        top_reference_margin = (
            max(28, min(72, int(sh * 0.05))) if show_top_reference else 0
        )
        self._content_layout.setContentsMargins(0, top_reference_margin, 0, 0)
        self._accent_line.setFixedWidth(max(120, min(280, sw // 6)))
        return available_width, available_height

    def resizeEvent(self, event) -> None:
        """Handle canvas resize: re-apply layout metrics, re-render content."""
        super().resizeEvent(event)
        if not self._config:
            return
        self._apply_layout_metrics(self._config)
        if self._current_slide:
            self._render_slide_content(self._current_slide)

    def _refresh_content_order(
        self,
        show_ref: bool,
        reference_position: str,
        accent_align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignHCenter,
    ) -> None:
        for i in reversed(range(self._content_layout.count())):
            item = self._content_layout.itemAt(i)
            if item.spacerItem():
                self._content_layout.removeItem(item)
            elif item.widget():
                item.widget().setParent(None)

        self._content_layout.addStretch(1)
        if show_ref and reference_position == "top":
            self._content_layout.addWidget(self.ref_label, 0)
            self._content_layout.addWidget(self._accent_line, 0, accent_align)
            self._content_layout.addWidget(self.text_label, 0)
        else:
            self._content_layout.addWidget(self.text_label, 0)
            self._content_layout.addWidget(self._accent_line, 0, accent_align)
            if show_ref:
                self._content_layout.addWidget(self.ref_label, 0)
        self._content_layout.addStretch(1)

    def _update_shell_style(self, cfg: dict[str, Any]) -> None:
        mode = str(cfg.get("layout_mode") or "fullscreen").lower()
        panel_on = bool(cfg.get("panel_enabled", False)) or mode in (
            "lower_third",
            "side_panel",
            "subtitle",
            "focus_card",
        )
        if not panel_on:
            self._content_shell.setStyleSheet(
                "QWidget#ProjectionCanvas { background: transparent; border: none; }"
            )
            return

        panel = self._parse_color(
            str(cfg.get("panel_color") or "rgba(5,12,24,0.86)")
        )
        panel.setAlphaF(
            max(0.0, min(1.0, float(cfg.get("panel_opacity", 0.86))))
        )
        radius = max(0, min(96, int(cfg.get("panel_radius") or 0)))
        rgba = (
            f"rgba({panel.red()}, {panel.green()}, {panel.blue()}, "
            f"{panel.alphaF():.3f})"
        )
        self._content_shell.setStyleSheet(
            "QWidget#ProjectionCanvas {"
            f" background: {rgba};"
            f" border-radius: {radius}px;"
            " border: 1px solid rgba(255,255,255,0.12);"
            "}"
        )

    _LAYOUT_MODES = ("fullscreen", "lower_third", "side_panel", "subtitle", "focus_card")

    @staticmethod
    def _choice(value: Any, allowed: tuple[str, ...], fallback: str) -> str:
        v = str(value or "").strip().lower()
        return v if v in allowed else fallback

    def _render_slide_content(self, slide: dict[str, Any]) -> None:
        slide = dict(slide)
        hidden = bool(slide.get("hidden"))
        visual_path = str(slide.get("image") or slide.get("background") or "")
        if (
            not visual_path
            and not hidden
            and self._config.get("bg_mode") == "image"
        ):
            visual_path = str(self._config.get("bg_image") or "")
        slide["_visual_key"] = visual_path
        self._current_slide = slide
        self._set_source_accent(str(slide.get("source") or "custom"))
        self._set_visual_background(visual_path)

        if hidden:
            self.text_label.setText("")
            self.ref_label.setText("")
            self._accent_line.hide()
            self._content_shell.hide()
            self.update()
            return

        cfg = self._config
        uppercase = bool(cfg.get("uppercase"))
        show_reference = bool(cfg.get("show_reference", True))
        align = str(cfg.get("align") or "center").lower()
        font_family = self._resolve_font_family(str(cfg.get("font_family") or ""))

        # Média pur (image/vidéo/web sans texte) : aucun titre projeté à l'écran.
        video_path = str(slide.get("video") or "").strip()
        web_url = str(slide.get("url") or "").strip()
        if (
            video_path
            or web_url
            or (visual_path and not str(slide.get("text") or "").strip())
        ):
            show_reference = False

        # The configured size is the target; auto-scaling only reduces it if needed.
        screen = self.screen()
        screen_w = max(self.width(), screen.geometry().width() if screen else 1920)
        text = str(slide.get("text") or "")
        ref = str(slide.get("reference") or "")
        font_weight = str(cfg.get("font_weight") or "600")
        transform = str(cfg.get("text_transform") or "none")

        if uppercase or transform == "uppercase":
            text = text.upper()
            ref = ref.upper()

        shell_margins = self._shell_layout.contentsMargins()
        # Use the constrained content width (content_width %) rather than the full
        # screen width, otherwise the auto-fit over-estimates how much text fits per
        # line and picks a font size that overflows on long verses.
        constrained_width = (
            self._available_content_width
            if self._available_content_width > 0
            else max(self._content_shell.width(), self.width(), screen_w)
        )
        available_width = max(
            360,
            constrained_width - shell_margins.left() - shell_margins.right(),
        )
        # Keep a typographic gutter inside the configured block. Qt's text
        # layout can have glyph overhang beyond horizontalAdvance(); using the
        # full width risks clipping the final word even when metrics say it fits.
        wrap_width = max(320, int(available_width * 0.90))

        # Configured pixel sizes are defined against a 1080p reference screen.
        # Larger displays scale text UP so it stays proportionally readable,
        # but the user's configured size is never reduced on smaller windows —
        # the readability floor below is the only minimum.
        screen_h = max(self.height(), 1)
        size_scale = max(1.0, min(3.0, screen_h / 1080.0))

        ref_size = int(round(float(cfg.get("ref_size") or 22) * size_scale))
        ref_size = max(8, ref_size)
        has_ref = show_reference and ref.strip()
        font = QFont(font_family)
        font.setWeight(self._font_weight_to_qt(font_weight))
        letter_spacing = int(cfg.get("letter_spacing") or 0)

        # Inner padding that lets the drop-shadow blur render without being
        # clipped at the widget edges.
        shadow_on = bool(cfg.get("text_shadow", True))
        blur_px = max(4, min(80, int(cfg.get("shadow_blur") or 18)))
        pad_px = (int(blur_px * 0.75) + 6) if shadow_on else 0

        def wrap_for_qt(value: str, size: int, width: int) -> str:
            wrap_font = QFont(font_family)
            wrap_font.setWeight(self._font_weight_to_qt(font_weight))
            wrap_font.setPixelSize(size)
            metrics = QFontMetrics(wrap_font)
            wrapped: list[str] = []
            for paragraph in value.splitlines() or [value]:
                words = paragraph.split()
                if not words:
                    wrapped.append("")
                    continue
                current = ""
                for word in words:
                    candidate = f"{current} {word}".strip()
                    if not current or metrics.horizontalAdvance(candidate) <= width:
                        current = candidate
                        continue
                    wrapped.append(current)
                    current = word
                if current:
                    wrapped.append(current)
            return "\n".join(wrapped)

        # The configured value is authoritative. Text length must never change
        # local projection typography; only the display scale may affect it.
        text_size = max(
            10,
            int(round(float(cfg.get("text_size") or 54) * size_scale)),
        )

        text_color = str(cfg.get("text_color") or "#ffffff")
        ref_color = str(cfg.get("ref_color") or "rgba(255,255,255,0.75)")

        wrapped_text = wrap_for_qt(text, text_size, wrap_width)
        wrapped_ref = wrap_for_qt(ref, ref_size, wrap_width)

        pad_css = f"padding: {pad_px}px;" if pad_px else ""

        text_font = QFont(font_family)
        text_font.setPixelSize(text_size)
        text_font.setWeight(self._font_weight_to_qt(font_weight))
        text_font.setLetterSpacing(
            QFont.SpacingType.AbsoluteSpacing, float(letter_spacing)
        )
        # The widget's own stylesheet must carry the font properties: the
        # app-wide stylesheet sets QWidget to the application body size and would
        # otherwise override setFont() at polish time — which made the
        # projected text tiny no matter the computed size.
        self.text_label.setStyleSheet(
            f"color: {text_color}; background: transparent; border: none; {pad_css}"
            f' font-family: "{font_family}"; font-size: {text_size}px;'
        )
        self.text_label.setFont(text_font)

        ref_font = QFont(font_family)
        ref_font.setPixelSize(ref_size)
        ref_font.setWeight(QFont.Weight.DemiBold)
        ref_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 112.0)
        self.ref_label.setStyleSheet(
            f"color: {ref_color}; background: transparent; border: none; {pad_css}"
            f' font-family: "{font_family}"; font-size: {ref_size}px;'
        )
        self.ref_label.setFont(ref_font)

        # Apply the stylesheet fonts immediately so the effective font is
        # correct even before the widget is shown (and in tests).
        self.text_label.ensurePolished()
        self.ref_label.ensurePolished()

        # Text shadow painted by the labels themselves (see ShadowTextLabel) —
        # no QGraphicsEffect, so it composes cleanly with the opacity effect
        # used on the parent during transitions.
        if shadow_on:
            shadow_color = self._parse_color(
                str(cfg.get("shadow_color") or "rgba(0,0,0,0.85)")
            )
            dy = max(1, blur_px // 8)
            self.text_label.set_shadow(shadow_color, blur_px, dy)
            self.ref_label.set_shadow(shadow_color, blur_px, dy)
        else:
            self.text_label.set_shadow(None)
            self.ref_label.set_shadow(None)

        self.text_label.setText(wrapped_text)
        self.ref_label.setText(wrapped_ref if has_ref else "")
        # Refined divider between text and reference whenever a reference shows.
        self._accent_line.setVisible(bool(has_ref))
        has_content = bool(text.strip() or has_ref)
        self._content_shell.setVisible(has_content)
        self._update_shell_style(cfg)
        self.update()

    def _set_visual_background(self, visual_path: str) -> None:
        normalized = visual_path.strip()
        if normalized == self._active_visual_path:
            return

        self._active_visual_path = normalized
        if not normalized:
            self._background_pixmap = QPixmap()
            self.update()
            return

        visual_file = Path(normalized)
        if not visual_file.is_absolute() and self._presentation_dir is not None:
            visual_file = (self._presentation_dir / visual_file).resolve()

        # Static background — no motion, like a PowerPoint slide.
        pixmap = QPixmap(str(visual_file))
        self._background_pixmap = pixmap if not pixmap.isNull() else QPixmap()
        self.update()
