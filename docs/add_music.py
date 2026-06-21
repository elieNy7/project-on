"""
Incruste une piste audio sur la vidéo MP4 (fondu d'entrée/sortie, AAC).

Génère la musique si docs/music.wav est absent, l'ajuste à la durée exacte de
la vidéo (fondu de sortie), puis remux en réécrivant le MP4.

Usage :  py -3 docs/add_music.py
"""
import re, subprocess, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
VIDEO = HERE / "Project-On_presentation.mp4"
MUSIC = HERE / "music.wav"


def ffmpeg_exe():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def video_duration(ff, path):
    out = subprocess.run([ff, "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", out)
    if not m:
        return None
    h, mn, s = m.groups()
    return int(h) * 3600 + int(mn) * 60 + float(s)


def add_music(video=VIDEO, music=MUSIC):
    ff = ffmpeg_exe()

    if not music.exists():
        print("Musique absente, génération…")
        subprocess.run([sys.executable, str(HERE / "make_music.py")], check=True)

    dur = video_duration(ff, video) or 130.0
    fade_out = max(dur - 5.0, 0.1)
    tmp = video.with_name(video.stem + "_tmp.mp4")

    cmd = [
        ff, "-y",
        "-i", str(video),
        "-i", str(music),
        "-filter_complex",
        f"[1:a]afade=t=in:st=0:d=3,afade=t=out:st={fade_out:.2f}:d=5[a]",
        "-map", "0:v:0", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", str(tmp),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-3000:])
        sys.exit("Echec ffmpeg (mux audio).")

    tmp.replace(video)
    print(f"[OK] Musique ajoutee : {video}  (duree {dur:.1f}s)")


if __name__ == "__main__":
    add_music()
