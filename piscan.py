"""Module for Raspberry Pi that communicates with the Arduino"""

"""Todos
- Specify specific Exception in ask_arduino()
- Update to newer picamera?
- Try increasing gpu_mem in /boot/config.txt. to 384 or 512
- Make Disk Cache smaller https://blog.helmutkarger.de/raspberry-video-camera-teil-26-optimierungen-gegen-frame-drops/
- Try smaller previews
- To fix epxosure gains, let analog_gain and digital_gain settle on reasonable values, 
    then set exposure_mode to 'off'. For exposure gains, it’s usually enough to wait 
    until analog_gain is greater than 1 before exposure_mode is set to 'off'.
    https://picamera.readthedocs.io/en/release-1.13/recipes1.html

- picamera.mmal_check(status, prefix='')[

- Recognize when the camera is done

- Turn off screen (and maybe turn it on again)

if not encoder.wait(self.CAPTURE_TIMEOUT):
    raise PiCameraRuntimeError('Timed out waiting for capture to end')
capture_continuous
"""

import sys
import time
import enum
import typing
from smbus import SMBus
from picamera import PiCamera

RAWS_PATH = '/home/pi/Pictures/raw-sequences/{:05d}.jpg'

class Command(enum.Enum):
    IDLE = 0
    PING = 1
    ZOOM_CYCLE = 2
    SHOOT_RAW = 3
    READY = 4
    LAMP_ON = 5
    LAMP_OFF = 6

class ZoomMode(enum.Enum):
    Z1_1 = 0
    Z3_1 = 1
    Z10_1 = 2

class State:
    def __init__(self):
        self._zoom_mode = ZoomMode.Z1_1
        self.raw_count = 0

    @property
    def zoom_mode(self) -> int:
        return self._zoom_mode

    @zoom_mode.setter
    def zoom_mode(self, value: ZoomMode):
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

    def lamp_on(self):
        camera.start_preview()
        print("Camera Preview enabled")

    def lamp_off(self):
        camera.stop_preview()
        self.zoom_mode = ZoomMode.Z1_1
        print("Camera Preview disabled")

state = State()

arduino = SMBus(1) # Indicates /dev/ic2-1 where the Arduino is connected
arduino_i2c_address = 42 # This is the Arduino's i2c arduinoI2cAddress

camera = PiCamera(resolution=(1024, 768)) # This is for the embedded Preview JPG only

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
camera.awb_mode = 'auto'         # off becomes green
camera.shutter_speed = 800       # microseconds, this is 1/1256 s

def main():
    while True:
        loop()
        time.sleep(0.1)

def loop():
    command = ask_arduino()
    if command:
        # Using a dict instead of a switch/case, mapping I2C commands to functions
        func = {
            Command.ZOOM_CYCLE.value: state.cycle_zoom_mode,
            Command.SHOOT_RAW.value: shoot_raw,
            Command.READY.value: say_ready,
            Command.LAMP_ON.value: state.lamp_on,
            Command.LAMP_OFF.value: state.lamp_off
        }[command]

        if func:
            func()
        else:
            print("Invalid command: " + hex(command), file=sys.stderr)

def tell_arduino(command: Command):
    arduino.write_byte(arduino_i2c_address, command.value)

def ask_arduino() -> typing.Optional[int]:
    try:
        return arduino.read_byte(arduino_i2c_address)
    except:
        print("No I2C answer")

def shoot_raw():
    camera.capture(RAWS_PATH.format(state.raw_count), format='jpeg', bayer=True)
    state.raw_count += 1
    print("One raw taken")
    say_ready()

def say_ready():
    tell_arduino(Command.READY)
    print("Told Arduino we are ready")

if __name__ == '__main__':
    main()
