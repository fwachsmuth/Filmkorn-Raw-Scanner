#!/bin/bash

# !!!!!!!
# Make sure to run this on the Raspi, which will directly flash the AtMega328 on the connected controller board.
# !!!!!!!

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



log() {
  echo "flash-atmega328: $*"
}

HEX_PATH="/home/pi/Filmkorn-Raw-Scanner/scan-controller/build/arduino.avr.pro/scan-controller.ino.with_bootloader.hex"
CONF_PATH="/home/pi/Filmkorn-Raw-Scanner/scan-controller/avrdude_gpio.conf"

if [ ! -f "$HEX_PATH" ]; then
  echo "Missing hex: $HEX_PATH" >&2
  exit 2
fi

log "Attempting verification without stopping service."
if sudo /usr/local/bin/avrdude \
  -C "$CONF_PATH" \
  -p atmega328p \
  -c raspberry_pi_gpio \
  -P gpiochip0 \
  -U "flash:v:${HEX_PATH}:i"
then
  echo "ATmega328P flash already matches ${HEX_PATH}, skipping."
  exit 0
fi
    
# Burn uC Code & bootloader 
# This is for the new, self-built avrdude 8.1 with libgpiod support.
# Fuse setting still needs to be tested!!!! 
sudo /usr/local/bin/avrdude \
  -C "$CONF_PATH" \
  -p atmega328p \
  -c raspberry_pi_gpio \
  -P gpiochip0 \
  -U "flash:w:${HEX_PATH}:i"
