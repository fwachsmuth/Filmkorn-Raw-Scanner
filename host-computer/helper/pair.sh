#!/bin/bash
set -euo pipefail

# Run on the host computer, not on the Raspi.
# Pairs SSH keys in both directions and configures remote destination if available.

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

paired_exists=false
if [ -f ".paired" ]; then
  paired_exists=true
fi
if $paired_exists && [ -f ".scan_destination" ]; then
  warn "Systems already paired. Use ./helper/unpair.sh first if you want to initiate pairing again."
  exit 0
fi

if ! command -v ssh >/dev/null 2>&1; then
  warn "ssh is not installed."
  exit 1
fi
if ! command -v ssh-keygen >/dev/null 2>&1; then
  warn "ssh-keygen is not installed."
  exit 1
fi

# Generate and deploy a keypair to control the scanning Raspi
if ! $paired_exists; then
  info "Generating local SSH keypair for the scanner..."
  ssh-keygen -t ed25519 -q -f ~/.ssh/id_filmkorn-scanner_ed25519 -C "scanning-$(whoami)@$(hostname -s)" -N ''
fi

# Configure this computer for easy & secure ssh to the Raspi, if it isn't yet
if ! grep -q filmkorn-scanner.local ~/.ssh/config; then
  info "Updating ~/.ssh/config..."
  cat <<EOT >> ~/.ssh/config
Host filmkorn-scanner.local
  AddKeysToAgent no
  UseKeychain no
  IdentitiesOnly yes
  IdentityFile ~/.ssh/id_filmkorn-scanner_ed25519
  StrictHostKeyChecking no
EOT
fi

if ! $paired_exists; then
  # To do: Use sesame key for ssh-copy and delete it afterwards
  echo "Please enter the temporary Raspi password ${BOLD}'filmkornscanner'${RESET} to allow pairing."
  ssh-copy-id -i ~/.ssh/id_filmkorn-scanner_ed25519.pub pi@filmkorn-scanner.local > /dev/null 2> /dev/null
fi

if ! $paired_exists; then
  # On the Raspi, generate and deploy a keypair to send files to this computer
  info "Generating SSH keypair on the Raspi..."
  ssh pi@filmkorn-scanner.local "ssh-keygen -t ed25519 -q -f ~/.ssh/id_filmkorn-scanner_ed25519 -C pi@filmkorn-scanner -N ''"
  echo ""
  echo "When prompted, please enter the password ${BOLD}of this Mac${RESET} to allow receiving scanned film frames going forward."
  ssh pi@filmkorn-scanner.local -t "ssh-copy-id -i ~/.ssh/id_filmkorn-scanner_ed25519.pub $(whoami)@$(hostname -s).local > /dev/null 2> /dev/null"
fi

if [ -f ".scan_destination" ]; then
  info "Configuring where on the Mac the scans should be stored..."
  ssh -t pi@filmkorn-scanner.local "FORCE_COLOR=1 ./Filmkorn-Raw-Scanner/raspi/pairing/update-destination.sh -h $(whoami)@$(hostname -s).local -p \"$(cat .scan_destination)\""
else
  warn "No Scanning Destination defined yet."
  ./helper/set_scan_destination.sh
fi

echo ""
info "Pairing successfully completed!"
echo ""
touch .paired
