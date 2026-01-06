#!/bin/bash
set -euo pipefail

echo "Building ne hex, flashing ino, committing, and pushing it."

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

arduino-cli compile --fqbn arduino:avr:pro:cpu=8MHzatmega328 --export-binaries scan-controller
sudo avrdude   -C "${REPO_DIR}/scan-controller/avrdude_gpio.conf"   -p atmega328p   -c raspberry_pi_gpio   -P gpiochip0   -U flash:w:scan-controller/build/arduino.avr.pro/scan-controller.ino.with_bootloader.hex:i

git -C "$REPO_DIR" add scan-controller/build/arduino.avr.pro/scan-controller.ino.hex
git -C "$REPO_DIR" add scan-controller/build/arduino.avr.pro/scan-controller.ino.with_bootloader.hex
git -C "$REPO_DIR" commit -m "new hex files"
git -C "$REPO_DIR" push origin master

echo "Don't forget to pull on the host."
