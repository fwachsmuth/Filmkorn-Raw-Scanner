#!/bin/bash

# !!!!!!!
# Make sure to run this on the Host Computer, not on the Raspi, using a propoer 5V Prorgammer like the AVRISP mkII.
# Due to a voltage mismatch (Pi is 3.3V logic), a vanilla ATmega won’t read MISO correctly and would need level shifting to 5V.
# !!!!!!!

# Burn fuses using avrdude 8.1 from brew install avrdude
/Users/peaceman/Library/Arduino15/packages/arduino/tools/avrdude/6.3.0-arduino17/bin/avrdude -C/Users/peaceman/Library/Arduino15/packages/arduino/tools/avrdude/6.3.0-arduino17/etc/avrdude.conf -v -patmega328p -cstk500v2 -Pusb -e -Ulock:w:0x3F:m -Uefuse:w:0xFD:m -Uhfuse:w:0xDA:m -Ulfuse:w:0xFF:m 



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



