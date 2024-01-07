# To Dos

## Next
- [x] Let pair.sh take a parameter for the (Mac-side) raw-intermediates
- [x] let the pi start the converter on the Mac
- [ ] think about an update scneario (version info?)
- [ ] Test with 2 GB Raspi (1 GB Ramdisk)
- [ ] Consider the switch state on GPIO17 and allow local storage
- [ ] Write Build-your-own howtos
- [ ] Add "Insert Film to Scan" gfx in addition to status LED
- [ ] list python requirements (on host computer) per https://stackoverflow.com/a/68006970
- [x] Support reading the CONT_RUN_POT at runtime
- [x] Exposure Adjustment via potentiometer — this would require arguemnt transmission via I2C
- [x] Implement watermarking checks for the ramdisk
- [x] Update .hex in repo
- [x] Do I need the time.sleep(0.1)? Could save 6 minutes / roll

- [x] Make `/home/pi/Filmkorn-Raw-Scanner/raspi/scanner.py` always running

- [ ] Try out platformio


## Useful Links
    Useful Links:
    https://cdn.sparkfun.com/assets/c/6/2/2/1/ProMini8MHzv2.pdf
    https://pcbchecklist.com/
    https://arduino.stackexchange.com/a/9858
    https://github.com/raspberrypi/hats/blob/master/designguide.md
    https://forums.raspberrypi.com//viewtopic.php?f=91&t=217442 // Shutodwn pin: dtoverlay=gpio-shutdown,gpio_pin=26,active_low=1,gpio_pull=up

## For Install scripts

## Pairing/Unpairing
- [ ] Determine if pair/unpair scripts are running on Mac or Raspi
- [ ] remove dash from password to better support non-german keyboard layouts on console
- [ ] Disable password-ssh after pairing

## For Client 
- [ ] prune empty dirs after conversion 
- [ ] test re-enabling packing DNGs

## For SD-Image Generation 
### For `imaging-preflight.sh`
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
- [ ] Update ReadMes

## Raspi Todos:
### scanner.py
- [x] Support setting a destination user / host / path via arguments
- [ ] Start conversion watchdog on client
- [ ] Test: Spaces in -p paths (lsync config)
- [ ] Consider using https://pypi.org/project/picamerax/
- [ ] Exposure Adjustment via potentiometer — this would require arguemnt transmission via I2C
- [ ] Consider the switch state on GPIO17 and allow local storage
- [ ] Implement watermarking checks for the ramdisk
- `fim --quiet -d /dev/fb0 successful_connection_to_raspi.png` # or pygame? https://stackoverflow.com/questions/70685286/how-to-use-pygame-to-display-something-via-hdmi-on-dev-fb0-using-raspian-os-li

### System Config
- [ ] clear screen on boot / start my python code
- [ ] Inflate /root on first run
- [ ] lsync currently 2.2.3, 2.3.1 is recent

 
## Hardware
- [ ] Rastkugeln im Objektivgang ausbauen
- [ ] Staubschutzhaube bauen
- [ ] 1x Netzstrom wäre schön
- [ ] Redesign Lens Mount to allow cleaning the gate again
- [ ] Trafo-Brumm beseitigen
- [ ] Test higher PWM freqs

## Remote execution snippets
https://www.cyberciti.biz/faq/unix-linux-execute-command-using-ssh/
ssh pi@piscan2.local -t python3 /home/pi/Filmkorn-Raw-Scanner/raspi/scanner.py
ssh pi@piscan2.local "lsyncd ~/Filmkorn-Raw-Scanner/raspi/lsyncd.conf &" # doesn't go to background yet.
ssh -f pi@piscan2.local "nohup lsyncd ~/Filmkorn-Raw-Scanner/raspi/lsyncd.conf > /dev/null 2>&1 &" works
or cleaner: ssh -n -f user@host "sh -c 'cd /whereever; nohup ./whatever > /dev/null 2>&1 &'"
/root inflation how-to: https://raspberrypi.stackexchange.com/questions/499/how-can-i-resize-my-root-partition (seems raspi-cofig does the same). 

Or check nano /usr/bin/raspi-config
Or raspi-config --expand-rootfs