from __future__ import annotations

import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.utils.app_paths import ndi_dir, resource_root


@dataclass(frozen=True)
class NdiAvailability:
    runtime_found: bool
    python_bridge_found: bool
    numpy_found: bool
    usable: bool
    runtime_paths: tuple[str, ...] = ()
    message: str = ""


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(resolved)
    return out


def _runtime_search_roots() -> list[Path]:
    roots: list[Path] = []

    for getter in (ndi_dir, lambda: resource_root() / "ndi"):
        try:
            roots.append(getter())
        except Exception:
            pass

    for env_name in (
        "NDI_RUNTIME_DIR_V6",
        "NDI_RUNTIME_DIR_V5",
        "NDI_RUNTIME_DIR",
        "NDI_SDK_DIR",
    ):
        raw = os.environ.get(env_name)
        if raw:
            roots.append(Path(raw))

    if sys.platform == "win32":
        for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(env_name)
            if not base:
                continue
            base_path = Path(base)
            roots.extend(
                [
                    base_path / "NDI",
                    base_path / "NewTek" / "NDI",
                    base_path / "NDI" / "NDI 6 Runtime",
                    base_path / "NDI" / "NDI 5 Runtime",
                    base_path / "NDI" / "NDI 4 Runtime",
                ]
            )

    return _dedupe_paths(roots)


def _discover_ndi_runtime_dirs() -> list[Path]:
    dirs: list[Path] = []
    dll_names = (
        "Processing.NDI.Lib.x64.dll",
        "Processing.NDI.Lib.x86.dll",
        "Processing.NDI.Lib.dll",
    )

    for root in _runtime_search_roots():
        if not root.exists() or not root.is_dir():
            continue

        for child in (root, root / "bin", root / "runtime", root / "lib", root / "v5", root / "v6"):
            if child.exists() and child.is_dir():
                dirs.append(child)

        for dll_name in dll_names:
            try:
                hits = list(root.rglob(dll_name))
            except Exception:
                hits = []
            for hit in hits[:8]:
                dirs.append(hit.parent)

    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        path = Path(entry)
        try:
            if path.is_dir() and any((path / dll_name).exists() for dll_name in dll_names):
                dirs.append(path)
        except Exception:
            continue

    return _dedupe_paths(dirs)


def _activate_ndi_runtime_dirs(paths: list[Path]) -> None:
    for path in paths:
        try:
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(path))
            os.environ["PATH"] = str(path) + os.pathsep + os.environ.get("PATH", "")
        except Exception:
            pass


def check_ndi_availability() -> NdiAvailability:
    runtime_dirs = _discover_ndi_runtime_dirs()
    _activate_ndi_runtime_dirs(runtime_dirs)

    np = None
    ndi = None
    try:
        import numpy as np  # type: ignore
    except Exception:
        np = None

    try:
        import NDIlib as ndi  # type: ignore
    except Exception:
        ndi = None

    runtime_found = bool(runtime_dirs)
    python_bridge_found = ndi is not None
    numpy_found = np is not None
    usable = python_bridge_found and numpy_found

    if usable:
        message = "NDI detecte et pret."
    else:
        missing = []
        if not python_bridge_found:
            missing.append("NDIlib")
        if not numpy_found:
            missing.append("numpy")
        if runtime_found:
            message = "Runtime NDI detecte."
        else:
            message = "Runtime NDI non detecte sur ce systeme."
        if missing:
            message += " Dependances Python manquantes: " + ", ".join(missing) + "."

    return NdiAvailability(
        runtime_found=runtime_found,
        python_bridge_found=python_bridge_found,
        numpy_found=numpy_found,
        usable=usable,
        runtime_paths=tuple(str(p) for p in runtime_dirs),
        message=message,
    )


def _try_import_ndi():
    try:
        runtime_dirs = _discover_ndi_runtime_dirs()
        _activate_ndi_runtime_dirs(runtime_dirs)

        import NDIlib as ndi  # type: ignore
        import numpy as np  # type: ignore

        return np, ndi
    except Exception:
        return None, None


