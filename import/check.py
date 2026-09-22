"""Report on the finished library: songs per artist, missing covers, bad tags, playlist songs not yet in it.

    python import/check.py
"""
import re
from mutagen.id3 import ID3
from common import OUT, playlist_rows, OVERRIDES
from build import clean_title

norm = lambda t: re.sub(r'[^a-z0-9]+', ' ', clean_title(t).lower()).strip()
rows = playlist_rows()
have = set()
for artist in sorted(p for p in OUT.iterdir() if p.is_dir()):
    songs = sorted(artist.rglob('*.mp3'))
    covers = list(artist.rglob('cover.jpg'))
    bad = []
    for s in songs:
        try:
            id3 = ID3(s)
            if not id3.get('TIT2') or not id3.get('TPE1'): bad.append(s.name)
            have.add(norm(str(id3.get('TIT2'))))
        except Exception as e:
            bad.append(f"{s.name} ({e})")
    print(f"{artist.name:40} {len(songs):3} songs  {len(covers)} covers" + (f"  ! untagged: {bad}" if bad else ''))
missing = [r for r in rows if norm(r['Name']) not in have]
print(f"\n{len(rows)} playlist songs, {len(rows) - len(missing)} in the library, {len(missing)} not yet ripped:")
for r in missing: print(f"  {r['Artist']} - {r['Name']} ({int(r['Time'])//60}:{int(r['Time'])%60:02d})")
