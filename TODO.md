# To Dos

## Annoyances

- log insight (from host)

## Next
- [ ] Imaging Scripts
This restores ssh and history on the pi from ramdisk:
- host-computer/helper/dev/create-raspi-image.sh --output images/filmkorn-raspi-test.img.gz --skip-zeroing
  Only add --keep-ssh or --keep-history or --keep-history if you want to skip removal entirely

- [ ] handle scanner.log (increases, we have journalctl)

- [ ] avoid ssh warning on pairing (see notes)
- [ ] scan-log mit auf die Platte schreiben, ebenso update-logs (weitere?)
- [ ] test bootstrapping and fuse writing
- [ ] consider enabling wifi for time and updates (captive approach?)
- [ ] consider fsck on /mnt/usb

- [ ] Add davinci resolve assets to repo

- [ ] Fuses are still at 1 MHz when bootstrapping from raspi. Test burning fuses with 5 VCC. MISO is 5V tho. 47K inbetween? Reset has a 10k Pullup too. I would recommend driving the pins from 5V logic via at least 10K resistor and also connect an external Schottky diode from the pin to 3.3V to prevent the input pin's voltage rising much above the PI's supply rail.
- [ ] Auto-Stop in-channel Rewinds
- [ ] Test with 2 GB Raspi (1 GB Ramdisk)
- [ ] Test with a Raspi 5
- [ ] Write Build-your-own howtos
- [ ] Try out platformio and see if it fixes the crashy USB/UART oddity


## Useful Links
    Useful Links:
    https://pcbchecklist.com/
    https://arduino.stackexchange.com/a/9858

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

### System Config
- [ ] Inflate /root on first run

## Hardware
- [ ] Staubschutzhaube bauen
- [ ] Test higher PWM freqs
- [ ] Add a pull-down switch to GPIO5 (for remote mode)
- [ ] Disconnect GPIO3 and GPIIO 26 since we no longer an do proper power-down/up and need ugly i2c hacks rn
- [ ] Consider flipping the Raspi GPIO 180° (all wires out on one side)
- [ ] Relabel "Target" Switch with "Resolution"
- For avrdude, use linuxspi instead of linuxgpio. linuxgpio bit-bangt über sysfs; das ist auf neuen Kernels zunehmend hakelig. GPIO12 ist von PM/audio belegt...
	•	SPI über /dev/spidev* (Programmer linuxspi) 19-21-23
	•	plus ein frei gewählter Reset-GPIO
- [ ] Change Exposure Pot to a knobbed Alps type
- [ ] Use a longer power switch


## Snippets
/root inflation how-to: https://raspberrypi.stackexchange.com/questions/499/how-can-i-resize-my-root-partition (seems raspi-cofig does the same). 

Or check nano /usr/bin/raspi-config
Or raspi-config --expand-rootfs