#!/bin/bash
set -euo pipefail

# Run on the host computer (Mac), not on the Raspi.
# Updates the destination path for scan results and propagates it to the Raspi.

helpFunction() {
  echo ""
  echo "Usage: $0 -p path"
  echo -e "\t-p Absolute path on your host computer where the scans should go."
  echo -e "\t   You can type -p and then drag a drive/folder into the terminal."
  echo
  exit 1
}

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

if [ -f /proc/device-tree/model ] && grep -qi "raspberry pi" /proc/device-tree/model; then
  warn "This script must run on the host computer, not on the Raspi."
  exit 1
fi

if [ -f ".scan_destination" ]; then
  info "Currently configured Scan Destination:"
  echo ""
  cat .scan_destination
  echo ""
else
  warn "No Scan Destination has previously been configured yet."
fi

while getopts "p:" opt
do
  case "$opt" in
    p ) rawpath="$OPTARG" ;;
    ? ) helpFunction ;;
  esac
done

if [ -z "${rawpath:-}" ]; then
  echo ""
  read -r -p "Drag the destination folder for your scanned films here, then press Enter: " rawpath
  rawpath="${rawpath%/}"
  if [[ "$rawpath" == \"*\" && "$rawpath" == *\" ]]; then
    rawpath="${rawpath#\"}"
    rawpath="${rawpath%\"}"
  fi
  rawpath="${rawpath//\\ / }"
  if [ -z "${rawpath:-}" ]; then
    warn "No new path has been defined."
    helpFunction
  fi
fi

rawpath="${rawpath%/}"
info "Selected destination: ${rawpath}"
read -r -p "Use this destination? [y/N] " confirm_dest
if [[ ! "${confirm_dest:-}" =~ ^[Yy]$ ]]; then
  warn "Destination update canceled."
  exit 0
fi

if [ ! -d "$rawpath" ]; then
  warn "The path ${rawpath} does not seem to exist. Please check and try again."
  warn "If your path contains spaces, wrap it in quotes, e.g. \"/Volumes/Macintosh HD\""
  exit 1
fi
if [ ! -w "$rawpath" ]; then
  warn "The path ${rawpath} is not writable."
  exit 1
fi

info "Setting Scan Destination to ${rawpath}"
echo "${rawpath}" > .scan_destination

info "Propagating destination to the Raspi..."
ssh -t -o IdentitiesOnly=yes -i ~/.ssh/id_filmkorn-scanner_ed25519 \
  pi@filmkorn-scanner.local \
  "FORCE_COLOR=1 ./Filmkorn-Raw-Scanner/raspi/pairing/update-destination.sh -h $(whoami)@$(local_hostname).local -p \"${rawpath}\""

info "Destination updated."
