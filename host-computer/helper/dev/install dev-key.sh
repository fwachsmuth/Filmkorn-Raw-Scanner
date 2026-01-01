#!/bin/bash
set -euo pipefail

# Run on the host computer (Mac), not on the Raspi.
# Installs the dev SSH key on the scanner and enables git write access.

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

if ! command -v scp >/dev/null 2>&1; then
  warn "scp is not installed."
  exit 1
fi
if ! command -v ssh >/dev/null 2>&1; then
  warn "ssh is not installed."
  exit 1
fi

if ! ls ~/.ssh/id_filmkorn-scanner-dev_ed25519* >/dev/null 2>&1; then
  warn "Dev key not found at ~/.ssh/id_filmkorn-scanner-dev_ed25519*"
  exit 1
fi

info "Copying dev key to scanner..."
scp ~/.ssh/id_filmkorn-scanner-dev_ed25519* pi@filmkorn-scanner.local:~/.ssh

info "Enabling git write access on the scanner..."
ssh pi@filmkorn-scanner.local "cd Filmkorn-Raw-Scanner/raspi/dev; ./enable-git-write.sh"
