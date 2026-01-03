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

# If GPIO16 (uC power) is already high, skip stopping the service and re-driving it.
gpio16_level() {
  sudo python3 - <<'PY'
try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(16, GPIO.IN)
    print(1 if GPIO.input(16) else 0)
except Exception as exc:
    import sys
    print(f"ERR:{exc}", file=sys.stderr)
    print(0)
PY
}

set_gpio16_high() {
  python3 - <<'PY'
try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(16, GPIO.OUT, initial=GPIO.HIGH)
except Exception:
    pass
PY
}

GPIO16_LEVEL="$(gpio16_level || true)"
log "GPIO16 level=${GPIO16_LEVEL:-unknown}"
if [ "$GPIO16_LEVEL" = "1" ]; then
  log "GPIO16 already high; skipping service stop and power toggle."
  SKIP_SERVICE_RESTART=1
else
  if [ -z "${SKIP_SERVICE_RESTART:-}" ]; then
    SERVICE_NAME="filmkorn-scanner.service"
    log "Stopping ${SERVICE_NAME} to power MCU."
    sudo systemctl stop "$SERVICE_NAME"
    cleanup() {
      log "Starting ${SERVICE_NAME} after flashing."
      sudo systemctl start "$SERVICE_NAME"
    }
    trap cleanup EXIT
  fi
  log "Setting GPIO16 high to power MCU."
  set_gpio16_high
fi

HEX_PATH="/home/pi/Filmkorn-Raw-Scanner/scan-controller/build/arduino.avr.pro/scan-controller.ino.with_bootloader.hex"
CONF_PATH="/home/pi/Filmkorn-Raw-Scanner/scan-controller/avrdude_gpio.conf"

if [ ! -f "$HEX_PATH" ]; then
  echo "Missing hex: $HEX_PATH" >&2
  exit 2
fi

quick_bytes="$(sudo /usr/local/bin/avrdude \
  -C "$CONF_PATH" \
  -p atmega328p \
  -c raspberry_pi_gpio \
  -P gpiochip0 \
  -U flash:r:-:r 2>/dev/null | head -c 16 | od -An -tx1 | tr -d ' \n' || true)"

if [ -n "$quick_bytes" ] && [ "$quick_bytes" = "ffffffffffffffffffffffffffffffff" ]; then
  echo "ATmega328P flash appears empty (first 16 bytes are 0xFF), flashing."
else
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
