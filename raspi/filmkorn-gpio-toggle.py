#!/usr/bin/env python3
import subprocess
import time

import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)
BUTTON_PIN = 26
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

last_press = 0.0

def _run(cmd):
    subprocess.run(cmd, check=False)

def _handle_button(_channel):
    global last_press
    now = time.monotonic()
    if now - last_press < 1.0:
        return
    last_press = now
    scanner_active = subprocess.run(
        ["systemctl", "is-active", "--quiet", "filmkorn-scanner.service"]
    ).returncode == 0
    if scanner_active:
        _run(["systemctl", "start", "filmkorn-sleep.service"])
    else:
        _run(["systemctl", "start", "filmkorn-wake.service"])

GPIO.add_event_detect(BUTTON_PIN, GPIO.FALLING, callback=_handle_button, bouncetime=250)

try:
    while True:
        time.sleep(1)
finally:
    GPIO.cleanup()
