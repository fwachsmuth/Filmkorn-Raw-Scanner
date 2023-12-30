#!/usr/bin/python3
"""Raspi-side Scan Control Glue communicating between Raspi, Arduino and the Raspi HQ Cam"""

from time import sleep
from typing import Optional
import argparse
import datetime
import enum
import errno
import subprocess
import sys
import time
import os

from smbus import SMBus
from picamera import PiCamera

# Has to end with /
RAW_DIRS_PATH = "/mnt/ramdisk/"
FIXED_SHUTTER_SPEED = 2000  # Todo: make this somehow controllable for other LEDs / Setups
DISK_SPACE_WAIT_THRESHOLD = 200_000_000  # 200 MB
DISK_SPACE_ABORT_THRESHOLD = 30_000_000  # 30 MB

# print ("\033c")   # Clear Screen

subprocess.Popen(["fim", "--quiet",  "-d",  "/dev/fb0", "/home/pi/Filmkorn-Raw-Scanner/images/ready-to-scan.png"])
# proc = subprocess.Popen(["rm","-r","some.file"]), then to kill: proc.terminate()


class Command(enum.Enum):
    # Arduino to Raspi
    IDLE = 0
    PING = 1

    Z1_1 = 2
    Z3_1 = 3
    Z10_1 = 4
    SHOOT_RAW = 5
    LAMP_OFF = 6
    LAMP_ON = 7
    INIT_SCAN = 8
    START_SCAN = 9
    STOP_SCAN = 10
    SET_EXP = 11

    # Raspi to Arduino
    READY = 128

class ZoomMode(enum.Enum):
    Z1_1 = 0
    
    Z3_1 = 1
    Z10_1 = 2

class State:
    def __init__(self):
        self._zoom_mode = ZoomMode.Z1_1
        self.raws_path: Optional[str] = None
        self.raw_count = 0
        self.continue_dir = False

    @property
    def lamp_mode(self) -> bool:
        return camera.preview is not None

    @property
    def zoom_mode(self) -> ZoomMode:
        return self._zoom_mode

    def set_raws_path(self):
        raws_path = datetime_to_raws_path(datetime.datetime.now())
        remove_empty_dirs()
        os.makedirs(raws_path)
        self.raws_path = os.path.join(raws_path, "{:08d}.jpg")
        print(f"Set raws path to {raws_path}")

    def start_scan(self):
        if self.continue_dir:
            return

        self.raw_count = 0
        set_zoom_mode_1_1()
        set_lamp_on()
        self.set_raws_path()
        print("Started scanning")
        shoot_raw()

    def stop_scan(self):
        self.continue_dir = False
        print("Nevermind; Stopped scanning")
        set_lamp_off()


def datetime_to_raws_path(dt: datetime.datetime):
    return RAW_DIRS_PATH + dt.strftime("%Y-%m-%dT%H_%M_%S")

def remove_empty_dirs():
    for file_name in os.listdir(RAW_DIRS_PATH):
        file_path = RAW_DIRS_PATH + file_name
        if os.path.isdir(file_path) and len(os.listdir(file_path)) == 0:
            os.rmdir(file_path)

state = State()

arduino = SMBus(1) # Indicates /dev/ic2-1 where the Arduino is connected
arduino_i2c_address = 42 # This is the Arduino's i2c arduinoI2cAddress

camera = PiCamera(resolution=(507, 380)) # keep the exact AR to avoid rounding errors casuing overflow freezes

# Init the Camera
camera.rotation = 180
camera.hflip = True
camera.vflip = False
camera.iso = 100
camera.image_effect = 'none'
camera.brightness = 50 # (0 to 100)
camera.sharpness = 0   # (-100 to 100)
camera.contrast = 0    # (-100 to 100)
camera.saturation = 0  # (-100 to 100)
camera.exposure_compensation = 0 # (-25 to 25)
camera.awb_mode = 'sunlight'     # off becomes green, irrelevant anyway since we do Raws
camera.shutter_speed = FIXED_SHUTTER_SPEED
camera.shutter_speed = 0    # This enables AE
# sleep(2)

img_transfer_process: subprocess.Popen = None

def loop():
    command = ask_arduino()
    if command is not None:
        # Using a dict instead of a switch/case, mapping I2C commands to functions
        func = {
            Command.Z1_1: set_zoom_mode_1_1,
            Command.Z3_1: set_zoom_mode_3_1,
            Command.Z10_1: set_zoom_mode_10_1,
            Command.SHOOT_RAW: shoot_raw,
            Command.LAMP_ON: set_lamp_on,
            Command.LAMP_OFF: set_lamp_off,
            Command.START_SCAN: state.start_scan,
            Command.STOP_SCAN: state.stop_scan,
            Command.SET_EXP: set_exposure
        }.get(command, None)

        if func is not None:
            func()

