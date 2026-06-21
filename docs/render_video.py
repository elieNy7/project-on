"""
Rend la présentation HTML (docs/presentation.html) en vidéo MP4.

Pilote Chromium via Playwright, enregistre la lecture automatique en .webm,
puis transcode en .mp4 (H.264) avec le ffmpeg fourni par imageio-ffmpeg.

Usage :  py -3 docs/render_video.py
Sortie :  docs/Project-On_presentation.mp4   (1920x1080)
"""
import sys, time, pathlib, subprocess

HERE = pathlib.Path(__file__).resolve().parent
HTML = HERE / "presentation.html"
OUT_MP4 = HERE / "Project-On_presentation.mp4"
RAW_DIR = HERE / "_render_raw"
W, H = 1920, 1080

def main():
    from playwright.sync_api import sync_playwright
    import imageio_ffmpeg

    RAW_DIR.mkdir(exist_ok=True)
    url = HTML.as_uri() + "?autoplay=1"
    print(f"[1/3] Rendu de la page : {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--autoplay-policy=no-user-gesture-required",
                  "--force-color-profile=srgb",
                  "--disable-lcd-text"],
        )
        context = browser.new_context(
            viewport={"width": W, "height": H},
            device_scale_factor=1,
            record_video_dir=str(RAW_DIR),
            record_video_size={"width": W, "height": H},
        )
        page = context.new_page()
        page.goto(url, wait_until="load")

        total = page.evaluate("() => window.__total") or 125
        print(f"      Durée de la présentation : ~{total:.0f}s — patientez…")

        # Attend la fin réelle de la timeline (avec marge de sécurité).
        deadline = time.time() + total + 25
        while time.time() < deadline:
            if page.evaluate("() => window.__done === true"):
                break
            time.sleep(0.5)

        time.sleep(0.4)  # laisse passer la toute dernière frame
        video = page.video
        context.close()          # flush du fichier .webm
        browser.close()
        webm = pathlib.Path(video.path())
    print(f"[2/3] Vidéo brute : {webm.name}")

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    print(f"[3/3] Transcodage MP4 (H.264)…")
    cmd = [
        ffmpeg, "-y", "-i", str(webm),
        "-vf", f"scale={W}:{H}:flags=lanczos,format=yuv420p,fps=30",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-movflags", "+faststart",
        str(OUT_MP4),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-3000:])
        sys.exit("Échec ffmpeg.")

    # Ajoute la musique d'ambiance (génère music.wav si absent).
    try:
        import add_music
        add_music.add_music(video=OUT_MP4)
    except Exception as e:
        print(f"(Musique non ajoutee : {e})")

    size_mb = OUT_MP4.stat().st_size / 1e6
    print(f"\n[OK] Termine : {OUT_MP4}  ({size_mb:.1f} Mo)")

if __name__ == "__main__":
    main()
