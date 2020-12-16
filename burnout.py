from picamera import PiCamera
import time

camera = PiCamera(resolution=(320, 240)) # This is for the embedded Preview JPG only. Making it small so that it doesn't ever get confused with teh Raw

camera.iso = 100
camera.shutter_speed = 1500       # microseconds
# test setting sensor gain
# Test https://github.com/jtc42/picamerax – did not help
# Consider https://github.com/Hermann-SW/picamera
# https: // github.com/waveform80/picamera/issues/629

def main():
    raw_count = 0
    while True:
        raw_count += 1
        start_time = time.time()
        camera.capture('/home/pi/Pictures/raw-intermediates/test%s.jpg' % raw_count, format='jpeg', bayer=True)
        print("One raw taken ({:.3}s)".format(time.time() - start_time))
        time.sleep(1.0)

if __name__ == '__main__':
    main()
