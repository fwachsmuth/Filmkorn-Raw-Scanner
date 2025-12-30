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

export HOME="${HOME:-/root}"

PREV_REF="$(git rev-parse HEAD 2>/dev/null || true)"
PREV_DESC="$(git describe --tags --always 2>/dev/null || true)"

on_exit() {
  local status=$?
  if [ "$status" -ne 0 ]; then
    log "update: failed code=$status"
    if [ -n "$PREV_REF" ]; then
      log "update: restoring $PREV_DESC ($PREV_REF)"
      run_and_log "git-restore" git checkout "$PREV_REF"
    fi
  fi
  log "update: starting $SERVICE_NAME"
  sudo systemctl start "$SERVICE_NAME" || true
}

trap on_exit EXIT

run_and_log() {
  local label="$1"
  shift
  log "update: ${label} start"
  set +e
  "$@" 2>&1 | while IFS= read -r line; do
    log "${label}: ${line}"
  done
  local status=${PIPESTATUS[0]}
  set -e
  if [ "$status" -ne 0 ]; then
    log "update: ${label} failed code=${status}"
  else
    log "update: ${label} ok"
  fi
  return "$status"
}

cd "$REPO_DIR"
log "update: marking repo safe for git"
git config --system --add safe.directory "$REPO_DIR" || true
log "update: stopping $SERVICE_NAME"
sudo systemctl stop "$SERVICE_NAME" || true
log "update: fetching tags"
REMOTE_URL="$(git config --get remote.origin.url || true)"
if [[ "$REMOTE_URL" == git@github.com:* ]]; then
  HTTPS_URL="https://github.com/${REMOTE_URL#git@github.com:}"
  log "update: switching origin to HTTPS ($HTTPS_URL)"
  git remote set-url origin "$HTTPS_URL"
fi
run_and_log "git-fetch" git fetch --tags --prune
log "update: checking out $TAG"
run_and_log "git-checkout" git checkout "$TAG"

if [ -f scan-controller/scan-controller.ino.with_bootloader.hex ]; then
  log "update: flashing controller (avrdude)"
  run_and_log "flash" env SKIP_SERVICE_RESTART=1 bash scan-controller/bootstrap/flash-atmega328.sh
fi

log "update: reloading systemd"
run_and_log "systemd-reload" sudo systemctl daemon-reload
log "update: rebooting"
trap - EXIT
sudo reboot
