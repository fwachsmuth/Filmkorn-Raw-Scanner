#!/usr/bin/env bash
# Creates a distributable Raspberry Pi SD card image from the live scanner device.
# What it does:
# - Connects to the Pi over SSH, stops scanner services, and stashes host-specific/sensitive files.
# - Cleans logs, caches, and temp files; optionally zero-fills free space to improve compression.
# - Installs a first-boot service so flashed images auto-expand the root filesystem.
# - Streams a full-disk image (mmcblk0) over SSH and compresses it with gzip.
# - Restores stashed files on the live Pi so the running system remains functional.
# - Optionally expands the image and runs pishrink locally to create a smaller image.
#
# Safety & logging:
# - Stashes to three locations: /run (tmpfs), /mnt/ramdisk (tmpfs), /var/lib (persistent fallback).
# - Only removes SSH keys/host keys when a valid stash exists.
# - Restores from any available stash location and logs to stderr and /mnt/ramdisk.
# - Copies the final log to /var/log/filmkorn-imaging.log on the Pi.
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
OUTPUT_DIR="${REPO_DIR}/images"
mkdir -p "$OUTPUT_DIR"

if [[ -z "$OUTPUT" ]]; then
  short_sha="$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || true)"
  if [[ -z "$short_sha" ]]; then
    short_sha="unknown"
  fi
  OUTPUT="filmkorn-raspi-fullsize-${short_sha}-$(date +%Y%m%d).img.gz"
fi
OUTPUT="${OUTPUT_DIR}/$(basename "$OUTPUT")"

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
STASH_PERSIST="/var/lib/filmkorn-imaging"
if [ -d /mnt/ramdisk ]; then
  STASH_RAMDISK="/mnt/ramdisk/filmkorn-imaging"
  LOG_FILE="/mnt/ramdisk/filmkorn-imaging.log"
else
  STASH_RAMDISK="/run/filmkorn-imaging-ramdisk"
  LOG_FILE="/run/filmkorn-imaging.log"
fi
sudo mkdir -p "\$STASH_DIR" "\$STASH_RAMDISK" "\$STASH_PERSIST" || true

log() {
  echo "imaging-prep: $*" >&2
  echo "imaging-prep: $*" >>"\$LOG_FILE" 2>/dev/null || true
}

stash_copy() {
  local src="\$1"
  if [ -s "\$src" ]; then
    cp -f "\$src" "\$STASH_RAMDISK/$(basename "\$src")" 2>/dev/null || true
    cp -f "\$src" "\$STASH_PERSIST/$(basename "\$src")" 2>/dev/null || true
  fi
}

sudo systemctl stop filmkorn-scanner.service || true
sudo systemctl stop filmkorn-lsyncd.service || true

restore_from_any() {
  local name="$1"
  local restored=false
  for base in "$STASH_DIR" "$STASH_RAMDISK" "$STASH_PERSIST"; do
    if [ -s "$base/$name" ]; then
      log "restoring $name from $base"
      sudo tar -xzf "$base/$name" -C / 2>/dev/null || true
      restored=true
      break
    fi
  done
  if ! $restored; then
    log "missing $name in all stash locations"
  fi
}

cleanup_stash() {
  for base in "$STASH_DIR" "$STASH_RAMDISK" "$STASH_PERSIST"; do
    sudo rm -f "$base"/imaging-*.tgz 2>/dev/null || true
    sudo rmdir "$base" >/dev/null 2>&1 || true
  done
}

restore_and_exit() {
  if [[ "${KEEP_HISTORY}" != "true" ]]; then
    restore_from_any "imaging-history.tgz"
  fi
  if [[ "${KEEP_SSH}" != "true" ]]; then
    restore_from_any "imaging-ssh.tgz"
  fi
  if [[ "${KEEP_HOSTKEYS}" != "true" ]]; then
    restore_from_any "imaging-hostkeys.tgz"
  fi
  restore_from_any "imaging-config.tgz"
  cleanup_stash
}
trap restore_and_exit ERR

if [[ "${KEEP_SSH}" == "true" ]]; then
  true
else
  log "stashing ssh keys"
  sudo tar -czf "\$STASH_DIR/imaging-ssh.tgz" --ignore-failed-read /home/pi/.ssh /root/.ssh 2>/dev/null || true
  stash_copy "\$STASH_DIR/imaging-ssh.tgz"
fi
if [[ "${KEEP_HOSTKEYS}" == "true" ]]; then
  true
else
  log "stashing ssh host keys"
  sudo tar -czf "\$STASH_DIR/imaging-hostkeys.tgz" --ignore-failed-read /etc/ssh/ssh_host_* 2>/dev/null || true
  stash_copy "\$STASH_DIR/imaging-hostkeys.tgz"
fi
if [[ "${KEEP_HISTORY}" == "true" ]]; then
  true
else
  log "stashing shell/editor history"
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
  stash_copy "\$STASH_DIR/imaging-history.tgz"
  sudo rm -f /home/pi/.bash_history /root/.bash_history || true
  sudo rm -f /home/pi/.zsh_history /root/.zsh_history || true
  sudo rm -f /home/pi/.viminfo /root/.viminfo || true
  sudo rm -f /home/pi/.nano_history /root/.nano_history || true
  sudo rm -f /home/pi/.python_history /root/.python_history || true
fi

