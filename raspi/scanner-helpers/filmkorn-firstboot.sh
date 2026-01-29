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

echo "firstboot: ensuring ssh host keys"
ssh-keygen -A || true
systemctl enable --now ssh || true

# Create swap file if it doesn't exist (imaging excludes /var/swap to reduce image size)
SWAP_FILE="/var/swap"
SWAP_SIZE_MB=2048
if [ ! -f "$SWAP_FILE" ]; then
  echo "firstboot: creating ${SWAP_SIZE_MB}MB swap file"
  dd if=/dev/zero of="$SWAP_FILE" bs=1M count="$SWAP_SIZE_MB" status=progress || true
  chmod 600 "$SWAP_FILE"
  mkswap "$SWAP_FILE" || true
  swapon "$SWAP_FILE" || true
  # Ensure swap is enabled on boot (if not already in fstab)
  if ! grep -q "^$SWAP_FILE" /etc/fstab; then
    echo "$SWAP_FILE none swap sw 0 0" >> /etc/fstab
  fi
else
  echo "firstboot: swap file already exists"
fi

touch "$MARKER_FILE"
systemctl disable --now filmkorn-firstboot.service || true

echo "firstboot: done"
