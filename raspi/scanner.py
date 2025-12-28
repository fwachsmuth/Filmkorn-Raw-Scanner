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
import threading
import RPi.GPIO as GPIO
import logging
from collections import deque

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from smbus2 import SMBus
from picamera2 import Picamera2, Preview
from libcamera import Transform, controls
from datetime import datetime

# basic configuration variables
RAW_DIRS_PATH = "/mnt/ramdisk/" # This is where the camera saves to. Has to end with a slash
FULL_RESOLUTION = (4056, 3840)

SENSOR_BIT_DEPTH = 12

# --- Controller MCU (ATmega328P) Power Switch ---
UC_POWER_GPIO = 16  # GPIO16 (physical pin 36) enables µC power switch on the controller PCB
UC_POWER_BOOT_DELAY_S = 0.5  # allow the ATmega328P to boot before first I2C transaction

# lsyncd config switching
LSYNCD_DIR = "/home/pi/Filmkorn-Raw-Scanner/raspi"
LSYNCD_ACTIVE_CONF = os.path.join(LSYNCD_DIR, "lsyncd.active.conf")
LSYNCD_CONF_NET = os.path.join(LSYNCD_DIR, "lsyncd-to-host.conf")
LSYNCD_CONF_LOCAL = os.path.join(LSYNCD_DIR, "lsyncd-local-hd.conf")

AUTO_SHUTTER_SPEED = 0  # Zero enables AE, used in Preview mode
DISK_SPACE_WAIT_THRESHOLD = 200_000_000  # 200 MB
DISK_SPACE_ABORT_THRESHOLD = 30_000_000  # 30 MB

SHUTTER_SPEED_RANGE = 300, 500_000  # 300µs to 0.5s. This defines the range of the exposure potentiometer
EXPOSURE_VAL_FACTOR = math.log(SHUTTER_SPEED_RANGE[1] / SHUTTER_SPEED_RANGE[0]) / 1024

storage_location = None
current_screen = None
ready_screen_polling = False
camera_running = False
sensor_size = None
overlay_cache = {}
preview_started = False
preview_size = (640, 480)
overlay_ready = False
pending_overlay = None
ready_to_scan = False
last_status_screen = None
shutting_down = False
default_scaler_crop = None
shutdown_timer = None
shutdown_requested_at = None
ramdisk_empty_polling = False
last_fps_value = None
last_shutter_value = None
current_resolution_switch = None
last_resolution_label = None
last_sleep_toggle = 0.0
sleep_mode = False
last_sleep_button_state = 1
last_sleep_button_change = 0.0
sleep_button_armed = True
idle_since = None
overlay_supported = True
overlay_retry_count = 0
overlay_retry_timer = None
STATUS_SCREENS = {
    "insert-film",
    "ready-to-scan",
    "ready-to-scan-local",
    "ready-to-scan-net",
    "no-drive-connected",
    "waiting-for-files-to-sync",
    "target-dir-does-not-exist",
    "cannot-connect-to-arduino",
    "cannot-connect-to-paired-mac",
}

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
        self.scanning = False
        self.fps_history = deque(maxlen=36)

    @property
    def lamp_mode(self) -> bool:
        return camera_running

    @property
    def zoom_mode(self) -> ZoomMode:
        return self._zoom_mode

    def set_raws_path(self):
        raws_path = datetime_to_raws_path(datetime.now()) + _resolution_suffix()
        remove_empty_dirs()
        try:
            os.makedirs(raws_path)
        except OSError as exc:
            logging.error("Failed to create RAWs path %s: %s", raws_path, exc)
            show_screen("target-dir-does-not-exist")
            self.stop_scan()
            return
        self.raws_path = os.path.join(raws_path, "{:08d}.dng")
        logging.info(f"Set raws path to {raws_path}")

    def start_scan(self, arg_bytes=None):
        if self.continue_dir:
            return

        self.raw_count = 0
        self.scanning = True
        self.fps_history.clear()
        global last_fps_value, last_shutter_value
        last_fps_value = None
        last_shutter_value = None
        global sleep_mode
        sleep_mode = False
        set_zoom_mode_1_1()
        set_lamp_on()
        self.set_raws_path()
        logging.info("Started scanning")
        shoot_raw()

    def stop_scan(self, arg_bytes=None):
        self.continue_dir = False
        self.scanning = False
        logging.info("Nevermind; Stopped scanning")
        set_lamp_off()
        tell_arduino(Command.TELL_LOADSTATE)
        try:
            if os.listdir(RAW_DIRS_PATH):
                show_screen("waiting-for-files-to-sync")
                if not ramdisk_empty_polling:
                    threading.Thread(target=_ramdisk_empty_poll_loop, daemon=True).start()
        except FileNotFoundError:
            pass

