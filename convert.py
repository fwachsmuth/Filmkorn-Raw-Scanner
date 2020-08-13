"""Converts raw RPi Cam JPGs to DNGs using PyDNG

Help/usage: python convert.py -h
"""

import os
import io
import argparse
from pydng.core import RPICAM2DNG as RPiCam2DNG

def main():
    parser = argparse.ArgumentParser(
        description="convert RPi Cam JPEGs in a dir to DNGs")
    parser.add_argument(
        '-i', '--input', default=os.getcwd(), type=str,
        help="(default: .)", metavar='<input dir>')
    parser.add_argument(
        '-o', '--output', type=str, help="(default: "
        + os.path.join('..', '..', 'DNGs', '') + '<current dir name>)',
        metavar='<output dir>')
    parser.add_argument(
        '--compress', help="33%% smaller files, 288%% as much conversion time", action="store_true")
    parser.add_argument(
        '--cinema-dng', help="generate output in the Adobe CinemaDNG format",
        action='store_true')
    parser.add_argument(
        '--keep-jpgs', help="keep input files", action='store_true')

    converter = RPiCam2DNG()

    args = parser.parse_args()

    images_dir = os.path.realpath(args.input)

    if not os.path.exists(images_dir):
        raise FileNotFoundError("The input dir " + images_dir + " doesn't exist")

    dir_name = os.path.basename(images_dir)
    if args.output:
        destination_dir = os.path.realpath(args.output)
    else:
        destination_dir = os.path.join(os.path.dirname(
            os.path.dirname(images_dir)), 'DNGs', dir_name)
        if args.cinema_dng:
            destination_dir = os.path.join(
                destination_dir, 'CONTENTS', 'IMAGE', '000000')

    if not os.path.exists(destination_dir):
        os.makedirs(destination_dir)
    elif args.cinema_dng:
        raise FileExistsError(
            "CinemaDNG '" + os.path.dirname(os.path.dirname(
                os.path.dirname(destination_dir))) + "' already exists")

    if args.cinema_dng:
        if len(os.listdir(images_dir)) > 9999_9999:
            raise Exception("The maximum of 9999,9999 DNGs in one CinemaDNG would be exceeded")
        clip_number = 0
        dng_number = 0

    for file_name in os.listdir(images_dir):
        if file_name.lower().endswith('.jpg'):
            file = os.path.join(images_dir, file_name)
            if args.cinema_dng:
                if dng_number == 9999:
                    clip_number += 1
                    destination_dir = destination_dir[:-6] + str(clip_number).zfill(4) + '00'
                    if not os.path.exists(destination_dir):
                        os.mkdir(destination_dir)

                destination_file = os.path.join(destination_dir, dir_name + '_' + str(dng_number).zfill(4) + '.dng')
                dng_number += 1
            else:
                destination_file = os.path.join(destination_dir, file_name[:-3] + 'dng')

            with open(file, 'rb') as jpg_file, \
                 open(destination_file, 'wb') as dng_file:
                dng_file.write(converter.convert(io.BytesIO(jpg_file.read()), compress=args.compress))
            if not args.keep_jpgs:
                os.remove(file)

if __name__ == '__main__':
    main()
