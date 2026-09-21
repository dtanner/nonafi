#!/bin/bash
# Full-screen Chromium on the touchscreen, pointed at the local nonafi server.
URL="http://127.0.0.1:8080/"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

# Wait for the server so the first page load isn't an error page.
for _ in $(seq 1 60); do
  curl -fs -o /dev/null "$URL/api/albums" && break
  sleep 1
done

# Opt-in remote debugging (localhost only), used for driving the UI from scripts during development.
DEBUG_FLAGS=()
[ -e "$HOME/.config/nonafi/debug" ] && DEBUG_FLAGS=(--remote-debugging-port=9222 --remote-allow-origins=http://127.0.0.1:9222)

exec chromium \
  --kiosk "$URL" \
  --ozone-platform=wayland \
  --user-data-dir="$HOME/.config/nonafi-kiosk" \
  --noerrdialogs --disable-infobars --disable-session-crashed-bubble \
  --no-first-run --disable-features=TranslateUI \
  --autoplay-policy=no-user-gesture-required \
  --touch-events=enabled --disable-pinch --overscroll-history-navigation=0 \
  --check-for-update-interval=31536000 \
  --password-store=basic --disable-component-update \
  "${DEBUG_FLAGS[@]}"
