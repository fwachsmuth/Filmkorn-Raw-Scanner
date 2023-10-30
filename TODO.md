# To Dos

## For Install scripts

## Pairing/Unpairing
- [ ] Determine if pair/unpair scripts are running on Mac or Raspi
- [ ] remove dash from password to better support non-german keyboard layouts on console
- [ ] Disable password-ssh after pairing

## For Client 
- [ ] prune empty dirs after conversion 
- [ ] test re-enabling packing DNGs

sudo rpi-update 0642816ed05d31fb37fc8fbbba9e1774b475113f worked (to get back to old 5.4.x kernel with awb)


## For SD-Image Generation 
### For `imagingpre-flight.sh`
- [ ] Add development key removal 
- [ ] Remove logs and history `history -c && history -w`
- [ ] prune /boot.bak?

### General
- [ ] Inflate Filesystem once, `raspi-config --expand-rootfs`
- [x] add `dtoverlay=disable-wifi` and `dtoverlay=disable-bt` to `/boot/config.txt`
- [ ] remove dash from password to better support non-german keyboard layouts on console
- [ ] Determine which is the latest working "buster" kernel setting `gain_r` and `gain_b` to > `1.000` in the jpeg+raw file created. `5.4.79` is safe, `5.10.103` fails. More kernels: https://github.com/Hexxeh/rpi-firmware/commits/master


## Housekeeping:
- [ ] Document bootstrapping/installation on Raspi & Mac
- [x] Draw Schematics already
- [ ] Update ReadMes

## Raspi Todos:
### scanner.py
- [x] start lsyncd as demon
- [x] Support setting a destination user / host / path via arguments
- [ ] Start conversion watchdog on client
- [ ] Test: Spaces in -p paths (lsync config)
- [ ] Consider using https://pypi.org/project/picamerax/
- [x] Fixed Preview Aspect Ratio by editing /boot/config.txt to match the 5" 800x480 screen requirements
- [x] Let Preview Mode use dynamic exposure to allow easier focus adjustments
- [ ] Exposure Adjustment via potentiometer — this would require arguemnt transmission via I2C
- [ ] Implement watermarking checks for the ramdisk
- `fim --quiet -d /dev/fb0 successful_connection_to_raspi.png` # or pygame? https://stackoverflow.com/questions/70685286/how-to-use-pygame-to-display-something-via-hdmi-on-dev-fb0-using-raspian-os-li

### System Config
- [x] Update Raspi OS — no Bullseye until PiCamera2 is out of Beta
- [x] Try $ sudo systemctl disable getty@tty1.service — not clearing screen, so not really necessary?
- [ ] clear screen on boot / start my python code
- [x] consider not writing to SD (wear), but to Ramdisk or external drive
- [x] find out why the occasional slow writes happen
- [ ] Inflate /root on first run
- [ ] lsync currently 2.2.3, 2.3.1 is recent
- [x] more Ramdisks

 
## Hardware
- [ ] Replace Transformer
- [ ] Add soft reset button
- [ ] Rastkugeln im Objektivgang ausbauen
- [x] ~Arduino needs FTDI Power — why?~ Only when Projector isn't running
- [ ] Staubschutzhaube bauen
- [ ] 1x Netzstrom wäre schön
- [x] Fix the Fan mount
- [x] Analyze i2c signal intergity with oscilloscope (pullups?)
- [x] Add Film end Detector
- [ ] Redesign Lens Mount to allow cleaning the gate again
- [ ] Trafo-Brumm beseitigen
- [ ] Try shorter camera cable against the noise
- [ ] ~switch for hd / rsync~

## Remote execution snippets
https://www.cyberciti.biz/faq/unix-linux-execute-command-using-ssh/
ssh pi@piscan2.local -t python3 /home/pi/Filmkorn-Raw-Scanner/raspi/scanner.py
ssh pi@piscan2.local "lsyncd ~/Filmkorn-Raw-Scanner/raspi/lsyncd.conf &" # doesn't go to background yet.
ssh -f pi@piscan2.local "nohup lsyncd ~/Filmkorn-Raw-Scanner/raspi/lsyncd.conf > /dev/null 2>&1 &" works
or cleaner: ssh -n -f user@host "sh -c 'cd /whereever; nohup ./whatever > /dev/null 2>&1 &'"
/root inflation how-to: https://raspberrypi.stackexchange.com/questions/499/how-can-i-resize-my-root-partition (seems raspi-cofig does the same). 

Or check nano /usr/bin/raspi-config
Or raspi-config --expand-rootfs