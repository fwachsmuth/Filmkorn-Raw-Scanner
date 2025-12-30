#!/bin/bash
set -euo pipefail

TAG="${1:-}"
if [ -z "$TAG" ]; then
  echo "Usage: $0 <git-tag>"
  exit 1
fi

REPO_DIR="/home/pi/Filmkorn-Raw-Scanner"
SERVICE_NAME="filmkorn-scanner.service"
LOG_TAG="filmkorn-update"

log() {
  logger -t "$LOG_TAG" "$*"
}

cd "$REPO_DIR"
log "update: stopping $SERVICE_NAME"
sudo systemctl stop "$SERVICE_NAME" || true
cleanup() {
  log "update: starting $SERVICE_NAME"
  sudo systemctl start "$SERVICE_NAME" || true
}
trap cleanup EXIT
log "update: fetching tags"
git fetch --tags --prune
log "update: checking out $TAG"
git checkout "$TAG"

if [ -f scan-controller/scan-controller.ino.with_bootloader.hex ]; then
  log "update: flashing controller (avrdude)"
  SKIP_SERVICE_RESTART=1 bash scan-controller/bootstrap/flash-atmega328.sh 2>&1 \
    | while IFS= read -r line; do log "avrdude: $line"; done
  log "update: flashing complete"
fi

log "update: reloading systemd"
sudo systemctl daemon-reload || true
trap - EXIT
log "update: rebooting"
sudo reboot
