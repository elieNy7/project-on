from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PyQt6.QtGui import (
    QImage,
    QKeySequence,
    QGuiApplication,
    QPainter,
    QPixmap,
    QRegion,
    QShortcut,
)
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QWidget

from app.ui.slide_canvas import SlideCanvas, ShadowTextLabel, _blur_pixmap
from app.utils.themes import ThemeRegistry

__all__ = ["ProjectionWindow", "ShadowTextLabel", "_blur_pixmap"]


class ProjectionWindow(SlideCanvas):
    """Fenêtre de projection plein écran.

    Le dessin (fond, voiles, textes) vit dans :class:`SlideCanvas` — partagé
    avec l'aperçu opérateur et l'écran scène. Cette classe n'ajoute que la
    mécanique de fenêtre : écran cible, polling ``slide.json``/``config.json``,
    transitions, lecture vidéo et pages web.
    """

    def __init__(self, presentation_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(presentation_dir=presentation_dir, parent=parent)
        self.setWindowTitle("Project-On - Projection")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self._slide_path = presentation_dir / "slide.json"
        self._config_path = presentation_dir / "config.json"

        self._last_slide_mtime: float = -1.0
        self._last_config_mtime: float = -1.0
        self._active_display_screen = ""
        # Lecture vidéo (créée paresseusement à la première slide vidéo).
        self._video_widget: Any = None
        self._media_player: Any = None
        self._audio_output: Any = None
        self._active_video_path = ""
        self._multimedia_available = True
        # Pages web (créées paresseusement à la première slide web).
        self._web_view: Any = None
        self._active_web_url = ""
        self._webengine_available = True

        # Slide transition engine (pixmap animation in paintEvent)
        self._trans: dict[str, Any] | None = None
        self._trans_p = 0.0
        self._trans_anim = QVariantAnimation(self)
        self._trans_anim.setStartValue(0.0)
        self._trans_anim.setEndValue(1.0)
        self._trans_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._trans_anim.valueChanged.connect(self._on_trans_value)
        self._trans_anim.finished.connect(self._on_trans_finished)

        # Ken Burns : lente dérive du fond image, ping-pong continu.
        self._kb_forward = True
        self._kb_anim = QVariantAnimation(self)
        self._kb_anim.setStartValue(0.0)
        self._kb_anim.setEndValue(1.0)
        self._kb_anim.setDuration(16000)
        self._kb_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._kb_anim.valueChanged.connect(self._on_kb_value)
        self._kb_anim.finished.connect(self._on_kb_finished)

        self._timer = QTimer(self)
        self._timer.setInterval(250)
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
        super().paintEvent(event)
        # Slide transition (text block) painted over the continuous background.
        if self._trans is not None:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            self._paint_transition(painter)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._video_widget is not None:
            self._video_widget.setGeometry(self.rect())
        if self._web_view is not None:
            self._web_view.setGeometry(self.rect())

    # ── Lecture vidéo (QMediaPlayer, contrôle manuel opérateur) ───────────

    def _ensure_video_stack(self) -> bool:
        """Crée paresseusement le lecteur ; False si QtMultimedia manque."""
        if self._media_player is not None:
            return self._multimedia_available
        try:
            from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
            from PyQt6.QtMultimediaWidgets import QVideoWidget
        except Exception as exc:  # pragma: no cover - dépend de l'install
            log.warning("QtMultimedia indisponible : %s", exc)
            self._multimedia_available = False
            return False

        self._video_widget = QVideoWidget(self)
        self._video_widget.hide()
        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(1.0)
        self._media_player = QMediaPlayer(self)
        self._media_player.setAudioOutput(self._audio_output)
        self._media_player.setVideoOutput(self._video_widget)
        self._media_player.mediaStatusChanged.connect(self._on_media_status)
        return True

    def _show_video(self, path: str) -> None:
        """Passe en mode vidéo plein écran : contenu texte masqué, source chargée EN PAUSE."""
        if not self._ensure_video_stack():
            return
        from PyQt6.QtCore import QUrl

        self._content_shell.setVisible(False)
        if path != self._active_video_path:
            self._active_video_path = path
            self._media_player.setSource(QUrl.fromLocalFile(path))
        self._video_widget.setGeometry(self.rect())
        self._video_widget.show()
        self._video_widget.raise_()

    def _hide_video(self) -> None:
        """Quitte le mode vidéo : stop, masquage, contenu texte restauré."""
        if self._media_player is not None:
            self._media_player.stop()
        self._active_video_path = ""
        if self._video_widget is not None:
            self._video_widget.hide()

    def _apply_video_playing(self, playing: bool) -> None:
        """Applique la commande play/pause de l'opérateur (via slide.json)."""
        if self._media_player is None or not self._active_video_path:
            return
        from PyQt6.QtMultimedia import QMediaPlayer

        state = self._media_player.playbackState()
        if playing and state != QMediaPlayer.PlaybackState.PlayingState:
            self._media_player.play()
        elif not playing and state == QMediaPlayer.PlaybackState.PausedState:
            pass  # déjà en pause (contrôle manuel par défaut)
        elif not playing and state == QMediaPlayer.PlaybackState.PlayingState:
            self._media_player.pause()

    def _on_media_status(self, status) -> None:
        """Fin de lecture : rembobine et reste en pause sur la première frame."""
        from PyQt6.QtMultimedia import QMediaPlayer

        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._media_player.pause()
            self._media_player.setPosition(0)

    # ── Pages web (QWebEngineView, création paresseuse) ───────────────────

    def _ensure_web_stack(self) -> bool:
        """Crée paresseusement la vue web ; False si QtWebEngine manque."""
        if self._web_view is not None:
            return self._webengine_available
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
        except Exception as exc:  # pragma: no cover - dépend de l'install
            log.warning("QtWebEngine indisponible : %s", exc)
            self._webengine_available = False
            return False

        self._web_view = QWebEngineView(self)
        self._web_view.hide()
        return True

    def _show_web(self, url: str) -> None:
        """Passe en mode web plein écran : contenu et vidéo masqués."""
        if not self._ensure_web_stack():
            return
        from PyQt6.QtCore import QUrl

        self._content_shell.setVisible(False)
        if self._active_video_path:
            self._hide_video()
        if url != self._active_web_url:
            self._active_web_url = url
            self._web_view.load(QUrl(url))
        self._web_view.setGeometry(self.rect())
        self._web_view.show()
        self._web_view.raise_()

    def _hide_web(self) -> None:
        self._active_web_url = ""
        if self._web_view is not None:
            self._web_view.hide()

    def _apply_best_screen_fullscreen(self, preferred_name: str = "auto") -> None:
        try:
            screens = QGuiApplication.screens()
            if not screens:
                self.showFullScreen()
                return

            target_screen = next(
                (
                    screen
                    for screen in screens
                    if preferred_name not in ("", "auto")
                    and screen.name() == preferred_name
                ),
                None,
            )
            if target_screen is None and len(screens) >= 2:
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
            self._active_display_screen = str(target_screen.name() or "")
            self.setGeometry(geo)
            self.move(geo.topLeft())
            self.showFullScreen()
        except Exception as e:
            log.exception("Échec de la sélection de l'écran de projection")
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
                try:
                    self._apply_config(cfg)
                except Exception as e:
                    log.exception("Échec de l'application de la configuration de projection")

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
                    log.exception("Échec de l'application du slide")

    def _apply_config(self, cfg: dict[str, Any]) -> None:
        cfg = dict(cfg)
        # Registre de thèmes : la fenêtre résout elle-même le style par type
        # de contenu (bible → thème X, cantique → thème Y…).
        self._theme_registry = ThemeRegistry(cfg)
        self._global_config = dict(cfg)
        self._theme_active: str | None = None
        super()._apply_config(cfg)
        # Sélection de l'écran de sortie (préférence opérateur).
        preferred_screen = str(cfg.get("display_screen") or "auto")
        available_names = {
            str(screen.name() or "") for screen in QGuiApplication.screens()
        }
        if (
            preferred_screen not in ("", "auto")
            and preferred_screen in available_names
            and preferred_screen != self._active_display_screen
        ):
            self._apply_best_screen_fullscreen(preferred_screen)
        # Re-apply slide content from the live file.
        slide = self._read_json(self._slide_path) or {}
        if slide:
            self._apply_theme_for_slide(slide)
            self._render_slide_content(slide)

    def _apply_theme_for_slide(self, slide: dict[str, Any]) -> None:
        """Applique le thème assigné à la source de la slide, si besoin."""
        registry = getattr(self, "_theme_registry", None)
        if registry is None or not registry.themes:
            return
        source = str(slide.get("source") or "")
        theme_id = registry.theme_id_for(source)
        if theme_id == registry.active_id or theme_id not in registry.themes:
            if getattr(self, "_theme_active", None) is not None:
                SlideCanvas._apply_config(self, dict(self._global_config))
                self._theme_active = None
        elif self._theme_active != theme_id:
            SlideCanvas._apply_config(self, dict(registry.themes[theme_id]))
            self._theme_active = theme_id

    def _apply_slide(self, slide: dict[str, Any]) -> None:
        # Style par type de contenu (thèmes) avant tout rendu.
        self._apply_theme_for_slide(slide)
        text = str(slide.get("text") or "")
        ref = str(slide.get("reference") or "")
        hidden = bool(slide.get("hidden"))
        visual = str(slide.get("image") or slide.get("background") or "")
        if not visual and not hidden and self._config.get("bg_mode") == "image":
            visual = str(self._config.get("bg_image") or "")

        video_path = str(slide.get("video") or "").strip()
        web_url = str(slide.get("url") or "").strip()
        if hidden:
            video_path = ""
            web_url = ""
        if web_url:
            self._show_web(web_url)
        elif self._active_web_url:
            self._hide_web()
        if video_path:
            self._show_video(video_path)
        elif self._active_video_path:
            self._hide_video()

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

        # Commande play/pause de l'opérateur (portée par slide.json).
        if bool(slide.get("video_reset")) and video_path and self._media_player:
            self._media_player.pause()
            self._media_player.setPosition(0)
        else:
            self._apply_video_playing(
                bool(slide.get("video_playing")) and bool(video_path)
            )

    # ── Slide transition engine ────────────────────────────────────────────

    _ANIMATION_TYPES = ("none", "fade", "slide", "scale", "blur", "reveal")

    def _effective_animation_type(self, slide: dict[str, Any]) -> str:
        """Type d'animation effectif : surcharge par source si configurée,
        sinon le type global des réglages."""
        per_source = self._config.get("animation_by_source")
        if isinstance(per_source, dict):
            source = str(slide.get("source") or "").lower()
            value = str(per_source.get(source) or "").strip().lower()
            if value in self._ANIMATION_TYPES:
                return value
        return self._choice(
            self._config.get("animation_type"), self._ANIMATION_TYPES, "fade"
        )

    @staticmethod
    def _direction_vector(direction: str) -> tuple[float, float]:
        d = str(direction or "up").lower()
        return {
            "up": (0.0, -1.0),
            "down": (0.0, 1.0),
            "left": (-1.0, 0.0),
            "right": (1.0, 0.0),
        }.get(d, (0.0, -1.0))

    def _begin_transition(self, slide: dict[str, Any]) -> None:
        """Anime l'arrivée de la nouvelle slide. Le fond reste continu ;
        seul le bloc texte est animé comme un pixmap."""
        cfg = self._config
        anim_on = bool(cfg.get("animation_enabled", True))
        duration_value = cfg.get("animation_duration")
        duration = int(duration_value if duration_value is not None else 400)
        anim_type = self._effective_animation_type(slide)
        direction = str(cfg.get("animation_direction") or "up").lower()
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

        self._trans = {
            "out": QPixmap.fromImage(out_img),
            "outpos": out_pos,
            "in": QPixmap.fromImage(in_img),
            "inpos": in_pos,
            "type": anim_type,
            "dir": direction,
        }

        # Le flou est précalculé à demi-résolution : un seul coût au démarrage,
        # aucune re-blur par frame.
        if anim_type == "blur":
            blur_radius = float(max(10, min(40, duration // 16)))
            self._trans["out_blur"] = self._blurred_block(out_img, blur_radius)
            self._trans["in_blur"] = self._blurred_block(in_img, blur_radius)

        # Hide the live content; the pixmaps carry the animation.
        self._fade_effect.setOpacity(0.0)
        self._trans_p = 0.0
        self._trans_anim.stop()
        self._trans_anim.setDuration(duration)
        self._trans_anim.start()
        self.update()

    @staticmethod
    def _blurred_block(img: QImage, radius: float):
        """Version floue d'un bloc, calculée à demi-résolution puis remise
        à l'échelle (le flou gomme les détails, la perte est invisible)."""
        half = img.scaled(
            max(1, img.width() // 2),
            max(1, img.height() // 2),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        blurred = _blur_pixmap(QPixmap.fromImage(half), radius)
        return blurred.scaled(
            img.size(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

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
    def _ease(p: float) -> float:
        p = max(0.0, min(1.0, p))
        return p * p * p * (p * (p * 6 - 15) + 10)  # smootherstep

    def _draw_pix(self, painter, pix, x, y, scale, opacity) -> None:
        if opacity <= 0.004 or pix is None or pix.isNull():
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

    def _paint_transition(self, painter) -> None:
        """Dessine l'animation du bloc texte selon le type configuré :
        fondu, glissement, zoom, flou ou balayage (reveal)."""
        t = self._trans
        if not t:
            return
        e = self._ease(self._trans_p)
        kind = str(t.get("type") or "fade")
        dx, dy = self._direction_vector(str(t.get("dir") or "up"))
        w, h = float(self.width()), float(self.height())

        if kind == "slide":
            mv_x, mv_y = dx * w, dy * h
            self._draw_pix(
                painter, t["out"],
                t["outpos"].x() + mv_x * e, t["outpos"].y() + mv_y * e, 1.0, 1.0,
            )
            self._draw_pix(
                painter, t["in"],
                t["inpos"].x() - mv_x * (1.0 - e), t["inpos"].y() - mv_y * (1.0 - e),
                1.0, 1.0,
            )
            return

        if kind == "scale":
            self._draw_pix(
                painter, t["out"],
                t["outpos"].x(), t["outpos"].y(), 1.0 + 0.06 * e, 1.0 - e,
            )
            self._draw_pix(
                painter, t["in"],
                t["inpos"].x(), t["inpos"].y(), 0.94 + 0.06 * e, e,
            )
            return

        if kind == "blur":
            # Phase 1 : sortie nette → floue. Phase 2 : entrée floue → nette.
            if e < 0.5:
                p = e / 0.5
                self._draw_pix(painter, t["out"], t["outpos"].x(), t["outpos"].y(), 1.0, 1.0 - p)
                self._draw_pix(painter, t.get("out_blur"), t["outpos"].x(), t["outpos"].y(), 1.0, p)
            else:
                p = (e - 0.5) / 0.5
                self._draw_pix(painter, t.get("in_blur"), t["inpos"].x(), t["inpos"].y(), 1.0, 1.0 - p)
                self._draw_pix(painter, t["in"], t["inpos"].x(), t["inpos"].y(), 1.0, p)
            return

        if kind == "reveal":
            self._draw_pix(painter, t["out"], t["outpos"].x(), t["outpos"].y(), 1.0, 1.0)
            in_pix = t["in"]
            rect = QRectF(
                t["inpos"].x(), t["inpos"].y(),
                float(in_pix.width()), float(in_pix.height()),
            )
            # Balayage : le bord de révélation avance depuis le côté opposé
            # à la direction (monter = apparaître depuis le bas).
            if dy < 0:
                clip = QRectF(rect.left(), rect.bottom() - rect.height() * e,
                              rect.width(), rect.height() * e)
            elif dy > 0:
                clip = QRectF(rect.left(), rect.top(),
                              rect.width(), rect.height() * e)
            elif dx < 0:
                clip = QRectF(rect.right() - rect.width() * e, rect.top(),
                              rect.width() * e, rect.height())
            else:
                clip = QRectF(rect.left(), rect.top(),
                              rect.width() * e, rect.height())
            painter.save()
            painter.setClipRect(clip)
            self._draw_pix(painter, in_pix, t["inpos"].x(), t["inpos"].y(), 1.0, 1.0)
            painter.restore()
            return

        # fade (défaut) — fondu croisé élégant, façon PowerPoint.
        self._draw_pix(painter, t["out"], t["outpos"].x(), t["outpos"].y(), 1.0, 1.0 - e)
        self._draw_pix(painter, t["in"], t["inpos"].x(), t["inpos"].y(), 1.0, e)

    # ── Ken Burns (dérive lente du fond image) ────────────────────────────

    def _on_kb_value(self, value) -> None:
        p = float(value)
        if not self._kb_forward:
            p = 1.0 - p
        zoom = 1.0 + 0.085 * p
        pan_x = (p - 0.5) * 0.020
        pan_y = (0.5 - p) * 0.014
        self.set_ken_burns_state(zoom, pan_x, pan_y)

    def _on_kb_finished(self) -> None:
        # Ping-pong : la dérive repart en sens inverse, sans à-coup.
        self._kb_forward = not self._kb_forward
        self._kb_anim.start()

    def _update_ken_burns_state(self) -> None:
        active = (
            bool(self._config.get("ken_burns", True))
            and not self._background_pixmap.isNull()
            and not bool(self._current_slide.get("hidden"))
        )
        running = self._kb_anim.state() == QVariantAnimation.State.Running
        if active and not running:
            self._kb_forward = True
            self._kb_anim.start()
        elif not active and running:
            self._kb_anim.stop()
            self.set_ken_burns_state(1.0, 0.0, 0.0)

    def _set_visual_background(self, visual_path: str) -> None:
        super()._set_visual_background(visual_path)
        self._update_ken_burns_state()
