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
