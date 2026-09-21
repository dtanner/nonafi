# nonafi

A one-screen jukebox for a Raspberry Pi 5 with a 7" touchscreen, built for someone who should never have to learn an interface.

Everything is on a single screen. The right side shows pages of big album covers with up/down arrows when there is more than one page. Tap a cover and it plays from the first song. The left side shows what is playing with a big Play/Pause, Next, and volume minus/plus. The playing album gets a gold border. Songs play through in order and stop at the end of the album. Tapping the album that is already playing does nothing, so a stray tap never restarts it.

Runs entirely as the normal desktop user on the Pi. No sudo needed.

## How it works

- `nonafi/` is a small Python web server. It scans `~/Music` on the Pi, reads tags and cover art with mutagen, and serves a single-page UI plus the audio files.
- `nonafi/static/` is the UI, one page sized for 1024x600.
- `pi/nonafi.service` runs the server as a systemd user service.
- `pi/kiosk.sh` launches Chromium full-screen on the touchscreen, started from `~/.config/labwc/autostart`.
- Volume buttons set the real system volume through PipeWire (`wpctl`).

## Adding music

Put each album in its own folder. Tags are used when present, otherwise the folder name becomes the album title. Any mp3, m4a, flac, ogg, opus, or wav works in Chromium.

Cover art is taken from the embedded tag, then from a `cover.jpg` / `folder.jpg` / any image in the folder, and finally a generated placeholder with the album name.

```bash
just upload ~/Music/"Some Album"          # copies the folder into ~/Music on the Pi
just upload ~/Music/"Album A" ~/Music/"Album B"
just list                                 # what is on the Pi
just remove "Some Album"                  # delete an album from the Pi
```

The UI picks up new music within about 15 seconds. `just upload` also triggers a rescan immediately.

## Deploying and operating

```bash
just deploy          # sync code, install deps, (re)start server and kiosk
just restart         # restart only the server
just restart-kiosk   # relaunch the full-screen browser
just logs            # server log
just screenshot      # grab the Pi's screen into captures/
just sinks           # list audio outputs
just use-sink 58     # switch output, e.g. to USB speakers
just dev             # run the server on the Mac against ./music
```

The Pi host defaults to `admin@192.168.1.70`; override with `PI_HOST=admin@piaudio.local just deploy`.

## Switching to USB speakers

Plug them in, run `just sinks`, and `just use-sink <id>` on the new one. If the speakers show up as a device but not a sink, the USB device may need its profile enabled:

```bash
ssh admin@192.168.1.70 'wpctl status'            # find the device id under Devices
ssh admin@192.168.1.70 'wpctl set-profile <device-id> 1'
```
