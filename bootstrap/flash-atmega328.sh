#!/bin/bash
# Mostly copied from "Burn Bootloader"

# !!!!!!!
# Make sure to run this on the Raspi, which will directly flash the AtMega328 on the controller board.
# !!!!!!!

# writing Fuses
sudo avrdude \
    -C ~/avrdude_gpio.conf \
    -v \
    -p atmega328p \
    -c pi_1 \
    -U lock:w:0x2F:m \
    -U efuse:w:0xFD:m \
    -U hfuse:w:0xD6:m \
    -U lfuse:w:0xF7:m 
# avrdude: safemode: lfuse reads as FF
# avrdude: safemode: hfuse reads as DA
# avrdude: safemode: efuse reads as FD


# Burn uC Code & bootloader
sudo avrdude \
    -C ~/avrdude_gpio.conf \
    -v \
	-p atmega328p \
	-c pi_1 \
	-U flash:w:~/bootstrap/scan-controller-v1.0.ino.hex:i