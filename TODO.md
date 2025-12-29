# To Dos

## Annoyances

- log insight (from host)

## Next
- [ ] Gauge writing to /mn/usb directly instead of ramdisk

- [ ] Let the Arduino respond with a version number via i2c

- [ ] is opme.sh working and ever called?
- [ ] consider enabling wifi for time and updates
- [ ] "Allow full disk access for remote users" in installer script

- [ ] Fuses are still at 1 MHz when bootstrapping from raspi. Test burning fuses with 5 VCC. MISO is 5V tho. 47K inbetween? Reset has a 10k Pullup too. I would recommend driving the pins from 5V logic via at least 10K resistor and also connect an external Schottky diode from the pin to 3.3V to prevent the input pin's voltage rising much above the PI's supply rail.
- [ ] Auto-Stop in-channel Rewinds

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
        - scanner.py via git
        - controller via raspi via git
        - raspi via imaging if necessary
    - latest version announced via static github pages link?
        - might contain a commit id, or checkout via tag?

- [ ] Test with 2 GB Raspi (1 GB Ramdisk)
- [ ] Write Build-your-own howtos
- [ ] list python requirements (on host computer) per https://stackoverflow.com/a/68006970, https://stackoverflow.com/questions/51308683/how-to-move-all-modules-to-new-version-of-python-from-3-6-to-3-7/59608886#59608886
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

## Pairing/Unpairing
- [ ] Determine if pair/unpair scripts are running on Mac or Raspi
- [ ] remove dash from password to better support non-german keyboard layouts on console
- [ ] Disable password-ssh after pairing

## For SD-Image Generation 
### For `imaging-preflight.sh`
- [ ] Add development key removal 
- [ ] Remove logs and history `history -c && history -w`
- [ ] prune /boot.bak?

### General
- [ ] Inflate Filesystem once, `raspi-config --expand-rootfs`
- [ ] add `dtoverlay=disable-wifi` and `dtoverlay=disable-bt` to `/boot/config.txt`
- [ ] remove dash from password to better support non-german keyboard layouts on console

## Housekeeping:
- [ ] Document bootstrapping/installation on Raspi & Mac
- [ ] Update ReadMes

## Raspi Todos:
### scanner.py

### System Config
- [ ] Inflate /root on first run

## Hardware
- [ ] Staubschutzhaube bauen
- [ ] Test higher PWM freqs
- [ ] Add a pull-down switch to GPIO5 (for remote mode)
- [ ] Disconnect GPIO3 and GPIIO 26 since we no longer an do proper power-down/up and need ugly i2c hacks rn
- [ ] Consider flipping the Raspi GPIO 180° (all wires out on one side)
- [ ] Relabel "Target" Switch with "Resolution"
- For avrdude, use linuxspi instead of linuxgpio. linuxgpio bit-bangt über sysfs; das ist auf neuen Kernels zunehmend hakelig.
	•	SPI über /dev/spidev* (Programmer linuxspi)
	•	plus ein frei gewählter Reset-GPIO


## Snippets
/root inflation how-to: https://raspberrypi.stackexchange.com/questions/499/how-can-i-resize-my-root-partition (seems raspi-cofig does the same). 

Or check nano /usr/bin/raspi-config
Or raspi-config --expand-rootfs