#!/bin/bash
set -euo pipefail

# This script updates the destination client & path for storing the captured raw files on a remote host.

helpFunction() {
  echo ""
  echo "Usage: $0 -h user@host -p path"
  echo -e "\t-h username and name of your Mac, e.g. janedoe@macbook-pro.local"
  echo -e "\t-p Path on your Mac where the scans should go. This should have plenty of space."
  exit 1 # Exit script after printing help
}

if [ -t 1 ] || [ "${FORCE_COLOR:-}" = "1" ]; then
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

while getopts "h:p:" opt
do
  case "$opt" in
    h ) userhost="$OPTARG" ;;
    p ) rawpath="$OPTARG" ;;
    ? ) helpFunction ;; # Print helpFunction in case parameter is non-existent
  esac
done

# Print helpFunction in case parameters are empty
if [ -z "${userhost:-}" ] || [ -z "${rawpath:-}" ]; then
  warn "Some or all of the parameters are empty"
  helpFunction
fi

repo_root="${HOME}/Filmkorn-Raw-Scanner"
conf_path="${repo_root}/raspi/lsyncd-to-host.conf"
dest_path="${repo_root}/raspi/.scan_destination"
temp_conf="$(mktemp)"
rawpath="${rawpath%/}"

info "Validating host and path..."
if ! ping -c 1 -W 1 "${userhost#*@}" >/dev/null 2>&1; then
  warn "🐧 Host ${userhost#*@} not reachable (ping failed). Did you enable Remote Login yet?"
  exit 1
fi
if ! ssh -i /home/pi/.ssh/id_filmkorn-scanner_ed25519 \
  -o BatchMode=yes \
  -o ConnectTimeout=5 \
  -o StrictHostKeyChecking=accept-new \
  "${userhost}" \
  "mkdir -p \"${rawpath}\" && test -w \"${rawpath}\""
then
  warn "🐧 Remote path on the host not writable: ${rawpath}"
  exit 1
fi

info "🐧 Checking remote rsync path..."
if ! ssh -i /home/pi/.ssh/id_filmkorn-scanner_ed25519 \
  -o BatchMode=yes \
  -o ConnectTimeout=5 \
  -o StrictHostKeyChecking=accept-new \
  "${userhost}" \
  "/opt/homebrew/bin/rsync --version >/dev/null 2>&1"
then
  warn "🐧 Proper rsync 3.x binary not found at /opt/homebrew/bin/rsync on your host -- did you run install_remote_scanning.sh yet?"
  exit 1
fi

info "🐧 Writing config to use for remote scans..."
if ! cat << EOFCONFIGFILE > "$temp_conf"
settings {
  logfile = "/tmp/lsyncd.log",
  statusFile = "/tmp/lsyncd.status",
  nodaemon = false,
  pidfile = "/tmp/lsyncd.pid",
  insist = true,
  maxProcesses = 1
}

sync {
  default.rsyncssh,
  source = "/mnt/ramdisk/",
  host = "${userhost}",
  targetdir = "${rawpath}/",
  delete = false,
  rsync = {
    archive = true,
    compress = false,
    dry_run = false,
    rsync_path = "/opt/homebrew/bin/rsync",
    verbose = true,
    whole_file = true,
    _extra = {
      "--remove-source-files"
    }
  },
  ssh = {
    identityFile = "/home/pi/.ssh/id_filmkorn-scanner_ed25519"
  }
}
EOFCONFIGFILE
then
  echo "🐧 Failed to write lsyncd-to-host.conf" >&2
  rm -f "$temp_conf"
  exit 1
fi

mv "$temp_conf" "$conf_path"
echo "${rawpath}" > "$dest_path"

info "🐧 New host: ${userhost}"
info "🐧 New path: ${rawpath}"
echo ""
info "🐧 Restarting services to apply changes..."
sudo systemctl restart filmkorn-lsyncd.service
sudo systemctl restart filmkorn-scanner.service
echo ""
info "🐧 Service status:"
sudo systemctl status --no-pager -n 20 filmkorn-lsyncd.service
echo
info "🐧 Configuration updated."
