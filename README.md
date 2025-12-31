# Filmkorn Raw-Scanner

## What is this?
The Filmkorn Raw-Scanner, formerly known as Piscanuino, is an open source solution to make film scanning in amazing quality possible at a lowe price. In factm the project originated from [a bet](https://www.filmvorfuehrer.de/topic/31851-challenge-framescanner-f%C3%BCr-350%E2%82%AC-bauen/): 
*Is it possible to build a high quality film scanner for < 350 €?*

Well, it is, but this bet was won in 2020. Prices for many thing have gone up since then, so you might need to plan for a bit more, or get creative to stay within this budget.

### Shopping list
This is what I bought from my budget to build this scanner.
- Raspi 4 w/4GB of RAM: 50€
- A 5V/27W Power supply: 12€ (the usually bundled power supply only delivers 15W, which isn't sufficient if scanning to a USB drive)
- Raspberry Pi HQ Camera w/o lens: 50€
- C-Mount Spacer Rings (Ebay or Aliexpress): 30€
- M39 Enlarger lens EL-Nikkor 2.8/50mm: 50€
- M39 to M42 adapter ring: 10€
- M42 to C-Mount Adapter (Wittner): 30€
- YUJILEDS Full Spectrum CRI 98 COB LED [BC 135L (5600K, 9W)](https://www.yujiintl.com/bc-135l/): €20 ([potential alternative for 4€ ?](https://www.leds.de/nichia-ntcws024b-v2-cob-led-5000k-r95-32105.html))
- [5" HDMI Display](https://www.amazon.de/dp/B0BWJ8YP7S) or https://www.amazon.de/dp/B0CMCSCYPD/ for focusing and framing (and watching the scan going on) – any other monitor shoudl work, too. 640x480 is all we need.
- MDF wood, screws and hardware store stuff to mount it all

- Aluminium Heatsink 40x40x20: 5€
- Chipset Fan 40x40x20 (12V / 115 mA / 1.38W), zB MF40201VX-A99 https://de.elv.com/sunon-12-v-axial-luefter-mf40201vx-a99-40-x-40-x-20-mm-112421 6€
- 25g Bariumsulfat, 20g PVA, 10g IPA, Magnetrührer, coaten

You can definitely use other lenses, another LED and other ways than spacer rings to mount the Raspi Cam in front of the projector's gate. Get creative as needed. Note though that 50mm are pretty much perfect, shorter focal lengthes could be mechanically challenging, and longer focal lengths will be mechanically unstable and have plenty of air between the film and the sensor.
Also, if you want to scan color film, make sure to get a decent high CRI LED. This is particularly important for scanning color neg film.

The above totals to €240, so you have ~100€ left to get the electronics and an old Noris projector. 
You'll also need an external USB3 Drive, ideally a fast SSD — this scanner creates a ton of data (about 35 MB/s). 

IMPORTANT: External SSD (and HDD) can cause power shortages (and glitches) on the Raspi, since the continuous writing of large files is uncommon stress for the Raspi (which also drives a camera and is busily processing image data). You really need a 5V/27W Power Supply for the Raspi (not the standard 15W one), or you'll need to connect your external drive via an active USB3 Hub. This also eliminates power problems.

#### The electronics
Ebay and/or AliExpress are good sources here, depending on how long you can wait and/or risk counterfeits...
- Arduino Pro Mini (AtMega328P) 3.3V / 8 MHz
- 8 momentary switches (push buttons)
- Constant Current Board for the LED
- DRV8871 BoB to drive the projector DC motor
- 74HC14 Schmitt Trigger
- QRE1113 BoBs (Sparkfun or Synkino)
- 2 small Rectifiers and some passives 
- Some 40x40mm Heatsink and Chipset Fan

or, get the ready-to-go controller PCB from me.

# Code!
Anyway, this repository is for the software part of the project, consisting of four parts:

1. The actual Scan Software that turns your Rasberry Pi with its HQ Cam into a digital camera, shooting 12-Bit Raw photos of ach film frame, either in 4K or 2K (much faster)
3. The Arduino Software that controls your sacrificed projector and acts as the "glue" between the Raspberry Pi, the Camera, the Projector, and all controls.

## Installation
To get ready, you need to install software on all three parts of the system. In fact, this sscanner is actually using three reaal computers. :)

### For the Arduino
- Arduino IDE, arduino-cli or the Arduino Extension for VSCode — or whatever you like to use to get your compiled AVR binaries onto the AtMega328P. It doesn't matter, the IDE is probably the easiest way: Open the `scan-controller.ino` file from the repo, hit "Upload" and you are done. Alternatively, the Raspi can directly flash the ready-to-go controller PCB from me, if needed (it is already flashed, though)

### On your Computer
A computer is only required to process the scan into a video. This includes any of cutting editing color grading, audio dubbing, compression and delivery / sharing.

Instead of scanning to a hard-drive, you can optionally also scan directly to your computer via an Ethernet Connection. I have only tested this on a Mac, but it should work flawlessly with Linux too, and with a bit of poking definitely on Windows, too. I don't use Windows, though. For the beginning, just scan to an external drive.

Just in case you want to scan directly to your computer:
- You will need rsync 3.x installed. MacOS comes with rsync, but for licensing reasons, it's version 2.9.6 and that's too old for our purposes. 
- You will need to "pair" your Scanner with your computer, and allow the scanner to login to cour computer ("enable ssh").
Both can easily be enabled by running host-computer/install_remote_scanning.sh from Terminal, once. 
- Note that you cannot scan via Wifi. Wifi is too slow for this, especially on the Raspi. You will need to use an Ethernet cable. If you don't have Ethernet infrastructure in your house, you can also connect the Raspi directly with your computer with an Ethernet cable. (TBC)

There are other helper scripts that you'll only need when scanning "in host mode" (to your computer):
- helper/pair.sh starts the parining process. It exchanges a ssh key pair with your raspi and sets the path for where you want your scans to go.
- helper/unpair.sh eliminates an existing pairing. Only needed if your computer or scanner changes or you run into other connectivity probelms.
- helper/set_scan_destination.sh changes the path where you want your incoming scans to go.

To enable host mode, you will need to pull GPIO05 to GND. This can easily be achieved with a jumper like this: [image]

### On the Raspberry Pi:

Note that you need a Raspberry Pi 4 B to use this software — ideally with 4 or more GB of RAM. 4 GB is totally sufficient, 8 GB won't bring you more speed or quality. 2 GB might work, but I haven't tested it yet. A Raspberry 5 shoudl work too, but I don't have one and hence could not test it.

For the Raspi, download the image file and flash it onto a good uSD-card using Belena Etcher or a similar tool. I recommend the golden Samsung cards for great performance and reliability.

## Connections
- Connect I<sup>2</sup>C from Arduino with SMBus Pins on Raspi
- Connect GND to have a common ground
- ..
- Ethernet (for updates, time, etc)

## Configuration
...

## System Setup: Get ready to scan!
- Connect Ethernet Cable to Hub or Mac
- Powerup Raspi
- Enable Internet Sharing since the Raspi needs Internet (Time, Updates, Packages etc.)
- Close Aperture two stops (e.g. to 5.6 or 8). Smaller apertures will cause severe diffraction blurring and is not recommended.
- TBC

## Using CinemaDNG
** outdated **
- Create a new Project
- Go to File -> Project Settings
- Set the Timeline Resolution to `4096 x 3112 Full Aperture`
- Set the Timeline and Playback Framerate to 16, 18, 24 fps or whatever matches your scanned footage (16 or 18 are okay, no frame interpolation needed!)
- Project Settings -> Camera RAW:
  - RAW Profile: CinemaDNG
  - Decode using Project 
  - White Balance: Daylight
  - Use Color Space Rec.709
  - Use Gamma = Gamma 2.4
  - Enable Highlight Recovery
  - Midtone Detail 25, Sharpness 25
  - Optional: Sharpness & Midtone Detail up


- Open the "Media" tab, open your scan folder in the file browser pane on the left
- Drag and Drop the Project Folder (e.g. `2022-12-19T13_18_44 @4K`) onto the Mediapool at the bottom
- Go to the "Cut" Tab and drag the clip onto your timeline. Happy editing!
- Enjoy grading 12 bit Raws! (TBC)

- For negatives, use my convert plugin
- Go to the "Color" Tab
- Click on "Effects" in the top right
- Scroll down to the ColorNegInvert effect and drag it to the Node area. Make it the first Node (except Denoise, whcih shoudl always be first-first)

The three sliders “Mask color” define the RGB values of the color that is substracted. To start with, one can put the three sliders to the maximum value and then bring them back one by one towards the left. For each channel, when you go towards the left, there is a point where the image stops being modified : stop there. Once the three channels approximately tuned, refine by moving each one slowly from right to left and left to right : one can sense the moment when the image goes from red to cyan, from green to magenta and from blue to yellow.

- When Grading Reversal film, check the "Camera Raw" tool on the very left. If you chose "Decode Using: Clip", you can adjust DNG parameters simliar to Lightroom (but not exactly equal to). This is useful for a first base correction. Especially te "Lift" and "Gain" sliders are useful. (For negative film, the slider woudl all wrok inverted — it's better to use Davincis own grading here.)
- You usually want to tick the "Highlight Recovery" Checkbox in the "Camera Raw" tool. watch any frame with blown-out highlights to see its doing its magic.

- Use WHite Balance = Daylight
- Use Color Space Rec.709
- Use Gamma = Gamma 2.4

## Make the Raspi a AVR Porgrammer
- `sudo apt-get install avrdude` does not work – 7.1 does not support gpiod.
- clone avrdude main from git and run ./build.sh after having libgpiod-dev installed.
- copy the global config to ~.
- make sure the Arduino currently has power!
- edit existing raspi config like this:
````
#------------------------------------------------------------
# Program from a Raspberry Pi GPIO port using linuxgpio
#------------------------------------------------------------

programmer # raspberry_pi_gpio
    id                     = "raspberry_pi_gpio";
    desc                   = "Raspberry Pi GPIO via sysfs/libgpiod";
    type                   = "linuxgpio";
    prog_modes             = PM_ISP;
    connection_type        = linuxgpio;
    reset                  = 12;
    sck                    = 24;
    sdo                    = 23;
    sdi                    = 18;
;
````
- sudo avrdude -C ~/avrdude_gpio.conf -p atmega328p  -c raspberry_pi_gpio -P gpiochip0  -vvvv


Build:
cd ~/Filmkorn-Raw-Scanner
arduino-cli compile --fqbn arduino:avr:pro:cpu=8MHzatmega328 --export-binaries scan-controller

Flash:
sudo avrdude \
  -C ~/avrdude_gpio.conf \
  -p atmega328p \
  -c raspberry_pi_gpio \
  -P gpiochip0 \
  -U flash:w:scan-controller/scan-controller.ino.with_bootloader.hex:i

Or, what we just built:
-U flash:w:scan-controller/build/arduino.avr.pro/scan-controller.ino.with_bootloader.hex:i


## Raspi Architecture
The scanner comes with a couple of systemd services and helper scripts and services:
- raspi/systemd/install_services.sh installs all the services properly. Do not forget to run this script if you hack any changes into the services residing in the repository.
- filmkorn-lsyncd.service takes care of getting scanned results written onto your hard drive or your host computer
- filmkorn-ramdisk.service creates a ramdisk that we scan to. This avoids wear on the uSD card ans is clearly the fastest way to write a way the huge DNG files.
- filmkorn-scanner.service is the scanner app itself. It coordinates all the things, kinda the "run loop" of this contraption
- filmkorn-sleep.service saves power and turns the camera and display off when not in use
- filmkorn-wake.service does the opposite
- usb-mount-largest@.service identifies the biggest partition on a connected drive and mounts it. extFS and ext4 are supported — NTFS is just too slow.

The other scripts you'll find are helpers that are called directly by the services, if needed. 'scanner.py' is where the brains are. 