# Displays a PNG in full screen, making our UI
def show_screen(message):
    global current_screen, pending_overlay, last_status_screen, idle_since

    message_path = f"controller-screens/{message}.png"
    overlay = overlay_cache.get(message_path)

    if overlay is None:
        image = Image.open(message_path).convert("RGBA")
        if image.size != preview_size:
            scale = min(preview_size[0] / image.size[0], preview_size[1] / image.size[1])
            new_size = (int(image.size[0] * scale), int(image.size[1] * scale))
            resized = image.resize(new_size, Image.LANCZOS)
            canvas = Image.new("RGBA", preview_size, (0, 0, 0, 255))
            offset = ((preview_size[0] - new_size[0]) // 2, (preview_size[1] - new_size[1]) // 2)
            canvas.paste(resized, offset)
            image = canvas
        rgba = np.array(image, dtype=np.uint8)
        rgba[..., 3] = 255
        overlay = rgba
        overlay_cache[message_path] = overlay

    current_screen = message
    if message in {"insert-film", "ready-to-scan", "ready-to-scan-local", "ready-to-scan-net"}:
        idle_since = time.monotonic()
    else:
        idle_since = None
    if message in STATUS_SCREENS and message != "waiting-for-files-to-sync":
        last_status_screen = message
    pending_overlay = overlay
    _apply_overlay_if_ready()
    _render_scan_overlay()
    if message == "no-drive-connected" and not ready_screen_polling:
        threading.Thread(target=_ready_screen_poll_loop, daemon=True).start()

def _apply_overlay_if_ready():
    global pending_overlay, overlay_supported, overlay_retry_count, overlay_retry_timer
    if (
        pending_overlay is None
        or not overlay_ready
        or not overlay_supported
        or shutting_down
        or not preview_started
    ):
        return
    try:
        camera.set_overlay(pending_overlay)
    except RuntimeError as exc:
        if "Overlays not supported" in str(exc):
            overlay_retry_count += 1
            if overlay_retry_count >= 10:
                overlay_supported = False
                pending_overlay = None
            else:
                if overlay_retry_timer is None or not overlay_retry_timer.is_alive():
                    overlay_retry_timer = threading.Timer(0.5, _apply_overlay_if_ready)
                    overlay_retry_timer.daemon = True
                    overlay_retry_timer.start()
            return
        else:
            raise
    pending_overlay = None
    overlay_retry_count = 0

def clear_overlay():
    global pending_overlay, current_screen
    pending_overlay = None
    current_screen = None
    if overlay_ready:
        camera.set_overlay(None)

def _draw_text_badge(base_img, text: str, position: str):
    draw = ImageDraw.Draw(base_img)
    font = None
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    except OSError:
        font = ImageFont.load_default()
    if hasattr(draw, "textbbox"):
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    else:
        text_w, text_h = draw.textsize(text, font=font)
    pad = 12
    margin = 12
    if position == "bottom-right":
        x = max(0, preview_size[0] - text_w - margin)
    elif position == "bottom-center":
        x = max(0, (preview_size[0] - text_w) // 2)
    else:
        x = margin
    y = max(0, preview_size[1] - text_h - margin)
    draw.rectangle(
        (x - pad, y - pad, x + text_w + pad, y + text_h + pad),
        fill=(0, 0, 0, 160),
    )
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))

def _build_fps_overlay(text: str):
    if preview_size is None:
        return None
    if current_screen:
        message_path = f"controller-screens/{current_screen}.png"
        base_overlay = overlay_cache.get(message_path)
    else:
        base_overlay = None
    if base_overlay is not None:
        base_img = Image.fromarray(base_overlay.copy(), "RGBA")
    else:
        base_img = Image.new("RGBA", preview_size, (0, 0, 0, 0))

    _draw_text_badge(base_img, text, "bottom-left")
    return np.array(base_img, dtype=np.uint8)

