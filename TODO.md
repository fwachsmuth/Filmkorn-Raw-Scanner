# To Dos

## General
- [ ] Make the Shutter Speed adjustable (pot?)

## Housekeeping:
- [ ] Document bootstrapping/installation on Raspi & Mac
- [ ] Draw Schematics already
- [ ] Readmes anpassen


## Raspi Todos:
- [ ] Update Raspi OS
- [ ] Let piscan.py also start lsyncd (as daemon?)
- [ ] Enable DHCP client instead of manual IP (and )

- [ ] Samba Share funktionierend machen
- [ ] lsync als daemon starten
- [ ] clear screen on boot / start my python code
- [ ] consider not writing to SD (wear), but to Ramdisk or external drive
- [ ] find out why the occasional slow writes happen
- [ ] Let Preview Mode use dynamic exposure to allow easier focus adjustments
- [ ] Make OSError in ask_arduino more specific (errno)
- [ ] Support setting a destination path / host

 
## Hardware
- [ ] Arduino bruacht FTDI Power?
- [ ] Staubschutz bauen
- [ ] 1x Strom wäre schön
- [ ] Fix the Fan
- [ ] Analyze i2c signal intergity with oscilloscope (pullups?)
- [ ] Switch for pos / neg
- [ ] switch for hd / rsync
- [ ] Exposure Adjustment via pot
- [ ] Add Film end Detector
- [ ] Add XOR Gate to Lamp/Fan Out to turn off Lamp when fan is not running
- [ ] Redesign Lens Mount to allow cleaning the gate again
- [ ] Trafo-Brumm beseitigen
- [ ] Try shorter camera cable


## Notes for future use:
- [ ] Enable Screen before Scan: `/opt/vc/bin/tvservice -p` (Display an)
- [ ] Disable Screen after Scan: `/opt/vc/bin/tvservice -o` (Display aus)
### Backup and Restore a uSD on a Mac
Use ApplePiBaker, or 
```
diskutil list
sudo dd if=/dev/disk6 of=~/PiscanuinoSDCardBackup.dmg
```
resp.
```
diskutil unmountDisk /dev/disk6
sudo dd if=~/PiscanuinoSDCardBackup.dmg of=/dev/disk6
```

