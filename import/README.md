# Importing rips into the library

How unnamed audio rips become the tagged, artist-and-album folders that `just upload` sends to the Pi. This is the runbook for "I ripped some more songs, help me name them and get them onto the jukebox."

## The setup

- **Source.** Songs are played from the **Mom** playlist in Music.app and recorded by Audio Hijack, which writes `App Recording YYYYMMDD HHMM.mp3` files to `~/Music/Audio Hijack`. The rips have no tags and no useful names. Audio Hijack splits on silence, so usually one file is one song, but sometimes two or more songs run together in one file, and sometimes a song is missed entirely.
- **Truth.** The playlist export from Music.app is the source of titles, artists, albums, track numbers, years, and durations. Export it with **File > Library > Export Playlist**, saving as `~/Downloads/Mom.txt` (it is UTF-16 tab-separated). The scripts convert it to `playlist.tsv` in the state folder automatically whenever the export is newer.
- **Library.** The finished library is `~/Music/Mom/<Album Artist>/<Album>/NN - Title.mp3` plus a `cover.jpg` per album. `just upload ~/Music/Mom/*` copies it to the Pi. The Pi shows one tile per top-level folder, so the album-artist folder name is what the user sees.
- **State.** `~/Music/Mom-import` holds the converted playlist, `plan.json`, and two caches (`durations.json` for ffprobe results, `artwork.json` for iTunes cover URLs). It is not in git. `stray/` in there holds earlier bad or duplicate builds kept for reference.
- **Decisions.** `import/overrides.json` in this repo records library-specific choices and is committed:
  - `album_rename` collapses many source albums into one folder. Every Beatles album becomes "Beatles Collection", every Chieftains album "Chieftains Collection", so the Pi gets one tidy list instead of a dozen two-song albums.
  - `album_artist` sets the folder for a collection, since the most-common-artist rule cannot see a renamed album.
  - `artwork_from` says which real album's cover to use for a collection.
  - `skip_files` lists rips to ignore (truncated duplicates from a bad recording session).

Tools needed on the Mac: `ffmpeg` and `ffprobe` from Homebrew, and the repo's `.venv` with the `import` extra (`.venv/bin/pip install -e '.[import]'`; the `just import-*` recipes do this for you).

## Everyday: a few new rips

1. Rip the songs. They land in `~/Music/Audio Hijack`.
2. If the songs were added to the playlist since the last export, export the playlist again to `~/Downloads/Mom.txt`.
3. Work out which song is in which file. `just import-align` lists every rip with its length and the best playlist match by duration. For a handful of files it is often quicker to just look at the lengths and say what was ripped. Listen if in doubt: `afplay -t 15 "~/Music/Audio Hijack/App Recording 20260921 1829.mp3"`.
4. File each rip, naming its songs in order:

   ```bash
   just import-add ~/Music/"Audio Hijack"/"App Recording 20260921 1829.mp3" "We Can Work It Out" "With a Little Help From My Friends" "Drive My Car"
   ```

   The title lookup is case-insensitive and ignores catalog suffixes like "(2022 Remaster)", but the song must be on the playlist. The script checks the rip's length against the songs' total and refuses if they are more than 15 seconds apart, which catches a wrong title or a truncated rip. Multi-song rips are split at the silence nearest each boundary without re-encoding. An older copy of the same song in the library is replaced, and the album folder is renumbered to playlist order.
5. `just import-check` shows songs and covers per artist and which playlist songs are still unripped.
6. Upload the artists that changed. Only run this when the Pi is on: `just upload ~/Music/Mom/"The Beatles"`. Then `just list` to confirm.
7. Clear or archive the rips from `~/Music/Audio Hijack` once they are in the library, so the next batch is easy to see.

## Starting over: aligning a whole session

When hundreds of rips were made in one go, the alignment script does the naming. It walks the rips in timestamp order and the playlist in play order and finds the cheapest way to line them up, where a rip may cover one to twenty consecutive songs and either side may be skipped at a fixed cost. The only signal is duration, which is enough because the playlist was played straight through.

```bash
just import-align          # prints one line per rip; MISSING lines are songs no rip matched
just import-build          # splits, tags, fetches artwork, writes the library
```

Or `import/rebuild.sh`, which runs both, saves the outputs to the state folder, and refuses to run with fewer than 200 rips (override with `MIN_RIPS=`), since a partial set will misalign everything.

Read the align output before building. Things to look for:

- A run of MISSING lines followed by a rip with a large `diff`: the recorder dropped songs and the alignment drifted. Usually fixed by re-ripping the missing songs and using `import-add`.
- A rip with `[N songs]` where N looks too large: two songs that happened to sum to a longer one. Check with `afplay`.
- `NO PLAYLIST MATCH`: a rip that is not on the playlist, or a duplicate. Add it to `skip_files` if it should be ignored.

`import-build` is idempotent. A song is skipped when the library file is newer than its rip, so re-running after fixing one rip only rewrites that rip's songs. Warnings on stderr starting with `!` mean a cut fell back to the timestamp because no silence was found nearby, or no artwork was found; both are worth a listen or a look.

## Tagging and naming rules

- Titles lose "(2019 Mix)", "(2022 Remaster)", and similar; "(Live - 2022 Remaster)" becomes "(Live)".
- Album artist is the most common artist on the album in the playlist, so a duet track still files under the main artist. Overrides win.
- Track numbers come from the playlist, except in a renamed collection, where they are assigned in playlist order.
- `/`, `:`, and `\` in names become `-`. Trailing dots are dropped.
- Tags are ID3v2.3 with title, artist, album artist, album, track, year, and embedded cover, written fresh so nothing from the rip leaks through.
- Artwork is the 600x600 cover from the iTunes Search API for the album, cached in `artwork.json`. To swap a cover, delete its entry there and the `cover.jpg`, or just drop your own `cover.jpg` in the folder; nothing overwrites an existing one via `import-add`.

## Other libraries

Every path is an environment variable, so the same scripts serve a second person or a test run:

| Variable | Default | What |
|---|---|---|
| `NONAFI_RIPS` | `~/Music/Audio Hijack` | unnamed rips |
| `NONAFI_PLAYLIST` | `~/Downloads/Mom.txt` | Music.app playlist export |
| `NONAFI_LIBRARY` | `~/Music/Mom` | finished library |
| `NONAFI_IMPORT` | `~/Music/Mom-import` | state and caches |

Put them in `.env` and `just` loads them. Rips that are not from a Music.app playlist need a `playlist.tsv` in the state folder with at least the columns `Name`, `Artist`, `Album`, `Time` (seconds), `Track Number`, and `Year`; a hand-written one works.

## Files

- `common.py` paths, playlist conversion, ffprobe duration.
- `align.py` duration alignment of rips to playlist, writes `plan.json`.
- `build.py` builds the library from `plan.json`; also holds the shared split, tag, artwork, and title-cleaning code.
- `add.py` one rip, songs named on the command line.
- `check.py` library report and unripped list.
- `rebuild.sh` align plus build for a complete session.
- `overrides.json` the decisions above.
