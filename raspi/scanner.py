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
import shlex
import secrets
import atexit
import threading
from collections import deque
import json
import re
import shutil
import RPi.GPIO as GPIO
import logging
try:
    from systemd.journal import JournalHandler
except ImportError:
    JournalHandler = None

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
DEBUG_DRAIN = True  # Log frame-drain timing to diagnose out-of-order captures
# Minimum frames to discard after motor stop (adds safety for buffered transport frames)
DRAIN_MIN_DISCARD_4K = 2
DRAIN_MIN_DISCARD_2K = 0
# SensorTimestamp safety margin (ns) added after motor stop
DRAIN_CUTOFF_MARGIN_NS_4K = 170_000_000
DRAIN_CUTOFF_MARGIN_NS_2K = 86_000_000

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
FPS_AVG_WINDOW = 0  # 0 = all frames in scan, >0 = rolling window size
USB_POWER_CHECK_INTERVAL_S = 30.0
USB3_CHECK_INTERVAL_S = 5.0
MCU_HEX_HASH_CACHE_ENABLED = True  # Enable/disable .mcu_hex_hash caching to skip verification

SHUTTER_SPEED_RANGE = 300, 500_000  # 300µs to 0.5s. This defines the range of the exposure potentiometer
EXPOSURE_VAL_FACTOR = math.log(SHUTTER_SPEED_RANGE[1] / SHUTTER_SPEED_RANGE[0]) / 1024

storage_location = None
current_screen = None
ready_screen_polling = False
camera_running = False
no_camera = False
sensor_size = None
raw_format = "SBGGR12"  # uncompressed 12-bit raw, updated in setup()
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
shutter_speed = AUTO_SHUTTER_SPEED
# Per-frame sensor-clock calibration for transport-frame drain.
# Recorded after each saved frame to anchor SensorTimestamp ↔ monotonic mapping.
_last_frame_sensor_ts = None   # SensorTimestamp (camera clock, nanoseconds)
_last_frame_mono_ts   = None   # time.monotonic() when that capture_request() returned
overlay_supported = True
overlay_retry_count = 0
overlay_retry_timer = None
last_usb_health_check = 0.0
usb_speed_warning_logged = False
usb_power_warning_logged = False
last_usb_power_check = 0.0
last_usb_speed_check = 0.0
power_warning_active = False
usb3_warning_active = False
dmesg_since = None

# OTA updates: only consider tags that start with this prefix (e.g. "v" for v0.9.2). Use "" to allow any semver tag.
OTA_TAG_PREFIX = "v"

update_mode = False
update_tags = []
update_selected = 0
update_scroll_offset = 0
update_current_tag = None
update_in_progress = False
update_error = None
update_confirmation_mode = False
update_confirmation_selected = 0  # 0 = No, 1 = Yes
pairing_mode = False
pairing_exit_pending = False
logs_mode = False
logs_in_progress = False
unpair_in_progress = False
unpair_mode = False
unpair_confirmation_mode = False
unpair_confirmation_selected = 0  # 0 = No, 1 = Yes
awb_mode = False
awb_selected = 0
awb_scroll_offset = 0
awb_stored_idx = 2  # Cached stored AWB setting (default to Daylight)
AWB_OPTIONS = [
    ("~3600K", controls.AwbModeEnum.Tungsten),
    ("~4500K", controls.AwbModeEnum.Fluorescent),
    ("~5500K", controls.AwbModeEnum.Daylight),
]
AWB_FILE = os.path.join(os.path.dirname(__file__), ".awb_mode")
menu_mode = False
menu_selected = 0
menu_scroll_offset = 0
# Scan target selection
target_mode = False
target_selected = 0
target_scroll_offset = 0
target_stored_idx = 2  # Default to GPIO5 (auto mode)
target_validation_error = False  # True when showing validation error screen
target_validation_failures = []  # List of failed tests: "ping", "ssh", "write"
last_target_unknown_command = None  # Track last unknown command to avoid log spam
pending_menu_entry = False  # Flag to enter menu mode after arduino is initialized
TARGET_OPTIONS = [
    ("USB-Drive", 1),      # storage_location = 1
    ("Host Computer", 0),  # storage_location = 0
    ("GPIO5", 2),          # storage_location = read from GPIO5
]
TARGET_FILE = os.path.join(os.path.dirname(__file__), ".scan_target_mode")
# WiFi setup mode
wifi_mode = False
wifi_selected = 0
wifi_scroll_offset = 0
wifi_portal_process = None  # Subprocess running the captive portal
WIFI_NETWORKS_FILE = os.path.join(os.path.dirname(__file__), ".wifi_networks")
MENU_ITEMS = [
    "menu.item.firmware-update",
    "menu.item.start-pairing",
    "menu.item.preview-wb",
    "menu.item.scan-target",
    "menu.item.setup-wifi",
    "menu.item.create-debug-log",
    "menu.item.factory-reset",
    "menu.item.language",
]

# --- Localization ---
LOCALE_OPTIONS = [
    ("en", "English"),
    ("de", "Deutsch"),
]
LOCALES_DIR = os.path.join(os.path.dirname(__file__), "locales")
LOCALE_FILE = os.path.join(os.path.dirname(__file__), ".locale")
current_locale = "en"
_translations: dict = {}

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
current_version_label = None
mcu_flash_in_progress = False
mcu_flash_checked = False
mcu_flash_error = None
MCU_FLASH_SCRIPT = os.path.join(repo_root, "scan-controller", "bootstrap", "flash-atmega328.sh")
MCU_HEX_PATH = os.path.join(
    repo_root,
    "scan-controller",
    "build",
    "arduino.avr.pro",
    "scan-controller.ino.with_bootloader.hex",
)
MCU_AVRDUDE = "/usr/local/bin/avrdude"
MCU_AVRDUDE_CONF = os.path.join(repo_root, "scan-controller", "avrdude_gpio.conf")
MCU_HEX_HASH_FILE = os.path.join(os.path.dirname(__file__), ".mcu_hex_hash")
STATUS_SCREENS = {
    "insert-film",
    "ready-to-scan",
    "ready-to-scan-local",
    "ready-to-scan-net",
    "no-drive-connected",
    "waiting-for-files-to-sync",
    "target-dir-does-not-exist",
    "no-host-computer-paired-yet",
    "updating-ino",
}
# Screens that must not be replaced by film-sensor state changes (insert-film / ready-to-scan).
# These represent conditions that must be resolved before scanning can proceed.
SCAN_BLOCKING_SCREENS = {
    "no-drive-connected",
    "no-host-computer-paired-yet",
    "no-camera-connected",
}

