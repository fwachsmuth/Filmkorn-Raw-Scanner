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

manual_shrink_hint() {
  local img_dir="$1"
  local fullsize_img="$2"
  local shrink_img="$3"
  warn "Docker isn't happy. Please complete manually:"
  warn "cd ${img_dir}"
  warn "pishrink ${fullsize_img} ${shrink_img}"
  warn "pigz  -9 -k ${shrink_img}"
}

HOST="filmkorn-scanner.local"
USER="pi"
# Keep connection alive during long imaging; fail fast on connect
# StrictHostKeyChecking=accept-new: auto-accept new host keys (e.g. after factory reset)
# but still reject if a known host presents a *different* key mid-session.
SSH_OPTS=(-o ConnectTimeout=30 -o ServerAliveInterval=60 -o ServerAliveCountMax=6 -o StrictHostKeyChecking=accept-new)
OUTPUT=""
ZERO_FILL=true
KEEP_SSH=false
KEEP_HOSTKEYS=false
KEEP_HISTORY=false
DRY_RUN=false
# Default pishrink: docker with images dir mounted (img_dir is set later when we run it)
PISHRINK_CMD="${PISHRINK_CMD:-}"

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

info "Before continuing, please:"
info "- open a separate SSH session (or two) to ${USER}@${HOST} and keep it open for recovery"
info "- connect USB drive to retain a safety copy of your ssh stuff and the history"
info "- make sure the scannes target is set to USB-Drive, so that you keep the stashed files on the USB drive"
info "- make sure that new hex files were built (run ./raspi/dev/ino-update.sh)"
info "- commit the new hex files"
info "- consider to tag your current commit"
info "- pull the tag and any remaining changes"
info "- start Docker Desktop and make sure it is running"
read -r -p "Press Enter to continue once you are ready: " confirm_ssh

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
REMOTE_REPO="/home/pi/Filmkorn-Raw-Scanner"
OUTPUT_DIR="${REPO_DIR}/images"
mkdir -p "$OUTPUT_DIR"

if [[ -z "$OUTPUT" ]]; then
  short_sha="$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || true)"
  if [[ -z "$short_sha" ]]; then
    short_sha="unknown"
  fi
  OUTPUT="filmkorn-raspi-fullsize-$(date +%Y%m%d)-${short_sha}.img.gz"
fi
OUTPUT="${OUTPUT_DIR}/$(basename "$OUTPUT")"

# Always start with a clean known_hosts entry for the scanner so that
# StrictHostKeyChecking=accept-new works even if the Pi's SSH host keys were
# regenerated since last pairing (e.g. after a factory reset + firstboot).
ssh-keygen -R "${HOST}" 2>/dev/null || true

if [[ "${DRY_RUN}" == "true" ]]; then
  info "Dry run: would prepare Raspberry Pi for imaging"
else
  info "Preparing Raspberry Pi for imaging..."
fi
if [[ "${DRY_RUN}" == "false" ]]; then
# sudo -E preserves KEEP_SSH/ZERO_FILL etc.; without it sudo wipes env and ZERO_FILL becomes false
ssh "${SSH_OPTS[@]}" "${USER}@${HOST}" "KEEP_SSH=${KEEP_SSH} KEEP_HOSTKEYS=${KEEP_HOSTKEYS} KEEP_HISTORY=${KEEP_HISTORY} ZERO_FILL=${ZERO_FILL} sudo -E bash -s" <<'EOF'
set -euo pipefail
KEEP_SSH="${KEEP_SSH:-false}"
KEEP_HOSTKEYS="${KEEP_HOSTKEYS:-false}"
KEEP_HISTORY="${KEEP_HISTORY:-false}"
ZERO_FILL="${ZERO_FILL:-false}"

STASH_DIR="/run/filmkorn-imaging"
STASH_PERSIST="/var/lib/filmkorn-imaging"
STASH_USB=""
if command -v mountpoint >/dev/null 2>&1 && mountpoint -q /mnt/ramdisk; then
  STASH_RAMDISK="/mnt/ramdisk/filmkorn-imaging"
  LOG_FILE="/mnt/ramdisk/filmkorn-imaging.log"
else
  STASH_RAMDISK="/run/filmkorn-imaging-ramdisk"
  LOG_FILE="/run/filmkorn-imaging.log"
