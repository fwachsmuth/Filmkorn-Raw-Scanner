#!/bin/bash
set -euo pipefail
umask 0002

OUT_DIR="/mnt/ramdisk"
if [ ! -d "$OUT_DIR" ]; then
  echo "export-logs: ${OUT_DIR} not found" >&2
  exit 1
fi

if [ ! -w "$OUT_DIR" ]; then
  echo "export-logs: ${OUT_DIR} is not writable" >&2
  exit 1
fi

if ! command -v zip >/dev/null 2>&1; then
  echo "export-logs: zip not installed" >&2
  exit 1
fi

timestamp="$(date +%Y%m%d-%H%M)"
outfile="${OUT_DIR}/scan-log-${timestamp}.zip"
tmpdir="$(mktemp -d)"

cleanup() {
  rm -rf "$tmpdir"
}
trap cleanup EXIT

scanner_log="/home/pi/Filmkorn-Raw-Scanner/raspi/scanner.log"
if [ -f "$scanner_log" ]; then
  cp "$scanner_log" "${tmpdir}/scanner.log"
fi

journalctl -b -o short-iso --no-pager > "${tmpdir}/journalctl-boot.log"

{
  echo "Timestamp: $(date --iso-8601=seconds)"
  echo "Uptime:"
  uptime
  echo
  echo "Kernel:"
  uname -a
  echo
  echo "Disk usage:"
  df -h
  echo
  echo "Block devices:"
  lsblk -f
  echo
  echo "Network:"
  ip -br a
  if command -v vcgencmd >/dev/null 2>&1; then
    echo
    echo "Throttling:"
    vcgencmd get_throttled
  fi
} > "${tmpdir}/system-info.txt"

(cd "$tmpdir" && zip -q -r "$outfile" .)
chown pi:pi "$outfile" || true
echo "$outfile"
