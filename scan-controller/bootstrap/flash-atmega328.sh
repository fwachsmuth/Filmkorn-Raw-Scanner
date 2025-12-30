#!/bin/bash

# !!!!!!!
# Make sure to run this on the Raspi, which will directly flash the AtMega328 on the connected controller board.
# !!!!!!!

# Let's stop the scanner service while we flash the microcontroller to free up the GPIOs and avoid interference
SERVICE_NAME="filmkorn-scanner.service"
sudo systemctl stop "$SERVICE_NAME"
cleanup() {
  sudo systemctl start "$SERVICE_NAME"
}
trap cleanup EXIT


# writing Fuses
# The below doesn't seem to work when run from a raspi, probably due to programming voltage being too low (~3.2V)
# It might also be a problem with the older Version 6.3-20171130 running on the raspi. IDE uses 6.3-20190619!
# Meanwhile, we need to burn the fuses using an external programmer.
#
# sudo avrdude \
#     -C ~/Filmkorn-Raw-Scanner/scan-controller/bootstrap/avrdude_gpio.conf \
#     -v \
#     -p atmega328p \
#     -c pi_1 \
#     -e \
#     -U lock:w:0x3F:m \
#     -U efuse:w:0xFD:m \
#     -U hfuse:w:0xDA:m \
#     -U lfuse:w:0xFF:m 

python3 - <<'PY'
import RPi.GPIO as GPIO

UC_POWER_GPIO = 16  # GPIO16 (physical pin 36) enables µC power switch on the controller PCB
GPIO.setmode(GPIO.BCM)
GPIO.setup(UC_POWER_GPIO, GPIO.OUT, initial=GPIO.HIGH)
PY
    
# Burn uC Code & bootloader 
# This is for the new, self-built avrdude 8.1 with libgpiod support.
# Fuse setting still needs to be tested!!!! 
sudo avrdude \
  -C ~/avrdude_gpio.conf \
  -p atmega328p \
  -c raspberry_pi_gpio \
  -P gpiochip0 \
  -U flash:w:scan-controller/scan-controller.ino.with_bootloader.hex:i

# use scan-controller.ino.hex for a faster start without bootloader, but no serial programming possible.
