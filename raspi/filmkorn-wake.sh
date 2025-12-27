#!/usr/bin/env bash
set -euo pipefail

log() {
  echo "[filmkorn-wake] $*"
}

if command -v vcgencmd >/dev/null 2>&1; then
  log "Turning display on"
  vcgencmd display_power 1 || true
fi

if [ -w /sys/class/graphics/fb0/blank ]; then
  log "Unblanking framebuffer"
  echo 0 > /sys/class/graphics/fb0/blank || true
fi

for backlight in /sys/class/backlight/*; do
  [ -d "$backlight" ] || continue
  name="$(basename "$backlight")"
  if [ -w "$backlight/bl_power" ]; then
    echo 0 > "$backlight/bl_power" || true
  fi
  if [ -w "$backlight/brightness" ]; then
    saved="/tmp/filmkorn-backlight-${name}.brightness"
    if [ -r "$saved" ]; then
      log "Restoring backlight: ${name}"
      cat "$saved" > "$backlight/brightness" || true
      rm -f "$saved" || true
    elif [ -r "$backlight/max_brightness" ]; then
      log "Setting backlight to max: ${name}"
      cat "$backlight/max_brightness" > "$backlight/brightness" || true
    fi
  fi
done

if command -v mount-largest-usb.sh >/dev/null 2>&1; then
  log "Mounting largest USB volume"
  mount-largest-usb.sh || true
else
  log "Triggering udev for block devices"
  udevadm trigger --subsystem-match=block --action=add || true
fi

log "Starting lsyncd and scanner services"
systemctl start filmkorn-lsyncd.service filmkorn-scanner.service || true
