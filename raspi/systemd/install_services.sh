#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME=filmkorn-scanner.service
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_SRC="${SCRIPT_DIR}/${SERVICE_NAME}"
SERVICE_DST="/etc/systemd/system/${SERVICE_NAME}"

if [[ ! -f "${SERVICE_SRC}" ]]; then
  echo "ERROR: ${SERVICE_SRC} not found"
  exit 1
fi

echo "Installing ${SERVICE_NAME} to ${SERVICE_DST}"
sudo cp "${SERVICE_SRC}" "${SERVICE_DST}"

echo "Reloading systemd daemon"
sudo systemctl daemon-reload

echo "Enabling service"
sudo systemctl enable "${SERVICE_NAME}"

echo
echo "Done."
echo
echo "You can now start it with:"
echo "  sudo systemctl start ${SERVICE_NAME}"
echo
echo "Logs:"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"

# lsyncd service installation
echo "Disabling SysV lsyncd.service if any"
sudo systemctl disable --now lsyncd.service 2>/dev/null || true
sudo systemctl mask lsyncd.service 2>/dev/null || true

echo "Installing filmkorn-lsyncd.service"
sudo cp -f "$(dirname "$0")/filmkorn-lsyncd.service" /etc/systemd/system/filmkorn-lsyncd.service

echo "Reloading systemd daemon"
sudo systemctl daemon-reload

echo "Enabling filmkorn-lsyncd.service"
sudo systemctl enable --now filmkorn-lsyncd.service