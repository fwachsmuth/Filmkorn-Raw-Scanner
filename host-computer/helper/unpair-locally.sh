#!/bin/bash
set -euo pipefail

# Run on the host computer (Mac), not on the Raspi.
# Removes local pairing artifacts without touching the Raspi.

if [ -t 1 ]; then
  BOLD="$(printf '\033[1m')"
  GREEN="$(printf '\033[32m')"
  YELLOW="$(printf '\033[33m')"
  RESET="$(printf '\033[0m')"
else
  BOLD=""
  GREEN=""
  YELLOW=""
  RESET=""
fi

info() {
  echo "${BOLD}${GREEN}$*${RESET}"
}

warn() {
  echo "${BOLD}${YELLOW}$*${RESET}"
}

if [ -f /proc/device-tree/model ] && grep -qi "raspberry pi" /proc/device-tree/model; then
  warn "This script must run on the host computer, not on the Raspi."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCAN_DESTINATION_FILE="${HOST_DIR}/.scan_destination"
INSTALL_SEMAPHORE="${HOST_DIR}/.scanner_installed"

read -r -p "Proceed with local unpairing (no changes on the Raspi)? [y/N] " confirm_unpair
if [[ ! "${confirm_unpair:-}" =~ ^[Yy]$ ]]; then
  warn "Local unpairing canceled."
  exit 0
fi

if [ -f "$SCAN_DESTINATION_FILE" ]; then
  read -r -p "Also delete the saved scan destination (.scan_destination)? [y/N] " delete_dest
  if [[ "${delete_dest:-}" =~ ^[Yy]$ ]]; then
    rm -f "$SCAN_DESTINATION_FILE" || true
  fi
fi

info "Removing Raspi from this computer's known_hosts..."
ssh-keygen -R filmkorn-scanner.local >/dev/null 2>&1 || true

info "Removing Raspi from this computer's authorized_keys..."
sed -i '' '\#pi@filmkorn-scanner#d' ~/.ssh/authorized_keys || true # BSD sed

info "Removing keypair from this computer..."
rm -f ~/.ssh/id_filmkorn-scanner_ed25519* || true

rm -f "${HOST_DIR}/.paired" || true
rm -f "$INSTALL_SEMAPHORE" || true

info "Local known_hosts:"
cat ~/.ssh/known_hosts || true
echo "------------------------------------------------"
info "Local authorized_keys:"
cat ~/.ssh/authorized_keys || true
echo "------------------------------------------------"
info "Remaining local keys:"
ls -la ~/.ssh/ || true
echo "------------------------------------------------"
info "Local ssh config:"
cat ~/.ssh/config || true
echo ""
echo "------------------------------------------------"

info "Local unpairing completed."