def _render_scan_overlay():
    global pending_overlay
    show_shutter = state.scanning or current_screen in {
        "ready-to-scan",
        "ready-to-scan-local",
        "ready-to-scan-net",
    }
    if current_screen == "waiting-for-files-to-sync" and not state.scanning:
        return
    if preview_size is None:
        return
    if current_screen:
        message_path = f"controller-screens/{current_screen}.png"
        base_overlay = overlay_cache.get(message_path)
    else:
        base_overlay = None
    if base_overlay is not None:
        base_img = Image.fromarray(base_overlay.copy(), "RGBA")
    else:
        base_img = Image.new("RGBA", preview_size, (0, 0, 0, 0))
    if last_fps_value is not None and state.scanning:
        _draw_text_badge(base_img, f"{last_fps_value:.1f} fps", "bottom-left")
    if last_shutter_value is not None and show_shutter:
        _draw_text_badge(base_img, _format_shutter_speed(last_shutter_value), "bottom-right")
    if current_screen in STATUS_SCREENS and last_resolution_label:
        _draw_text_badge(base_img, last_resolution_label, "bottom-center")
    pending_overlay = np.array(base_img, dtype=np.uint8)
    _apply_overlay_if_ready()

def update_fps_overlay(avg_fps: float):
    global last_fps_value
    last_fps_value = avg_fps
    _render_scan_overlay()

def _format_shutter_speed(speed_us: int) -> str:
    if speed_us <= 0:
        return "0"
    denom = max(1, int(round(1_000_000 / speed_us)))
    standard = [
        30, 25, 20, 15, 13, 10, 8, 6, 5, 4, 3, 2,
        1,
        2, 3, 4, 5, 6, 8, 10, 13, 15, 20, 25, 30,
        40, 50, 60, 80, 100, 125, 160, 200, 250,
        320, 400, 500, 640, 800, 1000, 1250, 1600,
        2000, 2500, 3200, 4000, 5000, 6400, 8000,
    ]
    nearest = min(standard, key=lambda s: abs(s - denom))
    return f"1/{nearest}s"

def update_shutter_overlay(speed_us: int):
    global last_shutter_value
    last_shutter_value = speed_us
    _render_scan_overlay()

def cleanup_terminal():
    print("Restoring terminal settings...")
    subprocess.run(['stty', 'sane'])

def _enter_sleep_mode():
    global sleep_mode, preview_started, camera_running
    logging.info("Entering sleep mode")
    try:
        GPIO.output(UC_POWER_GPIO, GPIO.LOW)
    except Exception:
        pass
    try:
        camera.stop_preview()
    except Exception:
        pass
    if camera_running:
        try:
            camera.stop()
        except Exception:
            pass
        camera_running = False
    preview_started = False
    sleep_mode = True
    subprocess.run(
        ["sudo", "systemctl", "start", "filmkorn-sleep.service"],
        check=False,
    )

def _exit_sleep_mode():
    global overlay_ready, overlay_supported, overlay_retry_count, overlay_retry_timer, sleep_mode
    logging.info("Waking up")
    subprocess.run(
        ["sudo", "systemctl", "start", "filmkorn-wake.service"],
        check=False,
    )
    try:
        with open("/sys/class/graphics/fb0/blank", "w") as blank:
            blank.write("0")
    except Exception:
        pass
    subprocess.run(["/usr/bin/vcgencmd", "display_power", "1"], check=False)
    try:
        GPIO.output(UC_POWER_GPIO, GPIO.HIGH)
    except Exception:
        pass
    if preview_started:
        try:
            camera.stop_preview()
        except Exception:
            pass
    camera_start()
    overlay_supported = True
    overlay_ready = True
    overlay_retry_count = 0
    overlay_retry_timer = None
    if current_screen or last_status_screen:
        screen_to_show = current_screen or last_status_screen
        threading.Timer(0.5, show_screen, args=(screen_to_show,)).start()
    sleep_mode = False

def _poll_sleep_button(now: float) -> bool:
    global last_sleep_button_state, last_sleep_button_change, last_sleep_toggle
    global sleep_button_armed
    button_state = GPIO.input(26)
    if button_state != last_sleep_button_state:
        last_sleep_button_state = button_state
        last_sleep_button_change = now
    if last_sleep_button_state == 1:
        sleep_button_armed = True
    if (
        sleep_button_armed
        and last_sleep_button_state == 0
        and (now - last_sleep_button_change) >= 0.05
        and (now - last_sleep_toggle) >= 1.0
    ):
        sleep_button_armed = False
        last_sleep_toggle = now
        if sleep_mode:
            logging.info("Sleep button pressed; waking up")
            _exit_sleep_mode()
        else:
            logging.info("Sleep button pressed; entering sleep mode")
            _enter_sleep_mode()
        return True
    return button_state == 0

