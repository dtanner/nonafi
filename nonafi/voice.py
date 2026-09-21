"""Voice control: wake word (openWakeWord) -> record a command -> transcribe (faster-whisper) -> POST /api/command.

Runs as its own process (`python -m nonafi.voice`) beside the server. Audio comes straight from ALSA via `arecord`,
16 kHz mono 16-bit, so no PipeWire source needs to be configured for the mic.

Environment:
  NONAFI_MIC       ALSA device, default: first USB capture card (plughw:CARD=...)
  NONAFI_WAKEWORD  openWakeWord model name or .onnx path, default "hey_jarvis"
  NONAFI_WAKE_THRESHOLD  0..1, default 0.5
  NONAFI_WHISPER   faster-whisper model, default "base.en"
  NONAFI_URL       server base URL, default http://127.0.0.1:8080
"""

from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import time
import urllib.request

import numpy as np

RATE = 16000
CHUNK = 1280                 # 80 ms, the frame size openWakeWord expects
MAX_COMMAND_S = 5.0          # stop listening after this long
SILENCE_S = 0.9              # ...or after this much quiet once speech has started
MIN_SPEECH_S = 0.3
COOLDOWN_S = 1.5             # ignore wake word for this long after a command


def log(*a):
    print("voice:", *a, flush=True)


# --- audio ----------------------------------------------------------------

def find_mic() -> str:
    dev = os.environ.get("NONAFI_MIC")
    if dev:
        return dev
    try:
        out = subprocess.run(["arecord", "-l"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        out = ""
    m = re.search(r"card \d+: (\S+) \[", out)
    return f"plughw:CARD={m.group(1)}" if m else "default"


def open_mic(device: str) -> subprocess.Popen:
    cmd = ["arecord", "-q", "-D", device, "-f", "S16_LE", "-r", str(RATE), "-c", "1", "-t", "raw"]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=CHUNK * 2 * 4)


def read_chunk(proc: subprocess.Popen) -> np.ndarray | None:
    data = proc.stdout.read(CHUNK * 2)
    if len(data) < CHUNK * 2:
        return None
    return np.frombuffer(data, dtype=np.int16)


def set_volume(level: float) -> None:
    try:
        subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", str(level)], timeout=3)
    except Exception:
        pass


# --- server -----------------------------------------------------------------

def post(url: str, obj: dict) -> None:
    try:
        req = urllib.request.Request(url + "/api/command", data=json.dumps(obj).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=3).read()
    except Exception as e:
        log("post failed:", e)


def albums(url: str) -> list[dict]:
    try:
        return json.loads(urllib.request.urlopen(url + "/api/albums", timeout=5).read())
    except Exception:
        return []


# --- intent -----------------------------------------------------------------

def normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split())


def interpret(text: str, lib: list[dict]) -> dict | None:
    """Map a transcript to a command for the UI."""
    t = normalize(text)
    if not t:
        return None
    words = set(t.split())
    if words & {"pause", "stop", "quiet", "silence", "hush"}:
        return {"action": "pause"}
    if words & {"next", "skip", "forward"}:
        return {"action": "next"}
    if re.search(r"\b(resume|continue|unpause|keep going)\b", t):
        return {"action": "play"}
    m = re.search(r"\b(?:play|put on|start)\b(.*)", t)
    if not m and not (words & {"music", "song", "songs", "album"}):
        return None
    rest = normalize(m.group(1) if m else t)
    rest = re.sub(r"\b(some|the|a|an|me|please|album|by|music|songs?|something)\b", " ", rest)
    rest = " ".join(rest.split())
    if not rest:
        return {"action": "play"}
    best = match_album(rest, lib)
    if best:
        return {"action": "play_album", "album": best["id"], "title": best["title"]}
    return {"action": "play"}


def match_album(query: str, lib: list[dict]) -> dict | None:
    scored = []
    for a in lib:
        for cand in (a["title"], a.get("artist", ""), f'{a["title"]} {a.get("artist", "")}'):
            c = normalize(cand)
            if not c:
                continue
            score = difflib.SequenceMatcher(None, query, c).ratio()
            if query in c or c in query:
                score = max(score, 0.85)
            scored.append((score, a))
    if not scored:
        return None
    score, a = max(scored, key=lambda x: x[0])
    return a if score >= 0.55 else None


# --- main loop --------------------------------------------------------------

def main(argv=None):
    from openwakeword.model import Model  # slow imports kept out of --help paths
    from openwakeword.utils import download_models
    from faster_whisper import WhisperModel

    url = os.environ.get("NONAFI_URL", "http://127.0.0.1:8080")
    wake = os.environ.get("NONAFI_WAKEWORD", "hey_jarvis")
    threshold = float(os.environ.get("NONAFI_WAKE_THRESHOLD", "0.5"))
    whisper_name = os.environ.get("NONAFI_WHISPER", "base.en")
    mic = find_mic()

    if not wake.endswith(".onnx") and not os.path.exists(wake):
        download_models([wake])
    oww = Model(wakeword_models=[wake], inference_framework="onnx")
    wake_key = list(oww.models)[0]
    whisper = WhisperModel(whisper_name, device="cpu", compute_type="int8", cpu_threads=4)
    log(f"ready: mic={mic} wakeword={wake_key} threshold={threshold} whisper={whisper_name}")

    proc = open_mic(mic)
    last_fire = 0.0
    while True:
        chunk = read_chunk(proc)
        if chunk is None:
            log("mic stream ended, reopening")
            proc.kill()
            time.sleep(1)
            proc = open_mic(mic)
            continue
        score = oww.predict(chunk)[wake_key]
        if score < threshold or time.monotonic() - last_fire < COOLDOWN_S:
            continue

        log(f"wake word ({score:.2f})")
        post(url, {"action": "listening"})
        set_volume(0.15)
        try:
            audio = record_command(proc)
        finally:
            set_volume(1.0)
        oww.reset()
        last_fire = time.monotonic()

        t0 = time.time()
        segments, _ = whisper.transcribe(audio, language="en", beam_size=1, vad_filter=False,
                                         condition_on_previous_text=False)
        text = " ".join(s.text.strip() for s in segments).strip()
        log(f"heard {text!r} in {time.time() - t0:.1f}s")
        cmd = interpret(text, albums(url))
        post(url, {"action": "heard", "text": text, "command": cmd})
        if cmd:
            log("command:", cmd)
            post(url, cmd)


def record_command(proc: subprocess.Popen) -> np.ndarray:
    """Capture until the speaker goes quiet (energy-based), returning float32 audio."""
    frames: list[np.ndarray] = []
    noise = None
    speech_started = False
    quiet_for = 0.0
    start = time.monotonic()
    while time.monotonic() - start < MAX_COMMAND_S:
        chunk = read_chunk(proc)
        if chunk is None:
            break
        frames.append(chunk)
        rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2))) + 1e-6
        # Track the noise floor: drop to quieter frames at once, creep up slowly otherwise.
        noise = rms if noise is None or rms < noise else noise * 1.02
        loud = rms > max(noise * 3.0, 150.0)
        elapsed = time.monotonic() - start
        if loud:
            speech_started = True
            quiet_for = 0.0
        elif speech_started:
            quiet_for += CHUNK / RATE
            if quiet_for >= SILENCE_S and elapsed >= MIN_SPEECH_S:
                break
    if not frames:
        return np.zeros(RATE, dtype=np.float32)
    return np.concatenate(frames).astype(np.float32) / 32768.0


if __name__ == "__main__":
    main()
