#!/bin/bash
# Desktop pieces for touch-only Wi-Fi setup, run on the Pi by `just deploy`. Idempotent, no sudo.
#  - starts the squeekboard on-screen keyboard with the session (the top bar already has its toggle)
#  - adds a "Jukebox" launcher to the top bar and the desktop that returns to the kiosk
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
mkdir -p ~/.config/labwc ~/.local/share/applications ~/.config/wf-panel-pi ~/.config/nonafi

grep -q '^/usr/bin/sbout' ~/.config/labwc/autostart 2>/dev/null || echo '/usr/bin/sbout &' >> ~/.config/labwc/autostart
pgrep -x squeekboard > /dev/null || setsid -f /usr/bin/sbout > /dev/null 2>&1 < /dev/null

cat > ~/.local/share/applications/nonafi-jukebox.desktop <<DESKTOP
[Desktop Entry]
Type=Application
Name=Jukebox
Comment=Back to the jukebox
Icon=audio-x-generic
Exec=rm -f $HOME/.config/nonafi/setup
Terminal=false
DESKTOP

# The same launcher as a big labelled icon on the desktop.
mkdir -p ~/Desktop
cp ~/.local/share/applications/nonafi-jukebox.desktop ~/Desktop/Jukebox.desktop
chmod +x ~/Desktop/Jukebox.desktop

INI=~/.config/wf-panel-pi/wf-panel-pi.ini
if ! grep -q nonafi-jukebox "$INI" 2>/dev/null; then
  if grep -q '^launchers=' "$INI" 2>/dev/null; then
    sed -i 's/^launchers=/launchers=nonafi-jukebox /' "$INI"
  else
    printf '[panel]\nlaunchers=nonafi-jukebox\n' >> "$INI"
  fi
  pkill -x wf-panel-pi   # lwrespawn brings it back with the new launcher
fi
echo "desktop setup done"
