#!/bin/bash
set -euo pipefail

# Runs after git checkout (and again after flashing, if flashing happens).
# It will not run if git fetch/checkout fails.
# Use this for migrations or cleanup that should happen with the new version,
# and for installing packages or system-wide config changes.
# Execution details:
# - Runs as root (systemd-run), not as the pi user.
# - Minimal environment; HOME is /root and PATH may be limited.
# - Working directory is the repo root (/home/pi/Filmkorn-Raw-Scanner).
# - No TTY/interactive input.

log() {
    logger -t "filmkorn-postflight" "$*"
    echo "$*"
}

log "postflight: starting"

REPO_ROOT="/home/pi/Filmkorn-Raw-Scanner"
WIFI_PORTAL_DIR="${REPO_ROOT}/raspi/wifi_portal"

# --- WiFi Portal Setup ---

# Ensure wifi_portal directory has correct ownership (only if needed)
if [ -d "$WIFI_PORTAL_DIR" ]; then
    # Check if ownership is already correct
    current_owner=$(stat -c '%U:%G' "$WIFI_PORTAL_DIR" 2>/dev/null || echo "unknown")
    if [ "$current_owner" != "pi:pi" ]; then
        log "postflight: setting wifi_portal directory ownership (was: $current_owner)"
        chown -R pi:pi "$WIFI_PORTAL_DIR"
    fi
fi

# --- NetworkManager Configuration ---

# Ensure NetworkManager is managing wlan0 (required for WiFi setup to work)
# Only run if nmcli is available and wlan0 exists
if command -v nmcli &>/dev/null && nmcli device show wlan0 &>/dev/null; then
    wlan_managed=$(nmcli -t -f GENERAL.STATE device show wlan0 2>/dev/null | grep -v unmanaged || echo "")
    if [ -z "$wlan_managed" ]; then
        log "postflight: setting wlan0 to managed"
        nmcli device set wlan0 managed yes 2>/dev/null || true
    fi
fi

# --- Unmask hostapd and dnsmasq ---
# We masked them in preflight to prevent auto-start, but we need them available
# for the captive portal to start on-demand

for svc in hostapd dnsmasq; do
    svc_state=$(systemctl is-enabled "$svc" 2>/dev/null || echo "unknown")
    if [ "$svc_state" = "masked" ]; then
        log "postflight: unmasking $svc (but keeping disabled)"
        systemctl unmask "$svc" 2>/dev/null || true
        # Keep it disabled so it doesn't auto-start
        systemctl disable "$svc" 2>/dev/null || true
    fi
done

# --- Cleanup old configurations ---

# Remove any stale captive portal temp files
rm -f /tmp/filmkorn-hostapd.conf /tmp/filmkorn-dnsmasq.conf 2>/dev/null || true

log "postflight: completed"
