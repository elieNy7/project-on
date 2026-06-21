from __future__ import annotations

import json
import math
import re
from html import escape
from pathlib import Path
from typing import Any

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QImage,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPixmap,
    QRegion,
    QShortcut,
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


class ProjectionWindow(QWidget):
    def __init__(self, presentation_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Project-On - Projection")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self._presentation_dir = presentation_dir
        self._slide_path = presentation_dir / "slide.json"
        self._config_path = presentation_dir / "config.json"

        self._last_slide_mtime: float = -1.0
        self._last_config_mtime: float = -1.0
        self._config: dict[str, Any] = {}
        self._current_slide: dict[str, Any] = {}
        self._background_pixmap = QPixmap()
        self._active_visual_path = ""
        self._available_content_width = 0
        self._available_content_height = 0
        self._stage_accent = QColor(116, 167, 248, 210)
        self._stage_accent_soft = QColor(116, 167, 248, 42)

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

        # Content Widget for Animation
        self._content_widget = QWidget(self._content_shell)
        self._content_widget.setStyleSheet("background: transparent;")
        self._content_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(18)

        self.text_label = QLabel("")
        self.text_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.text_label.setWordWrap(True)
        self.text_label.setTextFormat(Qt.TextFormat.RichText)
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

        self.ref_label = QLabel("")
        self.ref_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.ref_label.setWordWrap(True)
        self.ref_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._shell_layout.addWidget(self._content_widget, 1)
        self._main_layout.addWidget(self._content_shell, 1)

        # Opacity effect — used to hide the live content while a pixmap-based
        # transition plays over the (continuous) background.
        self._fade_effect = QGraphicsOpacityEffect(self._content_widget)
        self._fade_effect.setOpacity(1.0)
        self._content_widget.setGraphicsEffect(self._fade_effect)

        # Slide transition engine (pixmap cross-animation in paintEvent)
        self._trans: dict[str, Any] | None = None
        self._trans_p = 0.0
        self._trans_anim = QVariantAnimation(self)
        self._trans_anim.setStartValue(0.0)
        self._trans_anim.setEndValue(1.0)
        self._trans_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._trans_anim.valueChanged.connect(self._on_trans_value)
        self._trans_anim.finished.connect(self._on_trans_finished)

        # Ken Burns — slow continuous zoom on full-screen background images
        self._kb_t = 0.0
        self._kb_active = False
        self._kb_anim = QVariantAnimation(self)
        self._kb_anim.setStartValue(0.0)
        self._kb_anim.setEndValue(1.0)
        self._kb_anim.setDuration(16000)
        self._kb_anim.setLoopCount(-1)
        self._kb_anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._kb_anim.valueChanged.connect(self._on_kb_value)

        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self._apply_best_screen_fullscreen()
        self._tick()

        # Close on Escape or F11
        esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc_shortcut.activated.connect(self.close)
        f11_shortcut = QShortcut(QKeySequence(Qt.Key.Key_F11), self)
        f11_shortcut.activated.connect(self.close)

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
            angle = float(cfg.get("bg_gradient_angle") or 180)

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
            # Ken Burns: gently zoom the cover image over time.
            if self._kb_active and not is_contain:
                f = self._kb_factor()
                cx, cy = target.center().x(), target.center().y()
                nw, nh = target.width() * f, target.height() * f
                target = QRectF(cx - nw / 2, cy - nh / 2, nw, nh)
            painter.drawPixmap(
                target,
                self._background_pixmap,
                QRectF(self._background_pixmap.rect()),
            )
            if has_text or has_ref:
                overlay = QColor(0, 0, 0, 88)
                painter.setBrush(QBrush(overlay))
                painter.drawRect(rect)

        # Slide transition (text block) painted over the continuous background.
        if self._trans is not None:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            self._paint_transition(painter)

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
            "custom": QColor(116, 167, 248, 220),
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

        edge_guard = max(8, min(28, int(min(sw, sh) * 0.018)))
        self._main_layout.setContentsMargins(
            edge_guard, edge_guard, edge_guard, edge_guard
        )

        width_pct = max(40, min(100, int(cfg.get("content_width") or cfg.get("max_width") or 88)))
        height_pct = max(35, min(100, int(cfg.get("content_height") or 82)))
        available_width = max(320, int((sw - (edge_guard * 2)) * width_pct / 100))
        available_height = max(240, int((sh - (edge_guard * 2)) * height_pct / 100))

        self._available_content_width = available_width
        self._available_content_height = available_height
        self._content_shell.setMaximumWidth(available_width)
        self._content_shell.setMaximumHeight(available_height)
        self._content_shell.setMinimumWidth(min(available_width, 320))
        self._content_shell.setMinimumHeight(min(available_height, 240))
        self._content_widget.setMinimumWidth(max(260, available_width - 96))
        self._content_widget.setMinimumHeight(max(180, available_height - 96))
        self.text_label.setMinimumWidth(max(260, available_width - 96))
        self.ref_label.setMinimumWidth(max(260, available_width - 96))

        # Text sits directly on the background — no inner frame padding.
        self._shell_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(max(8, min(24, int(sh * 0.018))))
        show_top_reference = (
            bool(cfg.get("show_reference", True))
            and str(cfg.get("reference_position") or "bottom").lower() == "top"
        )
        top_reference_margin = (
            max(28, min(72, int(sh * 0.05))) if show_top_reference else 0
        )
        self._content_layout.setContentsMargins(0, top_reference_margin, 0, 0)
        self._accent_line.setMaximumWidth(max(100, min(260, sw // 5)))
        return available_width, available_height

    def resizeEvent(self, event) -> None:
        """Handle screen resize."""
        super().resizeEvent(event)

        if not hasattr(self, "_config") or not getattr(self, "_config", None):
            return

        cfg = self._config
        self._apply_layout_metrics(cfg)

    def _refresh_content_order(self, show_ref: bool, reference_position: str) -> None:
        for i in reversed(range(self._content_layout.count())):
            item = self._content_layout.itemAt(i)
            if item.spacerItem():
                self._content_layout.removeItem(item)
            elif item.widget():
                item.widget().setParent(None)

        if show_ref and reference_position == "top":
            self._content_layout.addWidget(self.ref_label, 0)
            self._content_layout.addWidget(self.text_label, 1)
        else:
            self._content_layout.addWidget(self.text_label, 1)
            if show_ref:
                self._content_layout.addWidget(self.ref_label, 0)

    def _update_shell_style(self, cfg: dict[str, Any]) -> None:
        # Text is drawn directly over the background — never inside a framed box.
        self._content_shell.setStyleSheet(
            "QWidget#ProjectionCanvas { background: transparent; border: none; }"
        )

    def _apply_best_screen_fullscreen(self) -> None:
        try:
            screens = QGuiApplication.screens()
            if not screens:
                self.showFullScreen()
                return

            target_screen = None
            if len(screens) >= 2:
                primary = QGuiApplication.primaryScreen()
                secondary = [s for s in screens if s != primary]
                if secondary:
                    target_screen = max(
                        secondary,
                        key=lambda s: s.geometry().width() * s.geometry().height(),
                    )

            if not target_screen:
                target_screen = max(
                    screens,
                    key=lambda s: s.geometry().width() * s.geometry().height(),
                )

            geo = target_screen.geometry()
            self.setGeometry(geo)
            self.move(geo.topLeft())
            self.showFullScreen()
        except Exception as e:
            print(f"Error selecting screen for projection: {e}")
            self.showFullScreen()

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        try:
            if not path.exists() or not path.is_file():
                return None
            raw = path.read_text(encoding="utf-8")
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def _tick(self) -> None:
        try:
            cfg_mtime = (
                self._config_path.stat().st_mtime
                if self._config_path.exists()
                else -1.0
            )
        except Exception:
            cfg_mtime = -1.0

        if cfg_mtime != self._last_config_mtime:
            self._last_config_mtime = cfg_mtime
            cfg = self._read_json(self._config_path) or {}
            if cfg:
                self._config = cfg
                try:
                    self._apply_config(cfg)
                except Exception as e:
                    print(f"Error applying projection config: {e}")

        try:
            slide_mtime = (
                self._slide_path.stat().st_mtime if self._slide_path.exists() else -1.0
            )
        except Exception:
            slide_mtime = -1.0

        if slide_mtime != self._last_slide_mtime:
            self._last_slide_mtime = slide_mtime
            slide = self._read_json(self._slide_path) or {}
            if slide:
                try:
                    self._apply_slide(slide)
                except Exception as e:
                    print(f"Error applying slide: {e}")

    def _apply_config(self, cfg: dict[str, Any]) -> None:
        self._config = cfg
        pos = str(cfg.get("position") or "center").lower()
        align = str(cfg.get("align") or "center").lower()
        reference_position = str(cfg.get("reference_position") or "bottom").lower()
        slide_style = str(cfg.get("slide_style") or "cinematic").lower()
        if slide_style == "split":
            align = "left"

        self._apply_layout_metrics(cfg)
        self._update_shell_style(cfg)

        while self._main_layout.count():
            item = self._main_layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self._content_shell:
                widget.setParent(None)

        show_ref = bool(cfg.get("show_reference", True))
        self._refresh_content_order(show_ref, reference_position)

        vertical_container_align = (
            Qt.AlignmentFlag.AlignTop
            if pos == "top"
            else Qt.AlignmentFlag.AlignBottom
            if pos == "bottom"
            else Qt.AlignmentFlag.AlignVCenter
        )
        horizontal_container_align = (
            Qt.AlignmentFlag.AlignLeft
            if slide_style == "split"
            else Qt.AlignmentFlag.AlignHCenter
        )
        self._main_layout.addWidget(
            self._content_shell,
            1,
            horizontal_container_align | vertical_container_align,
        )

        self._accent_line.setVisible(False)

        # Text Alignment
        horizontal_align = (
            Qt.AlignmentFlag.AlignHCenter
            if align == "center"
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

        # Re-apply slide content
        slide = self._read_json(self._slide_path) or {}
        if slide:
            self._render_slide_content(slide)

    def _apply_slide(self, slide: dict[str, Any]) -> None:
        text = str(slide.get("text") or "")
        ref = str(slide.get("reference") or "")
        hidden = bool(slide.get("hidden"))
        visual = str(slide.get("image") or slide.get("background") or "")
        if not visual and not hidden and self._config.get("bg_mode") == "image":
            visual = str(self._config.get("bg_image") or "")

        if hidden:
            text = ""
            ref = ""

        changed = (
            text != self._current_slide.get("text")
            or ref != self._current_slide.get("reference")
            or visual != self._current_slide.get("_visual_key")
        )
        if changed:
            self._begin_transition(slide)
        else:
            self._render_slide_content(slide)

    # ── Slide transition engine ────────────────────────────────────────────
    def _begin_transition(self, slide: dict[str, Any]) -> None:
        """Render the new slide with a configurable transition. The background
        stays continuous; only the text block cross-animates as a pixmap."""
        cfg = self._config
        anim_on = bool(cfg.get("animation_enabled", True))
        anim_type = str(cfg.get("animation_type") or "fade").lower()
        duration = int(cfg.get("animation_duration") or 420)
        was_hidden = not self._content_shell.isVisible()
        going_hidden = bool(slide.get("hidden"))

        if (
            not anim_on
            or anim_type == "none"
            or duration <= 0
            or was_hidden
            or going_hidden
        ):
            self._trans = None
            self._fade_effect.setOpacity(1.0)
            self._render_slide_content(slide)
            return

        try:
            self._fade_effect.setOpacity(1.0)
            out_img, out_pos = self._grab_block()
            self._render_slide_content(slide)
            in_img, in_pos = self._grab_block()
        except Exception:
            self._trans = None
            self._fade_effect.setOpacity(1.0)
            self._render_slide_content(slide)
            return

        if out_img is None or in_img is None:
            self._trans = None
            self._fade_effect.setOpacity(1.0)
            return

        trans: dict[str, Any] = {
            "type": anim_type,
            "dir": str(cfg.get("animation_direction") or "up").lower(),
            "out": QPixmap.fromImage(out_img),
            "outpos": out_pos,
            "in": QPixmap.fromImage(in_img),
            "inpos": in_pos,
        }
        if anim_type == "blur":
            radius = max(6.0, min(out_img.width(), out_img.height()) * 0.05)
            trans["out_blur"] = self._blur_pixmap(trans["out"], radius)
            trans["in_blur"] = self._blur_pixmap(trans["in"], radius)
        self._trans = trans

        # Hide the live content; the pixmaps carry the animation.
        self._fade_effect.setOpacity(0.0)
        self._trans_p = 0.0
        self._trans_anim.stop()
        self._trans_anim.setDuration(duration)
        self._trans_anim.start()
        self.update()

    def _on_trans_value(self, value) -> None:
        self._trans_p = float(value)
        self.update()

    def _on_trans_finished(self) -> None:
        self._trans = None
        self._fade_effect.setOpacity(1.0)
        self.update()

    def _grab_block(self) -> tuple[QImage | None, QPoint]:
        w = self._content_shell
        if w.width() <= 1 or w.height() <= 1:
            return None, QPoint()
        img = QImage(w.size(), QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        w.render(img, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
        return img, w.geometry().topLeft()

    @staticmethod
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

    @staticmethod
    def _ease(p: float) -> float:
        p = max(0.0, min(1.0, p))
        return p * p * p * (p * (p * 6 - 15) + 10)  # smootherstep

    def _draw_pix(self, painter, pix, x, y, scale, opacity) -> None:
        if opacity <= 0.004 or pix.isNull():
            return
        painter.setOpacity(max(0.0, min(1.0, opacity)))
        if abs(scale - 1.0) < 1e-3:
            painter.drawPixmap(QPoint(int(round(x)), int(round(y))), pix)
        else:
            w, h = pix.width(), pix.height()
            cx, cy = x + w / 2.0, y + h / 2.0
            nw, nh = w * scale, h * scale
            painter.drawPixmap(
                QRectF(cx - nw / 2, cy - nh / 2, nw, nh), pix, QRectF(pix.rect())
            )
        painter.setOpacity(1.0)

    @staticmethod
    def _slide_offsets(direction: str, pix: QPixmap) -> tuple[float, float]:
        dh, dv = pix.width() * 0.6, pix.height() * 0.6
        return {
            "up": (0.0, -dv),
            "down": (0.0, dv),
            "left": (-dh, 0.0),
            "right": (dh, 0.0),
        }.get(direction, (0.0, -dv))

    @staticmethod
    def _reveal_clip(direction: str, pix: QPixmap, ip: QPoint, e: float) -> QRectF:
        w, h = pix.width(), pix.height()
        x, y = ip.x(), ip.y()
        if direction == "down":
            return QRectF(x, y, w, h * e)
        if direction == "left":
            return QRectF(x + w * (1 - e), y, w * e, h)
        if direction == "right":
            return QRectF(x, y, w * e, h)
        return QRectF(x, y + h * (1 - e), w, h * e)  # "up"

    def _paint_transition(self, painter) -> None:
        t = self._trans
        if not t:
            return
        e = self._ease(self._trans_p)
        typ = t["type"]
        out, op = t["out"], t["outpos"]
        inn, ip = t["in"], t["inpos"]

        if typ == "slide":
            dx, dy = self._slide_offsets(t["dir"], inn)
            self._draw_pix(painter, out, op.x() + dx * e, op.y() + dy * e, 1.0, 1.0 - e)
            self._draw_pix(
                painter, inn, ip.x() - dx * (1 - e), ip.y() - dy * (1 - e), 1.0, e
            )
        elif typ == "scale":
            self._draw_pix(painter, out, op.x(), op.y(), 1.0 + 0.06 * e, 1.0 - e)
            self._draw_pix(painter, inn, ip.x(), ip.y(), 0.94 + 0.06 * e, e)
        elif typ == "blur":
            ob = t.get("out_blur", out)
            ib = t.get("in_blur", inn)
            self._draw_pix(painter, ob, op.x(), op.y(), 1.0, 1.0 - e)
            self._draw_pix(painter, ib, ip.x(), ip.y(), 1.0, e * (1 - e) * 2.0)
            self._draw_pix(painter, inn, ip.x(), ip.y(), 1.0, e * e)
        elif typ == "reveal":
            self._draw_pix(painter, out, op.x(), op.y(), 1.0, 1.0)
            painter.save()
            painter.setClipRect(self._reveal_clip(t["dir"], inn, ip, e))
            self._draw_pix(painter, inn, ip.x(), ip.y(), 1.0, 1.0)
            painter.restore()
        else:  # fade (default)
            self._draw_pix(painter, out, op.x(), op.y(), 1.0, 1.0 - e)
            self._draw_pix(painter, inn, ip.x(), ip.y(), 1.0, e)

    # ── Ken Burns (background image slow zoom) ─────────────────────────────
    def _kb_factor(self) -> float:
        tri = 1.0 - abs(2.0 * self._kb_t - 1.0)  # 0 -> 1 -> 0 over one loop
        return 1.0 + 0.07 * tri

    def _on_kb_value(self, value) -> None:
        self._kb_t = float(value)
        if self._kb_active:
            self.update()

    def _start_ken_burns(self) -> None:
        self._kb_active = True
        self._kb_anim.stop()
        self._kb_anim.start()

    def _stop_ken_burns(self) -> None:
        self._kb_active = False
        self._kb_anim.stop()
        self._kb_t = 0.0

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
        if str(cfg.get("slide_style") or "").lower() == "split":
            align = "left"
        line_height = float(cfg.get("line_height") or 1.35)
        font_family = str(cfg.get("font_family") or "Poppins")

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

        lines = [line for line in text.splitlines() if line.strip()] or [text]
        content_margins = self._content_layout.contentsMargins()
        available_height = max(
            360,
            self.height()
            - self._main_layout.contentsMargins().top()
            - self._main_layout.contentsMargins().bottom()
            - content_margins.top()
            - content_margins.bottom(),
        )
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

        ref_size = max(8, int(float(cfg.get("ref_size") or 22)))
        has_ref = show_reference and ref.strip()
        text_available_height = max(
            120,
            available_height - (int(ref_size * 1.8) if has_ref else 0),
        )

        font = QFont(font_family)
        font.setWeight(self._font_weight_to_qt(font_weight))

        def estimated_text_height(size: int) -> float:
            font.setPixelSize(size)
            metrics = QFontMetrics(font)
            wrapped_lines = 0
            for line in lines:
                line_width = max(1, metrics.horizontalAdvance(line))
                wrapped_lines += max(1, math.ceil(line_width / available_width))
            return wrapped_lines * metrics.lineSpacing() * max(line_height, 0.9)

        configured_size = max(8, int(float(cfg.get("text_size") or 54)))
        low = 8
        high = configured_size
        best = low
        while low <= high:
            mid = (low + high) // 2
            if estimated_text_height(mid) <= text_available_height * 0.96:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        text_size = best

        letter_spacing = int(cfg.get("letter_spacing") or 0)
        text_color = str(cfg.get("text_color") or "#ffffff")
        ref_color = str(cfg.get("ref_color") or "rgba(255,255,255,0.75)")

        text_html = escape(text).replace("\n", "<br>")
        ref_html = escape(ref).replace("\n", "<br>")

        css_align = "center" if align == "center" else "left"

        # Simple presentation shadow only when enabled.
        shadow_css = ""
        if bool(cfg.get("text_shadow", True)):
            s_color = str(cfg.get("shadow_color") or "rgba(0,0,0,0.7)")
            blur = int(cfg.get("shadow_blur") or 12)
            shadow_css = f"text-shadow: 0px 2px {blur}px {s_color}; "

        base_style = (
            f"font-family: '{font_family}', 'Poppins', system-ui; "
            f"line-height: {line_height}; "
            f"text-align: {css_align}; "
            f"font-weight: {font_weight}; "
            f"letter-spacing: {letter_spacing}px; "
            f"display: block; "
            f"width: 100%; "
            f"margin: 0; "
            f"{shadow_css}"
        )

        html_text = (
            f'<div style="{base_style} font-size: {text_size}px; color: {text_color};'
            f' word-break: normal; overflow-wrap: anywhere;">{text_html}</div>'
        )
        html_ref = (
            f'<div style="{base_style} font-size: {ref_size}px; color: {ref_color};'
            f' font-weight: 600; letter-spacing: 0px;'
            f' word-break: normal; overflow-wrap: anywhere;">{ref_html}</div>'
        )

        self.text_label.setText(html_text)
        self.ref_label.setText(html_ref if has_ref else "")
        self._accent_line.setVisible(False)
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
            self._stop_ken_burns()
            self.update()
            return

        visual_file = Path(normalized)
        if not visual_file.is_absolute():
            visual_file = (self._presentation_dir / visual_file).resolve()

        pixmap = QPixmap(str(visual_file))
        self._background_pixmap = pixmap if not pixmap.isNull() else QPixmap()
        if not self._background_pixmap.isNull() and bool(
            self._config.get("ken_burns", True)
        ):
            self._start_ken_burns()
        else:
            self._stop_ken_burns()
        self.update()
