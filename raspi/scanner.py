#!/usr/bin/python3
"""Raspi-side Scan Control Glue communicating between Raspi, Arduino and the Raspi HQ Cam"""

from time import sleep
from typing import Optional
import argparse
import enum
import errno
import math
import subprocess
import sys
import signal
import time
import os
import os.path
import atexit
import RPi.GPIO as GPIO
import logging

from smbus2 import SMBus
from picamera import PiCamera
from datetime import datetime

# basic configuration variables
RAW_DIRS_PATH = "/mnt/ramdisk/" # This is where the camera saves to. Has to end with a slash
AUTO_SHUTTER_SPEED = 0  # Zero enables AE, used in Preview mode
DISK_SPACE_WAIT_THRESHOLD = 200_000_000  # 200 MB
DISK_SPACE_ABORT_THRESHOLD = 30_000_000  # 30 MB

SHUTTER_SPEED_RANGE = 300, 500_000  # 300µs to 0.5s. This defines the range of the exposure potentiometer
EXPOSURE_VAL_FACTOR = math.log(SHUTTER_SPEED_RANGE[1] / SHUTTER_SPEED_RANGE[0]) / 1024

class Command(enum.Enum):
    # Arduino to Raspi. Note we are polling the Arduino though, since we are master.
    # This is 
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
    SHOW_INSERT_FILM = 12
    SHOW_READY_TO_SCAN = 13
    SET_INITVALUES = 14

    # Raspi to Arduino. Ths is handled by i2cReceive() on the Controller side.
    READY = 128
    TELL_INITVALUES = 129 # asks for film load state and exposure pot value (both only get send when they change)
    TELL_LOADSTATE = 130

def process_is_running(contents: str) -> bool:
    try:
        pid = int(contents)
    except ValueError:
        return False

    if pid <= 0:
        return False # invalid

    try:
        os.kill(pid, 0) # signal 0 doesn't do anything
    except OSError as err:
        if err.errno == errno.ESRCH: # no such process
            return False
        if err.errno == errno.EPERM: # no permission, but process exists
            return True

        raise

    return True

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
        raws_path = datetime_to_raws_path(datetime.now())
        remove_empty_dirs()
        os.makedirs(raws_path)
        self.raws_path = os.path.join(raws_path, "{:08d}.jpg")
        logging.info(f"Set raws path to {raws_path}")

    def start_scan(self, arg_bytes=None):
        if self.continue_dir:
            return

        self.raw_count = 0
        set_zoom_mode_1_1()
        set_lamp_on()
        self.set_raws_path()
        logging.info("Started scanning")
        shoot_raw()

    def stop_scan(self, arg_bytes=None):
        self.continue_dir = False
        logging.info("Nevermind; Stopped scanning")
        set_lamp_off()
        tell_arduino(Command.TELL_LOADSTATE)

