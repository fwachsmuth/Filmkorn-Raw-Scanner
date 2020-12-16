from pydng.core import RPICAM2DNG
import os

def files(path):
    for file in os.listdir(path):
        if os.path.isfile(os.path.join(path, file)):
            if ".jpg" in file:
                yield os.path.join(path, file)
for file in files("/Volumes/Daten/Movies/yosemite"):
    RPICAM2DNG().convert(file, compress=True)
