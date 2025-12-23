#!/usr/bin/python3

# For use from the login console, when not running X Windows.

import time
import RPi.GPIO as GPIO

from time import sleep

from picamera2 import Picamera2, Preview
from libcamera import Transform, controls

# --- Controller MCU (ATmega328P) Power Switch ---
UC_POWER_GPIO = 16  # GPIO16 (physical pin 36) enables µC power switch on the controller PCB
UC_POWER_BOOT_DELAY_S = 0.5  # allow the ATmega328P to boot before first I2C transaction
# Set the GPIO mode to BCM
GPIO.setmode(GPIO.BCM)
GPIO.setup(UC_POWER_GPIO, GPIO.OUT, initial=GPIO.HIGH)
sleep(UC_POWER_BOOT_DELAY_S)

picam2 = Picamera2()

picam2.start_preview(Preview.DRM, x=80, y=0, width=640, height=480)

preview_config = picam2.create_preview_configuration(
    transform=Transform(rotation=180, hflip=True, vflip=False)
)

picam2.configure(preview_config)

picam2.start()
time.sleep(30)