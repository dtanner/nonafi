"""Build the library from plan.json: split multi-song rips at silences, tag, add artwork. Idempotent.

    python import/build.py            # writes into NONAFI_LIBRARY (default ~/Music/Mom)

A song is skipped when its file in the library is newer than the rip, so re-running only does new work.
Progress goes to stdout, warnings ("!" lines) to stderr.
"""
import json, re, shutil, subprocess, sys
from collections import Counter
import requests
from mutagen.id3 import ID3, TIT2, TPE1, TPE2, TALB, TRCK, TDRC, APIC, ID3NoHeaderError
from common import RIPS, OUT, PLAN, ART_CACHE, OVERRIDES, playlist_rows

rows = playlist_rows()
art_cache = json.loads(ART_CACHE.read_text()) if ART_CACHE.exists() else {}

# Album artist = the most common artist on that album in the playlist, unless overridden.
album_artist = {alb: Counter(r['Artist'] for r in rows if r['Album'] == alb).most_common(1)[0][0] for alb in {r['Album'] for r in rows}}
album_artist.update(OVERRIDES.get('album_artist', {}))
album_rename = OVERRIDES.get('album_rename', {})
art_source = OVERRIDES.get('artwork_from', {})


def clean_title(t):
    """Drop streaming-catalog suffixes like "(2019 Mix)" or "(2022 Remaster)"; keep "(Live)"."""
    t = re.sub(r'\s*[\(\[](\d{4} (Remaster|Mix)|"Greatest Hits" Version|Original Version|Live - \d{4} Remaster)[\)\]]',
               lambda m: ' (Live)' if m.group(1).startswith('Live') else '', t)
    return t.strip()


def safe(s):
    return re.sub(r'[/:\\]', '-', s).strip().rstrip('.')


def silences(path, noise='-45dB', d='0.3'):
    out = subprocess.run(['ffmpeg', '-nostats', '-i', str(path), '-af', f'silencedetect=noise={noise}:d={d}', '-f', 'null', '-'],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r'silence_start: ([\d.]+)', out)]
    ends = [float(x) for x in re.findall(r'silence_end: ([\d.]+)', out)]
    return [(s + e) / 2 for s, e in zip(starts, ends)]


def cut_points(path, tracks, dur):
    """One cut per song boundary: the silence nearest the cumulative playlist time, else the time itself."""
    sil = silences(path); loose = None; cuts = []; t = 0.0
    scale = dur / sum(tr['time'] for tr in tracks)
    for tr in tracks[:-1]:
        t += tr['time'] * scale
        near = min(sil, key=lambda s: abs(s - t), default=None)
        if near is not None and abs(near - t) <= 20: cuts.append(near); continue
        if loose is None: loose = silences(path, '-32dB', '0.15')
        near = min(loose, key=lambda s: abs(s - t), default=None)
        if near is not None and abs(near - t) <= 20:
            cuts.append(near); print(f"   ~ loose silence at {near:.0f}s (wanted {t:.0f}s) in {path.name}", file=sys.stderr)
        else:
            cuts.append(t); print(f"   ! no silence near {t:.0f}s in {path.name}, cutting on time", file=sys.stderr)
    return cuts


def artwork(artist, album):
    """600x600 cover from the iTunes Search API, cached by artist|album in artwork.json."""
    artist, album = art_source.get(album, (artist, album))
    key = f'{artist}|{album}'
    if key not in art_cache:
        r = requests.get('https://itunes.apple.com/search', params={'term': f'{artist} {album}', 'entity': 'album', 'limit': 10}).json().get('results', [])
        hit = next((x for x in r if x['collectionName'].lower()[:12] == album.lower()[:12]), None) or (r[0] if r else None)
        art_cache[key] = hit['artworkUrl100'].replace('100x100bb', '600x600bb') if hit else None
        ART_CACHE.write_text(json.dumps(art_cache, indent=1))
    url = art_cache[key]
    return requests.get(url).content if url else None


def tag(path, tr, cover):
    """Replace all ID3 tags with title, artist, album artist, album, track, year, and cover (ID3v2.3)."""
    try: ID3(path).delete(path)
    except ID3NoHeaderError: pass
    id3 = ID3()
    id3.add(TIT2(encoding=3, text=tr['title'])); id3.add(TPE1(encoding=3, text=tr['artist']))
    id3.add(TPE2(encoding=3, text=tr['album_artist'])); id3.add(TALB(encoding=3, text=tr['album']))
    if tr['track_number']: id3.add(TRCK(encoding=3, text=str(tr['track_number'])))
    if tr['year']: id3.add(TDRC(encoding=3, text=str(tr['year'])))
    if cover: id3.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=cover))
    id3.save(path, v2_version=3)


def split(src, dest, bounds, i):
    """Copy the i-th segment of src (between bounds[i] and bounds[i+1]) to dest without re-encoding."""
    args = ['ffmpeg', '-v', 'error', '-y', '-i', str(src), '-ss', str(bounds[i])] + (['-to', str(bounds[i + 1])] if bounds[i + 1] else []) + ['-c', 'copy', str(dest)]
    subprocess.run(args, check=True)


if __name__ == '__main__':
    plan = json.load(open(PLAN))
    covers = {}; made = 0; seq = Counter()
    for p in plan:
        if not p['file'] or not p['tracks']: continue
        src = RIPS / p['file']; tracks = p['track_info']
        for tr in tracks:
            tr['title'] = clean_title(tr['title'])
            renamed = tr['album'] != album_rename.get(tr['album'], tr['album'])
            tr['album'] = album_rename.get(tr['album'], tr['album']); tr['album_artist'] = album_artist.get(tr['album'], tr['artist'])
            seq[tr['album']] += 1
            if renamed or not tr['track_number']: tr['track_number'] = seq[tr['album']]
        cuts = cut_points(src, tracks, p['dur']) if len(tracks) > 1 else []
        bounds = [0.0] + cuts + [None]
        for i, tr in enumerate(tracks):
            folder = OUT / safe(tr['album_artist']) / safe(tr['album']); folder.mkdir(parents=True, exist_ok=True)
            dest = folder / f"{int(tr['track_number']):02d} - {safe(tr['title'])}.mp3"
            if tr['album'] not in covers:
                covers[tr['album']] = artwork(tr['album_artist'], tr['album'])
                if covers[tr['album']]: (folder / 'cover.jpg').write_bytes(covers[tr['album']])
                else: print(f"   ! no artwork for {tr['album_artist']} - {tr['album']}", file=sys.stderr)
            if dest.exists() and dest.stat().st_mtime > src.stat().st_mtime: continue
            if len(tracks) == 1: shutil.copy2(src, dest)
            else: split(src, dest, bounds, i)
            tag(dest, tr, covers[tr['album']]); made += 1
            print(dest.relative_to(OUT))
    print(f"\nwrote {made} tracks to {OUT}", file=sys.stderr)
