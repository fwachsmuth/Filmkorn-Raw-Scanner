# Filmkorn Raw-Scanner

## What is this?
The Filmkorn Raw-Scanner, formerly known as Piscanuino, is an open source solution to make film scanning in amazing quality possible at a lowe price. In factm the project originated from [a bet](https://www.filmvorfuehrer.de/topic/31851-challenge-framescanner-f%C3%BCr-350%E2%82%AC-bauen/): *Is it possible to build a high quality film scanner for < 350 €?*

Well, it is, but this bet was won in 2020. Prices for many thing have gone up since then, so you might need to plan for a bit more, or get creative to stay within this budget.

Anyway, this repository is for the software part of the project, consistint of four parts:

1. The actual Scan Software that turns your Rasberry Pi with its HQ Cam into a digital camera, shooting one 4K 12-Bit Raw photo approximately every 0.6 seconds and transferring it to your main computer for further processing
2. The Converter Software for your Mac that converts the incoming Raw files from their proprietary format into 4K CinmaDNG format, which can directly be imported into e.g. Davinci Resolve. Note that this is a lossless format with 12 Bit per color channel, so really really good (and big)
3. The Arduino Software that controls your sacrificed projector and acts as the "glue" between the Raspberry Pi, the Camera, the Projector, and all controls.

In addition to the software coming with this repo, you will need a couple of other libraries and tools, as mentioned in this Readme. 
==Note that my main computer is a Mac, and that's what I am describing here, but nothing Mac-specific is actually needed. It should be totally possible (and rather easy) to use Windows or even Linux instead, too — if you do so, please share your Notes or create a PR to this Readme.==


Some of the required software:

Raspberry Pi APT packages:
- python3
- python3-smbus
- python3-picamera

To run convert.py:
- Python 3
- [PyDNG](https://github.com/schoolpost/PyDNG) ~2020
- watchdog (will be added eventually)

Arduino:
- Arduino 2.0 IDE

## Installation Steps (incomplete – see raspis history.txt)
- Enable ssh from rapsi to Mac: `ssh-copy-id -i .ssh/id_rsa_piscan.pub peaceman@192.168.2.1`
- Enable key auth via `.ssh/config`: 
  ```
  Host *
  AddKeysToAgent yes
  IdentityFile ~/.ssh/id_rsa_piscan
  ```
- Enable ssh from Mac to Raspi
- Raspi: Install lsync
- Mac: Update rsync (2.6.9 is too old, need 3.x): `brew install rsync` which goes into in `/opt/homebrew/bin/rsync` (ref'd as such in lsync.conf)
- Mac: `pip3 install pidng==3.4.7`
- Mac: `python3 cineDNG_creator.py -i /Volumes/Filme/raw-intermediates/ -o /Volumes/Filme/CinemaDNG --cinema-dng --keep-running`
- Mac: `pip3 install -U watchdog`



- ...
- Profit

## System Setup: Get ready to scan!
- Powerup Raspi
- Powerup Arduino via FTDI
- Connect Ethernet to Mac
- Enable Internet Sharing if the Raspi needs Internet (Time, Updates, Packages etc.)
- Mac: Set eth-if to `192.168.2.1` (Raspi is `192.168.2.2`)
- Mac: **Enable** Settings -> General -> Sharing -> Remote Login, then click (i) and enable "Allow full disk access for remote users" 
- (Projektor starten)
- Blende auf 11
- Check `camera.shutter_speed` in scanner.px (on the Raspi)
- Raspi: `cd /home/pi/code/Piscanuino`
- Raspi: Adjust Target Path in `lsyncd.conf` if needed – note that the Target drive can not be APFS!
- Raspi: `lsyncd lsyncd.conf &`
- Raspi: `python3 /home/pi/code/Piscanuino/piscan.py`
- Mac: `python3 cineDNG_creator.py -i /Volumes/Filme/raw-intermediates/ -o /Volumes/Filme/CinemaDNG/. --cinema-dng --keep-running`

