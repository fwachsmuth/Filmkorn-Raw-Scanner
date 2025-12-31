#!/bin/bash
set -euo pipefail

# Run on the host computer (Mac), not on the Raspi.
# Removes pairing keys and local references.

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

info "Asking Raspi to unpair..."
ssh pi@filmkorn-scanner.local "cd Filmkorn-Raw-Scanner/raspi; ./unpair-from-client.sh" || warn "Raspi unpair command failed"

info "Removing Raspi from this computer's known_hosts..."
ssh-keygen -R filmkorn-scanner.local >/dev/null 2>&1 || true

info "Removing Raspi from this computer's authorized_keys..."
sed -i '' '\#pi@filmkorn-scanner#d' ~/.ssh/authorized_keys || true # BSD sed

info "Removing keypair from this computer..."
rm -f ~/.ssh/id_filmkorn-scanner_ed25519* || true

rm -f .paired || true

info "Local known_hosts:"
cat ~/.ssh/known_hosts || true
echo "------------------------------------------------"
info "Local authorized_keys:"
cat ~/.ssh/authorized_keys || true
echo "------------------------------------------------"
info "Local keys:"
ls -la ~/.ssh/ || true
echo "------------------------------------------------"
info "Local config:"
cat ~/.ssh/config || true
echo "------------------------------------------------"
