from __future__ import annotations

from pathlib import Path

from PIL import Image


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    src = root / "assets" / "logo" / "app icon.png"
    out_dir = root / "build"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "app.ico"

    img = Image.open(src).convert("RGBA")

    # Common Windows icon sizes
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(out, format="ICO", sizes=sizes)

    print(f"Wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
