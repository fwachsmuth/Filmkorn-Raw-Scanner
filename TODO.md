# To Dos

## Next
- [ ] Add a logging facility
- [ ] Terminate (gracefully) and restart converter when raspi restarts
- [ ] Add dedicated voltage source for Fan
- [ ] create scripts to restart scanner and converter
- [ ] think about an update scenario (version info?)
- [ ] Test with 2 GB Raspi (1 GB Ramdisk)
- [ ] Consider the switch state on GPIO17 and allow local storage
- [ ] Write Build-your-own howtos
- [ ] list python requirements (on host computer) per https://stackoverflow.com/a/68006970, https://stackoverflow.com/questions/51308683/how-to-move-all-modules-to-new-version-of-python-from-3-6-to-3-7/59608886#59608886
- [ ] Create a pyenv on the host computer
- [ ] Update python on the raspi
- [ ] avoid too many fims
- [x] Add "Insert Film to Scan" gfx in addition to status LED
- [x] fim needs up to 100% CPU during scanning?
- [x] After low disk space ever showed, wrong png is shown after STOP
- [x] Don't ever start scanner.py twice
- [x] Make Ramdisk size dynamic
- [x] Let pair.sh take a parameter for the (Mac-side) raw-intermediates
- [x] let the pi start the converter on the Mac
- [x] Fix scanner autostart (systemd instead of rc.local) https://learn.sparkfun.com/tutorials/how-to-run-a-raspberry-pi-program-on-startup/all#example-code
- [x] Support reading the CONT_RUN_POT at runtime
- [x] Exposure Adjustment via potentiometer — this would require arguemnt transmission via I2C
- [x] Implement watermarking checks for the ramdisk
- [ ] Update .hex in repo
- [x] Do I need the time.sleep(0.1)? Could save 6 minutes / roll
- [x] Make `/home/pi/Filmkorn-Raw-Scanner/raspi/scanner.py` always running

- [ ] Try out platformio


## Useful Links
    Useful Links:
    https://pcbchecklist.com/
    https://arduino.stackexchange.com/a/9858
    https://forums.raspberrypi.com//viewtopic.php?f=91&t=217442 // Shutodwn pin: dtoverlay=gpio-shutdown,gpio_pin=26,active_low=1,gpio_pull=up

## For Install scripts

## Pairing/Unpairing
- [ ] Determine if pair/unpair scripts are running on Mac or Raspi
- [ ] remove dash from password to better support non-german keyboard layouts on console
- [ ] Disable password-ssh after pairing

## For Client 
- [ ] prune empty dirs after conversion 

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
- [ ] Consider using https://pypi.org/project/picamerax/
- [ ] Consider the switch state on GPIO17 and allow local storage

### System Config
- [ ] clear screen on boot / start my python code
- [ ] Inflate /root on first run
- [ ] lsync currently 2.2.3, 2.3.1 is recent

 
## Hardware
- [ ] Rastkugeln im Objektivgang ausbauen?
- [ ] Staubschutzhaube bauen
- [ ] Test higher PWM freqs

## Snippets
/root inflation how-to: https://raspberrypi.stackexchange.com/questions/499/how-can-i-resize-my-root-partition (seems raspi-cofig does the same). 

Or check nano /usr/bin/raspi-config
Or raspi-config --expand-rootfs