def _parse_rgba_tuple(
    value: str, fallback: tuple[int, int, int, int]
) -> tuple[int, int, int, int]:
    s = str(value or "").strip().lower()
    if not s:
        return fallback
    if s.startswith("rgba") and "(" in s and ")" in s:
        inner = s[s.find("(") + 1 : s.rfind(")")]
        parts = [p.strip() for p in inner.split(",")]
        if len(parts) == 4:
            try:
                r = int(float(parts[0]))
                g = int(float(parts[1]))
                b = int(float(parts[2]))
                a = int(max(0.0, min(1.0, float(parts[3]))) * 255)
                return (r, g, b, a)
            except Exception:
                return fallback
    if s.startswith("rgb") and "(" in s and ")" in s:
        inner = s[s.find("(") + 1 : s.rfind(")")]
        parts = [p.strip() for p in inner.split(",")]
        if len(parts) >= 3:
            try:
                r = int(float(parts[0]))
                g = int(float(parts[1]))
                b = int(float(parts[2]))
                return (r, g, b, 255)
            except Exception:
                return fallback
    if s.startswith("#"):
        raw = s[1:]
        try:
            if len(raw) == 3:
                r = int(raw[0] * 2, 16)
                g = int(raw[1] * 2, 16)
                b = int(raw[2] * 2, 16)
                return (r, g, b, 255)
            if len(raw) >= 6:
                r = int(raw[0:2], 16)
                g = int(raw[2:4], 16)
                b = int(raw[4:6], 16)
                return (r, g, b, 255)
        except Exception:
            return fallback
    return fallback


def _wrap_text(draw, text: str, font, max_width: int) -> str:
    raw = str(text or "").replace("\r", "").strip()
    if not raw:
        return ""
    lines_out: list[str] = []
    for para in raw.split("\n"):
        words = [w for w in para.split(" ") if w]
        if not words:
            lines_out.append("")
            continue
        line = words[0]
        for w in words[1:]:
            test = f"{line} {w}".strip()
            w_px = draw.textlength(test, font=font)
            if w_px <= max_width:
                line = test
            else:
                lines_out.append(line)
                line = w
        lines_out.append(line)
    return "\n".join(lines_out)


@dataclass
class NdiLowerThirdConfig:
    layout_mode: str = "lower_third"
    panel_side: str = "left"
    safe_area_percent: int = 5
    font_family: str = "Google Sans"
    text_size: int = 48
    ref_size: int = 24
    align: str = "center"  # center|left|right
    show_reference: bool = True
    bg_color: str = "rgba(0, 0, 0, 0.75)"
    bg_opacity: float = 0.88
    text_color: str = "rgba(255, 255, 255, 0.95)"
    ref_color: str = "rgba(255, 255, 255, 0.7)"
    max_width: int = 82
    padding_horizontal: int = 48
    padding_vertical: int = 26
    border_radius: int = 22
    line_height: float = 1.16
    # Parity with the OBS web overlay (fully adjustable lower third)
    position: str = "bottom"  # bottom|top|center
    band_align: str = "center"  # left|center|right
    offset_x: int = 0
    offset_y: int = 0
    edge_margin: int = 64
    bg_enabled: bool = True
    bg_gradient_enabled: bool = False
    bg_color_2: str = ""
    text_transform: str = "none"  # none|uppercase
    text_shadow: bool = True
    show_accent_bar: bool = True
    accent_mode: str = "auto"  # auto|custom
    accent_color: str = "#74a7f8"
    opacity: float = 1.0


