"""Match unnamed rips to the playlist by duration. Writes plan.json; prints one line per rip.

Rips are taken in filename (timestamp) order and the playlist in play order. A rip may hold several
consecutive songs (the recorder missed a gap) or a song may have no rip (the recorder missed it).
Dynamic programming finds the cheapest alignment; the cost of a match is the difference between the
rip's length and the summed playlist lengths. Nothing is written to the library here.

    python import/align.py            # then read the output and fix anything odd in overrides.json
"""
import json
from common import RIPS, PLAN, DURATIONS, OVERRIDES, playlist_rows, duration

rows = playlist_rows()
T = [int(r['Time']) for r in rows]
skip = set(OVERRIDES.get('skip_files', []))
files = sorted(f for f in RIPS.glob('*.mp3') if f.name not in skip)
durs = json.load(open(DURATIONS)) if DURATIONS.exists() else {}
for f in files:
    if f.name not in durs:
        durs[f.name] = duration(f)
json.dump(durs, open(DURATIONS, 'w'), indent=1)
D = [durs[f.name] for f in files]

MAXK = 20          # most songs one rip may contain
TOL = 12.0         # seconds of slack per match, plus 3s per extra song
SKIP_FILE = 60.0   # cost of leaving a rip unmatched
SKIP_TRACK = 60.0  # cost of leaving a playlist song unripped
n, m = len(files), len(rows)
INF = float('inf')
best = [[INF] * (m + 1) for _ in range(n + 1)]; back = [[None] * (m + 1) for _ in range(n + 1)]
best[0][0] = 0
for i in range(n + 1):
    for j in range(m + 1):
        c = best[i][j]
        if c == INF: continue
        if i < n and c + SKIP_FILE < best[i + 1][j]: best[i + 1][j] = c + SKIP_FILE; back[i + 1][j] = ('skipf',)
        if j < m and c + SKIP_TRACK < best[i][j + 1]: best[i][j + 1] = c + SKIP_TRACK; back[i][j + 1] = ('skipt',)
        if i < n:
            s = 0
            for k in range(1, MAXK + 1):
                if j + k > m: break
                s += T[j + k - 1]
                diff = abs(D[i] - s)
                if diff > TOL + 3 * k: continue
                cost = c + diff
                if cost < best[i + 1][j + k]: best[i + 1][j + k] = cost; back[i + 1][j + k] = ('match', k, diff)

i, j = n, m; plan = []
while i or j:
    b = back[i][j]
    if b[0] == 'skipf': i -= 1; plan.append({'file': files[i].name, 'dur': D[i], 'tracks': [], 'note': 'NO PLAYLIST MATCH'})
    elif b[0] == 'skipt': j -= 1; plan.append({'file': None, 'tracks': [j], 'note': 'TRACK NOT RIPPED'})
    else:
        k = b[1]; i -= 1; j -= k
        plan.append({'file': files[i].name, 'dur': D[i], 'tracks': list(range(j, j + k)), 'diff': round(b[2], 1)})
plan.reverse()
for p in plan:
    p['track_info'] = [{'idx': t, 'title': rows[t]['Name'], 'artist': rows[t]['Artist'], 'album': rows[t]['Album'],
                        'album_artist': rows[t]['Artist'], 'time': T[t], 'track_number': rows[t]['Track Number'], 'year': rows[t]['Year']} for t in p['tracks']]
json.dump(plan, open(PLAN, 'w'), indent=1)

for p in plan:
    if p['file'] is None:
        print(f"{'':32}  --  MISSING: {rows[p['tracks'][0]]['Artist']} - {rows[p['tracks'][0]]['Name']} ({T[p['tracks'][0]]}s)"); continue
    tag = f"[{len(p['tracks'])} songs] " if len(p['tracks']) > 1 else ''
    desc = ' + '.join(f"{ti['artist']} - {ti['title']}" for ti in p['track_info']) or p['note']
    print(f"{p['file']}  {p['dur']:7.1f}s  diff={p.get('diff', '-'):>5}  {tag}{desc}")
print(f"\n{n} files, {m} tracks, matched {sum(1 for p in plan if p['file'] and p['tracks'])} files, "
      f"{sum(1 for p in plan if p['file'] and not p['tracks'])} unmatched files, {sum(1 for p in plan if p['file'] is None)} unripped tracks, "
      f"{sum(1 for p in plan if len(p['tracks']) > 1)} files with multiple songs")
