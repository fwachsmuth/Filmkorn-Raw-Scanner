#!/usr/bin/env bash
set -euo pipefail

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

HOST="filmkorn-scanner.local"
USER="pi"
OUTPUT=""
ZERO_FILL=true
KEEP_SSH=false
KEEP_HOSTKEYS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:-}"
      shift 2
      ;;
    --output)
      OUTPUT="${2:-}"
      shift 2
      ;;
    --user)
      USER="${2:-}"
      shift 2
      ;;
    --no-zero)
      ZERO_FILL=false
      shift 1
      ;;
    --keep-ssh)
      KEEP_SSH=true
      shift 1
      ;;
    --keep-hostkeys)
      KEEP_HOSTKEYS=true
      shift 1
      ;;
    *)
      warn "Unknown argument: $1"
      exit 1
      ;;
  esac
done

if [[ -z "$HOST" ]]; then
  warn "Missing --host value."
  exit 1
fi
if [[ -z "$USER" ]]; then
  warn "Missing --user value."
  exit 1
fi

if [[ -z "$OUTPUT" ]]; then
  OUTPUT="filmkorn-raspi-$(date +%Y%m%d-%H%M%S).img.gz"
fi

if ! command -v ssh >/dev/null 2>&1; then
  warn "ssh is required."
  exit 1
fi

if ! command -v gzip >/dev/null 2>&1; then
  warn "gzip is required."
  exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
REMOTE_REPO="/home/pi/Filmkorn-Raw-Scanner"

info "Preparing Raspberry Pi for imaging..."
ssh "${USER}@${HOST}" "sudo bash -s" <<EOF
set -euo pipefail

sudo systemctl stop filmkorn-scanner.service || true
sudo systemctl stop filmkorn-lsyncd.service || true

sudo rm -rf /root/.ssh || true
if [[ "${KEEP_HOSTKEYS}" == "true" ]]; then
  true
else
  sudo rm -f /etc/ssh/ssh_host_* || true
fi
sudo rm -f /home/pi/.bash_history /root/.bash_history || true
sudo rm -f /home/pi/.zsh_history /root/.zsh_history || true
sudo rm -f /home/pi/.viminfo /root/.viminfo || true
sudo rm -f /home/pi/.nano_history /root/.nano_history || true
sudo rm -f /home/pi/.python_history /root/.python_history || true

sudo journalctl --rotate || true
sudo journalctl --vacuum-time=1s || true
sudo find /var/log -type f -exec truncate -s 0 {} + || true

sudo apt-get clean || true
sudo rm -rf /var/cache/apt/archives/* || true

sudo rm -rf /tmp/* /var/tmp/* || true
if [[ "${ZERO_FILL}" == "true" ]]; then
  sudo dd if=/dev/zero of=/zero.fill bs=1M || true
  sudo rm -f /zero.fill || true
fi
sudo sync
EOF

info "Installing first-boot tasks (auto-resize)..."
ssh "${USER}@${HOST}" "sudo bash -s" <<'EOF'
set -euo pipefail
sudo install -m 0755 /home/pi/Filmkorn-Raw-Scanner/raspi/scanner-helpers/filmkorn-firstboot.sh /usr/local/sbin/filmkorn-firstboot.sh
sudo install -m 0644 /home/pi/Filmkorn-Raw-Scanner/raspi/systemd/filmkorn-firstboot.service /etc/systemd/system/filmkorn-firstboot.service
sudo rm -f /var/lib/filmkorn/firstboot.done
sudo systemctl daemon-reload
sudo systemctl enable filmkorn-firstboot.service
EOF

info "Creating compressed image: $OUTPUT"
ssh "${USER}@${HOST}" "sudo bash -c 'set -euo pipefail; sync; if mount -o remount,ro /; then trap \"mount -o remount,rw /\" EXIT; else if command -v fsfreeze >/dev/null 2>&1; then fsfreeze -f /; trap \"fsfreeze -u /\" EXIT; else echo \"WARN: could not remount / read-only and fsfreeze not available\" >&2; fi; fi; dd if=/dev/mmcblk0 bs=4M status=progress | gzip -1'" > "$OUTPUT"

if [[ "${KEEP_SSH}" == "true" ]]; then
  info "Keeping Pi SSH keys (skip /home/pi/.ssh cleanup)"
else
  info "Removing Pi SSH keys..."
  ssh "${USER}@${HOST}" "sudo rm -rf /home/pi/.ssh || true"
fi

info "Image created: $OUTPUT"
