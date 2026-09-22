"""Score wake-word models on macOS `say` voices, confusable phrases, and speech mixed with library music.

    ~/.cache/nonafi-wakeword/.venv/bin/python wakeword/eval.py nonafi/models/hey_device.onnx [more.onnx ...]

Runs from the training work dir's venv (it needs openwakeword and soundfile) and uses the 16 kHz music slices
in ~/.cache/nonafi-wakeword/background_clips/music made by train.sh. `say` is a different TTS engine from the
piper voices the model was trained on, so it is a fair, if clean, generalization check.
"""
import os, subprocess, sys, tempfile
import numpy as np
import soundfile as sf
from openwakeword.model import Model

WORK = os.environ.get("NONAFI_WAKEWORD_WORK", os.path.expanduser("~/.cache/nonafi-wakeword"))
PHRASE = "hey device"
VOICES = ["Samantha", "Daniel", "Karen", "Moira"]
NEGATIVES = ["hey dave", "the device is on", "hey there", "play some music", "hey david", "nice device"]
SR = 16000


def say(text, voice, out):
    aiff = out + ".aiff"
    subprocess.run(["say", "-v", voice, "-o", aiff, text], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", aiff, "-ar", str(SR), "-ac", "1", "-sample_fmt", "s16", out], check=True)
    a, _ = sf.read(out, dtype="float32")
    return np.concatenate([np.zeros(SR, np.float32), a, np.zeros(SR, np.float32)])


def score(model, audio):
    model.reset()
    best = {k: 0.0 for k in model.models}
    for i in range(0, len(audio) - 1280, 1280):
        for k, v in model.predict((audio[i:i + 1280] * 32767).astype(np.int16)).items():
            best[k] = max(best[k], v)
    return best


def main(paths):
    model = Model(wakeword_models=paths, inference_framework="onnx")
    keys = list(model.models)
    tmp = tempfile.mkdtemp()
    pos = {v: say(PHRASE, v, f"{tmp}/{v}.wav") for v in VOICES}
    neg = {t: say(t, "Samantha", f"{tmp}/{i}.wav") for i, t in enumerate(NEGATIVES)}
    print(f"{'clip':34s} " + "  ".join(f"{k[-8:]:>8s}" for k in keys))
    for name, a in [(f'"{PHRASE}" ({v})', a) for v, a in pos.items()] + [(f'"{t}"', a) for t, a in neg.items()]:
        print(f"{name:34s} " + "  ".join(f"{s:8.2f}" for s in score(model, a).values()))

    music_dir = os.path.join(WORK, "background_clips", "music")
    songs = sorted(os.listdir(music_dir))[:6] if os.path.isdir(music_dir) else []
    if not songs:
        return
    print("\nvoice-to-music ratio: share of clips scoring >= 0.5, over 4 voices x 6 songs")
    for db in (10, 5, 0):
        hits = {k: [] for k in keys}
        for a in pos.values():
            for s in songs:
                mu, _ = sf.read(os.path.join(music_dir, s), dtype="float32")
                mu = mu[:len(a)]
                g = np.sqrt((a ** 2).mean()) / (np.sqrt((mu ** 2).mean()) + 1e-9) / 10 ** (db / 20)
                for k, v in score(model, np.clip(a + g * mu, -1, 1)).items():
                    hits[k].append(v >= 0.5)
        print(f"{db:3d} dB {'':27s} " + "  ".join(f"{np.mean(h):8.0%}" for h in hits.values()))
    fp = {k: 0.0 for k in keys}
    for s in sorted(os.listdir(music_dir))[:40]:
        for k, v in score(model, sf.read(os.path.join(music_dir, s), dtype="float32")[0]).items():
            fp[k] = max(fp[k], v)
    print(f"{'music only, max score (40 clips)':34s} " + "  ".join(f"{v:8.2f}" for v in fp.values()))


if __name__ == "__main__":
    main(sys.argv[1:])
