#!/bin/bash
set -euo pipefail

# Runs after git checkout and before flashing.
# Use this for checks that depend on the checked-out version
# (e.g., required files, config validation, network tests),
# and for installing packages or system-wide config changes.
# Execution details:
# - Runs as root (systemd-run), not as the pi user.
# - Minimal environment; HOME is /root and PATH may be limited.
# - Working directory is the repo root (/home/pi/Filmkorn-Raw-Scanner).
# - No TTY/interactive input.

log() {
    logger -t "filmkorn-preflight" "$*"
    echo "$*"
}

log "preflight: starting"

# --- WiFi Captive Portal Dependencies ---
# Install packages required for the WiFi setup captive portal feature

WIFI_PORTAL_PACKAGES=(
    hostapd     # WiFi access point daemon
    dnsmasq     # DHCP/DNS for captive portal
    python3-flask  # Web framework for portal
)

# Check if any packages need to be installed
PACKAGES_TO_INSTALL=()
for pkg in "${WIFI_PORTAL_PACKAGES[@]}"; do
    if ! dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
        PACKAGES_TO_INSTALL+=("$pkg")
    fi
done

if [ ${#PACKAGES_TO_INSTALL[@]} -gt 0 ]; then
    log "preflight: installing WiFi portal packages: ${PACKAGES_TO_INSTALL[*]}"
    
    # Update package lists
    apt-get update -qq
    
    # Install packages
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        "${PACKAGES_TO_INSTALL[@]}"
    
    log "preflight: packages installed successfully"
else
    log "preflight: WiFi portal packages already installed"
fi

# Disable hostapd and dnsmasq by default - we start them on-demand from the portal
# These services should not run automatically at boot
for svc in hostapd dnsmasq; do
    svc_state=$(systemctl is-enabled "$svc" 2>/dev/null || echo "unknown")
    case "$svc_state" in
        enabled)
            log "preflight: disabling and masking $svc (started on-demand by portal)"
            systemctl disable --now "$svc" 2>/dev/null || true
            systemctl mask "$svc" 2>/dev/null || true
            ;;
        disabled)
            # Disabled but not masked - mask it
            log "preflight: masking $svc (already disabled)"
            systemctl mask "$svc" 2>/dev/null || true
            ;;
        masked)
            # Already masked, nothing to do
            ;;
        *)
            # Unknown state or service doesn't exist yet
            ;;
    esac
done

log "preflight: completed"
