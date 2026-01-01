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

sudo install -m 0755 "${SCRIPT_DIR}/../scanner-helpers/mount-largest-usb.sh" \
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

sudo install -m 0755 "${SCRIPT_DIR}/../scanner-helpers/create_ramdisk.sh" \
  /usr/local/sbin/filmkorn-create-ramdisk.sh

sudo install -m 0644 "${SCRIPT_DIR}/filmkorn-ramdisk.service" \
  /etc/systemd/system/filmkorn-ramdisk.service

sudo systemctl daemon-reload
sudo systemctl enable filmkorn-ramdisk.service
sudo systemctl restart filmkorn-ramdisk.service

###
### Sleep/Wake helper services
###
echo "Installing sleep/wake helper services"

sudo install -m 0755 "${SCRIPT_DIR}/../scanner-helpers/filmkorn-sleep.sh" \
  /usr/local/sbin/filmkorn-sleep.sh
sudo install -m 0755 "${SCRIPT_DIR}/../scanner-helpers/filmkorn-wake.sh" \
  /usr/local/sbin/filmkorn-wake.sh

sudo install -m 0644 "${SCRIPT_DIR}/filmkorn-sleep.service" \
  /etc/systemd/system/filmkorn-sleep.service
sudo install -m 0644 "${SCRIPT_DIR}/filmkorn-wake.service" \
  /etc/systemd/system/filmkorn-wake.service

sudo systemctl daemon-reload
sudo systemctl disable --now filmkorn-sleep.service filmkorn-wake.service || true

###
### OTP pairing expiry helper
###
echo "Installing OTP pairing expiry helpers"

sudo install -m 0755 "${SCRIPT_DIR}/../scanner-helpers/filmkorn-otp-revoke.sh" \
  /usr/local/sbin/filmkorn-otp-revoke.sh
sudo install -m 0755 "${SCRIPT_DIR}/../scanner-helpers/filmkorn-otp-schedule.sh" \
  /usr/local/sbin/filmkorn-otp-schedule.sh

sudo install -m 0644 "${SCRIPT_DIR}/filmkorn-otp-schedule.service" \
  /etc/systemd/system/filmkorn-otp-schedule.service

sudo systemctl daemon-reload
sudo systemctl enable filmkorn-otp-schedule.service
sudo systemctl restart filmkorn-otp-schedule.service || true

echo
echo "All services installed and restarted where applicable."
