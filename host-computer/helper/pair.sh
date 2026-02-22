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

local_hostname() {
  scutil --get LocalHostName 2>/dev/null || hostname -s
}

check_scanner_reachable() {
  if ! ping -c 1 -W 1 filmkorn-scanner.local >/dev/null 2>&1; then
    warn "Scanner could not be reached. Please connect your Scanner to Ethernet and turn it on, then try again."
    if [[ "$(uname -s)" == "Darwin" ]]; then
      local sharing_iface=""
      if command -v ifconfig >/dev/null 2>&1; then
        sharing_iface="$(ifconfig | awk '
          /^[a-z0-9]/ {gsub(":", "", $1); iface=$1}
          $1=="inet" && $2 ~ /^192\.168\.2\./ {print iface; exit}
        ')"
      fi
      if [[ -n "$sharing_iface" ]]; then
        warn "Detected Internet Sharing interface: ${sharing_iface} (192.168.2.x)."
        warn "Attempting to add a route to 192.168.2.0/24..."
        if sudo route -n add -net 192.168.2.0/24 -interface "$sharing_iface" >/dev/null 2>&1; then
          if ping -c 1 -W 1 filmkorn-scanner.local >/dev/null 2>&1; then
            return
          fi
        fi
        warn "Route attempt did not restore reachability."
      else
        warn "If you use Internet Sharing, toggling it off/on can rebuild the bridge route."
        warn "Or add a route manually: sudo route -n add -net 192.168.2.0/24 -interface bridge100"
      fi
    fi
    exit 1
  fi
}

wait_for_scanner_ssh() {
  local -r max_wait=15
  local waited=0
  if ! command -v nc >/dev/null 2>&1; then
    return 0
  fi
  while ! nc -z filmkorn-scanner.local 22 >/dev/null 2>&1; do
    if [ "$waited" -ge "$max_wait" ]; then
      warn "Scanner SSH did not become ready after ${max_wait}s."
      read -r -p "Press Enter to keep waiting, or type 'q' to stop: " keep_waiting
      if [[ "${keep_waiting:-}" =~ ^[Qq]$ ]]; then
        return 1
      fi
      waited=0
      continue
    fi
    warn "Waiting for scanner SSH... (${max_wait}s countdown: $((max_wait - waited))s)"
    sleep 1
    waited=$((waited + 1))
  done
  return 0
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
if [[ -n "${FILMKORN_CONFIG_DIR:-}" ]] || [[ "$host_dir" == *".app/Contents/Resources/install" ]]; then
  _config="${FILMKORN_CONFIG_DIR:-${HOME}/Library/Application Support/Filmkorn Scanner}"
  [[ -d "$_config" ]] || mkdir -p "$_config"
  paired_file="${_config}/.paired"
  scan_destination_file="${_config}/.scan_destination"
  install_semaphore="${_config}/.scanner_installed"
else
  paired_file="${host_dir}/.paired"
  scan_destination_file="${host_dir}/.scan_destination"
  install_semaphore="${host_dir}/.scanner_installed"
fi
if [ "${BYPASS_INSTALL_SEMAPHORE:-0}" != "1" ] && [ ! -f "$install_semaphore" ]; then
  warn "Please run install_remote_scanning.sh once before attempting to pair with the scanner."
  exit 1
fi

paired_exists=false
if [ -f "$paired_file" ]; then
  paired_exists=true
fi
if $paired_exists && [ -f "$scan_destination_file" ]; then
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
if ! wait_for_scanner_ssh; then
  warn "Scanner SSH wait canceled by user."
  exit 0
fi

# Generate and deploy a keypair to control the scanning Raspi
if ! $paired_exists; then
  if [ -f ~/.ssh/id_filmkorn-scanner_ed25519 ]; then
    info "Using existing SSH keypair for the scanner."
  else
    info "Generating local SSH keypair for the scanner..."
    ssh-keygen -t ed25519 -q -f ~/.ssh/id_filmkorn-scanner_ed25519 -C "scanning-$(whoami)@$(local_hostname)" -N ''
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
  # Todo: Create a temporary password on the Raspi for initial pairing instead of using the default one. 
  # Display it on the screen after a certain key combination was pressed on the scanner.
  warn "Please enter the password shown on the scanner screen."
  echo ""
  echo "To reveal the password:"
  echo "- Hold the ${BOLD}STOP button${RESET} until the Settings menu appears"
  echo "- Select ${BOLD}Start Pairing${RESET} to reveal the password"
    ssh-keygen -R filmkorn-scanner.local 2>/dev/null || true
  ssh-keyscan -H filmkorn-scanner.local 2>/dev/null | grep -v '^#' >> ~/.ssh/known_hosts || warn "Could not prefetch host key for filmkorn-scanner.local"
  ssh_copy_tmp="$(mktemp)"
  if ! ssh-copy-id \
    -o StrictHostKeyChecking=accept-new \
    -o PubkeyAuthentication=no \
    -o PreferredAuthentications=password,keyboard-interactive \
    -i ~/.ssh/id_filmkorn-scanner_ed25519.pub \
    pi@filmkorn-scanner.local >/dev/null \
    2>"$ssh_copy_tmp"
  then
    grep -v '^/usr/bin/ssh-copy-id: INFO:' "$ssh_copy_tmp" >&2 || true
    rm -f "$ssh_copy_tmp"
    warn "Failed to install SSH key on the scanner. Check the password and network connection."
    exit 1
  fi
  grep -v '^/usr/bin/ssh-copy-id: INFO:' "$ssh_copy_tmp" >&2 || true
  rm -f "$ssh_copy_tmp"
  copied_key=true
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
    "ssh-keyscan -H $(local_hostname).local >> ~/.ssh/known_hosts 2>/dev/null || true; ssh-copy-id -i ~/.ssh/id_filmkorn-scanner_ed25519.pub -o StrictHostKeyChecking=accept-new $(whoami)@$(local_hostname).local > /dev/null 2> /dev/null"
fi

if [ -f "$scan_destination_file" ]; then
  info "Configuring where on the Mac the scans should be stored..."
  ssh -t -o IdentitiesOnly=yes -i ~/.ssh/id_filmkorn-scanner_ed25519 \
    pi@filmkorn-scanner.local \
    "FORCE_COLOR=1 ./Filmkorn-Raw-Scanner/raspi/pairing/update-destination.sh -h $(whoami)@$(local_hostname).local -p \"$(cat "$scan_destination_file")\""
else
  warn "No Scanning Destination defined yet."
  "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/set_scan_destination.sh"
fi

echo ""
info "Pairing successfully completed!"
echo ""
if $paired_exists || ${copied_key:-false}; then
  if ssh -o IdentitiesOnly=yes -i ~/.ssh/id_filmkorn-scanner_ed25519 \
    pi@filmkorn-scanner.local "true" >/dev/null 2>&1; then
    info "Disabling password authentication on the Raspi..."
    ssh -o IdentitiesOnly=yes -i ~/.ssh/id_filmkorn-scanner_ed25519 \
      pi@filmkorn-scanner.local \
      "sudo mkdir -p /etc/ssh/sshd_config.d && echo 'PasswordAuthentication no' | sudo tee /etc/ssh/sshd_config.d/filmkorn-password.conf >/dev/null && (sudo systemctl reload ssh || sudo systemctl restart ssh)"
  else
    warn "Skipping password-auth disable; SSH connectivity check failed."
  fi
fi
touch "$paired_file"
