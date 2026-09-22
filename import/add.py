"""Add one rip to the library by naming the songs in it, in order. Splits, tags, and renumbers.

    python import/add.py "rip.mp3" "Blackbird" "Ob-La-Di, Ob-La-Da" "A Hard Day's Night"

This is the everyday path: rip a song or a few, then name them. Titles are matched against the
playlist (case-insensitive, ignoring "(2019 Mix)"-style suffixes), so the song has to be on the
playlist. An earlier copy of the same song in the library is replaced. Every album folder touched is
renumbered so its tracks follow playlist order.
"""
import re, shutil, sys
from pathlib import Path
from mutagen.id3 import ID3, TRCK
from common import OUT, duration
from build import rows, album_artist, album_rename, clean_title, safe, cut_points, artwork, tag, split


def norm(t):
    return re.sub(r'[^a-z0-9]+', ' ', clean_title(t).lower()).strip()


def find_row(title):
    q = norm(title)
    hits = [i for i, r in enumerate(rows) if norm(r['Name']) == q]
    if not hits:
        hits = [i for i, r in enumerate(rows) if q in norm(r['Name'])]
    if len(hits) != 1:
        sys.exit(f"{'no' if not hits else 'several'} playlist songs match {title!r}: {[rows[i]['Name'] for i in hits]}")
    return hits[0]


def playlist_pos(album):
    """Playlist index of each song title in an album (after collection renames), for ordering."""
    pos = {}
    for i, r in enumerate(rows):
        if album_rename.get(r['Album'], r['Album']) == album:
            pos.setdefault(norm(r['Name']), i)
    return pos


def renumber(folder, album):
    pos = playlist_pos(album)
    files = sorted(folder.glob('*.mp3'), key=lambda p: pos.get(norm(str(ID3(p).get('TIT2'))), 10**6))
    for n, p in enumerate(files, 1):
        title = str(ID3(p).get('TIT2'))
        dest = folder / f"{n:02d} - {safe(title)}.mp3"
        if dest != p:
            shutil.move(str(p), dest)
        id3 = ID3(dest); id3.delall('TRCK'); id3.add(TRCK(encoding=3, text=str(n))); id3.save(dest, v2_version=3)
    print(f"renumbered {len(files)} tracks in {folder.relative_to(OUT)}")


def main():
    if len(sys.argv) < 3 or not Path(sys.argv[1]).exists():
        sys.exit(__doc__)
    src = Path(sys.argv[1]); titles = sys.argv[2:]
    tracks = []
    for t in titles:
        r = rows[find_row(t)]
        album = album_rename.get(r['Album'], r['Album'])
        tracks.append({'title': clean_title(r['Name']), 'artist': r['Artist'], 'album': album,
                       'album_artist': album_artist.get(album, r['Artist']), 'time': int(r['Time']),
                       'track_number': r['Track Number'] if album == r['Album'] else 0, 'year': r['Year']})
    dur = duration(src)
    want = sum(t['time'] for t in tracks)
    if abs(dur - want) > 15:
        sys.exit(f"{src.name} is {dur:.0f}s but those songs add up to {want}s; check the titles or the rip")
    cuts = cut_points(src, tracks, dur) if len(tracks) > 1 else []
    bounds = [0.0] + cuts + [None]
    touched = set()
    for i, tr in enumerate(tracks):
        folder = OUT / safe(tr['album_artist']) / safe(tr['album']); folder.mkdir(parents=True, exist_ok=True)
        cover_f = folder / 'cover.jpg'
        cover = cover_f.read_bytes() if cover_f.exists() else artwork(tr['album_artist'], tr['album'])
        if cover and not cover_f.exists(): cover_f.write_bytes(cover)
        dest = folder / f"00 - {safe(tr['title'])}.mp3"
        for old in folder.glob(f"* - {safe(tr['title'])}.mp3"):   # replacing an earlier version of this song
            old.unlink()
        if len(tracks) == 1: shutil.copy2(src, dest)
        else: split(src, dest, bounds, i)
        tag(dest, tr, cover); touched.add((folder, tr['album']))
        print(f"wrote {tr['album_artist']} / {tr['title']}")
    for folder, album in touched:
        renumber(folder, album)


if __name__ == '__main__':
    main()
