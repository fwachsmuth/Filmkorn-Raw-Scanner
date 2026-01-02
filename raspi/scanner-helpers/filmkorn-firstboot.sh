#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="/var/log/filmkorn-firstboot.log"
MARKER_FILE="/var/lib/filmkorn/firstboot.done"

mkdir -p "$(dirname "$LOG_FILE")" "/var/lib/filmkorn"
exec >>"$LOG_FILE" 2>&1

if [[ -f "$MARKER_FILE" ]]; then
  exit 0
fi

echo "firstboot: start $(date -Is)"

if command -v raspi-config >/dev/null 2>&1; then
  echo "firstboot: expanding root filesystem"
  raspi-config nonint do_expand_rootfs || true
else
  echo "firstboot: raspi-config not found; skipping expand"
fi

touch "$MARKER_FILE"
systemctl disable --now filmkorn-firstboot.service || true

echo "firstboot: done"
