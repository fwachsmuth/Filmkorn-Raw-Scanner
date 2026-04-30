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

---

# Filmkorn Raw Scanner — Release Notes v0.9.9

_Released March 8, 2026_

---

## What's New

### More Languages

The scanner UI is now also available in **French**, **Spanish**, and **Italian** — in addition to the existing English and German. The language can be selected from the Settings menu (long press on STOP button)

### Flexible Film End Sensor configurations

The film-end sensor can now be configured to match your hardware. A new **Film End Sensor** setting in the Settings menu offers three modes:

- **Normal** — the default, for standard active-low sensors, as the one coming with the controller
- **Inverted** — for sensors that signal the opposite polarity (like some fork sensors)
- **None** — disables end-of-film detection entirely, useful when no sensor is installed. You need to stop the projector manually once the scan is complete, otherwise your hard drive will fill up quickly with blank frames!

### Pairing Menu Timeout

The Bluetooth pairing screen now exits automatically after a timeout instead of waiting indefinitely. If no device pairs within the window, the scanner returns to the main menu on its own — no more getting stuck on the pairing screen after an accidental button press.

### Scan-Idle Watchdog

A new watchdog monitors for situations where the scanner appears to be running but no frames are advancing — typically caused by a rare I²C communication jam between the Raspberry Pi and the scan controller. When detected, the scanner now recovers automatically instead of hanging silently mid-roll.

---

## Bug Fixes & Reliability Improvements

### Firmware Update Menu Exit

Fixed a bug where the firmware update submenu could not be exited cleanly, leaving the scanner unresponsive until restarted.

### Settings Menu Polish

Labels, layout, and spacing across all settings screens have been cleaned up and made consistent. The menus now look and feel uniform regardless of which language is selected.

---

# Filmkorn Raw Scanner — Release Notes v0.9.8

_Released March 6, 2026_

---

## What's New

### Motor Calibration

The scanner can now calibrate itself to your specific projector motor. Open the **Settings menu** and choose **Calibrate Motor** — the scanner will run through its speed range once and find the exact minimum power level needed to keep film transport always going reliably.

### Adjustable Capture Latency

A new **Capture Latency** setting in the Settings menu lets you tune how many camera-frames (not film frames!) are discarded after the motor stops before the image is captured. The default (1 frame) works well for most setups, but you can dial it up if you're occasionally getting slightly blurry, jello- or motion-affected frames, or dial it down if you want maximum speed. Note that a _slower_ (mid-range) stepping speed is often beneficial for the film to settle quickly after tranport, then potentially allowing a lower cpature latency, scanning effectively slightly faster. :) 

### Settings Survive Re-imaging

All your settings — pairing configuration, Wi-Fi networks, language, capture latency, and motor calibration — are now automatically backed up to the scan controller itself. If you ever need to re-flash the Raspberry Pi, your settings are restored from the controller without you having to reconfigure anything.

### Community 3D-Printable Parts

A new [`3d-parts/`](3d-parts/) folder has been added to the repository, containing printable STL files contributed by the community:

- **Noris lens adapters** (M37 and M40.5 threads) — lets you mount enlarger lenses on a Noris projector without modifying the original lens; contributed by Sebastian
- **Parametric motor shaft sensor holder** (includes Fusion 360 source) — adjustable arm length and spacer; contributed by Sandro
- **Film end sensor holder and reflector** — makes mounting the end-of-film detector much easier


---

## Bug Fixes & Reliability Improvements

### Frame Capture Reliability
The core capture logic was significantly overhauled. The scanner now uses the camera's internal sensor  timestamps to guarantee frames are pulled from the buffer in the correct order, and actively discards any stale frames that accumulated while the motor was running. This fixes rare cases where an out-of-order or motion-blurred frame could slip through during long scans.

### Settings Menu Was Sometimes Unreachable
Fixed a communication issue between the Raspberry Pi and the scan controller that could make the Settings menu unresponsive. 

### OTA Updater Permission Fix
Fixed a (final?) bug in the over-the-air update mechanism that caused incorrect file permissions after an update, which could prevent subsequent updates from working. This is more complicated than I anticipated :)

### Disk-Full Handling
Fixed a race condition where filling up the disk mid-scan could cause the scanner to hang rather than stopping cleanly.

### Update Check Fix
Fixed an issue where the version update check could fail silently on systems using developer keys.

### First Frame preserved
Occasionally, the first scanned frame was dropped. Now no more!