class NdiLowerThirdSender:
    def __init__(self, presentation_dir: Path, source_name: str) -> None:
        self._presentation_dir = presentation_dir
        self._source_name = str(source_name or "Project-On").strip() or "Project-On"

        self._slide_path = presentation_dir / "slide.json"
        self._cfg_path = presentation_dir / "obs-config.json"

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self._np = None
        self._ndi = None
        self._ndi_send = None
        self._video_frame = None

        self._last_slide_mtime: float = -1.0
        self._last_cfg_mtime: float = -1.0
        self._last_payload: dict[str, Any] | None = None
        self._last_cfg: dict[str, Any] | None = None

        self._width = 1920
        self._height = 1080

    @staticmethod
    def availability() -> NdiAvailability:
        return check_ndi_availability()

    def start(self) -> bool:
        np, ndi = _try_import_ndi()
        if np is None or ndi is None:
            return False
        self._np = np
        self._ndi = ndi

        if not ndi.initialize():
            return False

        # ndi-python supports both `send_create()` and `send_create(SendCreate(...))`
        # depending on wrapper version.
        try:
            self._ndi_send = ndi.send_create(
                ndi.SendCreate(p_ndi_name=self._source_name)
            )
        except Exception:
            self._ndi_send = ndi.send_create()
        if self._ndi_send is None:
            ndi.destroy()
            return False

        img = np.zeros((self._height, self._width, 4), dtype=np.uint8)
        video_frame = ndi.VideoFrameV2()
        video_frame.data = img
        video_frame.FourCC = ndi.FOURCC_VIDEO_TYPE_BGRA

        self._video_frame = video_frame
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

        if self._ndi is None:
            return
        try:
            if self._ndi_send is not None:
                self._ndi.send_destroy(self._ndi_send)
        finally:
            self._ndi_send = None
            self._video_frame = None
            try:
                self._ndi.destroy()
            except Exception:
                pass

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        try:
            if not path.exists() or not path.is_file():
                return None
            raw = path.read_text(encoding="utf-8")
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def _get_config(self) -> NdiLowerThirdConfig:
        cfg = self._last_cfg or {}
        out = NdiLowerThirdConfig()
        out.layout_mode = str(cfg.get("layout_mode") or out.layout_mode).lower()
        out.panel_side = str(cfg.get("panel_side") or out.panel_side).lower()
        try:
            out.safe_area_percent = max(
                0, min(15, int(cfg.get("safe_area_percent") or 0))
            )
        except Exception:
            pass
        out.font_family = str(cfg.get("font_family") or out.font_family)
        try:
            out.text_size = int(cfg.get("text_size") or out.text_size)
        except Exception:
            pass
        try:
            out.ref_size = int(cfg.get("ref_size") or out.ref_size)
        except Exception:
            pass
        out.align = str(cfg.get("align") or out.align)
        out.show_reference = bool(
            cfg.get("show_reference") if "show_reference" in cfg else out.show_reference
        )
        out.bg_color = str(cfg.get("bg_color") or out.bg_color)
        try:
            out.bg_opacity = float(
                cfg.get("bg_opacity") if "bg_opacity" in cfg else out.bg_opacity
            )
        except Exception:
            pass
        out.text_color = str(cfg.get("text_color") or out.text_color)
        out.ref_color = str(cfg.get("ref_color") or out.ref_color)
        for attr in (
            "max_width",
            "padding_horizontal",
            "padding_vertical",
            "border_radius",
        ):
            try:
                value = cfg.get(attr)
                if value is not None:
                    setattr(out, attr, int(value))
            except Exception:
                pass
        try:
            out.line_height = float(cfg.get("line_height") or out.line_height)
        except Exception:
            pass
        # Parity fields with the OBS web overlay
        out.position = str(cfg.get("position") or out.position).lower()
        out.band_align = str(cfg.get("band_align") or out.band_align).lower()
        for attr in ("offset_x", "offset_y"):
            try:
                setattr(out, attr, int(cfg.get(attr) or 0))
            except Exception:
                pass
        try:
            if cfg.get("edge_margin") is not None:
                out.edge_margin = max(0, int(cfg.get("edge_margin")))
        except Exception:
            pass
        out.bg_enabled = bool(
            cfg.get("bg_enabled") if "bg_enabled" in cfg else out.bg_enabled
        )
        out.bg_gradient_enabled = bool(cfg.get("bg_gradient_enabled"))
        out.bg_color_2 = str(cfg.get("bg_color_2") or "")
        out.text_transform = str(cfg.get("text_transform") or out.text_transform)
        out.text_shadow = bool(
            cfg.get("text_shadow") if "text_shadow" in cfg else out.text_shadow
        )
        out.show_accent_bar = bool(
            cfg.get("show_accent_bar")
            if "show_accent_bar" in cfg
            else out.show_accent_bar
        )
        out.accent_mode = str(cfg.get("accent_mode") or out.accent_mode)
        out.accent_color = str(cfg.get("accent_color") or out.accent_color)
        try:
            out.opacity = max(
                0.0,
                min(1.0, float(cfg.get("opacity") if "opacity" in cfg else out.opacity)),
            )
        except Exception:
            pass
        return out

    def _render(self, slide: dict[str, Any] | None) -> Any:
        assert self._np is not None

        from PIL import Image, ImageDraw, ImageFont  # type: ignore

        cfg = self._get_config()

        if not slide or bool(slide.get("hidden")):
            return self._np.zeros((self._height, self._width, 4), dtype=self._np.uint8)

        text = str(slide.get("text") or "")
        ref = str(slide.get("reference") or "")
        if not text.strip() and not ref.strip():
            return self._np.zeros((self._height, self._width, 4), dtype=self._np.uint8)

        if str(cfg.text_transform).lower() == "uppercase":
            text = text.upper()
            ref = ref.upper()

        img = Image.new("RGBA", (self._width, self._height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Fonts
        def _load_font(px: int):
            try:
                return ImageFont.truetype(cfg.font_family, px)
            except Exception:
                try:
                    return ImageFont.truetype("arial.ttf", px)
                except Exception:
                    return ImageFont.load_default()

        font_text = _load_font(int(cfg.text_size))
        font_ref = _load_font(int(cfg.ref_size))

        layout_mode = str(cfg.layout_mode or "lower_third").lower()
        max_width_pct = max(40, min(100, int(cfg.max_width)))
        if layout_mode == "fullscreen":
            max_width_pct = max(40, min(100, max_width_pct))
        elif layout_mode == "side_panel":
            max_width_pct = max(40, min(100, max_width_pct))
        elif layout_mode == "subtitle":
            max_width_pct = max(40, min(100, max_width_pct))
        elif layout_mode == "focus_card":
            max_width_pct = max(40, min(100, max_width_pct))
        box_max_w = int(self._width * max_width_pct / 100)
        pad_x = max(0, min(110, int(cfg.padding_horizontal)))
        pad_y = max(0, min(80, int(cfg.padding_vertical)))
        accent_gap = 26
        accent_w = 7
        inner_w = max(320, box_max_w - (pad_x * 2) - accent_w - accent_gap)
        wrapped_text = _wrap_text(draw, text, font_text, inner_w)

        text_fill = _parse_rgba_tuple(cfg.text_color, (255, 255, 255, 242))
        ref_fill = _parse_rgba_tuple(cfg.ref_color, (255, 255, 255, 178))
        source = str(slide.get("source") or "custom").lower()
        # Canonical palette — mirrors theme.Colors.SRC_* and obs-style.css .source-*
        accents = {
            "bible": ((86, 214, 129, 245), (181, 243, 202, 220)),
            "sermon": ((224, 160, 68, 245), (255, 217, 160, 220)),
            "hymn": ((185, 151, 255, 245), (232, 220, 255, 220)),
            "expose": ((0, 172, 193, 245), (127, 228, 239, 220)),
            "custom": ((116, 167, 248, 245), (207, 224, 255, 220)),
            "image": ((130, 123, 112, 245), (228, 222, 212, 220)),
        }
        accent, accent_2 = accents.get(source, accents["custom"])
        if str(cfg.accent_mode).lower() == "custom":
            custom = _parse_rgba_tuple(cfg.accent_color, accent)
            accent = (custom[0], custom[1], custom[2], 245)
            accent_2 = (custom[0], custom[1], custom[2], 220)

        line_spacing = max(4, int(cfg.text_size * (cfg.line_height - 1) * 0.72))
        bbox = draw.multiline_textbbox(
            (0, 0), wrapped_text, font=font_text, spacing=line_spacing, align="left"
        )
        text_w = (bbox[2] - bbox[0]) if bbox else 0
        text_h = (bbox[3] - bbox[1]) if bbox else 0

        ref_block = ""
        ref_w = 0
        ref_h = 0
        if cfg.show_reference and ref.strip():
            ref_block = _wrap_text(draw, ref, font_ref, inner_w)
            ref_bbox = draw.multiline_textbbox(
                (0, 0), ref_block, font=font_ref, spacing=4, align="left"
            )
            ref_w = (ref_bbox[2] - ref_bbox[0]) if ref_bbox else 0
            ref_h = (ref_bbox[3] - ref_bbox[1]) if ref_bbox else 0

        divider_gap = 15 if ref_block else 0
        ref_badge_h = ref_h + 14 if ref_block else 0
        content_w = min(inner_w, max(text_w, ref_w + 42, 340))
        box_w = min(box_max_w, content_w + pad_x * 2 + accent_w + accent_gap)
        box_h = text_h + ref_badge_h + divider_gap + pad_y * 2
        box_h = max(box_h, 136)

        # ── Band placement (position + band_align + fine offsets) ──────
        safe_margin = int(
            min(self._width, self._height) * cfg.safe_area_percent / 100
        )
        margin = max(0, int(cfg.edge_margin)) + safe_margin
        if layout_mode == "fullscreen":
            box_w = self._width - (margin * 2)
            box_h = self._height - (margin * 2)
        elif layout_mode == "side_panel":
            box_h = self._height - (margin * 2)
        elif layout_mode == "subtitle":
            box_w = min(box_w, self._width - (margin * 2))
        elif layout_mode == "focus_card":
            box_w = min(box_w, self._width - (margin * 2))
            box_h = max(box_h, int(self._height * 0.48))

        band_align = str(cfg.band_align).lower()
        if layout_mode == "side_panel":
            box_x = (
                self._width - box_w - margin
                if cfg.panel_side == "right"
                else margin
            )
        elif band_align == "left":
            box_x = margin
        elif band_align == "right":
            box_x = self._width - box_w - margin
        else:
            box_x = int((self._width - box_w) / 2)

        position = str(cfg.position).lower()
        if layout_mode in ("fullscreen", "side_panel", "focus_card"):
            box_y = int((self._height - box_h) / 2)
        elif position == "top":
            box_y = margin
        elif position == "center":
            box_y = int((self._height - box_h) / 2)
        else:
            box_y = self._height - box_h - margin

        box_x += int(cfg.offset_x)
        box_y += int(cfg.offset_y)
        box_x = max(-box_w, min(self._width, box_x))
        box_y = max(-box_h, min(self._height, box_y))

        radius = max(0, min(48, int(cfg.border_radius)))

        if cfg.bg_enabled:
            bg = _parse_rgba_tuple(cfg.bg_color, (8, 15, 28, int(0.82 * 255)))
            bg_alpha = int(255 * max(0.0, min(1.0, cfg.bg_opacity)))
            bg = (bg[0], bg[1], bg[2], bg_alpha)

            for offset, alpha in ((18, 34), (8, 48)):
                draw.rounded_rectangle(
                    [box_x, box_y + offset, box_x + box_w, box_y + box_h + offset],
                    radius=radius,
                    fill=(0, 0, 0, alpha),
                )

            if cfg.bg_gradient_enabled and cfg.bg_color_2.strip():
                # Vertical two-colour gradient inside a rounded-corner mask.
                bg2 = _parse_rgba_tuple(cfg.bg_color_2, bg)
                bg2 = (bg2[0], bg2[1], bg2[2], bg_alpha)
                grad = Image.new("RGBA", (1, max(2, box_h)))
                for gy in range(grad.height):
                    t = gy / (grad.height - 1)
                    grad.putpixel(
                        (0, gy),
                        (
                            int(bg[0] + (bg2[0] - bg[0]) * t),
                            int(bg[1] + (bg2[1] - bg[1]) * t),
                            int(bg[2] + (bg2[2] - bg[2]) * t),
                            bg_alpha,
                        ),
                    )
                grad = grad.resize((max(1, box_w), max(2, box_h)))
                mask = Image.new("L", grad.size, 0)
                ImageDraw.Draw(mask).rounded_rectangle(
                    [0, 0, grad.width - 1, grad.height - 1], radius=radius, fill=255
                )
                img.paste(grad, (box_x, box_y), mask)
            else:
                draw.rounded_rectangle(
                    [box_x, box_y, box_x + box_w, box_y + box_h],
                    radius=radius,
                    fill=bg,
                )

            if cfg.show_accent_bar:
                draw.rounded_rectangle(
                    [
                        box_x + pad_x,
                        box_y + box_h - 2,
                        box_x + box_w - pad_x,
                        box_y + box_h,
                    ],
                    radius=2,
                    fill=accent_2,
                )

        accent_x = box_x + pad_x
        accent_y = box_y + pad_y
        if cfg.bg_enabled and cfg.show_accent_bar:
            draw.rounded_rectangle(
                [accent_x, accent_y, accent_x + accent_w, box_y + box_h - pad_y],
                radius=accent_w,
                fill=accent,
            )

        content_x = accent_x + accent_w + accent_gap
        content_block_h = text_h + ref_badge_h + divider_gap
        content_y = box_y + max(
            pad_y,
            int((box_h - content_block_h) / 2)
            if layout_mode in ("fullscreen", "side_panel", "focus_card")
            else pad_y,
        )
        cfg_align = str(cfg.align).lower()
        align_mode = cfg_align if cfg_align in ("left", "right") else "center"
        if align_mode == "left":
            text_x = content_x
            anchor = None
        elif align_mode == "right":
            text_x = content_x + content_w
            anchor = "ra"
        else:
            text_x = content_x + content_w // 2
            anchor = "ma"

        if cfg.text_shadow:
            shadow_fill = (0, 0, 0, 132)
            draw.multiline_text(
                (text_x + (2 if align_mode == "left" else 0), content_y + 3),
                wrapped_text,
                font=font_text,
                fill=shadow_fill,
                spacing=line_spacing,
                align=align_mode,
                anchor=anchor,
            )
        draw.multiline_text(
            (text_x, content_y),
            wrapped_text,
            font=font_text,
            fill=text_fill,
            spacing=line_spacing,
            align=align_mode,
            anchor=anchor,
        )

        if ref_block:
            divider_y = content_y + text_h + 14
            draw.line(
                [content_x, divider_y, content_x + content_w, divider_y],
                fill=(accent[0], accent[1], accent[2], 120),
                width=2,
            )
            badge_y = divider_y + 14
            badge_w = min(content_w, ref_w + 42)
            if align_mode == "left":
                badge_x = content_x
            elif align_mode == "right":
                badge_x = content_x + content_w - badge_w
            else:
                badge_x = content_x + (content_w - badge_w) // 2
            draw.rounded_rectangle(
                [badge_x, badge_y, badge_x + badge_w, badge_y + ref_badge_h],
                radius=ref_badge_h // 2,
                fill=(255, 255, 255, 18),
            )
            if align_mode == "center":
                ref_x = badge_x + badge_w // 2
                ref_anchor = "ma"
            elif align_mode == "right":
                ref_x = badge_x + badge_w - 20
                ref_anchor = "ra"
            else:
                ref_x = badge_x + 20
                ref_anchor = None
            draw.multiline_text(
                (ref_x, badge_y + 7),
                ref_block,
                font=font_ref,
                fill=ref_fill,
                spacing=4,
                align=align_mode,
                anchor=ref_anchor,
            )

        rgba = self._np.array(img, dtype=self._np.uint8)
        opacity = max(0.0, min(1.0, float(cfg.opacity)))
        if opacity < 1.0:
            rgba[:, :, 3] = (rgba[:, :, 3].astype(self._np.float32) * opacity).astype(
                self._np.uint8
            )
        bgra = rgba[:, :, [2, 1, 0, 3]].copy()
        return bgra

    def _run(self) -> None:
        assert self._ndi is not None
        assert self._np is not None
        assert self._ndi_send is not None
        assert self._video_frame is not None

        fps = 30.0
        interval = 1.0 / fps

        last_frame = self._np.zeros(
            (self._height, self._width, 4), dtype=self._np.uint8
        )

        needs_render = True
        while not self._stop.is_set():
            try:
                cfg_mtime = (
                    self._cfg_path.stat().st_mtime if self._cfg_path.exists() else -1.0
                )
            except Exception:
                cfg_mtime = -1.0
            if cfg_mtime != self._last_cfg_mtime:
                self._last_cfg_mtime = cfg_mtime
                self._last_cfg = self._read_json(self._cfg_path) or {}
                needs_render = True

            try:
                slide_mtime = (
                    self._slide_path.stat().st_mtime
                    if self._slide_path.exists()
                    else -1.0
                )
            except Exception:
                slide_mtime = -1.0
            if slide_mtime != self._last_slide_mtime:
                self._last_slide_mtime = slide_mtime
                self._last_payload = self._read_json(self._slide_path)
                needs_render = True

            # Only re-render (PIL raster) when the slide or config actually
            # changed; the same cached frame is streamed at a steady rate.
            if needs_render:
                try:
                    frame = self._render(self._last_payload)
                except Exception:
                    frame = None
                if frame is not None:
                    last_frame = frame
                needs_render = False

            # Reuse frame object; swap underlying data
            self._video_frame.data = last_frame
            self._ndi.send_send_video_v2(self._ndi_send, self._video_frame)

            time.sleep(interval)
