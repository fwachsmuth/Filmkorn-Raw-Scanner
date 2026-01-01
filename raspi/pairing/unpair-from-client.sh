#!/bin/bash
set -euo pipefail

# To be run on the Raspi, not on the host computer.
# This script removes ssh pairing artifacts on the Raspi, allowing a fresh pairing.


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

info "🐧 Removing your host computer from Raspi's authorized_keys..."
sed -i '\#scanning-#d' ~/.ssh/authorized_keys || true

# Remove local keypairs
info "🐧 Removing keypair from Raspi..."
rm -f ~/.ssh/id_filmkorn-scanner_ed25519* || true

info "🐧 Re-enabling password authentication on Raspi..."
sudo rm -f /etc/ssh/sshd_config.d/filmkorn-password.conf || true
sudo rm -f /var/lib/filmkorn/otp_expires_at || true
sudo systemctl stop filmkorn-otp-expire.service >/dev/null 2>&1 || true
sudo systemctl reload ssh || sudo systemctl restart ssh || true

# Verify
echo ""
info "🐧 Results of unpairing on Raspi:"
info "🐧 Raspi's known_hosts:"
test ~/.ssh/known_hosts && cat ~/.ssh/known_hosts || true
echo "------------------------------------------------"
info "🐧 Raspi's remaining authorized_keys:"
test ~/.ssh/authorized_keys && cat ~/.ssh/authorized_keys || true
echo "------------------------------------------------"
info "🐧 Raspi's remaining keys:"
ls -la ~/.ssh/ || true
echo "------------------------------------------------"
info "🐧 Raspi's remaining ssh config:"
test ~/.ssh/config && cat ~/.ssh/config || true
echo "------------------------------------------------"

info "🐧 Raspi finished its unpairing."
echo ""
