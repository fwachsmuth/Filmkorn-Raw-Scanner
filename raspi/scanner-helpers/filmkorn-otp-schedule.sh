#!/usr/bin/env bash
set -euo pipefail

OTP_STATE_FILE="/var/lib/filmkorn/otp_expires_at"
REVOKE_SCRIPT="/usr/local/sbin/filmkorn-otp-revoke.sh"

if [[ ! -f "$OTP_STATE_FILE" ]]; then
  exit 0
fi

expiry="$(tr -d ' \n\r\t' < "$OTP_STATE_FILE" || true)"
if [[ ! "$expiry" =~ ^[0-9]+$ ]]; then
  "$REVOKE_SCRIPT"
  exit 0
fi

now="$(date +%s)"
if (( expiry <= now )); then
  "$REVOKE_SCRIPT"
  exit 0
fi

delay=$((expiry - now))
sudo systemctl reset-failed filmkorn-otp-expire.timer filmkorn-otp-expire.service >/dev/null 2>&1 || true
sudo systemctl stop filmkorn-otp-expire.timer filmkorn-otp-expire.service >/dev/null 2>&1 || true
if ! sudo systemd-run --unit=filmkorn-otp-expire --timer-property=AccuracySec=1s --collect --replace --on-active="${delay}s" "$REVOKE_SCRIPT" >/dev/null 2>&1; then
  sudo systemd-run --unit=filmkorn-otp-expire-${now} --timer-property=AccuracySec=1s --collect --on-active="${delay}s" "$REVOKE_SCRIPT" >/dev/null
fi
