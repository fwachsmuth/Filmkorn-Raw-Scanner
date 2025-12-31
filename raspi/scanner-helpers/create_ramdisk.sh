#!/usr/bin/env bash
set -euo pipefail

# Create and mount a tmpfs RAM disk at /mnt/ramdisk.
# Size is computed to leave ~1 GiB free for the camera.

MNT="/mnt/ramdisk"
LEAVE_KIB=1048576  # 1 GiB in KiB

# Total RAM in KiB
TOTAL_KIB="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"

# Keep at least 256 MiB ramdisk if something is weird
if [[ -z "${TOTAL_KIB}" || "${TOTAL_KIB}" -le $((LEAVE_KIB + 262144)) ]]; then
  SIZE_KIB=262144
else
  SIZE_KIB=$((TOTAL_KIB - LEAVE_KIB))
fi

mkdir -p "${MNT}"

# If already mounted, do nothing
if /usr/bin/findmnt -rn "${MNT}" >/dev/null 2>&1; then
  exit 0
fi

exec /usr/bin/mount -t tmpfs -o "size=${SIZE_KIB}k" tmpfs "${MNT}"