def tell_arduino(command: Command):
    while True:
        try:
            arduino.write_byte(arduino_i2c_address, command.value)
            return
        except OSError as e:
            if e.errno != errno.EREMOTEIO:
                raise e

            sleep(1)

def ask_arduino_raw() -> Optional[int]:
    try:
        return arduino.read_byte(arduino_i2c_address)
    except OSError:
        print("No I2C answer. Is the Arduino powered up?")

def ask_arduino() -> Optional[Command]:
    raw = ask_arduino_raw()
    
    try:
        return Command(raw)
    except ValueError:
        print(f"Received unknown command {raw}")

def get_available_disk_space() -> int:
    info = os.statvfs(RAW_DIRS_PATH)
    return info.f_bavail * info.f_bsize

def check_available_disk_space():
    available = get_available_disk_space()
    if available < DISK_SPACE_WAIT_THRESHOLD:   # 200 MB
        print(f"Only {available} bytes left on the volume; waiting for more space")
        camera.stop_preview()
        camera.shutter_speed = FIXED_SHUTTER_SPEED
        subprocess.Popen(["fim", "--quiet",  "-d",  "/dev/fb0", "/home/pi/Filmkorn-Raw-Scanner/images/waiting-for-files-to-sync.png"])
        while True:
            sleep(1)
            if get_available_disk_space() >= DISK_SPACE_WAIT_THRESHOLD:
                camera.start_preview()
                return

    if available < DISK_SPACE_ABORT_THRESHOLD:    # 30 MB  
        print(f"Only {available} bytes left on the volume; aborting")
        sys.exit(1)

def set_exposure():
    print("set_exposure")
    hi, lo = None, None
    while lo is None:
        #lo = arduino.read_byte_data(arduino_i2c_address, 1)
        lo = ask_arduino_raw()
    while hi is None:
        #hi = arduino.read_byte_data(arduino_i2c_address, 2)
        hi = ask_arduino_raw()

    val = hi << 8 | lo
    print("Received new Exposure Value:", val)

def shoot_raw():
    camera.shutter_speed = FIXED_SHUTTER_SPEED
    start_time = time.time()
    camera.capture(state.raws_path.format(state.raw_count), format='jpeg', bayer=True)
    state.raw_count += 1
    print("One raw taken ({:.2}s); ".format(time.time() - start_time), end='')
    say_ready()

def say_ready():
    tell_arduino(Command.READY)
    print("then told Arduino we are ready")

def set_zoom_mode_1_1():
    state._zoom_mode = ZoomMode.Z1_1
    camera.shutter_speed = FIXED_SHUTTER_SPEED
    camera.zoom = (0.0, 0.0, 1.0, 1.0)  # (x, y, w, h)
    print("Zoom Level: 1:1")

def set_zoom_mode_3_1():
    set_lamp_on()
    state._zoom_mode = ZoomMode.Z1_1
    camera.shutter_speed = 0
    camera.zoom = (1/3, 1/3, 1/3, 1/3)  # (x, y, w, h)
    print("Zoom Level: 3:1")

def set_zoom_mode_10_1():
    set_lamp_on()
    state._zoom_mode = ZoomMode.Z1_1
    camera.shutter_speed = 0
    camera.zoom = (0.42, 0.42, 1/6, 1/6)  # (x, y, w, h)
    print("Zoom Level: 6:1")

def set_lamp_off():
    set_zoom_mode_1_1()
    camera.stop_preview()
    camera.shutter_speed = FIXED_SHUTTER_SPEED
    print("Lamp and camera preview disabled")

def set_lamp_on():
    # camera.shutter_speed = 0
    camera.start_preview()
    print("Lamp and camera preview enabled")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--continue-at', default=-1, type=int,
        help="continue writing to the previous directory",
        metavar="<next image no>")

    args = parser.parse_args()

    if args.continue_at != -1:
        state.raws_path = RAW_DIRS_PATH + os.path.join(
            sorted(os.listdir(RAW_DIRS_PATH))[-1], '') + "{:08d}.jpg"
        state.raw_count = args.continue_at
        state.continue_dir = True
        camera.start_preview()
        shoot_raw()

    try:
        while True:
            loop()
            check_available_disk_space()
            time.sleep(0.1)
    except KeyboardInterrupt:
        print()
        sys.exit(1)