def _apply_camera_controls():
    camera.set_controls({
        "AeEnable": True,
        "AwbEnable": True,
        "AwbMode": controls.AwbModeEnum.Daylight,
        "Brightness": 0.0,
        "Sharpness": 1.0,
        "Contrast": 1.0,
        "Saturation": 1.0,
        "ExposureValue": 0.0,
        "AnalogueGain": 1.0,
    })

def _create_camera_config(raw_size):
    return camera.create_preview_configuration(
        main={"size": (preview_size), "format": "XBGR8888"},
        raw={"size": raw_size, "format": "SBGGR12_CSI2P"},
        transform=Transform(rotation=180, hflip=True, vflip=False),
    )

def _reconfigure_camera(raw_size):
    global overlay_ready, preview_started, camera_running, sensor_size, preview_size, default_scaler_crop, overlay_supported, overlay_retry_count
    overlay_snapshot = pending_overlay
    overlay_ready = False
    overlay_supported = True
    overlay_retry_count = 0
    try:
        if preview_started:
            camera.stop_preview()
        if camera_running:
            camera.stop()
    except Exception:
        pass
    preview_started = False
    camera_running = False
    camera.configure(_create_camera_config(raw_size))
    sensor_size = camera.camera_configuration().get("sensor", {}).get("output_size", FULL_RESOLUTION)
    preview_size = camera.camera_configuration().get("main", {}).get("size", preview_size)
    _apply_camera_controls()
    default_scaler_crop = None
    camera_start()
    overlay_ready = True
    overlay_supported = True
    if overlay_snapshot is not None:
        camera.set_overlay(overlay_snapshot)
    if current_screen:
        show_screen(current_screen)

def showInsertFilm(arg_bytes=None):
    logging.info("Showing Screen: Please insert film")
    global ready_to_scan
    ready_to_scan = False
    show_screen("insert-film")

def showReadyToScan(arg_bytes=None):
    logging.info("Showing Screen: Ready to Scan")
    global ready_to_scan
    ready_to_scan = True
    show_ready_to_scan()

def _ready_screen_poll_loop():
    global ready_screen_polling, storage_location
    ready_screen_polling = True
    try:
        while (ready_to_scan or current_screen == "no-drive-connected") and not shutting_down:
            new_storage_location = GPIO.input(5)
            if new_storage_location != storage_location:
                storage_location = new_storage_location
                logging.info(
                    f"GPIO 5 changed while ready (1=HDD/local, 0=Net/remote): {storage_location}"
                )
                if storage_location == 1 and not os.path.ismount("/mnt/usb"):
                    if not shutting_down:
                        show_screen("no-drive-connected")
                else:
                    switch_lsyncd_config(storage_location)
                    if not shutting_down:
                        show_ready_to_scan()
                sleep(1)
                continue
            if (
                storage_location == 1
                and current_screen == "no-drive-connected"
                and os.path.ismount("/mnt/usb")
            ):
                switch_lsyncd_config(storage_location)
                if not shutting_down:
                    show_ready_to_scan()
            sleep(1)
    finally:
        ready_screen_polling = False

def _ramdisk_empty_poll_loop():
    global ramdisk_empty_polling
    ramdisk_empty_polling = True
    try:
        def _ramdisk_has_files() -> bool:
            for root, _dirs, files in os.walk(RAW_DIRS_PATH):
                if files:
                    return True
            return False

        while not shutting_down:
            try:
                if not _ramdisk_has_files():
                    break
            except FileNotFoundError:
                break
            sleep(1)
        if not shutting_down:
            if last_status_screen:
                show_screen(last_status_screen)
            else:
                show_ready_to_scan()
    finally:
        ramdisk_empty_polling = False

def show_ready_to_scan():
    global ready_to_scan
    if storage_location == 1 and not os.path.ismount("/mnt/usb"):
        ready_to_scan = False
        show_screen("no-drive-connected")
        if not ready_screen_polling:
            threading.Thread(target=_ready_screen_poll_loop, daemon=True).start()
        return
    ready_to_scan = True
    if storage_location == 1:
        screen = "ready-to-scan-local"
    elif storage_location == 0:
        screen = "ready-to-scan-net"
    else:
        screen = "ready-to-scan"
    show_screen(screen)
    if last_shutter_value is not None:
        update_shutter_overlay(last_shutter_value)
    if ready_to_scan and not ready_screen_polling:
        threading.Thread(target=_ready_screen_poll_loop, daemon=True).start()

def camera_start():
    global camera_running, preview_started, default_scaler_crop
    if camera_running:
        return
    if not preview_started:
        camera.start_preview(Preview.DRM, x=80, y=0, width=640, height=480)
        camera.start()
        if default_scaler_crop is None:
            try:
                default_scaler_crop = camera.capture_metadata().get("ScalerCrop")
            except Exception:
                default_scaler_crop = None
        preview_started = True
        camera_running = True
        return
    camera.start()
    camera_running = True

