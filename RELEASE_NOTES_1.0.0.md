# Filmkorn Raw Scanner — Release Notes v1.0.0

_Released April 26, 2026_

---

## What's New

### DaVinci Resolve Project Presets

Some DaVinci Resolve project settings presets for 18/24 fps and 2K/4K are now bundled with the scanner and automatically placed on the connected USB drive. Import them directly to your Resolve Project Manager to get a solid starting point for color grading your scans — no manual configuration needed.

### Resources and 3D Parts on USB Drive

The community 3D-printable parts and DaVinci Resolve assets are now automatically copied to your USB drive whenever it is connected. This makes them accessible directly from the drive without having to visit the repository or dig into installation directories.

### Pairing App Auto-Update

The pairing app on the USB drive is now automatically kept up to date. If an older version is detected, it is replaced with the current one at pairing time — no manual downloads required.

### Board Revision Detection

The scanner now detects which hardware revision of the controller board is installed and adapts its behavior accordingly. Rev E+ boards correctly handle GPIO5 as the Target Switch, which was previously mislabeled. This also lays the groundwork for transparent support of future board revisions.

---

## Bug Fixes & Reliability Improvements

### FPS Display Accuracy

Fixed a calculation error in the frames-per-second readout on the HUD. The displayed value now correctly reflects the actual scanning rate.

### Hostname Cleanup on Unpairing

Fixed an issue where stale hostname entries could remain after unpairing the scanner, which could cause confusing behavior on subsequent pairing attempts.
