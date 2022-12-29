# To Dos

## For Image Generation
- Adjust identity key path in lsyncd.conf
- Test camera.preview_window = (0, 0, 640, 480) per https://picamera.readthedocs.io/en/release-1.13/deprecated.html?highlight=start_preview#preview-functions
- Try $ sudo systemctl disable getty@tty1.service
- image creation pre-flight:
    - remove my keys from ~/.ssh: `rm ~/.ssh/id_filmkorn-scanner_ed25519*`
    - and my dev key for git
    - remove history
OR use -p on a linux PiShrink
`sudo xz -zkv3T8 /Users/peaceman/Filmkorn-Scanner-small.img` keeps original and is verbose. 6 might be better but takes 2.3x longer at ~15% gain

- remove dash from password?






## General
- [ ] Make the Shutter Speed adjustable (pot?)

## Housekeeping:
- [ ] Document bootstrapping/installation on Raspi & Mac
- [ ] Draw Schematics already
- [ ] Readmes anpassen


## Raspi Todos:
- [ ] Update Raspi OS
- [ ] Let piscan.py also start lsyncd (as daemon?)
- [ ] Enable DHCP client instead of manual IP (and )

- [ ] Samba Share funktionierend machen
- [ ] lsync als daemon starten
- [ ] clear screen on boot / start my python code
- [ ] consider not writing to SD (wear), but to Ramdisk or external drive
- [ ] find out why the occasional slow writes happen
- [ ] Let Preview Mode use dynamic exposure to allow easier focus adjustments
- [ ] Make OSError in ask_arduino more specific (errno)
- [ ] Support setting a destination path / host

 
## Hardware
- [ ] Rastkugeln im Objektivgang ausbauen
- [ ] Arduino braucht FTDI Power — why?
- [ ] Staubschutzhaube bauen
- [ ] 1x Netzstrom wäre schön
- [ ] Fix the Fan mount
- [ ] Analyze i2c signal intergity with oscilloscope (pullups?)
- [ ] Switch for pos / neg
- [ ] switch for hd / rsync
- [ ] Exposure Adjustment via pot
- [ ] Add Film end Detector
- [ ] Add XOR Gate to Lamp/Fan Out to turn off Lamp when fan is not running
- [ ] Redesign Lens Mount to allow cleaning the gate again
- [ ] Trafo-Brumm beseitigen
- [ ] Try shorter camera cable


## Notes for future use:
- [ ] Enable Screen before Scan: `/opt/vc/bin/tvservice -p` (Display an)
- [ ] Disable Screen after Scan: `/opt/vc/bin/tvservice -o` (Display aus)
### Backup and Restore a uSD on a Mac
Use ApplePiBaker, or 
```
diskutil list
sudo dd if=/dev/disk6 of=~/PiscanuinoSDCardBackup.dmg
```
resp.
```
diskutil unmountDisk /dev/disk6
sudo dd if=~/PiscanuinoSDCardBackup.dmg of=/dev/disk6
```

## Remote execution snippets
https://www.cyberciti.biz/faq/unix-linux-execute-command-using-ssh/
ssh pi@piscan2.local -t python3 /home/pi/Filmkorn-Raw-Scanner/raspi/scanner.py
ssh pi@piscan2.local "lsyncd ~/Filmkorn-Raw-Scanner/raspi/lsyncd.conf &" # doesn't go to background yet.
ssh -f pi@piscan2.local "nohup lsyncd ~/Filmkorn-Raw-Scanner/raspi/lsyncd.conf > /dev/null 2>&1 &" works
or cleaner: ssh -n -f user@host "sh -c 'cd /whereever; nohup ./whatever > /dev/null 2>&1 &'"

ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no pi@piscan2.local

### Flow draft:
#### Initial keypair creation: 
`` `ssh-keygen -t ed25519 -f ~/.ssh/id_filmkorn-scanner_ed25519 -C scanning-`whoami`@`hostname -s` -N ''` ``
`ssh-copy-id -i ~/.ssh/id_filmkorn-scanner_ed25519.pub pi@filmkorn-scanner.local` yes / filmkorn-rocks

```
cat <<EOT >> ~/.ssh/config
Host filmkorn-scanner.local
  IdentityFile ~/.ssh/id_filmkorn-scanner_ed25519
  StrictHostKeyChecking no
EOT
```
`sudo launchctl stop com.openssh.sshd` ??
`sudo launchctl startp com.openssh.sshd` ??
`ssh pi@filmkorn-scanner.local "ssh-keygen -t ed25519 -f ~/.ssh/id_filmkorn-scanner_ed25519 -C pi@filmkorn-scanner -N ''"`
`` `ssh pi@filmkorn-scanner.local -t "ssh-copy-id -i ~/.ssh/id_filmkorn-scanner_ed25519.pub `whoami`@`hostname -s`.local"` ``





~create /etc/ssh/sshd_config with password allowed~
add keys
exchange /etc/ssh/sshd_config
restart sshd `sudo systemctl restart sshd`