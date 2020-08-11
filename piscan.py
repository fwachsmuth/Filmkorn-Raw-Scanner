"""
Todos
- update to newer picamera?
- try increasing gpu_mem in /boot/config.txt. auf 384 oder 512
- Disk Cache verkleinern https://blog.helmutkarger.de/raspberry-video-camera-teil-26-optimierungen-gegen-frame-drops/
- try smaller previews
- To fix epxosure gains, let analog_gain and digital_gain settle on reasonable values, 
    then set exposure_mode to 'off'. For exposure gains, it’s usually enough to wait 
    until analog_gain is greater than 1 before exposure_mode is set to 'off'.
    https://picamera.readthedocs.io/en/release-1.13/recipes1.html

- picamera.mmal_check(status, prefix='')[

- Folder pro Scanvorgang anlegen
- Merken wann die Kamera fertig ist
- Scans sauberer durchnummerieren (strformat)

- Screen abschalten und ggf. wieder anschalten

 if not encoder.wait(self.CAPTURE_TIMEOUT):
                            raise PiCameraRuntimeError(
                                'Timed out waiting for capture to end')
capture_continuous

"""


import smbus
import time
from picamera import PiCamera
from time import sleep

arduino = smbus.SMBus(1)    # indicates /dev/ic2-1 where the Arduino is connected
arduino_i2c_address = 42      # This is the Arduino's i2c arduino_i2c_address

camera = PiCamera()

prev_command = 0
zoom_mode = 0
i = 0

# Init the Camera
camera.rotation = 180
camera.hflip = True
camera.vflip = False
camera.iso = 100
camera.image_effect = 'none'
camera.brightness = 50  # (0 to 100)
camera.sharpness = 0    # (-100 to 100)
camera.contrast = 0     # (-100 to 100)
camera.saturation = 0   # (-100 to 100)
camera.exposure_compensation = 0    # (-25 to 25)
camera.awb_mode = 'auto'            # off becomes green
camera.resolution = (1024, 768)  # This is for the embedded Preview JPG only
camera.shutter_speed = 800      # microseconds, this is 1/1256 s


def tell_arduino(command):
    arduino.write_byte(arduino_i2c_address, command)
    return -1

def ask_arduino():
    try:
        return arduino.read_byte(arduino_i2c_address)
    except:
        print("No i2c answer.")
        return False


def zoom_cycle():
    global zoom_mode
    zoom_mode += 1
    if zoom_mode % 3 == 0:
        print("Zoom Level: 1:1")
        camera.zoom = (0.0, 0.0, 1.0, 1.0)  # (x, y, w, h) floating points
    elif zoom_mode % 3 == 1:
        print("Zoom Level: 3:1")
        camera.zoom = (0.4, 0.4, 0.3, 0.3)
    else:
        print("Zoom Level: 10:1")
        camera.zoom = (0.45, 0.45, 0.1, 0.1)

def lamp_on():
    camera.start_preview()
    #camera.start_preview(resolution=(800, 480))
    print("Camera Preview enabled")

def lamp_off():
    camera.stop_preview()
    camera.zoom = (0.0, 0.0, 1.0, 1.0)
    global zoom_mode
    zoom_mode = 0
    print("Camera Preview disabled")

def shoot_raw():
    # camera.capture('/home/pi/Desktop/image%s.jpg' % i)
    global i
    i += 1
    camera.capture('/home/pi/Pictures/raw-sequences/%05d.jpg' %i,
                   format='jpeg', bayer=True)
    print("One Raw taken.")
    say_ready()

def say_ready():
    tell_arduino(4)
    print("Told Arduino we are ready")

# Using a dict instead of a switch/case, mapping i2c commands to function calls
switcher = {
    2: zoom_cycle,
    3: shoot_raw,
    4: say_ready,
    5: lamp_on,
    6: lamp_off
   }

def cmd_to_func(argument):
    func = switcher.get(argument, "invalid command")
    return func()

while True:
    time.sleep(0.05)
    command = ask_arduino()
    if command:
        cmd_to_func(command)
        prev_command = command
