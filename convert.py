"""
Converts raw RPi Cam "JPGs" to DNGs using PyDNG

# Usage

CLI:
    python3 convert.py -h

Python:
    import convert
    convert( <...> )
"""

import argparse
import io
import os
import sys
import time

from pydng.core import RPICAM2DNG as RPiCam2DNG


class CinemaDNGPicture:
    def __init__(self, input_dir: str, image_base_path: str, cinema_dng_name: str):
        self.input_dir = input_dir
        self.image_base_path = os.path.join(
            image_base_path, 'CONTENTS', 'IMAGE')

        if os.path.exists(self.image_base_path):
            raise FileExistsError(
                "CinemaDNG '"
                + os.path.dirname(os.path.dirname(self.image_base_path))
                + "' already exists")

        self.cinema_dng_name = cinema_dng_name
        self.clip_number = 0
        self._dng_number = 0
        self.dir_definitely_exists = False

        self.reset = self.__init__

    @property
    def dng_number(self):
        return self._dng_number

    @dng_number.setter
    def dng_number(self, value):
        if value == 10000:
            self._dng_number = 0
            self.clip_number += 1
        else:
            self._dng_number = value

    @property
    def path(self):
        clip_path = os.path.join(self.image_base_path,
                                 "{:04d}00".format(self.clip_number))
        if not self.dir_definitely_exists:
            self.dir_definitely_exists = True
            os.makedirs(clip_path, exist_ok=True)

        return os.path.join(clip_path, "{}_{:04d}.dng".format(
            self.cinema_dng_name, self.dng_number))


def convert(input: str, output: str = None, compress=False, cinema_dng=False,
            keep_jpgs=False, keep_running=False):

    input = os.path.realpath(input)

    if not os.path.exists(input):
        raise FileNotFoundError("The input dir " + input + " does not exist")

    split_input = input.split(os.sep)

    if output:
        output = os.path.realpath(output)
    else:
        if len(split_input) < 3:
            raise Exception(
                "Your input folder must be at least on the 3rd layer of your"
                "folder structure if you did not specify an output folder")

        output = os.path.join(os.path.dirname(input), 'DNGs')

    cinema_dng_picture = None

    if cinema_dng:
        cinema_dng_picture = CinemaDNGPicture(input, output, split_input[-1])
    else:
        os.makedirs(output, exist_ok=True)

    if keep_running:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent

        def convert_new_raw(raw_path: str):
            raw_path = os.path.realpath(raw_path)

            convert_raw(
                raw_path, input, output,
                compress, cinema_dng_picture, keep_jpgs)

        class NewRawEventHandler(FileSystemEventHandler):
            def on_created(self, event: FileCreatedEvent):
                convert_new_raw(event.src_path)

            def on_moved(self, event: FileMovedEvent):
                convert_new_raw(event.dest_path)

        event_handler = NewRawEventHandler()
        observer = Observer()
        observer.schedule(event_handler, input, recursive=True)

    no_jpg_error = True

    for file in find_files(input):
        if convert_raw(
                file, input, output,
                compress, cinema_dng_picture, keep_jpgs):

            no_jpg_error = False

    if keep_running:
        return observer

    if no_jpg_error:
        raise FileNotFoundError(
            "No JPG files found that were not already converted")


def convert_raw(raw_path: str, input: str, output: str, compress: bool,
                cinema_dng_picture: CinemaDNGPicture, keep_jpgs: bool):

    if raw_path[-4:].lower() != '.jpg':
        return False

    if cinema_dng_picture:
        raw_dirname = os.path.dirname(raw_path)
        if cinema_dng_picture.input_dir != raw_dirname:
            cinema_dng_picture.reset(
                raw_dirname, os.path.dirname(output + raw_path[len(input):]),
                os.path.basename(raw_dirname))

        dest_file = cinema_dng_picture.path
        cinema_dng_picture.dng_number += 1
    else:
        dest_file = output + raw_path[len(input):-3] + 'dng'
        os.makedirs(os.path.dirname(dest_file), exist_ok=True)

    if os.path.exists(dest_file):
        return False

    converter = RPiCam2DNG()
    with open(raw_path, 'rb') as jpg_file, \
            open(dest_file, 'wb') as dng_file:
        dng_file.write(converter.convert(
            io.BytesIO(jpg_file.read()), compress=compress))

    print(raw_path + " converted to " + dest_file)

    if not keep_jpgs:
        os.remove(raw_path)

    return True


def find_files(dir: str):
    files = []

    for root, _, filenames in os.walk(dir):
        for filename in filenames:
            files.append(os.path.join(root, filename))

    files.sort()

    return files


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="convert RPi Cam JPGs in a dir to DNGs")
    parser.add_argument(
        '-i', '--input', default=os.getcwd(), type=str,
        help="(default: .)", metavar="<input dir>")
    parser.add_argument(
        '-o', '--output', type=str, help="(default: <input dir"
        + os.path.join('>', '..', 'DNGs', '…'),
        metavar="<output dir>")
    parser.add_argument(
        '--compress', help="approx. 33%% smaller files, 288%% as much conversion time",
        action='store_true')
    parser.add_argument(
        '--cinema-dng', help="generate output in the Adobe CinemaDNG format",
        action='store_true')
    parser.add_argument(
        '--keep-jpgs', help="keep input files", action='store_true')
    parser.add_argument(
        '--keep-running', help="actively watch the input dir and all subdirs",
        action='store_true')

    args = parser.parse_args()

    # Call function convert with the command-line args as keyworded python args
    observer = convert(**vars(args))

    if observer:
        import atexit

        @atexit.register
        def exit_handler():
            observer.stop()
            observer.join()

        observer.start()
        while True:
            time.sleep(1)
else:
    sys.modules[__name__] = convert
