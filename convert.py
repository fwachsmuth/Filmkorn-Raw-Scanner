"""
Converts raw RPi Cam JPEGs to DNGs using PyDNG

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

from pydng.core import RPICAM2DNG as RPiCam2DNG

def convert(input: str, output: str=None, compress=False, cinema_dng=False, keep_jpgs=False):
    converter = RPiCam2DNG()

    input = os.path.realpath(input)

    if not os.path.exists(input):
        raise FileNotFoundError("The input dir " + input + " doesn't exist")

    dir_name = os.path.basename(input)
    if output:
        output = os.path.realpath(output)
    else:
        output = os.path.join(os.path.dirname(
            os.path.dirname(input)), 'DNGs', dir_name)
        if cinema_dng:
            output = os.path.join(
                output, 'CONTENTS', 'IMAGE', '000000')

    if cinema_dng and os.path.exists(output):
        raise FileExistsError(
            "CinemaDNG '" + os.path.dirname(os.path.dirname(
                os.path.dirname(output))) + "' already exists")
                
    os.makedirs(output, exist_ok=True)

    if cinema_dng:
        clip_number = 0
        dng_number = 0

    no_jpg_error = True

    for file_name in os.listdir(input):
        if not file_name.lower().endswith('.jpg'):
            continue

        no_jpg_error = False

        file = os.path.join(input, file_name)
        if cinema_dng:
            if dng_number == 9999:
                clip_number += 1
                output = output[:-6] + str(clip_number).zfill(4) + '00'
                os.mkdir(output, exist_ok=True)

            destination_file = os.path.join(output, dir_name + '_' + str(dng_number).zfill(4) + '.dng')
            dng_number += 1
        else:
            destination_file = os.path.join(output, file_name[:-3] + 'dng')

        with open(file, 'rb') as jpg_file, \
             open(destination_file, 'wb') as dng_file:
            print(file + "; " + destination_file)
            dng_file.write(converter.convert(io.BytesIO(jpg_file.read()), compress=compress))

        if not keep_jpgs:
            os.remove(file)

    if no_jpg_error:
        raise FileNotFoundError("No JPG files found")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="convert RPi Cam JPEGs in a dir to DNGs")
    parser.add_argument(
        '-i', '--input', default=os.getcwd(), type=str,
        help="(default: .)", metavar='<input dir>')
    parser.add_argument(
        '-o', '--output', type=str, help="(default: <input dir"
        + os.path.join('>', '..', '..', 'DNGs', '<') + 'current dir name>)',
        metavar='<output dir>')
    parser.add_argument(
        '--compress', help="approx. 33%% smaller files, 288%% as much conversion time",
        action="store_true")
    parser.add_argument(
        '--cinema-dng', help="generate output in the Adobe CinemaDNG format",
        action='store_true')
    parser.add_argument(
        '--keep-jpgs', help="keep input files", action='store_true')
    
    # Call function convert with the command-line args as keyworded python args
    convert(**vars(parser.parse_args()))
else:
    sys.modules[__name__] = convert
