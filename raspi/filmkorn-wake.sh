#!/usr/bin/env bash
set -euo pipefail

log() {
  echo "[filmkorn-wake] $*"
}

if command -v vcgencmd >/dev/null 2>&1; then
  log "Turning display on"
  vcgencmd display_power 1 || true
fi

if command -v mount-largest-usb.sh >/dev/null 2>&1; then
  log "Mounting largest USB volume"
  mount-largest-usb.sh || true
else
  log "Triggering udev for block devices"
  udevadm trigger --subsystem-match=block --action=add || true
fi

log "Starting lsyncd and scanner services"
systemctl start filmkorn-lsyncd.service filmkorn-scanner.service || true
