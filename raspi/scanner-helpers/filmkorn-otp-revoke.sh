#!/usr/bin/env bash
set -euo pipefail

OTP_STATE_FILE="/var/lib/filmkorn/otp_expires_at"
SSH_CONF_FILE="/etc/ssh/sshd_config.d/filmkorn-password.conf"

sudo rm -f "$SSH_CONF_FILE" || true
sudo passwd -l pi >/dev/null 2>&1 || true
sudo rm -f "$OTP_STATE_FILE" || true

sudo systemctl reload ssh || sudo systemctl restart ssh || true