SCREEN_DEFINITIONS = {
    "insert-film": {
        "icon_name": "film.png",
        "title_key": "screen.insert-film.title",
    },
    "no-drive-connected": {
        "icon_name": "warning.png",
        "title_key": "screen.no-drive-connected.title",
    },
    "checking-filesystem": {
        "icon_name": "hourglass.png",
        "title_key": "screen.checking-filesystem.title",
    },
    "generating-debug-log": {
        "icon_name": "bug.png",
        "title_key": "screen.generating-debug-log.title",
    },
    "updating-ino": {
        "icon_name": "lightning.png",
        "title_key": "screen.updating-ino.title",
    },
    "waiting-for-files-to-sync": {
        "icon_name": "hourglass.png",
        "title_key": "screen.waiting-for-files-to-sync.title",
    },
    "ready-to-scan": {
        "title_key": "screen.ready-to-scan.title",
    },
    "ready-to-scan-local": {
        "title_key": "screen.ready-to-scan.title",
    },
    "ready-to-scan-net": {
        "title_key": "screen.ready-to-scan-net.title",
    },
    "no-host-computer-paired-yet": {
        "icon_name": "warning.png",
        "title_key": "screen.no-host-computer-paired-yet.title",
        "description_key": "screen.no-host-computer-paired-yet.description",
    },
    "too-much-power": {
        "icon_name": "warning.png",
        "title_key": "screen.too-much-power.title",
        "description_key": "screen.too-much-power.description",
    },
    "no-usb3-drive": {
        "icon_name": "snail.png",
        "title_key": "screen.no-usb3-drive.title",
        "description_key": "screen.no-usb3-drive.description",
    },
    "target-dir-does-not-exist": {
        "icon_name": "warning.png",
        "title_key": "screen.target-dir-does-not-exist.title",
        "description_key": "screen.target-dir-does-not-exist.description",
    },
    "unpaired-from-client": {
        "icon_name": "construction.png",
        "title_key": "screen.unpaired-from-client.title",
        "description_key": "screen.unpaired-from-client.description",
    },
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
    UPDATE_ENTER = 15
    UPDATE_PREV = 16
    UPDATE_NEXT = 17
    UPDATE_CONFIRM = 18
    UPDATE_CANCEL = 19
    PAIRING_ENTER = 20
    PAIRING_EXIT = 21
    PAIRING_CANCEL = 22
    LOGS_ENTER = 23
    LOGS_EXIT = 24
    UNPAIR_ENTER = 25
    UNPAIR_PREV = 26
    UNPAIR_NEXT = 27
    UNPAIR_CONFIRM = 28
    UNPAIR_CANCEL = 29
    AWB_ENTER = 30
    AWB_PREV = 31
    AWB_NEXT = 32
    AWB_CONFIRM = 33
    AWB_CANCEL = 34
    TARGET_ENTER = 35
    TARGET_PREV = 36
    TARGET_NEXT = 37
    TARGET_CONFIRM = 38
    TARGET_CANCEL = 39
    MENU_ENTER = 40
    MENU_EXIT = 41
    MENU_PREV = 42
    MENU_NEXT = 43
    MENU_SELECT = 44
    WIFI_ENTER = 45
    WIFI_PREV = 46
    WIFI_NEXT = 47
    WIFI_CONFIRM = 48
    WIFI_CANCEL = 49
    WIFI_EXIT = 134

    # Raspi to Arduino. These are handled by i2cReceive() on the Controller side.
    READY = 128
    TELL_INITVALUES = 129 # asks for film load state and exposure pot value (both only get send when they change)
    TELL_LOADSTATE = 130
    AWB_EXIT = 131
    TARGET_EXIT = 132
    TARGET_REENTER = 133  # Re-enter target mode (used when returning from validation error)
    SCAN_REJECTED = 135   # Tell Arduino to abort scan (Pi rejected START_SCAN)

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
        self.fps_history = deque(maxlen=FPS_AVG_WINDOW) if FPS_AVG_WINDOW > 0 else None
        self.fps_sum = 0.0
        self.fps_count = 0
        self.warmup_needed = False

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

        if no_camera:
            logging.warning("start_scan: blocked - no camera connected")
            tell_arduino(Command.SCAN_REJECTED)
            return
        if storage_location == 1 and not os.path.ismount("/mnt/usb"):
            logging.warning("start_scan: blocked - no USB drive connected")
            tell_arduino(Command.SCAN_REJECTED)
            return
        if storage_location == 0 and not _is_paired():
            logging.warning("start_scan: blocked - no host computer paired")
            tell_arduino(Command.SCAN_REJECTED)
            return

        # Check ethernet before scanning to host (storage_location == 0)
        # WiFi must not be used for file sync
        if storage_location == 0:
            _wifi_radio_off()
            if not _is_ethernet_up():
                logging.warning("start_scan: blocked - ethernet is down for host scanning")
                _show_ethernet_warning()
                _wifi_radio_on()
                return

        self.raw_count = 0
        self.scanning = True
        if self.fps_history is not None:
            self.fps_history.clear()
        self.fps_sum = 0.0
        self.fps_count = 0
        global last_fps_value, last_shutter_value
        last_fps_value = None
        last_shutter_value = None
        global sleep_mode
        sleep_mode = False
        self.warmup_needed = True
        set_zoom_mode_1_1()
        set_lamp_on()
        self.set_raws_path()
        logging.info("Started scanning")
        sleep(1.0)  # allow lamp to reach full brightness
        say_ready()

    def stop_scan(self, arg_bytes=None):
        self.continue_dir = False
        self.scanning = False
        logging.info("Scanning stopped")
        if storage_location == 0:
            _wifi_radio_on()
        set_lamp_off()
        tell_arduino(Command.TELL_LOADSTATE)
        try:
            if os.listdir(RAW_DIRS_PATH):
                show_screen("waiting-for-files-to-sync")
                if not ramdisk_empty_polling:
                    threading.Thread(target=_ramdisk_empty_poll_loop, daemon=True).start()
        except FileNotFoundError:
            pass

_icon_cache = {}


def _load_locale_setting() -> str:
    """Return the persisted locale code, falling back to 'en'."""
    if os.path.exists(LOCALE_FILE):
        try:
            with open(LOCALE_FILE, "r") as f:
                code = f.read().strip()
                if code in dict(LOCALE_OPTIONS):
                    return code
        except IOError:
            pass
    return "en"


def _save_locale_setting(code: str):
    try:
        with open(LOCALE_FILE, "w") as f:
            f.write(code)
        logging.info("locale: saved %s", code)
    except IOError as e:
        logging.error("locale: failed to save: %s", e)


def _load_locale(code: str = "en"):
    """Load the JSON locale file for *code*, falling back to English for missing keys."""
    global _translations, current_locale
    current_locale = code
    base: dict = {}
    # Always load English as the fallback layer
    en_path = os.path.join(LOCALES_DIR, "en.json")
    try:
        with open(en_path, "r", encoding="utf-8") as f:
            base = json.load(f)
    except Exception as e:
        logging.error("locale: failed to load en.json: %s", e)
    if code != "en":
        locale_path = os.path.join(LOCALES_DIR, f"{code}.json")
        try:
            with open(locale_path, "r", encoding="utf-8") as f:
                overrides = json.load(f)
            base.update(overrides)
        except Exception as e:
            logging.error("locale: failed to load %s.json: %s", code, e)
    _translations = base
    logging.info("locale: loaded '%s' (%d keys)", code, len(_translations))


def _(key: str, **kwargs) -> str:
    """Return the localised string for *key*, formatting with *kwargs* if provided.

    Falls back to the key itself when no translation exists so that untranslated
    strings are at least readable during development.
    """
    text = _translations.get(key, key)
    return text.format(**kwargs) if kwargs else text


def build_status_screen(title, icon_name=None, description=None):
    """Build a status screen overlay with logo, optional icon, title, and optional description.

    Args:
        title: Main text, may contain newlines for multi-line titles.
        icon_name: Filename of an icon in controller-screens/icons/ (e.g. "warning.png").
        description: Smaller text shown below the title.

    Returns:
        A numpy RGBA array (H, W, 4) suitable for use as a camera overlay,
        or None if preview_size is not set.
    """
    if preview_size is None:
        return None

    base = Image.new("RGBA", preview_size, (0, 0, 0, 255))
    draw = ImageDraw.Draw(base)

    has_description = description is not None and description.strip()
    title_size = 36 if has_description else 48

    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", title_size)
    except OSError:
        title_font = ImageFont.load_default()
    try:
        desc_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
    except OSError:
        desc_font = ImageFont.load_default()

    logo_height = _get_logo_height()
    w, h = preview_size

    icon_img = None
    if icon_name:
        icon_img = _icon_cache.get(icon_name)
        if icon_img is None:
            icon_path = os.path.join("controller-screens", "icons", icon_name)
            if os.path.exists(icon_path):
                try:
                    icon_img = Image.open(icon_path).convert("RGBA")
                    _icon_cache[icon_name] = icon_img
                except Exception:
                    pass

    def _text_block_height(text, font):
        lines = text.split("\n")
        total = 0
        for line in lines:
            if hasattr(draw, "textbbox"):
                bbox = draw.textbbox((0, 0), line or " ", font=font)
                total += bbox[3] - bbox[1]
            else:
                total += draw.textsize(line or " ", font=font)[1]
        total += 6 * max(0, len(lines) - 1)
        return total

    icon_h = icon_img.size[1] if icon_img else 0
    icon_gap = 35 if icon_img else 0
    title_gap = 20
    desc_gap = 25

    title_h = _text_block_height(title, title_font)
    desc_h = _text_block_height(description, desc_font) if has_description else 0

    content_h = icon_h + (icon_gap > 0) * icon_gap + title_h + (desc_h > 0) * (desc_gap + desc_h)
    available = h - logo_height - 10
    start_y = logo_height + 10 + max(0, (available - content_h) // 2)

    y = start_y

    if icon_img:
        icon_x = (w - icon_img.size[0]) // 2
        base.paste(icon_img, (icon_x, y), icon_img)
        y += icon_h + title_gap

    title_lines = title.split("\n")
    for line in title_lines:
        if hasattr(draw, "textbbox"):
            bbox = draw.textbbox((0, 0), line, font=title_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        else:
            tw, th = draw.textsize(line, font=title_font)
        tx = (w - tw) // 2
        draw.text((tx, y), line, font=title_font, fill=(255, 255, 255, 255))
        y += th + 6

    if has_description:
        y += desc_gap - 6
        desc_lines = description.split("\n")
        for line in desc_lines:
            if hasattr(draw, "textbbox"):
                bbox = draw.textbbox((0, 0), line or " ", font=desc_font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            else:
                tw, th = draw.textsize(line or " ", font=desc_font)
            tx = (w - tw) // 2
            draw.text((tx, y), line, font=desc_font, fill=(200, 200, 200, 255))
            y += th + 6

    base = _stamp_logo(base)

    rgba = np.array(base, dtype=np.uint8)
    rgba[..., 3] = 255
    return rgba


def show_screen(message):
    global current_screen, pending_overlay, last_status_screen, idle_since
    if no_camera:
        return
    if update_mode or pairing_mode or menu_mode:
        return
    if power_warning_active and not sleep_mode and message != "too-much-power":
        return
    if usb3_warning_active and not sleep_mode and message not in {"no-usb3-drive", "too-much-power"}:
        return

    overlay = overlay_cache.get(message)

    if overlay is None:
        screen_def = SCREEN_DEFINITIONS.get(message)
        if screen_def:
            build_kwargs = {"icon_name": screen_def.get("icon_name")}
            build_kwargs["title"] = _(screen_def["title_key"])
            if "description_key" in screen_def:
                build_kwargs["description"] = _(screen_def["description_key"])
            overlay = build_status_screen(**build_kwargs)
        else:
            logging.warning("No screen definition for '%s'", message)
            overlay = build_status_screen(title=message.replace("-", " ").title())
        if overlay is not None:
            overlay_cache[message] = overlay

    current_screen = message
    if message in {"insert-film", "ready-to-scan", "ready-to-scan-local", "ready-to-scan-net", "no-usb3-drive", "no-drive-connected"}:
        idle_since = time.monotonic()
    else:
        idle_since = None
    if message in STATUS_SCREENS and message != "waiting-for-files-to-sync":
        last_status_screen = message
    # Keep base overlay as fallback for screens where _render_scan_overlay() exits early.
    # Don't apply the base first — let _render_scan_overlay() produce the complete overlay
    # (including shutter badge) as the first thing the camera sees.
    pending_overlay = overlay
    _render_scan_overlay()
    # _render_scan_overlay() may return early for some screens (e.g. waiting-for-files-to-sync
    # when not scanning), leaving pending_overlay as the base screen. Apply it now in that case.
    _apply_overlay_if_ready()
    if message == "no-drive-connected" and not ready_screen_polling:
        threading.Thread(target=_ready_screen_poll_loop, daemon=True).start()

def _build_update_overlay(lines, footer_left=None, footer_right=None, button_labels=None, scroll_offset=0):
    if preview_size is None:
        return None
    base = Image.new("RGBA", preview_size, (0, 0, 0, 255))
    draw = ImageDraw.Draw(base)
    try:
        text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except OSError:
        text_font = ImageFont.load_default()

    def _measure_mixed(text: str):
        width = 0
        height = 0
        for ch in text:
            if hasattr(draw, "textbbox"):
                bbox = draw.textbbox((0, 0), ch, font=text_font)
                w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            else:
                w, h = draw.textsize(ch, font=text_font)
            width += w
            height = max(height, h)
        return width, height

    def _draw_mixed(text: str, x: int, y: int):
        for ch in text:
            draw.text((x, y), ch, font=text_font, fill=(255, 255, 255, 255))
            if hasattr(draw, "textbbox"):
                bbox = draw.textbbox((0, 0), ch, font=text_font)
                x += bbox[2] - bbox[0]
            else:
                x += draw.textsize(ch, font=text_font)[0]

    # Get logo height to avoid overlapping
    logo_height = _get_logo_height()
    logo_margin = 10  # Small margin below logo

    # Calculate button label area height if labels are provided
    button_area_height = 0
    if button_labels:
        try:
            label_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        except OSError:
            label_font = ImageFont.load_default()
        if hasattr(draw, "textbbox"):
            bbox = draw.textbbox((0, 0), "Test", font=label_font)
            button_area_height = (bbox[3] - bbox[1]) + 20  # Add padding
        else:
            button_area_height = draw.textsize("Test", font=label_font)[1] + 20
    
    metrics = []
    for line in lines:
        line_w, line_h = _measure_mixed(line)
        metrics.append((line, line_w, line_h))
    spacing = 10
    total_height = sum(h for _, _, h in metrics) + spacing * (len(metrics) - 1)
    
    # Calculate available height: screen - logo - button labels - footer space
    footer_space = 40 if (footer_left or footer_right) else 0
    available_height = preview_size[1] - logo_height - logo_margin - button_area_height - footer_space
    
    # Calculate how many lines fit on screen
    if not metrics:
        visible_metrics = []
    else:
        # Estimate lines that fit (using average line height)
        avg_line_height = total_height / len(metrics) if metrics else 0
        if avg_line_height > 0:
            max_visible_lines = int(available_height / (avg_line_height + spacing))
        else:
            max_visible_lines = len(metrics)
        
        # Clamp scroll_offset
        max_scroll = max(0, len(metrics) - max_visible_lines)
        scroll_offset = max(0, min(scroll_offset, max_scroll))
        
        # Determine which lines to render
        visible_metrics = metrics[scroll_offset:]
    
    # Start y position below logo
    start_y = logo_height + logo_margin
    y = start_y
    for line, w, h in visible_metrics:
        # Only draw if it fits in available space
        if y + h <= preview_size[1] - button_area_height - footer_space:
            x = max(0, (preview_size[0] - w) // 2)
            _draw_mixed(line, x, y)
            y += h + spacing
        else:
            break  # Stop if we've run out of space
    
    if footer_left or footer_right:
        margin = 16
        footer_h = 0
        if footer_left:
            _, h = _measure_mixed(footer_left)
            footer_h = max(footer_h, h)
        if footer_right:
            _, h = _measure_mixed(footer_right)
            footer_h = max(footer_h, h)
        footer_y = max(0, preview_size[1] - footer_h - margin)
        if footer_left:
            footer_left_x = int(preview_size[0] * 9 / 16)
            _draw_mixed(footer_left, footer_left_x, footer_y)
        if footer_right:
            footer_right_w, _ = _measure_mixed(footer_right)
            footer_right_x = max(0, preview_size[0] - footer_right_w)
            _draw_mixed(footer_right, footer_right_x, footer_y)
    
    # Draw button labels at the bottom
    if button_labels:
        try:
            label_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        except OSError:
            label_font = ImageFont.load_default()
        # Make slots 15% smaller and center them
        slot_width = (preview_size[0] / 6) * 0.85
        total_width = slot_width * 6
        start_x = (preview_size[0] - total_width) / 2
        label_y = preview_size[1] - button_area_height + 10
        for slot in range(1, 7):  # Slots 1-6
            if slot in button_labels:
                label_text = button_labels[slot]
                # Center the label in its slot
                if hasattr(draw, "textbbox"):
                    bbox = draw.textbbox((0, 0), label_text, font=label_font)
                    label_w = bbox[2] - bbox[0]
                else:
                    label_w = draw.textsize(label_text, font=label_font)[0]
                label_x = start_x + (slot - 1) * slot_width + (slot_width - label_w) / 2
                draw.text((label_x, label_y), label_text, font=label_font, fill=(255, 255, 255, 255))
    
    # Stamp logo before converting to numpy
    base = _stamp_logo(base)
    
    rgba = np.array(base, dtype=np.uint8)
    rgba[..., 3] = 255
    return rgba

def _build_menu_overlay(lines, button_labels=None, scroll_offset=0):
    """Build a left-aligned menu overlay with optional button labels at the bottom.
    
    button_labels: dict with keys 2-6 (slot numbers) mapping to label text.
                   For example: {2: "Back", 3: "Up", 5: "Down", 6: "OK"}
    scroll_offset: Number of lines to skip from the top (for scrolling)
    """
    if preview_size is None:
        return None
    base = Image.new("RGBA", preview_size, (0, 0, 0, 255))
    draw = ImageDraw.Draw(base)
    try:
        symbol_font = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSansSymbols2-Regular.ttf", 28)
    except OSError:
        symbol_font = ImageFont.load_default()
    try:
        text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except OSError:
        text_font = ImageFont.load_default()
    try:
        label_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
    except OSError:
        label_font = ImageFont.load_default()
    symbol_chars = {"\u23ea", "\u23e9", "\u23fa", "\u23f9"}

    def _measure_mixed(text: str):
        width = 0
        height = 0
        for ch in text:
            font = symbol_font if ch in symbol_chars else text_font
            if hasattr(draw, "textbbox"):
                bbox = draw.textbbox((0, 0), ch, font=font)
                w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            else:
                w, h = draw.textsize(ch, font=font)
            width += w
            height = max(height, h)
        return width, height

    def _draw_mixed(text: str, x: int, y: int):
        for ch in text:
            font = symbol_font if ch in symbol_chars else text_font
            draw.text((x, y), ch, font=font, fill=(255, 255, 255, 255))
            if hasattr(draw, "textbbox"):
                bbox = draw.textbbox((0, 0), ch, font=font)
                x += bbox[2] - bbox[0]
            else:
                x += draw.textsize(ch, font=font)[0]

    # Get logo height to avoid overlapping
    logo_height = _get_logo_height()
    logo_margin = 10  # Small margin below logo
    
    # Calculate button label area height if labels are provided
    button_area_height = 0
    if button_labels:
        # Measure label height
        if hasattr(draw, "textbbox"):
            bbox = draw.textbbox((0, 0), "Test", font=label_font)
            button_area_height = (bbox[3] - bbox[1]) + 20  # Add padding
        else:
            button_area_height = draw.textsize("Test", font=label_font)[1] + 20

    # Calculate metrics for all lines
    metrics = []
    for line in lines:
        line_w, line_h = _measure_mixed(line)
        metrics.append((line, line_w, line_h))
    
    spacing = 10
    total_height = sum(h for _, _, h in metrics) + spacing * (len(metrics) - 1)
    
    # Calculate available height: screen - logo - button labels
    available_height = preview_size[1] - logo_height - logo_margin - button_area_height
    
    # Start y position below logo
    start_y = logo_height + logo_margin
    
    # Calculate how many lines fit on screen
    if not metrics:
        visible_metrics = []
        visible_lines = 0
    else:
        # Estimate lines that fit (using average line height)
        avg_line_height = total_height / len(metrics) if metrics else 0
        if avg_line_height > 0:
            max_visible_lines = int(available_height / (avg_line_height + spacing))
        else:
            max_visible_lines = len(metrics)
        
        # Clamp scroll_offset
        max_scroll = max(0, len(metrics) - max_visible_lines)
        scroll_offset = max(0, min(scroll_offset, max_scroll))
        
        # Determine which lines to render
        visible_metrics = metrics[scroll_offset:]
        visible_lines = len(visible_metrics)
    
    # Draw visible lines starting below logo
    y = start_y
    left_margin = 20  # Left margin for menu alignment
    for line, w, h in visible_metrics:
        # Only draw if it fits in available space
        if y + h <= preview_size[1] - button_area_height:
            x = left_margin  # Left-align instead of center
            _draw_mixed(line, x, y)
            y += h + spacing
        else:
            break  # Stop if we've run out of space
    
    # Draw button labels at the bottom
    if button_labels:
        # Make slots 15% smaller and center them
        slot_width = (preview_size[0] / 6) * 0.85
        total_width = slot_width * 6
        start_x = (preview_size[0] - total_width) / 2
        label_y = preview_size[1] - button_area_height + 10
        for slot in range(1, 7):  # Slots 1-6
            if slot in button_labels:
                label_text = button_labels[slot]
                # Center the label in its slot
                if hasattr(draw, "textbbox"):
                    bbox = draw.textbbox((0, 0), label_text, font=label_font)
                    label_w = bbox[2] - bbox[0]
                else:
                    label_w = draw.textsize(label_text, font=label_font)[0]
                label_x = start_x + (slot - 1) * slot_width + (slot_width - label_w) / 2
                draw.text((label_x, label_y), label_text, font=label_font, fill=(255, 255, 255, 255))
    
    # Stamp logo before converting to numpy
    base = _stamp_logo(base)
    
    rgba = np.array(base, dtype=np.uint8)
    rgba[..., 3] = 255
    return rgba

def show_update_screen(lines, footer_left=None, footer_right=None, button_labels=None):
    global current_screen, pending_overlay, idle_since, overlay_ready
    overlay_key = "update:" + "|".join(lines) + f"|{footer_left}|{footer_right}|{button_labels}"
    overlay = overlay_cache.get(overlay_key)
    if overlay is None:
        overlay = _build_update_overlay(lines, footer_left=footer_left, footer_right=footer_right, button_labels=button_labels)
        overlay_cache[overlay_key] = overlay
    current_screen = "update"
    idle_since = None
    pending_overlay = overlay
    if not preview_started:
        logging.info("Update screen: starting preview for overlay")
        try:
            camera_start()
        except Exception as exc:
            logging.error("Update screen: failed to start preview: %s", exc)
    overlay_ready = True
    _apply_overlay_if_ready()
    if pending_overlay is not None:
        threading.Timer(0.2, _apply_overlay_if_ready).start()

def _git(*args):
    logging.info("update: git %s", " ".join(args))
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

def _get_version_label() -> Optional[str]:
    result = _git("describe", "--tags", "--exact-match")
    if result.returncode == 0:
        return result.stdout.strip() or None
    sha_result = _git("rev-parse", "--short", "HEAD")
    if sha_result.returncode != 0:
        logging.info("version: git rev-parse failed: %s", sha_result.stderr.strip())
        return None
    return sha_result.stdout.strip() or None

def _fetch_tags() -> bool:
    # Mirror update.sh: convert SSH remote to HTTPS so fetch works without SSH keys
    # (SSH keys are stripped from distributed images for security)
    url_result = _git("config", "--get", "remote.origin.url")
    if url_result.returncode == 0:
        remote_url = url_result.stdout.strip()
        if remote_url.startswith("git@github.com:"):
            https_url = "https://github.com/" + remote_url[len("git@github.com:"):]
            logging.info("update: switching origin to HTTPS (%s)", https_url)
            _git("remote", "set-url", "origin", https_url)
    result = _git("fetch", "--tags", "--prune", "--force")
    if result.returncode != 0:
        logging.error(
            "update: git fetch failed (code=%s) stderr=%s",
            result.returncode,
            result.stderr.strip(),
        )
        return False
    remote_tags = set()
    remote_result = _git("ls-remote", "--tags", "origin")
    if remote_result.returncode == 0:
        for line in remote_result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            ref = parts[1]
            if ref.endswith("^{}"):
                ref = ref[:-3]
            if ref.startswith("refs/tags/"):
                remote_tags.add(ref[len("refs/tags/"):])
        local_result = _git("tag", "--list")
        if local_result.returncode == 0:
            local_tags = {line.strip() for line in local_result.stdout.splitlines() if line.strip()}
            stale_tags = sorted(local_tags - remote_tags)
            for tag in stale_tags:
                logging.info("update: deleting stale local tag %s", tag)
                _git("tag", "-d", tag)
    else:
        logging.info("update: ls-remote --tags failed: %s", remote_result.stderr.strip())
    if result.stdout.strip():
        logging.info("update: git fetch stdout=%s", result.stdout.strip())
    return True

def _has_dev_keys() -> bool:
    """Return True if ~/.ssh/id_filmkorn-scanner-dev_ed25519* keys are present."""
    ssh_dir = os.path.expanduser("~/.ssh")
    try:
        return any(
            f.startswith("id_filmkorn-scanner-dev_ed25519")
            for f in os.listdir(ssh_dir)
        )
    except OSError:
        return False


def _list_tags() -> list:
    result = _git("tag", "--list", "--sort=v:refname")
    if result.returncode != 0:
        logging.error(
            "update: git tag failed (code=%s) stderr=%s",
            result.returncode,
            result.stderr.strip(),
        )
        return []
    tags = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if OTA_TAG_PREFIX:
        if _has_dev_keys():
            # Dev keys present: also include bare X.Y.Z tags (no prefix)
            bare_semver = re.compile(r"^\d+\.\d+\.\d+(?:-[A-Za-z0-9._-]+)?$")
            tags = [t for t in tags if t.startswith(OTA_TAG_PREFIX) or bare_semver.match(t)]
            logging.info("update: dev keys found, including un-prefixed tags")
        else:
            tags = [t for t in tags if t.startswith(OTA_TAG_PREFIX)]
    tag_pattern = re.compile(r"^v?\d+\.\d+\.\d+(?:-[A-Za-z0-9._-]+)?$")
    filtered = [tag for tag in tags if tag_pattern.match(tag)]
    logging.info("update: found %d tags, %d installable", len(tags), len(filtered))
    if filtered:
        logging.info("update: installable tags: %s", ", ".join(filtered))
    return filtered

def _get_current_tag() -> Optional[str]:
    result = _git("describe", "--tags", "--exact-match")
    if result.returncode != 0:
        logging.info("update: no exact tag for current commit")
        return None
    logging.info("update: current tag is %s", result.stdout.strip())
    return result.stdout.strip() or None

def _show_update_selection():
    global current_screen, pending_overlay, overlay_ready, update_confirmation_mode, update_confirmation_selected, update_scroll_offset, preview_started
    if update_confirmation_mode:
        lines = [_("update.confirm-title"), "", ""]
        lines.append("> " + _("update.no") if update_confirmation_selected == 0 else "  " + _("update.no"))
        lines.append("> " + _("update.yes") if update_confirmation_selected == 1 else "  " + _("update.yes"))
        lines.append("")
        button_labels = {2: _("btn.back"), 3: _("btn.up"), 5: _("btn.down"), 6: _("btn.ok")}
        overlay = _build_menu_overlay(lines, button_labels=button_labels, scroll_offset=0)
        current_screen = "update_confirm"
        pending_overlay = overlay
        if not preview_started:
            try:
                camera_start()
            except Exception as exc:
                logging.error("Update confirm screen: failed to start preview: %s", exc)
        overlay_ready = True
        _apply_overlay_if_ready()
        if pending_overlay is not None:
            threading.Timer(0.2, _apply_overlay_if_ready).start()
        return
    
    if update_error:
        logging.error("update: error=%s", update_error)
        show_update_screen([_("update.error"), update_error, _("update.check-connection")])
        return
    if not update_tags:
        logging.info("update: no installable tags")
        show_update_screen([_("update.no-update"), _("update.no-tags")])
        return

    lines = [_("update.title"), "", ""]
    for i, tag in enumerate(update_tags):
        prefix = "> " if i == update_selected else "  "
        lines.append(prefix + tag)
    lines.append("")
    if update_current_tag:
        lines.append(_("update.current", tag=update_current_tag))
    
    # Calculate scroll offset to keep selected item visible
    selected_line_idx = 3 + update_selected  # 3 = title + 2 empty lines
    logo_height = _get_logo_height()
    button_area_height = 60
    available_height = preview_size[1] - logo_height - 10 - button_area_height if preview_size else 400
    estimated_line_height = 40
    max_visible_lines = max(1, int(available_height / estimated_line_height))
    
    # Adjust scroll to keep selected item visible
    if selected_line_idx < update_scroll_offset:
        update_scroll_offset = max(0, selected_line_idx)
    elif selected_line_idx >= update_scroll_offset + max_visible_lines:
        update_scroll_offset = max(0, selected_line_idx - max_visible_lines + 1)
    
    button_labels = {2: _("btn.back"), 3: _("btn.up"), 5: _("btn.down"), 6: _("btn.ok")}
    overlay = _build_menu_overlay(lines, button_labels=button_labels, scroll_offset=update_scroll_offset)
    current_screen = "update"
    pending_overlay = overlay
    if not preview_started:
        try:
            camera_start()
        except Exception as exc:
            logging.error("Update screen: failed to start preview: %s", exc)
    overlay_ready = True
    _apply_overlay_if_ready()
    if pending_overlay is not None:
        threading.Timer(0.2, _apply_overlay_if_ready).start()

def _enter_update_mode():
    global update_mode, update_tags, update_selected, update_current_tag, update_error, update_confirmation_mode
    logging.info("update: entering update mode")
    update_mode = True
    update_error = None
    update_confirmation_mode = False
    
    # Show menu immediately with cached tags (if any) for instant feedback
    try:
        update_tags = _list_tags()  # Get cached tags first
        update_current_tag = _get_current_tag()
        if update_tags:
            update_selected = len(update_tags) - 1
        else:
            update_selected = 0
        _show_update_selection()  # Show menu immediately
    except Exception as exc:
        logging.exception("update: failed to show cached tags: %s", exc)
        update_tags = []
        update_selected = 0
        update_current_tag = None
        _show_update_selection()
    
    # Then fetch tags in background and update menu when done
    def _fetch_and_update():
        global update_tags, update_selected, update_current_tag, update_error
        try:
            if not _fetch_tags():
                update_error = "Fetch failed"
                update_tags = []
                update_selected = 0
                update_current_tag = None
            else:
                update_tags = _list_tags()
                update_current_tag = _get_current_tag()
                if update_tags:
                    update_selected = len(update_tags) - 1
                else:
                    update_selected = 0
            _show_update_selection()
        except Exception as exc:
            logging.exception("update: fetch failed: %s", exc)
            update_error = "Unexpected error"
            update_tags = []
            update_selected = 0
            update_current_tag = None
            _show_update_selection()
    
    # Start fetch in background thread
    threading.Thread(target=_fetch_and_update, daemon=True).start()

def _update_prev(_args=None):
    global update_selected, update_confirmation_mode, update_confirmation_selected
    if not update_mode:
        _show_update_selection()
        return
    if update_confirmation_mode:
        # Navigate confirmation menu
        update_confirmation_selected = (update_confirmation_selected - 1) % 2
        logging.info("update: confirmation selected %s", "No" if update_confirmation_selected == 0 else "Yes")
        _show_update_selection()
        return
    if not update_tags:
        _show_update_selection()
        return
    update_selected = (update_selected - 1) % len(update_tags)
    logging.info("update: selected tag %s", update_tags[update_selected])
    _show_update_selection()

def _update_next(_args=None):
    global update_selected, update_confirmation_mode, update_confirmation_selected
    if not update_mode:
        _show_update_selection()
        return
    if update_confirmation_mode:
        # Navigate confirmation menu
        update_confirmation_selected = (update_confirmation_selected + 1) % 2
        logging.info("update: confirmation selected %s", "No" if update_confirmation_selected == 0 else "Yes")
        _show_update_selection()
        return
    if not update_tags:
        _show_update_selection()
        return
    update_selected = (update_selected + 1) % len(update_tags)
    logging.info("update: selected tag %s", update_tags[update_selected])
    _show_update_selection()

def _start_update(tag: str):
    global update_in_progress
    update_in_progress = True
    logging.info("update: starting update to %s", tag)
    # Delete MCU hex hash file so MCU firmware will be verified/flashed on next boot
    # This ensures the MCU firmware matches the updated code
    if os.path.exists(MCU_HEX_HASH_FILE):
        try:
            os.remove(MCU_HEX_HASH_FILE)
            logging.info("update: deleted .mcu_hex_hash to force MCU firmware check on next boot")
        except Exception as exc:
            logging.warning("update: failed to delete .mcu_hex_hash: %s", exc)
    show_update_screen([_("update.updating", tag=tag), _("update.please-wait")])
    update_script = os.path.join(os.path.dirname(__file__), "ota-updating", "update.sh")
    try:
        subprocess.run(
            ["sudo", "systemctl", "reset-failed", "filmkorn-update.service"],
            check=False,
        )
        subprocess.Popen(
            [
                "sudo",
                "systemd-run",
                "--unit=filmkorn-update",
                "--collect",
                "--no-ask-password",
                "/bin/bash",
                update_script,
                tag,
            ],
            cwd=repo_root,
        )
    except Exception as exc:
        logging.exception("update: failed to launch update script: %s", exc)
        show_update_screen([_("update.failed"), _("update.could-not-start")])

def _confirm_update_after_delay(tag: str):
    show_update_screen([_("update.warning1"), _("update.warning2")])
    def _start():
        clear_overlay()
        _start_update(tag)
    threading.Timer(5.0, _start).start()

def _update_confirm(_args=None):
    global update_confirmation_mode, update_confirmation_selected
    if not update_mode:
        return
    if update_confirmation_mode:
        # In confirmation menu - handle Yes/No selection
        if update_confirmation_selected == 1:  # Yes selected
            selected = update_tags[update_selected]
            logging.info("update: confirmed tag %s", selected)
            update_confirmation_mode = False
            _confirm_update_after_delay(selected)
        else:  # No selected - go back to tag selection
            logging.info("update: confirmation cancelled")
            update_confirmation_mode = False
            _show_update_selection()
        return
    if not update_tags:
        _show_update_selection()
        return
    # Show confirmation menu
    selected = update_tags[update_selected]
    logging.info("update: show confirmation for tag %s", selected)
    update_confirmation_mode = True
    update_confirmation_selected = 0  # Default to "No"
    _show_update_selection()

def _update_cancel(_args=None):
    global update_mode, menu_mode, update_confirmation_mode
    if not update_mode:
        return
    if update_confirmation_mode:
        # Cancel confirmation - go back to tag selection
        logging.info("update: confirmation cancelled")
        update_confirmation_mode = False
        _show_update_selection()
        return
    logging.info("update: canceled by user")
    update_mode = False
    update_confirmation_mode = False
    # Clear update screen first
    clear_overlay()
    # If we came from menu, show menu (will be cleared if MENU_EXIT follows)
    # If Arduino exits menu completely (STOP pressed), it will send CMD_MENU_EXIT
    # next, which will call _exit_menu_mode() to clear menu_mode and hide menu
    if menu_mode:
        _show_menu_screen()
    else:
        show_ready_to_scan()

# --- AWB Menu ---

def _load_awb_setting() -> int:
    """Load the stored AWB mode index from file. Returns 2 (Daylight) as default."""
    if os.path.exists(AWB_FILE):
        try:
            with open(AWB_FILE, "r") as f:
                idx = int(f.read().strip())
                if 0 <= idx < len(AWB_OPTIONS):
                    return idx
        except (ValueError, IOError):
            pass
    return 2  # Default to Daylight (~5500K)

def _save_awb_setting(idx: int):
    """Save the AWB mode index to file."""
    try:
        with open(AWB_FILE, "w") as f:
            f.write(str(idx))
        logging.info("awb: saved setting %d (%s)", idx, AWB_OPTIONS[idx][0])
    except IOError as e:
        logging.error("awb: failed to save setting: %s", e)

def _get_current_awb_mode():
    """Get the current AWB mode enum based on stored setting."""
    idx = _load_awb_setting()
    return AWB_OPTIONS[idx][1]

def _show_awb_selection():
    global awb_selected, awb_scroll_offset, current_screen, pending_overlay, overlay_ready, preview_started, awb_stored_idx
    # Show options in vertical list (like settings menu)
    lines = [_("awb.title"), "", ""]
    for i, (label, _awb_mode) in enumerate(AWB_OPTIONS):
        prefix = "> " if i == awb_selected else "  "
        lines.append(prefix + label)
    lines.append("")
    stored_label = AWB_OPTIONS[awb_stored_idx][0]
    lines.append(_("awb.current", label=stored_label))

    selected_line_idx = 3 + awb_selected  # 3 = title + 2 empty lines
    logo_height = _get_logo_height()
    button_area_height = 60
    available_height = preview_size[1] - logo_height - 10 - button_area_height if preview_size else 400
    estimated_line_height = 40
    max_visible_lines = max(1, int(available_height / estimated_line_height))

    if selected_line_idx < awb_scroll_offset:
        awb_scroll_offset = max(0, selected_line_idx)
    elif selected_line_idx >= awb_scroll_offset + max_visible_lines:
        awb_scroll_offset = max(0, selected_line_idx - max_visible_lines + 1)

    button_labels = {2: _("btn.back"), 3: _("btn.up"), 5: _("btn.down"), 6: _("btn.ok")}
    overlay = _build_menu_overlay(lines, button_labels=button_labels, scroll_offset=awb_scroll_offset)
    current_screen = "awb"
    pending_overlay = overlay
    if not preview_started:
        try:
            camera_start()
        except Exception as exc:
            logging.error("AWB screen: failed to start preview: %s", exc)
    overlay_ready = True
    _apply_overlay_if_ready()
    if pending_overlay is not None:
        threading.Timer(0.2, _apply_overlay_if_ready).start()

def _enter_awb_mode():
    global awb_mode, awb_selected, awb_stored_idx
    logging.info("awb: entering AWB menu")
    awb_mode = True
    # Load and cache the stored setting once when entering menu
    awb_stored_idx = _load_awb_setting()
    awb_selected = awb_stored_idx
    _show_awb_selection()

def _awb_prev(_args=None):
    global awb_selected
    if not awb_mode:
        return
    awb_selected = (awb_selected - 1) % len(AWB_OPTIONS)
    logging.info("awb: selected %s", AWB_OPTIONS[awb_selected][0])
    _show_awb_selection()

def _awb_next(_args=None):
    global awb_selected
    if not awb_mode:
        return
    awb_selected = (awb_selected + 1) % len(AWB_OPTIONS)
    logging.info("awb: selected %s", AWB_OPTIONS[awb_selected][0])
    _show_awb_selection()

def _awb_confirm(_args=None):
    global awb_mode, awb_stored_idx, menu_mode
    if not awb_mode:
        return
    logging.info("awb: confirmed %s", AWB_OPTIONS[awb_selected][0])
    _save_awb_setting(awb_selected)
    awb_stored_idx = awb_selected  # Update cached stored index
    awb_mode = False
    try:
        tell_arduino(Command.AWB_EXIT)
    except Exception as exc:
        logging.warning("awb: failed to notify controller to exit AWB mode: %s", exc)
    _apply_camera_controls()
    # If we came from menu, go back to menu; otherwise show ready screen
    if menu_mode:
        _show_menu_screen()
    else:
        show_ready_to_scan()

def _awb_cancel(_args=None):
    global awb_mode, menu_mode
    if not awb_mode:
        return
    logging.info("awb: canceled by user")
    awb_mode = False
    try:
        tell_arduino(Command.AWB_EXIT)
    except Exception as exc:
        logging.warning("awb: failed to notify controller to exit AWB mode: %s", exc)
    # If we came from menu, go back to menu; otherwise show ready screen
    if menu_mode:
        _show_menu_screen()
    else:
        show_ready_to_scan()

# --- End AWB Menu ---

# --- Scan Target Menu ---

def _load_target_setting() -> int:
    """Load the stored scan target mode index from file. Returns 2 (GPIO5) as default."""
    if os.path.exists(TARGET_FILE):
        try:
            with open(TARGET_FILE, "r") as f:
                idx = int(f.read().strip())
                if 0 <= idx < len(TARGET_OPTIONS):
                    return idx
        except (ValueError, IOError):
            pass
    return 2  # Default to GPIO5 (auto mode)

def _save_target_setting(idx: int):
    try:
        with open(TARGET_FILE, "w") as f:
            f.write(str(idx))
        logging.info("target: saved setting %d (%s)", idx, TARGET_OPTIONS[idx][0])
    except IOError as e:
        logging.error("target: failed to save setting: %s", e)

def _show_target_selection():
    global target_selected, target_scroll_offset, current_screen, pending_overlay, overlay_ready, preview_started, target_stored_idx
    lines = [_("target.title"), "", ""]
    for i, (label, _target_loc) in enumerate(TARGET_OPTIONS):
        prefix = "> " if i == target_selected else "  "
        lines.append(prefix + label)
    lines.append("")
    stored_label = TARGET_OPTIONS[target_stored_idx][0]
    lines.append(_("target.current", label=stored_label))

    selected_line_idx = 3 + target_selected  # 3 = title + 2 empty lines
    logo_height = _get_logo_height()
    button_area_height = 60
    available_height = preview_size[1] - logo_height - 10 - button_area_height if preview_size else 400
    estimated_line_height = 40
    max_visible_lines = max(1, int(available_height / estimated_line_height))

    if selected_line_idx < target_scroll_offset:
        target_scroll_offset = max(0, selected_line_idx)
    elif selected_line_idx >= target_scroll_offset + max_visible_lines:
        target_scroll_offset = max(0, selected_line_idx - max_visible_lines + 1)

    button_labels = {2: _("btn.back"), 3: _("btn.up"), 5: _("btn.down"), 6: _("btn.ok")}
    overlay = _build_menu_overlay(lines, button_labels=button_labels, scroll_offset=target_scroll_offset)
    current_screen = "target"
    pending_overlay = overlay
    if not preview_started:
        logging.info("Target selection: starting preview for overlay")
        try:
            camera_start()
        except Exception as exc:
            logging.error("Target selection: failed to start preview: %s", exc)
    overlay_ready = True
    _apply_overlay_if_ready()
    if pending_overlay is not None:
        threading.Timer(0.2, _apply_overlay_if_ready).start()

def _enter_target_mode():
    global target_mode, target_selected, target_stored_idx
    logging.info("target: entering target selection menu")
    target_mode = True
    # Turn WiFi off so host connectivity uses eth0 only (avoids asymmetric routing)
    _wifi_radio_off()
    # Load and cache the stored setting once when entering menu
    target_stored_idx = _load_target_setting()
    target_selected = target_stored_idx
    _show_target_selection()

def _target_prev(_args=None):
    global target_selected, target_validation_error, target_mode
    if not target_mode:
        logging.warning("target: _target_prev called but target_mode is False")
        return
    # Ignore navigation when in validation error mode
    if target_validation_error:
        logging.debug("target: ignoring prev navigation in validation error mode")
        return
    target_selected = (target_selected - 1) % len(TARGET_OPTIONS)
    logging.info("target: selected %s (prev)", TARGET_OPTIONS[target_selected][0])
    _show_target_selection()

def _target_next(_args=None):
    global target_selected, target_validation_error, target_mode
    if not target_mode:
        logging.warning("target: _target_next called but target_mode is False")
        return
    # Ignore navigation when in validation error mode
    if target_validation_error:
        logging.debug("target: ignoring next navigation in validation error mode")
        return
    target_selected = (target_selected + 1) % len(TARGET_OPTIONS)
    logging.info("target: selected %s (next)", TARGET_OPTIONS[target_selected][0])
    _show_target_selection()

def _validate_host_target() -> list:
    """Validate Host Computer target connectivity.
    Returns list of failed tests: empty if all pass, otherwise ["ping"], ["ssh"], ["write"], or combinations.
    """
    failures = []
    user_and_host = _read_user_and_host()
    scan_destination = _read_scan_destination()
    
    if not user_and_host:
        logging.warning("target: no host configured for validation")
        failures.append("config")
        return failures
    
    host = user_and_host.split("@", 1)[-1] if user_and_host else None
    if not host:
        failures.append("config")
        return failures
    
    # Test 1: Ping (via eth0 only - sync must use ethernet, not WiFi)
    logging.info("target: validating ping to %s via eth0", host)
    ping_result = subprocess.run(
        ["ping", "-c", "1", "-W", "2", "-I", "eth0", host],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if ping_result.returncode != 0:
        logging.warning("target: ping failed to %s via eth0 (connect scanner via ethernet cable to same network as host)", host)
        failures.append("ping")
        return failures  # No point testing further if ping fails
    logging.info("target: ping to %s via eth0 OK", host)
    
    # Test 2: SSH + Write (combined)
    if scan_destination:
        logging.info("target: validating write to %s:%s", user_and_host, scan_destination)
        probe_path = os.path.join(scan_destination, ".filmkorn_write_test")
        quoted_probe = shlex.quote(probe_path)
        remote_cmd = f"touch {quoted_probe} && rm -f {quoted_probe}"
        result = subprocess.run(
            [
                "ssh",
                "-i",
                "/home/pi/.ssh/id_filmkorn-scanner_ed25519",
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=5",
                "-o", "BindInterface=eth0",
                user_and_host,
                remote_cmd,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            logging.warning("target: ssh/write test failed: %s", stderr)
            # Try to distinguish between SSH connection failure and write failure
            # If we can't connect via SSH, mark as "ssh" failure
            # If we can connect but can't write, mark as "write" failure
            if "Connection" in stderr or "Could not resolve" in stderr or "Permission denied" in stderr:
                failures.append("ssh")
            else:
                failures.append("write")
    
    return failures

def _show_target_validation_error():
    """Show error screen with specific failed tests."""
    global current_screen, pending_overlay, overlay_ready, preview_started, target_validation_failures
    
    lines = [_("target.error.title"), ""]

    if "config" in target_validation_failures:
        lines.append(_("target.error.no-config"))
        lines.append(_("target.error.run-pairing"))
    else:
        if "ping" in target_validation_failures:
            lines.append(_("target.error.ping"))
            lines.append(_("target.error.ping-hint"))
        if "ssh" in target_validation_failures:
            lines.append(_("target.error.ssh"))
            lines.append(_("target.error.ssh-hint"))
        if "write" in target_validation_failures:
            lines.append(_("target.error.write"))
            lines.append(_("target.error.write-hint"))

    button_labels = {2: _("btn.back")}
    overlay = _build_menu_overlay(lines, button_labels=button_labels)
    current_screen = "target_validation_error"
    pending_overlay = overlay
    if not preview_started:
        try:
            camera_start()
        except Exception as exc:
            logging.error("Target validation error: failed to start preview: %s", exc)
    overlay_ready = True
    _apply_overlay_if_ready()
    if pending_overlay is not None:
        threading.Timer(0.2, _apply_overlay_if_ready).start()

def _target_confirm(_args=None):
    global target_mode, target_stored_idx, target_selected, menu_mode, storage_location, target_validation_error, target_validation_failures
    if not target_mode:
        return
    
    # If we're in validation error mode, just go back to target selection
    if target_validation_error:
        target_validation_error = False
        target_validation_failures = []
        # Ensure target_mode is still True (should be, but make it explicit)
        target_mode = True
        logging.info("target: returning to target selection from validation error (via confirm)")
        # Don't send any command to Arduino - it should still be in target mode
        # The Arduino's targetMode flag should still be true
        _show_target_selection()
        return
    
    logging.info("target: confirmed %s", TARGET_OPTIONS[target_selected][0])
    
    # Store previous selection in case validation fails
    previous_selected = target_stored_idx
    
    # If selecting "Host Computer", validate first
    target_value = TARGET_OPTIONS[target_selected][1]
    if target_value == 0:  # Host Computer
        logging.info("target: validating Host Computer connectivity...")
        show_update_screen([_("target.checking"), _("target.please-wait")])
        failures = _validate_host_target()
        if failures:
            logging.warning("target: validation failed: %s", failures)
            # Restore previous selection
            target_selected = previous_selected
            target_validation_error = True
            target_validation_failures = failures
            _show_target_validation_error()
            return  # Don't change target, stay in target_mode
    
    # Validation passed (or not needed), proceed with target change
    _save_target_setting(target_selected)
    target_stored_idx = target_selected  # Update cached stored index
    target_mode = False
    target_validation_error = False
    target_validation_failures = []
    _wifi_radio_on()
    try:
        tell_arduino(Command.TARGET_EXIT)
    except Exception as exc:
        logging.warning("target: failed to notify controller to exit target mode: %s", exc)
    
    # Apply the new target setting
    if target_value == 2:
        # GPIO5 mode - read from GPIO
        storage_location = GPIO.input(5)
        logging.info("target: switched to GPIO5 mode, current GPIO5 state: %d", storage_location)
    else:
        # Manual mode - set storage_location directly
        storage_location = target_value
        logging.info("target: switched to manual mode, storage_location: %d", storage_location)
    
    # Update lsyncd config (this may block if connection fails, but will respect shutting_down)
    switch_lsyncd_config(storage_location)
    
    # If we came from menu, go back to menu; otherwise show ready screen
    # Note: show_ready_to_scan() will use the updated storage_location to show the correct screen
    if menu_mode:
        _show_menu_screen()
    else:
        # Explicitly show the correct ready screen based on storage_location
        if storage_location == 1:
            show_screen("ready-to-scan-local")
        elif storage_location == 0:
            show_screen("ready-to-scan-net")
        else:
            show_ready_to_scan()

def _target_cancel(_args=None):
    global target_mode, menu_mode, target_validation_error, target_validation_failures
    if not target_mode:
        return
    
    # If we're in validation error mode, go back to target selection
    if target_validation_error:
        target_validation_error = False
        target_validation_failures = []
        # Ensure target_mode is still True (should be, but make it explicit)
        target_mode = True
        logging.info("target: returning to target selection from validation error")
        # Don't send TARGET_EXIT to Arduino - it should still be in target mode
        # The Arduino's targetMode flag should still be true from when we entered
        _show_target_selection()
        return
    
    logging.info("target: canceled by user")
    target_mode = False
    target_validation_error = False
    target_validation_failures = []
    _wifi_radio_on()
    try:
        tell_arduino(Command.TARGET_EXIT)
    except Exception as exc:
        logging.warning("target: failed to notify controller to exit target mode: %s", exc)
    # If we came from menu, go back to menu; otherwise show ready screen
    if menu_mode:
        _show_menu_screen()
    else:
        show_ready_to_scan()

# --- End Scan Target Menu ---

# --- WiFi Setup Menu ---

def _load_wifi_networks() -> list:
    """Load the stored WiFi networks from file. Returns list of dicts with 'ssid' and 'timestamp'."""
    if os.path.exists(WIFI_NETWORKS_FILE):
        try:
            import json
            with open(WIFI_NETWORKS_FILE, "r") as f:
                data = json.load(f)
                return data.get("networks", [])[:5]  # Limit to 5
        except (ValueError, IOError) as e:
            logging.error("wifi: failed to load networks: %s", e)
    return []

def _save_wifi_network(ssid: str):
    """Save a WiFi network to the networks file, keeping only the last 5."""
    import json
    import time
    networks = _load_wifi_networks()
    # Remove existing entry for this SSID if present
    networks = [n for n in networks if n.get("ssid") != ssid]
    # Add new entry at the beginning
    networks.insert(0, {"ssid": ssid, "timestamp": int(time.time())})
    # Keep only the last 5
    networks = networks[:5]
    try:
        with open(WIFI_NETWORKS_FILE, "w") as f:
            json.dump({"networks": networks}, f)
        logging.info("wifi: saved network %s", ssid)
    except IOError as e:
        logging.error("wifi: failed to save network: %s", e)

def _show_wifi_menu():
    """Display the WiFi setup menu with configured networks."""
    global wifi_selected, wifi_scroll_offset, current_screen, pending_overlay, overlay_ready, preview_started
    
    networks = _load_wifi_networks()
    lines = [_("wifi.title"), "", ""]

    menu_options = [_("wifi.start-setup")]
    for net in networks:
        menu_options.append(f"  {net.get('ssid', 'Unknown')}")

    for i, option in enumerate(menu_options):
        prefix = "> " if i == wifi_selected else "  "
        lines.append(prefix + option)

    lines.append("")
    if networks:
        lines.append(_("wifi.configured"))
    else:
        lines.append(_("wifi.no-networks"))
    
    # Calculate scroll offset to keep selected item visible
    selected_line_idx = 3 + wifi_selected
    logo_height = _get_logo_height()
    button_area_height = 60
    available_height = preview_size[1] - logo_height - 10 - button_area_height if preview_size else 400
    estimated_line_height = 40
    max_visible_lines = max(1, int(available_height / estimated_line_height))
    
    if selected_line_idx < wifi_scroll_offset:
        wifi_scroll_offset = max(0, selected_line_idx)
    elif selected_line_idx >= wifi_scroll_offset + max_visible_lines:
        wifi_scroll_offset = max(0, selected_line_idx - max_visible_lines + 1)
    
    button_labels = {2: _("btn.back"), 3: _("btn.up"), 5: _("btn.down"), 6: _("btn.ok")}
    overlay = _build_menu_overlay(lines, button_labels=button_labels, scroll_offset=wifi_scroll_offset)
    current_screen = "wifi"
    pending_overlay = overlay
    logging.info("wifi: showing menu with %d options, selected=%d, preview_started=%s", 
                 len(menu_options), wifi_selected, preview_started)
    if not preview_started:
        logging.info("WiFi menu: starting preview for overlay")
        try:
            camera_start()
        except Exception as exc:
            logging.error("WiFi menu: failed to start preview: %s", exc)
    overlay_ready = True
    _apply_overlay_if_ready()
    if pending_overlay is not None:
        threading.Timer(0.2, _apply_overlay_if_ready).start()

def _enter_wifi_mode():
    """Enter the WiFi setup menu."""
    global wifi_mode, wifi_selected, wifi_scroll_offset
    logging.info("wifi: entering WiFi setup menu")
    wifi_mode = True
    wifi_selected = 0
    wifi_scroll_offset = 0
    _show_wifi_menu()

def _wifi_prev(_args=None):
    """Navigate up in the WiFi menu."""
    global wifi_selected
    if not wifi_mode:
        return
    networks = _load_wifi_networks()
    menu_count = 1 + len(networks)  # "Start Setup" + configured networks
    wifi_selected = (wifi_selected - 1 + menu_count) % menu_count
    logging.info("wifi: selected item %d", wifi_selected)
    _show_wifi_menu()

def _wifi_next(_args=None):
    """Navigate down in the WiFi menu."""
    global wifi_selected
    if not wifi_mode:
        return
    networks = _load_wifi_networks()
    menu_count = 1 + len(networks)
    wifi_selected = (wifi_selected + 1) % menu_count
    logging.info("wifi: selected item %d", wifi_selected)
    _show_wifi_menu()

def _wifi_confirm(_args=None):
    """Confirm selection in the WiFi menu."""
    global wifi_mode, wifi_portal_process, menu_mode
    logging.info("wifi: _wifi_confirm called, wifi_mode=%s, wifi_selected=%d", wifi_mode, wifi_selected)
    if not wifi_mode:
        logging.warning("wifi: _wifi_confirm called but wifi_mode is False")
        return
    
    if wifi_selected == 0:
        # Start captive portal setup
        logging.info("wifi: starting captive portal setup")
        _start_wifi_portal()
    else:
        # Selected a configured network - reconnect using existing NM profile
        networks = _load_wifi_networks()
        logging.info("wifi: selected item %d, networks count=%d", wifi_selected, len(networks))
        if wifi_selected - 1 < len(networks):
            ssid = networks[wifi_selected - 1].get("ssid", "Unknown")
            logging.info("wifi: reconnecting to configured network: %s", ssid)
            _reconnect_wifi(ssid)
        else:
            logging.warning("wifi: wifi_selected %d out of range (networks: %d)", wifi_selected, len(networks))

def _wifi_cancel(_args=None):
    """Cancel and exit the WiFi menu."""
    global wifi_mode, wifi_portal_process, menu_mode
    if not wifi_mode:
        return
    
    logging.info("wifi: canceled by user")
    
    # Stop portal if running
    if wifi_portal_process is not None:
        logging.info("wifi: stopping captive portal")
        try:
            wifi_portal_process.terminate()
            wifi_portal_process.wait(timeout=5)
        except Exception as e:
            logging.warning("wifi: failed to stop portal cleanly: %s", e)
            try:
                wifi_portal_process.kill()
            except:
                pass
        wifi_portal_process = None
    
    wifi_mode = False
    
    # If we came from menu, go back to menu; otherwise show ready screen
    if menu_mode:
        _show_menu_screen()
    else:
        show_ready_to_scan()

def _reconnect_wifi(ssid: str):
    """Reconnect to a configured WiFi network using the existing NM profile."""
    global current_screen, pending_overlay, overlay_ready, wifi_mode, preview_started
    
    logging.info("wifi: attempting to reconnect to %s", ssid)
    
    lines = [
        _("wifi.heading"),
        "",
        "",
        _("wifi.connecting-to"),
        f"  {ssid}",
        "",
        _("wifi.please-wait"),
    ]
    button_labels = {}  # No buttons during connection
    overlay = _build_menu_overlay(lines, button_labels=button_labels)
    current_screen = "wifi-connecting"
    pending_overlay = overlay
    overlay_ready = True
    _apply_overlay_if_ready()
    
    success = False
    try:
        # Run as pi user with system bus (same as portal)
        result = subprocess.run(
            ["sudo", "-u", "pi", "nmcli", "connection", "up", "id", ssid],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            logging.info("wifi: successfully reconnected to %s", ssid)
            success = True
        else:
            err = (result.stderr or result.stdout or "").strip()
            logging.warning("wifi: reconnect to %s failed (exit %d): %s", ssid, result.returncode, err)
    except subprocess.TimeoutExpired:
        logging.warning("wifi: reconnect to %s timed out", ssid)
    except Exception as e:
        logging.warning("wifi: reconnect failed: %s", e)
    
    if success:
        lines = [
            _("wifi.heading"),
            "",
            "",
            _("wifi.connected-to"),
            f"  {ssid}",
            "",
            "",
        ]
        overlay = _build_menu_overlay(lines, button_labels={})
        pending_overlay = overlay
        overlay_ready = True
        _apply_overlay_if_ready()
        time.sleep(2)

        wifi_mode = False
        try:
            tell_arduino(Command.WIFI_EXIT)
        except Exception as exc:
            logging.warning("wifi: failed to notify controller to exit WiFi mode: %s", exc)
        if menu_mode:
            _show_menu_screen()
        else:
            show_ready_to_scan()
    else:
        lines = [
            _("wifi.heading"),
            "",
            "",
            _("wifi.connect-failed"),
            "",
            _("wifi.could-not-connect"),
            f"  {ssid}",
        ]
        button_labels = {6: _("btn.ok")}
        overlay = _build_menu_overlay(lines, button_labels=button_labels)
        pending_overlay = overlay
        overlay_ready = True
        _apply_overlay_if_ready()
        time.sleep(3)
        
        # Return to WiFi menu
        _show_wifi_menu()


def _start_wifi_portal():
    """Start the WiFi captive portal subprocess."""
    global wifi_portal_process, current_screen, pending_overlay, overlay_ready
    
    portal_script = os.path.join(os.path.dirname(__file__), "wifi_portal", "portal.py")
    
    if not os.path.exists(portal_script):
        logging.error("wifi: portal script not found at %s", portal_script)
        lines = [_("wifi.error-title"), "", "", _("wifi.portal-not-installed"), "", _("wifi.update-firmware")]
        button_labels = {2: _("btn.back")}
        overlay = _build_menu_overlay(lines, button_labels=button_labels)
        current_screen = "wifi-error"
        pending_overlay = overlay
        overlay_ready = True
        _apply_overlay_if_ready()
        return

    lines = [
        _("wifi.title"),
        "",
        "",
        _("wifi.portal-starting"),
        "",
        _("wifi.portal-connect"),
        _("wifi.portal-network-name"),
        "",
        _("wifi.portal-open-website"),
        _("wifi.portal-configure"),
    ]
    button_labels = {2: _("btn.cancel")}
    overlay = _build_menu_overlay(lines, button_labels=button_labels)
    current_screen = "wifi-portal"
    pending_overlay = overlay
    overlay_ready = True
    _apply_overlay_if_ready()
    
    # Start portal as subprocess
    try:
        wifi_portal_process = subprocess.Popen(
            ["sudo", "python3", portal_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        logging.info("wifi: captive portal started with PID %d", wifi_portal_process.pid)
        
        # Start a thread to monitor the portal process
        threading.Thread(target=_monitor_wifi_portal, daemon=True).start()
    except Exception as e:
        logging.error("wifi: failed to start captive portal: %s", e)
        wifi_portal_process = None

def _monitor_wifi_portal():
    """Monitor the WiFi portal subprocess for completion."""
    global wifi_portal_process, wifi_mode
    
    if wifi_portal_process is None:
        return
    
    portal_exit_code = -1
    try:
        # Read output and wait for completion
        output, _ = wifi_portal_process.communicate(timeout=300)  # 5 minute timeout
        portal_exit_code = wifi_portal_process.returncode
        
        logging.info("wifi: portal exited with code %d", portal_exit_code)
        if output:
            for line in output.strip().split('\n'):
                logging.info("wifi portal: %s", line)
        
        if portal_exit_code == 0:
            logging.info("wifi: portal completed successfully")
    except subprocess.TimeoutExpired:
        logging.warning("wifi: portal timed out")
        wifi_portal_process.kill()
    except Exception as e:
        logging.error("wifi: error monitoring portal: %s", e)
    finally:
        wifi_portal_process = None
        
        # Return to menu if still in wifi mode
        logging.info("wifi: portal monitor cleanup, wifi_mode=%s, portal_exit_code=%d, menu_mode=%s", 
                     wifi_mode, portal_exit_code, menu_mode)
        if wifi_mode:
            if portal_exit_code == 0:
                # Success - exit WiFi menu and return to main menu
                logging.info("wifi: portal succeeded, exiting WiFi mode")
                wifi_mode = False
                try:
                    tell_arduino(Command.WIFI_EXIT)
                except Exception as exc:
                    logging.warning("wifi: failed to notify controller to exit WiFi mode: %s", exc)
                if menu_mode:
                    _show_menu_screen()
                else:
                    show_ready_to_scan()
            else:
                # Failed/cancelled - return to WiFi submenu so user can try again
                logging.info("wifi: portal cancelled/failed, returning to WiFi menu")
                _show_wifi_menu()
        else:
            logging.warning("wifi: portal monitor - wifi_mode was False")

# --- End WiFi Setup Menu ---

def _run_otp_scheduler() -> bool:
    candidates = [
        "/usr/local/sbin/filmkorn-otp-schedule.sh",
        os.path.join(repo_root, "raspi", "scanner-helpers", "filmkorn-otp-schedule.sh"),
    ]
    for path in candidates:
        if os.path.exists(path):
            schedule = subprocess.run(
                ["sudo", path],
                check=False,
                capture_output=True,
                text=True,
            )
            if schedule.returncode == 0:
                logging.info("pairing: expiry scheduled via %s", path)
                return True
            logging.error(
                "pairing: failed to schedule OTP expiry via %s: %s",
                path,
                schedule.stderr.strip(),
            )
            return False
    logging.error("pairing: OTP scheduler script not found")
    return False

def _enable_pairing_password(code: str, expires_at: int) -> bool:
    config_lines = "PasswordAuthentication yes\nKbdInteractiveAuthentication yes\n"
    try:
        result = subprocess.run(
            [
                "sudo",
                "/bin/sh",
                "-c",
                "mkdir -p /etc/ssh/sshd_config.d && "
                "printf '%s' \"$1\" | tee /etc/ssh/sshd_config.d/filmkorn-password.conf >/dev/null",
                "_",
                config_lines,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logging.error("pairing: failed to enable password auth: %s", result.stderr.strip())
            return False
        logging.info("pairing: password authentication enabled")
        expiry_result = subprocess.run(
            [
                "sudo",
                "/bin/sh",
                "-c",
                "mkdir -p /var/lib/filmkorn && printf '%s\\n' \"$1\" | tee /var/lib/filmkorn/otp_expires_at >/dev/null",
                "_",
                str(expires_at),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if expiry_result.returncode != 0:
            logging.error("pairing: failed to write OTP expiry: %s", expiry_result.stderr.strip())
            return False
        logging.info("pairing: expiry timestamp written")
        passwd_result = subprocess.run(
            ["sudo", "/bin/sh", "-c", "echo \"pi:$1\" | chpasswd", "_", code],
            check=False,
            capture_output=True,
            text=True,
        )
        if passwd_result.returncode != 0:
            logging.error("pairing: failed to set pi password: %s", passwd_result.stderr.strip())
            return False
        logging.info("pairing: pi password set")
        if not _run_otp_scheduler():
            return False
        restart = subprocess.run(
            ["sudo", "/bin/sh", "-c", "systemctl reload ssh || systemctl restart ssh"],
            check=False,
            capture_output=True,
            text=True,
        )
        if restart.returncode != 0:
            logging.error("pairing: failed to reload ssh: %s", restart.stderr.strip())
            return False
        logging.info("pairing: ssh reloaded")
        return True
    except Exception as exc:
        logging.exception("pairing: enable password auth failed: %s", exc)
        return False

def _exit_pairing_mode_screen():
    global pairing_mode, pairing_exit_pending
    if not pairing_mode:
        return
    logging.info("pairing: auto-leaving pairing screen")
    pairing_mode = False
    if state.scanning:
        logging.info("pairing: forcing scan state to stopped")
        state.scanning = False
    pairing_exit_pending = True
    if not sleep_mode:
        show_ready_to_scan()
    _reset_sleep_button_state()

def _cancel_pairing_mode():
    global pairing_mode, menu_mode
    if not pairing_mode:
        return
    logging.info("pairing: canceled by controller")
    pairing_mode = False
    global pairing_exit_pending
    pairing_exit_pending = True
    if state.scanning:
        logging.info("pairing: forcing scan state to stopped")
        state.scanning = False
    # If we came from menu, go back to menu; otherwise show ready screen
    if menu_mode:
        _show_menu_screen()
    else:
        show_ready_to_scan()
    _reset_sleep_button_state()

def _enter_pairing_mode():
    global pairing_mode
    logging.info("pairing: entering pairing mode")
    logging.info(
        "pairing: enter state sleep_mode=%s current_screen=%s update_mode=%s",
        sleep_mode,
        current_screen,
        update_mode,
    )
    pairing_mode = True
    code = f"{secrets.randbelow(1000000):06d}"
    expires_at = int(time.time()) + 120
    if not _enable_pairing_password(code, expires_at):
        show_update_screen([_("pairing.failed"), _("pairing.ssh-error")], button_labels={2: _("btn.back")})
        return
    logging.info("pairing: otp code generated")
    show_update_screen([_("pairing.code-title"), code, _("pairing.code-hint")], button_labels={2: _("btn.back")})
    threading.Timer(120.0, _exit_pairing_mode_screen).start()

def _export_logs() -> str:
    export_script = os.path.join(os.path.dirname(__file__), "scanner-helpers", "export-logs.sh")
    if not os.path.exists(export_script):
        raise FileNotFoundError(export_script)
    result = subprocess.run(
        ["sudo", export_script],
        check=False,
        capture_output=True,
        text=True,
    )
    logging.info("logs: export stdout: %s", result.stdout.strip())
    if result.stderr.strip():
        logging.warning("logs: export stderr: %s", result.stderr.strip())
    if result.returncode != 0:
        raise RuntimeError(f"export failed code={result.returncode}")
    return result.stdout.strip()

def _enter_logs_mode():
    global logs_mode, logs_in_progress, last_status_screen
    if logs_mode or logs_in_progress:
        return
    logging.info("logs: entering log export mode")
    logs_mode = True
    logs_in_progress = True
    show_screen("generating-debug-log")
    try:
        output_path = _export_logs()
        logging.info("logs: export saved %s", output_path)
    except Exception as exc:
        logging.exception("logs: export failed: %s", exc)
    finally:
        logs_in_progress = False
        logs_mode = False
        try:
            tell_arduino(Command.LOGS_EXIT)
        except Exception as exc:
            logging.warning("logs: failed to notify controller to exit logs mode: %s", exc)
        # If we came from menu, go back to menu; otherwise show ready screen
        if menu_mode:
            _show_menu_screen()
        elif last_status_screen:
            show_screen(last_status_screen)
        else:
            show_ready_to_scan()

def _enter_unpair_mode():
    global unpair_mode, unpair_confirmation_mode, unpair_confirmation_selected
    logging.info("unpair: entering unpair confirmation mode")
    unpair_mode = True
    unpair_confirmation_mode = True
    unpair_confirmation_selected = 0  # Default to "No"
    _show_unpair_confirmation()

def _show_unpair_confirmation():
    global current_screen, pending_overlay, overlay_ready, preview_started
    lines = [_("unpair.title"), "", ""]
    lines.append("> " + _("update.no") if unpair_confirmation_selected == 0 else "  " + _("update.no"))
    lines.append("> " + _("update.yes") if unpair_confirmation_selected == 1 else "  " + _("update.yes"))
    lines.append("")
    lines.append(_("unpair.detail"))
    button_labels = {2: _("btn.back"), 3: _("btn.up"), 5: _("btn.down"), 6: _("btn.ok")}
    overlay = _build_menu_overlay(lines, button_labels=button_labels)
    current_screen = "unpair_confirm"
    pending_overlay = overlay
    if not preview_started:
        try:
            camera_start()
        except Exception as exc:
            logging.error("Unpair confirm screen: failed to start preview: %s", exc)
    overlay_ready = True
    _apply_overlay_if_ready()
    if pending_overlay is not None:
        threading.Timer(0.2, _apply_overlay_if_ready).start()

def _unpair_prev(_args=None):
    global unpair_confirmation_selected
    if not unpair_mode:
        return
    unpair_confirmation_selected = (unpair_confirmation_selected - 1) % 2
    logging.info("unpair: selected %s", "No" if unpair_confirmation_selected == 0 else "Yes")
    _show_unpair_confirmation()

def _unpair_next(_args=None):
    global unpair_confirmation_selected
    if not unpair_mode:
        return
    unpair_confirmation_selected = (unpair_confirmation_selected + 1) % 2
    logging.info("unpair: selected %s", "No" if unpair_confirmation_selected == 0 else "Yes")
    _show_unpair_confirmation()

def _unpair_confirm(_args=None):
    global unpair_mode, unpair_confirmation_mode, unpair_in_progress
    if not unpair_mode:
        return
    if unpair_confirmation_selected == 0:
        # User selected "No" - go back to menu
        logging.info("unpair: user selected No, returning to menu")
        _unpair_cancel()
        return
    # User selected "Yes" - proceed with unpair
    logging.info("unpair: user confirmed, proceeding with factory reset")
    unpair_mode = False
    unpair_confirmation_mode = False
    unpair_in_progress = True
    unpair_script = os.path.join(os.path.dirname(__file__), "pairing", "unpair-from-client.sh")
    if not os.path.exists(unpair_script):
        logging.error("unpair: script not found at %s", unpair_script)
    else:
        try:
            result = subprocess.run(
                ["sudo", unpair_script],
                check=False,
                capture_output=True,
                text=True,
            )
            logging.info("unpair: stdout: %s", result.stdout.strip())
            if result.stderr.strip():
                logging.warning("unpair: stderr: %s", result.stderr.strip())
            if result.returncode != 0:
                logging.error("unpair: script failed code=%s", result.returncode)
        except Exception as exc:
            logging.exception("unpair: failed to run script: %s", exc)
    
    # Delete all preference dotfiles
    preference_files = [
        AWB_FILE,           # .awb_mode
        TARGET_FILE,        # .scan_target_mode
        MCU_HEX_HASH_FILE,  # .mcu_hex_hash
        WIFI_NETWORKS_FILE, # .wifi_networks
        ".user_and_host",
        ".scan_destination",
        ".host_path",
    ]
    for pref_file in preference_files:
        file_path = pref_file if os.path.isabs(pref_file) else os.path.join(os.path.dirname(__file__), pref_file)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logging.info("unpair: deleted preference file: %s", file_path)
            except Exception as exc:
                logging.warning("unpair: failed to delete %s: %s", file_path, exc)
    
    show_screen("unpaired-from-client")
    time.sleep(5)
    # Go back to menu or ready screen
    if menu_mode:
        _show_menu_screen()
    elif last_status_screen:
        show_screen(last_status_screen)
    else:
        show_ready_to_scan()
    unpair_in_progress = False

def _unpair_cancel(_args=None):
    global unpair_mode, unpair_confirmation_mode
    logging.info("unpair: canceled by user")
    unpair_mode = False
    unpair_confirmation_mode = False
    clear_overlay()
    # Return to menu if we came from there
    # Note: Arduino should have already changed state to MENU_MAIN when it sent CMD_UNPAIR_CANCEL
    # But if we're canceling from Python (e.g., user selected "No"), tell Arduino to go back
    if menu_mode:
        try:
            tell_arduino(Command.MENU_EXIT)  # This will be handled as menu back, not full exit
        except Exception as exc:
            logging.warning("unpair: failed to notify controller: %s", exc)
        _show_menu_screen()
    else:
        show_ready_to_scan()

def _show_menu_screen():
    global current_screen, pending_overlay, idle_since, overlay_ready, menu_selected, menu_scroll_offset, awb_stored_idx, target_stored_idx
    # Ensure AWB setting is loaded (in case it changed)
    awb_stored_idx = _load_awb_setting()
    target_stored_idx = _load_target_setting()
    lines = [_("menu.title"), "", ""]  # Extra empty line after title
    for i, item_key in enumerate(MENU_ITEMS):
        prefix = "> " if i == menu_selected else "  "
        if item_key == "menu.item.preview-wb":
            awb_label = AWB_OPTIONS[awb_stored_idx][0]
            k_value = awb_label.replace("~", "").replace("K", "").strip()
            display_item = _("menu.item.preview-wb", k=k_value)
        elif item_key == "menu.item.scan-target":
            target_label = TARGET_OPTIONS[target_stored_idx][0]
            display_item = _("menu.item.scan-target", target=target_label)
        elif item_key == "menu.item.language":
            locale_name = _("locale.name")
            display_item = _("menu.item.language", name=locale_name)
        else:
            display_item = _(item_key)
        lines.append(prefix + display_item)
    lines.append("")  # Empty line after menu items

    # Calculate scroll offset to keep selected item visible
    selected_line_idx = 3 + menu_selected  # 3 = title + 2 empty lines
    logo_height = _get_logo_height()
    button_area_height = 60  # Approximate
    available_height = preview_size[1] - logo_height - 10 - button_area_height if preview_size else 400
    estimated_line_height = 40  # Approximate line height
    max_visible_lines = max(1, int(available_height / estimated_line_height))

    # Adjust scroll to keep selected item visible
    if selected_line_idx < menu_scroll_offset:
        menu_scroll_offset = max(0, selected_line_idx)
    elif selected_line_idx >= menu_scroll_offset + max_visible_lines:
        menu_scroll_offset = max(0, selected_line_idx - max_visible_lines + 1)

    # Button labels: Slot 2=Back, 3=Up, 5=Down, 6=OK
    button_labels = {2: _("btn.back"), 3: _("btn.up"), 5: _("btn.down"), 6: _("btn.ok")}
    overlay = _build_menu_overlay(lines, button_labels=button_labels, scroll_offset=menu_scroll_offset)
    current_screen = "menu"
    idle_since = None
    pending_overlay = overlay
    if not preview_started:
        logging.info("Menu screen: starting preview for overlay")
        try:
            camera_start()
        except Exception as exc:
            logging.error("Menu screen: failed to start preview: %s", exc)
    overlay_ready = True
    _apply_overlay_if_ready()
    if pending_overlay is not None:
        threading.Timer(0.2, _apply_overlay_if_ready).start()

def _enter_menu_mode():
    global menu_mode, menu_selected
    logging.info("menu: entering menu mode")
    menu_mode = True
    menu_selected = 0
    _show_menu_screen()

def _exit_menu_mode():
    global menu_mode
    logging.info("menu: exiting menu mode")
    menu_mode = False
    try:
        tell_arduino(Command.MENU_EXIT)
    except Exception as exc:
        logging.warning("menu: failed to notify controller to exit menu mode: %s", exc)
    # Always show the current ready screen based on storage_location, not the cached last_status_screen
    # This ensures the screen is correct after target changes
    show_ready_to_scan()

def _menu_prev():
    global menu_selected
    if not menu_mode:
        return
    menu_selected = (menu_selected - 1 + len(MENU_ITEMS)) % len(MENU_ITEMS)
    logging.info("menu: selected item %d: %s", menu_selected, MENU_ITEMS[menu_selected])
    _show_menu_screen()

def _menu_next():
    global menu_selected
    if not menu_mode:
        return
    menu_selected = (menu_selected + 1) % len(MENU_ITEMS)
    logging.info("menu: selected item %d: %s", menu_selected, MENU_ITEMS[menu_selected])
    _show_menu_screen()

def _cycle_locale():
    """Cycle to the next available locale, save it, and refresh the menu."""
    global current_locale
    codes = [c for c, _ in LOCALE_OPTIONS]
    current_idx = codes.index(current_locale) if current_locale in codes else 0
    new_locale = codes[(current_idx + 1) % len(codes)]
    logging.info("locale: switching %s → %s", current_locale, new_locale)
    _save_locale_setting(new_locale)
    _load_locale(new_locale)
    overlay_cache.clear()
    _show_menu_screen()


def _menu_select():
    global menu_selected, current_locale
    if not menu_mode:
        return
    selected_item = MENU_ITEMS[menu_selected]
    logging.info("menu: selected item %d: %s", menu_selected, selected_item)

    if selected_item == "menu.item.language":
        _cycle_locale()
        return
    # For all other items the Arduino drives the submenu transition.

def _apply_overlay_if_ready():
    global pending_overlay, overlay_supported, overlay_retry_count, overlay_retry_timer
    if no_camera:
        return
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
    if no_camera:
        return
    pending_overlay = None
    current_screen = None
    if overlay_ready:
        camera.set_overlay(None)


def _is_ethernet_up() -> bool:
    """Check if eth0 has link and is UP."""
    try:
        result = subprocess.run(
            ["ip", "link", "show", "eth0"],
            capture_output=True, text=True, timeout=2
        )
        return "state UP" in result.stdout
    except Exception as e:
        logging.warning("ethernet: failed to check eth0 status: %s", e)
        return False


def _wifi_radio_off():
    """Turn WiFi radio off (avoids asymmetric routing when using eth0 for host sync)."""
    try:
        subprocess.run(
            ["nmcli", "radio", "wifi", "off"],
            capture_output=True, text=True, timeout=5, check=False
        )
        logging.info("wifi: radio turned off")
    except Exception as e:
        logging.warning("wifi: failed to turn radio off: %s", e)


def _wifi_radio_on():
    """Turn WiFi radio on (e.g. after host target/scan or at scanner start)."""
    try:
        subprocess.run(
            ["nmcli", "radio", "wifi", "on"],
            capture_output=True, text=True, timeout=5, check=False
        )
        logging.info("wifi: radio turned on")
    except Exception as e:
        logging.warning("wifi: failed to turn radio on: %s", e)


def _show_ethernet_warning():
    """Show a warning that ethernet is not connected (required for host scanning)."""
    global current_screen, pending_overlay, overlay_ready
    logging.warning("ethernet: eth0 is not connected, cannot scan to host")
    
    lines = [
        _("ethernet.title"),
        "",
        "",
        _("ethernet.line1"),
        _("ethernet.line2"),
        "",
        _("ethernet.line3"),
        _("ethernet.line4"),
        "",
        _("ethernet.line5"),
        _("ethernet.line6"),
    ]
    button_labels = {2: _("btn.back")}
    overlay = _build_menu_overlay(lines, button_labels=button_labels)
    current_screen = "ethernet-warning"
    pending_overlay = overlay
    overlay_ready = True
    _apply_overlay_if_ready()


_LOGO_SCALE = 0.8  # Display the logo at 80% of its original size

def _get_logo_height() -> int:
    """Get the scaled height of the logo if it exists, otherwise return 0."""
    logo_path = "controller-screens/logo.png"
    if not os.path.exists(logo_path):
        return 0
    try:
        logo = Image.open(logo_path)
        return round(logo.size[1] * _LOGO_SCALE)
    except Exception:
        return 0

def _stamp_logo(base_img: Image.Image) -> Image.Image:
    """Stamp a logo onto the base image if logo.png exists in controller-screens/.

    The logo is scaled to _LOGO_SCALE and placed at the top center.
    If the logo doesn't exist, the image is returned unchanged.
    """
    logo_path = "controller-screens/logo.png"
    if not os.path.exists(logo_path):
        return base_img

    try:
        logo = Image.open(logo_path).convert("RGBA")
        new_w = round(logo.size[0] * _LOGO_SCALE)
        new_h = round(logo.size[1] * _LOGO_SCALE)
        logo = logo.resize((new_w, new_h), Image.LANCZOS)
        x = (base_img.size[0] - new_w) // 2  # Center horizontally
        y = 0  # At the very top
        base_img.paste(logo, (x, y), logo)
    except Exception as e:
        logging.warning(f"Failed to stamp logo: {e}")

    return base_img

def _draw_text_badge(base_img, text: str, position: str, y_offset: int = 0):
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
    pad = 0
    margin = 12
    if position == "bottom-right":
        x = max(0, preview_size[0] - text_w - margin)
    elif position == "bottom-center":
        x = max(0, (preview_size[0] - text_w) // 2)
    elif position == "top-right":
        x = max(0, preview_size[0] - text_w - margin)
    elif position == "top-left":
        x = margin
    else:
        x = margin
    if position == "top-left" or position == "top-right":
        y = y_offset  # Start at actual top, no margin
    else:
        y = max(0, preview_size[1] - text_h - margin)
    draw.rectangle(
        (x - pad, y - pad, x + text_w + pad, y + text_h + pad),
        fill=(0, 0, 0, 160),
    )
    draw.text((x, y), text, font=font, fill=(160, 160, 160, 255))

def _build_fps_overlay(text: str):
    if preview_size is None:
        return None
    if current_screen:
        base_overlay = overlay_cache.get(current_screen)
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
    if update_mode or pairing_mode:
        return
    show_shutter = state.scanning or current_screen in {
        "insert-film",
        "no-drive-connected",
        "ready-to-scan",
        "ready-to-scan-local",
        "ready-to-scan-net",
    }
    if current_screen == "waiting-for-files-to-sync" and not state.scanning:
        return
    if preview_size is None:
        return
    if current_screen:
        base_overlay = overlay_cache.get(current_screen)
    else:
        base_overlay = None
    if base_overlay is not None:
        base_img = Image.fromarray(base_overlay.copy(), "RGBA")
    else:
        base_img = Image.new("RGBA", preview_size, (0, 0, 0, 0))
    if last_fps_value is not None and state.scanning:
        _draw_text_badge(base_img, f"{last_fps_value:.1f} fps", "bottom-left")
    # Draw resolution label and shutter speed in top-left, stacked vertically
    top_left_y_offset = 0
    if (
        current_screen in STATUS_SCREENS
        and current_screen != "target-dir-does-not-exist"
        and last_resolution_label
    ):
        # Calculate actual badge height for proper spacing
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        except OSError:
            font = ImageFont.load_default()
        draw = ImageDraw.Draw(base_img)
        if hasattr(draw, "textbbox"):
            bbox = draw.textbbox((0, 0), last_resolution_label, font=font)
            text_h = bbox[3] - bbox[1]
        else:
            text_h = draw.textsize(last_resolution_label, font=font)[1]
        badge_height = text_h  # No padding, just text height
        _draw_text_badge(base_img, last_resolution_label, "top-left", top_left_y_offset)
        # Offset for next badge: text height + 1/4 character height spacing
        spacing = int(text_h * 0.25)  # 1/4 of character height
        top_left_y_offset = badge_height + spacing
    if last_shutter_value is not None and show_shutter:
        _draw_text_badge(base_img, _format_shutter_speed(last_shutter_value), "top-left", top_left_y_offset)
    if current_screen in STATUS_SCREENS and current_version_label:
        _draw_text_badge(base_img, current_version_label, "top-right")
    
    # Stamp logo before converting to numpy (hide during scanning)
    if not state.scanning:
        base_img = _stamp_logo(base_img)
    
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

def clear_tty1():
    try:
        with open("/dev/tty1", "w") as tty:
            tty.write("\033[2J\033[H")
            tty.flush()
    except Exception:
        pass

def _show_tty_warning(text: str):
    """Print a warning message to tty1 (used when camera is unavailable)."""
    try:
        with open("/dev/tty1", "w") as tty:
            tty.write("\033[2J\033[H")
            tty.write(f"\n\n  *** {text} ***\n")
            tty.flush()
        logging.info("Displayed tty1 warning: %s", text)
    except Exception as exc:
        logging.error("Failed to write tty1 warning: %s", exc)


def _enter_sleep_mode():
    global sleep_mode, preview_started, camera_running, pairing_mode, current_screen, pairing_exit_pending
    logging.info("Entering sleep mode")
    if pairing_mode:
        logging.info("pairing: exiting pairing screen due to sleep")
        pairing_mode = False
        current_screen = None
        pairing_exit_pending = True
    try:
        GPIO.output(UC_POWER_GPIO, GPIO.LOW)
    except Exception:
        pass
    if not no_camera and camera is not None:
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
    global overlay_ready, overlay_supported, overlay_retry_count, overlay_retry_timer, sleep_mode, pairing_mode
    global power_warning_active, usb3_warning_active, usb_speed_warning_logged, usb_power_warning_logged
    global last_usb_power_check, last_usb_speed_check
    logging.info("Waking up")
    if pairing_mode:
        logging.info("pairing: clearing pairing mode on wake")
        pairing_mode = False
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
    if not no_camera and camera is not None:
        if preview_started:
            try:
                camera.stop_preview()
            except Exception:
                pass
        camera_start()
        overlay_supported = True
        overlay_ready = True
    elif no_camera:
        _show_tty_warning("No Camera Connected")
    overlay_retry_count = 0
    overlay_retry_timer = None
    # Restore appropriate screen after wake
    if menu_mode:
        # If we were in the menu, restore the menu screen
        threading.Timer(0.5, _show_menu_screen).start()
    elif update_mode:
        threading.Timer(0.5, _show_update_selection).start()
    elif awb_mode:
        threading.Timer(0.5, _show_awb_selection).start()
    elif target_mode:
        threading.Timer(0.5, _show_target_selection).start()
    elif unpair_mode:
        threading.Timer(0.5, _show_unpair_confirmation).start()
    else:
        screen_to_show = current_screen
        if screen_to_show in {"too-much-power", "no-usb3-drive"}:
            screen_to_show = last_status_screen
        if screen_to_show or last_status_screen:
            screen_to_show = screen_to_show or last_status_screen
            threading.Timer(0.5, show_screen, args=(screen_to_show,)).start()
        else:
            threading.Timer(0.5, show_ready_to_scan).start()
    threading.Timer(1.0, _post_wake_checks).start()
    sleep_mode = False
    power_warning_active = False
    usb3_warning_active = False
    usb_speed_warning_logged = False
    usb_power_warning_logged = False
    last_usb_power_check = 0.0
    last_usb_speed_check = 0.0

def _post_wake_checks():
    _check_usb_power_warning()
    if (
        storage_location == 1
        and current_screen in {"ready-to-scan-local", "insert-film", "no-usb3-drive"}
        and not state.scanning
    ):
        _check_usb3_speed_warning()

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

def _reset_sleep_button_state():
    global last_sleep_button_state, last_sleep_button_change, sleep_button_armed
    try:
        last_sleep_button_state = GPIO.input(26)
    except Exception:
        last_sleep_button_state = 1
    last_sleep_button_change = time.monotonic()
    sleep_button_armed = (last_sleep_button_state == 1)

def _apply_camera_controls():
    awb_mode_setting = _get_current_awb_mode()
    camera.set_controls({
        "AeEnable": True,
        "AwbEnable": True,
        "AwbMode": awb_mode_setting,
        "Brightness": 0.0,
        "Sharpness": 1.0,
        "Contrast": 1.0,
        "Saturation": 1.0,
        "ExposureValue": 0.0,
    })

def _create_camera_config(raw_size, raw_format="SBGGR12"):
    return camera.create_preview_configuration(
        main={"size": (preview_size), "format": "XBGR8888"},
        raw={"size": raw_size, "format": raw_format},  # uncompressed for best quality
        transform=Transform(rotation=180, hflip=True, vflip=False),
        buffer_count=4,  # increase from default 1 for better performance
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
    camera.configure(_create_camera_config(raw_size, raw_format))
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
    global ready_to_scan, last_status_screen
    ready_to_scan = False
    if current_screen in SCAN_BLOCKING_SCREENS:
        last_status_screen = "insert-film"
        return
    # When user has lamp on (preview only, no overlay), don't replace the preview with the overlay
    if current_screen is not None:
        logging.info("Showing Screen: Please insert film")
        show_screen("insert-film")
    else:
        last_status_screen = "insert-film"

def showReadyToScan(arg_bytes=None):
    global ready_to_scan, last_status_screen
    ready_to_scan = True
    if current_screen in SCAN_BLOCKING_SCREENS:
        return
    # When user has lamp on (preview only, no overlay), don't replace the preview with the overlay
    if current_screen is not None:
        logging.info("Showing Screen: Ready to Scan")
        show_ready_to_scan()
    else:
        if storage_location == 1 and not os.path.ismount("/mnt/usb"):
            last_status_screen = "no-drive-connected"
        elif storage_location == 1:
            last_status_screen = "ready-to-scan-local"
        elif storage_location == 0:
            last_status_screen = "ready-to-scan-net"
        else:
            last_status_screen = "ready-to-scan"

def _ready_screen_poll_loop():
    global ready_screen_polling, storage_location
    ready_screen_polling = True
    try:
        while (ready_to_scan or current_screen == "no-drive-connected") and not shutting_down:
            if sleep_mode:
                sleep(1)
                continue
            if storage_location == 1 and not os.path.ismount("/mnt/usb"):
                _ensure_usb_mount()
                if not os.path.ismount("/mnt/usb") and not shutting_down and current_screen != "no-drive-connected":
                    show_screen("no-drive-connected")
            # Check GPIO 5 for target switch state change (only if in GPIO5 mode)
            target_setting = _load_target_setting()
            if target_setting == 2:  # GPIO5 mode
                new_storage_location = GPIO.input(5)
                if new_storage_location != storage_location:
                    storage_location = new_storage_location
                    logging.info(
                        f"GPIO 5 changed while ready (1=HDD/local, 0=Net/remote): {storage_location}"
                    )
                    if storage_location == 1 and not os.path.ismount("/mnt/usb"):
                        if not shutting_down:
                            if current_screen != "no-drive-connected":
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
        last_available = get_available_disk_space()
        last_increase_at = time.time()
        restarted_lsyncd = False
        no_progress_timeout_s = 15

        while not shutting_down:
            try:
                if not _ramdisk_has_files():
                    break
            except FileNotFoundError:
                break
            available = get_available_disk_space()
            if available > last_available:
                last_available = available
                last_increase_at = time.time()
            if not restarted_lsyncd and time.time() - last_increase_at >= no_progress_timeout_s:
                logging.warning("No disk space increase detected; restarting filmkorn-lsyncd.service")
                subprocess.run(
                    ["sudo", "systemctl", "restart", "filmkorn-lsyncd.service"],
                    check=False,
                )
                last_increase_at = time.time()
                restarted_lsyncd = True
            sleep(1)
        try:
            os.sync()
        except OSError:
            pass
        if not shutting_down:
            if last_status_screen:
                show_screen(last_status_screen)
            else:
                show_ready_to_scan()
    finally:
        ramdisk_empty_polling = False

def show_ready_to_scan():
    global ready_to_scan
    # Don't show ready screen if we're in menu mode
    if menu_mode:
        return
    if storage_location == 1 and not os.path.ismount("/mnt/usb"):
        ready_to_scan = False
        show_screen("no-drive-connected")
        if not ready_screen_polling:
            threading.Thread(target=_ready_screen_poll_loop, daemon=True).start()
        return
    ready_to_scan = True
    if storage_location == 1:
        _ensure_usb_mount()
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
    if no_camera or camera_running:
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
    if no_camera:
        return
    camera.set_controls({"AeEnable": enabled})

def set_zoom_crop(x_frac: float, y_frac: float, w_frac: float, h_frac: float):
    if no_camera or sensor_size is None:
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
def tell_arduino(command: Command) -> bool:
    """Send a command to Arduino via I2C. Returns True if sent successfully, False otherwise."""
    # Check if arduino exists before trying to use it
    try:
        arduino_var = globals().get('arduino')
        arduino_addr = globals().get('arduino_i2c_address')
        if arduino_var is None or arduino_addr is None:
            logging.warning("tell_arduino: arduino not initialized yet, skipping command %s", command)
            return False
    except Exception:
        logging.warning("tell_arduino: arduino not initialized yet, skipping command %s", command)
        return False
    
    # Now we know arduino exists, use it
    max_retries = 5  # Set a max number of retries
    retry_delay = 0.1  # Initial delay between retries in seconds
    for attempt in range(max_retries):
        try:
            arduino_var.write_byte(arduino_addr, command.value)
            return True  # Success
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
    return False

# For retrieving (multi-byte) answers to explicit tells
def ask_arduino() -> Optional["list[int]"]:
    global arduino, arduino_i2c_address
    # Check if arduino is initialized
    if 'arduino' not in globals() or arduino is None:
        return None
    # Keep total retry block under ~0.5 s so we don't starve the camera pipeline.
    # V4L2 dequeue timer is 1 s; blocking longer can cause "Camera frontend has timed out".
    max_retries = 4
    retry_delay = 0.07
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
            retry_delay *= 2  # Exponential backoff: 50, 100, 200 ms → ~350 ms total
    logging.error("Failed to read from Arduino after several attempts. Attempting I2C bus recovery.")
    try:
        arduino.close()
        time.sleep(0.1)
        arduino = SMBus(1)
        logging.info("I2C bus recovery: SMBus reopened successfully")
    except Exception as exc:
        logging.error("I2C bus recovery failed: %s", exc)
    return None

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

def _get_mount_device(mount_point: str) -> Optional[str]:
    try:
        with open("/proc/mounts", "r") as file:
            for line in file:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == mount_point:
                    return parts[0]
    except Exception:
        return None
    return None

def _get_block_device_name(device_path: str) -> Optional[str]:
    if not device_path.startswith("/dev/"):
        return None
    name = os.path.basename(device_path)
    if name.startswith("nvme") or name.startswith("mmcblk"):
        return re.sub(r"p\d+$", "", name)
    return re.sub(r"\d+$", "", name)

def _find_usb_speed(block_device: str) -> Optional[float]:
    sys_path = os.path.realpath(os.path.join("/sys/class/block", block_device))
    current = sys_path
    while True:
        speed_path = os.path.join(current, "speed")
        if os.path.isfile(speed_path):
            try:
                with open(speed_path, "r") as file:
                    return float(file.read().strip())
            except Exception:
                return None
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None

def _dmesg_power_warning() -> Optional[str]:
    args = ["dmesg"]
    if dmesg_since:
        args.extend(["--since", dmesg_since])
    result = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        lower = line.lower()
        if "over-current" in lower:
            return line.strip()
        if "undervoltage" in lower or "under-voltage" in lower:
            return line.strip()
        if "insufficient power" in lower:
            return line.strip()
    return None

def _check_usb_power_warning() -> None:
    global last_usb_power_check, usb_power_warning_logged, power_warning_active
    now = time.monotonic()
    if now - last_usb_power_check < USB_POWER_CHECK_INTERVAL_S:
        return
    last_usb_power_check = now
    warning_line = _dmesg_power_warning()
    if not usb_power_warning_logged and warning_line:
        logging.warning("Detected USB power warning in dmesg: %s", warning_line)
        usb_power_warning_logged = True
        power_warning_active = True
    if power_warning_active and not sleep_mode:
        if state.scanning:
            state.stop_scan()
        if current_screen != "too-much-power":
            show_screen("too-much-power")

def _check_usb3_speed_warning() -> None:
    global last_usb_speed_check, usb_speed_warning_logged, usb3_warning_active
    now = time.monotonic()
    if now - last_usb_speed_check < USB3_CHECK_INTERVAL_S:
        return
    last_usb_speed_check = now
    if not os.path.ismount("/mnt/usb"):
        return
    mount_device = _get_mount_device("/mnt/usb")
    if not mount_device:
        return
    block_device = _get_block_device_name(mount_device)
    if not block_device:
        return
    speed = _find_usb_speed(block_device)
    if speed is None:
        return
    if speed >= 1000.0:
        usb_speed_warning_logged = False
        if usb3_warning_active:
            usb3_warning_active = False
            if current_screen == "no-usb3-drive":
                if last_status_screen:
                    show_screen(last_status_screen)
                else:
                    show_ready_to_scan()
        return
    if not usb_speed_warning_logged:
        logging.warning(
            "USB drive at /mnt/usb is running at %.0fMbit/s (USB3 is 5000M).",
            speed,
        )
        usb_speed_warning_logged = True
    usb3_warning_active = True
    if not sleep_mode and not power_warning_active:
        show_screen("no-usb3-drive")

def _read_user_and_host() -> Optional[str]:
    try:
        with open(".user_and_host", "r") as file:
            return file.read().strip()
    except Exception:
        return None

def _read_scan_destination() -> Optional[str]:
    try:
        with open(".scan_destination", "r") as file:
            return file.read().strip()
    except Exception:
        return None

def _read_host_path() -> Optional[str]:
    try:
        with open(".host_path", "r") as file:
            return file.read().strip()
    except Exception:
        return None

def _compute_hex_hash() -> str:
    """Compute SHA256 hash of the MCU HEX file."""
    import hashlib
    sha256 = hashlib.sha256()
    with open(MCU_HEX_PATH, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def _get_stored_hex_hash() -> str:
    """Get the stored hash of the last verified/flashed HEX file."""
    if not MCU_HEX_HASH_CACHE_ENABLED:
        return ""
    if os.path.isfile(MCU_HEX_HASH_FILE):
        try:
            with open(MCU_HEX_HASH_FILE, "r") as f:
                return f.read().strip()
        except Exception:
            pass
    return ""

def _save_hex_hash(hex_hash: str):
    """Save the hash of the current HEX file."""
    if not MCU_HEX_HASH_CACHE_ENABLED:
        return
    try:
        with open(MCU_HEX_HASH_FILE, "w") as f:
            f.write(hex_hash)
    except Exception as e:
        logging.warning("mcu: failed to save hex hash: %s", e)

def _verify_mcu_firmware() -> bool:
    global mcu_flash_checked, mcu_flash_error
    if mcu_flash_checked:
        return False
    mcu_flash_checked = True
    
    if not os.path.isfile(MCU_HEX_PATH):
        mcu_flash_error = f"missing hex: {MCU_HEX_PATH}"
        logging.error("mcu: %s", mcu_flash_error)
        return False
    
    # Check if HEX file has changed since last verification
    current_hash = _compute_hex_hash()
    stored_hash = _get_stored_hex_hash()
    if current_hash == stored_hash:
        logging.info("mcu: hex file unchanged (hash match), skipping avrdude verify")
        return False
    
    logging.info("mcu: hex file changed, starting firmware verify")
    if not os.path.isfile(MCU_AVRDUDE_CONF):
        mcu_flash_error = f"missing avrdude config: {MCU_AVRDUDE_CONF}"
        logging.error("mcu: %s", mcu_flash_error)
        return False
    if not os.path.isfile(MCU_AVRDUDE):
        mcu_flash_error = f"missing avrdude: {MCU_AVRDUDE}"
        logging.error("mcu: %s", mcu_flash_error)
        return False
    result = subprocess.run(
        [
            MCU_AVRDUDE,
            "-C",
            MCU_AVRDUDE_CONF,
            "-p",
            "atmega328p",
            "-c",
            "raspberry_pi_gpio",
            "-P",
            "gpiochip0",
            "-U",
            f"flash:v:{MCU_HEX_PATH}:i",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode == 0:
        logging.info("mcu: firmware already matches expected hex")
        _save_hex_hash(current_hash)  # Save hash on successful verify
        return False
    else:
        logging.warning("mcu: firmware mismatch detected (code=%s)", result.returncode)
        if result.stderr:
            logging.info("mcu: verify stderr: %s", result.stderr.strip())
        return True

def _run_mcu_flash_if_needed():
    global mcu_flash_in_progress, mcu_flash_error
    if mcu_flash_in_progress:
        return
    if not os.path.isfile(MCU_FLASH_SCRIPT):
        mcu_flash_error = f"missing flash script: {MCU_FLASH_SCRIPT}"
        logging.error("mcu: %s", mcu_flash_error)
        return
    mcu_flash_in_progress = True
    logging.info("mcu: flashing start")
    show_screen("updating-ino")
    result = subprocess.run(
        ["bash", MCU_FLASH_SCRIPT],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.stdout:
        logging.info("mcu: flash stdout: %s", result.stdout.strip())
    if result.stderr:
        logging.info("mcu: flash stderr: %s", result.stderr.strip())
    if result.returncode == 0:
        logging.info("mcu: flashing completed")
        # Save hash after successful flash
        try:
            _save_hex_hash(_compute_hex_hash())
        except Exception as e:
            logging.warning("mcu: failed to save hex hash after flash: %s", e)
    else:
        logging.error("mcu: flashing failed (code=%s)", result.returncode)
    mcu_flash_in_progress = False
    if last_status_screen:
        show_screen(last_status_screen)
    else:
        show_ready_to_scan()

def _ensure_usb_mount() -> bool:
    if os.path.ismount("/mnt/usb"):
        return True
    if sleep_mode:
        return False
    disk = None
    for _ in range(10):
        disk = _find_usb_disk_name()
        if disk:
            break
        sleep(0.2)
    if not disk or not disk.strip():
        logging.info("USB mount: no removable/USB disk found")
        return False
    disk = disk.strip()
    if not disk.startswith(("sd", "mmcblk", "nvme")):
        logging.info("USB mount: unsupported disk name '%s'", disk)
        return False
    logging.info("USB mount: attempting %s", disk)
    result = subprocess.run(
        ["sudo", "/usr/local/sbin/mount-largest-usb.sh", disk],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logging.info(
            "USB mount script returned %s stdout=%s stderr=%s",
            result.returncode,
            result.stdout.strip(),
            result.stderr.strip(),
        )
    return os.path.ismount("/mnt/usb")

def _check_usb_filesystem() -> bool:
    """Check and repair USB filesystem if needed. Returns True if check passed."""
    if not os.path.ismount("/mnt/usb"):
        logging.info("fsck: /mnt/usb not mounted, skipping")
        return False

    mount_device = _get_mount_device("/mnt/usb")
    if not mount_device:
        logging.info("fsck: could not determine mount device")
        return False

    logging.info("fsck: checking filesystem on %s", mount_device)
    show_screen("checking-filesystem")

    # Unmount for fsck (can't check mounted filesystem)
    umount_result = subprocess.run(
        ["sudo", "umount", "/mnt/usb"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if umount_result.returncode != 0:
        logging.warning("fsck: failed to unmount: %s", umount_result.stderr.strip())
        return False

    # Run fsck with auto-repair (-a for FAT/exFAT, -p for ext)
    fsck_result = subprocess.run(
        ["sudo", "fsck", "-y", mount_device],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    logging.info("fsck: exit code %s", fsck_result.returncode)
    if fsck_result.stdout:
        logging.info("fsck: stdout: %s", fsck_result.stdout.strip())
    if fsck_result.stderr:
        logging.info("fsck: stderr: %s", fsck_result.stderr.strip())

    # Remount using the original mount script to preserve options (uid/gid for exFAT)
    # Extract disk name from device path (e.g., /dev/sda2 -> sda)
    block_device = _get_block_device_name(mount_device)
    if block_device:
        mount_result = subprocess.run(
            ["sudo", "/usr/local/sbin/mount-largest-usb.sh", block_device],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    else:
        # Fallback to simple mount
        mount_result = subprocess.run(
            ["sudo", "mount", mount_device, "/mnt/usb"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    if mount_result.returncode != 0:
        logging.error("fsck: failed to remount: %s", mount_result.stderr.strip())
        return False

    # fsck exit codes: 0 = clean, 1 = errors corrected, 2+ = errors remain
    return fsck_result.returncode in (0, 1)


def _is_paired() -> bool:
    """True iff both .user_and_host and .host_path exist in the raspi dir."""
    raspi_dir = os.path.dirname(os.path.abspath(__file__))
    uah = os.path.join(raspi_dir, ".user_and_host")
    hp = os.path.join(raspi_dir, ".host_path")
    return os.path.isfile(uah) and os.path.isfile(hp)


def _ignore_app_metadata_for_usb(_dir: str, names: list) -> list:
    """Exclude macOS metadata when copying app to USB. Icon\\r is invalid on exFAT/FAT32."""
    return [
        n for n in names
        if n == "Icon\r" or n.endswith("\r") or n == ".DS_Store"
    ]


def _ensure_install_bundle_on_usb() -> None:
    """When unpaired and /mnt/usb mounted, seed Pair Filmkorn-Scanner (Mac).app on USB if missing.

    Copies the app to USB root with install scripts and helper inside
    Contents/Resources/install/. If the app exists but lacks install/, we add it (fixes old USBs).
    """
    if _is_paired():
        return
    if not os.path.ismount("/mnt/usb"):
        return
    usb_root = "/mnt/usb"
    host = os.path.join(repo_root, "host-computer")
    app_name = "Pair Filmkorn-Scanner (Mac).app"
    app_src = os.path.join(repo_root, "host-computer", "helper", app_name)
    app_dest = os.path.join(usb_root, app_name)
    install_res = os.path.join(app_dest, "Contents", "Resources", "install")
    install_cmd = os.path.join(install_res, "install_remote_scanning.command")
    helper_dest = os.path.join(install_res, "helper")
    bundle_files = [
        (os.path.join(host, "install_remote_scanning.sh"), install_res),
        (os.path.join(host, "install_remote_scanning.command"), install_res),
        (os.path.join(host, "helper", "pair.sh"), helper_dest),
        (os.path.join(host, "helper", "set_scan_destination.sh"), helper_dest),
        (os.path.join(host, "helper", "unpair.sh"), helper_dest),
    ]
    try:
        if not os.path.isdir(app_src):
            logging.warning(
                "USB install bundle: app source missing at %s, skipping",
                app_src,
            )
            return
        for src, _ in bundle_files:
            if not os.path.isfile(src):
                logging.warning(
                    "USB install bundle: script missing at %s, skipping",
                    src,
                )
                return
        need_app = not os.path.isdir(app_dest)
        need_install = not os.path.isfile(install_cmd)
        if not need_app and not need_install:
            return
        if need_app:
            shutil.copytree(
                app_src,
                app_dest,
                ignore=_ignore_app_metadata_for_usb,
            )
            logging.info("USB install bundle: copied app to %s", app_dest)
        if need_install:
            os.makedirs(helper_dest, exist_ok=True)
            for src, dstdir in bundle_files:
                shutil.copy2(src, dstdir)
                logging.debug("USB install bundle: copied %s -> %s", src, dstdir)
            if os.path.isfile(install_cmd):
                try:
                    os.sync()
                except OSError:
                    pass
                logging.info(
                    "Installed %s on USB%s",
                    app_name,
                    " (added install)" if not need_app else "",
                )
            else:
                logging.warning(
                    "USB install bundle: install scripts copied but %s missing",
                    install_cmd,
                )
    except Exception as exc:
        logging.warning("Failed to install bundle on USB: %s", exc)


def _find_usb_disk_name() -> Optional[str]:
    result = subprocess.run(
        ["lsblk", "-nr", "-o", "NAME,TYPE,RM,TRAN"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logging.info("lsblk failed: %s", result.stderr.strip())
        return None
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        name, dev_type, rm, tran = parts[:4]
        if dev_type == "disk" and (rm == "1" or tran == "usb"):
            return name
    return None

def _can_write_remote_path(user_and_host: str, scan_destination: str) -> bool:
    probe_path = os.path.join(scan_destination, ".filmkorn_write_test")
    quoted_probe = shlex.quote(probe_path)
    remote_cmd = f"touch {quoted_probe} && rm -f {quoted_probe}"
    result = subprocess.run(
        [
            "ssh",
            "-i",
            "/home/pi/.ssh/id_filmkorn-scanner_ed25519",
            "-o", "BindInterface=eth0",
            user_and_host,
            remote_cmd,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    logging.info(
        "lsyncd: remote write probe to %s:%s -> %s",
        user_and_host,
        probe_path,
        result.returncode,
    )
    if result.stderr:
        logging.info("lsyncd: remote write probe stderr: %s", result.stderr.strip())
    return result.returncode == 0

def switch_lsyncd_config(storage_location_param: int) -> None:
    """
    Switch lsyncd config via the lsyncd.active.conf symlink and restart lsyncd.

      - 1 => HDD / local USB (exFAT) target
      - 0 => Net / remote target
    """
    global target_mode, target_validation_error, target_validation_failures, menu_mode, storage_location
    global current_screen, pending_overlay, overlay_ready, preview_started
    # Use parameter value, but update global when we change it (e.g., GPIO5 mode)
    storage_location = storage_location_param
    target_conf = LSYNCD_CONF_LOCAL if storage_location == 1 else LSYNCD_CONF_NET
    try:
        if target_conf == LSYNCD_CONF_LOCAL and not os.path.ismount("/mnt/usb"):
            if current_screen != "no-drive-connected":
                show_screen("no-drive-connected")
            while not os.path.ismount("/mnt/usb") and not shutting_down:
                now = time.monotonic()
                _poll_sleep_button(now)
                if not sleep_mode and idle_since is not None and (now - idle_since) >= 900.0:
                    _enter_sleep_mode()
                    idle_since = None
                sleep(1)
            if shutting_down:
                logging.info("lsyncd: aborting config switch due to shutdown")
                return
            # USB is now mounted, show ready screen (only if not in menu mode)
            if storage_location == 1 and not menu_mode:
                show_screen("ready-to-scan-local")
        if target_conf == LSYNCD_CONF_NET:
            user_and_host = _read_user_and_host()
            host = user_and_host.split("@", 1)[-1] if user_and_host else None
            scan_destination = _read_scan_destination()
            if host:
                logging.info(
                    "lsyncd: checking host=%s user_and_host=%s scan_destination=%s",
                    host,
                    user_and_host,
                    scan_destination,
                )
                # Check if we're in preference mode (not GPIO5 mode)
                target_setting = _load_target_setting()
                is_preference_mode = (target_setting != 2)  # 2 = GPIO5 mode
                
                # Turn WiFi off so validation uses eth0 only (avoids asymmetric routing)
                _wifi_radio_off()

                # Run validation tests (same as menu)
                failures = _validate_host_target()
                
                if failures:
                    # Host validation failed
                    if is_preference_mode:
                        # Preference mode: enter target menu and show error
                        logging.warning("lsyncd: host validation failed in preference mode, entering target menu")
                        target_validation_error = True
                        target_validation_failures = failures
                        target_mode = True
                        menu_mode = True  # We're entering menu mode
                        # Tell Arduino to enter target mode (it will handle entering menu mode if needed)
                        # This must complete before showing the menu, otherwise buttons won't work
                        # Note: arduino might not be initialized yet if called during startup
                        # In that case, we'll set a flag and enter menu mode after arduino is ready
                        global pending_menu_entry
                        pending_menu_entry = True  # Flag to enter menu after arduino is ready
                        if tell_arduino(Command.TARGET_REENTER):
                            pending_menu_entry = False  # Success, clear flag
                            logging.info("lsyncd: sent TARGET_REENTER to Arduino, menu should be active now")
                        else:
                            logging.info("lsyncd: arduino not ready yet, will enter menu after initialization")
                        _show_target_validation_error()
                        return  # Don't proceed with lsyncd config
                    else:
                        # GPIO5 mode: show simple error message; restore WiFi
                        _wifi_radio_on()
                        logging.warning("lsyncd: host validation failed in GPIO5 mode")
                        error_lines = [
                            _("gpio5.error.title"),
                            "",
                            _("gpio5.error.line1"),
                            _("gpio5.error.line2"),
                            _("gpio5.error.line3"),
                            "",
                            _("gpio5.error.line4"),
                            _("gpio5.error.line5"),
                        ]
                        button_labels = {}  # No buttons, user must flip switch
                        overlay = _build_menu_overlay(error_lines, button_labels=button_labels)
                        current_screen = "gpio5_host_error"
                        pending_overlay = overlay
                        if not preview_started:
                            try:
                                camera_start()
                            except Exception as exc:
                                logging.error("GPIO5 host error: failed to start preview: %s", exc)
                        overlay_ready = True
                        _apply_overlay_if_ready()
                        # Wait for GPIO5 to change or shutdown
                        while not shutting_down:
                            new_storage_location = GPIO.input(5)
                            if new_storage_location != storage_location:
                                logging.info("lsyncd: GPIO5 changed from %d to %d, retrying", storage_location, new_storage_location)
                                storage_location = new_storage_location  # Update global
                                # Retry with new storage_location
                                switch_lsyncd_config(storage_location)
                                return
                            sleep(1)
                        return  # Don't proceed with lsyncd config
                
                # Validation passed, turn WiFi back on and proceed with normal lsyncd config
                _wifi_radio_on()
                logging.info("lsyncd: host validation passed, proceeding with config")
        _atomic_symlink(target_conf, LSYNCD_ACTIVE_CONF)
        logging.info(f"lsyncd: set active config -> {target_conf}")
        # Requires sudoers rule for pi to restart lsyncd without password.
        # subprocess.run(["sudo", "systemctl", "daemon-reload"], check=False)
        subprocess.run(["sudo", "systemctl", "restart", "filmkorn-lsyncd.service"], check=False) # TODO: try reload instead
        # Show the appropriate ready screen after config switch completes (only if not in menu mode)
        if not shutting_down and not menu_mode:
            if storage_location == 1:
                show_screen("ready-to-scan-local")
            elif storage_location == 0:
                show_screen("ready-to-scan-net")
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
        last_available = available
        last_increase_at = time.time()
        restarted_lsyncd = False
        no_progress_timeout_s = 15
        while True:
            sleep(1)
            available = get_available_disk_space()
            if available > last_available:
                last_available = available
                last_increase_at = time.time()
            if not restarted_lsyncd and time.time() - last_increase_at >= no_progress_timeout_s:
                logging.warning("No disk space increase detected; restarting filmkorn-lsyncd.service")
                subprocess.run(
                    ["sudo", "systemctl", "restart", "filmkorn-lsyncd.service"],
                    check=False,
                )
                last_increase_at = time.time()
                restarted_lsyncd = True
            if available >= DISK_SPACE_WAIT_THRESHOLD * 2:
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

    if current_screen in SCAN_BLOCKING_SCREENS:
        logging.info("Skipping initial screen (current blocking screen: %s)", current_screen)
    elif arg_bytes[2] == 0:
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
    global _last_frame_sensor_ts, _last_frame_mono_ts
    if no_camera:
        return
    # Record when CMD_SHOOT_RAW arrived (≈ motor-stop time in monotonic clock).
    cmd_received_mono = time.monotonic()
    camera_start()
    if state.raws_path is None or not os.path.isdir(os.path.dirname(state.raws_path)):
        logging.error("RAWs path inaccessible; stopping scan")
        state.stop_scan()
        return
    camera.set_controls({
        "AeEnable": False,
        "ExposureTime": shutter_speed,
        "AnalogueGain": 1.0,  # ISO 100 on HQ camera (IMX477)
    })
    start_time = time.time()
    request = None
    try:
        if state.warmup_needed:
            for _ in range(5):
                warmup = camera.capture_request()
                try:
                    pass
                finally:
                    warmup.release()
            state.warmup_needed = False

            attempts = 6
            for i in range(attempts):
                candidate = camera.capture_request()
                try:
                    meta = candidate.get_metadata()
                    exposure = meta.get("ExposureTime")
                    tolerance = max(200, int(shutter_speed * 0.05))
                    if exposure is not None and abs(exposure - shutter_speed) <= tolerance:
                        request = candidate
                        break
                finally:
                    if request is not candidate:
                        candidate.release()

        discarded = 0
        is_full_res = (current_resolution_switch == 0)
        min_discard = DRAIN_MIN_DISCARD_4K if is_full_res else DRAIN_MIN_DISCARD_2K
        cutoff_margin_ns = DRAIN_CUTOFF_MARGIN_NS_4K if is_full_res else DRAIN_CUTOFF_MARGIN_NS_2K
        if request is None:
            # Buffer drain rules (summary):
            # 1) Prefer SensorTimestamp-based cutoff when we have a recent anchor frame.
            #    Accept first frame with SensorTimestamp > (last_ts + elapsed_since_last + margin),
            #    while discarding at least min_discard frames.
            # 2) If no recent anchor, fall back to time-based drain using time.monotonic(),
            #    still honoring min_discard.
            # 3) If exposure is very long (>50ms), extend settle time before accepting a frame.
            if shutter_speed > 50_000:
                # Long exposures: wait extra time so we don't accept a transport-era frame.
                motor_settle_s = 0.15
                drain_until = time.monotonic() + motor_settle_s + shutter_speed / 1_000_000
                while True:
                    candidate = camera.capture_request()
                    if time.monotonic() >= drain_until and discarded >= min_discard:
                        request = candidate
                        break
                    discarded += 1
                    candidate.release()
            else:
                # Drain stale transport-era frames using per-frame calibrated
                # SensorTimestamp comparison.
                #
                # The original SensorTimestamp approach (vs CLOCK_BOOTTIME) failed
                # after ~30 s because the IMX477 oscillator drifts ~1000 ppm from
                # the Pi's system clock, accumulating ~30 ms of error in 30 s.
                #
                # The fixed-deadline approach (time.monotonic()) fails under I/O
                # load: when the Pi is busy writing DNGs, capture_request() can
                # block >75 ms even for a stale buffered frame, letting a transport
                # frame slip through the deadline filter.
                #
                # Solution: compare SensorTimestamps in camera-clock space, but
                # anchor the reference to the PREVIOUS frame (not session start).
                # Only ~150 ms of monotonic time elapses between the reference frame
                # and cmd_received_mono, so the accumulated drift is < 0.2 ms —
                # negligible and correct indefinitely.
                #
                # cutoff = last_ts + elapsed_ns + 33 ms
                #   last_ts       : SensorTimestamp of last saved frame
                #   elapsed_ns    : monotonic delta → camera-clock delta (< 0.2 ms error)
                #   + 66 ms       : skip two frame periods so the accepted frame's
                #                   top row (rolling shutter) lands ≥66 ms after
                #                   motor stop, well past the mechanical settling
                #                   window (33 ms was not enough in practice).
                if _last_frame_sensor_ts is not None and \
                        (cmd_received_mono - _last_frame_mono_ts) < 10.0:
                    # SensorTimestamp-based drain: use last accepted frame as a reference.
                    # cutoff_ts is in camera-clock ns; reject frames until we're safely past motor stop.
                    elapsed_ns  = int((cmd_received_mono - _last_frame_mono_ts) * 1e9)
                    cutoff_ts   = _last_frame_sensor_ts + elapsed_ns + cutoff_margin_ns
                    while True:
                        candidate = camera.capture_request()
                        cand_ts = candidate.get_metadata().get("SensorTimestamp", 0)
                        if cand_ts > cutoff_ts and discarded >= min_discard:
                            request = candidate
                            break
                        discarded += 1
                        candidate.release()
                else:
                    # First frame of a scan (no reference yet) or scan resumed
                    # after a long pause: fall back to fixed-deadline drain.
                    # This uses time.monotonic() instead of SensorTimestamp.
                    motor_settle_s = 0.075
                    drain_until = time.monotonic() + motor_settle_s
                    while True:
                        candidate = camera.capture_request()
                        now_mono = time.monotonic()
                        if now_mono >= drain_until and discarded >= min_discard:
                            request = candidate
                            break
                        discarded += 1
                        candidate.release()

        # Anchor calibration point for next cycle's SensorTimestamp drain.
        # Must be recorded BEFORE save_dng() so that _last_frame_mono_ts is
        # close to when capture_request() returned (≈ frame capture time).
        # Recording it after save_dng() would shift the reference by 50–150 ms,
        # making cutoff_ts land before motor stop and letting transport frames
        # through.
        if DEBUG_DRAIN:
            accepted_ts = request.get_metadata().get("SensorTimestamp")
            if state.raws_path is not None:
                dng_name = os.path.basename(state.raws_path.format(state.raw_count))
            else:
                dng_name = "unknown"
            if _last_frame_sensor_ts is None or accepted_ts is None:
                logging.info("drain: accepted %s (discarded=%d) delta_ms=n/a", dng_name, discarded)
            else:
                delta_ms = (accepted_ts - _last_frame_sensor_ts) / 1_000_000.0
                note = "OK"
                if delta_ms < 50.0:
                    note = "SMALL"
                elif delta_ms > 120.0:
                    note = "LARGE"
                logging.info("drain: accepted %s (discarded=%d) delta_ms=%.1f [%s]", dng_name, discarded, delta_ms, note)
        _last_frame_sensor_ts = request.get_metadata().get("SensorTimestamp")
        _last_frame_mono_ts   = time.monotonic()
        request.save_dng(state.raws_path.format(state.raw_count), name="raw")
    finally:
        if request is not None:
            request.release()
    state.raw_count += 1
    elapsed_time = time.time() - start_time
    fps = 1 / elapsed_time if elapsed_time > 0 else 0.0
    if state.fps_history is not None:
        state.fps_history.append(fps)
        avg_fps = sum(state.fps_history) / len(state.fps_history)
        avg_count = len(state.fps_history)
    else:
        state.fps_sum += fps
        state.fps_count += 1
        avg_fps = state.fps_sum / state.fps_count
        avg_count = state.fps_count
    logging.info(
        "One raw with shutter speed %s taken and saved in %.2fs, avg %.1ffps (count %d)",
        _format_shutter_speed(shutter_speed),
        elapsed_time,
        avg_fps,
        avg_count,
    )
    update_fps_overlay(avg_fps)
    update_shutter_overlay(shutter_speed)
    check_available_disk_space()
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
    global PID_FILE_PATH, arduino, arduino_i2c_address, ssh_subprocess, state, camera, storage_location, sensor_size, preview_size, overlay_ready, overlay_supported, overlay_retry_count, overlay_retry_timer, current_resolution_switch, last_resolution_label, last_sleep_button_state, last_sleep_button_change, sleep_button_armed, dmesg_since, current_version_label
    os.chdir("/home/pi/Filmkorn-Raw-Scanner/raspi")
    
    atexit.register(cleanup_terminal)
    clear_tty1()

    # set up logging (file + direct journald when available; stdout fallback)
    logging.root.handlers.clear()
    file_handler = logging.FileHandler("scanner.log")
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(levelname)s:%(name)s:%(message)s")
    file_handler.setFormatter(formatter)
    handlers = [file_handler]
    journald_setup_error = None
    if JournalHandler is not None:
        try:
            journald_handler = JournalHandler(SYSLOG_IDENTIFIER="filmkorn-scanner")
            journald_handler.setLevel(logging.DEBUG)
            journald_handler.setFormatter(formatter)
            handlers.append(journald_handler)
        except Exception as exc:
            journald_setup_error = exc

    # Fallback for systems without python3-systemd or when JournalHandler fails.
    if len(handlers) == 1:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)

    logging.basicConfig(level=logging.DEBUG, handlers=handlers)
    if JournalHandler is None:
        logging.warning("journald: python3-systemd not available; using stdout fallback")
    elif journald_setup_error is not None:
        logging.warning("journald: failed to initialize direct handler (%s); using stdout fallback", journald_setup_error)
    else:
        logging.info("journald: direct JournalHandler enabled")
    logging.getLogger("picamera2").setLevel(logging.WARNING)
    logging.getLogger("libcamera").setLevel(logging.WARNING)

    logging.info("----------------------------------------------------------------------------------")
    _load_locale(_load_locale_setting())
    start_time = datetime.now()
    dmesg_since = start_time.strftime('%Y-%m-%d %H:%M:%S')
    logging.info("Scanner started at %s", start_time.strftime('%Y-%m-%d %H:%M:%S'))
    current_version_label = _get_version_label()
    if current_version_label:
        logging.info("Version: %s", current_version_label)

    # Ensure WiFi radio is on at scanner start (user may use captive portal, etc.)
    _wifi_radio_on()

    # Set the GPIO mode to BCM
    GPIO.setmode(GPIO.BCM)

    # --- Power up the Arduino/Controller MCU (required for I2C to respond) ---
    # The controller PCB gates 3.3V to the ATmega via GPIO16 (physical pin 36).
    GPIO.setup(UC_POWER_GPIO, GPIO.OUT, initial=GPIO.HIGH)
    sleep(UC_POWER_BOOT_DELAY_S)

    # GPIO 17 (BCM) input. "Resolution" switch is connected here.
    #   0 => Full-res RAW
    #   1 => Half-res RAW
    GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_OFF)
    resolution_switch = GPIO.input(17)
    current_resolution_switch = resolution_switch
    last_resolution_label = "4K Raw" if resolution_switch == 0 else "2K Raw"
    logging.info(f"GPIO 17 state (0=Full-res, 1=Half-res): {resolution_switch}")

    # GPIO 5 (BCM) input. "Target" switch is connected here.
    #   1 => HDD / local USB
    #   0 => Net / remote
    GPIO.setup(5, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
    # Load the target setting and initialize storage_location accordingly
    target_stored_idx = _load_target_setting()
    target_value = TARGET_OPTIONS[target_stored_idx][1]
    if target_value == 2:
        # GPIO5 mode - read from GPIO
        storage_location = GPIO.input(5)
        logging.info(f"GPIO 5 state (1=HDD/local, 0=Net/remote): {storage_location}")
    else:
        # Manual mode - use stored value
        storage_location = target_value
        logging.info(f"Manual target mode: storage_location={storage_location} (ignoring GPIO5)")
    
    if storage_location == 1:
        _ensure_usb_mount()

    # GPIO 26 (BCM) input. Sleep/wake button (momentary, active low).
    GPIO.setup(26, GPIO.IN, pull_up_down=GPIO.PUD_OFF)
    last_sleep_button_state = GPIO.input(26)
    last_sleep_button_change = time.monotonic()
    sleep_button_armed = (last_sleep_button_state == 1)


    # Instanziate things
    state = State()
    global no_camera
    try:
        if not Picamera2.global_camera_info():
            raise RuntimeError("No camera detected")
        # Use scientific tuning file - no lens shading correction, better for telecine
        # See: https://forums.kinograph.cc/t/pi-hq-camera-vs-dslr-image-fidelity/2810/32
        tuning = Picamera2.load_tuning_file('imx477_scientific.json')
        camera = Picamera2(tuning=tuning)
        global raw_format
        for candidate in camera.sensor_modes:
            if candidate.get("bit_depth") == SENSOR_BIT_DEPTH:
                raw_format = candidate.get("unpacked") or candidate.get("format")
                break
        logging.info(f"Using raw format: {raw_format}")
        overlay_ready = False
        overlay_supported = True
        overlay_retry_count = 0
        overlay_retry_timer = None
        raw_size = (4056, 3040) if resolution_switch == 0 else (2028, 1520)
        camera_config = _create_camera_config(raw_size, raw_format)
        camera.configure(camera_config)

        sensor_size = camera.camera_configuration().get("sensor", {}).get("output_size", FULL_RESOLUTION)
        preview_size = camera.camera_configuration().get("main", {}).get("size", preview_size)
        _apply_camera_controls()
        camera_start()
        overlay_ready = True
        _apply_overlay_if_ready()
    except Exception as exc:
        logging.error("Camera initialization failed: %s", exc)
        no_camera = True
        camera = None
        current_screen = "no-camera-connected"
        _show_tty_warning("No Camera Connected")

    # Check USB filesystem if in local storage mode
    if storage_location == 1 and os.path.ismount("/mnt/usb"):
        _check_usb_filesystem()

    # Switch lsyncd to the right config for the selected storage target.
    # When storage_location==1 and USB not mounted, this blocks until user plugs USB.
    switch_lsyncd_config(storage_location)

    # Seed Install Remote Scanning bundle on USB when unpaired and USB mounted.
    # Run after switch_lsyncd_config so we see USB once it has been waited for.
    if not _is_paired() and os.path.ismount("/mnt/usb"):
        _ensure_install_bundle_on_usb()
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

    # Reset Arduino menu state in case it was stuck in a menu from before restart
    # But don't reset if we need to enter menu mode due to validation failure
    global pending_menu_entry
    if not pending_menu_entry:
        try:
            tell_arduino(Command.MENU_EXIT)
            logging.info("Reset Arduino menu state on startup")
        except Exception as exc:
            logging.warning("Failed to reset Arduino menu state: %s", exc)
    else:
        # We need to enter menu mode - do it now that arduino is ready
        if tell_arduino(Command.TARGET_REENTER):
            pending_menu_entry = False
            logging.info("Entered target menu mode after arduino initialization (due to validation failure)")
        else:
            logging.error("Failed to enter target menu mode after arduino initialization")
            pending_menu_entry = False

    user_and_host = _read_user_and_host()
    host_path = _read_host_path()
    if not user_and_host or not host_path:
        logging.warning("No host computer paired yet (missing .user_and_host or .host_path).")

    # Show a first screen to indicate we are running.
    # Only require host pairing when the active target is the host computer (storage_location == 0).
    # USB and GPIO5-pointing-to-USB targets don't need a paired host to be ready.
    if storage_location != 0 or (user_and_host and host_path):
        show_ready_to_scan()
    else:
        show_screen("no-host-computer-paired-yet")
    if _verify_mcu_firmware():
        _run_mcu_flash_if_needed()
    tell_arduino(Command.TELL_INITVALUES)
    logging.info("Asked Controller about the initial values. ")

    ssh_subprocess = None

def loop():
    global target_mode, target_validation_error, target_validation_failures
    if mcu_flash_in_progress:
        time.sleep(0.05)
        return

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
        # Menu system commands
        if command == Command.MENU_ENTER:
            _enter_menu_mode()
            return
        if command == Command.MENU_EXIT:
            _exit_menu_mode()
            return
        if command == Command.MENU_PREV:
            _menu_prev()
            return
        if command == Command.MENU_NEXT:
            _menu_next()
            return
        if command == Command.MENU_SELECT:
            _menu_select()
            return
        
        if command == Command.PAIRING_ENTER:
            logging.info("pairing: received pairing enter command")
            _enter_pairing_mode()
            return
        if command == Command.PAIRING_CANCEL:
            _cancel_pairing_mode()
            return
        if command == Command.LOGS_ENTER:
            _enter_logs_mode()
            return
        if command == Command.UNPAIR_ENTER:
            _enter_unpair_mode()
            return
        if unpair_mode:
            if command == Command.UNPAIR_CANCEL:
                _unpair_cancel(received[1:])
                return
            func = {
                Command.UNPAIR_PREV: _unpair_prev,
                Command.UNPAIR_NEXT: _unpair_next,
                Command.UNPAIR_CONFIRM: _unpair_confirm,
            }.get(command, None)
            if func is not None:
                func(received[1:])
            return
        if command == Command.UPDATE_ENTER:
            _enter_update_mode()
            return
        if update_mode:
            if command == Command.UPDATE_CANCEL:
                _update_cancel(received[1:])
                return
            func = {
                Command.UPDATE_PREV: _update_prev,
                Command.UPDATE_NEXT: _update_next,
                Command.UPDATE_CONFIRM: _update_confirm,
            }.get(command, None)
            if func is not None:
                func(received[1:])
            return
        if command == Command.AWB_ENTER:
            _enter_awb_mode()
            return
        if awb_mode:
            func = {
                Command.AWB_PREV: _awb_prev,
                Command.AWB_NEXT: _awb_next,
                Command.AWB_CONFIRM: _awb_confirm,
                Command.AWB_CANCEL: _awb_cancel,
            }.get(command, None)
            if func is not None:
                func(received[1:])
            return
        if command == Command.TARGET_ENTER:
            _enter_target_mode()
            return
        if target_mode:
            # Special handling: if we're in validation error and receive CANCEL, 
            # we need to re-enter target mode on Arduino since it cleared targetMode
            if command == Command.TARGET_CANCEL and target_validation_error:
                # User pressed Back from validation error - go back to target selection
                # and tell Arduino to re-enter target mode
                logging.info("target: received CANCEL while in validation error - re-entering target mode")
                target_validation_error = False
                target_validation_failures = []
                target_mode = True
                # Tell Arduino to re-enter target mode
                try:
                    tell_arduino(Command.TARGET_REENTER)
                except Exception as exc:
                    logging.warning("target: failed to tell Arduino to re-enter target mode: %s", exc)
                _show_target_selection()
                return
            global last_target_unknown_command
            func = {
                Command.TARGET_PREV: _target_prev,
                Command.TARGET_NEXT: _target_next,
                Command.TARGET_CONFIRM: _target_confirm,
                Command.TARGET_CANCEL: _target_cancel,
            }.get(command, None)
            if func is not None:
                # Reset tracking when we handle a known command
                last_target_unknown_command = None
                func(received[1:])
            elif command != Command.IDLE:
                # Only log unknown commands (not IDLE) and only when they change
                if last_target_unknown_command != command:
                    logging.warning("target: received unknown command %s (value %d) while in target_mode", command, command.value)
                    last_target_unknown_command = command
            return
        else:
            # If we receive target commands but target_mode is False, log it
            if command in (Command.TARGET_PREV, Command.TARGET_NEXT, Command.TARGET_CONFIRM, Command.TARGET_CANCEL):
                logging.warning("target: received %s but target_mode is False - state mismatch!", command)
        if command == Command.WIFI_ENTER:
            _enter_wifi_mode()
            return
        if command in (Command.WIFI_PREV, Command.WIFI_NEXT, Command.WIFI_CONFIRM, Command.WIFI_CANCEL):
            logging.info("wifi: received %s, wifi_mode=%s", command, wifi_mode)
            if wifi_mode:
                func = {
                    Command.WIFI_PREV: _wifi_prev,
                    Command.WIFI_NEXT: _wifi_next,
                    Command.WIFI_CONFIRM: _wifi_confirm,
                    Command.WIFI_CANCEL: _wifi_cancel,
                }.get(command, None)
                if func is not None:
                    func(received[1:])
            else:
                logging.warning("wifi: received %s but wifi_mode is False - state mismatch!", command)
            return
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
            if pairing_exit_pending and not sleep_mode:
                try:
                    tell_arduino(Command.PAIRING_EXIT)
                    pairing_exit_pending = False
                except Exception as exc:
                    logging.warning("pairing: failed to notify controller to exit pairing mode: %s", exc)
            if not state.scanning and not shutting_down:
                if _poll_sleep_button(now):
                    time.sleep(0.05)
                    continue
                if sleep_mode:
                    time.sleep(0.1)
                    continue
            if (
                not state.scanning
                and not shutting_down
                and (
                    current_screen in {
                        "insert-film",
                        "ready-to-scan",
                        "ready-to-scan-local",
                        "ready-to-scan-net",
                        "no-drive-connected",
                        "too-much-power",
                        "no-usb3-drive",
                        "no-camera-connected",
                    }
                    or pairing_mode
                )
            ):
                if current_screen in {"no-drive-connected", "no-camera-connected"} and idle_since is None:
                    idle_since = now
                if (
                    idle_since is not None
                    and (now - idle_since) >= 900.0
                    and current_screen != "too-much-power"
                ):
                    _enter_sleep_mode()
                    idle_since = None
                    time.sleep(0.1)
                    continue
            loop()
            if not no_camera:
                if now - last_disk_check >= (1.0 if state.scanning else 3.0):
                    check_available_disk_space()
                    last_disk_check = now
                _check_usb_power_warning()
                if (
                    not state.scanning
                    and storage_location == 1
                    and current_screen in {"ready-to-scan-local", "insert-film", "no-usb3-drive"}
                ):
                    _check_usb3_speed_warning()
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
            if not no_camera and camera is not None:
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