fi
if command -v mountpoint >/dev/null 2>&1 && mountpoint -q /mnt/usb; then
  STASH_USB="/mnt/usb/filmkorn-imaging"
fi
sudo mkdir -p "$STASH_DIR" "$STASH_RAMDISK" "$STASH_PERSIST" || true
if [ -n "$STASH_USB" ]; then
  sudo mkdir -p "$STASH_USB" || true
fi
touch "$LOG_FILE" 2>/dev/null || true

log() {
  echo "imaging-prep: $*" >&2
  echo "imaging-prep: $*" >>"$LOG_FILE" 2>/dev/null || true
  logger -t filmkorn-imaging "imaging-prep: $*" 2>/dev/null || true
}

stash_copy() {
  local src="\$1"
  if [ -s "\$src" ]; then
    cp -f "\$src" "\$STASH_RAMDISK/$(basename "\$src")" 2>/dev/null || true
    cp -f "\$src" "\$STASH_PERSIST/$(basename "\$src")" 2>/dev/null || true
    if [ -n "\$STASH_USB" ]; then
      cp -f "\$src" "\$STASH_USB/$(basename "\$src")" 2>/dev/null || true
    fi
  fi
}

sudo systemctl stop filmkorn-scanner.service || true
sudo systemctl stop filmkorn-lsyncd.service || true
# Stop every service that periodically writes to the root filesystem so that
# the dirty-read image is as clean as possible (e2fsck repairs the rest on
# first boot).  Services that only write to tmpfs (/run, /tmp) are left alone.
for svc in \
    cron.service \
    rsyslog.service \
    fake-hwclock.service \
    bluetooth.service \
    triggerhappy.service \
    ; do
  sudo systemctl stop "$svc" 2>/dev/null && log "stopped $svc" || true
done

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
    sudo rm -f "$base"/imaging-*.tgz "$base"/imaging-swap-size 2>/dev/null || true
    sudo rmdir "$base" >/dev/null 2>&1 || true
  done
}

restore_swap() {
  local swap_size_mb=""
  for base in "$STASH_DIR" "$STASH_RAMDISK" "$STASH_PERSIST"; do
    if [ -s "$base/imaging-swap-size" ]; then
      swap_size_mb=$(cat "$base/imaging-swap-size")
      break
    fi
  done
  if [ -n "$swap_size_mb" ] && [ "$swap_size_mb" -gt 0 ] 2>/dev/null; then
    log "restoring swap file: ${swap_size_mb} MB"
    sudo dd if=/dev/zero of=/var/swap bs=1M count="$swap_size_mb" status=progress 2>&1 || true
    sudo chmod 600 /var/swap
    sudo mkswap /var/swap || true
    sudo swapon /var/swap || true
  else
    log "no swap size stashed; skipping swap restore"
  fi
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
  restore_swap
  cleanup_stash
}
trap restore_and_exit ERR

if [[ "${KEEP_SSH}" == "true" ]]; then
  true
else
  log "stashing ssh keys"
  sudo tar -czf "$STASH_DIR/imaging-ssh.tgz" --ignore-failed-read /home/pi/.ssh /root/.ssh 2>/dev/null || true
  if [ ! -s "$STASH_DIR/imaging-ssh.tgz" ]; then
    log "FATAL: ssh stash missing; aborting imaging"
    exit 1
  fi
  stash_copy "$STASH_DIR/imaging-ssh.tgz"
fi
if [[ "${KEEP_HOSTKEYS}" == "true" ]]; then
  true
else
  log "stashing ssh host keys"
  sudo tar -czf "$STASH_DIR/imaging-hostkeys.tgz" --ignore-failed-read /etc/ssh/ssh_host_* 2>/dev/null || true
  if [ ! -s "$STASH_DIR/imaging-hostkeys.tgz" ]; then
    log "FATAL: ssh host key stash missing; aborting imaging"
    exit 1
  fi
  stash_copy "$STASH_DIR/imaging-hostkeys.tgz"
fi
if [[ "${KEEP_HISTORY}" == "true" ]]; then
  true
