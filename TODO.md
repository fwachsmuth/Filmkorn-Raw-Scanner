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
- [ ] Inflate Filesystem again
- [ ] add `dtoverlay=disable-wifi` and `dtoverlay=disable-bt` to `/boot/config.txt`
- [ ] remove dash from password to better support non-german keyboard layouts on console

## Housekeeping:
- [ ] Document bootstrapping/installation on Raspi & Mac
- [x] Draw Schematics already
- [ ] Update ReadMes

## Client Todos
- [ ] prune empty dirs after conversion 


## Raspi Todos:
### scanner.py
- [x] start lsyncd as demon
- [x] Support setting a destination user / host / path via arguments
- [ ] Test: Spaces in -p paths
- [ ] Test camera.preview_window = (0, 0, 640, 480) per https://picamera.readthedocs.io/en/release-1.13/deprecated.html?highlight=start_preview#preview-functions
- [ ] Let Preview Mode use dynamic exposure to allow easier focus adjustments
- [ ] Exposure Adjustment via pot

### System Config
- [x] Update Raspi OS — no Bullseye until PiCamera2 is out of Beta
- [ ] Try $ sudo systemctl disable getty@tty1.service
- [ ] Samba Share funktionierend machen (why?)
- [ ] clear screen on boot / start my python code
- [x] consider not writing to SD (wear), but to Ramdisk or external drive
- [x] find out why the occasional slow writes happen
- [ ] Inflate /root on first run
- [ ] lsync currently 2.2.3, 2.3.1 is recent
 
## Hardware
- [ ] Rastkugeln im Objektivgang ausbauen
- [x] ~Arduino needs FTDI Power — why?~ Only when Projector isn't running
- [ ] Staubschutzhaube bauen
- [ ] 1x Netzstrom wäre schön
- [x] Fix the Fan mount
- [x] Analyze i2c signal intergity with oscilloscope (pullups?)
- [ ] ~switch for hd / rsync~
- [x] Add Film end Detector
- [ ] ~Add XOR Gate to Lamp/Fan Out to turn off Lamp when fan is not running~
- [ ] Redesign Lens Mount to allow cleaning the gate again
- [ ] Trafo-Brumm beseitigen
- [ ] Try shorter camera cable against the noise


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
/root inflation how-to: https://raspberrypi.stackexchange.com/questions/499/how-can-i-resize-my-root-partition (seems raspi-cofig does the same). 

Or check nano /usr/bin/raspi-config
Or raspi-config --expand-rootfs