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

check_scanner_reachable() {
  if ! ping -c 1 -W 1 filmkorn-scanner.local >/dev/null 2>&1; then
    warn "Scanner could not be reached. Please connect your Scanner to Ethernet and turn it on, then try again."
    exit 1
  fi
}

check_local_ssh_reachable() {
  if ! command -v nc >/dev/null 2>&1; then
    warn "nc (netcat) not found; skipping local SSH reachability check."
    return
  fi
  if ! nc -z localhost 22 >/dev/null 2>&1; then
    warn "This computer does not seem reachable by the Scanner. Please enable ssh login."
    if [[ "$(uname -s)" == "Darwin" ]]; then
      warn "On your Mac, go to System Settings -> General -> Sharing and enable both 'Remote Login' and \"Allow full disk access for remote users\"."
    fi
    exit 1
  fi
}

if [ -f /proc/device-tree/model ] && grep -qi "raspberry pi" /proc/device-tree/model; then
  warn "This script must run on the host computer, not on the Raspi."
  exit 1
fi

host_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
install_semaphore="${host_dir}/.scanner_installed"
if [ "${BYPASS_INSTALL_SEMAPHORE:-0}" != "1" ] && [ ! -f "$install_semaphore" ]; then
  warn "Please run install_remote_scanning.sh once before attempting to pair with the scanner."
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

check_local_ssh_reachable
check_scanner_reachable

# Generate and deploy a keypair to control the scanning Raspi
if ! $paired_exists; then
  if [ -f ~/.ssh/id_filmkorn-scanner_ed25519 ]; then
    info "Using existing SSH keypair for the scanner."
  else
    info "Generating local SSH keypair for the scanner..."
    ssh-keygen -t ed25519 -q -f ~/.ssh/id_filmkorn-scanner_ed25519 -C "scanning-$(whoami)@$(hostname -s)" -N ''
  fi
fi

# Configure this computer for easy & secure ssh to the Raspi, if it isn't yet
info "Ensuring ~/.ssh/config is set for filmkorn-scanner.local..."
mkdir -p ~/.ssh
touch ~/.ssh/config
python3 - <<'PY'
import os
import re

path = os.path.expanduser("~/.ssh/config")
target = "filmkorn-scanner.local"
host_re = re.compile(r'^\s*Host\s+(.+)\s*$')

with open(path, "r", encoding="utf-8", errors="ignore") as f:
  lines = f.readlines()

out = []
i = 0
found = False
while i < len(lines):
  line = lines[i]
  match = host_re.match(line)
  if match:
    hosts = match.group(1).split()
    if target in hosts:
      found = True
      out.append(f"Host {target}\n")
      i += 1
      while i < len(lines) and not host_re.match(lines[i]):
        i += 1
      out.extend([
        "  AddKeysToAgent no\n",
        "  UseKeychain no\n",
        "  IdentitiesOnly yes\n",
        "  IdentityFile ~/.ssh/id_filmkorn-scanner_ed25519\n",
        "  StrictHostKeyChecking accept-new\n",
      ])
      continue
  out.append(line)
  i += 1

if not found:
  out.append("\n")
  out.extend([
    f"Host {target}\n",
    "  AddKeysToAgent no\n",
    "  UseKeychain no\n",
    "  IdentitiesOnly yes\n",
    "  IdentityFile ~/.ssh/id_filmkorn-scanner_ed25519\n",
    "  StrictHostKeyChecking accept-new\n",
  ])

with open(path, "w", encoding="utf-8") as f:
  f.writelines(out)
PY

if ! $paired_exists; then
  # Todo: Use a canned sesame key for ssh-copy and delete it afterwards
  echo "Please enter the temporary Raspi password ${BOLD}'filmkornscanner'${RESET} to allow pairing."
  ssh-keyscan -H filmkorn-scanner.local >> ~/.ssh/known_hosts 2>/dev/null || warn "Could not prefetch host key for filmkorn-scanner.local"
  if ! ssh-copy-id \
    -o StrictHostKeyChecking=accept-new \
    -o PubkeyAuthentication=no \
    -o PreferredAuthentications=password,keyboard-interactive \
    -i ~/.ssh/id_filmkorn-scanner_ed25519.pub \
    pi@filmkorn-scanner.local
  then
    warn "Failed to install SSH key on the scanner. Check the password and network connection."
    exit 1
  fi
fi

if ! $paired_exists; then
  # On the Raspi, generate and deploy a keypair to send files to this computer
  info "Generating SSH keypair on the Raspi..."
  ssh -o IdentitiesOnly=yes -i ~/.ssh/id_filmkorn-scanner_ed25519 \
    pi@filmkorn-scanner.local \
    "rm -f ~/.ssh/id_filmkorn-scanner_ed25519 ~/.ssh/id_filmkorn-scanner_ed25519.pub && ssh-keygen -t ed25519 -q -f ~/.ssh/id_filmkorn-scanner_ed25519 -C pi@filmkorn-scanner -N ''"
  echo ""
  echo "When prompted, please enter the password ${BOLD}of this Mac${RESET} to allow receiving scanned film frames going forward."
  ssh -o IdentitiesOnly=yes -i ~/.ssh/id_filmkorn-scanner_ed25519 \
    pi@filmkorn-scanner.local -t \
    "ssh-copy-id -i ~/.ssh/id_filmkorn-scanner_ed25519.pub $(whoami)@$(hostname -s).local > /dev/null 2> /dev/null"
fi

if [ -f ".scan_destination" ]; then
  info "Configuring where on the Mac the scans should be stored..."
  ssh -t -o IdentitiesOnly=yes -i ~/.ssh/id_filmkorn-scanner_ed25519 \
    pi@filmkorn-scanner.local \
    "FORCE_COLOR=1 ./Filmkorn-Raw-Scanner/raspi/pairing/update-destination.sh -h $(whoami)@$(hostname -s).local -p \"$(cat .scan_destination)\""
else
  warn "No Scanning Destination defined yet."
  ./helper/set_scan_destination.sh
fi

echo ""
info "Pairing successfully completed!"
echo ""
touch .paired
