#!/bin/bash

# !!!!!!!
# Make sure to run this on the Raspi, which will directly flash the AtMega328 on the connected controller board.
# !!!!!!!

# Let's stop the scanner service while we flash the microcontroller to free up the GPIOs and avoid interference
if [ -z "${SKIP_SERVICE_RESTART:-}" ]; then
  SERVICE_NAME="filmkorn-scanner.service"
  sudo systemctl stop "$SERVICE_NAME"
  cleanup() {
    sudo systemctl start "$SERVICE_NAME"
  }
  trap cleanup EXIT
fi

# This is how we successfully flash in raspi/dev/ino-update.sh, so we replicate it here:
# run_and_log "flash" /usr/local/bin/avrdude \
#   -C /home/pi/Filmkorn-Raw-Scanner/scan-controller/avrdude_gpio.conf \
#   -p atmega328p \
#   -c raspberry_pi_gpio \
#   -P gpiochip0 \
#   -U flash:w:${HEX_PATH}:i

# Burn fuses

# sudo /usr/local/bin/avrdude \
#     -C /home/pi/Filmkorn-Raw-Scanner/scan-controller/avrdude_gpio.conf \
#     -p atmega328p \
#     -c raspberry_pi_gpio \
#     -P gpiochip0 \
#     -e \
#     -U lock:w:0x3F:m \
#     -U efuse:w:0xFD:m \
#     -U hfuse:w:0xDA:m \
#     -U lfuse:w:0xFF:m 

# Seems to lead to a Voltage mismatch: Pi is 3.3V logic. A vanilla Arduino/ATmega at 5V might need level shifting or it won’t read MISO correctly.



python3 - <<'PY'
import RPi.GPIO as GPIO

UC_POWER_GPIO = 16  # GPIO16 (physical pin 36) enables µC power switch on the controller PCB
GPIO.setmode(GPIO.BCM)
GPIO.setup(UC_POWER_GPIO, GPIO.OUT, initial=GPIO.HIGH)
PY
    
# Burn uC Code & bootloader 
# This is for the new, self-built avrdude 8.1 with libgpiod support.
# Fuse setting still needs to be tested!!!! 
sudo /usr/local/bin/avrdude \
  -C /home/pi/Filmkorn-Raw-Scanner/scan-controller/avrdude_gpio.conf \
  -p atmega328p \
  -c raspberry_pi_gpio \
  -P gpiochip0 \
  -U flash:w:scan-controller/build/arduino.avr.pro/scan-controller.ino.with_bootloader.hex:i
