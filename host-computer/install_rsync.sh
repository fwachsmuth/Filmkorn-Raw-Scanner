#!/usr/bin/env bash
# install-rsync-with-brew.sh
#
# Installs Homebrew (if missing), then installs rsync (if missing),
# and ensures the current shell can find brew/rsync.
#
# Usage:
#   curl -fsSL <your-url>/install-rsync-with-brew.sh | bash
# or:
#   bash install-rsync-with-brew.sh
#
# Notes:
# - This script targets macOS.
# - It does NOT uninstall or modify Apple's /usr/bin/rsync.
# - It installs Homebrew into the default location:
#     Apple Silicon: /opt/homebrew
#     Intel:         /usr/local
#
set -euo pipefail

# ---------- helpers ----------
log()  { printf "\033[1;32m[+]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[!]\033[0m %s\n" "$*"; }
err()  { printf "\033[1;31m[x]\033[0m %s\n" "$*"; }
die()  { err "$*"; exit 1; }

have_cmd() { command -v "$1" >/dev/null 2>&1; }

# Retry helper for transient network hiccups
retry() {
  local -r max=3
  local n=1
  while true; do
    if "$@"; then
      return 0
    fi
    if [[ $n -ge $max ]]; then
      return 1
    fi
    warn "Command failed (attempt $n/$max). Retrying in 2s…"
    sleep 2
    n=$((n+1))
  done
}

# ---------- preflight ----------
[[ "$(uname -s)" == "Darwin" ]] || die "This script is for macOS (Darwin) only."

arch="$(uname -m)"
if [[ "$arch" == "arm64" ]]; then
  brew_prefix="/opt/homebrew"
else
  brew_prefix="/usr/local"
fi
brew_bin="${brew_prefix}/bin/brew"

log "macOS detected (${arch}). Target Homebrew prefix: ${brew_prefix}"

# Check basic network reachability to GitHub raw (Homebrew installer)
if ! retry curl -fsSLI https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh >/dev/null; then
  die "Network check failed. Can't reach raw.githubusercontent.com. \
Check your internet connection, VPN, proxy, or corporate firewall."
fi

# Xcode Command Line Tools check (Homebrew will often trigger this anyway, but we can guide)
if ! xcode-select -p >/dev/null 2>&1; then
  warn "Xcode Command Line Tools not found."
  warn "macOS should prompt you to install them. If it doesn't, run:"
  warn "  xcode-select --install"
  # Don’t hard-fail here; Homebrew may still proceed and prompt.
fi

# ---------- ensure Homebrew ----------
ensure_brew_in_shell() {
  # Make brew usable in THIS process without relying on the user’s dotfiles
  if [[ -x "$brew_bin" ]]; then
    # shellcheck disable=SC1090
    eval "$("$brew_bin" shellenv)"
  else
    # If brew is on PATH already, just use it
    if have_cmd brew; then
      # shellcheck disable=SC1090
      eval "$(brew shellenv)"
    fi
  fi
}

install_homebrew() {
  log "Installing Homebrew…"
  # Use official installer
  # Homebrew installer may request sudo password and/or prompt for CLT install.
  if ! retry /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; then
    die "Homebrew installer failed. Common causes: network/proxy restrictions, missing admin rights, or interrupted CLT install."
  fi
}

if have_cmd brew || [[ -x "$brew_bin" ]]; then
  log "Homebrew already installed."
else
  install_homebrew
fi

ensure_brew_in_shell
have_cmd brew || die "Homebrew installed but 'brew' is not available in PATH for this shell."

# ---------- diagnose brew health ----------
log "Checking Homebrew health…"
# Avoid failing on non-critical warnings; we’ll still proceed where possible.
if ! brew update >/dev/null 2>&1; then
  warn "brew update failed. Trying again with visible output…"
  brew update || die "brew update failed. Likely network/proxy restrictions."
fi

# ---------- ensure rsync ----------
stock_rsync="/usr/bin/rsync"
hb_rsync="$(brew --prefix)/bin/rsync"

# If Homebrew rsync is already installed, we’re done (but we’ll verify)
if [[ -x "$hb_rsync" ]]; then
  log "Homebrew rsync already installed at: $hb_rsync"
else
  log "Installing rsync via Homebrew…"
  if ! brew install rsync; then
    # Common error: permissions / ownership problems in prefix
    warn "brew install rsync failed. Running quick diagnostics…"
    brew doctor || true
    die "Failed to install rsync with Homebrew. See output above for the cause."
  fi
fi

[[ -x "$hb_rsync" ]] || die "rsync install reported success but binary not found at: $hb_rsync"

# ---------- verify versions and PATH ----------
log "Verifying rsync versions…"
stock_ver="$("$stock_rsync" --version | head -n1 || true)"
hb_ver="$("$hb_rsync" --version | head -n1 || true)"

printf "  Stock macOS rsync: %s (%s)\n" "$stock_rsync" "${stock_ver:-unknown}"
printf "  Homebrew rsync:    %s (%s)\n" "$hb_rsync" "${hb_ver:-unknown}"

# Ensure current shell finds the Homebrew rsync (optional; some users may prefer /usr/bin/rsync)
resolved="$(command -v rsync || true)"
if [[ "$resolved" != "$hb_rsync" ]]; then
  warn "Your shell currently resolves 'rsync' to: ${resolved:-<not found>}"
  warn "If you want 'rsync' to use Homebrew by default, add this to your shell profile:"
  if [[ "$arch" == "arm64" ]]; then
    cat <<'EOF'
  echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
  eval "$(/opt/homebrew/bin/brew shellenv)"
EOF
  else
    cat <<'EOF'
  echo 'eval "$(/usr/local/bin/brew shellenv)"' >> ~/.zprofile
  eval "$(/usr/local/bin/brew shellenv)"
EOF
  fi
else
  log "Great: 'rsync' in this shell points to Homebrew rsync."
fi

log "Done."
exit 0