# Contributing

The project has three editing targets: 
* code that runs on the **host Mac** (`host-computer/`) (optional)
* code that runs on the **Raspberry Pi** (`raspi/`)
* code that runs on the Arduino-like micro controller board (`scan-controller/`). 

Changes flow through Git — push from the host, pull on the Raspi. Arduino firmware changes additionally require a compile and flash step directly on the Raspi.

## Recommended Editor: VS Code 

It let's you edit python, shell scripts as well as C code easily and comfortable, and has a built-in terminal to control the raspi or watch its logs. For Raspi control,
* `ssh pi@filmkorn-scanner.local` (after pairing to not need a password)
* `cd Filmkorn-Scanner` to enter the repo
* use a 2nd terminal with `journalctl -u filmkorn-scanner.service -f` to keep the raspi service logs in view.

## Prerequisites

Normal user pairing must have been completed first (run `host-computer/install_remote_scanning.sh`) so the host can reach `filmkorn-scanner.local` over SSH.

You also need a personal dev SSH key at `~/.ssh/id_filmkorn-scanner-dev_ed25519` on the host. This key is separate from the per-installation pairing key and is what authenticates you to GitHub from the Raspi. 

## One-Time Dev Setup: `install-dev-key.sh`

Run this once on the **host Mac** to bootstrap Git write access on the Raspi:

```bash
./host-computer/helper/dev/install-dev-key.sh
```

It copies your dev key to the Raspi, fixes permissions, seeds GitHub's host key into the Raspi's `known_hosts`, and then automatically calls `raspi/dev/enable-git-write.sh` on the Raspi, which:

- Switches the Git remote to the SSH URL (`git@github.com:fwachsmuth/Filmkorn-Raw-Scanner.git`)
- Configures `git user.email` and `git user.name` if not already set
- Adds a `github.com` block to `~/.ssh/config` that points at the dev key
- Verifies the GitHub SSH connection works

You can also run `raspi/dev/enable-git-write.sh` directly on the Raspi if you ever need to re-apply it.

## Editing `raspi/` Code

1. Edit files locally under `raspi/`
2. `git push origin master`
3. On the Raspi: `git -C ~/Filmkorn-Raw-Scanner pull`

Changes to `scanner.py` and helper scripts take effect on the next scanner service restart:

```bash
sudo systemctl restart filmkorn-scanner.service
```

 If you create/install/alter Systemd service definitions in `raspi/systemd/`, that additionally requires running `raspi/systemd/install_services.sh` after pulling to deploy them.

## Editing Arduino Firmware

1. Edit `scan-controller/scan-controller.ino` locally
2. `git push origin master` (source only — no need to compile locally)
3. On the Raspi, pull and then run:

```bash
git -C ~/Filmkorn-Raw-Scanner pull
~/Filmkorn-Raw-Scanner/raspi/dev/ino-update.sh
```

`ino-update.sh` compiles the sketch with `arduino-cli`, sets the EESAVE fuse so calibration data in EEPROM survives flashing, writes the firmware via `avrdude` over GPIO, then commits the resulting hex files and pushes them. After it finishes, pull on the host to pick up the updated hex files.

You can also flash the ino via the FTDI port on top left of the board, but using the raspi to do the programming is much more comfortable (unless you need a serial port for debugging, then FTDI is preferred)
