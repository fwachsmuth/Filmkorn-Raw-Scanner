"""Module for Raspberry Pi that communicates with the Arduino"""

"""Done
- gpu_mem in /boot/config.txt increased to 512

"""

"""Todos
- over_voltage=2 aus boot.txt wieder rausnehmen?

- Try saving to an external disk

- Delete empty Dirs that have been lsynced
- Update to newer picamera? (Habe 1.13)
    - Isolate brightness crash
- Make Disk Cache smaller https://blog.helmutkarger.de/raspberry-video-camera-teil-26-optimierungen-gegen-frame-drops/

- rename intermediate raws something else than jpg

- lens stability isnt great yet

- Switch for pos / neg
- switch for hd / mac
- Exposure Adjustment
- destination path

- Streifen im Vorpann erklären (Störsignal?)

- im preview dynamisch belichten
- Fix 0B Output on white frame

- AND Gate am Lamp/Fan Out hinzufügen (oder Temp-Fühler?)

"""

import datetime
import enum
import subprocess
import sys
import time
import typing
import os

from smbus import SMBus
from picamera import PiCamera
from time import sleep

# Has to end with /
RAW_DIRS_PATH = "/home/pi/Pictures/raw-intermediates/"

#IMG_TRANSFER_CMD = ['rsync', '-avt', '...']

class Command(enum.Enum):
    # Arduino to Raspi
    IDLE = 0
    PING = 1
    ZOOM_CYCLE = 2
    SHOOT_RAW = 3
    LAMP_ON = 4
    LAMP_OFF = 5
    INIT_SCAN = 6
    START_SCAN = 7
    STOP_SCAN = 8

    # Raspi to Arduino
    READY = 128

class ZoomMode(enum.Enum):
    Z1_1 = 0
    Z3_1 = 1
    Z10_1 = 2

class State:
    def __init__(self):
        self._zoom_mode = ZoomMode.Z1_1
        self._raws_path: str = None
        self.raw_count = 0

    @property
    def lamp_mode(self) -> bool:
        return camera.preview is not None

    @lamp_mode.setter
    def lamp_mode(self, value: bool):
        if value == self.lamp_mode:
            return

        print("Lamp and camera preview ", end='')
        if value:
            camera.start_preview()
            print("enabled")
        else:
            self.zoom_mode = ZoomMode.Z1_1
            camera.stop_preview()
            print("disabled")

    @property
    def zoom_mode(self) -> ZoomMode:
        return self._zoom_mode

    @zoom_mode.setter
    def zoom_mode(self, value: ZoomMode):
        if value == self._zoom_mode:
            return

        if value != ZoomMode.Z1_1:
            self.lamp_mode = True

        self._zoom_mode = value

        # Using dicts instead of if/elif statements
        camera.zoom = {
            ZoomMode.Z1_1: (0.0, 0.0, 1.0, 1.0), # (x, y, w, h) floats
            ZoomMode.Z3_1: (1/3, 1/3, 1/3, 1/3),
            ZoomMode.Z10_1: (0.45, 0.45, 0.1, 0.1)
        }[value]

        print("Zoom Level: " + {
            ZoomMode.Z1_1: '1',
            ZoomMode.Z3_1: '3',
            ZoomMode.Z10_1: '10',
        }[value] + ':1')

    def cycle_zoom_mode(self):
        if (self._zoom_mode == ZoomMode.Z10_1):
            self.zoom_mode = ZoomMode.Z1_1
        else:
            self.zoom_mode = ZoomMode(self._zoom_mode.value + 1)

    @property
    def raws_path(self):
        return self._raws_path

    @raws_path.setter
    def raws_path(self, value: datetime.datetime):
        self._raws_path = RAW_DIRS_PATH + value.strftime("%Y-%m-%dT%H_%M_%S")

    def set_raws_path(self):
        self.raws_path = datetime.datetime.now()
        if os.path.exists(self._raws_path):
            self.raws_path = datetime.datetime.now() + datetime.timedelta(seconds=1)

        os.makedirs(self._raws_path)

        print("Set raws path to " + self._raws_path)

        self._raws_path = os.path.join(self._raws_path, '') + "{:05d}.jpg"

    def start_scan(self):
        #img_transfer_process = subprocess.Popen(IMG_TRANSFER_CMD)
        self.raw_count = 0
        self.zoom_mode = ZoomMode.Z1_1
        self.lamp_mode = True
        self.set_raws_path()
        print("Started scanning")
        shoot_raw()

    def stop_scan(self):
        #if img_transfer_process is None:
        #    raise Exception("Arduino told us it stopped scanning even though we weren't scanning")
        #else:
        #    img_transfer_process.terminate()
        print("Nevermind; Stopped scanning")
        self.lamp_mode = False

state = State()

arduino = SMBus(1) # Indicates /dev/ic2-1 where the Arduino is connected
arduino_i2c_address = 42 # This is the Arduino's i2c arduinoI2cAddress

camera = PiCamera(resolution=(507, 380)) // keep the exact AR to avoid rounding errors casuing overflow freezes

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
camera.awb_mode = 'sunlight'         # off becomes green, irrelevant anyway since we do Raws
camera.shutter_speed = 1600          
# camera.exposure_mode = 'off'    # lock all settings
# sleep(2)

img_transfer_process: subprocess.Popen = None

def main():
    while True:
        loop()
        time.sleep(0.1)

def loop():
    command = ask_arduino()
    if command is not None and command != Command.IDLE:
        # Using a dict instead of a switch/case, mapping I2C commands to functions
        func = {
            Command.ZOOM_CYCLE: state.cycle_zoom_mode,
            Command.SHOOT_RAW: shoot_raw,
            Command.LAMP_ON: lamp_on,
            Command.LAMP_OFF: lamp_off,
            Command.START_SCAN: state.start_scan,
            Command.STOP_SCAN: state.stop_scan
        }.get(command, None)

        if func is not None:
            func()

def tell_arduino(command: Command):
    arduino.write_byte(arduino_i2c_address, command.value)

def ask_arduino() -> typing.Optional[Command]:
    try:
        return Command(arduino.read_byte(arduino_i2c_address))
    except OSError:
        print("No I2C answer")

def shoot_raw():
    start_time = time.time()
    camera.capture(state.raws_path.format(state.raw_count), format='jpeg', bayer=True)
    state.raw_count += 1
    print("One raw taken ({:.3}s); ".format(time.time() - start_time), end='')
    say_ready()

def say_ready():
    tell_arduino(Command.READY)
    print("Told Arduino we are ready")

def lamp_on():
    state.lamp_mode = True

def lamp_off():
    state.lamp_mode = False

if __name__ == '__main__':
    main()
