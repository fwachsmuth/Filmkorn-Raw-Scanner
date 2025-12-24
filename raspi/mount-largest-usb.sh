#!/bin/bash
set -euo pipefail

DISK="${1:-}"        # e.g. sda
MNT="/mnt/usb"
LOCK="/run/mount-largest-usb.lock"

exec 9>"$LOCK"
flock -x 9

if [[ -z "$DISK" ]]; then
  echo "usage: $0 <diskname like sda>" >&2
  exit 2
fi

DEV="/dev/$DISK"

# If disk node isn't there yet, make this a transient failure so systemd can retry
[[ -b "$DEV" ]] || { echo "Disk device $DEV not present (yet)" >&2; exit 1; }

mkdir -p "$MNT"

# udev race: partitions/FSTYPE can appear shortly after the disk event
for _ in $(seq 1 50); do
  if lsblk -nr -o TYPE,FSTYPE "$DEV" 2>/dev/null \
    | awk '$1=="part" && ($2=="ext4"||$2=="ext3"||$2=="ext2"||$2=="exfat") {found=1} END{exit(found?0:1)}'
  then
    break
  fi
  sleep 0.1
done

best_part="$(
  lsblk -b -nr -o NAME,SIZE,TYPE,FSTYPE "$DEV" \
    | awk '$3=="part" && ($4=="ext4" || $4=="ext3" || $4=="ext2" || $4=="exfat") {print $1, $2, $4}' \
    | sort -k2,2nr \
    | head -n1 \
    | awk '{print $1}'
)"

if [[ -z "${best_part:-}" ]]; then
  echo "No ext2/3/4 or exfat partition found on $DEV (yet)" >&2
  exit 1
fi

PART="/dev/$best_part"
FSTYPE="$(blkid -o value -s TYPE "$PART" 2>/dev/null || true)"

if mountpoint -q "$MNT"; then
  cur_src="$(findmnt -n -o SOURCE --target "$MNT" || true)"
  if [[ "$cur_src" == "$PART" ]]; then
    if ! ( : >"$MNT/.filmkorn_rw_test" 2>/dev/null && rm -f "$MNT/.filmkorn_rw_test" 2>/dev/null ); then
      echo "Mounted on $MNT but not writable (stale mount?). Remounting..." >&2
      umount "$MNT" || umount -l "$MNT" || true
    else
      exit 0
    fi
  else
    umount "$MNT" || umount -l "$MNT" || true
  fi
fi

if [[ "$FSTYPE" == "exfat" ]]; then
  UID_PI="$(id -u pi 2>/dev/null || echo 1000)"
  GID_PI="$(id -g pi 2>/dev/null || echo 1000)"
  mount -t exfat -o "noatime,lazytime,uid=$UID_PI,gid=$GID_PI,fmask=0022,dmask=0022" "$PART" "$MNT"
else
  mount -t "$FSTYPE" -o "noatime,lazytime" "$PART" "$MNT"
fi

# Ensure we actually mounted
findmnt -n --target "$MNT" >/dev/null 2>&1 || { echo "Mount failed: $MNT is not a mountpoint" >&2; exit 1; }