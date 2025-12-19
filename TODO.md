# To Dos

## Annoyances

- log insight (from host)
- converter restart is tricky (host_computer/start_converting.sh)

## Potentially deferred
- [can't repro?] controller is stuck after i2c timeout and scanner termination 
- [can't repro?] i2c collisions. can i detect hangs? Consider a Watchdog? https://chat.openai.com/c/0a58a78e-a1ee-4510-95b5-fb1d8fc66790
- [seems to wokr fine] instead of fire & forget, ensure there’s proper synchronization between the command/response flow of Raspberry Pi and Arduino. Each command from the Pi should have a corresponding and expected response behavior on the Arduino.
- 

## Next
- [x] Detect and mount a local harddrive
- [ ] Consider the switch state on GPIO17 and allow local storage

- [ ] Roll the logfile
- [ ] Make clearer log message about film end detection (to detect bad sensor connections)
- [ ] Think about adjusting Exposure without Shell Access
- [ ] Fuses still at 1 MHz when bootstrapping from raspi. Test burning fuses with 5 VCC. MISO is 5V tho. 47K inbetween? Reset has a 10k Pullup too. I would recommend driving the pins from 5V logic via at least 10K resistor and also connect an external Schottky diode from the pin to 3.3V to prevent the input pin's voltage rising much above the PI's supply rail.
- [ ] Handle if Directory on Host PC does not exist
- [ ] Show "No connection to Controller" on display (for e.g. misaligned GPIO header)
- [ ] try one lsyncd restart if the disk is full
- [ ] Get the Log onto the Host PC (rsync?)
- [ ] Average the scan speed rate
- [ ] Auto-Stop Rewinds
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