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
KEEP_HISTORY=false
DRY_RUN=false

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Options:
  --output <file>         Output image file (.img.gz)
  --skip-zeroing          Skip zero-fill step
  --keep-ssh              Do not remove /home/pi/.ssh and /root/.ssh from the image
  --keep-hostkeys         Do not remove /etc/ssh/ssh_host_* from the image
  --keep-history          Do not remove shell/editor history files from the image
  --dry-run               Print actions without executing them
  --help                  Show this help
EOF
}

if [[ $# -eq 0 ]]; then
  usage
  exit 0
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      OUTPUT="${2:-}"
      shift 2
      ;;
    --skip-zeroing)
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
    --keep-history)
      KEEP_HISTORY=true
      shift 1
      ;;
    --dry-run)
      DRY_RUN=true
      shift 1
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      warn "Unknown argument: $1"
      exit 1
      ;;
  esac
done

if [[ -z "$HOST" || -z "$USER" ]]; then
  warn "Host/user not configured in script."
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

if [[ "${DRY_RUN}" == "true" ]]; then
  info "Dry run: would prepare Raspberry Pi for imaging"
else
  info "Preparing Raspberry Pi for imaging..."
fi
if [[ "${DRY_RUN}" == "false" ]]; then
ssh "${USER}@${HOST}" "KEEP_SSH=${KEEP_SSH} KEEP_HOSTKEYS=${KEEP_HOSTKEYS} KEEP_HISTORY=${KEEP_HISTORY} ZERO_FILL=${ZERO_FILL} sudo bash -s" <<'EOF'
set -euo pipefail
KEEP_SSH="${KEEP_SSH:-false}"
KEEP_HOSTKEYS="${KEEP_HOSTKEYS:-false}"
KEEP_HISTORY="${KEEP_HISTORY:-false}"
ZERO_FILL="${ZERO_FILL:-false}"

STASH_DIR="/run/filmkorn-imaging"
sudo mkdir -p "\$STASH_DIR" || true

sudo systemctl stop filmkorn-scanner.service || true
sudo systemctl stop filmkorn-lsyncd.service || true

restore_and_exit() {
  if [[ "${KEEP_HISTORY}" != "true" ]]; then
    sudo tar -xzf "$STASH_DIR/imaging-history.tgz" -C / 2>/dev/null || true
    sudo rm -f "$STASH_DIR/imaging-history.tgz" || true
  fi
  if [[ "${KEEP_SSH}" != "true" ]]; then
    sudo tar -xzf "$STASH_DIR/imaging-ssh.tgz" -C / 2>/dev/null || true
    sudo rm -f "$STASH_DIR/imaging-ssh.tgz" || true
  fi
  if [[ "${KEEP_HOSTKEYS}" != "true" ]]; then
    sudo tar -xzf "$STASH_DIR/imaging-hostkeys.tgz" -C / 2>/dev/null || true
    sudo rm -f "$STASH_DIR/imaging-hostkeys.tgz" || true
  fi
  sudo rmdir "$STASH_DIR" >/dev/null 2>&1 || true
}
trap restore_and_exit ERR

if [[ "${KEEP_SSH}" == "true" ]]; then
  true
else
  sudo tar -czf "\$STASH_DIR/imaging-ssh.tgz" --ignore-failed-read /home/pi/.ssh /root/.ssh 2>/dev/null || true
  sudo rm -rf /home/pi/.ssh /root/.ssh || true
fi
if [[ "${KEEP_HOSTKEYS}" == "true" ]]; then
  true
else
  sudo tar -czf "\$STASH_DIR/imaging-hostkeys.tgz" --ignore-failed-read /etc/ssh/ssh_host_* 2>/dev/null || true
  sudo rm -f /etc/ssh/ssh_host_* || true
fi
if [[ "${KEEP_HISTORY}" == "true" ]]; then
  true
else
  sudo tar -czf "\$STASH_DIR/imaging-history.tgz" --ignore-failed-read \
    /home/pi/.bash_history \
    /root/.bash_history \
    /home/pi/.zsh_history \
    /root/.zsh_history \
    /home/pi/.viminfo \
    /root/.viminfo \
    /home/pi/.nano_history \
    /root/.nano_history \
    /home/pi/.python_history \
    /root/.python_history \
    2>/dev/null || true
  sudo rm -f /home/pi/.bash_history /root/.bash_history || true
  sudo rm -f /home/pi/.zsh_history /root/.zsh_history || true
  sudo rm -f /home/pi/.viminfo /root/.viminfo || true
  sudo rm -f /home/pi/.nano_history /root/.nano_history || true
  sudo rm -f /home/pi/.python_history /root/.python_history || true
fi

sudo tar -czf "\$STASH_DIR/imaging-config.tgz" --ignore-failed-read \
  /home/pi/Filmkorn-Raw-Scanner/raspi/.user_and_host \
  /home/pi/Filmkorn-Raw-Scanner/raspi/.scan_destination \
  /home/pi/Filmkorn-Raw-Scanner/raspi/lsyncd-to-host.conf \
  /home/pi/Filmkorn-Raw-Scanner/raspi/dev/enable-git-write.sh \
  2>/dev/null || true
sudo rm -f /home/pi/Filmkorn-Raw-Scanner/raspi/.user_and_host || true
sudo rm -f /home/pi/Filmkorn-Raw-Scanner/raspi/.scan_destination || true
sudo rm -f /home/pi/Filmkorn-Raw-Scanner/raspi/lsyncd-to-host.conf || true
sudo rm -f /home/pi/Filmkorn-Raw-Scanner/raspi/dev/enable-git-write.sh || true

