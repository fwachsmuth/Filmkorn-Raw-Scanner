#!/bin/bash
set -euo pipefail

TAG="${1:-}"
if [ -z "$TAG" ]; then
  echo "Usage: $0 <git-tag>"
  exit 1
fi

REPO_DIR="/home/pi/Filmkorn-Raw-Scanner"
SERVICE_NAME="filmkorn-scanner.service"

cd "$REPO_DIR"
sudo systemctl stop "$SERVICE_NAME" || true
cleanup() {
  sudo systemctl start "$SERVICE_NAME" || true
}
trap cleanup EXIT
git fetch --tags --prune
git checkout "$TAG"

if [ -f scan-controller/scan-controller.ino.with_bootloader.hex ]; then
  SKIP_SERVICE_RESTART=1 bash scan-controller/bootstrap/flash-atmega328.sh
fi

sudo systemctl daemon-reload || true
trap - EXIT
sudo reboot
