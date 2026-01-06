# To Dos

## Next
- Remove "Starting Converter Process as peaceman@wachsmut-mbp-2025.local:/Volumes/Filme 4TB"

Bugs:
    Right after first boot:
    /usr/bin/ssh-copy-id: ERROR: ssh: connect to host filmkorn-scanner.local port 22: Connection refused
    Failed to install SSH key on the scanner. Check the password and network connection.

ISO ist nicht fest?


- [ ] 57 mm statt 60 mm
- [ ] 3 mm Abstand
- [ ] weisses SUgru
- [ ] add hystheresis to film end detection
- [ ] Don't crash w/o camera
- [ ] 27W Netzteil messen
- [ ] Bei TRansport oder Preview -> No Film LED an?
- [ ] Write Build-your-own howtos
- [ ] Add Note that "Full Access" is required!!
- [ ] consider enabling wifi for time and updates (captive approach?)
- [ ] consider fsck on /mnt/usb
- [ ] Add davinci resolve assets to repo
- [ ] Allow having multiple scanners on the network?
- [ ] Real Power off

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
- [ ] Bodge: R8 -> 1K, 100n zwischen Pin 1 und 2 von Q1
- [ ] 10u (!) Kerko parallel zu C6/8/10
- [ ] Klebepunkt im Weg

- [ ] Test higher PWM freqs
- [ ] Add a pull-down switch to GPIO5 (for remote mode)
- [ ] Disconnect GPIO3 and GPIIO 26 since we no longer an do proper power-down/up and rn need ugly hacks to not collide with i2c
- [ ] Consider flipping the Raspi GPIO 180° (all wires out on one side)
- [ ] Relabel "Target" Switch with "Resolution"
- [ ] Change Exposure Pot to a knobbed Alps type
- [ ] Use a longer power switch
- [ ] Bigger Net/HDD and Reslution Switches
- [ ] Add GND TPs to GPIO TPs
- [ ] Make SW2 Pull up/dn 10K or less. 47k is noisy.
- [ ] Staubschutzhaube bauen

## Snippets