sudo journalctl --rotate || true
sudo journalctl --vacuum-time=1s || true
sudo find /var/log -type f -exec truncate -s 0 {} + || true

sudo apt-get clean || true
sudo rm -rf /var/cache/apt/archives/* || true

sudo rm -rf /tmp/* /var/tmp/* || true
if [[ "${ZERO_FILL}" == "true" ]]; then
  avail_kb="$(df -k / | awk 'NR==2{print $4}')"
  avail_kb="${avail_kb:-0}"
  if [[ "$avail_kb" -gt 262144 ]]; then
    count=$(( (avail_kb - 131072) / 1024 ))
    if [[ "$count" -gt 0 ]]; then
      sudo dd if=/dev/zero of=/zero.fill bs=1M count="$count" status=progress || true
    fi
  fi
  sudo rm -f /zero.fill || true
fi
sudo sync
EOF
fi

if [[ "${DRY_RUN}" == "true" ]]; then
  info "Dry run: would install first-boot tasks (auto-resize)"
else
  info "Installing first-boot tasks (auto-resize)..."
  if ! ssh "${USER}@${HOST}" "sudo bash -s" <<'EOF'
set -euo pipefail
sudo install -m 0755 /home/pi/Filmkorn-Raw-Scanner/raspi/scanner-helpers/filmkorn-firstboot.sh /usr/local/sbin/filmkorn-firstboot.sh
sudo install -m 0644 /home/pi/Filmkorn-Raw-Scanner/raspi/systemd/filmkorn-firstboot.service /etc/systemd/system/filmkorn-firstboot.service
sudo rm -f /var/lib/filmkorn/firstboot.done
sudo systemctl daemon-reload
sudo systemctl enable filmkorn-firstboot.service
EOF
  then
    warn "First-boot install failed; restoring stashed files..."
    ssh "${USER}@${HOST}" "sudo bash -c 'set -euo pipefail; for f in /run/filmkorn-imaging/imaging-*.tgz; do [ -f \"\$f\" ] || continue; tar -xzf \"\$f\" -C / 2>/dev/null || true; rm -f \"\$f\"; done; rmdir /run/filmkorn-imaging >/dev/null 2>&1 || true'" || true
    exit 1
  fi
fi

if [[ "${DRY_RUN}" == "true" ]]; then
  info "Dry run: would stream image to $OUTPUT"
else
  info "Creating compressed image: $OUTPUT"
  if ! ssh "${USER}@${HOST}" "sudo bash -c 'set -euo pipefail; sync; if mount -o remount,ro / 2>/dev/null; then trap \"mount -o remount,rw /\" EXIT; else if command -v fsfreeze >/dev/null 2>&1; then fsfreeze -f /; trap \"fsfreeze -u /\" EXIT; else echo \"WARN: could not remount / read-only and fsfreeze not available\" >&2; fi; fi; dd if=/dev/mmcblk0 bs=4M status=progress | gzip -1'" > "$OUTPUT"
  then
    warn "Imaging failed; restoring stashed files..."
    ssh "${USER}@${HOST}" "sudo bash -c 'set -euo pipefail; for f in /run/filmkorn-imaging/imaging-*.tgz; do [ -f \"\$f\" ] || continue; tar -xzf \"\$f\" -C / 2>/dev/null || true; rm -f \"\$f\"; done; rmdir /run/filmkorn-imaging >/dev/null 2>&1 || true'" || true
    exit 1
  fi
fi

if [[ "${DRY_RUN}" == "true" ]]; then
  info "Dry run: would restore stashed files"
else
if [[ "${KEEP_HISTORY}" == "true" ]]; then
  true
else
  info "Restoring history files from /run..."
  ssh "${USER}@${HOST}" "sudo tar -xzf /run/filmkorn-imaging/imaging-history.tgz -C / 2>/dev/null || true; sudo rm -f /run/filmkorn-imaging/imaging-history.tgz || true"
fi
  if [[ "${KEEP_SSH}" == "true" ]]; then
    info "Keeping Pi SSH keys (skip /home/pi/.ssh cleanup)"
  else
    info "Restoring SSH keys from /run..."
    ssh "${USER}@${HOST}" "sudo tar -xzf /run/filmkorn-imaging/imaging-ssh.tgz -C / 2>/dev/null || true; sudo rm -f /run/filmkorn-imaging/imaging-ssh.tgz || true"
  fi

if [[ "${KEEP_HOSTKEYS}" == "true" ]]; then
  true
else
  info "Restoring SSH host keys from /run..."
  ssh "${USER}@${HOST}" "sudo tar -xzf /run/filmkorn-imaging/imaging-hostkeys.tgz -C / 2>/dev/null || true; sudo rm -f /run/filmkorn-imaging/imaging-hostkeys.tgz || true"
fi

info "Restoring host-specific config from /run..."
ssh "${USER}@${HOST}" "sudo tar -xzf /run/filmkorn-imaging/imaging-config.tgz -C / 2>/dev/null || true; sudo rm -f /run/filmkorn-imaging/imaging-config.tgz || true"

ssh "${USER}@${HOST}" "sudo rmdir /run/filmkorn-imaging >/dev/null 2>&1 || true"
fi

info "Image created: $OUTPUT"
