# nonafi: touchscreen jukebox for a Raspberry Pi.
# Run `just` to list commands.

set positional-arguments
set dotenv-load

# SSH target for the Pi. Put `PI_HOST=user@host` in a `.env` file (git-ignored) or export it.
pi_host := env_var_or_default("PI_HOST", "pi@raspberrypi.local")
pi_path := "~/nonafi"

default:
    @just --list

# Copy the code to the Pi, set up the venv, install/restart the service and kiosk.
deploy: sync
    ssh {{pi_host}} 'cd {{pi_path}} && \
      [ -x .venv/bin/python ] || python3 -m venv --system-site-packages .venv && \
      .venv/bin/pip install -q -e '.[voice]' && .venv/bin/pip install -q --no-deps openwakeword && \
      mkdir -p ~/.config/systemd/user ~/.config/labwc ~/Music && \
      cp pi/nonafi.service pi/nonafi-voice.service ~/.config/systemd/user/ && \
      systemctl --user daemon-reload && \
      systemctl --user enable --now nonafi.service nonafi-voice.service && \
      systemctl --user restart nonafi.service nonafi-voice.service && \
      bash pi/setup-desktop.sh && \
      grep -q nonafi/pi/kiosk.sh ~/.config/labwc/autostart 2>/dev/null || \
        echo "/usr/bin/lwrespawn $HOME/nonafi/pi/kiosk.sh &" >> ~/.config/labwc/autostart'
    just restart-kiosk

# rsync the repo to the Pi (no restart).
sync:
    rsync -az --delete --exclude .git --exclude .venv --exclude __pycache__ --exclude music ./ {{pi_host}}:{{pi_path}}/

# Restart just the server (after code changes).
restart:
    ssh {{pi_host}} 'systemctl --user restart nonafi.service && sleep 1 && systemctl --user is-active nonafi.service'

# Restart the voice service.
restart-voice:
    ssh {{pi_host}} 'systemctl --user restart nonafi-voice.service && sleep 1 && systemctl --user is-active nonafi-voice.service'

# Tail the voice service log (wake words, transcripts, commands).
voice-logs:
    ssh {{pi_host}} 'journalctl --user -u nonafi-voice.service -n 50 -f'

# Act on a phrase as if it had been spoken, e.g. `just say "play the beatles"`. Prints the command it chose.
say text:
    ssh {{pi_host}} 'cd ~/nonafi && .venv/bin/python -c "from nonafi import voice; u=\"http://127.0.0.1:8080\"; c=voice.interpret(\"{{text}}\", voice.artists(u)); print(c); c and voice.post(u, c)"'

# Relaunch the full-screen browser on the Pi's touchscreen.
restart-kiosk:
    ssh {{pi_host}} 'pkill -f "kiosk\\.s[h]"; pkill -f "nonafi-kios[k]"; true'
    ssh {{pi_host}} 'WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/$(id -u) setsid -f /usr/bin/lwrespawn {{pi_path}}/pi/kiosk.sh > /dev/null 2>&1 < /dev/null; echo kiosk started'

# Upload music: `just upload ~/Music/Mom/*` copies each artist folder into the Pi's Music folder.
upload +folders:
    rsync -avh --progress "$@" {{pi_host}}:~/Music/
    ssh {{pi_host}} 'curl -s -X POST http://127.0.0.1:8080/api/rescan; echo'

# Delete an artist folder from the Pi: `just remove "The Beatles"`.
remove folder:
    ssh {{pi_host}} "cd ~/Music && rm -rv '{{folder}}'"
    ssh {{pi_host}} 'curl -s -X POST http://127.0.0.1:8080/api/rescan; echo'

# Leave the kiosk for the Pi desktop (same as holding the left panel on the touchscreen).
setup-mode:
    ssh {{pi_host}} 'curl -s -X POST http://127.0.0.1:8080/api/setup; echo'

# Bring the kiosk back from the desktop (same as tapping the Jukebox icon in the top bar).
resume-kiosk:
    ssh {{pi_host}} 'rm -f ~/.config/nonafi/setup; echo resumed'

# Show audio output devices (sinks) on the Pi; the starred one is in use.
sinks:
    ssh {{pi_host}} 'wpctl status | sed -n "/Sinks:/,/Sources:/p"'

# Make a sink the default output, e.g. `just use-sink 58` (id from `just sinks`). Persists across reboots.
use-sink id:
    ssh {{pi_host}} 'wpctl set-default {{id}} && wpctl set-volume @DEFAULT_AUDIO_SINK@ 1.0 && wpctl set-mute @DEFAULT_AUDIO_SINK@ 0 && wpctl get-volume @DEFAULT_AUDIO_SINK@'

# List what music is on the Pi.
list:
    ssh {{pi_host}} 'find ~/Music -mindepth 1 -maxdepth 2 | sort'

# Tail the server log.
logs:
    ssh {{pi_host}} 'journalctl --user -u nonafi.service -n 50 -f'

# Take a screenshot of the Pi's screen and save it to screenshots/ (git-ignored).
screenshot:
    mkdir -p screenshots
    ssh {{pi_host}} 'WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/$(id -u) grim /tmp/nonafi.png' && scp -q {{pi_host}}:/tmp/nonafi.png screenshots/$(date +%Y%m%d-%H%M%S).png && ls -t screenshots | head -1

# Open a shell on the Pi.
ssh:
    ssh {{pi_host}}

# Run the server locally on this Mac against ./music for development.
dev:
    python3 -m venv .venv 2>/dev/null; .venv/bin/pip install -q -e . && NONAFI_DEBUG=1 .venv/bin/python -m nonafi --music ./music --port 8080

# --- Importing rips (see import/README.md) ---

# Name and file one rip by listing its songs in order: `just import-add ~/Music/"Audio Hijack"/"App Recording 20260921 1829.mp3" "Blackbird" "Yesterday"`.
import-add rip +titles:
    .venv/bin/pip install -q -e '.[import]' 2>/dev/null; .venv/bin/python import/add.py "$@"

# Show how the unnamed rips line up with the playlist, without writing anything.
import-align:
    .venv/bin/pip install -q -e '.[import]' 2>/dev/null; .venv/bin/python import/align.py

# Write the aligned rips into the library (split, tag, artwork). Safe to re-run.
import-build:
    .venv/bin/python import/build.py

# Library health: songs and covers per artist, untagged files, and which playlist songs are still unripped.
import-check:
    .venv/bin/pip install -q -e '.[import]' 2>/dev/null; .venv/bin/python import/check.py
