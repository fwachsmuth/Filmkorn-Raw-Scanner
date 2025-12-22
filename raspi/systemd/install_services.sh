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