def camera_stop():
    return

def set_auto_exposure(enabled: bool):
    camera.set_controls({"AeEnable": enabled})

def set_zoom_crop(x_frac: float, y_frac: float, w_frac: float, h_frac: float):
    if sensor_size is None:
        return
    sensor_width, sensor_height = sensor_size
    if default_scaler_crop:
        base_x, base_y, base_w, base_h = default_scaler_crop
    else:
        base_x, base_y, base_w, base_h = 0, 0, sensor_width, sensor_height
    w = max(1, int(base_w * w_frac))
    h = max(1, int(base_h * h_frac))
    x = int(base_x + (base_w - w) * x_frac)
    y = int(base_y + (base_h - h) * y_frac)
    if x + w > base_x + base_w:
        w = (base_x + base_w) - x
    if y + h > base_y + base_h:
        h = (base_y + base_h) - y
    camera.set_controls({"ScalerCrop": (x, y, w, h)})

# For things the Raspi tells (Ready to take next photo, give me value x).
# In most cases, we are polling the Arduino, which owns flow control (but can't be master due to Raspi limitations)
def tell_arduino(command: Command): 
#     while True:
#         try:
#             arduino.write_byte(arduino_i2c_address, command.value)
#             return
#         except OSError as e:
#             logging.warning("Got no I2C answer when telling the Arduino something.")
#             if e.errno != errno.EREMOTEIO:
#                 raise e
#             sleep(0.1)
    max_retries = 5  # Set a max number of retries
    retry_delay = 0.1  # Initial delay between retries in seconds
    for attempt in range(max_retries):
        try:
            arduino.write_byte(arduino_i2c_address, command.value)
            return  # Success, exit the function
        except OSError as e:
            # Depending on kernel/driver, a NACK can surface as EREMOTEIO or EIO.
            if e.errno not in (errno.EREMOTEIO, errno.EIO, errno.ETIMEDOUT):
                raise e  # unexpected
            logging.warning(
                f"Attempt {attempt + 1}: Got no I2C answer when telling the Arduino something (errno={e.errno})."
            )
            sleep(retry_delay)
            retry_delay *= 2  # exponential backoff
    logging.error("Failed to communicate with Arduino after several attempts.")

# For retrieving (multi-byte) answers to explicit tells
def ask_arduino() -> Optional["list[int]"]:
    # try:
    #     return arduino.read_i2c_block_data(arduino_i2c_address, 0, 4)
    # except OSError as e:
    #     logging.debug("No I2C answer when polling Arduino. Probably busy right now?")
    #     if e.errno != errno.EREMOTEIO:
    #         raise e
    #     sleep(0.1)
    max_retries = 5
    retry_delay = 0.1  # Start with 100ms delay
    for attempt in range(max_retries):
        try:
            response = arduino.read_i2c_block_data(arduino_i2c_address, 0, 4)
            return response  # Success, return the response
        except OSError as e:
            # Depending on kernel/driver, a NACK can surface as EREMOTEIO or EIO.
            if e.errno not in (errno.EREMOTEIO, errno.EIO, errno.ETIMEDOUT):
                raise e  # unexpected
            logging.warning(
                f"Attempt {attempt + 1}: No I2C answer when polling Arduino. Probably busy right now (errno={e.errno})."
            )
            sleep(retry_delay)
            retry_delay *= 2  # Exponential backoff
    logging.error("Failed to read from Arduino after several attempts. Arduino might be rebooting?")
    return None  # or handle this case specifically?

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

def clear_pid_file(_signum=None, _frame=None):
    global shutting_down, shutdown_requested_at
    shutting_down = True
    shutdown_requested_at = time.monotonic()
    try:
        os.remove(PID_FILE_PATH)
    except FileNotFoundError:
        pass

def _force_exit():
    logging.error("Shutdown timed out; forcing exit")
    os._exit(0)

def _start_shutdown_timer(timeout_s: float = 5.0):
    global shutdown_timer
    if shutdown_timer is not None:
        return
    shutdown_timer = threading.Timer(timeout_s, _force_exit)
    shutdown_timer.daemon = True
    shutdown_timer.start()

def datetime_to_raws_path(dt: datetime):
    return RAW_DIRS_PATH + dt.strftime("%Y-%m-%d at %H_%M_%S")

