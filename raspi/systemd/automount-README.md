## USB auto-mount to `/mnt/usb` (largest partition)

Goal: On USB attach, automatically mount the **largest** partition formatted as **exFAT or ext2/3/4** to **`/mnt/usb`**, using **kernel drivers (no FUSE)**.

### How it works

- **udev (add/change only)** starts a templated systemd unit:
  - `usb-mount-largest@sdX.service`
  - Triggered on `ACTION=add|change`, `DEVTYPE=disk`, `KERNEL=sd[a-z]`
- **Unmount is handled by systemd device lifecycle**, not udev `remove`:
  - The mount unit is tied to `dev-sdX.device` (`BindsTo=` + `StopWhenUnneeded=`).
  - When the disk disappears, systemd stops the unit → `ExecStop=` unmounts `/mnt/usb`.

This avoids brittle `ACTION=remove` races (device may already be gone; disk+partition events can fire in weird orders).

### Repo files

- Script: `raspi/mount-largest-usb.sh`
- systemd unit template: `raspi/systemd/usb-mount-largest@.service`
- udev rule: `raspi/systemd/99-usb-mount-largest.rules`
- Installer: `raspi/systemd/install_services.sh`

### Quick test

Replace `sdb` with whatever `lsblk` shows (device names can change).

```bash
sudo systemctl start usb-mount-largest@sdb.service
findmnt /mnt/usb
touch /mnt/usb/__test && echo OK