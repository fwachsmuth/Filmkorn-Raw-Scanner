#!/bin/bash
# When the Arduino IDE creates it's final avrdude line, navigate to the hex' parent directory and look out for the .with_bootloader hex to retain serial programming support.

# !!!!!!!
# Make sure to run this on the Raspi, which will directly flash the AtMega328 on the controller board.
# !!!!!!!

# writing Fuses
sudo avrdude \
    -C ~/avrdude_gpio.conf \
    -v \
    -p atmega328p \
    -c pi_1 \
    -e \
    -U lock:w:0x3F:m \
    -U efuse:w:0xFD:m \
    -U hfuse:w:0xDA:m \
    -U lfuse:w:0xFF:m 


# Burn uC Code & bootloader
sudo avrdude \
    -C ~/avrdude_gpio.conf \
    -v \
	-p atmega328p \
	-c pi_1 \
	-U flash:w:scan-controller-v1.0.ino.hex:i
    