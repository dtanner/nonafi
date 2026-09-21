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
      .venv/bin/pip install -q -e . && \
      mkdir -p ~/.config/systemd/user ~/.config/labwc ~/Music && \
      cp pi/nonafi.service ~/.config/systemd/user/nonafi.service && \
      systemctl --user daemon-reload && \
      systemctl --user enable --now nonafi.service && \
      systemctl --user restart nonafi.service && \
      grep -q nonafi/pi/kiosk.sh ~/.config/labwc/autostart 2>/dev/null || \
        echo "/usr/bin/lwrespawn $HOME/nonafi/pi/kiosk.sh &" >> ~/.config/labwc/autostart'
    just restart-kiosk

# rsync the repo to the Pi (no restart).
sync:
    rsync -az --delete --exclude .git --exclude .venv --exclude __pycache__ --exclude music ./ {{pi_host}}:{{pi_path}}/

# Restart just the server (after code changes).
restart:
    ssh {{pi_host}} 'systemctl --user restart nonafi.service && sleep 1 && systemctl --user is-active nonafi.service'

# Relaunch the full-screen browser on the Pi's touchscreen.
restart-kiosk:
    ssh {{pi_host}} 'pkill -f "kiosk\\.s[h]"; pkill -f "nonafi-kios[k]"; true'
    ssh {{pi_host}} 'WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/$(id -u) setsid -f /usr/bin/lwrespawn {{pi_path}}/pi/kiosk.sh > /dev/null 2>&1 < /dev/null; echo kiosk started'

# Upload music: `just upload ~/Music/Some\ Album` copies that folder into the Pi's Music folder.
upload +folders:
    rsync -avh --progress "$@" {{pi_host}}:~/Music/
    ssh {{pi_host}} 'curl -s -X POST http://127.0.0.1:8080/api/rescan; echo'

# Delete an album folder from the Pi: `just remove "Demo Album One"`.
remove folder:
    ssh {{pi_host}} "cd ~/Music && rm -rv '{{folder}}'"
    ssh {{pi_host}} 'curl -s -X POST http://127.0.0.1:8080/api/rescan; echo'

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

# Take a screenshot of the Pi's screen and save it to captures/.
screenshot:
    mkdir -p captures
    ssh {{pi_host}} 'WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/$(id -u) grim /tmp/nonafi.png' && scp -q {{pi_host}}:/tmp/nonafi.png captures/$(date +%Y%m%d-%H%M%S).png && ls -t captures | head -1

# Open a shell on the Pi.
ssh:
    ssh {{pi_host}}

# Run the server locally on this Mac against ./music for development.
dev:
    python3 -m venv .venv 2>/dev/null; .venv/bin/pip install -q -e . && NONAFI_DEBUG=1 .venv/bin/python -m nonafi --music ./music --port 8080
