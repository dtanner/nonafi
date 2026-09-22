#!/bin/sh
# Rebuild the whole library from a complete set of rips plus the playlist export.
# Only for starting over: it realigns EVERY rip to the playlist, so all the rips must be present.
# To add a few songs, use add.py (just import-add) instead.
set -e
cd "$(dirname "$0")/.."
py=.venv/bin/python
rips="${NONAFI_RIPS:-$HOME/Music/Audio Hijack}"
state="${NONAFI_IMPORT:-$HOME/Music/Mom-import}"
n=$(ls "$rips"/*.mp3 2>/dev/null | wc -l | tr -d ' ')
[ "$n" -ge "${MIN_RIPS:-200}" ] || { echo "only $n rips in $rips; a full rebuild needs them all. Use add.py for a few songs (or MIN_RIPS=$n to force)."; exit 1; }
$py import/align.py > "$state/align.out"
tail -1 "$state/align.out"
grep -c MISSING "$state/align.out" | sed "s|\$| playlist songs not found in the rips (see $state/align.out)|"
$py import/build.py > "$state/build.out" 2> "$state/build.err"
tail -1 "$state/build.err"
grep -E '^\s+!' "$state/build.err" || true