def _resolution_suffix() -> str:
    if current_resolution_switch == 1:
        return " @2K"
    return " @4K"

def remove_empty_dirs():
    for file_name in os.listdir(RAW_DIRS_PATH):
        file_path = RAW_DIRS_PATH + file_name
        if os.path.isdir(file_path) and len(os.listdir(file_path)) == 0:
            os.rmdir(file_path)


# --- lsyncd config switching helpers ---
def _atomic_symlink(target: str, link_path: str) -> None:
    """Atomically replace link_path with a symlink to target."""
    tmp_path = link_path + ".tmp"
    try:
        if os.path.islink(tmp_path) or os.path.exists(tmp_path):
            os.unlink(tmp_path)
    except FileNotFoundError:
        pass
    os.symlink(target, tmp_path)
    os.replace(tmp_path, link_path)

def switch_lsyncd_config(storage_location: int) -> None:
    """
    Switch lsyncd config via the lsyncd.active.conf symlink and restart lsyncd.

      - 1 => HDD / local USB (exFAT) target
      - 0 => Net / remote target
    """
    target_conf = LSYNCD_CONF_LOCAL if storage_location == 1 else LSYNCD_CONF_NET
    try:
        if target_conf == LSYNCD_CONF_LOCAL and not os.path.ismount("/mnt/usb"):
            show_screen("no-drive-connected")
            while not os.path.ismount("/mnt/usb"):
                sleep(1)
        _atomic_symlink(target_conf, LSYNCD_ACTIVE_CONF)
        logging.info(f"lsyncd: set active config -> {target_conf}")
        # Requires sudoers rule for pi to restart lsyncd without password.
        # subprocess.run(["sudo", "systemctl", "daemon-reload"], check=False)
        subprocess.run(["sudo", "systemctl", "restart", "filmkorn-lsyncd.service"], check=False) # TODO: try reload instead
    except Exception as e:
        logging.exception(f"lsyncd: failed to switch config to {target_conf}: {e}")

def get_available_disk_space():
    # Ensure RAW output directory exists
    try:
        os.makedirs(RAW_DIRS_PATH, exist_ok=True)
    except Exception as e:
        print(f"WARNING: could not create RAW_DIRS_PATH '{RAW_DIRS_PATH}': {e}")

    try:
        info = os.statvfs(RAW_DIRS_PATH)
    except FileNotFoundError:
        # Fallback to root filesystem so the service keeps running
        info = os.statvfs("/")

    return info.f_bavail * info.f_frsize

def check_available_disk_space():
    available = get_available_disk_space()
    if available < DISK_SPACE_WAIT_THRESHOLD:   # 200 MB
        logging.warning(f"Only {available} bytes left on the volume; waiting for more space")
        set_auto_exposure(True)
        show_screen("waiting-for-files-to-sync")
        while True:
            sleep(1)
            if get_available_disk_space() >= DISK_SPACE_WAIT_THRESHOLD * 2:
                clear_overlay()
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
    update_shutter_overlay(shutter_speed)

    if arg_bytes[2] == 0:
        logging.info("Starting with Screen \"Insert Film\"")
        show_screen("insert-film")
    else:
        logging.info("Starting with Screen \"Ready to scan\"")
        show_ready_to_scan()

def set_zoom_mode_1_1(arg_bytes=None):
    state._zoom_mode = ZoomMode.Z1_1
    set_auto_exposure(True)
    set_zoom_crop(0.0, 0.0, 1.0, 1.0)
    logging.info("Changing Preview Zoom Level to 1:1")

def set_zoom_mode_3_1(arg_bytes=None):
    set_lamp_on()
    state._zoom_mode = ZoomMode.Z1_1
    set_auto_exposure(True)
    set_zoom_crop(1 / 3, 1 / 3, 1 / 3, 1 / 3)
    logging.info("Changing Preview Zoom Level to 3:1")

def set_zoom_mode_10_1(arg_bytes=None):
    set_lamp_on()
    state._zoom_mode = ZoomMode.Z1_1
    set_auto_exposure(True)
    set_zoom_crop(0.42, 0.42, 1 / 6, 1 / 6)
    logging.info("Changing Preview Zoom Level to 6:1")

def set_lamp_off(arg_bytes=None):
    set_zoom_mode_1_1()
    set_auto_exposure(True)
    if last_status_screen in ("ready-to-scan", "ready-to-scan-local", "ready-to-scan-net"):
        show_ready_to_scan()
    elif last_status_screen:
        show_screen(last_status_screen)
    elif ready_to_scan:
        show_ready_to_scan()
    logging.info("Lamp turned off while keeping preview active")

