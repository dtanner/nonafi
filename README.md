# nonafi

A one-screen jukebox for a Raspberry Pi 5 with a 7" touchscreen, built for someone who should never have to learn an interface.

Everything is on a single screen. The right side shows pages of big artist tiles with up/down arrows when there is more than one page. Tap an artist and it plays all of their songs from the first one. The left side shows what is playing with a big Play/Pause, Previous, and Next. Volume is controlled on the speakers. The playing artist gets a gold border. Songs play through in order and stop at the end of the artist's list. Tapping the artist that is already playing does nothing, so a stray tap never restarts it. Tapping the cover or artist name on the left shows that artist's songs on the right, seven to a page with the same up/down arrows. Tap a song to play it, or the big Artists button to go back. The list also closes by itself after fifteen seconds without a touch.

There are no albums in the interface. One artist, one tile, one list of songs.

After ten minutes without a touch the screen dims to about 30% brightness. The next touch only wakes it, so a wake-up tap can never start an artist.

Runs entirely as the normal desktop user on the Pi. No sudo needed.

## Quick reference

Everything is driven from this repo on the Mac with [just](https://github.com/casey/just). Run `just` alone to list the commands.

```bash
just deploy          # sync code to the Pi, install deps, (re)start server, voice, and kiosk
just restart         # restart only the server
just restart-voice   # restart only voice control
just restart-kiosk   # relaunch the full-screen browser
just logs            # server log (Ctrl-C to stop)
just voice-logs      # wake-word scores, transcripts, chosen commands
just say "play the beatles"   # act on a phrase without speaking it

just upload ~/Music/Mom/*     # copy artist folders to the Pi
just list                     # what music is on the Pi
just remove "The Beatles"     # delete an artist from the Pi
just import-add rip.mp3 "Title" ["Title 2"...]   # name a rip and file it into ~/Music/Mom
just import-check             # library report and unripped playlist songs

just sinks           # list audio outputs; the starred one is in use
just use-sink 58     # switch output, e.g. to USB speakers
just setup-mode      # leave the kiosk for the Pi desktop (Wi-Fi setup)
just resume-kiosk    # come back to the jukebox
just screenshot      # grab the Pi's screen into screenshots/
just ssh             # shell on the Pi
just dev             # run the server on the Mac against ./music
```

## Setting up from scratch

Do these in order. Steps 1 and 2 are on the Mac; the rest happen through `just`.

1. **Mac tools.** `brew install just`. Clone this repo.
2. **Point at the Pi.** Copy `.env.example` to `.env` and set `PI_HOST` to the Pi's SSH target, for example `admin@nonafi` or `admin@192.168.1.70`. The file is git-ignored. Every `just` command uses it. You need passwordless SSH to the Pi: either `ssh-copy-id` a key, or Tailscale SSH (see [Remote access](#remote-access)).
3. **The Pi.** Raspberry Pi OS with desktop, Bookworm or later, set to auto-login to the desktop (the current Pi runs Debian 13 "trixie"). The desktop session must be labwc, which is the default on a Pi 5; `just deploy` writes to `~/.config/labwc/autostart`. Everything else it needs is in the standard image: `chromium`, `python3`, `rsync`, `curl`, `grim`, `wpctl`, `arecord`, `squeekboard`. Enable SSH in raspi-config or the imager.
4. **Deploy.** `just deploy`. This rsyncs the repo to `~/nonafi` on the Pi, creates `.venv` there, installs the Python deps, installs and starts the two systemd user services, runs `pi/setup-desktop.sh` (on-screen keyboard and the Jukebox launcher), adds the kiosk to labwc's autostart, and launches the kiosk. The first run downloads the wake-word and whisper models, so the Pi needs internet and the voice service takes a minute to come up.
5. **Music.** `just upload ~/Music/Mom/*`. See [Adding music](#adding-music) for the folder layout.
6. **Speakers.** Plug them in, `just sinks`, then `just use-sink <id>` on the new one. See [Audio output](#audio-output) if they do not show up as a sink.
7. **Microphone.** Plug in any USB mic. The voice service picks the first USB capture card automatically. `just restart-voice` after plugging one in, then `just voice-logs` should show a `ready:` line naming it.
8. **Reboot the Pi** once to confirm it all comes back on its own: server, voice, and kiosk.

Repeating step 4 is also how you push any code change. It is safe to run again at any time.

## Adding music

Put each artist in their own folder under `~/Music` on the Pi. The folder name is what shows on the tile. Inside, any layout works: songs straight in the folder, or one subfolder per album. Songs are ordered by subfolder, then album tag, then disc and track number, so albums stay together and in order. Any mp3, m4a, flac, ogg, opus, or wav works in Chromium.

```
Music/
  The Beatles/
    cover.jpg
    01 - Help!.mp3
    ...
  Jim Croce/
    I Got a Name/
      cover.jpg
      01 - I Got a Name.mp3
    Life & Times/
      ...
```

Files dropped straight into `~/Music` with no folder are grouped by their album-artist (or artist) tag instead.

The artist's picture is the first of: an image in the artist folder, preferring names like `cover`, `folder`, `front`, `artist`, or `artwork` (jpg, png, or webp); then the same in its subfolders, so an album's `cover.jpg` is used when there is nothing above it; then the first embedded picture in the songs; and finally a generated placeholder with the artist's name. To pick the picture for an artist with several albums, drop a `cover.jpg` in the artist folder.

```bash
just upload ~/Music/Mom/*                 # copies each artist folder into ~/Music on the Pi
just upload ~/Music/Mom/"The Beatles"
just list                                 # what is on the Pi
just remove "The Beatles"                 # delete an artist from the Pi
```

The UI picks up new music within about 15 seconds. `just upload` and `just remove` also trigger a rescan immediately.

### From rips to a library

The library in `~/Music/Mom` is built from unnamed Audio Hijack recordings plus a Music.app playlist export. The scripts in `import/` match rips to the playlist by duration, split files that hold several songs, tag them, fetch cover art, and write the artist/album folders above. The everyday case is one command per rip:

```bash
just import-add ~/Music/"Audio Hijack"/"App Recording 20260921 1829.mp3" "We Can Work It Out" "Drive My Car"
just import-check                         # what is in the library and what is still unripped
just upload ~/Music/Mom/"The Beatles"     # when the Pi is on
```

[import/README.md](import/README.md) is the full runbook, including how to align a whole recording session at once.

## Audio output

The Pi output is set to full volume and unmuted every time the server starts, so the speakers' own volume knob has its whole range. There is no volume control in the app.

To switch outputs, plug the speakers in, run `just sinks`, and `just use-sink <id>` on the new one. This persists across reboots. If the speakers show up as a device but not a sink, the USB device may need its profile enabled:

```bash
just ssh
wpctl status                       # find the device id under Devices
wpctl set-profile <device-id> 1
```

## Voice control

Say **"Hey Jarvis"**, wait for the chime, then:

- "play music" — resumes, or picks a random artist if nothing is up
- "play [artist name]" — fuzzy-matched against the artist names, so close is good enough ("beatles" finds The Beatles). "put on" and "start" work like "play".
- "pause" / "stop" / "quiet"
- "next" / "skip"
- "resume" / "continue"

Everything runs on the Pi. `nonafi/voice.py` listens with [openWakeWord](https://github.com/dscripka/openWakeWord), records until you stop talking, transcribes with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (`base.en`, about two seconds on a Pi 5), and posts the command to the server, which relays it to the page over server-sent events. The page chimes and shows a banner with what it heard. Music ducks to 15% while it listens so the mic can hear you over it.

```bash
just voice-logs                 # wake-word scores, transcripts, chosen commands
just restart-voice
just say "play the beatles"     # act on a phrase without speaking it
```

### Tuning

Settings are environment variables. To change one, add a line like `Environment=NONAFI_WAKE_THRESHOLD=0.6` under `[Service]` in `pi/nonafi-voice.service`, then `just deploy`.

- `NONAFI_WAKE_THRESHOLD` — default 0.5. Raise it if it false-triggers, lower it if it misses you. `just voice-logs` shows the score on each trigger.
- `NONAFI_WHISPER` — default `base.en`. `small.en` is more accurate and slower.
- `NONAFI_MIC` — an ALSA device such as `plughw:CARD=Device`. Defaults to the first USB capture card from `arecord -l`.
- `NONAFI_WAKEWORD` — default `hey_jarvis`, a stock openWakeWord model. "Hey Nona" needs a custom model trained with openWakeWord's training notebook; copy the resulting `.onnx` to the Pi and set this to its full path.

## Remote access

The Pi runs [Tailscale](https://tailscale.com) so it can be managed from anywhere it has internet, not just the local network. Its tailnet name is `nonafi`. Set `PI_HOST` in `.env` to `admin@nonafi` and every `just` recipe works the same from anywhere. Tailscale SSH is on (`tailscale up --ssh`), so login is authorized by the tailnet rather than a key on the Pi. In the Tailscale admin console, disable key expiry for the machine so it never logs itself out.

### Joining a new Wi-Fi network by touch

Hold a blank part of the left panel (not a button or the cover) for six seconds. A dialog asks to open the Pi desktop; tap **Open desktop** and the jukebox closes. In the desktop's top bar, tap the Wi-Fi icon to pick a network, and the on-screen keyboard (the keyboard icon at the far right of the bar) pops up for the password. Tap the **Jukebox** icon, in the top bar or on the desktop, to come back. If nobody does, the jukebox returns on its own after twenty minutes.

The same two steps are available remotely as `just setup-mode` and `just resume-kiosk`.

If you know the network in advance, add it over SSH instead:

```bash
ssh $PI_HOST 'sudo nmcli device wifi connect "NetworkName" password "Password"'
```

NetworkManager keeps every saved network and connects to whichever is present. Adding a phone hotspot too gives you a way back in if the new network does not work out.

## Troubleshooting

- **Blank or error page on the screen.** The server is down. `just logs` shows why; `just restart` restarts it. The kiosk waits up to a minute for the server before loading, so after a reboot give it that long.
- **Screen shows the Pi desktop instead of the jukebox.** Setup mode is on. `just resume-kiosk`, or tap the Jukebox icon. If that does not help, `just restart-kiosk`.
- **No sound.** `just sinks` and check the starred sink is the speakers. `just use-sink <id>` also resets volume to full and unmutes.
- **Voice does nothing.** `just voice-logs`. No `ready:` line means the service failed to start, usually a missing mic (`arecord -l` on the Pi) or a model download that needs internet. Scores below the threshold on every "Hey Jarvis" mean lower `NONAFI_WAKE_THRESHOLD`.
- **Music missing after upload.** `just list` to confirm the folder landed in `~/Music`, and check the folder holds audio files, not a nested extra folder with a different name than you expect. Tiles refresh within 15 seconds.
- **Check everything at once.** `just ssh`, then `systemctl --user status nonafi nonafi-voice` and `pgrep -af chromium`.

## How it works

- `nonafi/` is a small Python web server (standard library only, plus mutagen for tags and Pillow for covers). It scans `~/Music` on the Pi, groups songs by artist, and serves a single-page UI plus the audio files.
- `nonafi/static/` is the UI, one page sized for 1024x600.
- `nonafi/voice.py` is the voice service, a separate process.
- `pi/nonafi.service` and `pi/nonafi-voice.service` are the systemd user units. `just deploy` copies them to `~/.config/systemd/user/`.
- `pi/kiosk.sh` launches Chromium full-screen on the touchscreen, started from `~/.config/labwc/autostart` via `lwrespawn` so it comes back if it dies.
- `import/` turns Audio Hijack rips into the tagged library on the Mac. See [import/README.md](import/README.md).
- `pi/setup-desktop.sh` sets up the touch Wi-Fi flow: it starts the on-screen keyboard with the session and installs the Jukebox launcher. Setup mode works by the page posting to `/api/setup`; the server writes `~/.config/nonafi/setup` and closes Chromium, `kiosk.sh` waits while that file exists, and the Jukebox launcher deletes it.
- The Python venv on the Pi is created with `--system-site-packages`; `openwakeword` is installed with `--no-deps` because it pins a `tflite-runtime` that has no wheels for the Pi's Python. See the comment in `pyproject.toml`.
- The server listens on localhost only. The kiosk is the only client, so nothing is exposed to the network. To open the page from another device, add `Environment=NONAFI_HOST=0.0.0.0` under `[Service]` in `pi/nonafi.service` and `just deploy`.
- Chromium's remote debugging port stays off unless `~/.config/nonafi/debug` exists on the Pi. It is handy for driving the UI from a script while developing.

## Developing on the Mac

`just dev` runs the server locally on port 8080 against `./music`, which is git-ignored, so drop a few artist folders in there first. Then open http://127.0.0.1:8080/ in a browser. Voice control is Pi-only, but `just say` exercises the command path against the Pi.

`captures/` holds reference screenshots that are committed; `just screenshot` writes to `screenshots/`, which is not.
