#!/bin/bash

# !!!!!!!
# Make sure to run this on the Raspi, which will directly flash the AtMega328 on the connected controller board.
# !!!!!!!

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

# Burn uC Code & bootloader 
# This is for old avrdude 6 in /usr/bin/avrdude
# sudo avrdude \
#   -C ~/Filmkorn-Raw-Scanner/scan-controller/bootstrap/avrdude_gpio.conf \
#   -v \
# 	-p atmega328p \
# 	-c pi_1 \
# 	-U flash:w:scan-controller-v1.0.ino.hex:i
    
# Burn uC Code & bootloader 
# This is for new avrdude 7 in /usr/local/bin/avrdude
# Fuse setting still  NOT WORKING!!!! 
# avrdude -C avrdude7.conf -v -p atmega328p -c raspberry_pi_gpio -e -U lock:w:0x3F:m -U efuse:w:0xFD:m -U hfuse:w:0xDA:m -U lfuse:w:0xFF:m
avrdude -C avrdude7.conf \
	-v \
	-p atmega328p \
	-c raspberry_pi_gpio \
	-U flash:w:scan-controller-v1.0.ino.hex:i