def set_lamp_on(arg_bytes=None):
    set_zoom_crop(0.0, 0.0, 1.0, 1.0)
    camera_start()
    set_auto_exposure(True)
    clear_overlay()
    logging.info("Lamp turned on and camera preview enabled")

def shoot_raw(arg_bytes=None):
    camera_start()
    if state.raws_path is None or not os.path.isdir(os.path.dirname(state.raws_path)):
        logging.error("RAWs path inaccessible; stopping scan")
        state.stop_scan()
        return
    camera.set_controls({"AeEnable": False, "ExposureTime": shutter_speed})
    start_time = time.time()
    request = camera.capture_request()
    try:
        request.save_dng(state.raws_path.format(state.raw_count), name="raw")
    finally:
        request.release()
    state.raw_count += 1
    elapsed_time = time.time() - start_time
    fps = 1 / elapsed_time if elapsed_time > 0 else 0.0
    state.fps_history.append(fps)
    avg_fps = sum(state.fps_history) / len(state.fps_history)
    logging.info(
        "One raw with shutter speed %s taken and saved in %.2fs, avg %.1ffps (last %d)",
        _format_shutter_speed(shutter_speed),
        elapsed_time,
        avg_fps,
        len(state.fps_history),
    )
    update_fps_overlay(avg_fps)
    update_shutter_overlay(shutter_speed)
    say_ready()

def set_exposure(arg_bytes):
    exposure_val = arg_bytes[1] << 8 | arg_bytes[0]
    logging.info(f"Received new Exposure Value from Scan Controller: {exposure_val}")

    # calculate the pot value into meaningful new shutter speeds
    global shutter_speed
    shutter_speed = int(math.exp(exposure_val * EXPOSURE_VAL_FACTOR) * SHUTTER_SPEED_RANGE[0])
    update_shutter_overlay(shutter_speed)
    logging.info(f"This equals shutter speed {shutter_speed} µs")

def say_ready():
    tell_arduino(Command.READY)
    logging.debug("Told Arduino we are ready for next image")


