"""
Génère une musique d'ambiance ORIGINALE et 100 % libre de droits pour la vidéo.

Pad chaleureux et apaisant (synthèse additive), progression Bm - G - D - A,
adapté à une présentation d'église. Aucune source externe : aucun problème de
droits d'auteur sur YouTube.

Usage :  py -3 docs/make_music.py [duree_secondes]
Sortie :  docs/music.wav   (stéréo, 44.1 kHz)
"""
import sys, wave, pathlib
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "music.wav"
SR = 44100

# Triades (basse + 3 notes), en Hz. Progression douce et lumineuse.
CHORDS = [
    {"bass": 123.47, "triad": [246.94, 293.66, 369.99]},  # Si mineur
    {"bass":  98.00, "triad": [196.00, 246.94, 293.66]},  # Sol majeur
    {"bass": 146.83, "triad": [293.66, 369.99, 440.00]},  # Ré majeur
    {"bass": 110.00, "triad": [220.00, 277.18, 329.63]},  # La majeur
]

SEG = 8.0      # durée d'un accord (s)
STEP = 7.0     # avance entre accords -> 1 s de fondu enchaîné


def pad_voice(freq, n, pan, shimmer=False):
    """Une voix de pad : deux sinus légèrement désaccordés (chorus) + harmonique douce."""
    t = np.arange(n) / SR
    detune = 0.25
    base = (np.sin(2 * np.pi * (freq - detune) * t)
            + np.sin(2 * np.pi * (freq + detune) * t)) * 0.5
    base += 0.30 * np.sin(2 * np.pi * (2 * freq) * t)        # octave (corps)
    if shimmer:
        base += 0.12 * np.sin(2 * np.pi * (3 * freq) * t)    # quinte aiguë (éclat)
    left = base * (0.5 + 0.5 * (1 - pan))
    right = base * (0.5 + 0.5 * pan)
    return left, right


def chord_window(n):
    """Enveloppe en cosinus surélevé : montée 1.5 s, tenue, descente 1.5 s."""
    env = np.ones(n)
    r = int(1.5 * SR)
    ramp = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, r))
    env[:r] = ramp
    env[-r:] = ramp[::-1]
    return env


def main():
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 140.0
    total = int((dur + SEG) * SR)
    L = np.zeros(total)
    R = np.zeros(total)

    seg_n = int(SEG * SR)
    win = chord_window(seg_n)

    i = 0
    pos = 0.0
    while pos < dur:
        ch = CHORDS[i % len(CHORDS)]
        start = int(pos * SR)
        sl = slice(start, start + seg_n)

        # basse douce
        bl, br = pad_voice(ch["bass"], seg_n, pan=0.5)
        L[sl] += bl * win * 0.32
        R[sl] += br * win * 0.32

        # triade, voix réparties dans le champ stéréo
        pans = [0.18, 0.5, 0.82]
        for note, pan in zip(ch["triad"], pans):
            vl, vr = pad_voice(note, seg_n, pan=pan, shimmer=True)
            L[sl] += vl * win * 0.22
            R[sl] += vr * win * 0.22

        i += 1
        pos += STEP

    # léger battement d'amplitude (respiration) + normalisation douce
    t = np.arange(total) / SR
    breath = 1.0 + 0.07 * np.sin(2 * np.pi * 0.06 * t)
    L *= breath
    R *= breath

    peak = max(np.abs(L).max(), np.abs(R).max(), 1e-9)
    gain = 0.5 / peak           # niveau de fond confortable (-6 dB env.)
    L *= gain
    R *= gain

    # fondu d'entrée (3 s) baké dans le fichier
    fin = int(3.0 * SR)
    fade = np.linspace(0, 1, fin)
    L[:fin] *= fade
    R[:fin] *= fade

    stereo = np.empty((total, 2), dtype=np.float32)
    stereo[:, 0] = L
    stereo[:, 1] = R
    pcm = np.int16(np.clip(stereo, -1, 1) * 32767)

    with wave.open(str(OUT), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())

    print(f"[OK] Musique : {OUT}  ({total/SR:.1f}s)")


if __name__ == "__main__":
    main()
