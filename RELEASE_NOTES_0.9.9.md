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
