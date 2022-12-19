# Filmkorn Raw-Scanner

## What is this?
The Filmkorn Raw-Scanner, formerly known as Piscanuino, is an open source solution to make film scanning in amazing quality possible at a lowe price. In factm the project originated from [a bet](https://www.filmvorfuehrer.de/topic/31851-challenge-framescanner-f%C3%BCr-350%E2%82%AC-bauen/): *Is it possible to build a high quality film scanner for < 350 €?*

Well, it is, but this bet was won in 2020. Prices for many thing have gone up since then, so you might need to plan for a bit more, or get creative to stay within this budget.

Anyway, this repository is for the software part of the project, consistint of four parts:

1. The actual Scan Software that turns your Rasberry Pi with its HQ Cam into a digital camera, shooting one 4K 12-Bit Raw photo approximately every 0.6 seconds and transferring it to your main computer for further processing
2. The Converter Software for your Mac that converts the incoming Raw files from their proprietary format into 4K CinmaDNG format, which can directly be imported into e.g. Davinci Resolve. Note that this is a lossless format with 12 Bit per color channel, so really really good (and big)
3. The Arduino Software that controls your sacrificed projector and acts as the "glue" between the Raspberry Pi, the Camera, the Projector, and all controls.

In addition to the software coming with this repo, you will need a couple of other libraries and tools, as mentioned in this Readme. 

**Note that my main computer is a Mac, and that's what I am describing here, but nothing Mac-specific is actually needed. It should be totally possible (and rather easy) to use Windows or even Linux instead, too — if you do so, please share your Notes or create a PR to this Readme.**

## Installation
To get ready, you need to install software on all three parts of the system. In fact, this sscanner is actually using three reaal computers. :)

### For the Arduino
- Arduino IDE, arduino-cli or the Arduino Extension for VSCode — or whatever you like to use to get your compiled AVR binaries onto the AtMega328P. It doesn't matter, the IDE is probably the easiest way: Open the `scan-controller.ino` file from the repo, hit "Upload" and you are done.

### On your Mac
You should use the same Mac that also runs Davinci Resolve, wo you don't have to move tons of data around. The conversion process isn't crazy expensive, but not free either. On my intel iMac late 2015 with 4 GHz and 32 GB of RAM, the conversion was about as fast as the scanner delivered files, so it made a lot of sense to convert during scanning. On my current Apple Silicon MacBook Pro, conversion is so crazy fast that I don't mind converting after scanning has finished. :) 

- First of all, you will need [Homebrew](https://brew.sh/) to install the below things easily. If you don't have it yet, install it as described on the Homebrew website. If you have it but it is no longer working, use `brew doctor` until it works again.
- `rsync 3.x` since the `rsync 2.9.6` that Apple ships (even in macOS Ventura 13.0.1) is not comaptible with `lsync`. Install it via `brew install rsync` and note down where it gets installed (should be `/opt/homebrew/bin/rsync`, but brew likes to change its base paths)
- `python3` (latest should be fine, I'm using 3.10.9 right now). Install via `brew install python3` if you don't have it yet. If you are unsure, `` `which python3` --version `` or `` `which python` --version `` should tell you what version(s) you have already installed, and how they are called. Once Python 3 is installed, add the following two packages (they will bring quite some dependencies):
  - `PiDNG` in version 3.4.7, which is ancient and yanked, but works. Newer versions broke support for the HQ Cam and are not working at this point. Just type `pip3 install pidng==3.4.7` and you should be all set.
  - `watchdog`. `pip3 install -U watchdog` does the trick.

### On the Raspberry Pi:
Note that you need a Raspberry Pi 4 to use this software — ideally with 4 GB of RAM. More never hurts, less is untested and not a good idea. We are cretaing and handling a ton of data here.

*(Task list to be completed)*
- Raaspbian 10
- use raspi-conf to set foo and bar and baz.
  - foo
  - bar
  - baz
- `python3` (latest should be fine, I'm using 3.10.9 right now)
- `python3-smbus` to make python talk I<sup>2</sup>C 
- `python3-picamera` for support of the Raspi HQ Camera
- `lsync`

## Connections
- Connect I<sup>2</sup>C from Arduino with SMBus Pins on Raspi
- Connect GND to have a common ground


## Configuration
### Installation Steps (incomplete)
- Enable ssh from rapsi to Mac: `ssh-copy-id -i .ssh/id_rsa_piscan.pub peaceman@192.168.2.1`
- Enable key auth via `.ssh/config`: 
  ```
  Host *
  AddKeysToAgent yes
  IdentityFile ~/.ssh/id_rsa_piscan
  ```
- Enable ssh from Mac to Raspi
- ...
- Profit

## System Setup: Get ready to scan!
- Powerup Raspi
- Powerup Arduino (currently via FTDI)
- Connect Ethernet Cable to Mac
- Enable Internet Sharing since the Raspi needs Internet (Time, Updates, Packages etc.)
- Mac: Set eth-if to `192.168.2.1` (Raspi is `192.168.2.2`)
- Mac: **Enable** Settings -> General -> Sharing -> Remote Login, then click (i) and enable "Allow full disk access for remote users" 
- "Start" the Projector by pushing its "Fwd" Key. This gives power on the transformer. 
- Set Aperture to 8. Smaller apertures will cause severe diffraction blurring and is not recommended.
- Check `camera.shutter_speed` in scanner.px (on the Raspi)
- Raspi: `cd /home/pi/code/Filmkorn-Raw-Scanner/raspi`
- Raspi: Adjust Target Path in `lsyncd.conf` if needed
- Raspi: `lsyncd lsyncd.conf &`. (Using a separate shell here might make sense to let lsync not bleed into the scanner's log output)
- Raspi: `python3 /home/pi/code/Filmkorn-Raw-Scanner/raspi/scanner.py`
- Mac: `python3 cineDNG_creator.py -i /Volumes/Filme/raw-intermediates/ -o /Volumes/Filme/CinemaDNG/. --cinema-dng --keep-running`

## Using CinemaDNG
*(incomplete)*
- Set your Project Resolution to "4K wide aperture"
- Set your Project fps to match (16 or 18 are okay, no frame interpolation needed)
- Open the "Media" tab, open CinemaDNG folder in the file browser pane on the left
- Drag and Drop onto Timeline
- Note the "Camera Raw" tool in the Color Tab (Lift, Gain)
- Enjoy 12 bit Raws
- FOr negatives, use my convert plugin