else
  log "stashing shell/editor history"
  sudo tar -czf "$STASH_DIR/imaging-history.tgz" --ignore-failed-read \
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
    /home/pi/.gitconfig \
    /root/.gitconfig \
    2>/dev/null || true
  if [ ! -s "$STASH_DIR/imaging-history.tgz" ]; then
    log "FATAL: history stash missing; aborting imaging"
    exit 1
  fi
  stash_copy "$STASH_DIR/imaging-history.tgz"
  if [ -s "$STASH_DIR/imaging-history.tgz" ]; then
    sudo rm -f /home/pi/.bash_history /root/.bash_history || true
    sudo rm -f /home/pi/.zsh_history /root/.zsh_history || true
    sudo rm -f /home/pi/.viminfo /root/.viminfo || true
    sudo rm -f /home/pi/.nano_history /root/.nano_history || true
    sudo rm -f /home/pi/.python_history /root/.python_history || true
    sudo rm -f /home/pi/.gitconfig /root/.gitconfig || true
  else
    log "keeping history files (stash missing)"
  fi
fi

log "stashing host-specific config:"
log "  .user_and_host"
log "  .scan_destination"
log "  .host_path"
log "  .wifi_networks"
log "  lsyncd-to-host.conf"
log "  .locale"
log "  .mcu_hex_hash"
log "  .motor_calibration"
log "  .board_revision"
sudo tar -czf "$STASH_DIR/imaging-config.tgz" --ignore-failed-read \
  /home/pi/Filmkorn-Raw-Scanner/raspi/.user_and_host \
  /home/pi/Filmkorn-Raw-Scanner/raspi/.scan_destination \
  /home/pi/Filmkorn-Raw-Scanner/raspi/.host_path \
  /home/pi/Filmkorn-Raw-Scanner/raspi/.wifi_networks \
  /home/pi/Filmkorn-Raw-Scanner/raspi/lsyncd-to-host.conf \
  /home/pi/Filmkorn-Raw-Scanner/raspi/.locale \
  /home/pi/Filmkorn-Raw-Scanner/raspi/.mcu_hex_hash \
  /home/pi/Filmkorn-Raw-Scanner/raspi/.motor_calibration \
  /home/pi/Filmkorn-Raw-Scanner/raspi/.board_revision \
  2>/dev/null || true
if [ ! -s "$STASH_DIR/imaging-config.tgz" ]; then
  log "FATAL: host-specific config stash missing; aborting imaging"
  exit 1
fi
stash_copy "$STASH_DIR/imaging-config.tgz"
if [ -s "$STASH_DIR/imaging-config.tgz" ]; then
  sudo rm -f /home/pi/Filmkorn-Raw-Scanner/raspi/.user_and_host || true
  sudo rm -f /home/pi/Filmkorn-Raw-Scanner/raspi/.scan_destination || true
  sudo rm -f /home/pi/Filmkorn-Raw-Scanner/raspi/.host_path || true
  sudo rm -f /home/pi/Filmkorn-Raw-Scanner/raspi/.wifi_networks || true
  sudo rm -f /home/pi/Filmkorn-Raw-Scanner/raspi/lsyncd-to-host.conf || true
  sudo rm -f /home/pi/Filmkorn-Raw-Scanner/raspi/.locale || true
  sudo rm -f /home/pi/Filmkorn-Raw-Scanner/raspi/.mcu_hex_hash || true
  sudo rm -f /home/pi/Filmkorn-Raw-Scanner/raspi/.motor_calibration || true
  sudo rm -f /home/pi/Filmkorn-Raw-Scanner/raspi/.board_revision || true
else
  log "keeping host-specific config (stash missing)"
fi

# Stash swap file size and disable swap for imaging (will be restored after, recreated on first boot)
if [ -f /var/swap ]; then
  SWAP_SIZE_MB=$(( $(stat -c%s /var/swap 2>/dev/null || echo 0) / 1024 / 1024 ))
  log "stashing swap size: ${SWAP_SIZE_MB} MB"
  echo "$SWAP_SIZE_MB" > "$STASH_DIR/imaging-swap-size"
  stash_copy "$STASH_DIR/imaging-swap-size"
  log "disabling and removing swap for imaging"
  sudo swapoff /var/swap 2>/dev/null || true
  sudo rm -f /var/swap
else
  log "no /var/swap found; skipping swap stash"
fi

