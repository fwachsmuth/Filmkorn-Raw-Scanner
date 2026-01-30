#!/bin/bash
set -euo pipefail

# Run on the host computer (Mac) only.
# Extracts the custom app icon (Icon\r) into Contents/Resources/AppIcon.icns
# so it persists across git, copies, and USB. Run this after changing the
# app icon in Finder (Get Info → drag image onto icon).

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script runs on macOS only (requires DeRez)."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="${SCRIPT_DIR}/Pair Filmkorn-Scanner (Mac).app"
ICON_FILE="${APP}/Icon"$'\r'
RESOURCES="${APP}/Contents/Resources"
OUT="${RESOURCES}/AppIcon.icns"

if [[ ! -f "$ICON_FILE" ]]; then
  echo "No custom icon found at $APP (Icon file missing)."
  echo "Set an icon in Finder: Get Info → drag image onto the app icon."
  exit 1
fi

if ! command -v DeRez >/dev/null 2>&1; then
  echo "DeRez not found. Install Xcode Command Line Tools: xcode-select --install"
  exit 1
fi

mkdir -p "$RESOURCES"
DeRez -only icns "$ICON_FILE" 2>/dev/null \
  | sed -n 's/.*\$"\([^"]*\)".*/\1/p' \
  | tr -d ' \n' \
  | xxd -r -p > "$OUT"

echo "Wrote $OUT"
echo "Commit Contents/Resources/AppIcon.icns so the icon persists."