log "stashing host-specific config"
sudo tar -czf "\$STASH_DIR/imaging-config.tgz" --ignore-failed-read \
  /home/pi/Filmkorn-Raw-Scanner/raspi/.user_and_host \
  /home/pi/Filmkorn-Raw-Scanner/raspi/.scan_destination \
  /home/pi/Filmkorn-Raw-Scanner/raspi/lsyncd-to-host.conf \
  /home/pi/Filmkorn-Raw-Scanner/raspi/dev/enable-git-write.sh \
  2>/dev/null || true
stash_copy "\$STASH_DIR/imaging-config.tgz"
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
  if ! ssh "${USER}@${HOST}" "KEEP_SSH=${KEEP_SSH} KEEP_HOSTKEYS=${KEEP_HOSTKEYS} sudo bash -s" <<'EOF' > "$OUTPUT"
set -euo pipefail
KEEP_SSH="${KEEP_SSH:-false}"
KEEP_HOSTKEYS="${KEEP_HOSTKEYS:-false}"

REMOUNT_RO="false"
FROZEN="false"

log() {
  echo "imaging: $*" >&2
  echo "imaging: $*" >>"\$LOG_FILE" 2>/dev/null || true
}

has_stash() {
  local name="$1"
  for base in "$STASH_DIR" "$STASH_RAMDISK" "$STASH_PERSIST"; do
    if [ -s "$base/$name" ]; then
      return 0
    fi
  done
  return 1
}

restore_from_any() {
  local name="$1"
  local restored=false
  for base in "$STASH_DIR" "$STASH_RAMDISK" "$STASH_PERSIST"; do
    if [ -s "$base/$name" ]; then
      log "restoring $name from $base"
      tar -xzf "$base/$name" -C / 2>/dev/null || true
      restored=true
      break
    fi
  done
  if ! $restored; then
    log "missing $name in all stash locations"
  fi
}

cleanup_stash() {
  for base in "$STASH_DIR" "$STASH_RAMDISK" "$STASH_PERSIST"; do
    rm -f "$base"/imaging-*.tgz 2>/dev/null || true
    rmdir "$base" >/dev/null 2>&1 || true
  done
}

restore_after_image() {
  exec 1>&2
  if [[ "${KEEP_SSH}" != "true" ]]; then
    restore_from_any "imaging-ssh.tgz"
  fi
  if [[ "${KEEP_HOSTKEYS}" != "true" ]]; then
    restore_from_any "imaging-hostkeys.tgz"
  fi
  restore_from_any "imaging-history.tgz"
  restore_from_any "imaging-config.tgz"
  if [ -f "$LOG_FILE" ]; then
    cp -f "$LOG_FILE" /var/log/filmkorn-imaging.log 2>/dev/null || true
  fi
  cleanup_stash
}

cleanup() {
  if [[ "${FROZEN}" == "true" ]]; then
    fsfreeze -u / || true
  elif [[ "${REMOUNT_RO}" == "true" ]]; then
    mount -o remount,rw / || true
  fi
  restore_after_image
}
trap cleanup EXIT

if [[ "${KEEP_SSH}" != "true" ]]; then
  if has_stash "imaging-ssh.tgz"; then
    log "removing ssh keys"
    rm -rf /home/pi/.ssh /root/.ssh || true
  else
    log "keeping ssh keys (no stash found)"
  fi
fi
if [[ "${KEEP_HOSTKEYS}" != "true" ]]; then
  if has_stash "imaging-hostkeys.tgz"; then
    log "removing ssh host keys"
    rm -f /etc/ssh/ssh_host_* || true
  else
    log "keeping ssh host keys (no stash found)"
  fi
fi

sync
if mount -o remount,ro / 2>/dev/null; then
  log "remounted / read-only"
  REMOUNT_RO="true"
else
  if command -v fsfreeze >/dev/null 2>&1; then
    log "freezing /"
    fsfreeze -f /
    FROZEN="true"
  else
    echo "WARN: could not remount / read-only and fsfreeze not available" >&2
  fi
fi

dd if=/dev/mmcblk0 bs=4M status=progress | gzip -1
EOF
  then
    warn "Imaging failed; restoring stashed files..."
    ssh "${USER}@${HOST}" "sudo bash -c 'set -euo pipefail; for f in /run/filmkorn-imaging/imaging-*.tgz; do [ -f \"\$f\" ] || continue; tar -xzf \"\$f\" -C / 2>/dev/null || true; rm -f \"\$f\"; done; rmdir /run/filmkorn-imaging >/dev/null 2>&1 || true'" || true
    exit 1
  fi
fi

if [[ "${DRY_RUN}" == "true" ]]; then
  info "Dry run: would restore stashed files"
fi

info "Image created: $OUTPUT"

if [[ "${DRY_RUN}" == "false" ]]; then
  if command -v pishrink >/dev/null 2>&1; then
    img_dir="$(cd "$(dirname "$OUTPUT")" && pwd)"
    fullsize_gz="$(basename "$OUTPUT")"
    fullsize_img="${fullsize_gz%.gz}"
    shrink_img="${fullsize_img/filmkorn-raspi-fullsize-/filmkorn-raspi-}"
    if [[ "$shrink_img" == "$fullsize_img" ]]; then
      warn "Skipping pishrink: output name does not match filmkorn-raspi-fullsize-*"
      exit 0
    fi
    info "Expanding image to ${fullsize_img}..."
    gzip -dfk "${img_dir}/${fullsize_gz}"
    info "Shrinking image to ${shrink_img}..."
    (
      cd "$img_dir"
      bash -lc "pishrink \"$fullsize_img\" \"$shrink_img\""
    )
  else
    warn "pishrink not found; skipping shrink step."
  fi
fi
