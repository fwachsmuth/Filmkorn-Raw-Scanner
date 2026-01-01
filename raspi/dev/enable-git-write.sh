#!/bin/bash
set -euo pipefail

# Run on the Raspi, not on the host computer.
# Enables git write access using the dev SSH key.

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

if ! [ -f /proc/device-tree/model ] || ! grep -qi "raspberry pi" /proc/device-tree/model; then
  warn "This script must run on the Raspi."
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  warn "git is not installed."
  exit 1
fi

if [ ! -f ~/.ssh/id_filmkorn-scanner-dev_ed25519 ]; then
  warn "Dev key not found at ~/.ssh/id_filmkorn-scanner-dev_ed25519"
  exit 1
fi

cd ~/Filmkorn-Raw-Scanner

info "Setting GitHub SSH remote..."
git remote set-url origin git@github.com:fwachsmuth/Filmkorn-Raw-Scanner.git

info "Configuring git identity..."
git config --global user.email "me@peaceman.de"
git config --global user.name "Friedemann Wachsmuth"

if ! grep -q id_filmkorn-scanner-dev_ed25519 ~/.ssh/config; then
  info "Updating ~/.ssh/config..."
  cat <<EOT >> ~/.ssh/config
Host github.com
  HostName github.com
  IdentityFile ~/.ssh/id_filmkorn-scanner-dev_ed25519
EOT
  chmod 600 ~/.ssh/config
fi

info "Dev git write access enabled."
