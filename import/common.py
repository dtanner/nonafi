"""Shared paths and playlist loading for the import scripts. See import/README.md.

Everything is overridable with environment variables so the same scripts work for another library:
  NONAFI_RIPS      folder of unnamed rips           default ~/Music/Audio Hijack
  NONAFI_LIBRARY   finished library to upload       default ~/Music/Mom
  NONAFI_IMPORT    working state (tsv, plan, caches) default ~/Music/Mom-import
  NONAFI_PLAYLIST  Music.app playlist export         default ~/Downloads/Mom.txt
overrides.json lives next to this file and is committed; it records library-specific decisions.
"""
import csv, json, os, subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
RIPS = Path(os.environ.get('NONAFI_RIPS', Path.home() / 'Music' / 'Audio Hijack'))
OUT = Path(os.environ.get('NONAFI_LIBRARY', Path.home() / 'Music' / 'Mom'))
STATE = Path(os.environ.get('NONAFI_IMPORT', Path.home() / 'Music' / 'Mom-import'))
PLAYLIST_EXPORT = Path(os.environ.get('NONAFI_PLAYLIST', Path.home() / 'Downloads' / 'Mom.txt'))
TSV = STATE / 'playlist.tsv'
PLAN = STATE / 'plan.json'
DURATIONS = STATE / 'durations.json'
ART_CACHE = STATE / 'artwork.json'
OVERRIDES_FILE = HERE / 'overrides.json'

STATE.mkdir(parents=True, exist_ok=True)
OVERRIDES = json.loads(OVERRIDES_FILE.read_text()) if OVERRIDES_FILE.exists() else {}


def refresh_playlist():
    """Convert the Music.app export (UTF-16, CR line ends) to playlist.tsv when it is newer."""
    if PLAYLIST_EXPORT.exists() and (not TSV.exists() or PLAYLIST_EXPORT.stat().st_mtime > TSV.stat().st_mtime):
        raw = PLAYLIST_EXPORT.read_bytes().decode('utf-16').replace('\r\n', '\n').replace('\r', '\n')
        TSV.write_text(raw, encoding='utf-8')
        print(f"converted {PLAYLIST_EXPORT} -> {TSV}")
    if not TSV.exists():
        raise SystemExit(f"no playlist: export it from Music.app to {PLAYLIST_EXPORT} (File > Library > Export Playlist)")


def playlist_rows():
    refresh_playlist()
    return list(csv.DictReader(open(TSV, encoding='utf-8-sig'), delimiter='\t'))


def duration(path):
    return float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)]))
