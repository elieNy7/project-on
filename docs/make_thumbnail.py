"""
Rend docs/thumbnail.html en miniature YouTube PNG 1280x720 (nette, x2 + downscale).

Usage :  py -3 docs/make_thumbnail.py
Sortie :  docs/youtube_thumbnail.png
"""
import pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
HTML = HERE / "thumbnail.html"
OUT = HERE / "youtube_thumbnail.png"
TMP = HERE / "_thumb_2x.png"


def main():
    from playwright.sync_api import sync_playwright
    import imageio_ffmpeg

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--force-color-profile=srgb"])
        ctx = b.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=2)
        page = ctx.new_page()
        page.goto(HTML.as_uri(), wait_until="load")
        page.wait_for_timeout(600)  # polices + image
        page.screenshot(path=str(TMP), clip={"x": 0, "y": 0, "width": 1280, "height": 720})
        ctx.close(); b.close()

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    r = subprocess.run([ff, "-y", "-i", str(TMP),
                        "-vf", "scale=1280:720:flags=lanczos", str(OUT)],
                       capture_output=True, text=True)
    TMP.unlink(missing_ok=True)
    if r.returncode != 0:
        print(r.stderr[-2000:]); sys.exit("Echec ffmpeg.")
    print(f"[OK] Miniature : {OUT}  ({OUT.stat().st_size/1024:.0f} Ko)")


if __name__ == "__main__":
    main()
