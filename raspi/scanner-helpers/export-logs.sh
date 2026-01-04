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
  echo "Version:"
  (
    cd /home/pi/Filmkorn-Raw-Scanner \
      && git describe --tags --exact-match 2>/dev/null \
      || git rev-parse --short HEAD 2>/dev/null \
      || true
  )
  echo
  if [ -f /home/pi/Filmkorn-Raw-Scanner/raspi/.host_path ]; then
    echo ".host_path:"
    cat /home/pi/Filmkorn-Raw-Scanner/raspi/.host_path
    echo
  fi
  if [ -f /home/pi/Filmkorn-Raw-Scanner/raspi/.scan_destination ]; then
    echo ".scan_destination:"
    cat /home/pi/Filmkorn-Raw-Scanner/raspi/.scan_destination
    echo
  fi
  if [ -f /home/pi/Filmkorn-Raw-Scanner/raspi/.user_and_host ]; then
    echo ".user_and_host:"
    cat /home/pi/Filmkorn-Raw-Scanner/raspi/.user_and_host
    echo
  fi
  if [ -f /proc/device-tree/model ]; then
    echo "Model:"
    tr -d '\0' < /proc/device-tree/model
    echo
  fi
  if [ -f /sys/class/thermal/thermal_zone0/temp ]; then
    temp_c="$(awk '{printf "%.1f", $1/1000}' /sys/class/thermal/thermal_zone0/temp)"
    echo "Temperature: ${temp_c}C"
    echo
  elif command -v vcgencmd >/dev/null 2>&1; then
    echo "Temperature: $(vcgencmd measure_temp | sed 's/^temp=//')"
    echo
  fi
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
