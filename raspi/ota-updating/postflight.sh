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
