from io import BytesIO
from time import sleep
from picamera import PiCamera

# Create an in-memory stream
my_stream = BytesIO()
camera = PiCamera()

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

camera.shutter_speed = 1200      # 2000      

camera.start_preview()
# Camera warm-up time
print("-- Manual --")
print(camera.exposure_speed)
sleep(1)
print(camera.exposure_speed)
sleep(1)
print(camera.exposure_speed)
sleep(1)
print("-- Now Auto --")

camera.shutter_speed = 0

for i in range(25):
    print(camera.exposure_speed)
    sleep(1)
    print(camera.exposure_speed)
    sleep(1)
    print(camera.exposure_speed)
    sleep(1)
    print(camera.exposure_speed)
    sleep(1)
    print(camera.exposure_speed)
    sleep(1)
    print(camera.exposure_speed)
    sleep(1)
    print(camera.exposure_speed)
    sleep(1)
    print(camera.exposure_speed)
    sleep(1)
    print(camera.exposure_speed)
    sleep(1)

camera.capture(my_stream, 'jpeg')