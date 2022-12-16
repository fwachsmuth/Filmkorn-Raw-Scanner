# Piscanuino

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
    ````
Host *
  AddKeysToAgent yes
  IdentityFile ~/.ssh/id_rsa_piscan
  ```
- Enable ssh from Mac to Raspi
- Raspi: Install lsync
- Mac: Update rsync (2.6.9 is too old, need 3.x): `brew install rsync` which goes into in `/opt/homebrew/bin/rsync` (ref'd as such in lsync.conf)
- ...
- Profit


## System Setup
1. Powerup Raspi
2. Powerup Arduino via FTDI
3. Connect Ethernet to Mac
4. Enable Internet Sharing if the Raspi needs Internet (Time, Updates, Packages etc.)
4. Mac: Set eth-if to `192.168.2.1` (Raspi is `192.168.2.2`)
5. Mac: **Enable** Settings -> General -> Sharing -> Remote Login
5. 
5. (Projektor starten)
6. Raspi: `cd /home/pi/code/Piscanuino`
7. Raspi: Adjust Target Path in `lsyncd.conf` if needed – note that the Target drive can not be APFS!
7. Raspi: `lsyncd lsyncd.conf``


 1019  /usr/bin/python3 /home/pi/code/Piscanuino/piscan.py






## Backup and Restore a uSD on a Mac
Use ApplePiBaker, or 
```
diskutil list
sudo dd if=/dev/disk6 of=~/PiscanuinoSDCardBackup.dmg
````
resp.
````
diskutil unmountDisk /dev/disk6
sudo dd if=~/PiscanuinoSDCardBackup.dmg of=/dev/disk6
```
