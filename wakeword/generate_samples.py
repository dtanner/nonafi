"""Adapter so openWakeWord's train.py (which expects the old dscripka piper-sample-generator layout)
can use the current rhasspy piper-sample-generator package, which has no 16 kHz output option."""
import os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "piper-sample-generator")
sys.path.insert(0, os.path.abspath(ROOT))
from piper_sample_generator.__main__ import generate_samples as _generate_samples

MODEL = os.path.join(ROOT, "models", "en_US-libritts_r-medium.pt")
TARGET_SR = 16000


def generate_samples(text, output_dir, max_samples=None, batch_size=1, **kwargs):
    kwargs.pop("auto_reduce_batch_size", None)
    kwargs.setdefault("max_speakers", 400)
    kwargs.setdefault("slerp_weights", (0.0, 0.25, 0.5, 0.75, 1.0))
    _generate_samples(text=text, output_dir=output_dir, model=MODEL, max_samples=max_samples,
                      batch_size=batch_size, **kwargs)
    resample_dir(output_dir)


def resample_dir(output_dir):
    """openWakeWord trains on 16 kHz; piper emits 22.05 kHz."""
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly
    for name in os.listdir(output_dir):
        path = os.path.join(output_dir, name)
        if not name.endswith(".wav") or sf.info(path).samplerate == TARGET_SR:
            continue
        data, sr = sf.read(path, dtype="float32")
        data = resample_poly(data, TARGET_SR, sr)
        sf.write(path, np.clip(data, -1, 1), TARGET_SR, subtype="PCM_16")
