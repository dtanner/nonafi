# nonafi

Touchscreen jukebox for a Raspberry Pi. README.md covers the app and the Pi; `just` lists every command.

## Adding ripped music

When asked to identify, name, organize, or upload newly ripped songs, follow `import/README.md`. Short version:

1. Rips are unnamed mp3s in `~/Music/Audio Hijack`. The playlist export at `~/Downloads/Mom.txt` (Music.app, File > Library > Export Playlist) is the source of titles and durations; ask for a fresh export if songs were added.
2. `just import-align` to see how rip lengths match playlist songs. For a few files, compare durations yourself and listen with `afplay -t 15` if unsure. Never guess a title; the durations must add up.
3. `just import-add <rip> "<title>" ["<title 2>" ...]` per rip. It splits multi-song rips, tags, adds artwork, and renumbers the album.
4. `just import-check`, then `just upload ~/Music/Mom/"<Artist>"` for each artist touched. The Pi must be reachable (Tailscale `admin@nonafi`, see `.env`); if not, say so and stop after the library is built.
5. Library-wide decisions (merging albums into one folder, album artist, cover source, rips to ignore) go in `import/overrides.json`, not in the scripts.
