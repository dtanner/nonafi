# Wake word: "hey device"

`nonafi/models/hey_device.onnx` is a custom [openWakeWord](https://github.com/dscripka/openWakeWord) model. The voice service (`nonafi/voice.py`) loads it by default; `NONAFI_WAKEWORD` overrides it with a stock model name such as `hey_jarvis` or another `.onnx` path.

## Retraining

```bash
just train-wakeword     # = bash wakeword/train.sh
```

`train.sh` follows openWakeWord's automatic training recipe on this Mac instead of the Colab notebook:

1. Clones openWakeWord and rhasspy's piper-sample-generator into `~/.cache/nonafi-wakeword` and downloads the LibriTTS-R generator, the 17 GB ACAV100M negative-feature set, the validation feature set, the MIT room impulse responses, and one AudioSet shard.
2. Slices every mp3 under `~/Music/Mom` into two 30 s clips as additional background noise, so training sees the same music the jukebox plays while listening.
3. Generates 20k positive and 20k adversarial-negative synthetic clips with piper on the Apple GPU (about 15 minutes), augments them with reverb and background noise, extracts features, and trains the small classifier on CPU.
4. Copies the result to `nonafi/models/hey_device.onnx`. Then `just deploy` and `just voice-logs`.

`hey_device.yml` is the training config: the phrase, hand-picked confusable negatives ("hey dave", "the device"...), sample counts, and paths relative to the work dir. `generate_samples.py` adapts the current piper-sample-generator package to the older layout `train.py` imports. Reruns skip anything already downloaded or generated; delete `~/.cache/nonafi-wakeword/out` to regenerate clips after changing the phrase or negatives.

To try a different phrase, change `target_phrase` and `model_name` in `hey_device.yml`, run the script, and point `NONAFI_WAKEWORD` at the new file.