# Displays a PNG in full screen, making our UI
def show_screen(message):
    global last_fim_pid
    message_path = f'controller-screens/{message}.png'
    command = ["fim", "--quiet", "-d /dev/fb0", message_path]

    last_fim_pid = 0
    
    if last_fim_pid != 0:
        subprocess.run(["kill", "-9", str(last_fim_pid)])    
    fim = subprocess.Popen(command,
                        #  stdin =subprocess.PIPE,
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
    # stdout, stderr = fim.communicate()
    # logging.info(f"Command output:\nstdout: {stdout}\nstderr: {stderr}")

    last_fim_pid = fim.pid
    logging.debug(f"fim PID: {fim.pid}")                        

def showInsertFilm(arg_bytes=None):
    logging.info("Showing Screen: Please insert film")
    show_screen("insert-film")

def showReadyToScan(arg_bytes=None):
    logging.info("Showing Screen: Ready to Scan")
    show_screen("ready-to-scan")

# For things the Raspi tells (Ready to take next photo, give me value x).
# In most cases, we are polling the Arduino, which owns flow control (but can't be master due to Raspi limitations)
def tell_arduino(command: Command): 
    while True:
        try:
            arduino.write_byte(arduino_i2c_address, command.value)
            return
        except OSError as e:
            logging.warning("Got no I2C answer when telling the Arduino something.")
            if e.errno != errno.EREMOTEIO:
                raise e
            sleep(0.1)

# For retrieving (multi-byte) answers to explicit tells
def ask_arduino() -> Optional["list[int]"]:
    try:
        return arduino.read_i2c_block_data(arduino_i2c_address, 0, 4)
    except OSError as e:
        logging.debug("No I2C answer when polling Arduino. Probably busy right now?")
        if e.errno != errno.EREMOTEIO:
            raise e
        sleep(0.1)

def poll_ssh_subprocess():
    global ssh_subprocess

    if ssh_subprocess is not None and ssh_subprocess.poll():
        # Command is done; check if the command was successful
        if ssh_subprocess.returncode == 0:
            print('Remote script exited successfully.')
        else:
            print(f'Error executing remote script. Return code: {ssh_subprocess.returncode}')
            print('Output:', ssh_subprocess.stdout.read().decode())
            print('Error:', ssh_subprocess.stderr.read().decode())

        ssh_subprocess = None

def clear_pid_file():
    os.remove(PID_FILE_PATH)

def datetime_to_raws_path(dt: datetime):
    return RAW_DIRS_PATH + dt.strftime("%Y-%m-%d at %H_%M_%S")

def remove_empty_dirs():
    for file_name in os.listdir(RAW_DIRS_PATH):
        file_path = RAW_DIRS_PATH + file_name
        if os.path.isdir(file_path) and len(os.listdir(file_path)) == 0:
            os.rmdir(file_path)

def get_available_disk_space() -> int:
    info = os.statvfs(RAW_DIRS_PATH)
    return info.f_bavail * info.f_bsize

def check_available_disk_space():
    available = get_available_disk_space()
    if available < DISK_SPACE_WAIT_THRESHOLD:   # 200 MB
        logging.warning(f"Only {available} bytes left on the volume; waiting for more space")
        camera.stop_preview()
        camera.shutter_speed = AUTO_SHUTTER_SPEED
        show_screen("waiting-for-files-to-sync")
        while True:
            sleep(1)
            if get_available_disk_space() >= DISK_SPACE_WAIT_THRESHOLD:
                show_screen("ready-to-scan")
                camera.start_preview()
                return
    if available < DISK_SPACE_ABORT_THRESHOLD:    # 30 MB  
        logging.error(f"Fatal: Only {available} bytes left on the volume; aborting")
        sys.exit(1)

# Camera Features
def set_init_values(arg_bytes):
    exposure_val = arg_bytes[1] << 8 | arg_bytes[0]
    logging.info(f"Received currently set Exposure Value: {exposure_val}")

    # calculate the pot value into meaningful new shutter speeds
    global shutter_speed
    shutter_speed = int(math.exp(exposure_val * EXPOSURE_VAL_FACTOR) * SHUTTER_SPEED_RANGE[0])
    logging.info(f"This equals shutter speed {shutter_speed} µs")

    if arg_bytes[2] == 0:
        logging.info("Starting with Screen \"No Film loaded\"")
        show_screen("insert-film")
    else:
        logging.info("Starting with Screen \"Film loaded, ready to scan\"")
        show_screen("ready-to-scan")

def set_zoom_mode_1_1(arg_bytes=None):
    state._zoom_mode = ZoomMode.Z1_1
    camera.shutter_speed = AUTO_SHUTTER_SPEED
    camera.zoom = (0.0, 0.0, 1.0, 1.0)  # (x, y, w, h)
    logging.info("Changing Preview Zoom Level to 1:1")

def set_zoom_mode_3_1(arg_bytes=None):
    set_lamp_on()
    state._zoom_mode = ZoomMode.Z1_1
    camera.shutter_speed = 0
    camera.zoom = (1/3, 1/3, 1/3, 1/3)  # (x, y, w, h)
    logging.info("Changing Preview Zoom Level to 3:1")

def set_zoom_mode_10_1(arg_bytes=None):
    set_lamp_on()
    state._zoom_mode = ZoomMode.Z1_1
    camera.shutter_speed = 0
    camera.zoom = (0.42, 0.42, 1/6, 1/6)  # (x, y, w, h)
    logging.info("Changing Preview Zoom Level to 6:1")

def set_lamp_off(arg_bytes=None):
    set_zoom_mode_1_1()
    camera.stop_preview()
    camera.shutter_speed = AUTO_SHUTTER_SPEED
    logging.info("Lamp turned off and camera preview disabled")

def set_lamp_on(arg_bytes=None):
    # camera.shutter_speed = 0
    camera.start_preview()
    logging.info("Lamp turned on and camera preview enabled")

def shoot_raw(arg_bytes=None):
    camera.shutter_speed = shutter_speed
    start_time = time.time()
    camera.capture(state.raws_path.format(state.raw_count), format='jpeg', bayer=True)
    state.raw_count += 1
    elapsed_time = time.time() - start_time
    logging.info(f"One raw with shutter speed {shutter_speed}µs taken and saved in {elapsed_time:.2f}s, equalling {1/elapsed_time:.1f}fps")
    say_ready()

def set_exposure(arg_bytes):
    exposure_val = arg_bytes[1] << 8 | arg_bytes[0]
    logging.info(f"Received new Exposure Value from Scan Controller: {exposure_val}")

    # calculate the pot value into meaningful new shutter speeds
    global shutter_speed
    shutter_speed = int(math.exp(exposure_val * EXPOSURE_VAL_FACTOR) * SHUTTER_SPEED_RANGE[0])
    logging.info(f"This equals shutter speed {shutter_speed} µs")

def say_ready():
    tell_arduino(Command.READY)
    logging.debug("Told Arduino we are ready for next image")


# Now let's go
def setup():
    global PID_FILE_PATH, arduino, arduino_i2c_address, ssh_subprocess, state, camera, last_fim_pid
    os.chdir("/home/pi/Filmkorn-Raw-Scanner/raspi")
    
    # set up logging
    logging.basicConfig(filename='scanner.log', level=logging.DEBUG)
    console_handler = logging.StreamHandler()  # Create a handler for stdout
    console_handler.setLevel(logging.DEBUG)    # Set the logging level for the handler
    logging.getLogger('').addHandler(console_handler)  # Add the handler to the root logger

    logging.info(f"----------------------------------------------------------------------------------") 
    logging.info(f"Scanner started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}") 


    # Set the GPIO mode to BCM
    GPIO.setmode(GPIO.BCM)

    # Set up GPIO pin 17 as an input. The "Target" Switch is connected here.
    GPIO.setup(17, GPIO.IN)
    input_state = GPIO.input(17)
    logging.info(f"GPIO pin 17 state (0 is Net, 1 is HDD): {input_state}") 
    # ---- Make sure we only run once, to avoid horrible crashes ¯\_(ツ)_/¯ 
    PID_FILE_PATH = "/tmp/scanner.pid"
    # log a pid
    try:
        file = open(PID_FILE_PATH, "r+")
    except OSError:
        # no such file
        file = open(PID_FILE_PATH, "w+")

    with file:
        contents = file.read()
        if len(contents) != 0:
            # file is not empty, it has a PID
            if process_is_running(contents):
                logging.error(f"Scan Process is already running woth pid {contents}")
                sys.exit(0)

            file.seek(0)
            file.truncate()

        signal.signal(signal.SIGTERM, clear_pid_file)
        atexit.register(clear_pid_file)
        file.write(str(os.getpid()))
    # ---- Done with the pid handling. ------------

    # init i2c comms 
    arduino = SMBus(1) # Indicates /dev/ic2-1 where the Arduino is connected
    sleep(1) # wait a bit here to avoid i2c IO Errors
    arduino_i2c_address = 42 # This is the Arduino's i2c arduinoI2cAddress

    # Fetch the content of the files from /home/pi/Filmkorn-Raw-Scanner/raspi/
    with open(".user_and_host", "r") as file:
        user_and_host = file.read().strip()
    with open(".host_path", "r") as file:
        host_path = file.read().strip()
    logging.info(f"Starting Converter Process as {user_and_host}:{host_path}")

    # Define the SSH command and remote server details
    ssh_command_base = ['ssh', '-i', '~/.ssh/id_filmkorn-scanner_ed25519', user_and_host]
    ssh_command = ssh_command_base + [os.path.join(host_path, "start_converting.sh")]
    logging.debug(f"ssh command to execute: {ssh_command}")

    # Run the command
    ssh_subprocess = subprocess.Popen(ssh_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Open the target folder in the Finder
    subprocess.run(ssh_command_base + [f'open "`cat {host_path}/.scan_destination`/CinemaDNG"'])

    # Show a first screen to indicate we are running
    show_screen("ready-to-scan")
    tell_arduino(Command.TELL_INITVALUES)
    logging.info("Asked Controller about the initial values. ")

    # Instanziate things
    state = State()
    camera = PiCamera(resolution=(507, 380)) # keep the exact AR to avoid rounding errors casuing overflow freezes. This
                                            # only impacts the (unused) jpeg previews, not the scanned Raws!

    # Init the Camera with some base parameters for scanning
    # Some of these parameters are totally irrelevant for our Raws, but still need to be set to let Raw capture work correctly
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
    camera.shutter_speed = 0    # 0 enables AE, used in Preview Modes

    ssh_subprocess = None

def loop():
    poll_ssh_subprocess()

    received = ask_arduino() # This tells us what to do next. See Command enum.
    command = None
    if received is not None:
        try:
            command = Command(received[0])
        except ValueError:
            logging.error(f"Received unknown command {command}")

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
            Command.SET_EXP: set_exposure,
            Command.SHOW_INSERT_FILM: showInsertFilm,
            Command.SHOW_READY_TO_SCAN: showReadyToScan,
            Command.SET_INITVALUES: set_init_values
        }.get(command, None)

        if func is not None:
            func(received[1:])
# end main control loop

if __name__ == '__main__':
    setup()

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
            # time.sleep(0.01) # less i2c collisions
    except KeyboardInterrupt:
        print()
        sys.exit(1)
