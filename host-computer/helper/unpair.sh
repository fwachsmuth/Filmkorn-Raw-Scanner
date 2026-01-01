#!/bin/bash
set -euo pipefail

# this script removes ssh pairing keys and local references, allowing a fresh pairing.

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

read -r -p "Proceed with unpairing this host and your scanner? [y/N] " confirm_unpair
if [[ ! "${confirm_unpair:-}" =~ ^[Yy]$ ]]; then
  warn "Unpairing canceled."
  exit 0
fi

info "Asking Raspi to unpair..."
ssh-keygen -R filmkorn-scanner.local >/dev/null 2>&1 || true
ssh-keyscan -H -t ed25519 filmkorn-scanner.local 2>/dev/null | grep -v '^#' >> ~/.ssh/known_hosts || true
unpair_ok=true
if ! ssh -t -o StrictHostKeyChecking=accept-new -o IdentitiesOnly=yes -i ~/.ssh/id_filmkorn-scanner_ed25519 \
  pi@filmkorn-scanner.local \
  "cd Filmkorn-Raw-Scanner/raspi/pairing; FORCE_COLOR=1 ./unpair-from-client.sh"
then
  warn "The Raspi failed to unpair."
  unpair_ok=false
fi

info "  Removing Raspi from this computer's known_hosts..."
ssh-keygen -R filmkorn-scanner.local >/dev/null 2>&1 || true

info "  Removing Raspi from this computer's authorized_keys..."
sed -i '' '\#pi@filmkorn-scanner#d' ~/.ssh/authorized_keys || true # BSD sed

info "  Removing keypair from this computer..."
rm -f ~/.ssh/id_filmkorn-scanner_ed25519* || true

rm -f .paired || true

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

if $unpair_ok; then
  info "Unpairing completed on the Raspi."
else
  warn "Unpairing did not succeed on the Raspi. Please retry once the scanner is reachable."
fi
