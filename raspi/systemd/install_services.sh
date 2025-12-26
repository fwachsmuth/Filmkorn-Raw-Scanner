#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

###
### filmkorn-scanner.service
###
SERVICE_NAME=filmkorn-scanner.service
SERVICE_SRC="${SCRIPT_DIR}/${SERVICE_NAME}"
SERVICE_DST="/etc/systemd/system/${SERVICE_NAME}"

if [[ ! -f "${SERVICE_SRC}" ]]; then
  echo "ERROR: ${SERVICE_SRC} not found"
  exit 1
fi

echo "Installing ${SERVICE_NAME}"
sudo install -m 0644 "${SERVICE_SRC}" "${SERVICE_DST}"

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"

# Restart if already running
sudo systemctl try-restart "${SERVICE_NAME}" || true

echo
echo "${SERVICE_NAME} installed and restarted (if it was running)"
echo

###
### lsyncd (repo-managed)
###
echo "Disabling SysV lsyncd.service if any"
sudo systemctl disable --now lsyncd.service 2>/dev/null || true
sudo systemctl mask lsyncd.service 2>/dev/null || true

echo "Installing filmkorn-lsyncd.service"
sudo install -m 0644 "${SCRIPT_DIR}/filmkorn-lsyncd.service" \
  /etc/systemd/system/filmkorn-lsyncd.service

sudo systemctl daemon-reload
sudo systemctl enable filmkorn-lsyncd.service
sudo systemctl restart filmkorn-lsyncd.service

###
### USB auto-mount (largest exfat/ext*)
###
echo "Installing USB auto-mount (largest exfat/ext*)"

sudo install -m 0755 "${SCRIPT_DIR}/../mount-largest-usb.sh" \
  /usr/local/sbin/mount-largest-usb.sh

sudo install -m 0644 "${SCRIPT_DIR}/usb-mount-largest@.service" \
  /etc/systemd/system/usb-mount-largest@.service

sudo install -m 0644 "${SCRIPT_DIR}/99-usb-mount-largest.rules" \
  /etc/udev/rules.d/99-usb-mount-largest.rules

sudo systemctl daemon-reload
sudo udevadm control --reload-rules

# retrigger add events so mounts happen immediately
sudo udevadm trigger --subsystem-match=block --action=add

echo "USB auto-mount installed and retriggered."

###
### RAM disk (/mnt/ramdisk)
###
echo "Installing RAM disk service (/mnt/ramdisk)"

sudo install -m 0755 "${SCRIPT_DIR}/../create_ramdisk.sh" \
  /usr/local/sbin/filmkorn-create-ramdisk.sh

sudo install -m 0644 "${SCRIPT_DIR}/filmkorn-ramdisk.service" \
  /etc/systemd/system/filmkorn-ramdisk.service

sudo systemctl daemon-reload
sudo systemctl enable filmkorn-ramdisk.service
sudo systemctl restart filmkorn-ramdisk.service

echo
echo "All services installed and restarted where applicable."