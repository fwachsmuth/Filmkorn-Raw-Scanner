#!/bin/bash
set -euo pipefail

echo "Building ne hex, flashing ino, committingand pushing it."

arduino-cli compile --fqbn arduino:avr:pro:cpu=8MHzatmega328 --export-binaries scan-controller
sudo avrdude   -C ~/avrdude_gpio.conf   -p atmega328p   -c raspberry_pi_gpio   -P gpiochip0   -U flash:w:scan-controller/build/arduino.avr.pro/scan-controller.ino.with_bootloader.hex:i
