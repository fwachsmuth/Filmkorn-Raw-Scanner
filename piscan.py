import smbus
import time
from picamera import PiCamera
from time import sleep

arduino = smbus.SMBus(1)    # indicates /dev/ic2-1 where the Arduino is connected
arduinoI2cAddress = 42      # This is the Arduino's i2c arduinoI2cAddress

camera = PiCamera()

prevCommand = 0
zoomMode = 0

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


def tellArduino(command):
    arduino.write_byte(arduinoI2cAddress, command)
    return -1

def askArduino():
    try:
        command = arduino.read_byte(arduinoI2cAddress)
        return command
    except:
        print("No i2c answer.")
        return False


def zoomCycle():
    global zoomMode
    zoomMode += 1  
    if zoomMode % 3 == 0:
        print("Zoom Level: 1:1")
        camera.zoom = (0.0, 0.0, 1.0, 1.0)  # (x, y, w, h) floating points
    elif zoomMode % 3 == 1:
        print("Zoom Level: 3:1")
        camera.zoom = (0.4, 0.4, 0.3, 0.3)
    elif zoomMode % 3 == 2:
        print("Zoom Level: 10:1")
        camera.zoom = (0.45, 0.45, 0.1, 0.1)

def lampOn():
    camera.start_preview()
    print("Camera Preview enabled")

def lampOff():
    camera.stop_preview()
    camera.zoom = (0.0, 0.0, 1.0, 1.0)
    global zoomMode
    zoomMode = 0
    print("Camera Preview disabled")

def shootRaw():
    # camera.capture('/home/pi/Desktop/image%s.jpg' % i)
    camera.capture('/home/pi/Pictures/raw-sequences/image.dng',
                   format='jpeg', bayer=True)
    print("One Raw taken.")

def sayReady():
    tellArduino(4)
    print("Told Arduino we are ready")

# Using a dict instead of a switch/case, mapping i2c commands to function calls
switcher = {
    2: zoomCycle,
    3: shootRaw,
    4: sayReady,
    5: lampOn,
    6: lampOff
   }

def cmd_to_func(argument):
    func = switcher.get(argument, "invalid command")
    return func()

while True:
    time.sleep(0.1)
    command = askArduino()
    if command:
        cmd_to_func(command)
        prevCommand = command
    