# Now let's go
def setup():
    global PID_FILE_PATH, arduino, arduino_i2c_address, ssh_subprocess, state, camera, storage_location, sensor_size, preview_size, overlay_ready, overlay_supported, overlay_retry_count, overlay_retry_timer, current_resolution_switch, last_resolution_label, last_sleep_button_state, last_sleep_button_change, sleep_button_armed
    os.chdir("/home/pi/Filmkorn-Raw-Scanner/raspi")
    
    atexit.register(cleanup_terminal)

    # set up logging
    logging.basicConfig(filename='scanner.log', level=logging.DEBUG)
    console_handler = logging.StreamHandler()  # Create a handler for stdout
    console_handler.setLevel(logging.DEBUG)    # Set the logging level for the handler
    logging.getLogger('').addHandler(console_handler)  # Add the handler to the root logger

    logging.info("----------------------------------------------------------------------------------")
    logging.info("Scanner started at %s", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))


    # Set the GPIO mode to BCM
    GPIO.setmode(GPIO.BCM)

    # --- Power up the Arduino/Controller MCU (required for I2C to respond) ---
    # The controller PCB gates 3.3V to the ATmega via GPIO16 (physical pin 36).
    GPIO.setup(UC_POWER_GPIO, GPIO.OUT, initial=GPIO.HIGH)
    sleep(UC_POWER_BOOT_DELAY_S)

    # GPIO 17 (BCM) input. "Resolution" switch is connected here.
    #   0 => Full-res RAW
    #   1 => Half-res RAW
    GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    resolution_switch = GPIO.input(17)
    current_resolution_switch = resolution_switch
    last_resolution_label = "4K Raw" if resolution_switch == 0 else "2K Raw"
    logging.info(f"GPIO 17 state (0=Full-res, 1=Half-res): {resolution_switch}")

    # GPIO 5 (BCM) input. "Target" switch is connected here.
    #   1 => HDD / local USB
    #   0 => Net / remote
    GPIO.setup(5, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    storage_location = GPIO.input(5)
    logging.info(f"GPIO 5 state (1=HDD/local, 0=Net/remote): {storage_location}")

    # GPIO 26 (BCM) input. Sleep/wake button (momentary, active low).
    GPIO.setup(26, GPIO.IN, pull_up_down=GPIO.PUD_OFF)
    last_sleep_button_state = GPIO.input(26)
    last_sleep_button_change = time.monotonic()
    sleep_button_armed = (last_sleep_button_state == 1)


    # Instanziate things
    state = State()
    camera = Picamera2()
    raw_format = None
    for candidate in camera.sensor_modes:
        if candidate.get("bit_depth") == SENSOR_BIT_DEPTH:
            raw_format = candidate.get("unpacked") or candidate.get("format")
            break
    if raw_format is None:
        raw_format = "SRGGB12"
    overlay_ready = False
    overlay_supported = True
    overlay_retry_count = 0
    overlay_retry_timer = None
    raw_size = (4056, 3040) if resolution_switch == 0 else (2028, 1520)
    camera_config = _create_camera_config(raw_size)
    camera.configure(camera_config)
    

    sensor_size = camera.camera_configuration().get("sensor", {}).get("output_size", FULL_RESOLUTION)
    preview_size = camera.camera_configuration().get("main", {}).get("size", preview_size)
    _apply_camera_controls()
    camera_start()
    overlay_ready = True
    _apply_overlay_if_ready()

    # Switch lsyncd to the right config for the selected storage target.
    switch_lsyncd_config(storage_location)
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
                logging.error(f"Scan Process is already running with pid {contents}")
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
    # ssh_command_base = ['ssh', '-i', '~/.ssh/id_filmkorn-scanner_ed25519', user_and_host]
    # ssh_command = ssh_command_base + [os.path.join(host_path, "start_converting.sh")]
    # logging.debug(f"ssh command to execute: {ssh_command}")

    # # Run the command
    # ssh_subprocess = subprocess.Popen(ssh_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # # Open the target folder in the Finder
    # subprocess.run(ssh_command_base + [f'open "`cat {host_path}/.scan_destination`/CinemaDNG"'])

    # Show a first screen to indicate we are running
    show_ready_to_scan()
    tell_arduino(Command.TELL_INITVALUES)
    logging.info("Asked Controller about the initial values. ")

    ssh_subprocess = None

def loop():
    poll_ssh_subprocess()

    received = ask_arduino()  # This tells us what to do next. See Command enum.
    command = None
    if received is None:
        return
    try:
        command = Command(received[0])
    except ValueError:
        logging.error(f"Received unknown command byte: {received[0]}")
        return

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
            sorted(os.listdir(RAW_DIRS_PATH))[-1], '') + "{:08d}.dng"
        state.raw_count = args.continue_at
        state.continue_dir = True
        camera_start()
        shoot_raw()

    try:
        last_disk_check = 0.0
        last_resolution_check = 0.0
        while True:
            now = time.monotonic()
            if (
                not state.scanning
                and not shutting_down
                and (
                current_screen in {"insert-film", "ready-to-scan", "ready-to-scan-local", "ready-to-scan-net"}
                or sleep_mode
                )
            ):
                if _poll_sleep_button(now):
                    time.sleep(0.05)
                    continue
                if sleep_mode:
                    time.sleep(0.1)
                    continue
                if idle_since is not None and (now - idle_since) >= 300.0:
                    _enter_sleep_mode()
                    idle_since = None
                    time.sleep(0.1)
                    continue
            loop()
            if now - last_disk_check >= (1.0 if state.scanning else 3.0):
                check_available_disk_space()
                last_disk_check = now
            if not state.scanning and now - last_resolution_check >= 0.5:
                new_resolution = GPIO.input(17)
                if new_resolution != current_resolution_switch:
                    current_resolution_switch = new_resolution
                    raw_size = (4056, 3040) if new_resolution == 0 else (2028, 1520)
                    last_resolution_label = "4K Raw" if new_resolution == 0 else "2K Raw"
                    logging.info(
                        "GPIO 17 changed (0=Full-res, 1=Half-res): %s",
                        current_resolution_switch,
                    )
                    _reconfigure_camera(raw_size)
                last_resolution_check = now
            if shutting_down:
                _start_shutdown_timer()
                break
            time.sleep(0.01 if state.scanning else 0.1) # less i2c collisions
    except KeyboardInterrupt:
        print()
        sys.exit(1)
    finally:
        shutting_down = True
        _start_shutdown_timer()
        if shutdown_requested_at is not None:
            logging.info("Shutdown requested; elapsed %.2fs", time.monotonic() - shutdown_requested_at)
        try:
            if camera_running:
                camera.stop()
            camera.close()
            logging.info("Camera stopped and closed on shutdown")
        except Exception:
            pass
        # Best-effort: turn off the controller MCU power on exit.
        try:
            GPIO.output(UC_POWER_GPIO, GPIO.LOW)
        except Exception:
            pass
