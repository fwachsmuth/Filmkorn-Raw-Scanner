# To Dos

## Next
- [ ] Find out why turning on the lamp after a while of idling causes a Arduino Reboot
- [ ] Think about adjusting Exposure without Shell Access
- [ ] MCP entfernen
- [ ] Fues sind immer noch auf 1 MHz :-()
- [ ] Add Fan Voltage TPs
- [ ] Flip the speed pots
- [ ] Decouple C for U11 (in 1u, out 1n)
- [ ] Handle if Directory on Host PC does not exist
- [ ] Show "No connection to Controller" on display (for e.g. misaligned GPIO header)
- [ ] try one lsyncd restart if the disk is full
- [ ] create a launchctl for the converter
- [ ] Detect and mount a local harddrive
- [ ] Get the Log onto the Host PC (rsync?)
- [ ] Consider the switch state on GPIO17 and allow local storage
- [ ] think about an update scenario (version info?)
    - most pragmatic:
        - shellscript on host pc:
            - git pull on mac
            - git pull on raspi
            - reads current version of controller software (via hex filename?)
            - updates controller
    - All three parts need to contain/emit a version number
        - [ ] Let the Arduino respond with a version to the Pi
    - all components should get updated separately
        - converter.py via git
        - scanner.py via git
        - controller via raspi via git
        - raspi via imaging if necessary
    - latest version announced via static github pages link?
        - might contain a commit id, or checkout via tag?

- [ ] Terminate (gracefully) and restart converter when raspi restarts
- [x] Add dedicated voltage source for Fan
- [ ] create scripts to restart scanner and converter
- [ ] Test with 2 GB Raspi (1 GB Ramdisk)
- [ ] Write Build-your-own howtos
- [ ] list python requirements (on host computer) per https://stackoverflow.com/a/68006970, https://stackoverflow.com/questions/51308683/how-to-move-all-modules-to-new-version-of-python-from-3-6-to-3-7/59608886#59608886
- [ ] Create a pyenv on the host computer
- [ ] Update python on the raspi
- [ ] fix pair.sh: Can't git:
            Host key verification failed.
            fatal: Could not read from remote repository.

            Please make sure you have the correct access rights
            and the repository exists.
- [ ] Update .hex in repo
- [ ] Try out platformio and see if it fixes the crashy USB/UART oddity


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

### System Config
- [ ] Inflate /root on first run
- [ ] lsync currently 2.2.3, 2.3.1 is recent

## Hardware
- [ ] Staubschutzhaube bauen
- [ ] Test higher PWM freqs

## Snippets
/root inflation how-to: https://raspberrypi.stackexchange.com/questions/499/how-can-i-resize-my-root-partition (seems raspi-cofig does the same). 

Or check nano /usr/bin/raspi-config
Or raspi-config --expand-rootfs