sudo journalctl --rotate || true
sudo journalctl --vacuum-time=1s || true
sudo find /var/log -type f -exec truncate -s 0 {} + || true
sudo rm -f /home/pi/Filmkorn-Raw-Scanner/raspi/scanner.log || true
sudo rm -f /home/pi/Filmkorn-Raw-Scanner/raspi/.capture_latency || true

sudo apt-get clean || true
sudo rm -rf /var/cache/apt/archives/* || true

sudo rm -rf /tmp/* /var/tmp/* || true
if [[ "${ZERO_FILL}" == "true" ]]; then
  avail_kb="$(df -k / | tail -1 | awk '{print $4}')"
  avail_kb="${avail_kb:-0}"
  log "free space on /: ${avail_kb} KB (zero-fill needs >262144 KB)"
  if [[ "$avail_kb" -gt 262144 ]]; then
    count=$(( (avail_kb - 131072) / 1024 ))
    if [[ "$count" -gt 0 ]]; then
      log "zero-filling ${count} MB of free space..."
      sudo dd if=/dev/zero of=/zero.fill bs=1M count="$count" status=progress || true
    fi
  else
    log "skipping zero-fill: not enough free space"
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
  if ! ssh "${SSH_OPTS[@]}" "${USER}@${HOST}" "sudo bash -s" <<'EOF'
set -euo pipefail
sudo install -m 0755 /home/pi/Filmkorn-Raw-Scanner/raspi/scanner-helpers/filmkorn-firstboot.sh /usr/local/sbin/filmkorn-firstboot.sh
sudo install -m 0644 /home/pi/Filmkorn-Raw-Scanner/raspi/systemd/filmkorn-firstboot.service /etc/systemd/system/filmkorn-firstboot.service
sudo rm -f /var/lib/filmkorn/firstboot.done
sudo systemctl daemon-reload
sudo systemctl enable filmkorn-firstboot.service
EOF
  then
    warn "First-boot install failed; restoring stashed files..."
    ssh "${SSH_OPTS[@]}" "${USER}@${HOST}" "sudo bash -c 'set -euo pipefail; for f in /run/filmkorn-imaging/imaging-*.tgz; do [ -f \"\$f\" ] || continue; tar -xzf \"\$f\" -C / 2>/dev/null || true; rm -f \"\$f\"; done; rmdir /run/filmkorn-imaging >/dev/null 2>&1 || true'" || true
    exit 1
  fi
fi

if [[ "${DRY_RUN}" == "true" ]]; then
  info "Dry run: would stream image to $OUTPUT"
else
  info "Creating compressed image: $OUTPUT"
  if ! ssh "${SSH_OPTS[@]}" "${USER}@${HOST}" "KEEP_SSH=${KEEP_SSH} KEEP_HOSTKEYS=${KEEP_HOSTKEYS} sudo bash -s" <<'EOF' > "$OUTPUT"
set -euo pipefail
KEEP_SSH="${KEEP_SSH:-false}"
KEEP_HOSTKEYS="${KEEP_HOSTKEYS:-false}"

STASH_DIR="/run/filmkorn-imaging"
STASH_PERSIST="/var/lib/filmkorn-imaging"
if command -v mountpoint >/dev/null 2>&1 && mountpoint -q /mnt/ramdisk; then
  STASH_RAMDISK="/mnt/ramdisk/filmkorn-imaging"
  LOG_FILE="/mnt/ramdisk/filmkorn-imaging.log"
else
  STASH_RAMDISK="/run/filmkorn-imaging-ramdisk"
  LOG_FILE="/run/filmkorn-imaging.log"
fi
mkdir -p "$STASH_DIR" "$STASH_RAMDISK" "$STASH_PERSIST" || true
touch "$LOG_FILE" 2>/dev/null || true

log() {
  echo "imaging: $*" >&2
  echo "imaging: $*" >>"$LOG_FILE" 2>/dev/null || true
  logger -t filmkorn-imaging "imaging: $*" 2>/dev/null || true
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
    rm -f "$base"/imaging-*.tgz "$base"/imaging-swap-size 2>/dev/null || true
    rmdir "$base" >/dev/null 2>&1 || true
  done
}

restore_swap() {
  local swap_size_mb=""
  for base in "$STASH_DIR" "$STASH_RAMDISK" "$STASH_PERSIST"; do
    if [ -s "$base/imaging-swap-size" ]; then
      swap_size_mb=$(cat "$base/imaging-swap-size")
      break
    fi
  done
  if [ -n "$swap_size_mb" ] && [ "$swap_size_mb" -gt 0 ] 2>/dev/null; then
    log "restoring swap file: ${swap_size_mb} MB"
    dd if=/dev/zero of=/var/swap bs=1M count="$swap_size_mb" status=progress 2>&1 || true
    chmod 600 /var/swap
    mkswap /var/swap || true
    swapon /var/swap || true
  else
    log "no swap size stashed; skipping swap restore"
  fi
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
  restore_swap
  # The imaging script enabled filmkorn-firstboot.service and deleted its
  # marker so that the image triggers firstboot when flashed to a new card.
  # The source Pi itself must NOT run firstboot on its next boot (that would
  # regenerate SSH host keys and break existing SSH connections).
  log "disabling firstboot service on source Pi"
  systemctl disable filmkorn-firstboot.service 2>/dev/null || true
  mkdir -p /var/lib/filmkorn
  touch /var/lib/filmkorn/firstboot.done
  if [ -f "$LOG_FILE" ]; then
    cp -f "$LOG_FILE" /var/log/filmkorn-imaging.log 2>/dev/null || true
  fi
  cleanup_stash
}

# No fsfreeze: all disk-writing services were stopped in the prep phase.
# e2fsck runs on first boot to clean up any journal inconsistencies.
trap restore_after_image EXIT

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
log "streaming image (dirty read; e2fsck repairs on first boot)"
dd if=/dev/mmcblk0 bs=4M status=progress | gzip -1
EOF
  then
    warn "Imaging failed; restoring stashed files..."
    ssh "${SSH_OPTS[@]}" "${USER}@${HOST}" "sudo bash -c 'set -euo pipefail; for f in /run/filmkorn-imaging/imaging-*.tgz; do [ -f \"\$f\" ] || continue; tar -xzf \"\$f\" -C / 2>/dev/null || true; rm -f \"\$f\"; done; rmdir /run/filmkorn-imaging >/dev/null 2>&1 || true'" || true
    exit 1
  fi
fi

if [[ "${DRY_RUN}" == "true" ]]; then
  info "Dry run: would restore stashed files"
fi

info "Image created: $OUTPUT"

if [[ "${DRY_RUN}" == "false" ]]; then
  info "Rebooting Raspberry Pi to restore normal operation..."
  # Brief pause so sshd is fully ready after the imaging session closed.
  sleep 3
  # Connection will drop mid-command when the Pi starts rebooting; that is
  # expected and the non-zero SSH exit code is intentionally ignored.
  ssh "${SSH_OPTS[@]}" "${USER}@${HOST}" "sudo init 6" || true
  info "Pi is rebooting. Continuing with local shrink step..."
fi

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
      if [[ -n "${PISHRINK_CMD:-}" ]]; then
        if bash -lc "$PISHRINK_CMD \"$fullsize_img\" \"$shrink_img\""; then
          info "Compressing shrunk image with pigz -9 -k..."
          pigz -9 -k "$shrink_img"
        else
          manual_shrink_hint "$img_dir" "$fullsize_img" "$shrink_img"
        fi
      else
        # Mount images dir so the expanded .img is visible inside the container
        if docker run --rm -it --privileged -v "$img_dir":/workdir -w /workdir pishrink "$fullsize_img" "$shrink_img"; then
          info "Compressing shrunk image with pigz -9 -k..."
          pigz -9 -k "$shrink_img"
        else
          manual_shrink_hint "$img_dir" "$fullsize_img" "$shrink_img"
        fi
      fi
    )
  else
    warn "pishrink not found; skipping shrink step."
    img_dir="$(cd "$(dirname "$OUTPUT")" && pwd)"
    fullsize_gz="$(basename "$OUTPUT")"
    fullsize_img="${fullsize_gz%.gz}"
    shrink_img="${fullsize_img/filmkorn-raspi-fullsize-/filmkorn-raspi-}"
    manual_shrink_hint "$img_dir" "$fullsize_img" "$shrink_img"
  fi
fi
