#!/usr/bin/env bash
set -euo pipefail

log() {
  echo "[filmkorn-sleep] $*"
}

log "Stopping scanner and lsyncd services"
systemctl stop filmkorn-scanner.service filmkorn-lsyncd.service || true

if mountpoint -q /mnt/usb; then
  log "Unmounting /mnt/usb"
  umount /mnt/usb || umount -l /mnt/usb || true
fi

if command -v vcgencmd >/dev/null 2>&1; then
  log "Turning display off"
  vcgencmd display_power 0 || true
fi

for backlight in /sys/class/backlight/*; do
  [ -d "$backlight" ] || continue
  if [ -w "$backlight/brightness" ]; then
    name="$(basename "$backlight")"
    if [ -r "$backlight/brightness" ]; then
      cat "$backlight/brightness" > "/tmp/filmkorn-backlight-${name}.brightness" || true
    fi
    log "Disabling backlight: ${name}"
    echo 0 > "$backlight/brightness" || true
  fi
  if [ -w "$backlight/bl_power" ]; then
    echo 4 > "$backlight/bl_power" || true
  fi
done
