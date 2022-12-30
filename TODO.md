# To Dos

## For Install scripts
- [ ] Determine if pair/unpair scripts are running on Mac or Raspi
- [ ] configure `host` in `lsyncd.conf`s
- [ ] remove dash from password to better support non-german keyboard layouts on console

## For scanner.pv
- [ ] configure `lsyncd.conf`'s `targetdir` via `scanner.py` parameter


## For SD-Image Generation 
### For `imagingpre-flight.sh`
- [ ] Add development key removal 
- [ ] Remove logs and history
### General
- [ ] add `dtoverlay=disable-wifi` and `dtoverlay=disable-bt` to `/boot/config.txt`
- [ ] remove dash from password to better support non-german keyboard layouts on console


## General
- [ ] Make the Shutter Speed adjustable (pot?)

## Housekeeping:
- [ ] Document bootstrapping/installation on Raspi & Mac
- [ ] Draw Schematics already
- [ ] ReadMes

## Raspi Todos:
- [ ] Try $ sudo systemctl disable getty@tty1.service
- [x] Update Raspi OS — no Bullseye until PiCamera2 is out of Beta
- [ ] Let piscan.py also start lsyncd (as daemon?)
- [ ] Enable DHCP client instead of manual IP (and )
- [ ] Test camera.preview_window = (0, 0, 640, 480) per https://picamera.readthedocs.io/en/release-1.13/deprecated.html?highlight=start_preview#preview-functions
- [ ] Samba Share funktionierend machen
- [ ] lsync als daemon starten
- [ ] clear screen on boot / start my python code
- [ ] consider not writing to SD (wear), but to Ramdisk or external drive
- [ ] find out why the occasional slow writes happen
- [ ] Let Preview Mode use dynamic exposure to allow easier focus adjustments
- [ ] Make OSError in ask_arduino more specific (errno)
- [ ] Support setting a destination path / host

 
## Hardware
- [ ] Rastkugeln im Objektivgang ausbauen
- [ ] Arduino braucht FTDI Power — why?
- [ ] Staubschutzhaube bauen
- [ ] 1x Netzstrom wäre schön
- [ ] Fix the Fan mount
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

## Remote execution snippets
https://www.cyberciti.biz/faq/unix-linux-execute-command-using-ssh/
ssh pi@piscan2.local -t python3 /home/pi/Filmkorn-Raw-Scanner/raspi/scanner.py
ssh pi@piscan2.local "lsyncd ~/Filmkorn-Raw-Scanner/raspi/lsyncd.conf &" # doesn't go to background yet.
ssh -f pi@piscan2.local "nohup lsyncd ~/Filmkorn-Raw-Scanner/raspi/lsyncd.conf > /dev/null 2>&1 &" works
or cleaner: ssh -n -f user@host "sh -c 'cd /whereever; nohup ./whatever > /dev/null 2>&1 &'"
