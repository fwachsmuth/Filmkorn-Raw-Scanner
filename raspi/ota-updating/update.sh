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
PREFLIGHT_SCRIPT="/home/pi/Filmkorn-Raw-Scanner/raspi/ota-updating/preflight.sh"
POSTFLIGHT_SCRIPT="/home/pi/Filmkorn-Raw-Scanner/raspi/ota-updating/postflight.sh"

log() {
  logger -t "$LOG_TAG" "$*"
}

export HOME="${HOME:-/root}"

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

run_hook() {
  local label="$1"
  local script="$2"
  if [ -f "$script" ]; then
    run_and_log "$label" bash "$script"
  else
    log "update: ${label} skipped (missing $script)"
  fi
}

cd "$REPO_DIR"
log "update: marking repo safe for git"
git config --system --add safe.directory "$REPO_DIR" || true
PREV_REF="$(git rev-parse HEAD 2>/dev/null || true)"
PREV_DESC="$(git describe --tags --always 2>/dev/null || true)"
log "update: current ref $PREV_DESC ($PREV_REF)"

on_exit() {
  local status=$?
  if [ "$status" -ne 0 ]; then
    log "update: failed code=$status"
    if [ -n "$PREV_REF" ]; then
      log "update: restoring $PREV_DESC ($PREV_REF)"
      run_and_log "git-restore" git checkout -f "$PREV_REF"
    fi
  fi
  log "update: starting $SERVICE_NAME"
  sudo systemctl start "$SERVICE_NAME" || true
}

trap on_exit EXIT
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
HEX_PATH="scan-controller/build/arduino.avr.pro/scan-controller.ino.with_bootloader.hex"
if [ ! -f "$HEX_PATH" ]; then
  log "update: missing hex file $HEX_PATH; aborting update"
  exit 1
fi

log "update: flashing controller (avrdude)"
run_hook "preflight" "$PREFLIGHT_SCRIPT"
log "update: enabling MCU power (GPIO16)"
run_and_log "uc-power" python3 - <<'PY'
import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(16, GPIO.OUT, initial=GPIO.HIGH)
PY
sleep 0.5
run_and_log "flash" /usr/local/bin/avrdude \
  -C /home/pi/avrdude_gpio.conf \
  -p atmega328p \
  -c raspberry_pi_gpio \
  -P gpiochip0 \
  -U flash:w:${HEX_PATH}:i
run_hook "postflight" "$POSTFLIGHT_SCRIPT"

log "update: reloading systemd"
run_and_log "systemd-reload" sudo systemctl daemon-reload
log "update: installing systemd services"
run_and_log "systemd-install" sudo bash /home/pi/Filmkorn-Raw-Scanner/raspi/systemd/install_services.sh
log "update: completed (no reboot requested)"
