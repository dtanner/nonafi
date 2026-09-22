#!/usr/bin/env bash
# Train the "hey device" openWakeWord model. See wakeword/README.md.
# Idempotent: downloads, conversions, and generated clips are reused on rerun.
# Work dir: ~/.cache/nonafi-wakeword (override with NONAFI_WAKEWORD_WORK). Needs uv, git, curl, ffmpeg.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=${NONAFI_WAKEWORD_WORK:-$HOME/.cache/nonafi-wakeword}
MUSIC=${NONAFI_WAKEWORD_MUSIC:-$HOME/Music/Mom}
HF=https://huggingface.co
mkdir -p "$WORK" && cd "$WORK"

fetch() { [ -s "$2" ] || curl -sSL -C - -o "$2" "$1"; }

echo "== code and models"
[ -d openWakeWord ] || git clone -q --depth 1 https://github.com/dscripka/openWakeWord.git
[ -d piper-sample-generator ] || git clone -q --depth 1 https://github.com/rhasspy/piper-sample-generator.git
fetch https://github.com/rhasspy/piper-sample-generator/releases/download/v2.0.0/en_US-libritts_r-medium.pt \
      piper-sample-generator/models/en_US-libritts_r-medium.pt

echo "== negative and validation features (17 GB + 185 MB)"
fetch $HF/datasets/davidscripka/openwakeword_features/resolve/main/openwakeword_features_ACAV100M_2000_hrs_16bit.npy \
      openwakeword_features_ACAV100M_2000_hrs_16bit.npy
fetch $HF/datasets/davidscripka/openwakeword_features/resolve/main/validation_set_features.npy validation_set_features.npy

echo "== room impulse responses"
if [ ! -d mit_rirs ]; then
  mkdir mit_rirs
  curl -s "$HF/api/datasets/davidscripka/MIT_environmental_impulse_responses/tree/main/16khz" \
    | python3 -c 'import sys,json; [print(x["path"]) for x in json.load(sys.stdin)]' \
    | while read -r p; do curl -sSL -o "mit_rirs/$(basename "$p")" "$HF/datasets/davidscripka/MIT_environmental_impulse_responses/resolve/main/$p"; done
fi

echo "== python env"
[ -x .venv/bin/python ] || uv venv -q -p 3.11 .venv
uv pip install -q -p .venv/bin/python -e ./openWakeWord -e ./piper-sample-generator \
  "torch==2.8.*" "torchaudio==2.8.*" "torchinfo>=1.8" "torchmetrics>=0.11.4,<1" "speechbrain>=0.5.14,<1" \
  "audiomentations==0.33.0" "torch-audiomentations>=0.11.0,<1" mutagen tqdm pronouncing acoustics \
  pyyaml soundfile pyarrow onnx onnxruntime "scipy<1.17" "setuptools<81"

.venv/bin/python -c "from openwakeword.utils import download_models; download_models(['hey_jarvis'])"  # feature models

echo "== background noise: one AudioSet shard (500 clips) and 30 s slices of the music library"
mkdir -p background_clips/audioset background_clips/music
if [ -z "$(ls background_clips/audioset)" ]; then
  fetch $HF/datasets/agkphysics/AudioSet/resolve/main/data/bal_train/00.parquet audioset_00.parquet
  .venv/bin/python - <<'PY'
import pyarrow.parquet as pq, subprocess
f = pq.ParquetFile('audioset_00.parquet')
for rg in range(f.num_row_groups):
    for row in f.read_row_group(rg, columns=['video_id', 'audio']).to_pylist():
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', 'pipe:0', '-ar', '16000', '-ac', '1',
                        '-sample_fmt', 's16', f"background_clips/audioset/{row['video_id']}.wav"],
                       input=row['audio']['bytes'], check=True)
PY
fi
if [ -d "$MUSIC" ] && [ -z "$(ls background_clips/music)" ]; then
  i=0
  find "$MUSIC" -name '*.mp3' | while read -r f; do
    i=$((i + 1))
    for ss in 20 100; do
      ffmpeg -loglevel error -y -ss $ss -t 30 -i "$f" -ar 16000 -ac 1 -sample_fmt s16 "background_clips/music/m${i}_${ss}.wav"
    done
  done
fi

echo "== train"
# macOS spawns DataLoader workers, which cannot pickle train.py's lambdas; fork them instead.
sed -i '' 's/num_workers=n_cpus, prefetch_factor=16)/num_workers=n_cpus, prefetch_factor=16, multiprocessing_context="fork")/' openWakeWord/openwakeword/train.py
mkdir -p shim && cp "$HERE/generate_samples.py" shim/ && cp "$HERE/hey_device.yml" .
# torch 2.8: newer torchaudio needs torchcodec to load wavs. PYTORCH_JIT=0: the TTS model's scripted fused op has no MPS graph fuser on Apple Silicon.
PYTORCH_JIT=0 .venv/bin/python openWakeWord/openwakeword/train.py --training_config hey_device.yml \
  --generate_clips --augment_clips --train_model
cp out/hey_device.onnx "$HERE/../nonafi/models/hey_device.onnx"
echo "== wrote nonafi/models/hey_device.onnx"
