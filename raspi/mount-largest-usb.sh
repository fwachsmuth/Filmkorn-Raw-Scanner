#!/bin/bash
set -euo pipefail

DISK="${1:-}"        # e.g. sda
MNT="/mnt/usb"
LOCK="/run/mount-largest-usb.lock"

exec 9>"$LOCK"
flock -x 9

udevadm settle --timeout=5 || true

if [[ -z "$DISK" ]]; then
  echo "usage: $0 <diskname like sda>" >&2
  exit 2
fi

DEV="/dev/$DISK"
[[ -b "$DEV" ]] || exit 0

mkdir -p "$MNT"

# Pick largest partition with FSTYPE in {ext2,ext3,ext4,exfat}
best_part="$(
  lsblk -b -nr -o NAME,SIZE,TYPE,FSTYPE "$DEV" \
    | awk '$3=="part" && ($4=="ext4" || $4=="ext3" || $4=="ext2" || $4=="exfat") {print $1, $2, $4}' \
    | sort -k2,2nr \
    | head -n1 \
    | awk '{print $1}'
)"

if [[ -z "${best_part:-}" ]]; then
  echo "No ext2/3/4 or exfat partition found on $DEV" >&2
  exit 0
fi

PART="/dev/$best_part"
FSTYPE="$(blkid -o value -s TYPE "$PART" 2>/dev/null || true)"

# If something is already mounted there, only replace it if it's different
if mountpoint -q "$MNT"; then
  cur_src="$(findmnt -n -o SOURCE --target "$MNT" || true)"
  if [[ "$cur_src" == "$PART" ]]; then
    exit 0
  fi
  umount "$MNT" || umount -l "$MNT"
fi

# Mount options:
# - ext*: noatime,lazytime
# - exfat: plus ownership + masks (otherwise root-owned)
if [[ "$FSTYPE" == "exfat" ]]; then
  UID_PI="$(id -u pi 2>/dev/null || echo 1000)"
  GID_PI="$(id -g pi 2>/dev/null || echo 1000)"
  mount -t exfat -o "noatime,lazytime,uid=$UID_PI,gid=$GID_PI,fmask=0022,dmask=0022" "$PART" "$MNT"
else
  mount -t "$FSTYPE" -o "noatime,lazytime" "$PART" "$MNT"
fi