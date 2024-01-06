"""
Converts raw data attached in the EXIF blob of Raspi HQ Cam "JPGs" to DNGs using PyDNG

# Usage

CLI:
    python3 convert.py -h

Python:
    import convert
    convert( <...> )
"""

import abc
import argparse
import io
import os
import sys
import time

from pidng.core import RPICAM2DNG as RPiCam2DNG

class OutputDir(abc.ABC):
    def __init__(self, input: str, output: str):
        self.input_len = len(input)
        self.output = output

    @abc.abstractmethod
    def path_of_image(self, jpg_path: str) -> str:
        pass

class NormalOutputDir(OutputDir):
    def __init__(self, input: str, output: str):
        super().__init__(input, output)
        self.jpg_dirname = ""
        self.dng_dirname = ""

    def path_of_image(self, jpg_path: str) -> str:
        jpg_dirname = os.path.dirname(jpg_path)
        if self.jpg_dirname != jpg_dirname:
            self.jpg_dirname = jpg_dirname
            self.dng_dirname = self.output + jpg_dirname[self.input_len:]
            os.makedirs(self.dng_dirname, exist_ok=True)

        dng_basename = os.path.basename(jpg_dirname)[:-3] + "dng"
        return os.path.join(self.dng_dirname, dng_basename)

class OutputCinemaDNG(OutputDir):
    def __init__(self, input: str, output: str):
        super().__init__(input, output)
        self.jpg_dirname = ""
        self.cinema_dng_path = ""
        self.dng_dirname = ""

    def path_of_image(self, jpg_path: str) -> str:
        jpg_dirname = os.path.dirname(jpg_path)
        jpg_basename = os.path.basename(jpg_path)
        if self.jpg_dirname != jpg_dirname:
            self.jpg_dirname = jpg_dirname
            self.cinema_dng_path = self.output + jpg_dirname[self.input_len:]

        dng_dirname = os.path.join(
            self.cinema_dng_path, "CONTENTS", "IMAGE", jpg_basename[:4] + "00")
        if self.dng_dirname != dng_dirname:
            self.dng_dirname = dng_dirname
            os.makedirs(dng_dirname, exist_ok=True)

        dng_basename = jpg_basename[:-3] + "dng"
        return os.path.join(dng_dirname, dng_basename)

def convert(input: str, output: str=None, compress=False, cinema_dng=False,
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

    if cinema_dng:
        output_dir: OutputDir = OutputCinemaDNG(input, output)
    else:
        output_dir: OutputDir = NormalOutputDir(input, output)

    if keep_running:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent

        def convert_new_raw(event_handler, jpg_path: str):
            jpg_path = os.path.realpath(jpg_path)

            try:
                convert_raw(jpg_path, compress, output_dir, keep_jpgs)
            except FileNotFoundError:
                pass

        class NewRawEventHandler(FileSystemEventHandler):
            def __init__(self):
                self.previous_jpg_number = -1

            def on_created(self, event: FileCreatedEvent):
                convert_new_raw(self, event.src_path)

            def on_moved(self, event: FileMovedEvent):
                convert_new_raw(self, event.dest_path)

        event_handler = NewRawEventHandler()
        observer = Observer()
        observer.schedule(event_handler, input, recursive=True)

    no_jpg_error = True

    for jpg_path in find_files(input):
        if convert_raw(jpg_path, compress, output_dir, keep_jpgs):

            no_jpg_error = False

    if keep_running:
        return observer

    if no_jpg_error:
        raise FileNotFoundError(
            "No JPG files found that were not already converted")

def convert_raw(jpg_path: str, compress: bool,
                output_dir: OutputDir, keep_jpgs: bool):

    if jpg_path[-4:].lower() != '.jpg':
        return False

    dng_path = output_dir.path_of_image(jpg_path)

    if os.path.exists(dng_path) or os.path.getsize(jpg_path) == 0:
        if not keep_jpgs:
            os.remove(jpg_path)

        return False

    converter = RPiCam2DNG()
    with open(jpg_path, 'rb') as jpg_file, \
            open(dng_path, 'wb') as dng_file:
        dng_file.write(converter.convert(
            io.BytesIO(jpg_file.read()), compress=compress))

    if not keep_jpgs:
        os.remove(jpg_path)

    print(jpg_path, "converted to", dng_path)

    return True

def find_files(dir: str):
    files = []

    for dirpath, _, filenames in os.walk(dir):
        if len(filenames) == 0:
            os.rmdir(dirpath)
            continue

        for filename in filenames:
            files.append(os.path.join(dirpath, filename))

    files.sort()

    return files

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="convert RPi HQ Cam Raws in a dir to DNGs")
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
        print("Started watchdog")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print()
            sys.exit(1)
else:
    sys.modules[__name__] = convert
