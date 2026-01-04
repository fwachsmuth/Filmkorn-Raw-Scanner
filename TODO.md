# To Dos

## Next
- Remove Starting Converter Process as peaceman@wachsmut-mbp-2025.local:/Volumes/Filme 4TB

- [ ] Write Build-your-own howtos
- [ ] Add Note that "Full Access" is required!!
- [ ] consider enabling wifi for time and updates (captive approach?)
- [ ] consider fsck on /mnt/usb
- [ ] Add davinci resolve assets to repo
- [ ] Allow having multiple scanners on the network?

- [ ] Auto-Stop in-channel Rewinds
- [ ] Test with 2 GB Raspi (1 GB Ramdisk)
- [ ] Test with a Raspi 5
- [ ] Try out platformio and see if it fixes the crashy USB/UART oddity
- [x] Imaging Scripts
    - host-computer/helper/dev/create-raspi-image.sh --skip-zeroing
        (Only add --keep-ssh or --keep-history or --keep-history if you want to skip removal entirely)
        pishrink filmkorn-raspi-a34098.img smaller-a34098.img

## Useful Links
    Useful Links:
    https://pcbchecklist.com/
    https://arduino.stackexchange.com/a/9858

## Housekeeping:
- [ ] Update ReadMes

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
- [ ] Bigger Net/HDD Switch
- [ ] Add GND TPs to GPIO TPs
- [ ] Make SW2 Pull up/dn 10K or less. 47k is noisy.

## Snippets
