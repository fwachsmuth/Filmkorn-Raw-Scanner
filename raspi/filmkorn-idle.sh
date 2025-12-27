#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-}"
MNT="/mnt/usb"

# services you want to pause/resume
SCANNER_SVC="filmkorn-scanner.service"
LSYNCD_SVC="filmkorn-lsyncd.service"

display_off() {
  # works on Raspberry Pi OS with FKMS/KMS; harmless if unsupported
  /usr/bin/vcgencmd display_power 0 >/dev/null 2>&1 || true
}

display_on() {
  /usr/bin/vcgencmd display_power 1 >/dev/null 2>&1 || true
}

umount_usb() {
  if /usr/bin/findmnt -rn "$MNT" >/dev/null 2>&1; then
    /usr/bin/sync || true
    /usr/bin/umount "$MNT" || /usr/bin/umount -l "$MNT" || true
  fi
}

case "$ACTION" in
  sleep)
    # stop background load first
    /bin/systemctl stop "$LSYNCD_SVC" || true
    /bin/systemctl stop "$SCANNER_SVC" || true

    # ensure clean detach semantics
    umount_usb

    # turn display off
    display_off
    ;;

  wake)
    # turn display on first
    display_on

    # don’t force-mount here; udev automount will do it when the disk appears.
    # just bring services back
    /bin/systemctl start "$SCANNER_SVC" || true
    /bin/systemctl start "$LSYNCD_SVC" || true
    ;;

  *)
    echo "Usage: $0 {sleep|wake}" >&2
    exit 2
    ;;
esac