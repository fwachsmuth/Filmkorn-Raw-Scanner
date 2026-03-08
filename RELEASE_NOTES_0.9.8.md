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